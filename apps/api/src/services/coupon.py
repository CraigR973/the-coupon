"""The combined coupon — everyone's picks for a gameweek as one accumulator.

A leaderboard's members each hold one unique selection; stacked together they form a
single acca to reference on a real book. The combined price is the product of every leg's
snapshotted odds. ``combined_odds`` is pure (unit-tested directly); ``build_coupon``
assembles the legs from the database.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.pick import Pick, PickStatus
from src.models.profile import Profile
from src.services.gameweek import is_in_play
from src.services.match_link import scorelines_for

_TWO_DP = Decimal("0.01")


def combined_odds(odds: Sequence[Decimal]) -> Decimal:
    """Accumulator price: the product of the legs, to 2 dp. Empty → ``1.00``.

    The caller decides which legs are in it. Since Batch 156 that excludes voided ones:
    ``build_coupon`` filters before it gets here, so this stays the arithmetic and the
    rule about void lives with the data that knows about it.
    """
    product = Decimal(1)
    for value in odds:
        product *= value
    return product.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


class CouponLeg(BaseModel):
    """One member's pick, as it reads on the shared coupon.

    The last three fields are Batch 67 and every one of them is **optional with a
    default**, because Vercel deploys the web app from ``main`` on merge while the API
    waits for ``/ship-prod`` — a required field breaks the coupon for everyone in the gap.
    Batches 38, 41 and 48 each recorded that trap.
    """

    player_id: str
    player_name: str
    fixture_id: str
    home: str
    away: str
    competition: str
    market: str
    outcome: str
    runner_name: str
    odds: float
    status: str
    #: What this pick scored, once the round settled. ``None`` while it is still running,
    #: and also for a pick settled before ``points_awarded`` existed.
    points_awarded: int | None = None
    #: The score, when the leg's fixture could be resolved to a match carrying one.
    #: Both are ``None`` together, and ``None`` means *no score to show* rather than
    #: nil-nil — a wrong scoreline against a real member's pick is worse than none, so
    #: :mod:`src.services.match_link` fails open into this.
    home_goals: int | None = None
    away_goals: int | None = None
    #: Whether that score is the result or the state of play (Batch 72). ``False`` only
    #: on a round being played; a screen that renders a running score the same way it
    #: renders a final one tells a member their pick has landed when it has not.
    score_is_final: bool = True


class Coupon(BaseModel):
    """A leaderboard's combined accumulator for one gameweek."""

    gameweek_id: str
    status: str
    leg_count: int
    combined_odds: float
    legs: list[CouponLeg]
    all_won: bool | None  # None until the gameweek is settled
    #: How many of ``leg_count`` were voided and so left out of ``combined_odds``
    #: (Batch 156). Carried rather than left for the client to recount, so the screen and
    #: the clipboard cannot disagree about which number the price is a product of.
    #:
    #: **Optional with a default**, like every field added to this response since Batch
    #: 67: Vercel deploys the web app from ``main`` on merge while the API waits for
    #: ``/ship-prod``, so a required field breaks the coupon for everyone in the gap.
    void_leg_count: int = 0


async def build_coupon(db: AsyncSession, league_id: uuid.UUID, gameweek: Gameweek) -> Coupon:
    """Assemble the combined coupon for ``(league, gameweek)``.

    Legs are ordered by kick-off then home team so the acca reads in playing order.
    ``all_won`` is ``None`` until the gameweek settles, then ``True`` only if every leg won.

    **A settled round also carries its scorelines** (Batch 67). Between one round ending
    and the next opening this view *is* the result, and a won/lost badge is the outcome
    rather than the result — the member wants to know it finished 2-1. The scores are
    resolved through :func:`~src.services.match_link.scorelines_for`, which fails open, so
    a leg that cannot be matched to a played match simply carries no score.

    Only when settled. An unsettled round is still moving, and a partial score printed
    beside a pending pick would read as final; live scores are Batch 72.
    """
    display_name = Profile.display_name.label("player_name")
    result = await db.execute(
        select(Pick, Fixture, display_name)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .join(Profile, Profile.id == Pick.player_id)
        .where(Pick.league_id == league_id, Pick.gameweek_id == gameweek.id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )
    rows = result.all()

    # Two states carry a score, and they are not the same score. A settled round shows the
    # result; a round being played shows how it stands, marked as not final (Batch 72).
    # "Being played" is Batch 65's own `in_play` predicate, evaluated here rather than
    # restated, so the round the coupon calls current and the round it prints live scores
    # for cannot come apart.
    settled = gameweek.status == GameweekStatus.settled
    playing = not settled and await is_in_play(db, gameweek)
    scores = (
        await scorelines_for(db, [fixture for _, fixture, _ in rows], include_live=playing)
        if settled or playing
        else {}
    )

    legs: list[CouponLeg] = []
    odds: list[Decimal] = []
    for pick, fixture, player_name in rows:
        # Batch 156, owner's decision 2026-09-22. A voided leg's price used to multiply
        # into the accumulator unconditionally — production showed
        # `53.01 = 3.75 x 1.90 x 3.10(void) x 2.40`. A real accumulator settles a voided
        # leg at 1.0, and this product's own rule is that a void "scores nothing rather
        # than counting as a loss": carrying its price into the product is the
        # coupon-level version of counting it.
        #
        # The leg stays on the coupon with its frozen price, because it is still what
        # that member claimed. Only the product changes, and `void_leg_count` is what
        # lets both surfaces say so.
        if pick.status != PickStatus.void:
            odds.append(pick.odds_at_pick)
        score = scores.get(fixture.id)
        legs.append(
            CouponLeg(
                player_id=str(pick.player_id),
                player_name=player_name,
                fixture_id=str(fixture.id),
                home=fixture.home,
                away=fixture.away,
                competition=fixture.competition,
                market=pick.market.value,
                outcome=pick.outcome.value,
                runner_name=pick.runner_name,
                odds=float(pick.odds_at_pick),
                status=pick.status.value,
                points_awarded=pick.points_awarded,
                home_goals=score.home_goals if score else None,
                away_goals=score.away_goals if score else None,
                score_is_final=score.final if score else True,
            )
        )

    all_won: bool | None = None
    if settled and legs:
        all_won = all(leg.status == PickStatus.won.value for leg in legs)

    return Coupon(
        gameweek_id=str(gameweek.id),
        status=gameweek.status.value,
        leg_count=len(legs),
        combined_odds=float(combined_odds(odds)),
        legs=legs,
        all_won=all_won,
        void_leg_count=len(legs) - len(odds),
    )
