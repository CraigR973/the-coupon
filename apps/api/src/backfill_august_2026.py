"""Two rounds that were played before the app was watching, and two missing picks.

Batch 68. The 2-1 Hibs league played on 8 and 15 August 2026 and the product did not
exist yet; its first stored round is 22 August. This writes that history in, and adds the
two picks missing from 22 August itself.

**Mostly data, and the data is the hard part.** ``odds-api.io`` cannot supply
retrospective prices — ``odds_api.py:494`` records it, verified 2026-08-04: once a fixture
settles ``/odds`` returns it with no bookmakers and ``/odds/multi`` drops it entirely.
Both carry only what is still priced. So no amount of the provider's budget produces a
historic price: the odds are an **input** here, not an output, and a winning pick scores
``round(odds × 10)``, which makes an invented price an invented leaderboard position.
Every price below is therefore attributed in :attr:`BackfillPick.evidence`, and
``docs/backfills/2026-08-rounds.md`` says which are screenshot-evidenced and which rest on
the owner's word. One *scoreline* is in the same position — see :data:`KNOWN_SCORES`.

**Nothing here invents a result.** The picks carry no status and no points. They are
written ``pending`` and then settled by :func:`~src.services.scoring.settle_gameweek` —
the same function the 18:00 sweep calls — against settlements built from the scorelines
already stored in ``matches`` by the FotMob ingestion. That is deliberate: it makes
"``points_awarded`` recomputed rather than trusted from the insert" true by construction,
and it means a hand-written backfill and a provider-settled round are indistinguishable in
``picks``.

**It fails closed.** Every fixture, member and scoreline must resolve to exactly one row
or the whole run raises before writing anything. A backfill that guesses is worse than one
that stops, because the guess lands on a real member's record and nobody looks again.

Idempotent: a pick that already exists is left alone, so a partial run can be repeated.

Run it with::

    python -m src.backfill_august_2026 --dry-run
    python -m src.backfill_august_2026 --apply

Scope: one league, two rounds, two picks. Not a general import path — that is Batch 69's
manual-results screen, which now exists and is the right tool for anything after this.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile
from src.services.admin_ops import settlement_from_score
from src.services.gameweek import window_for
from src.services.match_link import _uk_date as uk_date
from src.services.match_link import scorelines_for
from src.services.scoring import settle_gameweek

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: The one league this batch touches.
LEAGUE_SLUG = "2-1-hibs"

#: Where each price came from. Two of the four sources are the owner's word rather than a
#: document, and the note in ``docs/backfills/2026-08-rounds.md`` says so plainly.
SLIP_08 = "bet365 slip, Sat 08 Aug 13:45, £3.50 12-fold"
SLIP_15 = "bet365 slip, £4.00 twelve-fold (settled)"
OWNER = "owner, 2026-08-24 — not documented"


@dataclass(frozen=True)
class BackfillPick:
    """One member's selection, as it was actually made.

    ``member`` is the app display name, not the nickname the coupon used: the two
    handwritten coupons name people as "Walesy", "Robbo" and "Gee", and mapping those onto
    profiles is the step where points can silently land on the wrong person. The mapping
    was confirmed with the owner on 2026-08-24 rather than inferred.
    """

    member: str
    home: str
    away: str
    market: PickMarket
    outcome: PickOutcome
    runner_name: str
    odds: Decimal
    evidence: str


@dataclass(frozen=True)
class BackfillRound:
    """One round to write, or to add picks to if it already exists."""

    starts_on: date
    picks: list[BackfillPick] = field(default_factory=list)


def _btts(member: str, home: str, away: str, odds: str, evidence: str) -> BackfillPick:
    """A both-teams-to-score Yes. ``runner_name`` is "Yes", matching every stored pick."""
    return BackfillPick(
        member=member,
        home=home,
        away=away,
        market=PickMarket.BOTH_TEAMS_TO_SCORE,
        outcome=PickOutcome.YES,
        runner_name="Yes",
        odds=Decimal(odds),
        evidence=evidence,
    )


def _win(member: str, home: str, away: str, *, on: str, odds: str, evidence: str) -> BackfillPick:
    """A match-odds win. ``on`` is the club backed, which decides HOME or AWAY."""
    if on not in (home, away):
        raise ValueError(f"{on!r} is neither side of {home} v {away}")
    return BackfillPick(
        member=member,
        home=home,
        away=away,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME if on == home else PickOutcome.AWAY,
        runner_name=on,
        odds=Decimal(odds),
        evidence=evidence,
    )


#: Saturday 8 August 2026. Twelve picks, every price off the bet365 slip.
#:
#: The slip quotes fractions; these are the decimal conversions. Cross-checked against the
#: slip's own stated return: the product of the twelve is 474.28, and 474.28 × £3.50 is
#: £1,659.99 against the slip's £1,660.24 — a 0.015% gap that is bet365's own rounding, and
#: confirmation that the conversions are right rather than plausible.
ROUND_08_AUG = BackfillRound(
    starts_on=date(2026, 8, 8),
    picks=[
        _btts("Adam wales", "Salford City", "Shrewsbury Town", "1.95", SLIP_08),
        _btts("Alan tipping", "Burton Albion", "Blackburn Rovers", "1.91", SLIP_08),
        _btts("Neal Currie", "Leyton Orient London", "Oxford United", "1.70", SLIP_08),
        _btts("Craig", "Dundee FC", "Aberdeen FC", "1.67", SLIP_08),
        _btts("Grant Moore", "St Mirren FC", "St. Johnstone FC", "1.67", SLIP_08),
        _btts("Shaun Johnstone", "Airdrieonians FC", "East Kilbride FC", "1.62", SLIP_08),
        _btts("Lewis", "Stranraer FC", "Annan Athletic FC", "1.73", SLIP_08),
        _win(
            "Josh Caldow",
            "Stockport County FC",
            "Doncaster Rovers",
            on="Stockport County FC",
            odds="1.67",
            evidence=SLIP_08,
        ),
        _win(
            "Birch", "Stoke City", "Oldham Athletic", on="Stoke City", odds="1.42", evidence=SLIP_08
        ),
        _win(
            "Scott cowie",
            "Stenhousemuir FC",
            "Greenock Morton FC",
            on="Stenhousemuir FC",
            odds="1.95",
            evidence=SLIP_08,
        ),
        _win(
            "Craig Gemmell",
            "Hamilton Academical FC",
            "Alloa Athletic FC",
            on="Hamilton Academical FC",
            odds="1.65",
            evidence=SLIP_08,
        ),
        _win(
            "Mikey stewart",
            "Ross County FC",
            "Montrose FC",
            on="Ross County FC",
            odds="1.27",
            evidence=SLIP_08,
        ),
    ],
)

#: Saturday 15 August 2026. Twelve picks, prices read as decimals off the settled slip.
ROUND_15_AUG = BackfillRound(
    starts_on=date(2026, 8, 15),
    picks=[
        _win(
            "Mikey stewart",
            "Norwich City",
            "West Bromwich Albion",
            on="Norwich City",
            odds="2.00",
            evidence=SLIP_15,
        ),
        _win(
            "Craig Gemmell",
            "Middlesbrough FC",
            "Lincoln City",
            on="Middlesbrough FC",
            odds="1.45",
            evidence=SLIP_15,
        ),
        _win(
            "Birch",
            "Plymouth Argyle",
            "Stockport County FC",
            on="Plymouth Argyle",
            odds="2.15",
            evidence=SLIP_15,
        ),
        _win(
            "Scott cowie",
            "Barnsley FC",
            "Bromley FC",
            on="Barnsley FC",
            odds="2.25",
            evidence=SLIP_15,
        ),
        # The one away pick of the round: Sheffield Wednesday at Leyton Orient.
        _win(
            "Shaun Johnstone",
            "Leyton Orient London",
            "Sheffield Wednesday",
            on="Sheffield Wednesday",
            odds="2.75",
            evidence=SLIP_15,
        ),
        _win(
            "Craig",
            "Chesterfield FC",
            "Fleetwood Town",
            on="Chesterfield FC",
            odds="1.83",
            evidence=SLIP_15,
        ),
        _win(
            "Lewis",
            "East Kilbride FC",
            "Cove Rangers FC",
            on="East Kilbride FC",
            odds="1.40",
            evidence=SLIP_15,
        ),
        _btts("Alan tipping", "Bristol City", "Millwall FC", "1.72", SLIP_15),
        _btts("Josh Caldow", "Stoke City", "Swansea City", "1.72", SLIP_15),
        _btts("Grant Moore", "Barnet FC", "Salford City", "1.66", SLIP_15),
        _btts("Neal Currie", "Grimsby Town", "Exeter City", "1.72", SLIP_15),
        _btts("Adam wales", "Aberdeen FC", "Dundee FC", "1.61", SLIP_15),
    ],
)

#: Saturday 22 August 2026 — the round that already exists, settled, with ten picks.
#: These two members' picks were never recorded. Both lost, so neither moves the
#: leaderboard; they matter for the history and for Batch 70's pick-shape figures.
ROUND_22_AUG = BackfillRound(
    starts_on=date(2026, 8, 22),
    picks=[
        _btts("Lewis", "Everton FC", "Crystal Palace", "1.70", OWNER),
        _win(
            "Josh Caldow",
            "Cove Rangers FC",
            "Peterhead FC",
            on="Peterhead FC",
            odds="2.25",
            evidence=OWNER,
        ),
    ],
)

#: Scorelines the football source does not carry, taken from the slip that settled them.
#:
#: One entry, and it is not an oversight in the ingestion. Aberdeen v Dundee on 15 August
#: is *Scotland - League Cup, Group C*, and no source The Coupon uses carries the Scottish
#: League Cup group stage — the L4 record already lists it among the three cups
#: api-football never resolved, and FotMob has nothing for it either. Production holds
#: zero finished matches in that competition, so :func:`scorelines_for` correctly returns
#: nothing.
#:
#: The result is still *evidenced*, and twice over: the settled bet365 slip prints
#: "Aberdeen 3 Dundee 0" with the leg marked lost, and the owner confirmed the same score
#: independently on 2026-08-24. So this is the same trade the odds make — a documented value
#: rather than a guess — and it is held to the same rule: :func:`_settle_from_stored_scores`
#: consults this **only** for a fixture the store cannot answer, and raises if an entry
#: here would override one it can. A fallback that can silently outrank real data is not a
#: fallback, it is a second source of truth.
KNOWN_SCORES: dict[tuple[str, str], tuple[int, int]] = {
    ("Aberdeen FC", "Dundee FC"): (3, 0),
}

ROUNDS = (ROUND_08_AUG, ROUND_15_AUG, ROUND_22_AUG)


class BackfillError(RuntimeError):
    """Something did not resolve to exactly one row. Nothing is written."""


async def _league(db: AsyncSession) -> League:
    league = (
        await db.execute(select(League).where(League.slug == LEAGUE_SLUG))
    ).scalar_one_or_none()
    if league is None:
        raise BackfillError(f"league {LEAGUE_SLUG!r} not found")
    return league


async def _members(db: AsyncSession, league: League) -> dict[str, uuid.UUID]:
    """Display name to player id, for this league's active members.

    Built once and used for every pick, so a name that matches nobody raises before any
    round is touched rather than half way through one.
    """
    rows = (
        await db.execute(
            select(Profile.display_name, Profile.id)
            .join(LeagueMembership, LeagueMembership.player_id == Profile.id)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.deleted_at.is_(None),
                Profile.deleted_at.is_(None),
            )
        )
    ).all()
    return {name: player_id for name, player_id in rows}


async def _fixture(db: AsyncSession, home: str, away: str, day: date) -> Fixture:
    """The one pooled fixture for this pairing on this day.

    Matched on the stored names exactly. Fuzzy matching is deliberately not used here:
    :mod:`src.services.match_link` may fail open because a missing scoreline costs a
    member nothing, but a backfill that attaches a pick to the wrong fixture costs them
    their record.
    """
    found = (
        (await db.execute(select(Fixture).where(Fixture.home == home, Fixture.away == away)))
        .scalars()
        .all()
    )
    on_day = [f for f in found if _uk_day(f.kickoff_utc) == day]
    if len(on_day) != 1:
        raise BackfillError(f"{home} v {away} on {day}: matched {len(on_day)} fixtures, need 1")
    return on_day[0]


def _uk_day(moment: datetime) -> date:
    """The UK calendar date a stored naive-UTC kick-off falls on.

    The same conversion :mod:`src.services.match_link` uses, reused rather than repeated:
    a 23:30 Friday kick-off is Saturday in UTC, and matching a round on the wrong day
    would find no fixture at all.
    """
    return uk_date(moment)


@dataclass
class RoundPlan:
    """What one round's run will do, resolved but not yet written."""

    starts_on: date
    gameweek_id: uuid.UUID | None
    creating: bool
    to_insert: list[tuple[BackfillPick, Fixture, uuid.UUID]] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)


