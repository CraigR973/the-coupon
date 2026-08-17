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
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile
from src.services.coupon import combined_odds
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
    """Apply event settlements to a round's pending picks; returns the count resolved.

    Idempotent and incremental: only pending picks whose fixture has a result are scored,
    so the scheduler can call this repeatedly as results land. Once no pending picks
    remain, the round flips to ``settled``. Does not commit — the caller owns the
    transaction.

    Since Batch 14 a round belongs to one league, so "no pending picks remain" means
    that league's picks. It used to mean *every* league's, which held one league's
    round open until an unrelated league had also finished settling.
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


async def pending_event_ids(
    db: AsyncSession, gameweeks: Sequence[Gameweek]
) -> dict[uuid.UUID, list[str]]:
    """Distinct provider event ids per round, across each round's still-pending picks.

    These are the fixtures the settle job asks the provider to resolve; a fixture with no
    pending pick (already resolved, or never picked) is skipped, which keeps the request
    count proportional to what is actually outstanding. A round with nothing pending has
    no key.

    Answered for the whole run in one query rather than one per round, because the job
    settles every settleable round together — and because a fixture is one pooled row, two
    leagues holding the same match report the same ``provider_event_id`` here, which is
    what lets the caller ask for it once.
    """
    if not gameweeks:
        return {}
    result = await db.execute(
        select(Pick.gameweek_id, Fixture.provider_event_id)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.gameweek_id.in_([gameweek.id for gameweek in gameweeks]),
            Pick.status == PickStatus.pending,
        )
        .distinct()
    )
    by_gameweek: dict[uuid.UUID, list[str]] = {}
    for gameweek_id, provider_event_id in result.all():
        by_gameweek.setdefault(gameweek_id, []).append(provider_event_id)
    return by_gameweek


async def settle_gameweeks_via_provider(
    db: AsyncSession, provider: OddsProvider, gameweeks: Sequence[Gameweek]
) -> dict[uuid.UUID, int]:
    """Settle several rounds against a **single** shared read of the provider.

    Gather every round's outstanding fixtures, de-duplicate them across the whole run, ask
    the provider once, then fan the results back out per round via :func:`settle_gameweek`
    — which picks out the settlements its own picks reference and ignores the rest.

    The de-duplication is the point. Settlement costs one provider request per fixture, and
    it used to be driven a round at a time, so two leagues playing the same Saturday paid
    separately for every match they both held — against a plan allowing 100 requests an
    hour. Five leagues on one window could approach 75 requests in a run, mostly
    duplicates, and the symptom of running out is not an error but picks staying
    ``pending`` for good. The bill is now the number of *distinct* fixtures outstanding
    rather than the number of leagues holding them, which is the rule
    :func:`~src.services.gameweek.discover_fixtures` already applies to slate windows.

    Returns the count resolved per gameweek id; a round with nothing pending is absent.
    Flushes but does not commit — the job owns the transaction.
    """
    by_gameweek = await pending_event_ids(db, gameweeks)
    event_ids = list(dict.fromkeys(eid for ids in by_gameweek.values() for eid in ids))
    if not event_ids:
        return {}
    settlements = await provider.settle(event_ids)
    return {
        gameweek.id: await settle_gameweek(db, gameweek, settlements)
        for gameweek in gameweeks
        if gameweek.id in by_gameweek
    }


async def settle_gameweek_via_provider(
    db: AsyncSession, provider: OddsProvider, gameweek: Gameweek
) -> int:
    """Read one round's results from the provider and settle its pending picks.

    :func:`settle_gameweeks_via_provider` over a single round, for the callers that
    genuinely hold one — the scheduler passes its whole run at once so the shared fixtures
    are only paid for once. Returns the count resolved (0 when nothing is pending).
    """
    return (await settle_gameweeks_via_provider(db, provider, [gameweek])).get(gameweek.id, 0)


class Standing(BaseModel):
    """One row of a leaderboard's season table."""

    player_id: str
    display_name: str
    total_points: int
    picks_played: int
    picks_won: int
    rank: int


