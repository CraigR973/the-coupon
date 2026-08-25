"""Domain notification triggers — thin wrappers over ``send_notification``.

Batch 1 kept only the league-membership trigger the leagues routers call; Batch 4 adds the
pick-reminder trigger the scheduler drives. Each decides *who* to notify and with what copy;
``send_notification`` enforces per-member mute / quiet hours and does the delivery.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.profile import Profile, UserRole
from src.services.gameweek import members_missing_picks, notification_targets
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
            league_id=uuid.UUID(member.league_id),
        )
        reminded += 1
    return reminded


async def notify_picks_open(session: AsyncSession, gameweek: Gameweek) -> int:
    """Tell a league its round is now claimable. Batch 76.

    ``run_open_gameweeks`` has flipped ``scheduled -> open`` hourly since Batch 27 and
    returned the rounds it moved; it simply told nobody. This is that missing half.

    **Dead code in 2-1 Hibs until the owner sets an offset**, and shipped anyway. That
    league has ``pick_open_offset_minutes`` unset, so its rounds are born ``open`` at
    discovery and ``open_due_gameweeks`` will never move one — there is no opening instant
    to announce. It is correct for ``the-coupon``, which carries the offset already.

    Everyone active and unmuted is told, not only those without a pick: nobody can hold a
    pick in a round that has this instant only just passed.
    """
    told = 0
    for member in await notification_targets(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            "Picks are open",
            f"The coupon is open in {member.league_name} — "
            f"picks lock {_lock_label(gameweek.locks_at_utc, member.timezone)}.",
            data={
                "type": "picks_open",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"picks-open-{member.league_id}-{gameweek.id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        told += 1
    return told


async def notify_pick_made(
    session: AsyncSession,
    gameweek: Gameweek,
    picker_id: uuid.UUID,
    picker_name: str,
    league_name: str,
    selection: str,
    odds: Decimal,
    *,
    moved: bool,
) -> int:
    """Tell the rest of the league somebody claimed — or moved. Batch 76.

    The event the game is actually built around: the coupon is a land-grab, and until now
    nothing announced a grab. ``moved`` carries the more useful half — a member switching
    frees their old selection back into the pool, and nothing in the product said so.

    **None of this is a disclosure.** ``routers/gameweek.py``'s ``_gameweek_members``
    already serves every member's pick, the holder's name and the frozen price to any
    member of that league *before* lock, because the land-grab is unreadable otherwise.
    This says on a phone what the screen already says.

    ``odds`` is ``Pick.odds_at_pick`` — the price frozen onto the row at claim time, never
    a live quote. A winning pick scores ``round(odds × 10)`` against that stored number, so
    an alert quoting anything else would be quoting a score nobody gets.

    The ``tag`` collapses per ``(league, round)``, which is load-bearing rather than tidy:
    twelve members each notifying eleven others is 132 sends a round in 2-1 Hibs, and the
    owner has chosen that over a digest. One live pick alert in the tray is what makes it
    survivable — that and the per-league mute, which this passes.
    """
    verb = "moved to" if moved else "took"
    told = 0
    for member in await notification_targets(session, gameweek, excluding=picker_id):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            f"{'Pick changed' if moved else 'New pick'} in {member.league_name}",
            f"{picker_name} {verb} {selection} at {odds:.2f} in {league_name}.",
            data={
                "type": "pick_changed" if moved else "pick_made",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"pick-made-{member.league_id}-{gameweek.id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        told += 1
    return told
