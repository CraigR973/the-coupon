"""Web Push delivery service.

send_notification() is the single entry point for all push delivery.
It respects preferences (global_mute, quiet hours), calls pywebpush for each
active PushSubscription, and auto-disables subscriptions that accumulate
3 consecutive send failures.

Since Batch 76 it also respects the **per-league** mute, when the caller says which
league the message is about. That column has existed on ``league_memberships`` since
Batch 32 and until now only one query honoured it, which meant a member who muted a
league still got its postponement alerts. See ``league_id`` below.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from functools import partial
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from pywebpush import WebPushException, webpush  # type: ignore[import-untyped,unused-ignore]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.league_membership import LeagueMembership
from src.models.notification import NotificationPreferences, PushSubscription

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_FAIL_THRESHOLD = 3


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _local_now(timezone_name: str, now_utc: datetime | None = None) -> datetime:
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    return now.astimezone(timezone).replace(tzinfo=None)


def _is_quiet(prefs: NotificationPreferences, now: datetime) -> bool:
    """Return True if local now falls within the configured quiet hours."""
    if prefs.quiet_hours_start is None or prefs.quiet_hours_end is None:
        return False
    start = prefs.quiet_hours_start.time()
    end = prefs.quiet_hours_end.time()
    t = now.time()
    if start <= end:
        return start <= t < end
    # Overnight window (e.g. 23:00 – 07:00)
    return t >= start or t < end


def _send_push_sync(subscription_data: dict[str, Any], payload: str) -> None:
    """Blocking push send — run in a thread executor."""
    webpush(
        subscription_info=subscription_data,
        data=payload,
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": f"mailto:{settings.vapid_contact_email}"},
        content_encoding="aes128gcm",
    )


async def send_notification(
    session: AsyncSession,
    user_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    tag: str | None = None,
    timezone_name: str = "UTC",
    now_utc: datetime | None = None,
    league_id: UUID | None = None,
) -> int:
    """Deliver a push notification to all active subscriptions for user_id.

    Returns the count of successfully sent pushes. Skips delivery when
    preferences block it. Auto-disables subscriptions after _FAIL_THRESHOLD
    consecutive failures.

    ``league_id`` names the league the message is *about*, and gates it on that
    membership's ``notification_muted``. Batch 76 added it, and the gap it closes is
    older than that: the column has been on ``league_memberships`` since Batch 32, but
    the only code reading it was a ``WHERE`` clause inside ``members_missing_picks``.
    This function took a ``user_id`` and no league, so it *could not* check — which is
    why ``fixture_postponed`` notified members who had muted the league it was about.

    It matters more now than it did. Batch 76 stacks two high-volume triggers on top of
    this, the owner has declined a separate opt-out for them, and so this column is a
    member's only recourse against the volume.

    **A missing membership row does not suppress.** The gate fires only on an explicit
    ``notification_muted = True``, so this is purely additive: no message that goes out
    today stops going out because a row could not be found. The callers already restrict
    themselves to active members, and a member who has left a league mid-round should
    still be told their pick was returned.
    """
    if not settings.vapid_private_key or not settings.vapid_public_key:
        log.debug("VAPID keys not configured — skipping push", user_id=str(user_id))
        return 0

    now = now_utc.replace(tzinfo=None) if now_utc is not None else _utc_now()
    local_current = _local_now(timezone_name, now)

    # ── Check the per-league mute ─────────────────────────────────────────────
    # Before the global preferences, because it is the more specific opt-out and answers
    # from one indexed row. A caller that passes no `league_id` is saying the message is
    # not about a league — an admin alert, say — and there is nothing to check.
    if league_id is not None:
        muted = await session.execute(
            select(LeagueMembership.notification_muted).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.player_id == user_id,
                LeagueMembership.deleted_at.is_(None),
            )
        )
        if muted.scalar_one_or_none() is True:
            log.debug(
                "notification suppressed by league mute",
                user_id=str(user_id),
                league_id=str(league_id),
            )
            return 0

    # ── Check preferences ─────────────────────────────────────────────────────
    prefs_result = await session.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()

    suppressed = False
    if prefs is not None:
        suppressed = prefs.global_mute or _is_quiet(prefs, local_current)

    if suppressed:
        log.debug("notification suppressed by preferences", user_id=str(user_id))
        return 0

    # ── Fetch active subscriptions ────────────────────────────────────────────
    subs_result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.is_active.is_(True),
        )
    )
    subscriptions = list(subs_result.scalars().all())

    if not subscriptions:
        return 0

    payload_obj: dict[str, Any] = {"title": title, "body": body, "data": data or {}}
    if tag is not None:
        payload_obj["tag"] = tag
    payload = json.dumps(payload_obj)
    sent = 0

    loop = asyncio.get_event_loop()
    for sub in subscriptions:
        sub_info: dict[str, Any] = {
            "endpoint": sub.subscription.get("endpoint", ""),
            "keys": sub.subscription.get("keys", {}),
        }
        try:
            await loop.run_in_executor(None, partial(_send_push_sync, sub_info, payload))
            sub.failed_send_count = 0
            sub.last_used_at = now
            sent += 1
        except WebPushException as exc:
            log.warning(
                "push send failed",
                user_id=str(user_id),
                subscription_id=str(sub.id),
                error=str(exc),
            )
            sub.failed_send_count = (sub.failed_send_count or 0) + 1
            if sub.failed_send_count >= _FAIL_THRESHOLD:
                sub.is_active = False
                log.info(
                    "push subscription auto-disabled",
                    subscription_id=str(sub.id),
                    fail_count=sub.failed_send_count,
                )
        except Exception as exc:
            log.error("unexpected push error", error=str(exc))

    return sent
