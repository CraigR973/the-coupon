"""Scoring — settle picks against the provider's results and rank the leaderboard.

The rule: a winning pick scores ``round(odds_at_pick × 10)`` (long shots pay more), a
losing or void pick scores nothing. Season standing is the cumulative sum per member.

``resolve_pick`` and ``points_for`` are pure (no DB) so the maths and the
:class:`~src.services.odds_provider.EventSettlement` mapping are unit-tested directly;
``settle_gameweek`` and ``standings`` apply them over the database.

A pick resolves on ``(market, outcome)`` against its *fixture's* settlement. Until ADR
0002 it resolved on a Betfair market and selection id stored on the pick itself; those
columns are gone (revision ``005``) because ``(fixture, market, outcome)`` is already the
league's uniqueness key and is the same in every provider's vocabulary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile
from src.services.odds_provider import (
    EventSettlement,
    Market,
    OddsProvider,
    Outcome,
)

_POINTS_MULTIPLIER = 10


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def points_for(odds: Decimal) -> int:
    """Points a winning pick at ``odds`` scores: ``round(odds × 10)``.

    Rounds half **up** (``2.05`` → ``21``, not Python's banker's-rounding ``20``) so the
    reward is predictable for players.
    """
    return int((odds * _POINTS_MULTIPLIER).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class PickResolution(BaseModel):
    """The outcome of scoring one pick against its market's settlement."""

    status: PickStatus
    points: int


def resolve_pick(
    market: PickMarket,
    outcome: PickOutcome,
    odds: Decimal,
    settlement: EventSettlement,
) -> PickResolution | None:
    """Score a single pick against its fixture's settlement.

    Returns ``None`` — leave the pick pending — when the fixture has no result yet, or
    when it has one but *this* market does not. That distinction is what stops a
    half-settled fixture from voiding picks that are merely still waiting.

    Once the market has settled: ``won`` when the outcome won, ``lost`` when it did not,
    and ``void`` when the fixture was postponed or abandoned, or the outcome has vanished
    from a settled market (a withdrawn selection). A void pick scores nothing but is not
    counted as a loss.
    """
    if not settlement.settled:
        return None
    if settlement.void:
        return PickResolution(status=PickStatus.void, points=0)
    if Market(market.value) not in settlement.settled_markets:
        return None
    result = next(
        (
            o
            for o in settlement.outcomes
            if o.market == Market(market.value) and o.outcome == Outcome(outcome.value)
        ),
        None,
    )
    if result is None:
        return PickResolution(status=PickStatus.void, points=0)
    if result.won:
        return PickResolution(status=PickStatus.won, points=points_for(odds))
    return PickResolution(status=PickStatus.lost, points=0)


async def settle_gameweek(
    db: AsyncSession, gameweek: Gameweek, settlements: list[EventSettlement]
) -> int:
    """Apply event settlements to a gameweek's pending picks; returns the count resolved.

    Idempotent and incremental: only pending picks whose fixture has a result are scored,
    so the scheduler can call this repeatedly as results land. Once no pending picks
    remain, the gameweek flips to ``settled``. Does not commit — the caller owns the
    transaction.
    """
    by_event = {s.provider_event_id: s for s in settlements if s.settled}

    result = await db.execute(
        select(Pick, Fixture.provider_event_id)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.gameweek_id == gameweek.id,
            Pick.status == PickStatus.pending,
        )
    )
    resolved = 0
    for pick, provider_event_id in result.all():
        settlement = by_event.get(provider_event_id)
        if settlement is None:
            continue
        resolution = resolve_pick(pick.market, pick.outcome, pick.odds_at_pick, settlement)
        if resolution is None:
            continue
        pick.status = resolution.status
        pick.points_awarded = resolution.points
        resolved += 1

    remaining = await db.execute(
        select(func.count())
        .select_from(Pick)
        .where(Pick.gameweek_id == gameweek.id, Pick.status == PickStatus.pending)
    )
    if remaining.scalar_one() == 0 and gameweek.status != GameweekStatus.settled:
        gameweek.status = GameweekStatus.settled
        gameweek.settled_at = _now()

    await db.flush()
    return resolved


async def pending_event_ids(db: AsyncSession, gameweek: Gameweek) -> list[str]:
    """Distinct provider event ids across a gameweek's still-pending picks.

    These are the fixtures the settle job asks the provider to resolve; a fixture with no
    pending pick (already resolved, or never picked) is skipped, which keeps the request
    count proportional to what is actually outstanding.
    """
    result = await db.execute(
        select(Fixture.provider_event_id)
        .join(Pick, Pick.fixture_id == Fixture.id)
        .where(Pick.gameweek_id == gameweek.id, Pick.status == PickStatus.pending)
        .distinct()
    )
    return list(result.scalars().all())


async def settle_gameweek_via_provider(
    db: AsyncSession, provider: OddsProvider, gameweek: Gameweek
) -> int:
    """Read a gameweek's results from the provider and settle its pending picks.

    The scheduler-facing wrapper: gather the distinct fixtures still awaiting a result, ask
    the provider to settle them, then apply the outcomes via :func:`settle_gameweek`.
    Returns the count resolved (0 when nothing is pending). Flushes but does not commit —
    the job owns the transaction.
    """
    event_ids = await pending_event_ids(db, gameweek)
    if not event_ids:
        return 0
    settlements = await provider.settle(event_ids)
    return await settle_gameweek(db, gameweek, settlements)


async def participating_league_ids(db: AsyncSession, gameweek: Gameweek) -> list[uuid.UUID]:
    """League ids holding ≥1 pick in ``gameweek`` — whose standings the settle job recomputes."""
    result = await db.execute(
        select(Pick.league_id).where(Pick.gameweek_id == gameweek.id).distinct()
    )
    return list(result.scalars().all())


class Standing(BaseModel):
    """One row of a leaderboard's season table."""

    player_id: str
    display_name: str
    total_points: int
    picks_played: int
    picks_won: int
    rank: int


async def standings(db: AsyncSession, league_id: uuid.UUID) -> list[Standing]:
    """Season leaderboard for a league: cumulative points per active member, ranked.

    Every current member gets a row (0 until they score). Members tied on total share a
    rank; display order breaks ties by wins then name.
    """
    settled = Pick.status.in_((PickStatus.won, PickStatus.lost, PickStatus.void))
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            LeagueMembership.player_id,
            display_name.label("display_name"),
            func.coalesce(func.sum(Pick.points_awarded), 0).label("total_points"),
            func.count(Pick.id).label("picks_played"),
            func.coalesce(func.sum(case((Pick.status == PickStatus.won, 1), else_=0)), 0).label(
                "picks_won"
            ),
        )
        .select_from(LeagueMembership)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .outerjoin(
            Pick,
            (Pick.player_id == LeagueMembership.player_id)
            & (Pick.league_id == LeagueMembership.league_id)
            & settled,
        )
        .where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.deleted_at.is_(None),
        )
        .group_by(LeagueMembership.player_id, display_name)
    )

    ranked = sorted(
        rows.all(),
        key=lambda r: (-int(r.total_points), -int(r.picks_won), r.display_name.lower()),
    )
    standings_out: list[Standing] = []
    for row in ranked:
        total = int(row.total_points)
        # Competition ranking: everyone with a strictly higher total is above you.
        rank = sum(1 for r in ranked if int(r.total_points) > total) + 1
        standings_out.append(
            Standing(
                player_id=str(row.player_id),
                display_name=row.display_name,
                total_points=total,
                picks_played=int(row.picks_played),
                picks_won=int(row.picks_won),
                rank=rank,
            )
        )
    return standings_out
