"""Monday calendar dues, immutable membership provenance and the existing FIFO pool.

This module is imported by API lifecycle hooks only. Settings are loaded at call
sites so the independent payments process can keep importing legacy dues safely.
There is no provider/bank I/O here and no money earmarked to a particular week.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.profile import Profile
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    MembershipInterval,
    ProviderWork,
    TwoGame,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.schemas import UtcDatetime
from src.services.dues import RoundDue, _dues_of, _member_ledgers, _round_dates, allocate
from src.services.provider_budget import naive_utc, utc_now
from src.services.two_game_storage import LONDON, ensure_two_game_week, london_utc


def billing_bounds(label: date) -> tuple[datetime, datetime]:
    if label.weekday() != 5:
        raise ValueError("billing week must be labelled by Saturday")
    return london_utc(label - timedelta(days=5)), london_utc(label + timedelta(days=2))


def billing_label(moment: datetime) -> date:
    local = naive_utc(moment).replace(tzinfo=UTC).astimezone(LONDON).date()
    return local + timedelta(days=5 - local.weekday())


async def tracking_enabled(db: AsyncSession) -> bool:
    from src.config import settings

    with db.no_autoflush:
        return settings.two_games_enabled or bool(
            await db.scalar(select(MembershipInterval.id).limit(1))
        )


async def member_barrier(db: AsyncSession, player_id: uuid.UUID, *, deleting: bool = False) -> bool:
    """Deletion snapshots a complete roster; a join never waits holding a league.

    A shared TRY lets independent joins proceed together. A deleting account owns
    the exclusive barrier before collecting its leagues, so a first join cannot
    escape that collection. Failed TRY must abort the caller's join transaction.
    """
    with db.no_autoflush:
        if not await tracking_enabled(db):
            return True
        if deleting:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 222))"),
                {"key": str(player_id)},
            )
            return True
        return bool(
            await db.scalar(
                text("SELECT pg_try_advisory_xact_lock_shared(hashtextextended(:key, 222))"),
                {"key": str(player_id)},
            )
        )


async def financial_lock(db: AsyncSession, league_id: uuid.UUID) -> bool:
    """Acquire BEFORE roster/invite/league mutations, never across external I/O.

    Previously activated provenance keeps tracking natural joins/departures even
    if a gate is subsequently disabled. Inactive installations without that
    history acquire no new lock and create no interval or monetary obligation.
    """
    from src.config import settings

    with db.no_autoflush:
        active = False
        if settings.two_games_enabled:
            active = bool(
                await db.scalar(
                    select(TwoGameRollout.league_id).where(
                        TwoGameRollout.league_id == league_id,
                        TwoGameRollout.enabled.is_(True),
                    )
                )
            )
        retained = bool(
            await db.scalar(
                select(MembershipInterval.id)
                .where(
                    MembershipInterval.league_id == league_id,
                )
                .limit(1)
            )
        )
        if not active and not retained:
            return False
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"),
            {"key": str(league_id)},
        )
    return True


async def financial_locks(db: AsyncSession, league_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    locked = set()
    for league_id in sorted(set(league_ids), key=str):
        if await financial_lock(db, league_id):
            locked.add(league_id)
    return locked


async def _rollout(db: AsyncSession, league_id: uuid.UUID) -> TwoGameRollout | None:
    from src.config import settings

    if not settings.two_games_enabled:
        return None
    row = await db.get(TwoGameRollout, league_id, populate_existing=True)
    league = await db.get(League, league_id, populate_existing=True)
    return row if row and row.enabled and league and league.deleted_at is None else None


async def _active_membership(
    db: AsyncSession,
    league_id: uuid.UUID,
    player_id: uuid.UUID,
) -> LeagueMembership | None:
    membership: LeagueMembership | None = await db.scalar(
        select(LeagueMembership)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.player_id == player_id,
            LeagueMembership.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    return membership


async def track_join(db: AsyncSession, membership: LeagueMembership) -> MembershipInterval | None:
    if not await financial_lock(db, membership.league_id):
        return None
    existing = await db.scalar(
        select(MembershipInterval)
        .where(
            MembershipInterval.league_id == membership.league_id,
            MembershipInterval.player_id == membership.player_id,
            MembershipInterval.left_at.is_(None),
        )
        .with_for_update()
    )
    if existing is not None:
        return existing
    interval = MembershipInterval(
        league_id=membership.league_id,
        player_id=membership.player_id,
        joined_at=membership.joined_at,
        provenance="recorded_membership",
    )
    db.add(interval)
    await db.flush()
    return interval


@dataclass(frozen=True)
class Interval:
    id: uuid.UUID | None
    joined_at: datetime
    left_at: datetime | None


@dataclass(frozen=True)
class PlannedDue:
    label: date
    interval_id: uuid.UUID | None
    owed_at: datetime


def plan_dues(
    intervals: Collection[Interval],
    first_week: date,
    through: date,
    now: datetime,
    *,
    early: bool,
) -> list[PlannedDue]:
    planned: dict[date, PlannedDue] = {}
    for interval in sorted(intervals, key=lambda item: (item.joined_at, str(item.id))):
        label = max(first_week, billing_label(interval.joined_at))
        while label <= through:
            start, end = billing_bounds(label)
            if interval.joined_at < end and (interval.left_at is None or interval.left_at > start):
                owed = max(start, interval.joined_at)
                if owed > now and early and interval.joined_at <= now and interval.left_at is None:
                    owed = now
                if (
                    owed <= now
                    and (interval.left_at is None or owed < interval.left_at)
                    and label not in planned
                ):
                    planned[label] = PlannedDue(label, interval.id, owed)
            label += timedelta(days=7)
    return sorted(planned.values(), key=lambda item: item.label)


async def _intervals(
    db: AsyncSession,
    league_id: uuid.UUID,
    player_id: uuid.UUID,
) -> list[Interval]:
    rows = await db.scalars(
        select(MembershipInterval)
        .where(
            MembershipInterval.league_id == league_id,
            MembershipInterval.player_id == player_id,
        )
        .order_by(MembershipInterval.joined_at, MembershipInterval.id)
    )
    return [Interval(row.id, row.joined_at, row.left_at) for row in rows]


async def materialize_dues(
    db: AsyncSession,
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    now: datetime,
    *,
    through: date | None = None,
    early: bool = False,
    bootstrap: bool = True,
) -> int:
    """Pair due/obligation atomically. Caller commits; no legacy reversal path."""
    if not await financial_lock(db, league_id):
        return 0
    rollout = await _rollout(db, league_id)
    if rollout is None:
        return 0
    if bootstrap:
        membership = await _active_membership(db, league_id, player_id)
        if membership is not None:
            await track_join(db, membership)
    target = through or billing_label(now)
    desired = plan_dues(
        await _intervals(db, league_id, player_id), rollout.first_week, target, now, early=early
    )
    written = 0
    existing = set(
        await db.scalars(
            select(WeeklyFeeObligation.week_label).where(
                WeeklyFeeObligation.league_id == league_id,
                WeeklyFeeObligation.player_id == player_id,
            )
        )
    )
    for due in desired:
        if due.label in existing:
            continue
        if due.interval_id is None:
            raise RuntimeError("materialisation requires persisted membership provenance")
        parent = await ensure_two_game_week(db, league_id, due.label, billing=True)
        if parent is None:
            raise RuntimeError("billing rollout changed inside its financial lock")
        start, end = billing_bounds(due.label)
        ledger = LedgerEntry(
            league_id=league_id,
            player_id=player_id,
            kind=LedgerKind.round_due,
            gameweek_id=parent.id,
            amount_pence=-100,
            occurred_at=due.owed_at,
            note=None,
        )
        db.add(ledger)
        await db.flush()
        db.add(
            WeeklyFeeObligation(
                league_id=league_id,
                player_id=player_id,
                week_id=parent.id,
                week_label=due.label,
                interval_id=due.interval_id,
                ledger_entry_id=ledger.id,
                billing_start=start,
                billing_end=end,
                owed_at=due.owed_at,
            )
        )
        await db.flush()
        written += 1
    return written


async def close_memberships(
    db: AsyncSession,
    league_ids: Collection[uuid.UUID],
    now: datetime,
    *,
    player_id: uuid.UUID | None = None,
) -> int:
    """Run before the caller ends/deactivates the roster/profile/league."""
    closed = 0
    for league_id in sorted(set(league_ids), key=str):
        if not await financial_lock(db, league_id):
            continue
        query = select(LeagueMembership).where(
            LeagueMembership.league_id == league_id, LeagueMembership.deleted_at.is_(None)
        )
        if player_id is not None:
            query = query.where(LeagueMembership.player_id == player_id)
        for membership in await db.scalars(query.order_by(LeagueMembership.player_id)):
            profile = await db.get(Profile, membership.player_id)
            if profile is not None and profile.is_active and profile.deleted_at is None:
                await track_join(db, membership)
        intervals = select(MembershipInterval).where(
            MembershipInterval.league_id == league_id, MembershipInterval.left_at.is_(None)
        )
        if player_id is not None:
            intervals = intervals.where(MembershipInterval.player_id == player_id)
        players = set()
        for interval in await db.scalars(intervals.with_for_update()):
            interval.left_at = now
            players.add(interval.player_id)
            closed += 1
        await db.flush()
        # Departure is exclusive. Plan against the closed interval, including
        # at Monday midnight; do not bootstrap the still-present roster again.
        for member_id in sorted(players, key=str):
            await materialize_dues(db, league_id, member_id, now, bootstrap=False)
    return closed


async def release_new_entries(
    db: AsyncSession,
    player_id: uuid.UUID,
    league_ids: Collection[uuid.UUID] | None,
    now: datetime,
) -> int:
    """Free unlocked claims while keeping exact-target revisions monotonic."""
    targets = (
        set(league_ids)
        if league_ids is not None
        else set(
            await db.scalars(
                select(GroupPick.league_id)
                .where(GroupPick.player_id == player_id)
                .union(select(FantasyPick.league_id).where(FantasyPick.player_id == player_id))
            )
        )
    )
    await financial_locks(db, targets)
    return await _release_new_model(
        db, GroupPick, player_id, targets, now
    ) + await _release_new_model(db, FantasyPick, player_id, targets, now)


_Entry = TypeVar("_Entry", GroupPick, FantasyPick)


async def _release_new_model(
    db: AsyncSession,
    model: type[_Entry],
    player_id: uuid.UUID,
    league_ids: Collection[uuid.UUID],
    now: datetime,
) -> int:
    released = 0
    query = (
        select(model)
        .join(TwoGame, TwoGame.id == model.game_id)
        .where(
            model.player_id == player_id,
            TwoGame.locks_at > now,
            TwoGame.status.not_in(("settled", "cancelled")),
        )
    )
    if league_ids is not None:
        query = query.where(model.league_id.in_(league_ids))
    for pick in await db.scalars(query.order_by(model.league_id, model.id)):
        slot = pick.slot if isinstance(pick, FantasyPick) else 0
        revisions: list[int] = [
            int(response.get("revision", 0))
            for response in await db.scalars(
                select(GameOperation.response).where(
                    GameOperation.game_id == pick.game_id,
                    GameOperation.player_id == player_id,
                    GameOperation.slot == slot,
                )
            )
        ]
        revision = max([pick.revision, *revisions]) + 1
        operation_id = uuid.uuid4()
        db.add(
            GameOperation(
                league_id=pick.league_id,
                week_id=pick.week_id,
                game_id=pick.game_id,
                game_kind=pick.game_kind,
                player_id=player_id,
                slot=slot,
                operation_id=operation_id,
                body_hash=sha256(f"membership-release:{operation_id}".encode()).hexdigest(),
                response={
                    "operation_id": str(operation_id),
                    "revision": revision,
                    "pick": None,
                },
            )
        )
        await db.delete(pick)
        released += 1
    return released


class FeeObligation(BaseModel):
    week_id: uuid.UUID | None
    week_label: date | None
    remaining_pence: int


class WeekFee(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    week_label: date
    billing_starts_at: UtcDatetime
    billing_ends_at: UtcDatetime
    obligation_pence: int
    amount_owed_pence: int
    paid_through: bool
    pooled_credit_pence: int
    payment_url: str | None
    destination: str
    obligations: list[FeeObligation]


@dataclass
class FeeProjection:
    league: League
    dues: list[RoundDue]
    credit: int
    actual_total: int
    weekly_amounts: dict[date, int]

    def for_week(self, week: Gameweek) -> WeekFee:
        through = [
            due for due in self.dues if due.starts_on is None or due.starts_on <= week.starts_on
        ]
        obligations = [
            FeeObligation(
                week_id=due.gameweek_id,
                week_label=due.starts_on,
                remaining_pence=due.amount_pence - paid,
            )
            for due, paid in allocate(self.credit, through)
            if due.amount_pence > paid
        ]
        owed = sum(item.remaining_pence for item in obligations)
        start, end = billing_bounds(week.starts_on)
        return WeekFee(
            league_id=self.league.id,
            week_id=week.id,
            week_label=week.starts_on,
            billing_starts_at=start,
            billing_ends_at=end,
            obligation_pence=self.weekly_amounts.get(week.starts_on, 0),
            amount_owed_pence=owed,
            paid_through=owed == 0,
            pooled_credit_pence=max(0, self.credit - self.actual_total),
            payment_url=self.league.payment_link_url,
            destination=f"/leagues/{self.league.id}/weeks/{week.id}/group#payment",
            obligations=obligations,
        )


async def project_fees(
    db: AsyncSession,
    league: League,
    player_id: uuid.UUID,
    through: date,
    now: datetime,
) -> FeeProjection:
    """Read projection includes future intervening weeks without writing them down."""
    rollout = await _rollout(db, league.id)
    if rollout is None:
        raise ValueError("inactive weekly billing")
    intervals = await _intervals(db, league.id, player_id)
    membership = await _active_membership(db, league.id, player_id)
    if membership is not None and not any(item.left_at is None for item in intervals):
        intervals.append(Interval(None, membership.joined_at, None))
    ledgers = await _member_ledgers(db, league.id, [player_id])
    ledger = ledgers.get(player_id)
    credit = ledger.credit_pence if ledger else 0
    rounds = await _round_dates(db, ledger.owed_by_round if ledger else [])
    dues = _dues_of(ledger, rounds) if ledger else []
    actual_total = sum(due.amount_pence for due in dues)
    amounts = {
        parent.starts_on: owed
        for parent_id, owed in (ledger.owed_by_round.items() if ledger else [])
        if parent_id is not None
        and (parent := rounds.get(parent_id)) is not None
        and parent.format == "two_game"
    }
    parents = {
        row.starts_on: row.id
        for row in await db.scalars(
            select(Gameweek).where(
                Gameweek.league_id == league.id,
                Gameweek.format == "two_game",
                Gameweek.starts_on <= through,
            )
        )
    }
    for planned in plan_dues(intervals, rollout.first_week, through, now, early=True):
        if planned.label not in amounts:
            amounts[planned.label] = 100
            dues.append(RoundDue(parents.get(planned.label), planned.label, 100))
    if credit < 0:
        dues.append(RoundDue(None, None, -credit))
    return FeeProjection(league, dues, max(credit, 0), actual_total, amounts)


class EntryFeeRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def materialize_entry_fees(
    sessions: async_sessionmaker[AsyncSession],
    *,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    game_id: uuid.UUID,
    game_kind: str,
    player_id: uuid.UUID,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> WeekFee:
    """Independent early fee commit survives any later quote/pick refusal/rollback."""
    async with sessions() as db, db.begin():
        if not await financial_lock(db, league_id):
            raise EntryFeeRefused("NOT_FOUND")
        moment = naive_utc(clock() if clock is not None else now or utc_now())
        rollout = await _rollout(db, league_id)
        parent = await db.get(Gameweek, week_id)
        game = await db.get(TwoGame, game_id)
        member = await _active_membership(db, league_id, player_id)
        if (
            rollout is None
            or parent is None
            or parent.league_id != league_id
            or parent.starts_on < rollout.first_week
            or member is None
            or member.joined_at > moment
            or game is None
            or (game.league_id, game.week_id, game.kind) != (league_id, week_id, game_kind)
        ):
            raise EntryFeeRefused("NOT_FOUND")
        if parent.format != "two_game":
            raise EntryFeeRefused("UNSUPPORTED_FORMAT")
        if rollout.suspended:
            raise EntryFeeRefused("SUSPENDED")
        if game.status == "cancelled":
            raise EntryFeeRefused("CANCELLED")
        if moment >= game.locks_at:
            raise EntryFeeRefused("LOCKED")
        calendar = await db.get(ProviderWork, f"calendar:{league_id}")
        if moment < game.opens_at or (
            calendar and calendar.payload.get("state") == "schedule_conflict"
        ):
            raise EntryFeeRefused("NOT_OPEN")
        await materialize_dues(
            db, league_id, player_id, moment, through=parent.starts_on, early=True
        )
        league = await db.get(League, league_id, populate_existing=True)
        if league is None or league.deleted_at is not None:
            raise EntryFeeRefused("NOT_FOUND")
        fee = (await project_fees(db, league, player_id, parent.starts_on, moment)).for_week(parent)
    # An unpaid result is returned after COMMIT. Raising inside the transaction
    # would incorrectly erase the approved early obligation.
    return fee


async def bill_all(sessions: async_sessionmaker[AsyncSession], now: datetime | None = None) -> int:
    from src.config import settings

    if not settings.two_games_enabled:
        return 0
    moment = naive_utc(now or utc_now())
    async with sessions() as db:
        league_ids = list(
            await db.scalars(
                select(TwoGameRollout.league_id)
                .where(TwoGameRollout.enabled.is_(True))
                .order_by(TwoGameRollout.league_id)
            )
        )
    count = 0
    failures: list[Exception] = []
    for league_id in league_ids:
        try:
            count += await _bill_league(sessions, league_id, moment)
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise ExceptionGroup(
            "weekly billing failed for some leagues; other commits retained", failures
        )
    return count


async def _bill_league(
    sessions: async_sessionmaker[AsyncSession], league_id: uuid.UUID, moment: datetime
) -> int:
    count = 0
    async with sessions() as db, db.begin():
        if not await financial_lock(db, league_id) or await _rollout(db, league_id) is None:
            return 0
        members = set(
            await db.scalars(
                select(MembershipInterval.player_id).where(
                    MembershipInterval.league_id == league_id
                )
            )
        )
        members.update(
            await db.scalars(
                select(LeagueMembership.player_id)
                .join(Profile, Profile.id == LeagueMembership.player_id)
                .where(
                    LeagueMembership.league_id == league_id,
                    LeagueMembership.deleted_at.is_(None),
                    Profile.deleted_at.is_(None),
                    Profile.is_active.is_(True),
                )
            )
        )
        for player_id in sorted(members, key=str):
            count += await materialize_dues(db, league_id, player_id, moment)
    return count
