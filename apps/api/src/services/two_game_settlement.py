"""Fair per-fixture result chunks, with durable token and manual-generation fences."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.two_game import (
    FantasyPick,
    GroupPick,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameRollout,
)
from src.services.football_week import settle_refusal
from src.services.gameweek import settleable_gameweeks
from src.services.odds_provider import VOID_STATUSES, EventSettlement, OddsProvider, is_void_status
from src.services.provider_budget import (
    ProviderBudgetRefused,
    naive_utc,
    provider_category,
    utc_now,
)
from src.services.provider_work import WorkLease, WorkQueue, enqueue
from src.services.scoring import _settle_empty_rounds, resolve_pick, resolve_status, settle_gameweek
from src.services.two_game_fixture_state import fixture_state_key
from src.services.two_game_results import recompute_game

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def active(db: AsyncSession) -> bool:
    from src.config import settings

    return settings.two_games_enabled and bool(
        await db.scalar(
            select(TwoGameRollout.league_id)
            .join(League, League.id == TwoGameRollout.league_id)
            .where(TwoGameRollout.enabled.is_(True), League.deleted_at.is_(None))
            .limit(1)
        )
    )


def result_key(fixture_id: uuid.UUID) -> str:
    return f"fixture-result:v1:{fixture_id}"


async def settlement_locks(db: AsyncSession, league_ids: list[uuid.UUID]) -> None:
    """The entry/fee league key, also covering legacy-only leagues in a mixed pass."""
    for league_id in sorted(set(league_ids), key=str):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"),
            {"key": str(league_id)},
        )


async def result_lock(db: AsyncSession, fixture_id: uuid.UUID) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 225))"), {"key": str(fixture_id)}
    )


async def result_locks(db: AsyncSession, fixture_ids: set[uuid.UUID]) -> None:
    for fixture_id in sorted(fixture_ids):
        await result_lock(db, fixture_id)


def observation_identity(observation: ProviderSnapshot | None) -> str | None:
    if observation is None:
        return None
    return json.dumps([observation.observed_at.isoformat(), observation.payload], sort_keys=True)


def current_cached_result(
    state: ProviderSnapshot | None, observation: ProviderSnapshot | None
) -> EventSettlement | None:
    result = effective_result(state)
    if (
        result is not None
        and result.void
        and state is not None
        and state.payload.get("authority") != "manual"
        and observation is not None
        and not is_void_status(str(observation.payload.get("status", "")))
        and state.payload.get("fixture_observation") != observation_identity(observation)
    ):
        return None
    return result


async def advance_generation(db: AsyncSession, fixture_id: uuid.UUID, now: datetime) -> None:
    """Fence an actual scoped manual mutation without promoting it to global truth."""
    state = await db.get(ProviderSnapshot, result_key(fixture_id), populate_existing=True)
    payload = dict(state.payload) if state else {}
    payload["generation"] = int(payload.get("generation", 0)) + 1
    if state is None:
        db.add(
            ProviderSnapshot(
                key=result_key(fixture_id),
                fixture_id=fixture_id,
                payload=payload,
                observed_at=now,
                expires_at=datetime.max,
            )
        )
    else:
        state.payload, state.observed_at = payload, now


def effective_result(state: ProviderSnapshot | None) -> EventSettlement | None:
    if state is None:
        return None
    payload = state.payload
    if payload.get("authority") != "manual" and payload.get("provider_generation") != payload.get(
        "generation", 0
    ):
        return None
    value = payload.get("settlement")
    return EventSettlement.model_validate(value) if isinstance(value, dict) else None


@dataclass
class Claim:
    kind: str
    pick: Pick | GroupPick | FantasyPick
    parent: Gameweek
    fixture: Fixture


def result_eligible(now: datetime, source: str) -> ColumnElement[bool]:
    observed_void = and_(
        ProviderSnapshot.key.startswith("fixture-state:v1:"),
        ProviderSnapshot.payload["source"].astext == source,
        func.lower(func.trim(ProviderSnapshot.payload["status"].astext)).in_(VOID_STATUSES),
    )
    known_result = and_(
        ProviderSnapshot.key.startswith("fixture-result:v1:"),
        ProviderSnapshot.payload["settlement"]["settled"].astext == "true",
        or_(
            ProviderSnapshot.payload["authority"].astext == "manual",
            and_(
                ProviderSnapshot.payload["provider_generation"].astext
                == func.coalesce(ProviderSnapshot.payload["generation"].astext, "0"),
                ProviderSnapshot.payload["settlement"]["void"].astext == "false",
            ),
        ),
    )
    return or_(
        Fixture.kickoff_utc <= now,
        exists().where(ProviderSnapshot.fixture_id == Fixture.id, or_(observed_void, known_result)),
    )


async def claims(
    db: AsyncSession,
    now: datetime,
    *,
    source: str,
    fixture_id: uuid.UUID | None = None,
    lock: bool = False,
) -> list[Claim]:
    """Select legitimate locked pending claims; never poll unstarted Sunday fixtures."""
    output: list[Claim] = []
    legacy = [
        week
        for week in await settleable_gameweeks(db, now)
        if await settle_refusal(db, week) is None
    ]
    if legacy:
        stmt = (
            select(Pick, Gameweek, Fixture)
            .join(Gameweek, Gameweek.id == Pick.gameweek_id)
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(
                Pick.gameweek_id.in_([week.id for week in legacy]),
                Pick.status == PickStatus.pending,
                result_eligible(now, source),
            )
            .order_by(Pick.id)
        )
        if fixture_id is not None:
            stmt = stmt.where(Pick.fixture_id == fixture_id)
        if lock:
            stmt = stmt.with_for_update(of=Pick)
        for pick, parent, fixture in (
            await db.execute(stmt.execution_options(populate_existing=True))
        ).all():
            output.append(Claim("legacy", pick, parent, fixture))
    for model, kind in ((GroupPick, "group"), (FantasyPick, "fantasy")):
        new_stmt = (
            select(model, Gameweek, Fixture)
            .join(Gameweek, Gameweek.id == model.week_id)
            .join(TwoGame, TwoGame.id == model.game_id)
            .join(Fixture, Fixture.id == model.fixture_id)
            .join(League, League.id == model.league_id)
            .join(TwoGameRollout, TwoGameRollout.league_id == model.league_id)
            .where(
                model.status == "pending",
                Gameweek.format == "two_game",
                TwoGame.locks_at <= now,
                result_eligible(now, source),
                League.deleted_at.is_(None),
                TwoGameRollout.enabled.is_(True),
                Gameweek.starts_on >= TwoGameRollout.first_week,
            )
            .order_by(model.id)
        )
        if fixture_id is not None:
            new_stmt = new_stmt.where(model.fixture_id == fixture_id)
        if lock:
            new_stmt = new_stmt.with_for_update(of=model)
        for pick, parent, fixture in (
            await db.execute(new_stmt.execution_options(populate_existing=True))
        ).all():
            output.append(Claim(kind, pick, parent, fixture))
    return output


def resolution(claim: Claim, settlement: EventSettlement) -> tuple[str, int | None] | None:
    pick = claim.pick
    if claim.kind == "group":
        verdict = resolve_status(PickMarket(pick.market), PickOutcome(pick.outcome), settlement)
        return (verdict.value, None) if verdict is not None else None
    if isinstance(pick, Pick):
        odds = pick.odds_at_pick
    elif isinstance(pick, FantasyPick):
        odds = pick.frozen_odds
    else:
        raise ValueError("priced resolution requires a legacy or fantasy pick")
    priced = resolve_pick(PickMarket(pick.market), PickOutcome(pick.outcome), odds, settlement)
    return (priced.status.value, priced.points) if priced is not None else None


async def record_legacy_completion(db: AsyncSession, parent: Gameweek, now: datetime) -> None:
    from src.services.two_game_events import stage_legacy_fact

    await stage_legacy_fact(db, parent, now)


class SettlementWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        acquire: Callable[[], Awaitable[OddsProvider]],
        *,
        source: str,
        clock: Callable[[], datetime] = utc_now,
        units_per_pass: int = 10,
        lease_seconds: int = 45,
    ) -> None:
        if units_per_pass < 1:
            raise ValueError("settlement pass must be bounded and positive")
        self.sessions, self.acquire, self.source, self.clock = sessions, acquire, source, clock
        self.units_per_pass = units_per_pass
        self.queue = WorkQueue(sessions, clock=clock, lease_seconds=lease_seconds)

    def now(self) -> datetime:
        return naive_utc(self.clock())

    async def prepare(self) -> bool:
        async with self.sessions() as db, db.begin():
            if not await active(db):
                return False
            picked = await claims(db, self.now(), source=self.source)
            distinct = {claim.fixture.id: claim.fixture.provider_event_id for claim in picked}
            for fixture_id, event_id in sorted(distinct.items()):
                key = (
                    "settlement:v1:"
                    + hashlib.sha256(json.dumps([self.source, event_id]).encode()).hexdigest()
                )
                await enqueue(
                    db,
                    key=key,
                    kind="settlement",
                    fixture_id=fixture_id,
                    payload=dict(source=self.source, event_id=event_id),
                    next_at=self.now(),
                )
                row = await db.get(ProviderWork, key, with_for_update=True)
                if row is not None and row.kind == "settled":
                    row.kind, row.completed_at, row.next_at = "settlement", None, self.now()
            stale = await db.scalars(
                select(ProviderWork)
                .where(
                    ProviderWork.kind == "settlement",
                    ProviderWork.payload["source"].astext == self.source,
                    ProviderWork.fixture_id.notin_(distinct),
                    or_(ProviderWork.lease_until.is_(None), ProviderWork.lease_until <= self.now()),
                )
                .with_for_update()
            )
            for work in stale:
                work.kind, work.completed_at = "settled", self.now()
                work.lease_token = work.lease_until = None
            return True

    async def _preflight(
        self, lease: WorkLease
    ) -> tuple[int, EventSettlement | None, bool, str | None]:
        if lease.fixture_id is None:
            raise ValueError("settlement work requires a fixture")
        async with self.sessions() as db:
            state = await db.get(ProviderSnapshot, result_key(lease.fixture_id))
            generation = int(state.payload.get("generation", 0)) if state else 0
            picked = await claims(db, self.now(), source=self.source, fixture_id=lease.fixture_id)
            observed = await db.get(
                ProviderSnapshot, fixture_state_key(self.source, lease.payload["event_id"])
            )
            identity = observation_identity(observed)
            cached = current_cached_result(state, observed)
            if cached is None:
                if observed is not None and is_void_status(str(observed.payload.get("status", ""))):
                    cached = EventSettlement(
                        provider_event_id=lease.payload["event_id"],
                        status=str(observed.payload["status"]),
                        settled=True,
                        void=True,
                    )
            if cached is not None and any(
                resolution(claim, cached) is not None for claim in picked
            ):
                return generation, cached, bool(picked), identity
            return generation, None, bool(picked), identity

    async def _apply(
        self,
        lease: WorkLease,
        captured: int,
        settlement: EventSettlement | None,
        *,
        from_cache: bool,
        captured_observation: str | None,
    ) -> int:
        if lease.fixture_id is None:
            raise ValueError("settlement work requires a fixture")
        now = self.now()
        async with self.sessions() as db, db.begin():
            if not await active(db):
                return 0
            picked = await claims(db, now, source=self.source, fixture_id=lease.fixture_id)
            locked_leagues = {claim.pick.league_id for claim in picked}
            await settlement_locks(db, list(locked_leagues))
            await result_lock(db, lease.fixture_id)
            row = await self.queue.owned(db, lease)
            if row is None or not await active(db):
                return 0
            # Census writers update shared metadata before their claim cleanup.
            # Fence that observation before locking picks in the same order.
            await db.scalar(
                select(Fixture.id).where(Fixture.id == lease.fixture_id).with_for_update(read=True)
            )
            now = self.now()
            picked = await claims(
                db, now, source=self.source, fixture_id=lease.fixture_id, lock=True
            )
            if not {claim.pick.league_id for claim in picked} <= locked_leagues:
                row.lease_token = row.lease_until = None
                row.next_at = now + timedelta(seconds=1)
                return 0
            state = await db.get(
                ProviderSnapshot, result_key(lease.fixture_id), populate_existing=True
            )
            generation = int(state.payload.get("generation", 0)) if state else 0
            observed = await db.get(
                ProviderSnapshot,
                fixture_state_key(self.source, lease.payload["event_id"]),
                populate_existing=True,
            )
            identity = observation_identity(observed)
            if generation != captured:
                settlement = (
                    effective_result(state)
                    if state and state.payload.get("authority") == "manual"
                    else None
                )
                from_cache = True
            elif from_cache:
                settlement = current_cached_result(state, observed)
                if (
                    settlement is None
                    and observed is not None
                    and is_void_status(str(observed.payload.get("status", "")))
                ):
                    settlement = EventSettlement(
                        provider_event_id=lease.payload["event_id"],
                        status=str(observed.payload["status"]),
                        settled=True,
                        void=True,
                    )
            elif (
                settlement is not None
                and settlement.void
                and captured_observation != identity
                and observed is not None
                and not is_void_status(str(observed.payload.get("status", "")))
            ):
                settlement = None
            if settlement is not None and settlement.provider_event_id != lease.payload["event_id"]:
                settlement = None
            if settlement is not None and not from_cache:
                values = dict(state.payload) if state else {}
                values.update(
                    generation=generation,
                    provider_generation=generation,
                    authority="provider",
                    source=self.source,
                    fixture_observation=identity,
                    settlement=settlement.model_dump(mode="json"),
                )
                if state is None:
                    db.add(
                        ProviderSnapshot(
                            key=result_key(lease.fixture_id),
                            fixture_id=lease.fixture_id,
                            payload=values,
                            observed_at=now,
                            expires_at=datetime.max,
                        )
                    )
                else:
                    state.payload, state.observed_at = values, now
            resolved = 0
            games: set[uuid.UUID] = set()
            parents: dict[uuid.UUID, Gameweek] = {}
            if settlement is not None:
                for claim in picked:
                    verdict = resolution(claim, settlement)
                    if verdict is None:
                        continue
                    result, points = verdict
                    pick = claim.pick
                    if isinstance(pick, Pick):
                        pick.status, pick.points_awarded = PickStatus(result), points
                        parents[claim.parent.id] = claim.parent
                    elif isinstance(pick, GroupPick | FantasyPick):
                        pick.status = result
                        if isinstance(pick, FantasyPick):
                            pick.points_awarded = points
                        games.add(pick.game_id)
                    resolved += 1
            await db.flush()
            for game_id in sorted(games):
                await recompute_game(db, game_id, now)
            for parent in parents.values():
                was_final = parent.status == GameweekStatus.settled
                await settle_gameweek(db, parent, [], now=now)
                if not was_final and parent.status == GameweekStatus.settled:
                    await record_legacy_completion(db, parent, now)
            remaining = await claims(db, now, source=self.source, fixture_id=lease.fixture_id)
            row.lease_token = row.lease_until = None
            if remaining:
                row.next_at, row.last_error = now + timedelta(minutes=6), "pending_result"
            else:
                row.kind, row.completed_at, row.last_error = "settled", now, None
            return resolved

    async def finalise(self) -> None:
        async with self.sessions() as db:
            if not await active(db):
                return
            leagues = list(
                await db.scalars(
                    select(League.id).where(League.deleted_at.is_(None)).order_by(League.id)
                )
            )
        for league_id in leagues:
            async with self.sessions() as db, db.begin():
                await settlement_locks(db, [league_id])
                now = self.now()
                legacy = [
                    week
                    for week in await settleable_gameweeks(db, now)
                    if week.league_id == league_id
                ]
                before = {week.id: week.status for week in legacy}
                await _settle_empty_rounds(db, legacy, now=now)
                # Recover a non-empty round whose independent chunks committed
                # before any one transaction observed every other result.
                for week in legacy:
                    picked = list(
                        await db.scalars(select(Pick.status).where(Pick.gameweek_id == week.id))
                    )
                    if picked and all(value != PickStatus.pending for value in picked):
                        await settle_gameweek(db, week, [], now=now)
                for week in legacy:
                    if (
                        before[week.id] != GameweekStatus.settled
                        and week.status == GameweekStatus.settled
                    ):
                        await record_legacy_completion(db, week, now)
                games = list(
                    await db.scalars(
                        select(TwoGame.id)
                        .join(League, League.id == TwoGame.league_id)
                        .join(TwoGameRollout, TwoGameRollout.league_id == League.id)
                        .where(
                            TwoGame.league_id == league_id,
                            TwoGame.locks_at <= now,
                            TwoGameRollout.enabled.is_(True),
                        )
                        .order_by(TwoGame.id)
                    )
                )
                for game_id in games:
                    await recompute_game(db, game_id, now)

    async def run(self) -> dict[str, int]:
        stats = dict(resolved=0, failures=0, chunks=0)
        if not await self.prepare():
            return stats
        try:
            for _ in range(self.units_per_pass):
                lease = await self.queue.claim(["settlement"], source=self.source)
                if lease is None:
                    break
                try:
                    generation, cached, has_claims, observation = await self._preflight(lease)
                    settlement = cached
                    if settlement is None and has_claims:
                        with provider_category("settlement"):
                            provider = await self.acquire()
                            results = await provider.settle([lease.payload["event_id"]])
                        settlement = next(
                            (
                                result
                                for result in results
                                if result.provider_event_id == lease.payload["event_id"]
                            ),
                            None,
                        )
                    stats["resolved"] += await self._apply(
                        lease,
                        generation,
                        settlement,
                        from_cache=cached is not None,
                        captured_observation=observation,
                    )
                    stats["chunks"] += 1
                except ProviderBudgetRefused as exc:
                    stats["failures"] += 1
                    await self.queue.defer(lease, "provider_budget", retry_at=exc.retry_at)
                except Exception as exc:
                    stats["failures"] += 1
                    log.warning("settlement chunk failed", error_type=type(exc).__name__)
                    await self.queue.defer(lease, type(exc).__name__)
        finally:
            await self.finalise()
        return stats
