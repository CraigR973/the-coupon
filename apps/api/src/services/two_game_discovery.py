"""Installation-wide paginated census and fair durable ten-fixture price work.

The scheduler prepares calendar work independently of roster, fees and entries.
Only a leased HTTP-sized unit acquires the provider. Page/chunk commits survive
later errors and process restarts; browse requests never run this worker.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.two_game import (
    FantasyPick,
    GroupPick,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
)
from src.services.gameweek import (
    active_leagues,
    fixtures_for,
    retire_stranded_rounds,
    selected_competition_slugs,
    sync_slate,
    upcoming_slate_dates,
    warmable_gameweeks,
    window_for,
)
from src.services.odds_pricing import askable, record_observations
from src.services.odds_provider import (
    CensusPage,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderBadRequest,
    Slate,
    SlateFixture,
    SlateWindow,
    as_utc,
)
from src.services.provider_budget import (
    Category,
    ProviderBudgetRefused,
    naive_utc,
    provider_category,
    utc_now,
)
from src.services.provider_work import WorkLease, WorkQueue
from src.services.season_calendar import extra_weeks_between
from src.services.two_game_fixture_state import (
    fixture_state_key,
    record_fixture_observations,
    void_events,
)
from src.services.two_game_quotes import SharedQuotes
from src.services.two_game_schedule import prepare_calendar
from src.services.two_game_storage import LONDON, legacy_date_blocked, london_utc


def census_ranges(first: datetime, last: datetime) -> list[tuple[datetime, datetime]]:
    """Share one Sat–Mon census; arbitrary legacy windows keep all their other days."""
    day = as_utc(first).astimezone(LONDON).date()
    end = as_utc(last).astimezone(LONDON).date()
    if as_utc(last) > london_utc(end).replace(tzinfo=UTC):
        end += timedelta(days=1)
    ranges: set[tuple[datetime, datetime]] = set()
    while day < end:
        if day.weekday() in (5, 6):
            saturday = day - timedelta(days=day.weekday() - 5)
            ranges.add((london_utc(saturday), london_utc(saturday + timedelta(days=2))))
        else:
            ranges.add((london_utc(day), london_utc(day + timedelta(days=1))))
        day += timedelta(days=1)
    return sorted(ranges)


class DiscoveryWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        acquire: Callable[[], Awaitable[OddsProvider]],
        *,
        source: str,
        bookmaker: str,
        clock: Callable[[], datetime] = utc_now,
        page_size: int = 5000,
        units_per_pass: int = 3,
        lookahead: int = 12,
        lease_seconds: int = 45,
        sweep_seconds: int = 6 * 3600,
        negative_seconds: int = 300,
        include_legacy: bool = True,
        verify_rows: Callable[[list[SlateFixture]], Awaitable[list[SlateFixture]]] | None = None,
    ) -> None:
        if not 1 <= page_size <= 5000 or min(units_per_pass, lookahead, sweep_seconds) <= 0:
            raise ValueError("invalid bounded discovery policy")
        self.sessions, self.acquire, self.clock = sessions, acquire, clock
        self.source, self.bookmaker = source, bookmaker
        self.page_size, self.units_per_pass, self.lookahead = page_size, units_per_pass, lookahead
        self.sweep_seconds, self.negative_seconds = sweep_seconds, negative_seconds
        self.include_legacy = include_legacy
        self.verify_rows = verify_rows
        self.queue = WorkQueue(sessions, clock=clock, lease_seconds=lease_seconds)

    def census_key(self, first: datetime, last: datetime) -> str:
        identity = json.dumps([self.source, first.isoformat(), last.isoformat()])
        return "census:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    async def enabled(self) -> bool:
        from src.config import settings

        if not settings.two_games_enabled:
            return False
        async with self.sessions() as db:
            return bool(
                await db.scalar(
                    select(TwoGameRollout.league_id)
                    .join(League, League.id == TwoGameRollout.league_id)
                    .where(TwoGameRollout.enabled.is_(True), League.deleted_at.is_(None))
                    .limit(1)
                )
            )

    def price_key(self, event_id: str) -> str:
        identity = json.dumps([self.source, self.bookmaker, event_id])
        return "price:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    def quote_key(self, event_id: str) -> str:
        identity = json.dumps([self.source, self.bookmaker, event_id], separators=(",", ":"))
        return "quote:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    async def _enqueue_ranges(
        self, db: AsyncSession, ranges: Mapping[str, tuple[datetime, datetime]]
    ) -> None:
        """Enqueue census ranges in one insert, then revive any that had been parked."""
        if not ranges:
            return
        now = naive_utc(self.clock())
        await db.execute(
            insert(ProviderWork)
            .values(
                [
                    dict(
                        key=key,
                        kind="census",
                        payload={
                            "source": self.source,
                            "first": first.isoformat(),
                            "last": last.isoformat(),
                        },
                        next_at=now,
                        fixture_id=None,
                    )
                    for key, (first, last) in sorted(ranges.items())
                ]
            )
            .on_conflict_do_nothing()
        )
        await db.execute(
            update(ProviderWork)
            .where(ProviderWork.key.in_(ranges), ProviderWork.last_error == "no_open_target")
            .values(next_at=now, last_error=None)
            .execution_options(synchronize_session=False)
        )

    async def prepare(self) -> None:
        """Calendar, links, legacy slates and price work, in short separate transactions.

        Batch 237. This used to be one transaction whose calendar step took every
        activated league's lock and held it while it issued a query per fixture: about
        80 s a pass in production, back to back, and every game read and save queued
        behind it. Now no step holds a league lock — the calendar takes one only to
        create a new parent week — and each step reads in batches, so an empty pass costs
        a few dozen statements whatever the card's size. Every step is idempotent, so a
        pass that fails part-way is completed by the next one.
        """
        now = naive_utc(self.clock())
        async with self.sessions() as db, db.begin():
            await prepare_calendar(db, now, lookahead=self.lookahead)
        needed: set[str] = set()
        async with self.sessions() as db, db.begin():
            rows = list(
                await db.execute(
                    select(TwoGame, Gameweek, League)
                    .join(Gameweek, Gameweek.id == TwoGame.week_id)
                    .join(League, League.id == TwoGame.league_id)
                    .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
                    .where(
                        TwoGameRollout.enabled.is_(True),
                        TwoGameRollout.suspended.is_(False),
                        League.deleted_at.is_(None),
                        TwoGame.window_end >= now,
                        TwoGame.status.notin_(("cancelled", "settled")),
                    )
                    .order_by(TwoGame.locks_at, TwoGame.kind)
                )
            )
            ranges: dict[str, tuple[datetime, datetime]] = {}
            keyed: list[tuple[str, TwoGame, League]] = []
            for game, parent, league in rows:
                first, last = (
                    london_utc(parent.starts_on),
                    london_utc(parent.starts_on + timedelta(days=2)),
                )
                key = self.census_key(first, last)
                ranges[key] = (first, last)
                keyed.append((key, game, league))
            await self._enqueue_ranges(db, ranges)
            needed.update(ranges)
            local = now.replace(tzinfo=UTC).astimezone(LONDON)
            if local.weekday() == 5 and local.hour == 12:
                opening = sorted(
                    {
                        key
                        for key, game, _ in keyed
                        if game.kind == "fantasy" and game.opens_at <= now < game.locks_at
                    }
                )
                if opening:
                    for work in await db.scalars(
                        select(ProviderWork)
                        .where(ProviderWork.key.in_(opening))
                        .order_by(ProviderWork.key)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    ):
                        self._schedule_opening_check(work, london_utc(local.date(), 12), now)
            snapshots = await self._snapshots(db, ranges)
            for key, game, league in keyed:
                snapshot = snapshots.get(key)
                if snapshot is not None:
                    await self._link_game(db, game, league, snapshot)
        if self.include_legacy:
            async with self.sessions() as db, db.begin():
                needed |= await self._prepare_legacy(db, now)
        async with self.sessions() as db, db.begin():
            needed |= await self._enqueue_prices(db, now)
        async with self.sessions() as db, db.begin():
            # Park work no open target needs. Rows already parked are left untouched.
            await db.execute(
                update(ProviderWork)
                .where(
                    ProviderWork.kind.in_(("census", "price", "price_single")),
                    ProviderWork.payload["source"].astext == self.source,
                    ProviderWork.key.notin_(needed),
                    or_(
                        ProviderWork.next_at != datetime.max,
                        ProviderWork.last_error.is_distinct_from("no_open_target"),
                    ),
                )
                .values(next_at=datetime.max, last_error="no_open_target")
                .execution_options(synchronize_session=False)
            )

    @staticmethod
    async def _snapshots(db: AsyncSession, keys: Iterable[str]) -> dict[str, ProviderSnapshot]:
        wanted = sorted(set(keys))
        if not wanted:
            return {}
        return {
            row.key: row
            for row in await db.scalars(
                select(ProviderSnapshot).where(ProviderSnapshot.key.in_(wanted))
            )
        }

    async def _prepare_legacy(self, db: AsyncSession, now: datetime) -> set[str]:
        from src.config import settings

        today = now.replace(tzinfo=UTC).astimezone(LONDON).date()
        leagues = await active_leagues(db)
        horizon = settings.slate_horizon_weeks
        ranges: dict[str, tuple[datetime, datetime]] = {}
        plans: list[tuple[League, SlateWindow, date, list[str]]] = []
        for league in leagues:
            window = window_for(league)
            dates = set(upcoming_slate_dates(today, window, horizon))
            if dates:
                dates |= await extra_weeks_between(db, today, max(dates))
            await retire_stranded_rounds(db, league, today, horizon)
            dates |= set(
                await db.scalars(
                    select(Gameweek.starts_on).where(
                        Gameweek.league_id == league.id,
                        Gameweek.format == "legacy",
                        Gameweek.locks_at_utc > now,
                    )
                )
            )
            for label in sorted(dates):
                if await legacy_date_blocked(db, league.id, label):
                    continue
                bounds = census_ranges(*window.query_bounds(label))
                keys = [self.census_key(first, last) for first, last in bounds]
                ranges.update(zip(keys, bounds, strict=True))
                plans.append((league, window, label, keys))
        await self._enqueue_ranges(db, ranges)
        snapshots = await self._snapshots(db, ranges)
        ready: list[tuple[League, SlateWindow, date, list[SlateFixture]]] = []
        for league, window, label, keys in plans:
            found = [snapshots.get(key) for key in keys]
            if not found or any(row is None or "complete_rows" not in row.payload for row in found):
                continue
            ready.append(
                (
                    league,
                    window,
                    label,
                    [
                        SlateFixture.model_validate(value)
                        for row in found
                        if row is not None
                        for value in row.payload["complete_rows"]
                    ],
                )
            )
        events = sorted({sf.provider_event_id for *_, slate in ready for sf in slate})
        pool = (
            {
                row.provider_event_id: row
                for row in await db.scalars(
                    select(Fixture).where(Fixture.provider_event_id.in_(events))
                )
            }
            if events
            else {}
        )
        states = await self._snapshots(
            db, (fixture_state_key(self.source, event) for event in events)
        )
        for league, window, label, slate in ready:
            fixtures: dict[str, SlateFixture] = {}
            for sf in slate:
                current = pool.get(sf.provider_event_id)
                if current is None:
                    continue
                state = states.get(fixture_state_key(self.source, sf.provider_event_id))
                sf = sf.model_copy(
                    update={
                        "home": current.home,
                        "away": current.away,
                        "kickoff_utc": current.kickoff_utc,
                        "competition": current.competition,
                        "competition_id": current.competition_id,
                        "status": str(state.payload.get("status", sf.status))
                        if state
                        else sf.status,
                    }
                )
                if window.contains(sf.kickoff_utc, label):
                    fixtures[sf.provider_event_id] = sf
            await sync_slate(db, league, Slate(starts_on=label, fixtures=list(fixtures.values())))
        return set(ranges)

    async def _link_game(
        self, db: AsyncSession, game: TwoGame, league: League, snapshot: ProviderSnapshot
    ) -> None:
        wanted = selected_competition_slugs(league)
        raw = snapshot.payload.get("rows", [])
        events = [SlateFixture.model_validate(value).provider_event_id for value in raw]
        pool = (
            {
                row.provider_event_id: row
                for row in await db.scalars(
                    select(Fixture).where(Fixture.provider_event_id.in_(sorted(set(events))))
                )
            }
            if events
            else {}
        )
        linked = list(
            await db.scalars(
                select(Fixture)
                .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
                .where(TwoGameFixture.game_id == game.id)
            )
        )
        void = await void_events(
            db, self.source, {row.provider_event_id for row in (*pool.values(), *linked)}
        )

        def eligible(fixture: Fixture) -> bool:
            stamp = fixture.kickoff_utc
            in_window = (
                stamp == game.window_start
                if game.kind == "group"
                else game.window_start <= stamp < game.window_end
            )
            return (
                in_window
                and (wanted is None or fixture.competition_id in wanted)
                and fixture.provider_event_id not in void
            )

        fresh = sorted(
            {pool[event].id for event in events if event in pool and eligible(pool[event])}
            - {fixture.id for fixture in linked}
        )
        if fresh:
            await db.execute(
                insert(TwoGameFixture)
                .values([dict(game_id=game.id, fixture_id=fixture_id) for fixture_id in fresh])
                .on_conflict_do_nothing()
            )
        # Range rows identify candidates; the shared current state decides eligibility.
        # A legacy refresh can reinstate a fixture while this range still caches a void.
        # Accepted picks retain their original link and settlement/correction history.
        stale = sorted({fixture.id for fixture in linked if not eligible(fixture)})
        if stale:
            claimed = set(
                await db.scalars(
                    select(GroupPick.fixture_id).where(
                        GroupPick.game_id == game.id, GroupPick.fixture_id.in_(stale)
                    )
                )
            )
            claimed.update(
                await db.scalars(
                    select(FantasyPick.fixture_id).where(
                        FantasyPick.game_id == game.id, FantasyPick.fixture_id.in_(stale)
                    )
                )
            )
            unclaimed = [fixture_id for fixture_id in stale if fixture_id not in claimed]
            if unclaimed:
                await db.execute(
                    delete(TwoGameFixture).where(
                        TwoGameFixture.game_id == game.id,
                        TwoGameFixture.fixture_id.in_(unclaimed),
                    )
                )
        complete = snapshot.payload.get("state") == "complete"
        linked_any = await db.scalar(
            select(TwoGameFixture.fixture_id).where(TwoGameFixture.game_id == game.id).limit(1)
        )
        game.coverage_state = "complete" if complete and linked_any is not None else "pending"
        if snapshot.payload.get("state") == "unavailable":
            game.coverage_state = "unavailable"

    async def _enqueue_prices(self, db: AsyncSession, now: datetime) -> set[str]:
        fixtures = list(
            await db.scalars(
                select(Fixture)
                .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
                .join(TwoGame, TwoGame.id == TwoGameFixture.game_id)
                .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
                .join(League, League.id == TwoGame.league_id)
                .where(
                    TwoGame.kind == "fantasy",
                    TwoGame.locks_at > now,
                    TwoGame.opens_at <= now + timedelta(days=7),
                    TwoGame.status.notin_(("cancelled", "settled")),
                    TwoGameRollout.enabled.is_(True),
                    TwoGameRollout.suspended.is_(False),
                    League.deleted_at.is_(None),
                )
                .distinct()
            )
        )
        if self.include_legacy:
            from src.config import settings

            for week in await warmable_gameweeks(
                db, now, horizon_weeks=settings.odds_warm_horizon_weeks
            ):
                fixtures.extend(
                    askable(
                        await fixtures_for(db, week.id),
                        now,
                        recheck_seconds=settings.odds_unpriced_recheck_seconds,
                    )
                )
        void = await void_events(db, self.source, {row.provider_event_id for row in fixtures})
        work: dict[str, Fixture] = {}
        for fixture in fixtures:
            if fixture.provider_event_id not in void:
                work.setdefault(self.price_key(fixture.provider_event_id), fixture)
        if not work:
            return set()
        await db.execute(
            insert(ProviderWork)
            .values(
                [
                    dict(
                        key=key,
                        kind="price",
                        payload={"source": self.source, "event_id": fixture.provider_event_id},
                        fixture_id=fixture.id,
                        next_at=now,
                    )
                    for key, fixture in sorted(work.items())
                ]
            )
            .on_conflict_do_nothing()
        )
        await db.execute(
            update(ProviderWork)
            .where(ProviderWork.key.in_(work), ProviderWork.last_error == "no_open_target")
            .values(next_at=now, last_error=None)
            .execution_options(synchronize_session=False)
        )
        local = now.replace(tzinfo=UTC).astimezone(LONDON)
        if local.weekday() == 5 and local.hour == 12:
            noon = london_utc(local.date(), 12)
            quotes = await self._snapshots(
                db, (self.quote_key(fixture.provider_event_id) for fixture in work.values())
            )
            recheck = sorted(
                key
                for key, fixture in work.items()
                if (quote := quotes.get(self.quote_key(fixture.provider_event_id))) is not None
                and quote.payload.get("state") == "unavailable"
                and quote.observed_at < noon
            )
            if recheck:
                for row in await db.scalars(
                    select(ProviderWork)
                    .where(ProviderWork.key.in_(recheck))
                    .order_by(ProviderWork.key)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ):
                    self._schedule_opening_check(row, noon, now)
        return set(work)

    @staticmethod
    def _schedule_opening_check(work: ProviderWork, opening: datetime, now: datetime) -> None:
        generation = opening.isoformat()
        if work.payload.get("opening_generation") != generation:
            work.payload = {**work.payload, "opening_generation": generation}
            work.next_at = min(work.next_at, now)

    async def _opening_keys(self, now: datetime) -> list[str]:
        async with self.sessions() as db:
            rows = list(
                await db.execute(
                    select(TwoGame, Gameweek)
                    .join(Gameweek, Gameweek.id == TwoGame.week_id)
                    .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
                    .join(League, League.id == TwoGame.league_id)
                    .where(
                        TwoGame.kind == "fantasy",
                        TwoGame.opens_at <= now,
                        TwoGame.locks_at > now,
                        TwoGame.status.notin_(("cancelled", "settled")),
                        TwoGameRollout.enabled.is_(True),
                        TwoGameRollout.suspended.is_(False),
                        League.deleted_at.is_(None),
                    )
                )
            )
            keys = {
                self.census_key(
                    london_utc(parent.starts_on), london_utc(parent.starts_on + timedelta(days=2))
                )
                for game, parent in rows
            }
            fixture_ids = select(TwoGameFixture.fixture_id).where(
                TwoGameFixture.game_id.in_([game.id for game, _ in rows])
            )
            keys.update(
                await db.scalars(
                    select(ProviderWork.key).where(
                        ProviderWork.fixture_id.in_(fixture_ids),
                        ProviderWork.kind.in_(("price", "price_single")),
                        ProviderWork.payload["source"].astext == self.source,
                    )
                )
            )
            return sorted(keys)

    async def _page(self, lease: WorkLease, provider: OddsProvider, category: Category) -> None:
        first, last = (datetime.fromisoformat(lease.payload[name]) for name in ("first", "last"))
        with provider_category(category):
            page = await provider.fetch_event_page(
                first, last, cursor=lease.cursor, limit=self.page_size
            )
        self._validate_page(page, lease.cursor)
        if self.verify_rows is not None:
            page = page.model_copy(update={"fixtures": await self.verify_rows(page.fixtures)})
        now = naive_utc(self.clock())
        async with self.sessions() as db, db.begin():
            work = await self.queue.owned(db, lease)
            if work is None:
                return
            snapshot = await db.get(ProviderSnapshot, lease.key, with_for_update=True)
            if snapshot is None:
                snapshot = ProviderSnapshot(
                    key=lease.key, payload={}, observed_at=now, expires_at=now
                )
                db.add(snapshot)
            prior = snapshot.payload
            rows = (
                {row["provider_event_id"]: row for row in prior.get("rows", [])}
                if lease.cursor is not None
                else {}
            )
            for sf in page.fixtures:
                if not first <= naive_utc(sf.kickoff_utc) < last:
                    raise OddsProviderAPIError("census returned an out-of-range fixture")
                rows[sf.provider_event_id] = sf.model_dump(mode="json")
            await record_fixture_observations(
                db,
                self.source,
                page.fixtures,
                observed_at=now,
                expires_at=now + timedelta(seconds=self.sweep_seconds),
            )
            payload: dict[str, Any] = {
                "state": "complete" if page.complete else "pending",
                "rows": list(rows.values()),
                "source": self.source,
                "raw_count": page.raw_count,
            }
            if page.complete:
                payload["complete_rows"] = list(rows.values())
                work.completed_at = now
            elif "complete_rows" in prior:
                payload["complete_rows"] = prior["complete_rows"]
            snapshot.payload, snapshot.observed_at = payload, now
            snapshot.expires_at = now + timedelta(seconds=self.sweep_seconds)
            work.cursor = page.next_cursor
            work.next_at = now + timedelta(seconds=self.sweep_seconds if page.complete else 360)
            work.last_error = None
            work.lease_token = work.lease_until = None
        # Link only committed pages. A failure here leaves the census reusable on
        # preparation/restart; it never spends the page request again for a DB retry.
        await self.prepare()

    def _validate_page(self, page: CensusPage, previous: str | None) -> None:
        if not 0 <= page.raw_count <= self.page_size or len(page.fixtures) > page.raw_count:
            raise OddsProviderAPIError("invalid census page counts")
        if page.complete:
            if page.next_cursor is not None:
                raise OddsProviderAPIError("complete census has a continuation")
        elif (
            page.raw_count != self.page_size
            or page.next_cursor is None
            or not page.next_cursor.isdigit()
            or int(page.next_cursor) <= int(previous or "0")
        ):
            raise OddsProviderAPIError("truncated or non-advancing census")

    async def _price(
        self, leases: Sequence[WorkLease], provider: OddsProvider, category: Category
    ) -> None:
        now = naive_utc(self.clock())
        ids = [str(lease.payload["event_id"]) for lease in leases]
        quotes = SharedQuotes(
            self.sessions,
            provider,
            source=self.source,
            bookmaker=self.bookmaker,
            clock=self.clock,
            negative_seconds=self.negative_seconds,
            lease_seconds=self.queue.lease_seconds,
        )
        local = now.replace(tzinfo=UTC).astimezone(LONDON)
        opening = london_utc(local.date(), 12) if category == "opening" else None
        views = await quotes.refresh_many(ids, category=category, opening_at=opening)
        async with self.sessions() as db, db.begin():
            for lease in leases:
                work = await self.queue.owned(db, lease)
                if work is None:
                    continue
                view = views[str(lease.payload["event_id"])]
                positive = view.availability == "available"
                observed = view.observed_at is not None and view.observed_at >= now
                delay = self.sweep_seconds if positive and observed else self.queue.lease_seconds
                if not positive and view.observed_at is not None:
                    work.next_at = max(
                        now + timedelta(seconds=1),
                        view.observed_at + timedelta(seconds=self.negative_seconds),
                    )
                else:
                    work.next_at = now + timedelta(seconds=delay)
                if observed and view.observed_at is not None:
                    work.completed_at = view.observed_at
                    fixture = await db.get(Fixture, lease.fixture_id) if lease.fixture_id else None
                    if fixture is not None:
                        record_observations(
                            [fixture],
                            {fixture.provider_event_id},
                            {fixture.provider_event_id} if positive else set(),
                            view.observed_at,
                        )
                work.kind = "price"
                work.last_error = None if positive else "price_unavailable"
                work.lease_token = work.lease_until = None

    async def run(self, *, prepare: bool = True) -> int:
        if not await self.enabled():
            return 0
        if prepare:
            await self.prepare()
        now = naive_utc(self.clock())
        local = now.replace(tzinfo=UTC).astimezone(LONDON)
        if local.weekday() == 5 and 10 <= local.hour < 12:
            return 0
        category: Category = (
            "opening" if local.weekday() == 5 and local.hour == 12 else "background"
        )
        keys = await self._opening_keys(now) if category == "opening" else None
        completed = 0
        for _ in range(self.units_per_pass):
            lease = await self.queue.claim(
                ("census", "price", "price_single"),
                source=self.source,
                keys=keys,
            )
            if lease is None:
                break
            leases = [lease]
            if lease.kind == "price":
                for _ in range(9):
                    extra = await self.queue.claim(("price",), source=self.source, keys=keys)
                    if extra is None:
                        break
                    leases.append(extra)
            try:
                # All preparation/lease transactions ended before login or HTTP.
                with provider_category(category):
                    provider = await self.acquire()
                if lease.kind == "census":
                    await self._page(lease, provider, category)
                else:
                    await self._price(leases, provider, category)
                completed += 1
            except Exception as exc:
                retry = exc.retry_at if isinstance(exc, ProviderBudgetRefused) else None
                if (
                    isinstance(exc, ProviderBudgetRefused)
                    and category == "opening"
                    and exc.reason.startswith("category_")
                ):
                    retry = min(exc.retry_at, london_utc(local.date(), 13))
                for owned in leases:
                    split = isinstance(exc, OddsProviderBadRequest) and len(leases) > 1
                    await self.queue.defer(
                        owned,
                        type(exc).__name__,
                        retry_at=retry,
                        kind="price_single" if split else None,
                    )
        return completed
