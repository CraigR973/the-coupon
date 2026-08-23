"""What happens to a member's sessions when their credential changes.

One module, because the rule is one rule and it has three callers: a member changing
their own PIN, a site admin resetting someone's, and a league admin doing the same.
Batch 56 established it for the first — the old behaviour wrote the new hash and left
every existing refresh token renewing itself for thirty days, so the session the member
was trying to shut out outlived the credential it was opened with. An admin-issued reset
is the same act performed by somebody else and inherits the same rule; the second and
third callers were each written separately, and one of them forgot.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile
from src.models.refresh_token import RefreshToken

#: How long a cleared credential stays claimable after the admin clears it.
#:
#: A profile with no PIN is claimable by whoever names it, because "no secret passes
#: through the admin" (owner, 2026-08-23) leaves no secret for the member to prove they
#: are the member. That is tolerable for as long as somebody is actually waiting on a
#: reset they asked for, and not tolerable indefinitely — an account left open for weeks
#: is one a display name is enough to take, and display names are on every leaderboard.
#:
#: Twenty-four hours, because the member has already asked (``pin/reset-request``) and is
#: waiting; past that the reset simply expires and they ask again, which now reaches a
#: real screen rather than a log line. See :func:`pin_reset_is_claimable`.
PIN_RESET_CLAIM_WINDOW = timedelta(hours=24)

#: Which half of the reset journey an audit row records. ``player_pin_reset`` covers
#: both because a new ``ActionType`` value cannot be undone — ``ALTER TYPE ... ADD
#: VALUE`` is irreversible and production has no restore point (owner's 2026-07-30
#: deferral) — so the stage is carried in ``changes`` instead. Batch 56 set the pattern
#: with ``"requested"``.
STAGE_REQUESTED = "requested"
STAGE_RESET = "reset"
STAGE_SET = "set"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def revoke_all_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every live refresh token for one member. Returns how many were revoked.

    The caller's own session goes with the rest. There is no way to spare it — a member
    authenticates with an *access* token, so the API never sees which refresh token
    belongs to this device, and guessing by ``device_hint`` would spare an attacker who
    copied the User-Agent. Losing the current session is the right trade anyway: the
    client clears its tokens on the next failed refresh and asks for the new PIN
    (``lib/api.ts`` already redirects to /login when a refresh 401s), which is exactly
    what should happen after a credential changes.

    Flushes nothing and commits nothing — the caller owns the transaction.
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    return result.rowcount or 0


async def clear_pin(db: AsyncSession, target: Profile) -> int:
    """Take away a member's credential entirely. Returns the sessions revoked.

    The whole of what an admin PIN reset does, so the two admin surfaces cannot drift
    apart. Three things, and all three are load-bearing:

    * ``pin_hash`` becomes ``NULL``. No temporary PIN is minted (owner, 2026-08-23):
      a temporary PIN is a secret that passes through the admin, can be written down,
      shared, and reused, and the member ends up with a credential somebody else chose.
      Clearing leaves nothing to leak, and the existing charset rules — including
      :func:`~src.auth.is_weak_pin` — apply at the point the member sets their own.
    * every refresh token is revoked, or the sessions opened under the old PIN outlive
      it, which is the defect Batch 56 fixed for the member's own change;
    * the lockout is cleared, because the member is about to be asked for a credential
      that does not exist yet and counting their attempts against it is nonsense.

    Commits nothing.
    """
    target.pin_hash = None
    revoked = await revoke_all_refresh_tokens(db, target.id)
    target.failed_login_count = 0
    target.locked_until = None
    target.updated_at = _now()
    return revoked


def pin_reset_audit(
    actor: Profile, target: Profile, stage: str, extra: dict[str, str] | None = None
) -> AuditLog:
    """One row of the reset journey, in the shape Batch 56 established."""
    changes: dict[str, str] = {"stage": stage, "display_name": target.display_name}
    if extra:
        changes.update(extra)
    return AuditLog(
        actor_id=actor.id,
        actor_type=ActorType.admin if actor.id != target.id else ActorType.player,
        action_type=ActionType.player_pin_reset,
        target_table="profiles",
        target_id=target.id,
        changes=changes,
    )


async def pin_reset_is_claimable(db: AsyncSession, target: Profile, now: datetime) -> bool:
    """True when this credential-less profile may still have a PIN set on it.

    The bound on :data:`PIN_RESET_CLAIM_WINDOW`, read from the audit row the reset
    already writes rather than from a column of its own — there is exactly one state
    being tracked here and ``pin_hash IS NULL`` already carries it, so a second column
    would be a second thing to keep in step.

    The newest ``player_pin_reset`` row for this member decides. It has to be the newest
    rather than "any recent one", because ``pin/reset-request`` writes the same action
    type at stage ``requested`` (Batch 56, for the same irreversible-enum reason), and a
    member asking again must not re-open a window an admin has not re-opened.
    """
    newest = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.action_type == ActionType.player_pin_reset,
                AuditLog.target_table == "profiles",
                AuditLog.target_id == target.id,
            )
            .order_by(desc(AuditLog.timestamp))
            .limit(1)
        )
    ).scalar_one_or_none()
    if newest is None or not isinstance(newest.changes, dict):
        return False
    if newest.changes.get("stage") != STAGE_RESET:
        return False
    return now - newest.timestamp <= PIN_RESET_CLAIM_WINDOW
