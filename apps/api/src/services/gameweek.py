"""Persist a provider's slate as the week's gameweek + fixtures.

Turns a :class:`~src.services.odds_provider.Slate` DTO into ``gameweeks`` / ``fixtures``
rows — the DTO→ORM mapping at the heart of Batch 3. Idempotent: syncing the same Saturday
twice updates the existing rows rather than duplicating them, so the Batch 4 scheduler can
refresh the slate repeatedly before lock.

The gameweek locks at **14:30 UK local** on its Saturday; all ``*_utc`` values are stored
naive-UTC to match the rest of the schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile
from src.services.odds_provider import OddsProvider, Slate

_UK_TZ = ZoneInfo("Europe/London")
_LOCK_HOUR = 14
_LOCK_MINUTE = 30  # picks lock 14:30 Saturday — 30 min before the 15:00 kick-offs
_SATURDAY = 5  # date.weekday(): Monday=0 … Saturday=5

# Tier boundaries for how stale a browsed price may be (see slate_odds_max_age).
_NEAR_LOCK_SECONDS = 6 * 3600
_MID_LOCK_SECONDS = 24 * 3600


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
    """The most recent gameweek by Saturday date — the one the pick screen defaults to."""
    result = await db.execute(select(Gameweek).order_by(Gameweek.saturday_date.desc()).limit(1))
    return result.scalar_one_or_none()


async def gameweek_by_id(db: AsyncSession, gameweek_id: str) -> Gameweek | None:
    """One gameweek by id, or ``None`` — including for an id that isn't a UUID.

    Callers pass a raw query-string value, and a malformed id is a miss rather than
    a 500: asking for a gameweek that cannot exist is the same as asking for one
    that doesn't.
    """
    try:
        key = uuid.UUID(gameweek_id)
    except (ValueError, AttributeError, TypeError):
        return None
    return await db.get(Gameweek, key)


async def resolve_gameweek(db: AsyncSession, gameweek_id: str | None) -> Gameweek:
    """The requested gameweek, or the latest when none is named.

    Shared by the slate and coupon reads so browsing back through the season means
    the same thing on both. Raises 404 either way — for an empty season and for an
    id that does not resolve — because to a client both are "there is nothing to
    show for what you asked".
    """
    gameweek = (
        await latest_gameweek(db) if gameweek_id is None else await gameweek_by_id(db, gameweek_id)
    )
    if gameweek is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No gameweek yet" if gameweek_id is None else "Gameweek not found",
        )
    return gameweek


async def all_gameweeks(db: AsyncSession) -> list[Gameweek]:
    """Every gameweek, newest first — the season's browsable history.

    Nothing is pruned or archived, so this is the whole record. A season is about
    forty rows, which is small enough not to need paging.
    """
    result = await db.execute(select(Gameweek).order_by(Gameweek.saturday_date.desc()))
    return list(result.scalars().all())


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
    by_event = {f.provider_event_id: f for f in existing.scalars().all()}

    for sf in slate.fixtures:
        fixture = by_event.get(sf.provider_event_id)
        if fixture is None:
            db.add(
                Fixture(
                    gameweek_id=gameweek.id,
                    provider_event_id=sf.provider_event_id,
                    home=sf.home,
                    away=sf.away,
                    kickoff_utc=_naive_utc(sf.kickoff_utc),
                    competition=sf.competition,
                    competition_id=sf.competition_id,
                )
            )
        else:
            # Names/kick-off can shift as the provider firms up the card before lock.
            fixture.home = sf.home
            fixture.away = sf.away
            fixture.kickoff_utc = _naive_utc(sf.kickoff_utc)
            fixture.competition = sf.competition
            fixture.competition_id = sf.competition_id

    await db.flush()
    return gameweek


# ── Scheduler-driven lifecycle (Batch 4) ────────────────────────────────────────


def upcoming_saturday(today: date) -> date:
    """The Saturday on or after ``today`` — the slate the refresh job targets.

    On a Saturday it returns that same day, so the match-day refreshes keep updating the
    current slate rather than skipping to next week.
    """
    return today + timedelta(days=(_SATURDAY - today.weekday()) % 7)


def upcoming_saturdays(today: date, count: int) -> list[date]:
    """The next ``count`` Saturdays starting with :func:`upcoming_saturday`.

    Fixture *discovery* runs on this horizon so the card for a Saturday exists days
    before anyone can pick on it. Pricing is deliberately not on this horizon —
    odds are fetched on demand, because a price is only meaningful at the moment a
    member freezes it onto a pick.
    """
    first = upcoming_saturday(today)
    return [first + timedelta(weeks=offset) for offset in range(max(count, 1))]


def slate_odds_max_age(gameweek: Gameweek, now: datetime, near_ttl: float, far_ttl: float) -> float:
    """How stale a browsed price may be, tightening as the lock approaches.

    Three tiers rather than a curve, because the cost is a step function of the TTL
    and a legible budget matters more here than a smooth one. A locked or settled
    gameweek gets the loosest tier: nothing can move a price that is already frozen,
    so re-fetching it buys nothing.
    """
    if gameweek.status != GameweekStatus.open:
        return far_ttl
    until_lock = (gameweek.locks_at_utc - now).total_seconds()
    if until_lock <= _NEAR_LOCK_SECONDS:
        return near_ttl
    if until_lock <= _MID_LOCK_SECONDS:
        return far_ttl / 2
    return far_ttl


async def discover_fixtures(
    db: AsyncSession, provider: OddsProvider, saturdays: Sequence[date]
) -> list[Gameweek]:
    """Walk each Saturday's card into ``gameweeks`` / ``fixtures``.

    The pre-fetch half of Batch 11's split: discovery is scheduled and cheap
    (one request per competition), pricing is on demand and rate-limited. Saturdays
    the provider carries nothing for are skipped rather than left as empty
    gameweeks. Flushes but does not commit — the caller owns the transaction.
    """
    discovered: list[Gameweek] = []
    for saturday in saturdays:
        gameweek = await refresh_slate(db, provider, saturday)
        if gameweek is not None:
            discovered.append(gameweek)
    return discovered


async def refresh_slate(
    db: AsyncSession, provider: OddsProvider, saturday: date
) -> Gameweek | None:
    """Fetch ``saturday``'s slate from the provider and upsert it as gameweek + fixtures.

    Returns the synced gameweek, or ``None`` when the provider carries no qualifying
    fixtures that day (so the periodic job never leaves an empty gameweek behind, e.g. out
    of season). Flushes but does not commit — the scheduler job owns the transaction.
    """
    slate = await provider.fetch_slate(saturday)
    if not slate.fixtures:
        return None
    return await sync_slate(db, slate)


async def lock_due_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Flip every open gameweek whose 14:30 lock has passed to ``locked``.

    ``now`` is naive-UTC (as stored). Predicate-based rather than "the latest one" so a
    missed run self-heals on the next. Flushes but does not commit.
    """
    result = await db.execute(
        select(Gameweek).where(
            Gameweek.status == GameweekStatus.open,
            Gameweek.locks_at_utc <= now,
        )
    )
    locked = list(result.scalars().all())
    for gameweek in locked:
        gameweek.status = GameweekStatus.locked
    await db.flush()
    return locked


