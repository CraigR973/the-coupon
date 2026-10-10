"""Push subscription and notification preference endpoints."""

import ipaddress
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.auth import CurrentUser
from src.config import settings
from src.database import get_db
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import MemberNotification, NotificationPreferences, PushSubscription
from src.rate_limit import limiter, per_user_key
from src.schemas import UtcDatetime
from src.services.push_notification_service import muted_inbox_kinds, send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["notifications"])

Db = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────


#: The push services a real browser subscription can name. Delivery POSTs to this
#: host server-side (``pywebpush``), so an unchecked endpoint is an SSRF primitive with
#: an attacker-chosen destination — hence an allowlist rather than a denylist.
ALLOWED_PUSH_HOSTS = frozenset(
    {
        "fcm.googleapis.com",  # Chrome, Edge, and every other Chromium browser
        "updates.push.services.mozilla.com",  # Firefox
        "web.push.apple.com",  # Safari
    }
)

#: Windows/WNS shards the host per-datacentre, so this one is a suffix match.
ALLOWED_PUSH_HOST_SUFFIXES = (".notify.windows.com",)


def _is_internal_host(host: str) -> bool:
    """True if ``host`` is an IP literal pointing somewhere inside our own network.

    Belt-and-braces behind the allowlist: no private address can also be an allowed
    push host, but the check is cheap and keeps the refusal reason honest.
    """
    try:
        ip = ipaddress.ip_address(host)  # ``hostname`` has already unwrapped [v6]
    except ValueError:
        return False  # a name, not a literal — the allowlist is what governs it
    # ``::ffff:127.0.0.1`` is loopback wearing an IPv6 coat; unwrap before judging.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private  # 10/8, 172.16/12, 192.168/16, fc00::/7
        or ip.is_loopback  # 127/8, ::1
        or ip.is_link_local  # 169.254/16, fe80::/10
        or ip.is_reserved
        or ip.is_unspecified  # 0.0.0.0, ::
    )


def _validate_push_endpoint(value: str) -> str:
    """Reject any endpoint a genuine browser subscription could not have produced."""
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise ValueError("Push endpoint must use https")

    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("Push endpoint must name a host")

    if _is_internal_host(host):
        raise ValueError("Push endpoint must not name an internal address")

    if host not in ALLOWED_PUSH_HOSTS and not host.endswith(ALLOWED_PUSH_HOST_SUFFIXES):
        raise ValueError("Push endpoint is not a recognised push service")

    # Batch 142. The allowlist names hosts, not ports, so without this an allowlisted host
    # could be aimed at any other service it runs. Every real push service is on 443.
    if parts.port not in (None, 443):
        raise ValueError("Push endpoint must use the standard HTTPS port")

    return value


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: dict[str, str]
    device_hint: str | None = None

    @field_validator("endpoint")
    @classmethod
    def _check_endpoint(cls, value: str) -> str:
        return _validate_push_endpoint(value)


class UnsubscribeRequest(BaseModel):
    endpoint: str


class LeagueMuteOut(BaseModel):
    league_id: str
    league_name: str
    muted: bool


class PreferencesOut(BaseModel):
    global_mute: bool
    mute_pick_activity: bool
    mute_round_updates: bool
    mute_results: bool
    quiet_hours_start: str | None  # "HH:MM"
    quiet_hours_end: str | None  # "HH:MM"
    leagues: list[LeagueMuteOut]


class PreferencesPatch(BaseModel):
    global_mute: bool | None = None
    mute_pick_activity: bool | None = None
    mute_round_updates: bool | None = None
    mute_results: bool | None = None
    quiet_hours_start: str | None = None  # "HH:MM" or empty string to clear
    quiet_hours_end: str | None = None
    #: league_id -> desired mute state. Only the leagues named here are touched.
    league_mutes: dict[str, bool] | None = None


