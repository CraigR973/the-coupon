"""Format fences and gated parent creation; no provider or payment side effects."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.two_game import TwoGameRollout

LONDON = ZoneInfo("Europe/London")


def is_two_game(week: Gameweek) -> bool:
    # Existing callers also construct unflushed legacy models with format=None.
    return week.format == "two_game"


def london_utc(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), LONDON).astimezone(UTC).replace(tzinfo=None)


async def rollout_for(
    db: AsyncSession, league_id: uuid.UUID, week_label: date, *, allow_suspended: bool = False
) -> TwoGameRollout | None:
    # Pure format fences are also imported by the independent payments process.
    # Loading API settings there would violate its deliberately separate runtime.
    from src.config import settings

    if not settings.two_games_enabled:
        return None
    row = await db.get(TwoGameRollout, league_id)
    if row is None or not row.enabled or week_label < row.first_week:
        return None
    if row.suspended and not allow_suspended:
        return None
    return row


async def legacy_date_blocked(db: AsyncSession, league_id: uuid.UUID, starts_on: date) -> bool:
    """Keep an accepted legacy parent, but never create a replacement beyond cutover.

    This fence remains even when the installation gate is subsequently off. Disabling
    entry cannot reinterpret an already assigned future format as a legacy week.
    """
    existing_legacy = (
        select(Gameweek.id)
        .where(
            Gameweek.league_id == league_id,
            Gameweek.starts_on == starts_on,
            Gameweek.format == "legacy",
        )
        .exists()
    )
    existing_new = (
        select(Gameweek.id)
        .where(
            Gameweek.league_id == league_id,
            Gameweek.starts_on == starts_on,
            Gameweek.format == "two_game",
        )
        .exists()
    )
    cutover = (
        select(TwoGameRollout.league_id)
        .where(
            TwoGameRollout.league_id == league_id,
            TwoGameRollout.enabled.is_(True),
            TwoGameRollout.first_week <= starts_on + timedelta(days=5),
        )
        .exists()
    )
    return bool(
        await db.scalar(
            select(literal(True)).where(and_(~existing_legacy, or_(existing_new, cutover)))
        )
    )


async def ensure_two_game_week(
    db: AsyncSession, league_id: uuid.UUID, week_label: date, *, billing: bool = False
) -> Gameweek | None:
    """Create an unplayable parent only, after both rollout gates. Caller commits."""
    if week_label.weekday() != 5:
        raise ValueError("football week must have a Saturday label")
    if await rollout_for(db, league_id, week_label, allow_suspended=billing) is None:
        return None
    # Serialise new parent/number allocation. No provider I/O occurs in this module.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"), {"key": str(league_id)}
    )
    week = await db.scalar(
        select(Gameweek).where(Gameweek.league_id == league_id, Gameweek.starts_on == week_label)
    )
    if week is not None:
        if not is_two_game(week):
            raise ValueError("cutover requires an untouched future week; legacy parent exists")
        return week
    from src.services.gameweek import next_gameweek_number

    week = Gameweek(
        league_id=league_id,
        starts_on=week_label,
        format="two_game",
        locks_at_utc=london_utc(week_label, 14, 30),
        picks_open_at_utc=None,
        status=GameweekStatus.locked,
        number=await next_gameweek_number(db, league_id, week_label),
    )
    db.add(week)
    await db.flush()
    return week
