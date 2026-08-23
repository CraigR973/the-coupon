"""The site admin's people console: members, invites, and every league.

Batch 66, and the reason it exists is a journey that stopped halfway. Batch 56 made
``/auth/pin/reset-request`` truthful — it had promised "an admin will be notified" and
notified nobody, and it now writes an audit row and pushes every active site admin. The
notification was real and **the action behind it did not exist**: the push sent the admin
to their own settings page because there was nowhere else to send them, and exactly one
endpoint in the whole API used the ``AdminUser`` dependency (avatar removal). A member
who forgot four digits was a lost account.

Scope is people and access only. The operational half — dashboard, manual sync, manual
results — is Batch 69, and nothing here triggers a job or spends a provider request.

Everything on this router is refused to a non-admin by :data:`~src.auth.AdminUser`, which
is a dependency rather than a check inside each handler so a new route cannot be added
without one.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Subquery

from src.auth import AdminUser, generate_join_code
from src.database import get_db
from src.models.invite import Invite
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile
from src.rate_limit import limiter, per_user_key
from src.schemas import UtcDatetime
from src.services.credentials import (
    STAGE_RESET,
    clear_pin,
    pin_reset_audit,
    revoke_all_refresh_tokens,
)

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
