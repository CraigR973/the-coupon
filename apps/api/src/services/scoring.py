"""Scoring — settle picks against Betfair results and rank the leaderboard.

The rule: a winning pick scores ``round(odds_at_pick × 10)`` (long shots pay more), a
losing or void pick scores nothing. Season standing is the cumulative sum per member.

``resolve_pick`` and ``points_for`` are pure (no DB) so the maths and the
:class:`~src.services.betfair.MarketSettlement` mapping are unit-tested directly;
``settle_gameweek`` and ``standings`` apply them over the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.models.profile import Profile
from src.services.betfair import MarketSettlement

_POINTS_MULTIPLIER = 10
_REMOVED = "REMOVED"


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
    betfair_selection_id: int, odds: Decimal, settlement: MarketSettlement
) -> PickResolution | None:
    """Score a single pick against its market settlement.

    Returns ``None`` when the market has not settled yet (leave the pick pending). Once
    settled: the selection is ``won`` if its runner is the Betfair ``WINNER``; ``void`` if
    the runner was removed (or is absent from the closed market) so it scores nothing but
    is not counted as a loss; otherwise ``lost``.
    """
    if not settlement.settled:
        return None
    runner = next(
        (r for r in settlement.runners if r.betfair_selection_id == betfair_selection_id),
        None,
    )
    if runner is None or runner.status.upper() == _REMOVED:
        return PickResolution(status=PickStatus.void, points=0)
    if runner.won:
        return PickResolution(status=PickStatus.won, points=points_for(odds))
    return PickResolution(status=PickStatus.lost, points=0)


async def settle_gameweek(
    db: AsyncSession, gameweek: Gameweek, settlements: list[MarketSettlement]
) -> int:
    """Apply market settlements to a gameweek's pending picks; returns the count resolved.

    Idempotent and incremental: only pending picks whose market is settled are scored, so
    the scheduler can call this repeatedly as markets close. Once no pending picks remain,
    the gameweek flips to ``settled``. Does not commit — the caller owns the transaction.
    """
    by_market = {s.betfair_market_id: s for s in settlements if s.settled}

    result = await db.execute(
        select(Pick).where(
            Pick.gameweek_id == gameweek.id,
            Pick.status == PickStatus.pending,
        )
    )
    resolved = 0
    for pick in result.scalars().all():
        settlement = by_market.get(pick.betfair_market_id)
        if settlement is None:
            continue
        resolution = resolve_pick(pick.betfair_selection_id, pick.odds_at_pick, settlement)
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
