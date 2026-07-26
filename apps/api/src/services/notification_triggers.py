"""Domain notification triggers — thin wrappers over ``send_notification``.

Batch 1 kept only the league-membership trigger the leagues routers call; Batch 4 adds the
pick-reminder trigger the scheduler drives. Each decides *who* to notify and with what copy;
``send_notification`` enforces per-member mute / quiet hours and does the delivery.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

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


async def send_pick_reminders(session: AsyncSession, gameweek: Gameweek) -> int:
    """Push a reminder to every active member who hasn't picked for ``gameweek``.

    Returns the number of members nudged (a member in N leagues without a pick is nudged
    once per league). ``send_notification`` honours each member's mute / quiet hours, so a
    suppressed recipient is still counted here — this reports who was *targeted*, and the
    delivery layer decides what actually goes out.
    """
    reminded = 0
    for member in await members_missing_picks(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            "Pick due",
            f"You haven't made your pick in {member.league_name} yet — picks lock 14:30.",
            data={"type": "pick_reminder", "league_id": member.league_id},
            tag=f"pick-reminder-{member.league_id}",
            timezone_name=member.timezone,
        )
        reminded += 1
    return reminded
