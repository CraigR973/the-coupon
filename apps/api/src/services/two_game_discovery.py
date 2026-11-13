"""Installation-wide paginated census and fair durable ten-fixture price work.

The scheduler prepares calendar work independently of roster, fees and entries.
Only a leased HTTP-sized unit acquires the provider. Page/chunk commits survive
later errors and process restarts; browse requests never run this worker.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
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
    as_utc,
    is_void_status,
)
from src.services.provider_budget import (
    Category,
    ProviderBudgetRefused,
    naive_utc,
    provider_category,
    utc_now,
)
from src.services.provider_work import WorkLease, WorkQueue, enqueue
from src.services.season_calendar import extra_weeks_between
from src.services.two_game_fixture_state import explicitly_void, fixture_state_key
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

    async def _enqueue_range(self, db: AsyncSession, first: datetime, last: datetime) -> str:
        key = self.census_key(first, last)
        await enqueue(
            db,
            key=key,
            kind="census",
            payload={"source": self.source, "first": first.isoformat(), "last": last.isoformat()},
            next_at=naive_utc(self.clock()),
        )
        work = await db.get(ProviderWork, key, with_for_update=True)
        if work is not None and work.last_error == "no_open_target":
            work.next_at, work.last_error = naive_utc(self.clock()), None
        return key

    async def prepare(self) -> None:
        now = naive_utc(self.clock())
        async with self.sessions() as db, db.begin():
            await prepare_calendar(db, now, lookahead=self.lookahead)
            needed: set[str] = set()
            rows = await db.execute(
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
            for game, parent, league in rows:
                first, last = (
                    london_utc(parent.starts_on),
                    london_utc(parent.starts_on + timedelta(days=2)),
                )
                key = await self._enqueue_range(db, first, last)
                needed.add(key)
                local = now.replace(tzinfo=UTC).astimezone(LONDON)
                if (
                    game.kind == "fantasy"
                    and game.opens_at <= now < game.locks_at
                    and local.weekday() == 5
                    and local.hour == 12
                ):
                    work = await db.get(ProviderWork, key, with_for_update=True)
                    if work is not None:
                        self._schedule_opening_check(work, london_utc(local.date(), 12), now)
                snapshot = await db.get(ProviderSnapshot, key)
                if snapshot is not None:
                    await self._link_game(db, game, league, snapshot)
            if self.include_legacy:
                needed |= await self._prepare_legacy(db, now)
            needed |= await self._enqueue_prices(db, now)
            for work in await db.scalars(
                select(ProviderWork)
                .where(
                    ProviderWork.kind.in_(("census", "price", "price_single")),
                    ProviderWork.payload["source"].astext == self.source,
                    ProviderWork.key.notin_(needed),
                )
                .with_for_update()
            ):
                work.next_at, work.last_error = datetime.max, "no_open_target"

    async def _prepare_legacy(self, db: AsyncSession, now: datetime) -> set[str]:
        from src.config import settings

        today = now.replace(tzinfo=UTC).astimezone(LONDON).date()
        leagues = await active_leagues(db)
        horizon = settings.slate_horizon_weeks
        needed: set[str] = set()
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
                keys = [
                    await self._enqueue_range(db, first, last)
                    for first, last in census_ranges(*window.query_bounds(label))
                ]
                needed.update(keys)
                snapshots = [await db.get(ProviderSnapshot, key) for key in keys]
                if not snapshots or any(
                    row is None or "complete_rows" not in row.payload for row in snapshots
                ):
                    continue
                fixtures: dict[str, SlateFixture] = {}
                for row in snapshots:
                    if row is None:
                        continue
                    for value in row.payload["complete_rows"]:
                        sf = SlateFixture.model_validate(value)
                        current = await db.scalar(
                            select(Fixture).where(Fixture.provider_event_id == sf.provider_event_id)
                        )
                        if current is None:
                            continue
                        state = await db.get(
                            ProviderSnapshot, fixture_state_key(self.source, sf.provider_event_id)
                        )
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
                await sync_slate(
                    db, league, Slate(starts_on=label, fixtures=list(fixtures.values()))
                )
        return needed

    async def _link_game(
        self, db: AsyncSession, game: TwoGame, league: League, snapshot: ProviderSnapshot
    ) -> None:
        wanted = selected_competition_slugs(league)
        raw = snapshot.payload.get("rows", [])
        fixtures = [SlateFixture.model_validate(value) for value in raw]
        voided = {sf.provider_event_id for sf in fixtures if is_void_status(sf.status)}
        for sf in fixtures:
            fixture = await db.scalar(
                select(Fixture).where(Fixture.provider_event_id == sf.provider_event_id)
            )
            if fixture is None:
                continue
            stamp = fixture.kickoff_utc
            in_window = (
                stamp == game.window_start
                if game.kind == "group"
                else game.window_start <= stamp < game.window_end
            )
            if (
                not in_window
                or wanted is not None
                and fixture.competition_id not in wanted
                or await explicitly_void(db, self.source, fixture.provider_event_id)
            ):
                continue
            await db.execute(
                insert(TwoGameFixture)
                .values(game_id=game.id, fixture_id=fixture.id)
                .on_conflict_do_nothing()
            )
        # A moved fixture can leave an unclaimed card. Accepted picks retain their
        # original link and history, and are resolved by settlement/corrections.
        for fixture in await db.scalars(
            select(Fixture)
            .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
            .where(TwoGameFixture.game_id == game.id)
        ):
            stamp = fixture.kickoff_utc
            in_window = (
                stamp == game.window_start
                if game.kind == "group"
                else game.window_start <= stamp < game.window_end
            )
            if (
                in_window
                and fixture.provider_event_id not in voided
                and not await explicitly_void(db, self.source, fixture.provider_event_id)
                and (wanted is None or fixture.competition_id in wanted)
            ):
                continue
            claimed = await db.scalar(
                select(GroupPick.id).where(
                    GroupPick.game_id == game.id, GroupPick.fixture_id == fixture.id
                )
            ) or await db.scalar(
                select(FantasyPick.id).where(
                    FantasyPick.game_id == game.id, FantasyPick.fixture_id == fixture.id
                )
            )
            if not claimed:
                await db.execute(
                    delete(TwoGameFixture).where(
                        TwoGameFixture.game_id == game.id, TwoGameFixture.fixture_id == fixture.id
                    )
                )
        complete = snapshot.payload.get("state") == "complete"
        linked = await db.scalar(
            select(TwoGameFixture.fixture_id).where(TwoGameFixture.game_id == game.id).limit(1)
        )
        game.coverage_state = "complete" if complete and linked is not None else "pending"
        if snapshot.payload.get("state") == "unavailable":
            game.coverage_state = "unavailable"

    async def _enqueue_prices(self, db: AsyncSession, now: datetime) -> set[str]:
        needed: set[str] = set()
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
        for fixture in fixtures:
            if await explicitly_void(db, self.source, fixture.provider_event_id):
                continue
            identity = json.dumps([self.source, self.bookmaker, fixture.provider_event_id])
            key = "price:v1:" + hashlib.sha256(identity.encode()).hexdigest()
            needed.add(key)
            await enqueue(
                db,
                key=key,
                kind="price",
                payload={"source": self.source, "event_id": fixture.provider_event_id},
                fixture_id=fixture.id,
                next_at=now,
            )
            work = await db.get(ProviderWork, key, with_for_update=True)
            if work is not None and work.last_error == "no_open_target":
                work.next_at, work.last_error = now, None
            local = now.replace(tzinfo=UTC).astimezone(LONDON)
            if work is not None and local.weekday() == 5 and local.hour == 12:
                quote_identity = json.dumps(
                    [self.source, self.bookmaker, fixture.provider_event_id], separators=(",", ":")
                )
                quote_key = "quote:v1:" + hashlib.sha256(quote_identity.encode()).hexdigest()
                quote = await db.get(ProviderSnapshot, quote_key)
                if (
                    quote is not None
                    and quote.payload.get("state") == "unavailable"
                    and quote.observed_at < london_utc(local.date(), 12)
                ):
                    self._schedule_opening_check(work, london_utc(local.date(), 12), now)
        return needed

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
                fixture_id = await db.scalar(
                    insert(Fixture)
                    .values(
                        provider_event_id=sf.provider_event_id,
                        home=sf.home,
                        away=sf.away,
                        kickoff_utc=naive_utc(sf.kickoff_utc),
                        competition=sf.competition,
                        competition_id=sf.competition_id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fixtures_provider_event",
                        set_={
                            "home": sf.home,
                            "away": sf.away,
                            "kickoff_utc": naive_utc(sf.kickoff_utc),
                            "competition": sf.competition,
                            "competition_id": sf.competition_id,
                        },
                    )
                    .returning(Fixture.id)
                )
                state = {
                    "source": self.source,
                    "event_id": sf.provider_event_id,
                    "status": sf.status,
                    "kickoff_utc": naive_utc(sf.kickoff_utc).isoformat(),
                }
                await db.execute(
                    insert(ProviderSnapshot)
                    .values(
                        key=fixture_state_key(self.source, sf.provider_event_id),
                        payload=state,
                        fixture_id=fixture_id,
                        observed_at=now,
                        expires_at=now + timedelta(seconds=self.sweep_seconds),
                    )
                    .on_conflict_do_update(
                        index_elements=[ProviderSnapshot.key],
                        set_={
                            "payload": state,
                            "fixture_id": fixture_id,
                            "observed_at": now,
                            "expires_at": now + timedelta(seconds=self.sweep_seconds),
                        },
                    )
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
