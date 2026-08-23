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

import structlog
from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped,unused-ignore]
    AsyncIOScheduler,
)
from sqlalchemy import and_, delete, or_, text

from src.config import settings
from src.database import AsyncSessionLocal
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.refresh_token import RefreshToken
from src.services.backup import create_backup
from src.services.football_data import backfill_season, season_or_default, sync_football_data
from src.services.football_session import football_session
from src.services.gameweek import (
    active_leagues,
    current_open_gameweeks,
    discover_fixtures,
    lock_due_gameweeks,
    open_due_gameweeks,
    settleable_gameweeks,
    uk_today,
    window_for,
)
from src.services.live_scores import poll_live_scores
from src.services.notification_triggers import send_pick_reminders
from src.services.odds_session import odds_session
from src.services.scoring import (
    settle_gameweeks_via_provider,
    standings,
)

#: How long a dead refresh token is kept before ``run_prune_refresh_tokens`` removes it.
#: Long enough that a revoked row still serves as evidence for reuse detection in
#: ``/auth/refresh``, short enough that the table does not accumulate a season of them.
REFRESH_TOKEN_RETENTION = timedelta(days=7)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    """Naive-UTC now — matches the ``*_utc`` storage convention used across the schema."""
    return datetime.now(UTC).replace(tzinfo=None)


def _uk_today() -> date:
    """Today's date in UK local time — the anchor for 'this Saturday's' slate.

    Delegates so the rule has one implementation; kept as a module-level name because
    the scheduler tests patch it to drive the clock.
    """
    return uk_today()


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


async def run_prune_refresh_tokens() -> bool:
    """Delete refresh tokens that can no longer be used. Housekeeping, not security.

    ``refresh_tokens`` was append-only: every login and every rotation inserted a row and
    nothing ever removed one. Rotation means a busy member writes a row per refresh, so
    the table grows without bound on a Supabase Free project with 500 MB to spend.

    A row is removable once it can never authenticate again — expired, or revoked. Both
    get a grace period rather than going immediately, because a revoked row is the only
    evidence of a *reuse* attempt: ``/auth/refresh`` distinguishes a replay from an
    unknown token by finding the revoked row, and deleting it too eagerly would turn a
    detected theft back into a silent 401.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - REFRESH_TOKEN_RETENTION
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(RefreshToken).where(
                    or_(
                        RefreshToken.expires_at < cutoff,
                        and_(
                            RefreshToken.revoked_at.is_not(None),
                            RefreshToken.revoked_at < cutoff,
                        ),
                    )
                )
            )
            await session.commit()
        log.info("pruned refresh tokens", removed=result.rowcount or 0)
        return True
    except Exception:
        log.exception("refresh token prune failed")
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
        football = await football_session.acquire()
        async with AsyncSessionLocal() as session:
            leagues = await active_leagues(session)
            gameweeks = await discover_fixtures(
                session,
                provider,
                leagues,
                _uk_today(),
                settings.slate_horizon_weeks,
                football=football,
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
    a postponement or a kick-off change. The horizon is 1 rather than the whole set,
    because the far weeks have not firmed up yet and re-fetching them would spend the
    provider budget on nothing.

    That horizon covers the nearest date of each league's *window* and any still-claimable
    round it already holds inside the same week, which is how an admin's one-off — Boxing
    Day, say — is reached at all: it is off the weekly cadence, so nothing else would ever
    revisit it.

    Odds themselves are snapshotted onto each pick at pick time and served through the
    provider's own TTL cache, so there is nothing to warm here.
    """
    try:
        provider = await odds_session.acquire()
        football = await football_session.acquire()
        async with AsyncSessionLocal() as session:
            leagues = await active_leagues(session)
            # Horizon of 1: only the round about to be played.
            gameweeks = await discover_fixtures(
                session, provider, leagues, _uk_today(), 1, football=football
            )
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