async def settleable_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Gameweeks past their lock that aren't settled yet — the settle job's candidates.

    Includes any still ``open`` past its lock (a defensive catch if the lock job missed a
    run) as well as ``locked`` ones. Ordered oldest-first.
    """
    result = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.status != GameweekStatus.settled,
            Gameweek.locks_at_utc <= now,
        )
        .order_by(Gameweek.saturday_date)
    )
    return list(result.scalars().all())


async def current_open_gameweek(db: AsyncSession, now: datetime) -> Gameweek | None:
    """The latest still-open gameweek whose lock is in the future — the one to remind for."""
    result = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.status == GameweekStatus.open,
            Gameweek.locks_at_utc > now,
        )
        .order_by(Gameweek.saturday_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


class MissingPickMember(BaseModel):
    """A member who still owes a pick for a gameweek — one pick-reminder recipient."""

    player_id: str
    display_name: str
    timezone: str
    league_id: str
    league_name: str


async def members_missing_picks(db: AsyncSession, gameweek: Gameweek) -> list[MissingPickMember]:
    """Active memberships with no pick for ``gameweek`` — the pick-reminder recipients.

    Picks are league-scoped, so a member in several leagues appears once per league they
    still owe. Excludes deleted memberships/leagues and inactive/deleted profiles.
    """
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            LeagueMembership.player_id,
            display_name.label("display_name"),
            Profile.timezone,
            League.id.label("league_id"),
            League.name.label("league_name"),
        )
        .select_from(LeagueMembership)
        .join(League, League.id == LeagueMembership.league_id)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .outerjoin(
            Pick,
            (Pick.league_id == LeagueMembership.league_id)
            & (Pick.player_id == LeagueMembership.player_id)
            & (Pick.gameweek_id == gameweek.id),
        )
        .where(
            LeagueMembership.deleted_at.is_(None),
            League.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
            Pick.id.is_(None),
        )
    )
    return [
        MissingPickMember(
            player_id=str(row.player_id),
            display_name=row.display_name,
            timezone=row.timezone,
            league_id=str(row.league_id),
            league_name=row.league_name,
        )
        for row in rows.all()
    ]
