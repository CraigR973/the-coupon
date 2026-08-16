"""Unit tests for the scheduler harness and its two baseline jobs."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings
from src.models.notification import ActionType, ActorType, AuditLog
from src.scheduler import (
    create_scheduler,
    run_discover_fixtures,
    run_lock_gameweeks,
    run_pick_reminders,
    run_refresh_slate,
    run_scheduled_backup,
    run_settle_gameweeks,
    run_sync_football_data,
)


class _Ctx:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *a: object) -> None:
        return None


# ---------------------------------------------------------------------------
# run_scheduled_backup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_scheduled_backup_failure_writes_audit() -> None:
    """When create_backup raises, an audit row is written."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    with (
        patch(
            "src.scheduler.create_backup",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pg_dump not found"),
        ),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
    ):
        ok = await run_scheduled_backup()

    assert ok is False
    added = [call.args[0] for call in session.add.call_args_list]
    audit_rows = [a for a in added if isinstance(a, AuditLog)]
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row.action_type == ActionType.backup_failed
    assert row.actor_type == ActorType.system
    assert "pg_dump not found" in row.changes["error"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_scheduled_backup_success_does_not_raise() -> None:
    """On success, no exception is raised."""
    info = MagicMock()
    info.filename = "backup-20260721.sql.gz"
    info.size_bytes = 1024

    with patch("src.scheduler.create_backup", new_callable=AsyncMock, return_value=info):
        ok = await run_scheduled_backup()
    # No exception raised = pass
    assert ok is True


# ---------------------------------------------------------------------------
# create_scheduler
# ---------------------------------------------------------------------------


def test_create_scheduler_registers_baseline_jobs() -> None:
    scheduler = create_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert job_ids == {
            "connection_warmup",
            "daily_backup",
            "discover_fixtures",
            "refresh_slate",
            "pick_reminders",
            "open_gameweeks",
            "lock_gameweeks",
            "settle_gameweeks",
            "sync_football_data",
        }

        backup = scheduler.get_job("daily_backup")
        assert backup is not None
        assert str(backup.trigger) == "cron[hour='3', minute='0']"
        assert backup.coalesce is True
        assert backup.max_instances == 1

        warmup = scheduler.get_job("connection_warmup")
        assert warmup is not None
        assert str(warmup.trigger) == "interval[0:10:00]"
        assert warmup.next_run_time is not None
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_create_scheduler_domain_jobs_fire_on_uk_wall_clock() -> None:
    """The Coupon jobs run on Europe/London wall-clock so 14:30 lock survives BST/GMT."""
    scheduler = create_scheduler()
    try:
        # None of these filter on a weekday. They did when every league played the
        # same Saturday; since Batch 14 a league may play any day, and a Saturday-only
        # lock job would never lock a Friday league's round.
        expected = {
            # Discovery is daily and early — the pre-fetch half of the Batch 11 split.
            "discover_fixtures": "cron[hour='6', minute='0']",
            "refresh_slate": "cron[hour='9,13', minute='0']",
            "pick_reminders": "cron[hour='11', minute='0']",
            # Hourly, a minute clear of the lock sweep so the two never interleave.
            "open_gameweeks": "cron[minute='1']",
            "lock_gameweeks": "cron[minute='0']",
            "settle_gameweeks": "cron[hour='18,20,22', minute='0']",
        }
        for job_id, trigger_repr in expected.items():
            job = scheduler.get_job(job_id)
            assert job is not None
            assert str(job.trigger) == trigger_repr
            assert str(job.trigger.timezone) == "Europe/London"
            assert job.coalesce is True
            assert job.max_instances == 1
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Coupon domain jobs — wiring (own the tx + odds session, swallow errors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_discover_fixtures_walks_the_horizon_and_commits() -> None:
    """The daily job spans the configured horizon, not just this Saturday."""
    session = AsyncMock()
    gameweek = MagicMock()
    gameweek.id = uuid.uuid4()
    with (
        patch("src.scheduler.odds_session.acquire", new=AsyncMock(return_value=MagicMock())),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.active_leagues", new=AsyncMock(return_value=[MagicMock()])),
        patch(
            "src.scheduler.discover_fixtures", new=AsyncMock(return_value=[gameweek])
        ) as discover,
    ):
        assert await run_discover_fixtures() is True

    session.commit.assert_awaited_once()
    # discover_fixtures(session, provider, leagues, today, horizon)
    assert discover.await_args.args[4] == settings.slate_horizon_weeks


@pytest.mark.asyncio
async def test_run_discover_fixtures_swallows_provider_failure() -> None:
    """One bad provider run must never take the scheduler down."""
    with patch(
        "src.scheduler.odds_session.acquire", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await run_discover_fixtures() is False


@pytest.mark.asyncio
async def test_run_refresh_slate_covers_only_the_imminent_round() -> None:
    """The late match-day pass must not re-walk the whole horizon."""
    session = AsyncMock()
    gameweek = MagicMock()
    gameweek.id = uuid.uuid4()
    with (
        patch("src.scheduler.odds_session.acquire", new=AsyncMock(return_value=MagicMock())),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.active_leagues", new=AsyncMock(return_value=[MagicMock()])),
        patch(
            "src.scheduler.discover_fixtures", new=AsyncMock(return_value=[gameweek])
        ) as discover,
    ):
        await run_refresh_slate()
    assert discover.await_args.args[4] == 1, "horizon of one — the far weeks are not firm yet"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_refresh_slate_empty_slate_still_commits() -> None:
    """No target fixtures → no round created, but the (no-op) tx still closes cleanly."""
    session = AsyncMock()
    with (
        patch("src.scheduler.odds_session.acquire", new=AsyncMock(return_value=MagicMock())),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.active_leagues", new=AsyncMock(return_value=[])),
        patch("src.scheduler.discover_fixtures", new=AsyncMock(return_value=[])),
    ):
        await run_refresh_slate()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_refresh_slate_swallows_errors() -> None:
    with patch(
        "src.scheduler.odds_session.acquire",
        new=AsyncMock(side_effect=RuntimeError("odds provider down")),
    ):
        ok = await run_refresh_slate()  # a failed run must not propagate
    assert ok is False


@pytest.mark.asyncio
async def test_run_sync_football_data_passes_the_minute_pacing_setting() -> None:
    session = AsyncMock()
    with (
        patch("src.scheduler.football_session.acquire", new=AsyncMock(return_value=MagicMock())),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler._uk_today", return_value=MagicMock()),
        patch("src.scheduler.sync_football_data", new=AsyncMock(return_value=[])) as sync,
    ):
        ok = await run_sync_football_data()

    assert ok is True
    assert sync.await_args.kwargs["competition_spacing_seconds"] == (
        settings.football_competition_spacing_seconds
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_lock_gameweeks_commits() -> None:
    session = AsyncMock()
    locked = MagicMock()
    locked.id = uuid.uuid4()
    with (
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.lock_due_gameweeks", new=AsyncMock(return_value=[locked])) as lock,
    ):
        ok = await run_lock_gameweeks()
    assert ok is True
    lock.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_lock_gameweeks_swallows_errors() -> None:
    with patch("src.scheduler.AsyncSessionLocal", side_effect=RuntimeError("db down")):
        ok = await run_lock_gameweeks()
    assert ok is False


@pytest.mark.asyncio
async def test_run_settle_gameweeks_settles_then_recomputes_standings() -> None:
    session = AsyncMock()
    gameweek = MagicMock()
    gameweek.id = uuid.uuid4()
    leader = MagicMock()
    leader.display_name = "alice"
    leader.total_points = 24
    with (
        patch("src.scheduler.odds_session.acquire", new=AsyncMock(return_value=MagicMock())),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.settleable_gameweeks", new=AsyncMock(return_value=[gameweek])),
        patch(
            "src.scheduler.settle_gameweek_via_provider", new=AsyncMock(return_value=3)
        ) as settle,
        patch("src.scheduler.standings", new=AsyncMock(return_value=[leader])) as recompute,
    ):
        ok = await run_settle_gameweeks()
    assert ok is True
    settle.assert_awaited_once()
    recompute.assert_awaited_once()  # standings recomputed per participating league
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_settle_gameweeks_swallows_errors() -> None:
    with patch(
        "src.scheduler.odds_session.acquire",
        new=AsyncMock(side_effect=RuntimeError("odds provider down")),
    ):
        ok = await run_settle_gameweeks()
    assert ok is False


@pytest.mark.asyncio
async def test_run_pick_reminders_sends_and_commits() -> None:
    session = AsyncMock()
    gameweek = MagicMock()
    gameweek.id = uuid.uuid4()
    with (
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.current_open_gameweeks", new=AsyncMock(return_value=[gameweek])),
        patch("src.scheduler.send_pick_reminders", new=AsyncMock(return_value=2)) as remind,
    ):
        await run_pick_reminders()
    remind.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_pick_reminders_no_open_gameweek_is_noop() -> None:
    """With no open gameweek to remind for, the job returns without sending or committing."""
    session = AsyncMock()
    with (
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch("src.scheduler.current_open_gameweeks", new=AsyncMock(return_value=[])),
        patch("src.scheduler.send_pick_reminders", new=AsyncMock()) as remind,
    ):
        await run_pick_reminders()
    remind.assert_not_awaited()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Lifespan integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_lifespan_starts_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifespan context starts the scheduler when enabled."""
    import asyncio

    from src.config import settings
    from src.main import app, lifespan

    monkeypatch.setattr(settings, "scheduler_enabled", True)

    async with lifespan(app):
        scheduler = app.state.scheduler
        assert scheduler.running is True
        assert scheduler.get_job("daily_backup") is not None
        assert scheduler.get_job("connection_warmup") is not None

    await asyncio.sleep(0)
    assert scheduler.running is False


@pytest.mark.asyncio
async def test_scheduler_lifespan_disabled_skips_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """When scheduler_enabled is False the scheduler is created but never started."""
    from src.config import settings
    from src.main import app, lifespan

    monkeypatch.setattr(settings, "scheduler_enabled", False)

    async with lifespan(app):
        assert app.state.scheduler.running is False
