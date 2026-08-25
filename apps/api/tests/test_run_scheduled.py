"""Tests for the single-job runner used by external cron."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from src import run_scheduled, scheduler


def test_jobs_cover_expected_names() -> None:
    assert set(run_scheduled.JOBS) == {
        "backup",
        "discover-fixtures",
        "refresh-slate",
        "remind",
        "open",
        "lock",
        "settle",
        "sync-football",
        "live-scores",
        "football-backfill",
    }


def test_jobs_map_to_the_same_scheduler_coroutines() -> None:
    assert run_scheduled.JOBS["backup"] is scheduler.run_scheduled_backup
    assert run_scheduled.JOBS["discover-fixtures"] is scheduler.run_discover_fixtures
    assert run_scheduled.JOBS["refresh-slate"] is scheduler.run_refresh_slate
    assert run_scheduled.JOBS["remind"] is scheduler.run_pick_reminders
    assert run_scheduled.JOBS["open"] is scheduler.run_open_gameweeks
    assert run_scheduled.JOBS["lock"] is scheduler.run_lock_gameweeks
    assert run_scheduled.JOBS["live-scores"] is scheduler.run_live_scores
    assert run_scheduled.JOBS["settle"] is scheduler.run_settle_gameweeks
    assert run_scheduled.JOBS["sync-football"] is scheduler.run_sync_football_data
    assert run_scheduled.JOBS["football-backfill"] is scheduler.run_backfill_football_season


@pytest.mark.asyncio
async def test_run_awaits_selected_job() -> None:
    fake = AsyncMock(return_value=True)
    with patch.dict(run_scheduled.JOBS, {"backup": fake}):
        ok = await run_scheduled._run("backup")
    fake.assert_awaited_once()
    assert ok is True


def test_main_runs_named_job(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock(return_value=True)
    monkeypatch.setattr(sys, "argv", ["run_scheduled", "backup"])
    with patch.dict(run_scheduled.JOBS, {"backup": fake}):
        run_scheduled.main()
    fake.assert_awaited_once()


def test_main_exits_nonzero_when_job_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AsyncMock(return_value=False)
    monkeypatch.setattr(sys, "argv", ["run_scheduled", "backup"])
    with patch.dict(run_scheduled.JOBS, {"backup": fake}), pytest.raises(SystemExit) as exc:
        run_scheduled.main()
    assert exc.value.code == 1


def test_main_rejects_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_scheduled", "not-a-job"])
    with pytest.raises(SystemExit):
        run_scheduled.main()


def test_the_backup_is_still_reachable_on_demand_after_batch_75() -> None:
    """Batch 75 removed a *schedule*, not a capability, and this is the half that proves it.

    Paired deliberately with `test_scheduler.py`'s assertion that `daily_backup` is absent
    from the registered jobs. Either test alone is satisfiable by the wrong change: delete
    the coroutine and the scheduler assertion still passes; restore the nightly `add_job`
    and this one still passes. Together they pin the batch's actual claim — the 03:00 UTC
    run is gone and `python -m src.run_scheduled backup` still works, which is the tool
    worth having before a risky migration and costs nothing on the days nobody runs it.
    """
    from src.scheduler import create_scheduler

    scheduler_instance = create_scheduler()
    try:
        assert scheduler_instance.get_job("daily_backup") is None
    finally:
        if scheduler_instance.running:
            scheduler_instance.shutdown(wait=False)

    assert run_scheduled.JOBS["backup"] is scheduler.run_scheduled_backup
    assert callable(run_scheduled.JOBS["backup"])
