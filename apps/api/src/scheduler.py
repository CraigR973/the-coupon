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
from src.services.football_data import backfill_season, season_or_default, sync_football_data
from src.services.football_session import football_session
from src.services.gameweek import (
    active_leagues,
    current_open_gameweeks,
    discover_fixtures,
    lock_due_gameweeks,
    settleable_gameweeks,
    window_for,
)
from src.services.notification_triggers import send_pick_reminders
from src.services.odds_session import odds_session
from src.services.scoring import (
    settle_gameweek_via_provider,
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
# Each draws the odds provider from the shared ``odds_session`` and owns its DB
# transaction (the domain functions flush; the job commits), and logs+swallows its own
# errors so one bad run never takes the scheduler down.


async def run_discover_fixtures() -> bool:
    """Walk the coming weeks' fixtures into the table, once a day.

    The pre-fetch half of Batch 11's split. Discovery is scheduled, cheap, and ahead
    of time — one request per UK competition per Saturday, so the whole horizon costs
    about sixty requests once daily. Pricing is deliberately *not* pre-fetched: a
    price only matters at the instant a member freezes it onto a pick, and sweeping
    the card for odds is what the provider's rate limit cannot afford.
    """
    try:
        provider = await odds_session.acquire()
        async with AsyncSessionLocal() as session:
            leagues = await active_leagues(session)
            gameweeks = await discover_fixtures(
                session, provider, leagues, _uk_today(), settings.slate_horizon_weeks
            )
            gameweek_ids = [str(g.id) for g in gameweeks]
            windows = len({window_for(league) for league in leagues})
            await session.commit()
        log.info(
            "fixtures discovered",
            leagues=len(leagues),
            distinct_windows=windows,
            gameweeks=len(gameweek_ids),
        )
        return True
    except Exception:
        log.exception("fixture discovery failed")
        return False


async def run_refresh_slate() -> bool:
    """Firm up the imminent card shortly before lock.

    Discovery already walked this round in days ago; this is the late pass that catches
    a postponement or a kick-off change. It covers only the *nearest* date of each
    league's window rather than the whole horizon, because the far weeks have not
    firmed up yet and re-fetching them would spend the provider budget on nothing.

    Odds themselves are snapshotted onto each pick at pick time and served through the
    provider's own TTL cache, so there is nothing to warm here.
    """
    try:
        provider = await odds_session.acquire()
        async with AsyncSessionLocal() as session:
            leagues = await active_leagues(session)
            # Horizon of 1: only the round about to be played.
            gameweeks = await discover_fixtures(session, provider, leagues, _uk_today(), 1)
            refreshed = len(gameweeks)
            await session.commit()
        if refreshed:
            log.info("slate refreshed", leagues=len(leagues), gameweeks=refreshed)
        else:
            log.info("slate refresh: no target fixtures", leagues=len(leagues))
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
    """Settle locked gameweeks against the provider's results and recompute standings.

    Idempotent: :func:`~src.services.scoring.settle_gameweek_via_provider` resolves only
    picks whose fixture has a final result, so the Saturday-evening re-runs pick up late
    results and flip a gameweek to ``settled`` once nothing is pending. That retry window
    matters more under odds-api.io than it did on the Exchange, because a result is derived
    from a published score rather than pushed by a settlement feed. Standings are then
    recomputed per participating league and logged (they are read on demand — this surfaces
    the outcome).
    """
    try:
        provider = await odds_session.acquire()
        async with AsyncSessionLocal() as session:
            gameweeks = await settleable_gameweeks(session, _utc_now())
            resolved_by_gameweek: dict[str, int] = {}
            for gameweek in gameweeks:
                resolved = await settle_gameweek_via_provider(session, provider, gameweek)
                resolved_by_gameweek[str(gameweek.id)] = resolved
            await session.commit()

            # A round belongs to one league since Batch 14, so its league is the
            # only table a settlement can move — no lookup of "who played this
            # round" is needed any more.
            for gameweek in gameweeks:
                table = await standings(session, gameweek.league_id)
                leader = table[0] if table else None
                log.info(
                    "standings recomputed",
                    gameweek_id=str(gameweek.id),
                    league_id=str(gameweek.league_id),
                    leader_present=leader is not None,
                    leader_points=leader.total_points if leader else None,
                )
        if resolved_by_gameweek:
            log.info("gameweeks settled", resolved=resolved_by_gameweek)
        return True
    except Exception:
        log.exception("settle failed")
        return False


async def run_sync_football_data() -> bool:
    """Top up league tables, results and form for the competitions on the card.

    On the same daily rhythm as fixture discovery and half an hour behind it, so the
    fixture pool it takes its competition list from is the one discovery just refreshed.

    Bounded on purpose. API-Football's free plan allows 100 requests a *day* — a fifth of
    the odds source's — so a run covers ``football_competitions_per_run`` competitions,
    least-recently-synced first, and asks for results over a window rather than a season.
    Nothing here is in the request path; the screens read what this job stores.

    A run with no provider configured is a success that did nothing: ``none`` is the
    default, and Batch 16 must not turn a deployment that has not opted in into a failing
    job every morning.
    """
    try:
        provider = await football_session.acquire()
        if provider is None:
            log.info("football data sync skipped: no provider configured")
            return True
        async with AsyncSessionLocal() as session:
            reports = await sync_football_data(
                session,
                provider,
                season=season_or_default(settings.football_season),
                limit=settings.football_competitions_per_run,
                lookback_days=settings.football_results_lookback_days,
                today=_uk_today(),
            )
            await session.commit()
        log.info(
            "football data synced",
            competitions=len(reports),
            carried=sum(1 for report in reports if report.carried),
            table_rows=sum(report.table_rows for report in reports),
            matches=sum(report.matches for report in reports),
        )
        return True
    except Exception:
        log.exception("football data sync failed")
        return False


async def run_backfill_football_season() -> bool:
    """Pull a whole season of results and tables in one pass — the Batch 16 backfill.

    Deliberately **not** on the scheduler: it is a one-off run for a new deployment, a
    newly added competition, or a season change, and it is unbounded in date, so putting
    it on a clock would spend the daily allowance on history that cannot change. Invoked
    through ``python -m src.run_scheduled football-backfill``.

    Set ``FOOTBALL_SEASON`` to backfill a season other than the current one.
    """
    try:
        provider = await football_session.acquire()
        if provider is None:
            log.info("football backfill skipped: no provider configured")
            return True
        season = season_or_default(settings.football_season)
        async with AsyncSessionLocal() as session:
            reports = await backfill_season(session, provider, season=season)
            await session.commit()
        log.info(
            "football season backfilled",
            season=season,
            competitions=len(reports),
            carried=sum(1 for report in reports if report.carried),
            matches=sum(report.matches for report in reports),
        )
        return True
    except Exception:
        log.exception("football season backfill failed")
        return False


async def run_pick_reminders() -> bool:
    """Nudge members who still owe a pick, in every league with an open round.

    Iterates rather than taking "the" open round: since Batch 14 each league has its
    own, so reminding only one would silently leave every other league unreminded.
    """
    try:
        async with AsyncSessionLocal() as session:
            gameweeks = await current_open_gameweeks(session, _utc_now())
            if not gameweeks:
                log.info("pick reminder: no open gameweek")
                return True
            reminded = {
                str(gameweek.id): await send_pick_reminders(session, gameweek)
                for gameweek in gameweeks
            }
            await session.commit()
        log.info("pick reminders sent", gameweeks=len(reminded), by_gameweek=reminded)
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
    # Wall-clock schedules in Europe/London — APScheduler handles the BST/GMT shift, so a
    # league's lock stays aligned with its window across the season.
    #
    # None of these filter on a weekday any more. They did when every league played the
    # same Saturday; since Batch 14 a league may play any day, and a Saturday-only lock
    # job would simply never lock a Friday league's round. The per-round predicates
    # (``locks_at_utc <= now``, ``status != settled``) are the real source of truth, so
    # firing more often costs a cheap query and firing late still self-heals.
    scheduler.add_job(
        run_discover_fixtures,
        trigger="cron",
        hour=6,
        minute=0,
        timezone="Europe/London",
        id="discover_fixtures",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_refresh_slate,
        trigger="cron",
        hour="9,13",  # twice daily: leagues may play any day, so no day_of_week filter
        minute=0,
        timezone="Europe/London",
        id="refresh_slate",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_sync_football_data,
        trigger="cron",
        hour=6,
        minute=30,  # half an hour behind discovery, so the fixture pool is already fresh
        timezone="Europe/London",
        id="sync_football_data",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_pick_reminders,
        trigger="cron",
        hour=11,  # daily; the job itself only reminds leagues with an open round
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
        minute=0,  # hourly: each round carries its own lock, this only decides when to look
        timezone="Europe/London",
        id="lock_gameweeks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_settle_gameweeks,
        trigger="cron",
        hour="18,20,22",  # evening sweeps, every day — leagues may finish on any of them
        minute=0,
        timezone="Europe/London",
        id="settle_gameweeks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