class InboxItem(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    kind: str
    title: str
    body: str
    url: str
    created_at: UtcDatetime
    read_at: UtcDatetime | None


class InboxOut(BaseModel):
    items: list[InboxItem]
    unread_count: int


# ── VAPID public key ─────────────────────────────────────��────────────────────


@router.get("/push/vapid-public-key")
async def get_vapid_public_key() -> dict[str, str]:
    """Return the VAPID public key for client-side push subscription."""
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push not configured",
        )
    return {"vapid_public_key": settings.vapid_public_key}


# ── Push subscription management ──────────────────────────────────────────────


@router.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: SubscribeRequest,
    user: CurrentUser,
    db: Db,
) -> dict[str, str]:
    """Store a new push subscription for the authenticated user."""
    subscription_data: dict[str, Any] = {"endpoint": body.endpoint, "keys": body.keys}

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.subscription["endpoint"].astext == body.endpoint,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.subscription = subscription_data
        existing.is_active = True
        existing.failed_send_count = 0
        if body.device_hint:
            existing.device_hint = body.device_hint
    else:
        db.add(
            PushSubscription(
                user_id=user.id,
                subscription=subscription_data,
                device_hint=body.device_hint,
            )
        )

    await db.commit()
    log.info("push subscription stored", user_id=str(user.id))
    return {"status": "subscribed"}


@router.delete("/push/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe_push(
    body: UnsubscribeRequest,
    user: CurrentUser,
    db: Db,
) -> dict[str, str]:
    """Deactivate a push subscription by endpoint."""
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.subscription["endpoint"].astext == body.endpoint,
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.is_active = False
        await db.commit()
    return {"status": "unsubscribed"}


# ── Test push ────────────────────────────────────────────────────────────────


