"""Domain notification triggers — thin wrappers over ``send_notification``.

Batch 1 kept only the league-membership trigger the leagues routers call; Batch 4 adds the
pick-reminder trigger the scheduler drives. Each decides *who* to notify and with what copy;
``send_notification`` enforces per-member mute / quiet hours and does the delivery.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.profile import Profile, UserRole
from src.services.gameweek import members_missing_picks
from src.services.push_notification_service import send_notification

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def _admin_players(session: AsyncSession) -> Sequence[Profile]:
    """Active, non-deleted admin profiles — recipients for admin alerts."""
    result = await session.execute(
        select(Profile).where(
            Profile.role == UserRole.admin,
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
    )
    return result.scalars().all()


async def notify_member_joined(
    session: AsyncSession,
    player_name: str,
    league_name: str,
) -> None:
    """Notify admins when an existing player joins a league via code or invite."""
    for admin in await _admin_players(session):
        await send_notification(
            session,
            admin.id,
            f"New member: {league_name}",
            f"{player_name} has joined {league_name}.",
            timezone_name=admin.timezone,
        )


def _lock_label(locks_at_utc: datetime, timezone_name: str) -> str:
    """The deadline on the member's own clock, as ``Sat 14:30``.

    The copy said "14:30" flat until Batch 30. Lock time has been per-league since
    Batch 14 and admin-configurable since Batch 15, so a constant is simply wrong for
    a league playing Friday to Monday — and the reminder can precede the deadline by
    more than a day, which is why the weekday is named too. Unknown timezones fall back
    to UTC, matching ``push_notification_service``.
    """
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return locks_at_utc.replace(tzinfo=UTC).astimezone(zone).strftime("%a %H:%M")


async def send_pick_reminders(session: AsyncSession, gameweek: Gameweek) -> int:
    """Push a reminder to every active member who hasn't picked for ``gameweek``.

    Returns the number of members nudged (a member in N leagues without a pick is nudged
    once per league). ``send_notification`` honours each member's mute / quiet hours, so a
    suppressed recipient is still counted here — this reports who was *targeted*, and the
    delivery layer decides what actually goes out.

    The ``url`` is the point of naming the league in the body: before Batch 30 no address
    in the app named a league's coupon, so ``sw.ts`` fell back to ``/`` and a reminder about
    league B dropped the member on a list of every league they play.
    """
    reminded = 0
    for member in await members_missing_picks(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            "Pick due",
            f"You haven't made your pick in {member.league_name} yet — "
            f"picks lock {_lock_label(gameweek.locks_at_utc, member.timezone)}.",
            data={
                "type": "pick_reminder",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"pick-reminder-{member.league_id}",
            timezone_name=member.timezone,
        )
        reminded += 1
    return reminded
