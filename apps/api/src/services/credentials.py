"""What happens to a member's sessions when their credential changes.

One module, because the rule is one rule. It had three callers: a member changing their
own PIN, a site admin resetting someone's, and a league admin doing the same. Batch 56
established it for the first — the old behaviour wrote the new hash and left every
existing refresh token renewing itself for thirty days, so the session the member was
trying to shut out outlived the credential it was opened with. An admin-issued reset is
the same act performed by somebody else and inherits the same rule; the second and third
callers were each written separately, and one of them forgot. Batch 179 retired the third
(the league admin's), so every reset now comes from the site console.

**And the member is told (Batch 179).** A reset opens a window in which anyone who names
the account can choose its PIN, and until this batch the member heard about neither the
reset nor the PIN being set — they found out when their PIN stopped working. Both now push
to the member's devices, and the app shows the last thirty days of them on its next load
with a session (:func:`recent_pin_events`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile
from src.models.refresh_token import RefreshToken
from src.services.push_notification_service import send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

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


# ── Telling the member (Batch 179) ─────────────────────────────────────────────

#: What a member's devices are told when a reset is issued. It asks them to act, because
#: the reset is a race: until the member chooses a PIN, whoever names the account first at
#: ``/auth/pin/set`` chooses it for them.
PIN_RESET_PUSH_TITLE = "Your PIN was reset"
PIN_RESET_PUSH_BODY = (
    "An admin cleared your PIN and signed you out. Sign in with your name to choose a new "
    "one — the reset lasts 24 hours."
)

#: What they are told when a PIN is set. The member who just chose it reads this as a
#: receipt; a member who did not is reading the only warning they will get.
PIN_SET_PUSH_TITLE = "A new PIN was set"
PIN_SET_PUSH_BODY = (
    "A new PIN was chosen for your account. If that wasn't you, use “Forgot PIN?” on "
    "the sign-in screen to ask an admin to reset it."
)

#: How far back the app's notice reads. Long enough to cover a member who does not open
#: the app for a few weeks, short enough that a new phone is not shown last season's reset.
PIN_EVENT_LOOKBACK = timedelta(days=30)

#: The most events the notice lists. A reset and a set are one journey; five journeys in
#: a month is already something the site admin should be asking about.
PIN_EVENT_LIMIT = 10


async def _push_to_member(
    db: AsyncSession, member: Profile, title: str, body: str, kind: str
) -> int:
    """Best-effort, like the lockout push: a delivery failure must not fail the reset or set
    it reports, which has already been committed by the time this runs."""
    try:
        return await send_notification(
            db,
            member.id,
            title,
            body,
            data={"type": kind, "url": "/login"},
            tag=kind.replace("_", "-"),
            timezone_name=member.timezone,
        )
    except Exception:  # Deliberately broad: the change stands whether or not this lands.
        log.warning("pin notification failed", kind=kind, user_id=str(member.id))
        return 0


async def notify_pin_reset(db: AsyncSession, member: Profile) -> int:
    """Push the member that their PIN was cleared. Returns how many devices were reached.

    Push subscriptions belong to the member, not to a session, so this reaches the very
    devices the reset just signed out.
    """
    return await _push_to_member(db, member, PIN_RESET_PUSH_TITLE, PIN_RESET_PUSH_BODY, "pin_reset")


async def notify_pin_set(db: AsyncSession, member: Profile) -> int:
    """Push the member that a PIN was chosen for them. Returns how many devices were reached."""
    return await _push_to_member(db, member, PIN_SET_PUSH_TITLE, PIN_SET_PUSH_BODY, "pin_set")


async def recent_pin_events(
    db: AsyncSession, member_id: uuid.UUID, now: datetime
) -> list[tuple[str, datetime]]:
    """This member's resets and PIN sets in the last :data:`PIN_EVENT_LOOKBACK`, newest first.

    Read from the audit rows the reset journey already writes, so there is nothing new to
    keep in step: a ``reset`` row for every reset (site console, and league admins before
    Batch 179) and a ``set`` row for every PIN chosen at ``/auth/pin/set``. The member's own
    ``requested`` rows are left out — they know they asked.

    Which of these a device has already shown is the *device's* to remember, not a row
    here. A marker on the account would be cleared by whoever signs in first, and after a
    takeover that is the attacker; remembered per device, the member's own phone still
    shows them everything the next time it is theirs again.
    """
    rows = await db.execute(
        select(AuditLog.changes, AuditLog.timestamp)
        .where(
            AuditLog.action_type == ActionType.player_pin_reset,
            AuditLog.target_table == "profiles",
            AuditLog.target_id == member_id,
            AuditLog.timestamp >= now - PIN_EVENT_LOOKBACK,
            AuditLog.changes["stage"].astext.in_([STAGE_RESET, STAGE_SET]),
        )
        .order_by(desc(AuditLog.timestamp))
        .limit(PIN_EVENT_LIMIT)
    )
    return [(changes["stage"], timestamp) for changes, timestamp in rows.all()]