async def plan(db: AsyncSession) -> list[RoundPlan]:
    """Resolve every name, fixture and member without writing anything.

    The dry run *is* this function; ``--apply`` runs it and then acts on it. That means
    the thing reviewed before the write is the thing performed by it.
    """
    league = await _league(db)
    members = await _members(db, league)
    plans: list[RoundPlan] = []

    for wanted in ROUNDS:
        existing = (
            await db.execute(
                select(Gameweek).where(
                    Gameweek.league_id == league.id, Gameweek.starts_on == wanted.starts_on
                )
            )
        ).scalar_one_or_none()
        held = (
            set()
            if existing is None
            else {
                player_id
                for (player_id,) in (
                    await db.execute(select(Pick.player_id).where(Pick.gameweek_id == existing.id))
                ).all()
            }
        )
        entry = RoundPlan(
            starts_on=wanted.starts_on,
            gameweek_id=None if existing is None else existing.id,
            creating=existing is None,
        )
        for pick in wanted.picks:
            player_id = members.get(pick.member)
            if player_id is None:
                raise BackfillError(f"{pick.member!r} is not an active member of {LEAGUE_SLUG}")
            fixture = await _fixture(db, pick.home, pick.away, wanted.starts_on)
            if player_id in held:
                entry.already_present.append(pick.member)
                continue
            entry.to_insert.append((pick, fixture, player_id))
        plans.append(entry)
    return plans


