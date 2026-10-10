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
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
import structlog
from pywebpush import WebPushException, webpush  # type: ignore[import-untyped,unused-ignore]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.league_membership import LeagueMembership
from src.models.notification import MemberNotification, NotificationPreferences, PushSubscription

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_FAIL_THRESHOLD = 3

#: How long one push may take, in seconds (Batch 142). ``webpush()`` has no bound of its
#: own — pywebpush hands ``timeout=None`` straight to ``requests`` — so a push service that
#: accepted the connection and never answered held this send, and every send queued behind
#: it, for as long as it chose. Healthy services answer in well under a second; five is
#: generous to them and still bounds the rest.
PUSH_SEND_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class PreparedPush:
    """One copied subscription and payload, safe to carry outside a DB session."""

    subscription_id: UUID
    user_id: UUID
    endpoint: str
    keys: tuple[tuple[str, str], ...]
    payload: str


@dataclass(frozen=True)
class PreparedNotification:
    """All subscription sends for one member, prepared in the read transaction."""

    pushes: tuple[PreparedPush, ...]
    attempted_at: datetime


@dataclass(frozen=True)
class NotificationIntent:
    """One trigger call captured before its policy and subscriptions are read in bulk."""

    user_id: UUID
    payload: str
    title: str
    body: str
    data: dict[str, Any] | None
    timezone_name: str
    now: datetime
    league_id: UUID | None


@dataclass(frozen=True)
class PushDeliveryOutcome:
    """The session-free result later written in one short transaction."""

    subscription_id: UUID
    status: Literal["sent", "failed", "timeout", "unexpected"]


@dataclass(frozen=True)
class PushDeliveryReport:
    outcomes: tuple[PushDeliveryOutcome, ...]
    attempted_at: datetime

    @property
    def sent(self) -> int:
        return sum(outcome.status == "sent" for outcome in self.outcomes)


_notification_intents: ContextVar[list[NotificationIntent] | None] = ContextVar(
    "prepared_notifications", default=None
)

# Every league-scoped member event has one inbox category. Admin, account and test
# pushes have no league history. Quiet hours affect delivery, not this durable copy.
INBOX_KIND_CATEGORY = {
    "pick_made": "pick_activity",
    "pick_changed": "pick_activity",
    "all_picked": "pick_activity",
    "picks_open": "round_updates",
    "pick_reminder": "round_updates",
    "fixture_postponed": "round_updates",
    "round_settled": "results",
    "result_corrected": "results",
}


def _inbox_details(data: dict[str, Any] | None, league_id: UUID | None) -> tuple[str, str] | None:
    if league_id is None or data is None:
        return None
    kind = data.get("type")
    url = data.get("url")
    if not isinstance(kind, str) or kind not in INBOX_KIND_CATEGORY:
        return None
    if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
        return None
    return kind, url


def _category_muted(prefs: NotificationPreferences | None, category: str) -> bool:
    if prefs is None:
        return False
    return bool(
        (category == "pick_activity" and prefs.mute_pick_activity)
        or (category == "round_updates" and prefs.mute_round_updates)
        or (category == "results" and prefs.mute_results)
    )


def muted_inbox_kinds(prefs: NotificationPreferences | None) -> tuple[str, ...]:
    """Hide already-recorded events while a member mutes their category."""
    return tuple(
        kind for kind, category in INBOX_KIND_CATEGORY.items() if _category_muted(prefs, category)
    )


def _record_inbox(
    session: AsyncSession,
    *,
    user_id: UUID,
    league_id: UUID,
    kind: str,
    title: str,
    body: str,
    url: str,
    now: datetime,
) -> None:
    session.add(
        MemberNotification(
            user_id=user_id,
            league_id=league_id,
            kind=kind,
            title=title,
            body=body,
            url=url,
            created_at=now,
        )
    )


@contextmanager
def collect_notification_intents() -> Iterator[list[NotificationIntent]]:
    """Turn ``send_notification`` calls into immutable plans for this task.

    Notification triggers keep one source for recipients, copy and mute semantics. The
    pick path runs those same triggers inside this collector, commits and closes the read
    session, then delivers the returned plans without a database connection.
    """
    collected: list[NotificationIntent] = []
    token = _notification_intents.set(collected)
    try:
        yield collected
    finally:
        _notification_intents.reset(token)


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
        timeout=PUSH_SEND_TIMEOUT_SECONDS,
    )


