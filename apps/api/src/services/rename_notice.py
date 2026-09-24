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

**Identified by profile id, not by name (Batch 155).** This module used to carry all six
names, old and new. The repository is public and a display name is half of a member's
sign-in, so the names were replaced with the three profile ids, read from production on
2026-09-24. An id also cannot drift the way a name can: a member renamed again since is
still found. The copy names the sign-in name the profile holds *now* and says the old one
has gone rather than quoting it, because the old names are no longer anywhere this code
can read them.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile
from src.services.push_notification_service import send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: The three profiles Batch 74 renamed on 2026-08-26 — the owner and two members — by id.
#: Read from production, read-only, on 2026-09-24. An id resolves to a name only for a
#: member of the same league (``routers/players.py``), so publishing these re-identifies
#: nobody to a stranger.
RENAMED_PROFILE_IDS: tuple[uuid.UUID, ...] = (
    uuid.UUID("18963be2-8d47-484a-92f1-d657acd01e0d"),
    uuid.UUID("bd669741-8811-45d3-a204-45de344bbfe7"),
    uuid.UUID("39faae39-29a9-4c47-8905-109b2773f31b"),
)

NOTICE_TITLE = "Your sign-in name changed"

#: Serialises the whole task across processes. Railway is pinned to one replica and Batch
#: 100 refuses to migrate above one, but neither guards a *lifespan* hook, and two
#: containers booting together would otherwise both read "no marker" and both push. A
#: transaction-scoped advisory lock makes the second one wait and then see the first one's
#: row. Arbitrary constant; it only has to be unique among this app's advisory locks.
_ADVISORY_LOCK_KEY = 930074


def notice_body(display_name: str) -> str:
    """The copy. Names the sign-in name to use, and says the old one no longer works."""
    return (
        f'Sign in as "{display_name}" from now on. '
        "Your old sign-in name no longer works, and a forgotten-PIN "
        "request needs the new one. Your PIN itself has not changed."
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


async def _find_profile(session: AsyncSession, profile_id: uuid.UUID) -> Profile | None:
    result = await session.execute(
        select(Profile).where(Profile.id == profile_id, Profile.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def send_rename_notices(session: AsyncSession) -> dict[str, int]:
    """Notify any of the three who has not yet been reached. Returns pushes sent, by id.

    An id absent from the database is absent from the result — that is the normal answer
    everywhere except production, and the reason this is safe to run on every boot in every
    environment.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})

    sent_by_id: dict[str, int] = {}
    for profile_id in RENAMED_PROFILE_IDS:
        profile = await _find_profile(session, profile_id)
        if profile is None:
            continue
        if await _already_told(session, profile.id):
            continue

        sent = await send_notification(
            session,
            profile.id,
            NOTICE_TITLE,
            notice_body(profile.display_name),
            data={"type": "display_name_changed", "url": "/settings"},
            timezone_name=profile.timezone,
        )
        sent_by_id[str(profile.id)] = sent
        if sent == 0:
            # Unreachable right now — no active subscription, muted, or inside quiet
            # hours. Leaving the marker unwritten is deliberate: they have not been told.
            log.info("rename notice undelivered, will retry next boot", player_id=str(profile.id))
            continue

        session.add(
            AuditLog(
                actor_id=None,
                actor_type=ActorType.system,
                action_type=ActionType.display_name_changed,
                target_table="profiles",
                target_id=profile.id,
                # The name they were told to sign in as. The old one is not recorded: it is
                # no longer anywhere this code can read it (Batch 155).
                changes={"new": profile.display_name, "pushes": sent},
            )
        )
        log.info("rename notice delivered", player_id=str(profile.id), pushes=sent)

    return sent_by_id
