"""Background scheduler — APScheduler harness.

The skeleton ships two domain-agnostic jobs:
  - daily_backup: database backup at 03:00 UTC
  - connection_warmup: a cheap ``SELECT 1`` every 10 min so the first request
    after a quiet spell usually lands on a warm pooled connection.

Add your app's jobs to ``create_scheduler`` following the commented example at
the bottom. Each job function should log and swallow its own errors so a single
failing run never takes the scheduler down; ``run_scheduled.py`` exposes the
same coroutines to an external cron (Railway Cron / GitHub Actions) for when the
in-process scheduler can't be relied on (see docs/runbooks/scheduled-jobs-cron.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped,unused-ignore]
    AsyncIOScheduler,
)
from sqlalchemy import text

from src.config import settings
from src.database import AsyncSessionLocal
from src.models.notification import ActionType, ActorType, AuditLog
from src.services.backup import create_backup

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def run_scheduled_backup() -> None:
    """Daily backup job — runs at 03:00 UTC."""
    try:
        info = await create_backup(settings.backup_dir, settings.database_url)
        log.info("scheduled backup complete", filename=info.filename, size_bytes=info.size_bytes)
    except Exception as exc:
        reason = str(exc)
        log.exception("scheduled backup failed")
        async with AsyncSessionLocal() as session:
            session.add(
                AuditLog(
                    actor_id=None,
                    actor_type=ActorType.system,
                    action_type=ActionType.backup_failed,
                    target_table="",
                    target_id=None,
                    changes={"error": reason},
                )
            )
            await session.commit()


async def run_connection_warmup() -> None:
    """Keep a pooled DB connection hot so the first open rarely pays a cold connect.

    ``pool_recycle=1800`` recycles a connection idle for 30 min, so the first
    request after a quiet spell re-establishes a pooler connection (TLS + auth)
    before it can even start querying. A cheap ``SELECT 1`` every few minutes
    keeps at least one pooled connection alive.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        log.exception("connection warmup failed")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_connection_warmup,
        trigger="interval",
        minutes=10,
        id="connection_warmup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.now(UTC) + timedelta(seconds=30),
    )
    scheduler.add_job(
        run_scheduled_backup,
        trigger="cron",
        hour=3,
        minute=0,
        id="daily_backup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # --- Add your app's jobs below, following this pattern ---
    # scheduler.add_job(
    #     run_my_daily_job,
    #     trigger="cron",
    #     hour=7,
    #     minute=0,
    #     timezone="Europe/London",   # wall-clock jobs; APScheduler handles DST
    #     id="my_daily_job",
    #     replace_existing=True,
    #     coalesce=True,
    #     max_instances=1,
    # )
    return scheduler