@router.post("/push/test", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour", key_func=per_user_key)
async def test_push(request: Request, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Send a test push notification to the authenticated user."""
    sent = await send_notification(
        session=db,
        user_id=user.id,
        title="The Coupon — test",
        body="Push notifications are working!",
        data={"url": "/"},
    )
    await db.commit()
    return {"sent": sent}


# ── Notification preferences ──────────────────────────────────────────────────


async def _visible_inbox_filters(
    db: AsyncSession, user_id: uuid.UUID, cutoff: datetime
) -> list[ColumnElement[bool]]:
    """Apply the current mutes to both the list and its unread count."""
    filters: list[ColumnElement[bool]] = [
        MemberNotification.user_id == user_id,
        MemberNotification.created_at >= cutoff,
    ]
    prefs = await db.scalar(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
    )
    if prefs is not None and prefs.global_mute:
        filters.append(MemberNotification.id.is_(None))
        return filters
    hidden_kinds = muted_inbox_kinds(prefs)
    if hidden_kinds:
        filters.append(MemberNotification.kind.not_in(hidden_kinds))
    muted_leagues = (
        (
            await db.execute(
                select(LeagueMembership.league_id).where(
                    LeagueMembership.player_id == user_id,
                    LeagueMembership.deleted_at.is_(None),
                    LeagueMembership.notification_muted.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if muted_leagues:
        filters.append(MemberNotification.league_id.not_in(muted_leagues))
    return filters


@router.get("/notifications/inbox", response_model=InboxOut)
async def get_inbox(user: CurrentUser, db: Db) -> InboxOut:
    """The member's visible last 30 days of league events, newest first."""
    filters = await _visible_inbox_filters(
        db, user.id, datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    )
    rows = await db.execute(
        select(MemberNotification)
        .where(*filters)
        .order_by(MemberNotification.created_at.desc(), MemberNotification.id.desc())
        .limit(50)
    )
    unread_count = await db.scalar(
        select(func.count(MemberNotification.id)).where(
            *filters,
            MemberNotification.read_at.is_(None),
        )
    )
    return InboxOut(
        items=[InboxItem.model_validate(row, from_attributes=True) for row in rows.scalars()],
        unread_count=unread_count or 0,
    )


@router.post("/notifications/inbox/read")
async def mark_inbox_read(user: CurrentUser, db: Db) -> dict[str, int]:
    """Opening the bell marks only this member's retained notifications read."""
    now = datetime.now(UTC).replace(tzinfo=None)
    filters = await _visible_inbox_filters(db, user.id, now - timedelta(days=30))
    result = await db.execute(
        update(MemberNotification)
        .where(
            *filters,
            MemberNotification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()
    return {"read_count": result.rowcount or 0}


# ── Notification preferences ──────────────────────────────────────────────────


def _time_str(dt_field: object) -> str | None:
    """Format a datetime column (time-only sentinel) as HH:MM string."""
    from datetime import datetime as _dt

    if dt_field is None:
        return None
    if isinstance(dt_field, _dt):
        return dt_field.strftime("%H:%M")
    return None


async def _league_mutes(db: Db, user_id: uuid.UUID) -> list[LeagueMuteOut]:
    """The member's active leagues with their per-league mute state — one settings read."""
    rows = await db.execute(
        select(League.id, League.name, LeagueMembership.notification_muted)
        .join(LeagueMembership, LeagueMembership.league_id == League.id)
        .where(
            LeagueMembership.player_id == user_id,
            LeagueMembership.deleted_at.is_(None),
            League.deleted_at.is_(None),
        )
        .order_by(League.name)
    )
    return [
        LeagueMuteOut(league_id=str(row.id), league_name=row.name, muted=row.notification_muted)
        for row in rows
    ]


@router.get("/notifications/preferences", response_model=PreferencesOut)
async def get_preferences(user: CurrentUser, db: Db) -> PreferencesOut:
    """Return the user's notification preferences (creates defaults on first access)."""
    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        prefs = NotificationPreferences(user_id=user.id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)

    return PreferencesOut(
        global_mute=prefs.global_mute,
        mute_pick_activity=prefs.mute_pick_activity,
        mute_round_updates=prefs.mute_round_updates,
        mute_results=prefs.mute_results,
        quiet_hours_start=_time_str(prefs.quiet_hours_start),
        quiet_hours_end=_time_str(prefs.quiet_hours_end),
        leagues=await _league_mutes(db, user.id),
    )


@router.patch("/notifications/preferences", response_model=PreferencesOut)
async def patch_preferences(
    body: PreferencesPatch,
    user: CurrentUser,
    db: Db,
) -> PreferencesOut:
    """Partially update the user's notification preferences."""
    from datetime import datetime as _dt

    result = await db.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreferences(user_id=user.id)
        db.add(prefs)

    if body.global_mute is not None:
        prefs.global_mute = body.global_mute
    if body.mute_pick_activity is not None:
        prefs.mute_pick_activity = body.mute_pick_activity
    if body.mute_round_updates is not None:
        prefs.mute_round_updates = body.mute_round_updates
    if body.mute_results is not None:
        prefs.mute_results = body.mute_results

    def _parse_time(val: str | None) -> _dt | None:
        if val is None:
            return None
        if val == "":
            return None
        try:
            h, m = map(int, val.split(":"))
            return _dt(2000, 1, 1, h, m)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid time format: {val!r}",
            )

    if body.quiet_hours_start is not None:
        prefs.quiet_hours_start = _parse_time(body.quiet_hours_start)
    if body.quiet_hours_end is not None:
        prefs.quiet_hours_end = _parse_time(body.quiet_hours_end)

    if body.league_mutes:
        try:
            league_ids = {uuid.UUID(lid) for lid in body.league_mutes}
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid league_id in league_mutes",
            )
        membership_result = await db.execute(
            select(LeagueMembership).where(
                LeagueMembership.player_id == user.id,
                LeagueMembership.league_id.in_(league_ids),
                LeagueMembership.deleted_at.is_(None),
            )
        )
        for membership in membership_result.scalars():
            membership.notification_muted = body.league_mutes[str(membership.league_id)]

    await db.commit()
    await db.refresh(prefs)

    return PreferencesOut(
        global_mute=prefs.global_mute,
        mute_pick_activity=prefs.mute_pick_activity,
        mute_round_updates=prefs.mute_round_updates,
        mute_results=prefs.mute_results,
        quiet_hours_start=_time_str(prefs.quiet_hours_start),
        quiet_hours_end=_time_str(prefs.quiet_hours_end),
        leagues=await _league_mutes(db, user.id),
    )