async def apply(db: AsyncSession) -> list[RoundPlan]:
    """Write the rounds, the picks, and settle them.

    **Flushes but does not commit** — the caller owns the transaction, as everything else
    in this codebase does. One transaction for all three rounds on purpose: a backfill
    that half-lands leaves a league with a round nobody can explain, and the failure modes
    here — an unresolvable fixture, a missing scoreline — are all knowable before the
    first insert, so the whole thing either happens or none of it does.
    """
    league = await _league(db)
    plans = await plan(db)

    for entry in plans:
        if not entry.to_insert:
            continue
        gameweek = await _ensure_round(db, league, entry)
        fixtures = []
        for pick, fixture, player_id in entry.to_insert:
            await _link(db, gameweek, fixture)
            db.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=gameweek.id,
                    player_id=player_id,
                    fixture_id=fixture.id,
                    market=pick.market,
                    outcome=pick.outcome,
                    runner_name=pick.runner_name,
                    odds_at_pick=pick.odds,
                    status=PickStatus.pending,
                    points_awarded=None,
                )
            )
            fixtures.append(fixture)
        await db.flush()
        await _settle_from_stored_scores(db, gameweek, fixtures)

    return plans


async def _ensure_round(db: AsyncSession, league: League, entry: RoundPlan) -> Gameweek:
    """The round for this date, created at its real instants if it does not exist.

    ``number`` is left ``NULL`` deliberately. The league's 22 August round is "Gameweek 1"
    and members were told so; numbering these 3 and 4 would put a later number on an
    earlier date, and renumbering 22 August would rewrite a name people have already used.
    The column is nullable for exactly this — a round that predates the numbering — and
    nothing keys on it: locking, settlement and scoring all read instants and status.
    """
    if entry.gameweek_id is not None:
        found = await db.get(Gameweek, entry.gameweek_id)
        if found is None:  # pragma: no cover — planned id must exist
            raise BackfillError(f"round {entry.gameweek_id} vanished mid-run")
        return found
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=entry.starts_on,
        status=GameweekStatus.locked,
        locks_at_utc=window_for(league).locks_at(entry.starts_on),
        picks_open_at_utc=None,
        number=None,
    )
    db.add(gameweek)
    await db.flush()
    entry.gameweek_id = gameweek.id
    return gameweek


