"""Batch 237: game reads and saves never queue behind the two-game background jobs.

On 23-24 Nov 2026 discovery's setup held 2-1 Hibs' league lock (advisory key 220) for
about 80 s a pass, back to back, and every game read and save waited on it. These tests
pause or contend each background step and require the member's requests to finish.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select, text, update

from src.config import settings
from src.models.two_game import ProviderWork, TwoGame, TwoGameEvent, TwoGameFixture
from src.services.two_game_discovery import DiscoveryWorker
from src.services.two_game_events import deliver_events, lifecycle_events
from src.services.two_game_settlement import SettlementWorker
from tests import test_two_game_fantasy as entry_tests
from tests import two_game_test_store as result_store_fixtures
from tests.test_two_game_discovery import CensusSource

baseline_db_engine = result_store_fixtures.baseline_db_engine
result_store = result_store_fixtures.result_store
db_engine = result_store_fixtures.db_engine

fantasy = entry_tests.fantasy

LEAGUE_LOCK_HELD = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
    "AND ((classid::int8 << 32) | objid::int8) = hashtextextended(:key, 220)"
)


async def forbidden():
    raise AssertionError("no provider acquisition belongs in these passes")


def discovery(f, **options) -> DiscoveryWorker:
    # A source of its own keeps this test's work rows out of every other queue.
    return DiscoveryWorker(
        f.sessions,
        forbidden,
        source=f"locks-{uuid.uuid4().hex[:12]}",
        bookmaker="Bet365",
        clock=f.source.clock,
        include_legacy=False,
        **options,
    )


@pytest_asyncio.fixture
async def census(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    item = CensusSource(db_engine)
    try:
        yield item
    finally:
        await item.close()


@pytest.mark.asyncio
async def test_game_reads_and_saves_finish_while_discovery_setup_is_paused(fantasy, monkeypatch):
    f = fantasy
    worker = discovery(f)
    paused, release = asyncio.Event(), asyncio.Event()
    original = worker._enqueue_prices

    async def enqueue_then_pause(db, now):
        needed = await original(db, now)
        paused.set()
        await release.wait()
        return needed

    monkeypatch.setattr(worker, "_enqueue_prices", enqueue_then_pause)
    setup = asyncio.create_task(worker.prepare())
    try:
        await asyncio.wait_for(paused.wait(), timeout=10)
        async with f.sessions() as monitor:
            held = await monitor.scalar(LEAGUE_LOCK_HELD, {"key": str(f.league.id)})
        assert held == 0
        group_path = f.path.replace("/fantasy", "/group")
        for path in (f.path, f.path + "/slots/1", group_path, group_path + "/pick"):
            read = await asyncio.wait_for(f.request("GET", path=path), timeout=10)
            assert read.status_code == 200, (path, read.text)
        group_save = await asyncio.wait_for(
            f.request(
                "PUT",
                path=group_path + "/pick",
                body={
                    "fixture_id": str(f.fixtures[0].id),
                    "market": "MATCH_ODDS",
                    "outcome": "HOME",
                    "expected_revision": 0,
                    "operation_id": str(uuid.uuid4()),
                },
            ),
            timeout=10,
        )
        assert group_save.status_code == 200, group_save.text
        fantasy_save = await asyncio.wait_for(f.save(1, f.body(1)), timeout=10)
        assert fantasy_save.status_code == 200, fantasy_save.text
        assert not setup.done()
    finally:
        release.set()
        await asyncio.wait_for(setup, timeout=10)


@pytest.mark.asyncio
async def test_setup_and_empty_settlement_passes_never_wait_for_a_held_league_lock(fantasy):
    f = fantasy
    worker = discovery(f)
    settlement = SettlementWorker(f.sessions, forbidden, source="oddsapi", clock=f.source.clock)
    # Creating next week's parent is the one step that takes the lock, so it runs first;
    # recording the open games' lifecycle facts leaves the contended passes none to add.
    await worker.prepare()
    await lifecycle_events(f.sessions, f.source.clock.now)
    await deliver_events(f.sessions, clock=f.source.clock)
    async with f.sessions() as held, held.begin():
        await held.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"),
            {"key": str(f.league.id)},
        )
        await asyncio.wait_for(worker.prepare(), timeout=10)
        stats = await asyncio.wait_for(settlement.run(), timeout=10)
        await asyncio.wait_for(lifecycle_events(f.sessions, f.source.clock.now), timeout=10)
        delivered = await asyncio.wait_for(deliver_events(f.sessions, clock=f.source.clock), 10)
    assert stats == dict(resolved=0, failures=0, chunks=0)
    assert delivered == 0


@pytest.mark.asyncio
async def test_a_due_lifecycle_fact_still_waits_for_the_league_lock(fantasy):
    f = fantasy
    async with f.sessions() as held, held.begin():
        await held.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"),
            {"key": str(f.league.id)},
        )
        # The games have opened and no fact is recorded yet: this pass has work to do.
        pending = asyncio.create_task(lifecycle_events(f.sessions, f.source.clock.now))
        await asyncio.sleep(0.5)
        assert not pending.done()
    await asyncio.wait_for(pending, timeout=10)
    async with f.sessions() as db:
        statuses = set(
            await db.scalars(select(TwoGame.status).where(TwoGame.league_id == f.league.id))
        )
        opened = await db.scalar(
            select(func.count())
            .select_from(TwoGameEvent)
            .where(TwoGameEvent.league_id == f.league.id, TwoGameEvent.kind == "game_opened")
        )
    assert statuses == {"open"}
    assert opened == 2


@pytest.mark.asyncio
async def test_setup_statements_do_not_grow_with_the_card(census, db_engine):
    source = census
    await source.league()
    for index in range(4):
        source.event(f"small-{index}")
    worker = source.worker()

    async def settle_queue():
        for _ in range(12):
            await worker.run()
            source.clock.now += timedelta(minutes=7)

    async def statements() -> int:
        seen: list[str] = []

        def count(_conn, _cursor, statement, *_args):
            seen.append(statement)

        event.listen(db_engine.sync_engine, "before_cursor_execute", count)
        try:
            await worker.prepare()
        finally:
            event.remove(db_engine.sync_engine, "before_cursor_execute", count)
        return len(seen)

    async def links() -> int:
        async with source.sessions() as db:
            return await db.scalar(select(func.count()).select_from(TwoGameFixture))

    await settle_queue()
    small, small_links = await statements(), await links()
    for index in range(40):
        source.event(f"large-{index}")
    async with source.sessions() as db, db.begin():
        await db.execute(
            update(ProviderWork)
            .where(
                ProviderWork.kind == "census",
                ProviderWork.payload["source"].astext == source.source,
            )
            .values(next_at=source.clock.now)
        )
    await settle_queue()
    large, large_links = await statements(), await links()
    assert large_links - small_links == 80  # 40 more fixtures, each in group and fantasy
    assert large == small
