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

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped,unused-ignore]
    AsyncIOScheduler,
)
from sqlalchemy import text

from src.config import settings
from src.database import AsyncSessionLocal
from src.models.notification import ActionType, ActorType, AuditLog
from src.services.backup import create_backup
from src.services.betfair_session import betfair_session
from src.services.gameweek import (
    current_open_gameweek,
    lock_due_gameweeks,
    refresh_slate,
    settleable_gameweeks,
    upcoming_saturday,
)
from src.services.notification_triggers import send_pick_reminders
from src.services.scoring import (
    participating_league_ids,
    settle_gameweek_via_adapter,
    standings,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_UK_TZ = ZoneInfo("Europe/London")


def _utc_now() -> datetime:
    """Naive-UTC now — matches the ``*_utc`` storage convention used across the schema."""
    return datetime.now(UTC).replace(tzinfo=None)


def _uk_today() -> date:
    """Today's date in UK local time — the anchor for 'this Saturday's' slate."""
    return datetime.now(_UK_TZ).date()


async def run_scheduled_backup() -> bool:
    """Daily backup job — runs at 03:00 UTC."""
    try:
        info = await create_backup(settings.backup_dir, settings.database_url)
        log.info("scheduled backup complete", filename=info.filename, size_bytes=info.size_bytes)
        return True
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
        return False


async def run_connection_warmup() -> bool:
    """Keep a pooled DB connection hot so the first open rarely pays a cold connect.

    ``pool_recycle=1800`` recycles a connection idle for 30 min, so the first
    request after a quiet spell re-establishes a pooler connection (TLS + auth)
    before it can even start querying. A cheap ``SELECT 1`` every few minutes
    keeps at least one pooled connection alive.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        log.exception("connection warmup failed")
        return False


# ── Coupon domain jobs (Batch 4) ────────────────────────────────────────────────
# Each owns its Betfair session (via the shared ``betfair_session``) and its DB
# transaction (the domain functions flush; the job commits), and logs+swallows its own
# errors so one bad run never takes the scheduler down.


async def run_refresh_slate() -> bool:
    """Refresh the upcoming Saturday's slate + fixtures from Betfair.

    Runs a few times pre-lock so the card firms up (names, kick-offs). Odds themselves are
    snapshotted live onto each pick, so there is no separate odds cache to refresh here.
    """
    try:
        adapter = await betfair_session.acquire()
        saturday = upcoming_saturday(_uk_today())
        async with AsyncSessionLocal() as session:
            gameweek = await refresh_slate(session, adapter, saturday)
            gameweek_id = str(gameweek.id) if gameweek is not None else None
            await session.commit()
        if gameweek_id is not None:
            log.info("slate refreshed", saturday=str(saturday), gameweek_id=gameweek_id)
        else:
            log.info("slate refresh: no target fixtures", saturday=str(saturday))
        return True
    except Exception:
        log.exception("slate refresh failed")
        return False


async def run_lock_gameweeks() -> bool:
    """Lock any open gameweek whose 14:30 deadline has passed (fires 14:30 UK, Saturdays)."""
    try:
        async with AsyncSessionLocal() as session:
            locked = await lock_due_gameweeks(session, _utc_now())
            gameweek_ids = [str(g.id) for g in locked]
            await session.commit()
        if gameweek_ids:
            log.info("gameweeks locked", count=len(gameweek_ids), gameweek_ids=gameweek_ids)
        return True
    except Exception:
        log.exception("gameweek lock failed")
        return False


async def run_settle_gameweeks() -> bool:
    """Settle locked gameweeks against Betfair results and recompute standings.

    Idempotent: :func:`~src.services.scoring.settle_gameweek_via_adapter` resolves only picks
    whose market has closed, so the Saturday-evening re-runs pick up late settlements and
    flip a gameweek to ``settled`` once nothing is pending. Standings are then recomputed per
    participating league and logged (they are read on demand — this surfaces the outcome).
    """
    try:
        adapter = await betfair_session.acquire()
        async with AsyncSessionLocal() as session:
            gameweeks = await settleable_gameweeks(session, _utc_now())
            resolved_by_gameweek: dict[str, int] = {}
            for gameweek in gameweeks:
                resolved = await settle_gameweek_via_adapter(session, adapter, gameweek)
                resolved_by_gameweek[str(gameweek.id)] = resolved
            await session.commit()

            for gameweek in gameweeks:
                for league_id in await participating_league_ids(session, gameweek):
                    table = await standings(session, league_id)
                    leader = table[0] if table else None
                    log.info(
                        "standings recomputed",
                        gameweek_id=str(gameweek.id),
                        league_id=str(league_id),
                        leader_present=leader is not None,
                        leader_points=leader.total_points if leader else None,
                    )
        if resolved_by_gameweek:
            log.info("gameweeks settled", resolved=resolved_by_gameweek)
        return True
    except Exception:
        log.exception("settle failed")
        return False


async def run_pick_reminders() -> bool:
    """Nudge members who still owe a pick for the current open gameweek (fires pre-lock)."""
    try:
        async with AsyncSessionLocal() as session:
            gameweek = await current_open_gameweek(session, _utc_now())
            if gameweek is None:
                log.info("pick reminder: no open gameweek")
                return True
            gameweek_id = str(gameweek.id)
            reminded = await send_pick_reminders(session, gameweek)
            await session.commit()
        log.info("pick reminders sent", gameweek_id=gameweek_id, count=reminded)
        return True
    except Exception:
        log.exception("pick reminder failed")
        return False


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
    # --- Coupon domain jobs (Batch 4) ---
    # Wall-clock schedules in Europe/London — APScheduler handles the BST/GMT shift, so the
    # 14:30 lock stays aligned with ``gameweek.compute_locks_at`` across the season. The
    # per-gameweek ``locks_at_utc`` predicate is the real source of truth, so an off-by-a-run
    # firing still resolves correctly; the cron just decides when to look.
    scheduler.add_job(
        run_refresh_slate,
        trigger="cron",
        day_of_week="mon-sat",
        hour="9,12,14",  # a few times pre-lock on match day; keeps the slate fresh midweek
        minute=0,
        timezone="Europe/London",
        id="refresh_slate",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_pick_reminders,
        trigger="cron",
        day_of_week="sat",
        hour=11,
        minute=0,
        timezone="Europe/London",
        id="pick_reminders",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_lock_gameweeks,
        trigger="cron",
        day_of_week="sat",
        hour=14,
        minute=30,  # picks lock 14:30 UK
        timezone="Europe/London",
        id="lock_gameweeks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_settle_gameweeks,
        trigger="cron",
        day_of_week="sat,sun,mon",
        hour="18,20,22",  # Saturday evening plus Sunday/Monday retries for late markets
        minute=0,
        timezone="Europe/London",
        id="settle_gameweeks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