async def _link(db: AsyncSession, gameweek: Gameweek, fixture: Fixture) -> None:
    existing = await db.get(GameweekFixture, (gameweek.id, fixture.id))
    if existing is None:
        db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
        await db.flush()


async def _settle_from_stored_scores(
    db: AsyncSession, gameweek: Gameweek, fixtures: list[Fixture]
) -> None:
    """Settle the round from the scorelines already in ``matches``.

    The scores come from the FotMob ingestion, which is an independent source from the
    coupons the picks came off — so the outcome of every backfilled pick is decided by
    football data rather than by the person transcribing a screenshot.

    Fails closed. :func:`~src.services.match_link.scorelines_for` returns nothing for a
    fixture it cannot resolve, which is right for a screen and wrong here: an unsettled
    backfilled pick would sit pending forever and hold the round open.
    """
    scores = await scorelines_for(db, fixtures, include_live=False)

    # A stated score may only fill a hole, never cover one. If the store *can* answer for
    # a fixture we also hold a value for, the two are a disagreement to be looked at
    # rather than resolved silently in favour of the screenshot.
    overriding = [
        f"{f.home} v {f.away}"
        for f in fixtures
        if f.id in scores and (f.home, f.away) in KNOWN_SCORES
    ]
    if overriding:
        raise BackfillError(f"stated score would override stored data for: {', '.join(overriding)}")

    missing = [
        f"{f.home} v {f.away}"
        for f in fixtures
        if f.id not in scores and (f.home, f.away) not in KNOWN_SCORES
    ]
    if missing:
        raise BackfillError(f"no stored scoreline for: {', '.join(missing)}")

    settlements = []
    for fixture in fixtures:
        found = scores.get(fixture.id)
        home_goals, away_goals = (
            (found.home_goals, found.away_goals)
            if found is not None
            else KNOWN_SCORES[(fixture.home, fixture.away)]
        )
        settlements.append(settlement_from_score(fixture.provider_event_id, home_goals, away_goals))
    resolved = await settle_gameweek(db, gameweek, settlements)
    log.info(
        "backfilled round settled",
        starts_on=str(gameweek.starts_on),
        fixtures=len(fixtures),
        picks_resolved=resolved,
    )


def _describe(plans: list[RoundPlan]) -> str:
    lines = []
    for entry in plans:
        verb = "create" if entry.creating else "add to"
        lines.append(
            f"{entry.starts_on}: {verb} round, insert {len(entry.to_insert)} pick(s)"
            + (
                f", skip {len(entry.already_present)} already present"
                if entry.already_present
                else ""
            )
        )
        for pick, fixture, _ in entry.to_insert:
            lines.append(
                f"    {pick.member:<16} {fixture.home} v {fixture.away}"
                f"  {pick.market.value}/{pick.outcome.value} @ {pick.odds}  [{pick.evidence}]"
            )
    return "\n".join(lines)


async def _run(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not apply_changes:
            print(_describe(await plan(db)))
            print("\nDRY RUN — nothing written.")
            return
        plans = await apply(db)
        await db.commit()
        print(_describe(plans))
        print(f"\nAPPLIED at {datetime.now(UTC).isoformat()}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="resolve everything, write nothing")
    group.add_argument("--apply", action="store_true", help="write and settle")
    args = parser.parse_args()
    asyncio.run(_run(apply_changes=bool(args.apply)))


if __name__ == "__main__":
    main()
