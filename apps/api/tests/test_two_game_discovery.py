"""Real dispatch, persisted pages/leases and London calendar recovery, no live service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import settings
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.profile import Profile
from src.models.two_game import (
    ConfirmedBreak,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
)
from src.services.odds_api import OddsApiProvider
from src.services.odds_provider import OddsProviderAPIError, SlateWindow
from src.services.provider_budget import BudgetPolicy, ProviderBudget
from src.services.provider_work import WorkQueue, enqueue
from src.services.two_game_discovery import DiscoveryWorker, census_ranges
from src.services.two_game_schedule import fantasy_opening, game_schedule, prepare_calendar
from src.services.two_game_storage import london_utc

WEEK = date(2180, 1, 1)
WEEK += timedelta(days=(5 - WEEK.weekday()) % 7)


@dataclass
class Clock:
    now: datetime = london_utc(WEEK - timedelta(days=1), 9)

    def __call__(self) -> datetime:
        return self.now


class CensusSource:
    def __init__(self, db_engine):
        self.clock = Clock()
        self.sessions = async_sessionmaker(db_engine, expire_on_commit=False)
        self.source = f"census-{uuid.uuid4().hex[:12]}"
        self.budget = ProviderBudget(
            self.sessions,
            meter=self.source,
            clock=self.clock,
            policy=BudgetPolicy(),
        )
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.rows: list[dict] = []
        self.malformed = False
        self.fail_offset: int | None = None
        self.price = "2.15"
        self.odds_status = 200
        self.unpriced: set[str] = set()
        self.bad_ids: set[str] = set()
        self.leagues: list[uuid.UUID] = []
        self.client = OddsApiProvider(
            "synthetic-not-a-real-key",
            budget=self.budget,
            client=httpx.AsyncClient(
                base_url="https://synthetic.invalid", transport=httpx.MockTransport(self.dispatch)
            ),
        )

    def event(self, suffix: str, day: date = WEEK, hour: int = 15, minute: int = 0) -> str:
        event_id = f"{self.source}-{suffix}"
        self.rows.append(
            {
                "id": event_id,
                "home": f"Home {suffix}",
                "away": f"Away {suffix}",
                "date": london_utc(day, hour, minute).isoformat() + "Z",
                "status": "pending",
                "league": {"name": "Premier League", "slug": "england-premier-league"},
            }
        )
        return event_id

    async def dispatch(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.calls.append((request.url.path, params))
        if request.url.path == "/events":
            offset, limit = int(params["skip"]), int(params["limit"])
            if self.malformed or self.fail_offset == offset:
                return httpx.Response(200, json={"truncated": True})
            rows = [row for row in self.rows if params["from"] <= row["date"] <= params["to"]]
            return httpx.Response(200, json=rows[offset : offset + limit])
        ids = (params.get("eventIds") or params.get("eventId") or "").split(",")
        if self.odds_status != 200:
            return httpx.Response(self.odds_status, json={"error": "synthetic refusal"})
        if self.bad_ids.intersection(ids):
            return httpx.Response(400, json={"error": "synthetic expired event"})
        return httpx.Response(
            200,
            json=[
                {
                    "id": event,
                    "home": "Home",
                    "away": "Away",
                    "bookmakers": {
                        "Bet365": [
                            {
                                "name": "ML",
                                "odds": [{"home": self.price, "draw": "3.1", "away": "4"}],
                            }
                        ]
                    },
                }
                for event in ids
                if event not in self.unpriced
            ],
        )

    async def acquire(self):
        return self.client

    def worker(self, **kwargs) -> DiscoveryWorker:
        options = {"include_legacy": False, "units_per_pass": 1, **kwargs}
        return DiscoveryWorker(
            self.sessions,
            self.acquire,
            source=self.source,
            bookmaker="Bet365",
            clock=self.clock,
            **options,
        )

    async def league(self, *, first: date = WEEK, offset: int | None = None) -> uuid.UUID:
        async with self.sessions() as db, db.begin():
            profile = Profile(display_name=f"Synthetic {uuid.uuid4().hex}", pin_hash="x")
            db.add(profile)
            await db.flush()
            league = League(
                slug=f"census-{uuid.uuid4().hex}",
                name="Synthetic census",
                created_by=profile.id,
                pick_open_offset_minutes=offset,
            )
            db.add(league)
            await db.flush()
            db.add(
                TwoGameRollout(
                    league_id=league.id,
                    first_week=first,
                    enabled=True,
                    effective_opening=london_utc(first - timedelta(days=7), 12),
                )
            )
            self.leagues.append(league.id)
            return league.id

    async def close(self):
        await self.client.close()
        async with self.sessions() as db, db.begin():
            await db.execute(
                update(League).where(League.id.in_(self.leagues)).values(deleted_at=self.clock.now)
            )
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id.in_(self.leagues))
                .values(enabled=False)
            )


@pytest_asyncio.fixture
async def source(db_engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    item = CensusSource(db_engine)
    try:
        yield item
    finally:
        await item.close()


async def snapshot(source: CensusSource, worker: DiscoveryWorker, label: date = WEEK):
    key = worker.census_key(london_utc(label), london_utc(label + timedelta(days=2)))
    async with source.sessions() as db:
        return await db.get(ProviderSnapshot, key)


@pytest.mark.asyncio
async def test_inactive_gates_never_acquire_provider_or_create_work(source, monkeypatch):
    calls = 0

    async def forbidden():
        nonlocal calls
        calls += 1
        raise AssertionError("inactive worker acquired provider")

    worker = source.worker()
    worker.acquire = forbidden
    assert await worker.run() == 0
    league = await source.league()
    monkeypatch.setattr(settings, "two_games_enabled", False)
    assert await worker.run() == 0
    async with source.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(TwoGame).where(TwoGame.league_id == league)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProviderWork)
                .where(ProviderWork.payload["source"].astext == source.source)
            )
            == 0
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_paginated_census_has_no_bookmaker_filter_and_excludes_monday(source):
    source.event("sat", WEEK, 15)
    source.event("sun", WEEK + timedelta(days=1), 23, 59)
    source.event("monday", WEEK + timedelta(days=2), 0)
    first = await source.client.fetch_census_page(WEEK, limit=2)
    assert first.raw_count == 2 and not first.complete and first.next_cursor == "2"
    second = await source.client.fetch_census_page(WEEK, cursor=first.next_cursor, limit=2)
    assert second.complete and second.fixtures == [] and second.raw_count == 1
    assert len(source.calls) == 2
    assert source.calls[0][1]["sport"] == "football"
    assert not {"league", "bookmaker", "bookmakers"}.intersection(source.calls[0][1])
    assert source.calls[1][1]["skip"] == "2"


@pytest.mark.asyncio
async def test_full_unpriced_page_then_empty_page_is_complete_but_never_a_break(source):
    source.event("a")
    source.event("b")
    page = await source.client.fetch_census_page(WEEK, limit=2)
    empty = await source.client.fetch_census_page(WEEK, cursor=page.next_cursor, limit=2)
    assert len(page.fixtures) == 2 and not page.complete
    assert empty.complete and empty.raw_count == 0
    async with source.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ConfirmedBreak)) == 0


@pytest.mark.asyncio
async def test_malformed_page_is_unknown_not_success(source):
    source.malformed = True
    with pytest.raises(OddsProviderAPIError):
        await source.client.fetch_census_page(WEEK)
    assert len(source.calls) == 1 and (await source.budget.view()).spent_day == 1


@pytest.mark.asyncio
async def test_page_commit_cursor_restart_and_window_memberships_are_independent(source):
    league = await source.league()
    source.event("early", WEEK, 12, 29)
    opening = source.event("opening", WEEK, 12, 30)
    group = source.event("group")
    sunday = source.event("sunday", WEEK + timedelta(days=1), 23, 59)
    source.event("excluded", WEEK + timedelta(days=2), 0)
    worker = source.worker(page_size=2)
    # Each new worker/process resumes the committed offset; interleaved next-card
    # discovery and price work are allowed and counted at the actual transport.
    for _ in range(20):
        await worker.run()
        row = await snapshot(source, worker)
        if row is not None and row.payload.get("state") == "complete":
            break
        source.clock.now += timedelta(minutes=6)
        worker = source.worker(page_size=2)
    else:
        raise AssertionError("bounded census did not finish")
    async with source.sessions() as db:
        games = list(
            await db.scalars(
                select(TwoGame)
                .join(Gameweek)
                .where(Gameweek.league_id == league, Gameweek.starts_on == WEEK)
            )
        )
        actual = {}
        for game in games:
            actual[game.kind] = set(
                await db.scalars(
                    select(Fixture.provider_event_id)
                    .join(TwoGameFixture)
                    .where(TwoGameFixture.game_id == game.id)
                )
            )
        assert actual == {"group": {group}, "fantasy": {opening, group, sunday}}
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ConfirmedBreak)
                .where(ConfirmedBreak.league_id == league)
            )
            == 0
        )
    offsets = [
        int(params["skip"])
        for path, params in source.calls
        if path == "/events" and params["from"].startswith(WEEK.isoformat())
    ]
    assert offsets == [0, 2, 4]
    assert (await source.budget.view()).spent_day == len(source.calls)


@pytest.mark.asyncio
async def test_later_page_failure_preserves_prior_page_and_cursor(source):
    await source.league()
    source.event("a")
    source.event("b")
    source.event("c")
    worker = source.worker(page_size=2)
    await worker.prepare()
    key = worker.census_key(london_utc(WEEK), london_utc(WEEK + timedelta(days=2)))
    # Select this page directly so unrelated next-card work cannot determine ordering.
    async with source.sessions() as db, db.begin():
        await db.execute(
            update(ProviderWork)
            .where(ProviderWork.key != key, ProviderWork.payload["source"].astext == source.source)
            .values(next_at=datetime.max)
        )
    await worker.run(prepare=False)
    source.clock.now += timedelta(minutes=6)
    source.fail_offset = 2
    # Page completion legitimately enqueues fair price work. Isolate the next-page
    # failure target too; the separate end-to-end test exercises that interleaving.
    async with source.sessions() as db, db.begin():
        await db.execute(
            update(ProviderWork)
            .where(ProviderWork.key != key, ProviderWork.payload["source"].astext == source.source)
            .values(next_at=datetime.max)
        )
    await worker.run(prepare=False)
    async with source.sessions() as db:
        work = await db.get(ProviderWork, key)
        row = await db.get(ProviderSnapshot, key)
        assert work is not None and work.cursor == "2" and work.last_error == "OddsProviderAPIError"
        assert row is not None and len(row.payload["rows"]) == 2
    source.fail_offset = None
    source.clock.now += timedelta(minutes=12)
    await source.worker(page_size=2).run(prepare=False)
    row = await snapshot(source, worker)
    assert row is not None and row.payload["state"] == "complete" and len(row.payload["rows"]) == 3
    assert [int(p["skip"]) for path, p in source.calls if path == "/events"] == [0, 2, 2]


@pytest.mark.parametrize("label,hours", [(date(2027, 4, 3), 167), (date(2026, 10, 31), 169)])
def test_fantasy_calendar_crosses_dst_without_fixed_hour_subtraction(label, hours):
    assert london_utc(label, 12) - fantasy_opening(label, set()) == timedelta(hours=hours)


def test_group_policy_is_london_calendar_time_and_late_discovery_never_backdates():
    label = date(2027, 4, 3)
    league = League(pick_open_offset_minutes=7 * 24 * 60)
    schedule = game_schedule("group", label, league, set(), london_utc(label - timedelta(days=1)))
    assert schedule[0] == london_utc(label - timedelta(days=7), 15)
    assert schedule[1] - schedule[0] == timedelta(hours=166, minutes=30)
    league.pick_open_offset_minutes = None
    late = game_schedule("group", label, league, set(), london_utc(label, 16))
    assert late[0] == late[1] == london_utc(label, 14, 30)
    league.pick_open_offset_minutes = 10
    with pytest.raises(ValueError, match="later than"):
        game_schedule("group", label, league, set(), london_utc(label))


@pytest.mark.asyncio
async def test_confirmed_breaks_open_w3_at_legacy_w0_noon_and_empty_never_skips(source):
    first = WEEK + timedelta(days=7)
    league = await source.league(first=first)
    async with source.sessions() as db, db.begin():
        parent = Gameweek(
            league_id=league,
            starts_on=WEEK,
            locks_at_utc=london_utc(WEEK, 14, 30),
            status=GameweekStatus.open,
        )
        db.add(parent)
        owner = await db.get(League, league)
        assert owner is not None
        for label in (first, first + timedelta(days=7)):
            db.add(
                ConfirmedBreak(
                    league_id=league,
                    week_label=label,
                    evidence="Synthetic confirmed calendar",
                    confirmed_by=owner.created_by,
                )
            )
    await source.worker().prepare()
    async with source.sessions() as db:
        game = await db.scalar(
            select(TwoGame)
            .join(Gameweek)
            .where(
                TwoGame.league_id == league,
                Gameweek.starts_on == first + timedelta(days=14),
                TwoGame.kind == "fantasy",
            )
        )
        assert game is not None and game.opens_at == london_utc(WEEK, 12)
        old = await db.scalar(
            select(Gameweek).where(Gameweek.league_id == league, Gameweek.starts_on == WEEK)
        )
        assert old is not None and old.format == "legacy"
        assert (
            await db.scalar(
                select(func.count()).select_from(TwoGame).where(TwoGame.week_id == old.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_late_break_preserves_announced_game_and_reports_schedule_conflict(source):
    league = await source.league()
    worker = source.worker()
    await worker.prepare()
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, league)
        assert owner is not None
        before = await db.scalar(
            select(TwoGame)
            .join(Gameweek)
            .where(
                TwoGame.league_id == league,
                Gameweek.starts_on == WEEK + timedelta(days=7),
                TwoGame.kind == "fantasy",
            )
        )
        assert before is not None
        identity, opening = before.id, before.opens_at
        db.add(
            ConfirmedBreak(
                league_id=league,
                week_label=WEEK,
                evidence="Late synthetic evidence",
                confirmed_by=owner.created_by,
            )
        )
    await worker.prepare()
    async with source.sessions() as db:
        after = await db.get(TwoGame, identity)
        progress = await db.get(ProviderWork, f"calendar:{league}")
        assert after is not None and after.opens_at == opening
        assert progress is not None and progress.payload["state"] == "schedule_conflict"
        assert str(identity) in progress.payload["conflicting_game_ids"]


@pytest.mark.asyncio
async def test_exact_cutover_legacy_collision_is_reported_without_relabelling(source):
    league = await source.league()
    async with source.sessions() as db, db.begin():
        # Already-existing legacy is allowed at the storage boundary; it must become
        # explicit calendar conflict rather than silently shifting owner activation.
        await db.execute(
            update(TwoGameRollout).where(TwoGameRollout.league_id == league).values(enabled=False)
        )
        old = Gameweek(league_id=league, starts_on=WEEK, locks_at_utc=london_utc(WEEK, 14, 30))
        db.add(old)
        await db.flush()
        old_id = old.id
        await db.execute(
            update(TwoGameRollout).where(TwoGameRollout.league_id == league).values(enabled=True)
        )
    await source.worker().prepare()
    async with source.sessions() as db:
        progress = await db.get(ProviderWork, f"calendar:{league}")
        assert progress is not None and progress.payload["state"] == "schedule_conflict"
        assert f"legacy_week:{old_id}" in progress.payload["conflicting_game_ids"]
        assert (await db.get(Gameweek, old_id)).format == "legacy"


@pytest.mark.asyncio
async def test_bounded_unknown_horizon_resumes_and_long_group_openings_are_not_capped(source):
    league = await source.league(offset=20 * 7 * 24 * 60)
    async with source.sessions() as db, db.begin():
        await prepare_calendar(db, source.clock.now, lookahead=12)
    async with source.sessions() as db:
        progress = await db.get(ProviderWork, f"calendar:{league}")
        assert progress is not None and progress.payload["state"] == "horizon_pending"
        assert progress.cursor == (WEEK + timedelta(weeks=12)).isoformat()
    async with source.sessions() as db, db.begin():
        await prepare_calendar(db, source.clock.now, lookahead=12)
    async with source.sessions() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(TwoGame)
            .where(
                TwoGame.league_id == league,
                TwoGame.kind == "group",
                TwoGame.opens_at <= source.clock.now,
            )
        )
        assert count == 20


@pytest.mark.asyncio
async def test_work_crash_or_expired_failure_rotates_and_old_token_cannot_overwrite(source):
    queue = WorkQueue(source.sessions, clock=source.clock, lease_seconds=5)
    keys = [f"lease-{source.source}-{suffix}" for suffix in ("a", "b")]
    async with source.sessions() as db, db.begin():
        for key in keys:
            await enqueue(db, key=key, kind=source.source, payload={}, next_at=source.clock.now)
    first = await queue.claim((source.source,))
    assert first is not None and first.key == keys[0]
    source.clock.now += timedelta(seconds=6)
    second = await queue.claim((source.source,))
    assert second is not None and second.key == keys[1]
    await queue.defer(first, "expired_http_failure")
    async with source.sessions() as db:
        row = await db.get(ProviderWork, first.key)
        assert (
            row is not None
            and row.last_error == "expired_http_failure"
            and row.next_at > source.clock.now
        )
    source.clock.now += timedelta(minutes=7)
    reclaimed = await queue.claim((source.source,))
    assert reclaimed is not None
    await queue.defer(second, "old_owner")
    if reclaimed.key == second.key:
        async with source.sessions() as db:
            row = await db.get(ProviderWork, reclaimed.key)
            assert row is not None and row.lease_token == reclaimed.token and row.last_error is None


def test_legacy_friday_monday_window_keeps_weekdays_and_shares_weekend():
    friday = WEEK - timedelta(days=1)
    ranges = census_ranges(
        *SlateWindow(
            start_weekday=4, start_minute=19 * 60, end_weekday=0, end_minute=22 * 60
        ).query_bounds(friday)
    )
    assert ranges == [
        (london_utc(friday), london_utc(WEEK)),
        (london_utc(WEEK), london_utc(WEEK + timedelta(days=2))),
        (london_utc(WEEK + timedelta(days=2)), london_utc(WEEK + timedelta(days=3))),
    ]


async def one_census(source, worker, label):
    await worker.prepare()
    key = worker.census_key(london_utc(label), london_utc(label + timedelta(days=2)))
    async with source.sessions() as db, db.begin():
        await db.execute(
            update(ProviderWork).where(ProviderWork.key == key).values(next_at=source.clock.now)
        )
    lease = await worker.queue.claim(("census",), source=source.source, keys=[key])
    assert lease is not None
    await worker._page(lease, source.client, "background")


@pytest.mark.asyncio
async def test_authoritative_void_removes_unclaimed_links_but_retains_accepted_history(source):
    from src.models.league_membership import LeagueMembership
    from src.models.two_game import GroupPick
    from src.services.two_game_fixture_state import explicitly_void

    league = await source.league()
    claimed_id, unclaimed_id = source.event("claimed"), source.event("unclaimed")
    worker = source.worker()
    await one_census(source, worker, WEEK)
    async with source.sessions() as db, db.begin():
        game = await db.scalar(
            select(TwoGame)
            .join(Gameweek)
            .where(TwoGame.league_id == league, Gameweek.starts_on == WEEK, TwoGame.kind == "group")
        )
        owner = await db.get(League, league)
        fixture = await db.scalar(select(Fixture).where(Fixture.provider_event_id == claimed_id))
        assert game is not None and owner is not None and fixture is not None
        db.add(LeagueMembership(league_id=league, player_id=owner.created_by))
        await db.flush()
        pick = GroupPick(
            league_id=league,
            week_id=game.week_id,
            game_id=game.id,
            fixture_id=fixture.id,
            player_id=owner.created_by,
            market="MATCH_ODDS",
            outcome="HOME",
            runner_name="Home",
            operation_id=uuid.uuid4(),
        )
        db.add(pick)
        await db.flush()
        pick_id = pick.id
    for row in source.rows:
        row["status"] = "postponed"
    source.clock.now += timedelta(minutes=6)
    await one_census(source, worker, WEEK)
    async with source.sessions() as db:
        linked = set(
            await db.scalars(
                select(Fixture.provider_event_id)
                .join(TwoGameFixture)
                .join(TwoGame)
                .where(TwoGame.league_id == league)
            )
        )
        assert linked == {claimed_id}
        assert unclaimed_id not in linked
        assert await db.get(GroupPick, pick_id) is not None
        assert await explicitly_void(db, source.source, claimed_id)
        work = list(
            await db.scalars(
                select(ProviderWork).where(
                    ProviderWork.payload["source"].astext == source.source,
                    ProviderWork.kind.in_(("price", "price_single")),
                )
            )
        )
        assert all(
            row.last_error == "no_open_target" and row.next_at == datetime.max for row in work
        )


@pytest.mark.asyncio
async def test_suspension_preserves_games_and_stops_new_discovery_and_pricing(source):
    league = await source.league()
    source.event("keep")
    worker = source.worker()
    await one_census(source, worker, WEEK)
    before = len(source.calls)
    async with source.sessions() as db, db.begin():
        ids = set(await db.scalars(select(TwoGame.id).where(TwoGame.league_id == league)))
        await db.execute(
            update(TwoGameRollout).where(TwoGameRollout.league_id == league).values(suspended=True)
        )
    source.clock.now += timedelta(minutes=6)
    assert await worker.run() == 0
    async with source.sessions() as db:
        assert set(await db.scalars(select(TwoGame.id).where(TwoGame.league_id == league))) == ids
    assert len(source.calls) == before


@pytest.mark.asyncio
async def test_noon_checks_target_next_fantasy_and_recheck_pre_noon_negative_once(source):
    from src.services.two_game_quotes import SharedQuotes

    await source.league()
    target = WEEK + timedelta(days=7)
    event = source.event("next-negative", target)
    source.unpriced.add(event)
    worker = source.worker()
    await one_census(source, worker, target)
    source.clock.now = london_utc(WEEK, 11, 59)
    cache = SharedQuotes(
        source.sessions, source.client, source=source.source, bookmaker="Bet365", clock=source.clock
    )
    await cache.refresh_many([event], category="foreground")
    source.clock.now = london_utc(WEEK, 12)
    source.unpriced.clear()
    await worker.prepare()
    # This optional old backlog would previously consume the noon allowance first.
    unrelated = f"a-old-unrelated-{source.source}"
    async with source.sessions() as db, db.begin():
        await enqueue(
            db,
            key=unrelated,
            kind="census",
            payload={
                "source": source.source,
                "first": london_utc(WEEK - timedelta(days=1)).isoformat(),
                "last": london_utc(WEEK).isoformat(),
            },
            next_at=source.clock.now - timedelta(days=1),
        )
    before = len(source.calls)
    for _ in range(3):
        await worker.run(prepare=False)
    noon = source.calls[before:]
    assert len(noon) == 2
    assert sum(path.startswith("/odds") for path, _ in noon) == 1
    assert all(
        params.get("from", target.isoformat()).startswith(target.isoformat())
        for path, params in noon
        if path == "/events"
    )
    async with source.sessions() as db:
        work = await db.get(ProviderWork, unrelated)
        assert work is not None and work.attempts == 0
    view = (await cache.peek_many([event]))[event]
    assert view.availability == "available" and view.observed_at == source.clock.now


@pytest.mark.asyncio
async def test_repeated_noon_preparation_preserves_failed_negative_recheck_backoff(source):
    from src.services.two_game_quotes import SharedQuotes

    await source.league()
    target = WEEK + timedelta(days=7)
    event = source.event("next-refused", target)
    source.unpriced.add(event)
    worker = source.worker()
    await one_census(source, worker, target)
    source.clock.now = london_utc(WEEK, 11, 59)
    cache = SharedQuotes(
        source.sessions, source.client, source=source.source, bookmaker="Bet365", clock=source.clock
    )
    await cache.refresh_many([event], category="foreground")
    source.clock.now = london_utc(WEEK, 12)
    await worker.prepare()
    # Census succeeds first; the opening quote then receives a real fake 403.
    await worker.run(prepare=False)
    source.odds_status = 403
    await worker.run(prepare=False)
    async with source.sessions() as db:
        work = await db.scalar(
            select(ProviderWork).where(ProviderWork.payload["event_id"].astext == event)
        )
        assert work is not None and work.last_error is not None
        key, retry_at = work.key, work.next_at
        assert retry_at > source.clock.now
    before = len(source.calls)
    source.clock.now += timedelta(minutes=1)
    for _ in range(3):
        await worker.prepare()
        async with source.sessions() as db:
            after = await db.get(ProviderWork, key)
            assert after is not None and after.next_at == retry_at
    await worker.run(prepare=False)
    assert len(source.calls) == before


@pytest.mark.asyncio
async def test_arbitrary_legacy_window_uses_shared_complete_census_and_legacy_negative_marker(
    source, monkeypatch
):
    monkeypatch.setattr(settings, "slate_horizon_weeks", 1)
    await source.league()
    async with source.sessions() as db, db.begin():
        owner = Profile(display_name=f"Legacy {uuid.uuid4().hex}", pin_hash="x")
        db.add(owner)
        await db.flush()
        legacy = League(
            slug=f"legacy-{uuid.uuid4().hex}",
            name="Synthetic legacy weekday",
            created_by=owner.id,
            slate_start_weekday=4,
            slate_start_minute=19 * 60,
            slate_end_weekday=0,
            slate_end_minute=22 * 60,
        )
        db.add(legacy)
        await db.flush()
        legacy_id = legacy.id
        source.leagues.append(legacy_id)
    friday = WEEK - timedelta(days=1)
    unpriced = source.event("friday", friday, 19)
    saturday = source.event("saturday", WEEK, 15)
    sunday = source.event("sunday", WEEK + timedelta(days=1), 21)
    monday = source.event("monday", WEEK + timedelta(days=2), 22)
    source.event("too-late", WEEK + timedelta(days=2), 22, 1)
    source.unpriced.add(unpriced)
    worker = source.worker(include_legacy=True)
    for _ in range(20):
        await worker.run()
        source.clock.now += timedelta(minutes=6)
    async with source.sessions() as db:
        parent = await db.scalar(
            select(Gameweek).where(Gameweek.league_id == legacy_id, Gameweek.starts_on == friday)
        )
        assert parent is not None and parent.format == "legacy"
        linked = set(
            await db.scalars(
                select(Fixture.provider_event_id)
                .join(GameweekFixture)
                .where(GameweekFixture.gameweek_id == parent.id)
            )
        )
        assert linked == {unpriced, saturday, sunday, monday}
        fixture = await db.scalar(select(Fixture).where(Fixture.provider_event_id == unpriced))
        assert fixture is not None and fixture.odds_unpriced_since_utc is not None
    weekend_calls = [
        params
        for path, params in source.calls
        if path == "/events" and params["from"].startswith(WEEK.isoformat())
    ]
    assert len(weekend_calls) == 1
    unpriced_calls = [
        params
        for path, params in source.calls
        if path.startswith("/odds")
        and unpriced in (params.get("eventIds") or params.get("eventId") or "").split(",")
    ]
    assert len(unpriced_calls) == 1


@pytest.mark.asyncio
async def test_rejected_fixture_chunk_splits_durably_and_valid_later_prices_finish(source):
    await source.league()
    events = [source.event(f"isolate-{index}") for index in range(30)]
    source.bad_ids.add(events[0])
    worker = source.worker()
    for _ in range(35):
        await worker.run()
        async with source.sessions() as db:
            snapshots = list(
                await db.scalars(
                    select(ProviderSnapshot).where(
                        ProviderSnapshot.payload["provider"].astext == source.source
                    )
                )
            )
        positive = [row for row in snapshots if row.payload.get("state") == "available"]
        negative = [row for row in snapshots if row.payload.get("state") == "unavailable"]
        if len(positive) == 29 and len(negative) == 1:
            break
        source.clock.now += timedelta(minutes=6)
        worker = source.worker()
    else:
        raise AssertionError("one rejected fixture starved later valid price work")
    assert {row.payload["odds"]["provider_event_id"] for row in positive} == set(events[1:])
    assert len(source.calls) <= 20


@pytest.mark.asyncio
@pytest.mark.parametrize("label,hours", [(date(2027, 3, 27), 47), (date(2026, 10, 24), 49)])
async def test_census_bounds_follow_london_days_across_sunday_dst(source, label, hours):
    event = source.event("dst-sunday", label + timedelta(days=1), 23, 59)
    monday = source.event("dst-monday", label + timedelta(days=2), 0)
    page = await source.client.fetch_census_page(label)
    assert {row.provider_event_id for row in page.fixtures} == {event}
    assert monday not in {row.provider_event_id for row in page.fixtures}
    params = source.calls[0][1]
    first = datetime.fromisoformat(params["from"].replace("Z", "+00:00"))
    last = datetime.fromisoformat(params["to"].replace("Z", "+00:00"))
    assert last - first == timedelta(hours=hours)


@pytest.mark.asyncio
async def test_sunday_addition_changes_only_fantasy_membership_and_no_clock(source):
    league = await source.league()
    saturday = source.event("initial")
    worker = source.worker()
    await one_census(source, worker, WEEK)
    async with source.sessions() as db:
        games = list(
            await db.scalars(
                select(TwoGame)
                .join(Gameweek)
                .where(TwoGame.league_id == league, Gameweek.starts_on == WEEK)
            )
        )
        clocks = {
            game.id: (game.opens_at, game.locks_at, game.window_start, game.window_end)
            for game in games
        }
    sunday = source.event("late-sunday", WEEK + timedelta(days=1), 16)
    source.clock.now += timedelta(minutes=6)
    await one_census(source, worker, WEEK)
    async with source.sessions() as db:
        for game in await db.scalars(select(TwoGame).where(TwoGame.id.in_(clocks))):
            assert (game.opens_at, game.locks_at, game.window_start, game.window_end) == clocks[
                game.id
            ]
            linked = set(
                await db.scalars(
                    select(Fixture.provider_event_id)
                    .join(TwoGameFixture)
                    .where(TwoGameFixture.game_id == game.id)
                )
            )
            assert linked == ({saturday} if game.kind == "group" else {saturday, sunday})


@pytest.mark.asyncio
async def test_twelve_confirmed_breaks_persist_unknown_horizon_then_continue(source):
    league = await source.league()
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, league)
        assert owner is not None
        for index in range(12):
            db.add(
                ConfirmedBreak(
                    league_id=league,
                    week_label=WEEK + timedelta(weeks=index),
                    evidence="Synthetic approved break",
                    confirmed_by=owner.created_by,
                )
            )
    await source.worker().prepare()
    async with source.sessions() as db:
        progress = await db.get(ProviderWork, f"calendar:{league}")
        assert progress is not None and progress.payload["state"] == "horizon_pending"
        assert progress.cursor == (WEEK + timedelta(weeks=12)).isoformat()
        assert (
            await db.scalar(
                select(func.count()).select_from(TwoGame).where(TwoGame.league_id == league)
            )
            == 0
        )
    await source.worker().prepare()
    async with source.sessions() as db:
        first = await db.scalar(
            select(TwoGame)
            .join(Gameweek)
            .where(TwoGame.league_id == league, TwoGame.kind == "fantasy")
            .order_by(Gameweek.starts_on)
        )
        assert first is not None and first.opens_at == london_utc(WEEK - timedelta(days=7), 12)


@pytest.mark.asyncio
async def test_enabled_legacy_scheduler_entry_points_use_the_same_resumable_worker(
    source, monkeypatch
):
    from unittest.mock import AsyncMock

    from src import scheduler

    await source.league()
    worker = source.worker()
    monkeypatch.setattr(scheduler, "_two_game_discovery_worker", lambda: worker)
    silence, football = AsyncMock(), AsyncMock()
    monkeypatch.setattr(scheduler, "report_discovery_silence", silence)
    monkeypatch.setattr(scheduler, "report_football_provider_health", football)
    forbidden = AsyncMock(side_effect=AssertionError("old all-at-once acquisition"))
    monkeypatch.setattr(scheduler.odds_session, "acquire", forbidden)
    for run in (
        scheduler.run_discover_fixtures,
        scheduler.run_discover_full_catalogue,
        scheduler.run_refresh_slate,
        scheduler.run_warm_odds_marker,
    ):
        assert await run()
    assert forbidden.await_count == 0
    assert len(source.calls) == 1

    assert silence.await_count == football.await_count == 4


@pytest.mark.asyncio
async def test_old_cached_census_cannot_reinsert_a_fixture_moved_by_another_range(source):
    league = await source.league()
    event = source.event("moved-between-ranges")
    worker = source.worker()
    await one_census(source, worker, WEEK)
    target = WEEK + timedelta(days=7)
    source.rows[0]["date"] = london_utc(target, 15).isoformat() + "Z"
    source.clock.now += timedelta(minutes=6)
    # This commits the new global kickoff while the earlier census still stores the
    # old one. Preparation must not trip the immutable window insertion guard.
    await one_census(source, worker, target)
    async with source.sessions() as db:
        old = list(
            await db.scalars(
                select(TwoGameFixture)
                .join(TwoGame)
                .join(Gameweek)
                .where(TwoGame.league_id == league, Gameweek.starts_on == WEEK)
            )
        )
        new = list(
            await db.scalars(
                select(Fixture.provider_event_id)
                .join(TwoGameFixture)
                .join(TwoGame)
                .join(Gameweek)
                .where(TwoGame.league_id == league, Gameweek.starts_on == target)
            )
        )
        assert old == []
        assert new == [event, event]


@pytest.mark.asyncio
async def test_discovery_health_requires_usable_completed_child_evidence(source, monkeypatch):
    from src.models.league_membership import LeagueMembership
    from src.services.discovery_health import discovery_health

    league = await source.league()
    source.event("healthy")
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, league)
        assert owner is not None
        db.add(LeagueMembership(league_id=league, player_id=owner.created_by))
    worker = source.worker()
    await worker.prepare()
    async with source.sessions() as db:
        pending = await discovery_health(
            db, source.clock.now, stale_after_hours=24, provider_source=source.source
        )
        assert league in {row.league_id for row in pending.leagues_without_open_round}
        assert pending.hours_since_usable_discovery is None
    await one_census(source, worker, WEEK)
    before = len(source.calls)
    async with source.sessions() as db:
        healthy = await discovery_health(
            db, source.clock.now, stale_after_hours=24, provider_source=source.source
        )
        assert league not in {row.league_id for row in healthy.leagues_without_open_round}
        assert healthy.hours_since_usable_discovery == 0
        assert not healthy.stale
    monkeypatch.setattr(settings, "two_games_enabled", False)
    async with source.sessions() as db:
        inactive = await discovery_health(
            db, source.clock.now, stale_after_hours=24, provider_source=source.source
        )
        assert league in {row.league_id for row in inactive.leagues_without_open_round}
        assert inactive.hours_since_usable_discovery is None
    assert len(source.calls) == before


@pytest.mark.asyncio
async def test_cached_legacy_w0_cannot_overwrite_newer_shared_w1_fixture_move(source, monkeypatch):
    monkeypatch.setattr(settings, "slate_horizon_weeks", 1)
    league = await source.league(first=WEEK + timedelta(days=7))
    event = source.event("legacy-moves-to-new")
    worker = source.worker(include_legacy=True)
    await one_census(source, worker, WEEK)
    async with source.sessions() as db:
        old = await db.scalar(
            select(Gameweek).where(Gameweek.league_id == league, Gameweek.starts_on == WEEK)
        )
        assert old is not None and old.format == "legacy"
        old_id = old.id
    source.rows[0]["date"] = london_utc(WEEK + timedelta(days=7), 15).isoformat() + "Z"
    source.clock.now += timedelta(minutes=6)
    await one_census(source, worker, WEEK + timedelta(days=7))
    for _ in range(2):
        await worker.prepare()
    async with source.sessions() as db:
        fixture = await db.scalar(select(Fixture).where(Fixture.provider_event_id == event))
        assert fixture is not None and fixture.kickoff_utc == london_utc(
            WEEK + timedelta(days=7), 15
        )
        new = list(
            await db.scalars(
                select(TwoGameFixture)
                .join(TwoGame)
                .join(Gameweek)
                .where(TwoGame.league_id == league, Gameweek.starts_on == WEEK + timedelta(days=7))
            )
        )
        assert len(new) == 2 and all(link.fixture_id == fixture.id for link in new)
        assert (await db.get(Gameweek, old_id)).format == "legacy"


@pytest.mark.parametrize(
    ("moved_status", "fresh_status", "year"),
    [
        ("pending", "pending", 2300),
        ("postponed", "pending", 2301),
        ("pending", "postponed", 2302),
        ("postponed", "postponed", 2303),
    ],
)
@pytest.mark.asyncio
async def test_legacy_fresh_reschedule_reinstates_new_cards_despite_old_void_census(
    source, monkeypatch, moved_status, fresh_status, year
):
    from src.services import gameweek as legacy_service
    from src.services.gameweek import populate_cadence_rounds
    from src.services.odds_provider import Slate, SlateFixture
    from src.services.two_game_fixture_state import fixture_state_key

    # A separate season keeps the legacy pool genuinely empty at the fallback.
    label = date(year, 1, 1)
    label += timedelta(days=(5 - label.weekday()) % 7)
    source.clock.now = london_utc(label - timedelta(days=1), 9)
    monkeypatch.setattr(legacy_service, "_utc_now", source.clock)
    source.source = "oddsapi"
    league_id = await source.league(first=label)
    event = source.event(f"restored-{uuid.uuid4().hex[:12]}", day=label)
    source.rows[0]["status"] = "postponed"
    worker = source.worker(include_legacy=True)
    await one_census(source, worker, label)

    moved = label + timedelta(days=7)
    source.rows[0].update(date=london_utc(moved, 15).isoformat() + "Z", status=moved_status)
    source.clock.now += timedelta(minutes=6)
    await one_census(source, worker, moved)

    async def fresh_legacy(window, starts_on, **kwargs):
        assert starts_on == label
        return Slate(
            starts_on=label,
            fixtures=[
                SlateFixture(
                    provider_event_id=event,
                    home="Reinstated home",
                    away="Reinstated away",
                    competition="Premier League",
                    competition_id="england-premier-league",
                    kickoff_utc=london_utc(label, 15),
                    status=fresh_status,
                )
            ],
        )

    monkeypatch.setattr(source.client, "fetch_slate", fresh_legacy)
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, league_id)
        legacy = League(
            slug=f"legacy-reinstatement-{uuid.uuid4().hex}",
            name="Synthetic legacy reinstatement",
            created_by=owner.created_by,
        )
        db.add(legacy)
        await db.flush()
        source.leagues.append(legacy.id)
        populated = await populate_cadence_rounds(
            db, source.client, legacy, label - timedelta(days=1), 1, now=source.clock.now
        )
        # This proves the real on-demand empty-pool -> refresh_slate -> sync_slate path.
        assert populated.fetched_dates == [label]
        assert populated.created_dates == ([label] if fresh_status == "pending" else [])
        fixture = await db.scalar(select(Fixture).where(Fixture.provider_event_id == event))
        assert fixture.kickoff_utc == london_utc(label, 15)
        shared = await db.get(ProviderSnapshot, fixture_state_key(source.source, event))
        assert shared.payload["status"] == fresh_status
    old = await snapshot(source, worker, label)
    assert old.payload["rows"][0]["status"] == "postponed"
    before = len(source.calls)
    for _ in range(2):
        await worker.prepare()
        async with source.sessions() as db:
            rows = (
                await db.execute(
                    select(TwoGame.kind, Fixture.provider_event_id)
                    .join(TwoGameFixture, TwoGameFixture.game_id == TwoGame.id)
                    .join(Fixture, Fixture.id == TwoGameFixture.fixture_id)
                    .join(Gameweek, Gameweek.id == TwoGame.week_id)
                    .where(TwoGame.league_id == league_id, Gameweek.starts_on == label)
                    .order_by(TwoGame.kind)
                )
            ).all()
            expected = [("fantasy", event), ("group", event)] if fresh_status == "pending" else []
            assert rows == expected
    # The last observation is a provider-port seam; preparation buys no new HTTP.
    assert len(source.calls) == before == 2


@pytest.mark.asyncio
async def test_fresh_legacy_waiting_for_calendar_does_not_hold_shared_fixture(source, monkeypatch):
    import asyncio

    from sqlalchemy import text

    from src.models.season_calendar import SeasonCalendar
    from src.services import gameweek as legacy_service
    from src.services.football_provider import season_for
    from src.services.odds_provider import Slate, SlateFixture
    from src.services.two_game_fixture_state import fixture_state_key

    label = date(2310, 1, 1)
    label += timedelta(days=(5 - label.weekday()) % 7)
    source.clock.now = london_utc(label - timedelta(days=1), 9)
    source.source = "oddsapi"
    enabled = await source.league(first=label)
    event = f"calendar-lock-{uuid.uuid4().hex[:12]}"
    observed = SlateFixture(
        provider_event_id=event,
        home="Fresh home",
        away="Fresh away",
        kickoff_utc=london_utc(label, 15),
        competition="Premier League",
        competition_id="england-premier-league",
    )
    monkeypatch.setattr(legacy_service, "_utc_now", source.clock)

    async def fresh(*args, **kwargs):
        return Slate(starts_on=label, fixtures=[observed])

    monkeypatch.setattr(source.client, "fetch_slate", fresh)
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, enabled)
        legacy = League(
            slug=f"calendar-lock-{uuid.uuid4().hex}",
            name="Calendar lock",
            created_by=owner.created_by,
        )
        fixture = Fixture(
            provider_event_id=event,
            home="Prior home",
            away=observed.away,
            kickoff_utc=london_utc(label + timedelta(days=7), 15),
            competition=observed.competition,
            competition_id=observed.competition_id,
        )
        db.add_all(
            [
                legacy,
                fixture,
                SeasonCalendar(
                    season=season_for(label),
                    week_one_anchor=label + timedelta(days=7),
                    extra_weeks=[],
                ),
            ]
        )
        await db.flush()
        legacy_id, fixture_id = legacy.id, fixture.id
        source.leagues.append(legacy_id)

    pid_ready = asyncio.Event()
    pid = None

    async def refresh():
        nonlocal pid
        async with source.sessions() as db, db.begin():
            pid = await db.scalar(text("SELECT pg_backend_pid()"))
            pid_ready.set()
            league = await db.get(League, legacy_id)
            parent = await legacy_service.refresh_slate(db, source.client, league, label)
            assert parent is not None and parent.starts_on == label

    task = None
    try:
        async with source.sessions() as held, held.begin():
            await held.scalar(
                select(SeasonCalendar)
                .where(SeasonCalendar.season == season_for(label))
                .with_for_update()
            )
            task = asyncio.create_task(refresh())
            await asyncio.wait_for(pid_ready.wait(), timeout=3)
            async with source.sessions() as monitor:
                async with asyncio.timeout(3):
                    while not await monitor.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
                    ):
                        await asyncio.sleep(0.01)
            # A real calendar wait must not also retain Fixture UPDATE: another
            # metadata writer can complete, preventing the inverse lock cycle.
            async with source.sessions() as probe, probe.begin():
                row = await probe.scalar(
                    select(Fixture).where(Fixture.id == fixture_id).with_for_update(nowait=True)
                )
                row.home = "Concurrent census home"
        await asyncio.wait_for(task, timeout=3)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with source.sessions() as db:
        row = await db.get(Fixture, fixture_id)
        state = await db.get(ProviderSnapshot, fixture_state_key("oddsapi", event))
        calendar = await db.get(SeasonCalendar, season_for(label))
        assert row.home == observed.home and row.kickoff_utc == observed.kickoff_utc
        assert state.payload["status"] == observed.status
        assert calendar.week_one_anchor == label


@pytest.mark.parametrize("writer", ["legacy", "census"])
@pytest.mark.asyncio
async def test_legacy_and_census_lock_shared_metadata_in_the_same_order(source, writer):
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from src.services.gameweek import sync_slate
    from src.services.odds_provider import Slate, SlateFixture
    from src.services.two_game_fixture_state import record_fixture_observations

    label = date(2320 if writer == "legacy" else 2321, 1, 1)
    label += timedelta(days=(5 - label.weekday()) % 7)
    enabled = await source.league(first=label)
    prefix = f"ordered-{uuid.uuid4().hex[:12]}"
    fixtures = [
        SlateFixture(
            provider_event_id=f"{prefix}-{suffix}",
            home=f"Home {suffix}",
            away=f"Away {suffix}",
            kickoff_utc=london_utc(label, 15),
            competition="Premier League",
            competition_id="england-premier-league",
        )
        for suffix in ("a", "z")
    ]
    async with source.sessions() as db, db.begin():
        owner = await db.get(League, enabled)
        legacy = League(
            slug=f"ordered-{uuid.uuid4().hex}", name="Ordered writes", created_by=owner.created_by
        )
        db.add(legacy)
        await db.flush()
        legacy_id = legacy.id
        source.leagues.append(legacy_id)
        parent = Gameweek(
            league_id=legacy_id,
            starts_on=label,
            locks_at_utc=london_utc(label, 14, 30),
            status=GameweekStatus.open,
        )
        rows = [
            Fixture(
                provider_event_id=fixture.provider_event_id,
                home="Prior " + fixture.home,
                away=fixture.away,
                kickoff_utc=fixture.kickoff_utc,
                competition=fixture.competition,
                competition_id=fixture.competition_id,
            )
            for fixture in fixtures
        ]
        # Reverse the PK ordering and provider DTO ordering relative to event IDs.
        # Both paths must still take a before z for genuinely changed metadata.
        for row in rows:
            row.id = uuid.uuid4()
        rows.sort(key=lambda row: row.id.int, reverse=True)
        rows[0].provider_event_id, rows[1].provider_event_id = (
            fixtures[0].provider_event_id,
            fixtures[1].provider_event_id,
        )
        db.add_all([parent, *rows])
        await db.flush()
        first_id, last_id = rows[0].id, rows[1].id
    pid_ready = asyncio.Event()
    pid = None

    async def write():
        nonlocal pid
        async with source.sessions() as db, db.begin():
            pid = await db.scalar(text("SELECT pg_backend_pid()"))
            pid_ready.set()
            if writer == "legacy":
                league = await db.get(League, legacy_id)
                await sync_slate(
                    db, league, Slate(starts_on=label, fixtures=list(reversed(fixtures)))
                )
            else:
                await record_fixture_observations(
                    db,
                    source.source,
                    list(reversed(fixtures)),
                    observed_at=source.clock.now,
                    expires_at=source.clock.now + timedelta(hours=6),
                )

    task = None
    try:
        async with source.sessions() as held, held.begin():
            await held.scalar(select(Fixture).where(Fixture.id == last_id).with_for_update())
            task = asyncio.create_task(write())
            await asyncio.wait_for(pid_ready.wait(), timeout=3)
            async with source.sessions() as monitor:
                async with asyncio.timeout(3):
                    while not await monitor.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
                    ):
                        await asyncio.sleep(0.01)
            async with source.sessions() as probe:
                with pytest.raises(DBAPIError) as locked:
                    await probe.scalar(
                        select(Fixture).where(Fixture.id == first_id).with_for_update(nowait=True)
                    )
                assert locked.value.orig.sqlstate == "55P03"
        await asyncio.wait_for(task, timeout=3)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
