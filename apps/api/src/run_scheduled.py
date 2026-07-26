"""Run a single scheduled job once and exit.

This is the entry point for an *external* scheduler (Railway Cron, GitHub
Actions, cron-job.org, or a manual ``railway run``) when the in-process
APScheduler cannot be relied on — e.g. the web container is not continuously
running, so wall-clock and interval jobs do not fire reliably (see
``docs/runbooks/scheduled-jobs-cron.md``).

Each job name maps to the same coroutine the in-process scheduler runs, so
behaviour is identical; the job functions log and swallow their own errors, so
this exits 0 even on an internal failure (failures are visible in the logs).

Usage:
    python -m src.run_scheduled <job>

Jobs:
    backup         database backup
    refresh-slate  refresh the upcoming Saturday's slate + fixtures from Betfair
    remind         push a pick reminder to members who haven't picked
    lock           lock any gameweek past its 14:30 deadline
    settle         settle locked gameweeks against Betfair results + recompute standings
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable

from src.scheduler import (
    run_lock_gameweeks,
    run_pick_reminders,
    run_refresh_slate,
    run_scheduled_backup,
    run_settle_gameweeks,
)

JOBS: dict[str, Callable[[], Awaitable[None]]] = {
    "backup": run_scheduled_backup,
    "refresh-slate": run_refresh_slate,
    "remind": run_pick_reminders,
    "lock": run_lock_gameweeks,
    "settle": run_settle_gameweeks,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single scheduled job once and exit.")
    parser.add_argument("job", choices=sorted(JOBS), help="The scheduled job to run once")
    return parser


async def _run(job: str) -> None:
    await JOBS[job]()


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run(args.job))


if __name__ == "__main__":
    main()
