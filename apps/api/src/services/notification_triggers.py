"""Domain notification triggers — thin wrappers over ``send_notification``.

Batch 1 keeps only the league-membership trigger the leagues routers call.
Coupon-specific triggers (pick reminders, settlement) arrive with the scheduler
jobs in Batch 4.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.profile import Profile, UserRole
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
