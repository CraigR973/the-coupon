"""Run a single scheduled job once and exit.

This is the entry point for an *external* scheduler (Railway Cron, GitHub
Actions, cron-job.org, or a manual ``railway run``) when the in-process
APScheduler cannot be relied on — e.g. the web container is not continuously
running, so wall-clock and interval jobs do not fire reliably (see
``docs/runbooks/scheduled-jobs-cron.md``).

Each job name maps to the same coroutine the in-process scheduler runs, so
behaviour is identical. A job returns a success flag after logging its own
details; one-off runs exit non-zero when the selected job reports failure.

Usage:
    python -m src.run_scheduled <job>

Jobs:
    backup         database backup, to this container's /tmp
    offsite-backup the weekly off-site backup, now (Batch 95; needs BACKUP_STORAGE=s3)
    discover-full-catalogue  weekly walk of every competition this deployment plays
    refresh-slate  refresh the upcoming Saturday's slate + fixtures from the odds provider
    warm-odds      learn which of the imminent card's fixtures the bookmaker prices
    remind         push a pick reminder to members who haven't picked
    open           open any scheduled gameweek past its announced pick-open time
    lock           lock any gameweek past its 14:30 deadline
    settle         settle locked gameweeks against provider results + recompute standings
    sync-football  top up league tables, results and form for the competitions on the card
    live-scores    refresh the running score for any round being played right now
    football-backfill  pull a whole season of results and tables in one pass (one-off)
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable

from src.scheduler import (
    run_backfill_football_season,
    run_discover_fixtures,
    run_discover_full_catalogue,
    run_live_scores,
    run_lock_gameweeks,
    run_offsite_backup,
    run_open_gameweeks,
    run_pick_reminders,
    run_refresh_slate,
    run_scheduled_backup,
    run_settle_gameweeks,
    run_sync_football_data,
    run_warm_odds_marker,
)

JOBS: dict[str, Callable[[], Awaitable[bool]]] = {
    "backup": run_scheduled_backup,
    "offsite-backup": run_offsite_backup,
    "discover-fixtures": run_discover_fixtures,
    "discover-full-catalogue": run_discover_full_catalogue,
    "refresh-slate": run_refresh_slate,
    "warm-odds": run_warm_odds_marker,
    "remind": run_pick_reminders,
    "open": run_open_gameweeks,
    "lock": run_lock_gameweeks,
    "settle": run_settle_gameweeks,
    "sync-football": run_sync_football_data,
    "live-scores": run_live_scores,
    "football-backfill": run_backfill_football_season,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single scheduled job once and exit.")
    parser.add_argument("job", choices=sorted(JOBS), help="The scheduled job to run once")
    return parser


async def _run(job: str) -> bool:
    return await JOBS[job]()


def main() -> None:
    args = _build_parser().parse_args()
    ok = asyncio.run(_run(args.job))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
