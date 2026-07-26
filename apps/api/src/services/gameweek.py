"""Persist a Betfair slate as the week's gameweek + fixtures.

Turns the adapter's :class:`~src.services.betfair.Slate` DTO into ``gameweeks`` /
``fixtures`` rows — the DTO→ORM mapping at the heart of Batch 3. Idempotent: syncing the
same Saturday twice updates the existing rows rather than duplicating them, so the Batch 4
scheduler can refresh the slate repeatedly before lock.

The gameweek locks at **14:30 UK local** on its Saturday; all ``*_utc`` values are stored
naive-UTC to match the rest of the schema.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.services.betfair import Slate

_UK_TZ = ZoneInfo("Europe/London")
_LOCK_HOUR = 14
_LOCK_MINUTE = 30  # picks lock 14:30 Saturday — 30 min before the 15:00 kick-offs


def _naive_utc(value: datetime) -> datetime:
    """Strip to naive UTC (the storage convention for every ``*_utc`` column)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def is_open_for_picks(gameweek: Gameweek, now: datetime) -> bool:
    """True when picks are still accepted: status ``open`` and before the 14:30 lock.

    ``now`` must be naive-UTC (as stored). The scheduler flips ``status`` to ``locked`` at
    the deadline in Batch 4; until then this time check is the gate.
    """
    return gameweek.status == GameweekStatus.open and now < gameweek.locks_at_utc


def compute_locks_at(saturday: date) -> datetime:
    """Naive-UTC instant of 14:30 UK local on ``saturday``.

    Anchored in ``Europe/London`` so it is correct under both BST and GMT across the
    August–May season.
    """
    local = datetime(
        saturday.year, saturday.month, saturday.day, _LOCK_HOUR, _LOCK_MINUTE, tzinfo=_UK_TZ
    )
    return _naive_utc(local)


async def latest_gameweek(db: AsyncSession) -> Gameweek | None:
    """The most recent gameweek by Saturday date — the one the pick screen shows."""
    result = await db.execute(select(Gameweek).order_by(Gameweek.saturday_date.desc()).limit(1))
    return result.scalar_one_or_none()


async def sync_slate(db: AsyncSession, slate: Slate) -> Gameweek:
    """Upsert the gameweek for ``slate.saturday`` and its fixtures.

    Flushes so the returned gameweek and fixtures have ids, but does **not** commit —
    the caller owns the transaction boundary.
    """
    result = await db.execute(select(Gameweek).where(Gameweek.saturday_date == slate.saturday))
    gameweek = result.scalar_one_or_none()
    if gameweek is None:
        gameweek = Gameweek(
            saturday_date=slate.saturday,
            locks_at_utc=compute_locks_at(slate.saturday),
        )
        db.add(gameweek)
        await db.flush()

    existing = await db.execute(select(Fixture).where(Fixture.gameweek_id == gameweek.id))
    by_event = {f.betfair_event_id: f for f in existing.scalars().all()}

    for sf in slate.fixtures:
        fixture = by_event.get(sf.betfair_event_id)
        if fixture is None:
            db.add(
                Fixture(
                    gameweek_id=gameweek.id,
                    betfair_event_id=sf.betfair_event_id,
                    home=sf.home,
                    away=sf.away,
                    kickoff_utc=_naive_utc(sf.kickoff_utc),
                    competition=sf.competition,
                    competition_id=sf.competition_id,
                )
            )
        else:
            # Names/kick-off can shift as Betfair firms up the card before lock.
            fixture.home = sf.home
            fixture.away = sf.away
            fixture.kickoff_utc = _naive_utc(sf.kickoff_utc)
            fixture.competition = sf.competition
            fixture.competition_id = sf.competition_id

    await db.flush()
    return gameweek