def _payload_json(
    title: str,
    body: str,
    data: dict[str, Any] | None,
    tag: str | None,
) -> str:
    payload_obj: dict[str, Any] = {"title": title, "body": body, "data": data or {}}
    if tag is not None:
        payload_obj["tag"] = tag
    return json.dumps(payload_obj)


def _prepared_pushes(
    *,
    user_id: UUID,
    payload: str,
    subscriptions: Sequence[PushSubscription],
) -> tuple[PreparedPush, ...]:
    return tuple(
        PreparedPush(
            subscription_id=sub.id,
            user_id=user_id,
            endpoint=str(sub.subscription.get("endpoint", "")),
            keys=tuple(
                sorted(
                    (str(key), str(value))
                    for key, value in sub.subscription.get("keys", {}).items()
                )
            ),
            payload=payload,
        )
        for sub in subscriptions
    )


async def _prepare_notification(
    session: AsyncSession,
    user_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    tag: str | None = None,
    timezone_name: str = "UTC",
    now_utc: datetime | None = None,
    league_id: UUID | None = None,
) -> tuple[PreparedNotification, list[PushSubscription]]:
    """Read delivery policy and copy subscriptions into a session-free plan."""
    now = now_utc.replace(tzinfo=None) if now_utc is not None else _utc_now()
    empty = PreparedNotification(pushes=(), attempted_at=now)

    inbox = _inbox_details(data, league_id)
    if inbox is None and (not settings.vapid_private_key or not settings.vapid_public_key):
        log.debug("VAPID keys not configured — skipping push", user_id=str(user_id))
        return empty, []

    local_current = _local_now(timezone_name, now)

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
            return empty, []

    prefs_result = await session.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()

    if prefs is not None and prefs.global_mute:
        log.debug("notification suppressed by preferences", user_id=str(user_id))
        return empty, []

    if inbox is not None:
        kind, url = inbox
        if _category_muted(prefs, INBOX_KIND_CATEGORY[kind]):
            return empty, []
        assert league_id is not None
        _record_inbox(
            session,
            user_id=user_id,
            league_id=league_id,
            kind=kind,
            title=title,
            body=body,
            url=url,
            now=now,
        )

    if (prefs is not None and _is_quiet(prefs, local_current)) or not (
        settings.vapid_private_key and settings.vapid_public_key
    ):
        return empty, []

    subs_result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.is_active.is_(True),
        )
    )
    subscriptions = list(subs_result.scalars().all())
    if not subscriptions:
        return empty, []

    pushes = _prepared_pushes(
        user_id=user_id,
        payload=_payload_json(title, body, data, tag),
        subscriptions=subscriptions,
    )
    return PreparedNotification(pushes=pushes, attempted_at=now), subscriptions


