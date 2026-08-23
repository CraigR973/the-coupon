"""The site admin's console: people, and the operational half.

Batch 66, and the reason it exists is a journey that stopped halfway. Batch 56 made
``/auth/pin/reset-request`` truthful — it had promised "an admin will be notified" and
notified nobody, and it now writes an audit row and pushes every active site admin. The
notification was real and **the action behind it did not exist**: the push sent the admin
to their own settings page because there was nowhere else to send them, and exactly one
endpoint in the whole API used the ``AdminUser`` dependency (avatar removal). A member
who forgot four digits was a lost account.

Batch 69 added the operational half — dashboard, manual sync, manual results — on the
strength of work already being done by hand: Batch 64 opened with a Motherwell pick
returned manually and twelve fixtures removed manually, and Batch 68 is a backfill run
straight against the database.

**A manual sync trigger spends a shared, rate-limited budget.** It draws on the very same
per-admin bucket the ad-hoc slate fetch uses (``PROVIDER_SLATE_FETCH_SCOPE``) rather than a
second one of its own, because two ``2/hour`` limits against a plan with room for two is
simply ``4/hour``. See :mod:`src.services.admin_ops` for the cost each button carries.

Everything on this router is refused to a non-admin by :data:`~src.auth.AdminUser`, which
is a dependency rather than a check inside each handler so a new route cannot be added
without one.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Subquery

from src.auth import AdminUser, generate_join_code
from src.config import settings
from src.database import get_db
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.invite import Invite
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.pick import Pick, PickStatus
from src.models.profile import Profile
from src.rate_limit import consume_shared_limit, limiter, per_user_key
from src.routers.leagues import PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE
from src.schemas import UtcDatetime
from src.services.admin_ops import (
    job_by_key,
    manual_jobs,
    settlement_from_score,
    voided_settlement,
)
from src.services.credentials import (
    STAGE_RESET,
    clear_pin,
    pin_reset_audit,
    revoke_all_refresh_tokens,
)
from src.services.gameweek import PICKABLE_STATES
from src.services.scoring import settle_gameweek

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

Db = Annotated[AsyncSession, Depends(get_db)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _audit(
    actor: Profile,
    action: ActionType,
    target_table: str,
    target_id: uuid.UUID | None = None,
    changes: dict[str, object] | None = None,
) -> AuditLog:
    return AuditLog(
        actor_id=actor.id,
        actor_type=ActorType.admin,
        action_type=action,
        target_table=target_table,
        target_id=target_id,
        changes=changes,
    )


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


class AdminPlayer(BaseModel):
    """One member, as the console needs to see them.

    ``pin_set`` rather than anything about the hash: the console has to distinguish a
    member who simply cannot remember their PIN from one whose reset is already done and
    waiting on them, and those look identical from the outside otherwise.
    """

    id: str
    display_name: str
    role: str
    is_active: bool
    pin_set: bool
    failed_login_count: int
    locked_until: UtcDatetime | None
    deleted_at: UtcDatetime | None
    league_count: int
    created_at: UtcDatetime


class ResetPinResult(BaseModel):
    """What a reset did, so the console can say it rather than imply it."""

    pin_cleared: bool
    sessions_revoked: int


async def _load_player(db: AsyncSession, player_id: uuid.UUID) -> Profile:
    player = (await db.execute(select(Profile).where(Profile.id == player_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return player


@router.get("/players", response_model=list[AdminPlayer])
@limiter.limit("60/minute", key_func=per_user_key)
async def list_players(request: Request, admin: AdminUser, db: Db) -> list[AdminPlayer]:
    """Every member, deleted ones included.

    Deleted members are listed rather than filtered out because the delete is a *soft*
    one and their name stays reserved (see :func:`delete_player`) — an admin asking "why
    can nobody register as Dave" needs to be able to see the answer.
    """
    league_counts = (
        select(
            LeagueMembership.player_id.label("player_id"),
            func.count().label("leagues"),
        )
        .where(LeagueMembership.deleted_at.is_(None))
        .group_by(LeagueMembership.player_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Profile, func.coalesce(league_counts.c.leagues, 0))
            .outerjoin(league_counts, league_counts.c.player_id == Profile.id)
            .order_by(Profile.display_name)
        )
    ).all()
    return [
        AdminPlayer(
            id=str(player.id),
            display_name=player.display_name,
            role=player.role.value,
            is_active=player.is_active,
            pin_set=player.pin_hash is not None,
            failed_login_count=player.failed_login_count,
            locked_until=player.locked_until,
            deleted_at=player.deleted_at,
            league_count=leagues,
            created_at=player.created_at,
        )
        for player, leagues in rows
    ]


@router.post("/players/{player_id}/reset-pin", response_model=ResetPinResult)
@limiter.limit("20/hour", key_func=per_user_key)
async def reset_player_pin(
    request: Request, player_id: uuid.UUID, admin: AdminUser, db: Db
) -> ResetPinResult:
    """Clear a member's PIN so they can choose a new one at their next sign-in.

    No temporary PIN is minted and nothing is returned for the admin to read out — the
    owner's decision on 2026-08-23, and the point of it is that no secret passes through
    a third person. The whole of what this does lives in
    :func:`~src.services.credentials.clear_pin`, shared with the league-admin reset,
    because "an admin reset revokes every session" is a rule and a rule with two
    implementations is a rule with one bug.

    The audit row is what makes the cleared state claimable: ``/auth/pin/set`` reads it
    for the window, so a reset that is not recorded is a reset that cannot be used.
    """
    player = await _load_player(db, player_id)
    if player.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    revoked = await clear_pin(db, player)
    db.add(pin_reset_audit(admin, player, STAGE_RESET))
    await db.commit()
    log.info(
        "pin cleared by site admin",
        player_id=str(player_id),
        admin_id=str(admin.id),
        sessions_revoked=revoked,
    )
    return ResetPinResult(pin_cleared=True, sessions_revoked=revoked)


@router.post("/players/{player_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/hour", key_func=per_user_key)
async def unlock_player(request: Request, player_id: uuid.UUID, admin: AdminUser, db: Db) -> None:
    """Give a locked-out member their attempts back without touching their PIN.

    The lighter of the two remedies and usually the right one: a member who *knows* their
    PIN and mistyped it five times needs the counter cleared, not their credential taken
    away. Batch 56 already stopped an expired lockout ratcheting; this is for the fifteen
    minutes before it expires.

    No audit row. There is no ``ActionType`` for it and adding one is irreversible —
    ``ALTER TYPE ... ADD VALUE`` cannot be undone and production has no restore point
    (owner's 2026-07-30 deferral) — so this is logged rather than recorded, which is the
    right trade for an action that takes nothing away and grants no access.
    """
    player = await _load_player(db, player_id)
    player.failed_login_count = 0
    player.locked_until = None
    player.updated_at = _now()
    await db.commit()
    log.info("account unlocked by admin", player_id=str(player_id), admin_id=str(admin.id))


@router.delete("/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/hour", key_func=per_user_key)
async def delete_player(request: Request, player_id: uuid.UUID, admin: AdminUser, db: Db) -> None:
    """Remove a member from the product without removing them from its history.

    A **soft** delete (owner, 2026-08-23): ``deleted_at`` is stamped, the profile is
    deactivated and every session is revoked, and their picks stay exactly where they
    are so past leaderboards read as they were played. A hard delete would silently
    rewrite settled weeks other members remember.

    **Their display name stays reserved**, and that is a consequence rather than an
    oversight. ``display_name`` is globally unique and is the login identifier, and Batch
    63's case-insensitive uniqueness check includes soft-deleted rows specifically so a
    departed member's name cannot be re-registered by somebody else. Freeing it would
    mean reversing that, which is a different decision from deleting a player.

    An admin cannot delete themselves — there is no undelete screen, and locking the only
    admin out of the console is not a state to make one click away.
    """
    if player_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot delete your own account here.",
        )
    player = await _load_player(db, player_id)
    if player.deleted_at is not None:
        return

    player.deleted_at = _now()
    player.is_active = False
    player.updated_at = _now()
    revoked = await revoke_all_refresh_tokens(db, player.id)
    db.add(
        _audit(
            admin,
            # No site-level "player deleted" value exists and adding one is irreversible
            # (see :func:`unlock_player`). ``member_removed`` is the nearest true thing
            # and ``target_table`` says which kind of removal this was.
            ActionType.member_removed,
            "profiles",
            player.id,
            {"display_name": player.display_name, "scope": "site"},
        )
    )
    await db.commit()
    log.info(
        "player soft-deleted by admin",
        player_id=str(player_id),
        admin_id=str(admin.id),
        sessions_revoked=revoked,
    )


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


def _names_subquery() -> Subquery:
    """A handle on ``profiles`` carrying only the two columns the invite join wants.

    An invite names two members — who made it and who spent it — so the query needs the
    table twice. A subquery per side rather than ``aliased(Profile)`` because nothing
    here wants a whole profile, and joining the full mapper twice for two strings drags
    every column of both.
    """
    return select(Profile.id, Profile.display_name).subquery()


class AdminInvite(BaseModel):
    id: str
    token: str
    display_name_hint: str | None
    league_id: str
    league_name: str
    league_slug: str
    created_by_name: str | None
    claimed_by_name: str | None
    claimed_at: UtcDatetime | None
    expires_at: UtcDatetime | None
    is_active: bool
    created_at: UtcDatetime


@router.get("/invites", response_model=list[AdminInvite])
@limiter.limit("60/minute", key_func=per_user_key)
async def list_invites(request: Request, admin: AdminUser, db: Db) -> list[AdminInvite]:
    """Every invite in the product, live and spent, newest first.

    The league-admin screen already lists a single league's *active* invites. This one is
    cross-league and includes the claimed ones, because the question it answers is "who
    let this person in", which the active-only view cannot.
    """
    creator = _names_subquery()
    claimer = _names_subquery()
    rows = (
        await db.execute(
            select(Invite, League, creator.c.display_name, claimer.c.display_name)
            .join(League, League.id == Invite.league_id)
            .outerjoin(creator, creator.c.id == Invite.created_by)
            .outerjoin(claimer, claimer.c.id == Invite.claimed_by)
            .order_by(Invite.created_at.desc())
        )
    ).all()
    return [
        AdminInvite(
            id=str(invite.id),
            token=invite.token,
            display_name_hint=invite.display_name_hint,
            league_id=str(league.id),
            league_name=league.name,
            league_slug=league.slug,
            created_by_name=created_by,
            claimed_by_name=claimed_by,
            claimed_at=invite.claimed_at,
            expires_at=invite.expires_at,
            is_active=invite.is_active,
            created_at=invite.created_at,
        )
        for invite, league, created_by, claimed_by in rows
    ]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/hour", key_func=per_user_key)
async def revoke_invite(request: Request, invite_id: uuid.UUID, admin: AdminUser, db: Db) -> None:
    """Deactivate one invite link, whichever league it belongs to."""
    invite = (await db.execute(select(Invite).where(Invite.id == invite_id))).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite.is_active = False
    db.add(_audit(admin, ActionType.league_invite_revoked, "invites", invite.id, {"scope": "site"}))
    await db.commit()
    log.info("invite revoked by site admin", invite_id=str(invite_id), admin_id=str(admin.id))


# ---------------------------------------------------------------------------
# Leagues
# ---------------------------------------------------------------------------


class AdminLeague(BaseModel):
    id: str
    slug: str
    name: str
    privacy: str
    join_code: str | None
    member_count: int
    max_members: int
    created_at: UtcDatetime
    deleted_at: UtcDatetime | None


class RotatedJoinCode(BaseModel):
    join_code: str


@router.get("/leagues", response_model=list[AdminLeague])
@limiter.limit("60/minute", key_func=per_user_key)
async def list_leagues(request: Request, admin: AdminUser, db: Db) -> list[AdminLeague]:
    """Every league, including ones the admin is not a member of.

    That is the whole point of the screen: a site admin is not automatically in any
    league, so without this there is no way to see one they were never invited to, and
    the join code they would need to rotate is only served to members.
    """
    member_counts = (
        select(
            LeagueMembership.league_id.label("league_id"),
            func.count().label("members"),
        )
        .where(LeagueMembership.deleted_at.is_(None))
        .group_by(LeagueMembership.league_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(League, func.coalesce(member_counts.c.members, 0))
            .outerjoin(member_counts, member_counts.c.league_id == League.id)
            .order_by(League.name)
        )
    ).all()
    return [
        AdminLeague(
            id=str(league.id),
            slug=league.slug,
            name=league.name,
            privacy=league.privacy.value,
            join_code=league.join_code,
            member_count=members,
            max_members=league.max_members,
            created_at=league.created_at,
            deleted_at=league.deleted_at,
        )
        for league, members in rows
    ]


@router.post("/leagues/{league_id}/rotate-join-code", response_model=RotatedJoinCode)
@limiter.limit("20/hour", key_func=per_user_key)
async def rotate_league_join_code(
    request: Request, league_id: uuid.UUID, admin: AdminUser, db: Db
) -> RotatedJoinCode:
    """Mint a new join code for any league. The old link stops working immediately."""
    league = (await db.execute(select(League).where(League.id == league_id))).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    league.join_code = generate_join_code()
    league.updated_at = _now()
    db.add(
        _audit(admin, ActionType.league_join_code_rotated, "leagues", league.id, {"scope": "site"})
    )
    await db.commit()
    log.info("join code rotated by site admin", league_id=str(league_id), admin_id=str(admin.id))
    return RotatedJoinCode(join_code=league.join_code)


# ---------------------------------------------------------------------------
# Dashboard (Batch 69)
# ---------------------------------------------------------------------------


class UpcomingLock(BaseModel):
    """The next deadline one league is running towards."""

    league_slug: str
    league_name: str
    gameweek_id: str
    starts_on: date
    locks_at_utc: UtcDatetime
    picks_in: int
    members: int


class StuckRound(BaseModel):
    """A round past its lock that has not settled — the shape that hangs forever.

    Batch 64's phantom Scottish Premiership round is the worked example: the odds provider
    never resolved the fixtures, so the picks stayed pending, so the round never settled,
    and Batch 65 had to bound how long such a round may keep pinning its league. Counting
    them is how an admin finds out before a member does.
    """

    league_slug: str
    league_name: str
    gameweek_id: str
    starts_on: date
    locks_at_utc: UtcDatetime
    pending_picks: int


class AuditEntry(BaseModel):
    id: str
    actor_name: str | None
    action_type: str
    target_table: str
    target_id: str | None
    timestamp: UtcDatetime


class SchedulerJobState(BaseModel):
    id: str
    next_run_utc: UtcDatetime | None


class SchedulerState(BaseModel):
    """Whether the in-process scheduler is actually running, and what it holds.

    ``enabled`` is the configured intent and ``running`` is the fact. They come apart in
    exactly the case worth knowing about — a container that restarted into a state where
    APScheduler never started — and the runbook's answer to that is the external cron
    (``docs/runbooks/scheduled-jobs-cron.md``), which this screen's manual triggers are the
    third way of reaching.
    """

    enabled: bool
    running: bool
    jobs: list[SchedulerJobState]


class AdminDashboard(BaseModel):
    active_members: int
    members_awaiting_pin: int
    leagues: int
    upcoming_locks: list[UpcomingLock]
    stuck_rounds: list[StuckRound]
    recent_audit: list[AuditEntry]
    scheduler: SchedulerState


#: How much of the audit trail the dashboard shows. Enough to see this morning's activity,
#: short enough that the screen stays a summary rather than a log viewer.
RECENT_AUDIT_ROWS = 25


def _scheduler_state(request: Request) -> SchedulerState:
    """What the running scheduler holds, read from the live instance rather than config.

    ``main.py`` stores it on ``app.state`` and starts it only when ``scheduler_enabled``.
    Reading the instance means a scheduler that was configured on and failed to start
    reports ``running: false`` rather than being reported by its own setting.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return SchedulerState(enabled=settings.scheduler_enabled, running=False, jobs=[])
    jobs = [
        SchedulerJobState(
            id=str(job.id),
            next_run_utc=(
                job.next_run_time.astimezone(UTC).replace(tzinfo=None)
                if getattr(job, "next_run_time", None)
                else None
            ),
        )
        for job in scheduler.get_jobs()
    ]
    return SchedulerState(
        enabled=settings.scheduler_enabled,
        running=bool(scheduler.running),
        jobs=sorted(jobs, key=lambda entry: entry.id),
    )


@router.get("/dashboard", response_model=AdminDashboard)
@limiter.limit("60/minute", key_func=per_user_key)
async def dashboard(request: Request, admin: AdminUser, db: Db) -> AdminDashboard:
    """One read of everything an admin checks on a Saturday morning.

    Read-only: nothing here triggers a job, spends a provider request or writes a row, so
    it is safe to leave open on a second screen.
    """
    now = _now()

    active_members = (
        await db.execute(
            select(func.count())
            .select_from(Profile)
            .where(Profile.deleted_at.is_(None), Profile.is_active.is_(True))
        )
    ).scalar_one()
    awaiting_pin = (
        await db.execute(
            select(func.count())
            .select_from(Profile)
            .where(
                Profile.deleted_at.is_(None),
                Profile.is_active.is_(True),
                Profile.pin_hash.is_(None),
            )
        )
    ).scalar_one()
    league_count = (
        await db.execute(
            select(func.count()).select_from(League).where(League.deleted_at.is_(None))
        )
    ).scalar_one()

    picks_on_round = (
        select(Pick.gameweek_id.label("gameweek_id"), func.count().label("picks"))
        .group_by(Pick.gameweek_id)
        .subquery()
    )
    pending_on_round = (
        select(Pick.gameweek_id.label("gameweek_id"), func.count().label("pending"))
        .where(Pick.status == PickStatus.pending)
        .group_by(Pick.gameweek_id)
        .subquery()
    )
    members_in_league = (
        select(LeagueMembership.league_id.label("league_id"), func.count().label("members"))
        .where(LeagueMembership.deleted_at.is_(None))
        .group_by(LeagueMembership.league_id)
        .subquery()
    )

    # The next deadline per league, not every future round: the horizon holds two or
    # three, and only the nearest is a thing anyone can still act on.
    ranked = (
        select(
            Gameweek.id,
            Gameweek.league_id,
            Gameweek.starts_on,
            Gameweek.locks_at_utc,
            func.row_number()
            .over(partition_by=Gameweek.league_id, order_by=Gameweek.locks_at_utc.asc())
            .label("rn"),
        )
        .where(Gameweek.status.in_(PICKABLE_STATES), Gameweek.locks_at_utc > now)
        .subquery()
    )
    lock_rows = (
        await db.execute(
            select(
                ranked.c.id,
                ranked.c.starts_on,
                ranked.c.locks_at_utc,
                League.slug,
                League.name,
                func.coalesce(picks_on_round.c.picks, 0),
                func.coalesce(members_in_league.c.members, 0),
            )
            .join(League, League.id == ranked.c.league_id)
            .outerjoin(picks_on_round, picks_on_round.c.gameweek_id == ranked.c.id)
            .outerjoin(members_in_league, members_in_league.c.league_id == League.id)
            .where(ranked.c.rn == 1, League.deleted_at.is_(None))
            .order_by(ranked.c.locks_at_utc)
        )
    ).all()

    stuck_rows = (
        await db.execute(
            select(
                Gameweek.id,
                Gameweek.starts_on,
                Gameweek.locks_at_utc,
                League.slug,
                League.name,
                func.coalesce(pending_on_round.c.pending, 0),
            )
            .join(League, League.id == Gameweek.league_id)
            .outerjoin(pending_on_round, pending_on_round.c.gameweek_id == Gameweek.id)
            .where(
                Gameweek.status != GameweekStatus.settled,
                Gameweek.locks_at_utc <= now,
                League.deleted_at.is_(None),
            )
            .order_by(Gameweek.locks_at_utc)
        )
    ).all()

    actor = _names_subquery()
    audit_rows = (
        await db.execute(
            select(AuditLog, actor.c.display_name)
            .outerjoin(actor, actor.c.id == AuditLog.actor_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(RECENT_AUDIT_ROWS)
        )
    ).all()

    return AdminDashboard(
        active_members=active_members,
        members_awaiting_pin=awaiting_pin,
        leagues=league_count,
        upcoming_locks=[
            UpcomingLock(
                league_slug=slug,
                league_name=name,
                gameweek_id=str(gameweek_id),
                starts_on=starts_on,
                locks_at_utc=locks_at,
                picks_in=picks,
                members=members,
            )
            for gameweek_id, starts_on, locks_at, slug, name, picks, members in lock_rows
        ],
        stuck_rounds=[
            StuckRound(
                league_slug=slug,
                league_name=name,
                gameweek_id=str(gameweek_id),
                starts_on=starts_on,
                locks_at_utc=locks_at,
                pending_picks=pending,
            )
            for gameweek_id, starts_on, locks_at, slug, name, pending in stuck_rows
        ],
        recent_audit=[
            AuditEntry(
                id=str(entry.id),
                actor_name=actor_name,
                action_type=entry.action_type.value,
                target_table=entry.target_table,
                target_id=str(entry.target_id) if entry.target_id else None,
                timestamp=entry.timestamp,
            )
            for entry, actor_name in audit_rows
        ],
        scheduler=_scheduler_state(request),
    )


# ---------------------------------------------------------------------------
# Sync — per-job status and manual trigger (Batch 69)
# ---------------------------------------------------------------------------


class SyncJob(BaseModel):
    """One job an admin may run now, with what it will cost before they press it."""

    key: str
    label: str
    summary: str
    #: Estimated upstream calls against odds-api.io's metered plan. ``0`` is free.
    provider_requests: int
    spends_budget: bool
    #: How many of the shared bucket's hits one press costs. The bucket is denominated in
    #: slate walks, so a job walking the whole horizon costs more than one.
    budget_units: int
    next_run_utc: UtcDatetime | None


class SyncJobs(BaseModel):
    """The buttons, plus the budget they are all drawing on.

    ``hourly_budget`` and ``budget_limit`` are on the response rather than hard-coded in
    the client because the cost is only meaningful against the plan: "30 requests" says
    nothing, "30 of 100 an hour, shared with the scheduler" says what pressing it risks.
    """

    jobs: list[SyncJob]
    hourly_budget: int
    budget_limit: str


class SyncRunResult(BaseModel):
    key: str
    ok: bool


#: odds-api.io's free plan, measured 2026-08-04 and asserted in
#: ``tests/test_request_budget.py``. Shown beside each job's cost so an admin can see how
#: much of the hour a button takes.
PROVIDER_HOURLY_BUDGET = 100


@router.get("/jobs", response_model=SyncJobs)
@limiter.limit("60/minute", key_func=per_user_key)
async def list_jobs(request: Request, admin: AdminUser) -> SyncJobs:
    """What can be run by hand, when it is next due, and what running it costs."""
    scheduled = {job.id: job.next_run_utc for job in _scheduler_state(request).jobs}
    # The cron entry point and the in-process scheduler name the same job differently —
    # ``refresh-slate`` against ``refresh_slate`` — so the two are joined on the shape
    # rather than assumed equal.
    return SyncJobs(
        jobs=[
            SyncJob(
                key=job.key,
                label=job.label,
                summary=job.summary,
                provider_requests=job.provider_requests,
                spends_budget=job.spends_budget,
                budget_units=job.budget_units,
                next_run_utc=scheduled.get(job.key.replace("-", "_")),
            )
            for job in manual_jobs()
        ],
        hourly_budget=PROVIDER_HOURLY_BUDGET,
        budget_limit=PROVIDER_SLATE_FETCH_LIMIT,
    )


@router.post("/jobs/{key}/run", response_model=SyncRunResult)
@limiter.limit("30/hour", key_func=per_user_key)
async def run_job(request: Request, key: str, admin: AdminUser) -> SyncRunResult:
    """Run one scheduled job now — the same coroutine the scheduler runs.

    Taken from :data:`~src.run_scheduled.JOBS`, so there is no second implementation to
    drift: a hand-triggered settle and a 20:00 settle are the same call on the same input
    and write the same rows.

    **A job that spends the provider budget is charged to the shared per-admin bucket**
    rather than to a limit of its own. odds-api.io allows roughly 100 requests an hour
    across the whole deployment, the scheduler's jobs are sized against that, and a second
    ``2/hour`` limit beside the existing one would simply be ``4/hour`` — which is how an
    admin refreshing a slate at 14:00 on a Saturday 429s the refresh that matters. Free
    jobs are charged nothing, because pricing the harmless ones out is how the useful
    button stops being pressed.

    The job owns its own error handling and returns a success flag; a false answer is a
    job that ran and failed, not a request that broke, so it is a 200 carrying ``ok:
    false`` rather than a 500. The detail is in the logs the job itself wrote.
    """
    job = job_by_key(key)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job")

    # Charged per *slate walk*, not per press: the bucket was sized against one walk of
    # the thirty UK competitions, so discovery — which walks the whole horizon — costs
    # more than one. Charging it once would let an admin spend twice what the limit
    # permits, which is the same arithmetic error Batch 57 found on the pick path.
    bucket_key = per_user_key(request)
    if job.spends_budget and not all(
        consume_shared_limit(bucket_key, PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE)
        for _ in range(job.budget_units)
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "That job spends the shared odds-api.io budget and this hour's share is "
                "gone. The scheduler's own runs come first."
            ),
        )

    ok = await job.run()
    log.info("job run by admin", job=key, admin_id=str(admin.id), ok=ok)
    return SyncRunResult(key=key, ok=ok)


# ---------------------------------------------------------------------------
# Results — pending rounds, manual entry and override (Batch 69)
# ---------------------------------------------------------------------------


class PendingFixture(BaseModel):
    """One fixture on a round that has not settled, and what is riding on it."""

    fixture_id: str
    provider_event_id: str
    home: str
    away: str
    competition: str
    kickoff_utc: UtcDatetime
    pending_picks: int


class PendingRound(BaseModel):
    league_slug: str
    league_name: str
    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: UtcDatetime
    fixtures: list[PendingFixture]


class ManualResult(BaseModel):
    """One hand-entered result: a final score, or the fixture called off.

    A **score**, not a set of market verdicts. Both markets The Coupon offers follow from
    it, and asking an admin to say separately whether both teams scored is asking them to
    do arithmetic the code can do — and to get it wrong in a way nothing would catch.
    """

    fixture_id: uuid.UUID
    home_goals: int | None = Field(default=None, ge=0, le=99)
    away_goals: int | None = Field(default=None, ge=0, le=99)
    #: The fixture was never played. Every pick on it scores nothing and loses nothing.
    void: bool = False


class ManualResultsRequest(BaseModel):
    results: list[ManualResult]


class ManualResultsResponse(BaseModel):
    gameweek_id: str
    picks_resolved: int
    settled: bool


@router.get("/results/pending", response_model=list[PendingRound])
@limiter.limit("60/minute", key_func=per_user_key)
async def pending_results(request: Request, admin: AdminUser, db: Db) -> list[PendingRound]:
    """Every round past its lock with picks still pending, and the fixtures holding it up.

    The list the manual-entry screen works from. A round appears here because the odds
    provider has not resolved something, which is a state that does not clear itself —
    Batch 64's phantom round sat in it while the settle sweep ran three times a day.
    """
    now = _now()
    rounds = (
        await db.execute(
            select(Gameweek, League.slug, League.name)
            .join(League, League.id == Gameweek.league_id)
            .where(
                Gameweek.status != GameweekStatus.settled,
                Gameweek.locks_at_utc <= now,
                League.deleted_at.is_(None),
            )
            .order_by(Gameweek.locks_at_utc)
        )
    ).all()
    if not rounds:
        return []

    gameweek_ids = [gameweek.id for gameweek, _, _ in rounds]
    fixture_rows = (
        await db.execute(
            select(Pick.gameweek_id, Fixture, func.count().label("pending"))
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(Pick.gameweek_id.in_(gameweek_ids), Pick.status == PickStatus.pending)
            .group_by(Pick.gameweek_id, Fixture.id)
            .order_by(Fixture.kickoff_utc)
        )
    ).all()

    by_round: dict[uuid.UUID, list[PendingFixture]] = {}
    for gameweek_id, fixture, pending in fixture_rows:
        by_round.setdefault(gameweek_id, []).append(
            PendingFixture(
                fixture_id=str(fixture.id),
                provider_event_id=fixture.provider_event_id,
                home=fixture.home,
                away=fixture.away,
                competition=fixture.competition,
                kickoff_utc=fixture.kickoff_utc,
                pending_picks=pending,
            )
        )

    return [
        PendingRound(
            league_slug=slug,
            league_name=name,
            gameweek_id=str(gameweek.id),
            starts_on=gameweek.starts_on,
            status=gameweek.status.value,
            locks_at_utc=gameweek.locks_at_utc,
            fixtures=by_round.get(gameweek.id, []),
        )
        for gameweek, slug, name in rounds
    ]


@router.post("/results/{gameweek_id}/settle", response_model=ManualResultsResponse)
@limiter.limit("20/hour", key_func=per_user_key)
async def settle_manually(
    request: Request,
    gameweek_id: uuid.UUID,
    body: ManualResultsRequest,
    admin: AdminUser,
    db: Db,
) -> ManualResultsResponse:
    """Settle a round from hand-entered results — the same path the scheduler settles on.

    The scores become :class:`~src.services.odds_provider.EventSettlement` values and go
    into :func:`~src.services.scoring.settle_gameweek` **unchanged**. That is the whole
    design: there is one scoring rule, and a hand-entered result and a provider-supplied
    one write byte-identical ``picks`` rows and award identical points. A second scoring
    path would be a second answer to "what did this pick score", and the failure mode is a
    leaderboard that disagrees with itself.

    Only *pending* picks are touched, because that is what ``settle_gameweek`` does. An
    already-scored pick is left alone, so this cannot silently rewrite a settled week; a
    genuine override means correcting the pick, which is a different act and is not this
    endpoint.

    Spends nothing upstream — the admin supplied the results — so it is not charged to the
    provider budget.
    """
    gameweek = (
        await db.execute(select(Gameweek).where(Gameweek.id == gameweek_id))
    ).scalar_one_or_none()
    if gameweek is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Round not found")
    if gameweek.status == GameweekStatus.settled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That round has already settled.",
        )

    wanted = {result.fixture_id for result in body.results}
    fixtures = (await db.execute(select(Fixture).where(Fixture.id.in_(wanted)))).scalars().all()
    event_ids = {fixture.id: fixture.provider_event_id for fixture in fixtures}
    missing = wanted - set(event_ids)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{len(missing)} fixture(s) not found",
        )

    settlements = []
    for result in body.results:
        provider_event_id = event_ids[result.fixture_id]
        if result.void:
            settlements.append(voided_settlement(provider_event_id))
            continue
        if result.home_goals is None or result.away_goals is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A result needs both scores, or void.",
            )
        settlements.append(
            settlement_from_score(provider_event_id, result.home_goals, result.away_goals)
        )

    resolved = await settle_gameweek(db, gameweek, settlements)
    # Re-read through the enum rather than off the attribute: the guard above narrowed
    # `gameweek.status` to "not settled", and `settle_gameweek` is exactly the call that
    # can have made it settled since.
    final_status = GameweekStatus(gameweek.status.value)
    db.add(
        _audit(
            admin,
            # No "results entered by hand" value exists and adding one is irreversible;
            # `league_updated` against the `gameweeks` table with an explicit note is the
            # nearest true thing, and the note is what a reader actually needs.
            ActionType.league_updated,
            "gameweeks",
            gameweek.id,
            {
                "action": "manual_settlement",
                "fixtures": len(settlements),
                "picks_resolved": resolved,
            },
        )
    )
    await db.commit()
    log.info(
        "round settled by hand",
        gameweek_id=str(gameweek_id),
        admin_id=str(admin.id),
        fixtures=len(settlements),
        picks_resolved=resolved,
        settled=final_status is GameweekStatus.settled,
    )
    return ManualResultsResponse(
        gameweek_id=str(gameweek_id),
        picks_resolved=resolved,
        settled=final_status is GameweekStatus.settled,
    )