async def run_open_gameweeks() -> bool:
    """Open any scheduled gameweek whose announced pick-open time has passed.

    Label-keeping only, and deliberately so: the submit endpoint decides on the stored
    instant, so a member is never held out by a job that has not run. This is what makes
    the badge on the screen agree with the rule — which is the whole point of announcing
    an opening rather than letting discovery decide it.
    """
    try:
        async with AsyncSessionLocal() as session:
            opened = await open_due_gameweeks(session, _utc_now())
            gameweek_ids = [str(g.id) for g in opened]
            await session.commit()
        if gameweek_ids:
            log.info("gameweeks opened", count=len(gameweek_ids), gameweek_ids=gameweek_ids)
        return True
    except Exception:
        log.exception("gameweek open failed")
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

    Every settleable round is settled from **one** provider read, not one read per round:
    :func:`~src.services.scoring.settle_gameweeks_via_provider` de-duplicates the
    outstanding fixtures across the whole run first, so leagues sharing a Saturday share
    the requests it costs rather than each buying the same fixtures again (Batch 31).

    Idempotent: it resolves only picks whose fixture has a final result, so the
    Saturday-evening re-runs pick up late results and flip a gameweek to ``settled`` once
    nothing is pending. That retry window matters more under odds-api.io than it did on the
    Exchange, because a result is derived from a published score rather than pushed by a
    settlement feed. Standings are then recomputed per participating league and logged
    (they are read on demand — this surfaces the outcome).
    """
    try:
        provider = await odds_session.acquire()
        async with AsyncSessionLocal() as session:
            gameweeks = await settleable_gameweeks(session, _utc_now())
            resolved = await settle_gameweeks_via_provider(session, provider, gameweeks)
            # Keyed over every settleable round, so the log still names the rounds this
            # run considered and not only the ones that moved.
            resolved_by_gameweek = {str(g.id): resolved.get(g.id, 0) for g in gameweeks}
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

    Bounded on purpose. API-Football's free plan allows 100 requests a *day* and 10 a
    minute, so a run covers ``football_competitions_per_run`` competitions,
    least-recently-synced first, spaces each competition attempt, and asks for results
    over a window rather than a season. Nothing here is in the request path; the screens
    read what this job stores.

    A run with no provider configured is a success that did nothing: ``none`` is the
    default, and Batch 16 must not turn a deployment that has not opted in into a failing
    job every morning. A run over an empty fixture pool is a success for the same reason.

    **A run that attempted a non-empty card and carried none of it is a failure** (Batch
    45). It did not used to be: this returned ``True`` on any run that reached the
    provider, so on 2026-08-20 a sweep that failed all 21 competitions — 18 rejected at
    ``/standings`` because the free plan carries no part of the current season, 3 cups
    that resolve no id — logged ``football data synced`` and exited 0, and had been doing
    so every morning while ingesting nothing. The summary line carried the truth the
    whole time; nothing was reading it.

    The sweep's own tolerance is untouched. One division the provider dropped must not
    cost the other twenty-nine their tables, and it still does not — the verdict is the
    caller's job, not the sweep's.
    """
    try:
        provider = await football_session.acquire()
        if provider is None:
            log.info("football data sync skipped: no provider configured")
            return True
        async with AsyncSessionLocal() as session:
            sweep = await sync_football_data(
                session,
                provider,
                season=season_or_default(settings.football_season),
                limit=settings.football_competitions_per_run,
                lookback_days=settings.football_results_lookback_days,
                today=_uk_today(),
                competition_spacing_seconds=settings.football_competition_spacing_seconds,
            )
            await session.commit()
        if sweep.carried_nothing:
            log.error("football data sync carried nothing", **sweep.summary())
            return False
        log.info("football data synced", **sweep.summary())
        return True
    except Exception:
        log.exception("football data sync failed")
        return False


async def run_live_scores() -> bool:
    """Refresh the running score for any round being played right now (Batch 72).

    **Costs nothing when nothing is on**, which is most hours of most weeks:
    :func:`~src.services.live_scores.competitions_in_play` answers from the database and
    the job returns before touching a provider. That is what makes a ten-minute cadence
    affordable rather than rude.

    Bounded the other way too. "In play" is Batch 65's definition, so a round the odds
    provider never settles stops being polled once it passes the grace measured from its
    own window closing — without that, Batch 64's phantom Premiership round would have
    kept a competition being fetched every ten minutes until May.

    **Writes only to ``teams`` and ``matches``. Never to ``picks``.** Settlement has one
    authority and it is the odds provider; a live score that moved a pick's status would
    be a member watching points awarded and then withdrawn.

    No provider, or a provider that cannot answer, is a success that did nothing — the
    round simply renders without scores, which is the degradation this feature is
    supposed to have.
    """
    try:
        provider = await football_session.acquire()
        if provider is None:
            return True
        async with AsyncSessionLocal() as session:
            sweep = await poll_live_scores(
                session,
                provider,
                season=season_or_default(settings.football_season),
                now=_utc_now(),
                limit=settings.live_scores_competitions_per_run,
            )
            await session.commit()
        if sweep.rounds_in_play:
            log.info("live scores polled", **sweep.summary())
        return True
    except Exception:
        log.exception("live score poll failed")
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
            sweep = await backfill_season(session, provider, season=season)
            await session.commit()
        if sweep.carried_nothing:
            # Same verdict as the daily job, for the same reason. A human runs this one
            # and reads its output, which makes a silent total failure more likely to be
            # believed rather than less.
            log.error("football backfill carried nothing", season=season, **sweep.summary())
            return False
        log.info("football season backfilled", season=season, **sweep.summary())
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
        run_prune_refresh_tokens,
        trigger="cron",
        hour=4,
        minute=30,  # after the 03:00 backup, so a pruned row is still in last night's copy
        id="prune_refresh_tokens",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
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
    # Every ten minutes, and almost always free: the job reads the database first and
    # returns without a request unless some league has a round in play. Ten minutes is
    # chosen against what it is for — a member glancing at a score during the round —
    # rather than against a rate limit, because FotMob has none to protect.
    scheduler.add_job(
        run_live_scores,
        trigger="cron",
        minute="*/10",
        id="live_scores",
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
        run_open_gameweeks,
        trigger="cron",
        minute=1,  # hourly, a minute clear of the lock sweep so the two never interleave
        timezone="Europe/London",
        id="open_gameweeks",
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
