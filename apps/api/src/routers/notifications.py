"""Push subscription and notification preference endpoints."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.config import settings
from src.database import get_db
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import NotificationPreferences, PushSubscription
from src.rate_limit import limiter, per_user_key
from src.services.push_notification_service import send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["notifications"])

Db = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: dict[str, str]
    device_hint: str | None = None


class UnsubscribeRequest(BaseModel):
    endpoint: str


class LeagueMuteOut(BaseModel):
    league_id: str
    league_name: str
    muted: bool


class PreferencesOut(BaseModel):
    global_mute: bool
    quiet_hours_start: str | None  # "HH:MM"
    quiet_hours_end: str | None  # "HH:MM"
    leagues: list[LeagueMuteOut]


class PreferencesPatch(BaseModel):
    global_mute: bool | None = None
    quiet_hours_start: str | None = None  # "HH:MM" or empty string to clear
    quiet_hours_end: str | None = None
    #: league_id -> desired mute state. Only the leagues named here are touched.
    league_mutes: dict[str, bool] | None = None


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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        quiet_hours_start=_time_str(prefs.quiet_hours_start),
        quiet_hours_end=_time_str(prefs.quiet_hours_end),
        leagues=await _league_mutes(db, user.id),
    )
