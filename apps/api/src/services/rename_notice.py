"""Batch 93 — tell the three members Batch 74 renamed that their sign-in name changed.

Batch 74 rewrote three ``profiles.display_name`` values on 2026-08-26. That column is the
login identifier (``routers/auth.py`` matches it exactly), so the rename changed how those
three people sign in — but nobody was signed out, because the JWT subject is the player id.
The consequence is a delayed surprise: the next session expiry or forgotten-PIN request
fails for a reason that arrives days later and looks unrelated. Nothing in the product
tells them. This does, once.

**Why a boot task and not a migration.** Delivery is web push, which means an HTTP call per
subscription; a migration runs synchronous SQL and cannot make it. So the trigger is the
one other thing that happens exactly on a deploy — application startup — and the
idempotency Alembic would have given for free is rebuilt here out of an ``audit_log`` row,
the same way Batch 101 made its alert cooldown survive a redeploy.

**What "once" means here.** The marker row is written only when a push was actually
delivered. A member with no active subscription, or one who is muted or inside quiet
hours, has not been told anything, so the next boot tries again — that is the behaviour the
requirement asks for, not a violation of it. It also means this task keeps running until
all three are reached, which is why it is cheap: three indexed lookups against
``audit_log`` and ``profiles``.

**Expected lifetime.** This is a one-off for three already-affected accounts, not a
"display name changed" feature — renaming a fourth member would need its own decision about
notifying them. Once production holds three ``display_name_changed`` rows, the call in
``main.lifespan`` and this module can go.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile
from src.services.push_notification_service import send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RenamedMember:
    """One rename Batch 74 applied, as recorded in the backfill note."""

    old_name: str
    new_name: str


#: The three renames, from ``docs/backfills/2026-08-names-and-numbers.md``. Identified by
#: the *new* name because that is what the row holds now; the old one is only copy. No
#: profile ids were recorded in the backfill note, and names are what it can be matched on.
RENAMED_MEMBERS: tuple[RenamedMember, ...] = (
    RenamedMember(old_name="Craig", new_name="Craig Robinson"),
    RenamedMember(old_name="Birch", new_name="Marc Birch"),
    RenamedMember(old_name="Lewis", new_name="Lewis Steele"),
)

NOTICE_TITLE = "Your sign-in name changed"

#: Serialises the whole task across processes. Railway is pinned to one replica and Batch
#: 100 refuses to migrate above one, but neither guards a *lifespan* hook, and two
#: containers booting together would otherwise both read "no marker" and both push. A
#: transaction-scoped advisory lock makes the second one wait and then see the first one's
#: row. Arbitrary constant; it only has to be unique among this app's advisory locks.
_ADVISORY_LOCK_KEY = 930074


def notice_body(member: RenamedMember) -> str:
    """The copy. Names both halves — the old name is what they will try first."""
    return (
        f'Sign in as "{member.new_name}" from now on. '
        f'Your old name "{member.old_name}" no longer works, and a forgotten-PIN '
        f"request needs the new one. Your PIN itself has not changed."
    )


async def _already_told(session: AsyncSession, profile_id: object) -> bool:
    result = await session.execute(
        select(AuditLog.id)
        .where(
            AuditLog.action_type == ActionType.display_name_changed,
            AuditLog.target_table == "profiles",
            AuditLog.target_id == profile_id,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _find_profile(session: AsyncSession, new_name: str) -> Profile | None:
    """Match case-insensitively — migration 017 made display names CI-unique."""
    result = await session.execute(
        select(Profile).where(
            func.lower(Profile.display_name) == new_name.lower(),
            Profile.deleted_at.is_(None),
        )
    )
    return result.scalars().first()


async def send_rename_notices(session: AsyncSession) -> dict[str, int]:
    """Notify any of the three who has not yet been reached. Returns pushes sent, by name.

    A name absent from the database is absent from the result — that is the normal answer
    everywhere except production, and the reason this is safe to run on every boot in every
    environment.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})

    sent_by_name: dict[str, int] = {}
    for member in RENAMED_MEMBERS:
        profile = await _find_profile(session, member.new_name)
        if profile is None:
            continue
        if await _already_told(session, profile.id):
            continue

        sent = await send_notification(
            session,
            profile.id,
            NOTICE_TITLE,
            notice_body(member),
            data={"type": "display_name_changed", "url": "/settings"},
            timezone_name=profile.timezone,
        )
        sent_by_name[member.new_name] = sent
        if sent == 0:
            # Unreachable right now — no active subscription, muted, or inside quiet
            # hours. Leaving the marker unwritten is deliberate: they have not been told.
            log.info(
                "rename notice undelivered, will retry next boot",
                display_name=member.new_name,
            )
            continue

        session.add(
            AuditLog(
                actor_id=None,
                actor_type=ActorType.system,
                action_type=ActionType.display_name_changed,
                target_table="profiles",
                target_id=profile.id,
                changes={"old": member.old_name, "new": member.new_name, "pushes": sent},
            )
        )
        log.info("rename notice delivered", display_name=member.new_name, pushes=sent)

    return sent_by_name
