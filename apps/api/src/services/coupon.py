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

_TWO_DP = Decimal("0.01")


def combined_odds(odds: Sequence[Decimal]) -> Decimal:
    """Accumulator price: the product of the legs, to 2 dp. Empty → ``1.00``."""
    product = Decimal(1)
    for value in odds:
        product *= value
    return product.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


class CouponLeg(BaseModel):
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


class Coupon(BaseModel):
    """A leaderboard's combined accumulator for one gameweek."""

    gameweek_id: str
    status: str
    leg_count: int
    combined_odds: float
    legs: list[CouponLeg]
    all_won: bool | None  # None until the gameweek is settled


async def build_coupon(db: AsyncSession, league_id: uuid.UUID, gameweek: Gameweek) -> Coupon:
    """Assemble the combined coupon for ``(league, gameweek)``.

    Legs are ordered by kick-off then home team so the acca reads in playing order.
    ``all_won`` is ``None`` until the gameweek settles, then ``True`` only if every leg won.
    """
    display_name = Profile.display_name.label("player_name")
    result = await db.execute(
        select(Pick, Fixture, display_name)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .join(Profile, Profile.id == Pick.player_id)
        .where(Pick.league_id == league_id, Pick.gameweek_id == gameweek.id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )

    legs: list[CouponLeg] = []
    odds: list[Decimal] = []
    for pick, fixture, player_name in result.all():
        odds.append(pick.odds_at_pick)
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
            )
        )

    all_won: bool | None = None
    if gameweek.status == GameweekStatus.settled and legs:
        all_won = all(leg.status == PickStatus.won.value for leg in legs)

    return Coupon(
        gameweek_id=str(gameweek.id),
        status=gameweek.status.value,
        leg_count=len(legs),
        combined_odds=float(combined_odds(odds)),
        legs=legs,
        all_won=all_won,
    )