async def prepare_collected_notifications(
    session: AsyncSession,
    intents: Sequence[NotificationIntent],
) -> tuple[PreparedNotification, ...]:
    """Resolve a trigger's audience policy and subscriptions in three bulk reads."""
    if not intents:
        return ()

    push_configured = bool(settings.vapid_private_key and settings.vapid_public_key)

    user_ids = {intent.user_id for intent in intents}
    league_ids = {intent.league_id for intent in intents if intent.league_id is not None}

    muted_pairs: set[tuple[UUID, UUID]] = set()
    if league_ids:
        muted_rows = await session.execute(
            select(LeagueMembership.league_id, LeagueMembership.player_id).where(
                LeagueMembership.league_id.in_(league_ids),
                LeagueMembership.player_id.in_(user_ids),
                LeagueMembership.deleted_at.is_(None),
                LeagueMembership.notification_muted.is_(True),
            )
        )
        muted_pairs = {(row.league_id, row.player_id) for row in muted_rows.all()}

    preferences = {
        prefs.user_id: prefs
        for prefs in (
            (
                await session.execute(
                    select(NotificationPreferences).where(
                        NotificationPreferences.user_id.in_(user_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
    }
    subscriptions_by_user: dict[UUID, list[PushSubscription]] = {}
    if push_configured:
        subscriptions = (
            (
                await session.execute(
                    select(PushSubscription).where(
                        PushSubscription.user_id.in_(user_ids),
                        PushSubscription.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for subscription in subscriptions:
            subscriptions_by_user.setdefault(subscription.user_id, []).append(subscription)

    plans: list[PreparedNotification] = []
    for intent in intents:
        if intent.league_id is not None and (intent.league_id, intent.user_id) in muted_pairs:
            continue
        prefs = preferences.get(intent.user_id)
        local_current = _local_now(intent.timezone_name, intent.now)
        if prefs is not None and prefs.global_mute:
            continue
        inbox = _inbox_details(intent.data, intent.league_id)
        if inbox is not None:
            kind, url = inbox
            if _category_muted(prefs, INBOX_KIND_CATEGORY[kind]):
                continue
            assert intent.league_id is not None
            _record_inbox(
                session,
                user_id=intent.user_id,
                league_id=intent.league_id,
                kind=kind,
                title=intent.title,
                body=intent.body,
                url=url,
                now=intent.now,
            )
        if (prefs is not None and _is_quiet(prefs, local_current)) or not push_configured:
            continue
        member_subscriptions = subscriptions_by_user.get(intent.user_id, [])
        if not member_subscriptions:
            continue
        plans.append(
            PreparedNotification(
                pushes=_prepared_pushes(
                    user_id=intent.user_id,
                    payload=intent.payload,
                    subscriptions=member_subscriptions,
                ),
                attempted_at=intent.now,
            )
        )
    return tuple(plans)


async def deliver_prepared_notification(plan: PreparedNotification) -> PushDeliveryReport:
    """Deliver a copied plan without touching a session or the connection pool."""
    outcomes: list[PushDeliveryOutcome] = []
    loop = asyncio.get_running_loop()
    for push in plan.pushes:
        subscription_data: dict[str, Any] = {
            "endpoint": push.endpoint,
            "keys": dict(push.keys),
        }
        try:
            await loop.run_in_executor(
                None, partial(_send_push_sync, subscription_data, push.payload)
            )
            status: Literal["sent", "failed", "timeout", "unexpected"] = "sent"
        except WebPushException as exc:
            status = "failed"
            log.warning(
                "push send failed",
                user_id=str(push.user_id),
                subscription_id=str(push.subscription_id),
                error=str(exc),
            )
        except requests.exceptions.Timeout:
            status = "timeout"
            log.warning(
                "push send timed out",
                user_id=str(push.user_id),
                subscription_id=str(push.subscription_id),
                timeout_s=PUSH_SEND_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            status = "unexpected"
            log.error("unexpected push error", error=str(exc))
        outcomes.append(PushDeliveryOutcome(subscription_id=push.subscription_id, status=status))
    return PushDeliveryReport(outcomes=tuple(outcomes), attempted_at=plan.attempted_at)


def _apply_delivery_outcomes(
    subscriptions: Sequence[PushSubscription],
    reports: Sequence[PushDeliveryReport],
) -> None:
    by_id = {subscription.id: subscription for subscription in subscriptions}
    for report in reports:
        for outcome in report.outcomes:
            subscription = by_id.get(outcome.subscription_id)
            if subscription is None:
                continue
            if outcome.status == "sent":
                subscription.failed_send_count = 0
                subscription.last_used_at = report.attempted_at
            elif outcome.status == "failed":
                subscription.failed_send_count = (subscription.failed_send_count or 0) + 1
                if subscription.failed_send_count >= _FAIL_THRESHOLD:
                    subscription.is_active = False
                    log.info(
                        "push subscription auto-disabled",
                        subscription_id=str(subscription.id),
                        fail_count=subscription.failed_send_count,
                    )


async def record_notification_outcomes(
    session: AsyncSession,
    reports: Sequence[PushDeliveryReport],
) -> None:
    """Persist copied delivery results after sending, under short row locks."""
    subscription_ids = {
        outcome.subscription_id for report in reports for outcome in report.outcomes
    }
    if not subscription_ids:
        return
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.id.in_(subscription_ids)).with_for_update()
    )
    _apply_delivery_outcomes(list(result.scalars().all()), reports)


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
    collector = _notification_intents.get()
    if collector is not None:
        now = now_utc.replace(tzinfo=None) if now_utc is not None else _utc_now()
        collector.append(
            NotificationIntent(
                user_id=user_id,
                payload=_payload_json(title, body, data, tag),
                title=title,
                body=body,
                data=data,
                timezone_name=timezone_name,
                now=now,
                league_id=league_id,
            )
        )
        return 0

    plan, subscriptions = await _prepare_notification(
        session,
        user_id,
        title,
        body,
        data=data,
        tag=tag,
        timezone_name=timezone_name,
        now_utc=now_utc,
        league_id=league_id,
    )
    report = await deliver_prepared_notification(plan)
    _apply_delivery_outcomes(subscriptions, [report])
    return report.sent