def _rank_rows(rows: Sequence[Any]) -> list[Standing]:
    """Order one league's aggregated rows and assign competition ranks."""
    ranked = sorted(
        rows,
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


async def standings_by_league(
    db: AsyncSession, league_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Standing]]:
    """Season tables for several leagues at once, keyed by league id.

    One query for the whole set rather than one per league, so a caller holding a
    member's leagues — the cross-league summary — costs the same number of round trips
    whether they are in one league or six. A league with no active members has no key.

    The per-league table is exactly what :func:`standings` returns, because that is
    now this function over a single id: there is one ranking rule in the codebase and
    the leaderboard, the profile and the summary all read it.
    """
    if not league_ids:
        return {}

    settled = Pick.status.in_((PickStatus.won, PickStatus.lost, PickStatus.void))
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            LeagueMembership.league_id,
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
            LeagueMembership.league_id.in_(league_ids),
            LeagueMembership.deleted_at.is_(None),
        )
        .group_by(LeagueMembership.league_id, LeagueMembership.player_id, display_name)
    )

    grouped: dict[uuid.UUID, list[Any]] = {}
    for row in rows.all():
        grouped.setdefault(row.league_id, []).append(row)
    return {league_id: _rank_rows(league_rows) for league_id, league_rows in grouped.items()}


async def standings(db: AsyncSession, league_id: uuid.UUID) -> list[Standing]:
    """Season leaderboard for a league: cumulative points per active member, ranked.

    Every current member gets a row (0 until they score). Members tied on total share a
    rank; display order breaks ties by wins then name.
    """
    return (await standings_by_league(db, [league_id])).get(league_id, [])


class GameweekResult(BaseModel):
    """One settled round's headline outcome — who won it and how the coupon landed."""

    gameweek_id: str
    starts_on: date
    winner_names: list[str]
    winner_points: int
    leg_count: int
    combined_odds: float
    all_won: bool | None


async def gameweek_results(db: AsyncSession, league_id: uuid.UUID) -> list[GameweekResult]:
    """Every settled round for a league, newest first — the results list.

    The winner is whoever's pick scored the most that round; a tie names every player
    who shares the top score rather than picking one arbitrarily. ``all_won`` and
    ``combined_odds`` mirror :func:`src.services.coupon.build_coupon`'s coupon-outcome
    maths, computed here over every settled round in one query rather than one per row.
    A settled round with no picks in this league (vacuously settled) still gets a row,
    with no winner and an empty coupon.
    """
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            Gameweek.id,
            Gameweek.starts_on,
            display_name.label("display_name"),
            Pick.points_awarded,
            Pick.status,
            Pick.odds_at_pick,
        )
        .select_from(Gameweek)
        .outerjoin(Pick, (Pick.gameweek_id == Gameweek.id) & (Pick.league_id == league_id))
        .outerjoin(
            LeagueMembership,
            (LeagueMembership.player_id == Pick.player_id)
            & (LeagueMembership.league_id == league_id),
        )
        .outerjoin(Profile, Profile.id == Pick.player_id)
        .where(Gameweek.league_id == league_id, Gameweek.status == GameweekStatus.settled)
        .order_by(Gameweek.starts_on.desc())
    )

    by_gameweek: dict[uuid.UUID, tuple[date, list[tuple[str, int, PickStatus, Decimal]]]] = {}
    for gw_id, starts_on, name, points, status_, odds in rows.all():
        _, picks = by_gameweek.setdefault(gw_id, (starts_on, []))
        if points is not None:
            picks.append((name, int(points), status_, odds))

    results: list[GameweekResult] = []
    for gw_id, (starts_on, picks) in by_gameweek.items():
        top_points = max((p for _, p, _, _ in picks), default=0)
        winner_names = sorted({name for name, p, _, _ in picks if p == top_points})
        results.append(
            GameweekResult(
                gameweek_id=str(gw_id),
                starts_on=starts_on,
                winner_names=winner_names,
                winner_points=top_points,
                leg_count=len(picks),
                combined_odds=float(combined_odds([odds for _, _, _, odds in picks])),
                all_won=all(status_ == PickStatus.won for _, _, status_, _ in picks)
                if picks
                else None,
            )
        )
    results.sort(key=lambda r: r.starts_on, reverse=True)
    return results
