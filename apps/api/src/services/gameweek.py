"""Persist a provider's slate as a league's round, drawing on the shared fixture pool.

Turns a :class:`~src.services.odds_provider.Slate` DTO into ``gameweeks`` / ``fixtures`` /
``gameweek_fixtures`` rows. Idempotent: syncing the same round twice updates the existing
rows rather than duplicating them, so the scheduler can refresh before lock.

**Per-league since Batch 14.** A round belongs to one league, and the window it covers —
which days, which kick-off times, how long before it opens picks lock — is that league's
configuration rather than a constant. Fixtures live in a pool shared by every league, so
two leagues playing the same match cost one row and one provider request.

All ``*_utc`` values are stored naive-UTC to match the rest of the schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile
from src.services.odds_provider import OddsProvider, Slate, SlateWindow

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


def window_for(league: League) -> SlateWindow:
    """The slate window this league plays.

    The single place league columns become the value object the rest of the code
    reasons with, so nothing outside this function needs to know the window is
    stored as five integers.
    """
    return SlateWindow(
        start_weekday=league.slate_start_weekday,
        start_minute=league.slate_start_minute,
        end_weekday=league.slate_end_weekday,
        end_minute=league.slate_end_minute,
        lock_offset_minutes=league.lock_offset_minutes,
    )


async def latest_gameweek(db: AsyncSession, league_id: uuid.UUID) -> Gameweek | None:
    """This league's most recent round — what the pick screen defaults to."""
    result = await db.execute(
        select(Gameweek)
        .where(Gameweek.league_id == league_id)
        .order_by(Gameweek.starts_on.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def gameweek_by_id(
    db: AsyncSession, league_id: uuid.UUID, gameweek_id: str
) -> Gameweek | None:
    """One of *this league's* rounds by id, or ``None``.

    Scoped to the league deliberately: before Batch 14 this was a bare primary-key
    lookup, so a member of one league could read another league's round just by
    knowing its id. A round belonging to someone else is now indistinguishable from
    one that does not exist.

    A malformed id is a miss rather than a 500 — callers pass a raw query-string
    value, and asking for a round that cannot exist is the same as asking for one
    that doesn't.
    """
    try:
        key = uuid.UUID(gameweek_id)
    except (ValueError, AttributeError, TypeError):
        return None
    result = await db.execute(
        select(Gameweek).where(Gameweek.id == key, Gameweek.league_id == league_id)
    )
    return result.scalar_one_or_none()


async def resolve_gameweek(
    db: AsyncSession, league_id: uuid.UUID, gameweek_id: str | None
) -> Gameweek:
    """The requested round of this league, or its latest when none is named.

    Shared by the slate and coupon reads so browsing back through the season means
    the same thing on both, and so the league scoping is enforced in one place.
    Raises 404 either way — for an empty season and for an id that does not resolve
    within this league — because to a client both are "there is nothing to show for
    what you asked".
    """
    gameweek = (
        await latest_gameweek(db, league_id)
        if gameweek_id is None
        else await gameweek_by_id(db, league_id, gameweek_id)
    )
    if gameweek is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No gameweek yet" if gameweek_id is None else "Gameweek not found",
        )
    return gameweek


async def all_gameweeks(db: AsyncSession, league_id: uuid.UUID) -> list[Gameweek]:
    """This league's rounds, newest first — its browsable season history.

    Nothing is pruned or archived, so this is the whole record. A season is about
    forty rows, which is small enough not to need paging.
    """
    result = await db.execute(
        select(Gameweek).where(Gameweek.league_id == league_id).order_by(Gameweek.starts_on.desc())
    )
    return list(result.scalars().all())


async def sync_slate(db: AsyncSession, league: League, slate: Slate) -> Gameweek:
    """Upsert this league's round for ``slate.starts_on`` and the fixtures it plays.

    Fixtures go into the **shared pool**, keyed on ``provider_event_id``: a match another
    league already discovered is updated rather than duplicated, and this league's round
    simply links to it. That is what keeps a second league on the same window free —
    no extra rows, and no extra provider request.

    Links are added, never removed. A fixture that drops off a later refresh — postponed,
    or re-scheduled out of the window — stays on the round, because a member may already
    hold a pick on it and settlement still has to resolve that pick.

    Flushes so the returned gameweek and fixtures have ids, but does **not** commit —
    the caller owns the transaction boundary.
    """
    window = window_for(league)
    result = await db.execute(
        select(Gameweek).where(
            Gameweek.league_id == league.id, Gameweek.starts_on == slate.starts_on
        )
    )
    gameweek = result.scalar_one_or_none()
    if gameweek is None:
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=slate.starts_on,
            locks_at_utc=window.locks_at(slate.starts_on),
        )
        db.add(gameweek)
        await db.flush()

    if not slate.fixtures:
        return gameweek

    events = [sf.provider_event_id for sf in slate.fixtures]
    pooled = await db.execute(select(Fixture).where(Fixture.provider_event_id.in_(events)))
    by_event = {f.provider_event_id: f for f in pooled.scalars().all()}

    for sf in slate.fixtures:
        fixture = by_event.get(sf.provider_event_id)
        if fixture is None:
            fixture = Fixture(provider_event_id=sf.provider_event_id)
            db.add(fixture)
            by_event[sf.provider_event_id] = fixture
        # Names/kick-off can shift as the provider firms up the card before lock.
        fixture.home = sf.home
        fixture.away = sf.away
        fixture.kickoff_utc = _naive_utc(sf.kickoff_utc)
        fixture.competition = sf.competition
        fixture.competition_id = sf.competition_id
    await db.flush()

    linked = await db.execute(
        select(GameweekFixture.fixture_id).where(GameweekFixture.gameweek_id == gameweek.id)
    )
    already = set(linked.scalars().all())
    for fixture in by_event.values():
        if fixture.id not in already:
            db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))

    await db.flush()
    return gameweek


async def fixtures_for(db: AsyncSession, gameweek_id: uuid.UUID) -> list[Fixture]:
    """The fixtures a round plays, in kick-off order."""
    result = await db.execute(
        select(Fixture)
        .join(GameweekFixture, GameweekFixture.fixture_id == Fixture.id)
        .where(GameweekFixture.gameweek_id == gameweek_id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )
    return list(result.scalars().all())


# ── Scheduler-driven lifecycle (Batch 4) ────────────────────────────────────────


def upcoming_slate_dates(today: date, window: SlateWindow, count: int) -> list[date]:
    """The next ``count`` dates this window opens on, today included.

    Fixture *discovery* runs on this horizon so a round's card exists days before
    anyone can pick on it. Pricing is deliberately not on this horizon — odds are
    fetched on demand, because a price is only meaningful at the moment a member
    freezes it onto a pick.
    """
    first = window.first_start_on_or_after(today)
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


async def active_leagues(db: AsyncSession) -> list[League]:
    """Every league still playing — the leagues discovery has to cover."""
    result = await db.execute(select(League).where(League.deleted_at.is_(None)))
    return list(result.scalars().all())


async def discover_fixtures(
    db: AsyncSession, provider: OddsProvider, leagues: Sequence[League], today: date, horizon: int
) -> list[Gameweek]:
    """Walk every league's coming cards into the pool and link them to its rounds.

    The pre-fetch half of Batch 11's split: discovery is scheduled and cheap, pricing
    is on demand and rate-limited.

    Leagues are grouped **by window** and each ``(window, date)`` is fetched exactly
    once, then shared by every league playing it. This is what stops per-league
    windows multiplying the provider bill: the cost is the number of *distinct*
    windows, not the number of leagues, so a second league on the default Saturday
    is free. Only leagues that genuinely play a different window cost anything more.

    Dates the provider carries nothing for are skipped rather than left as empty
    rounds. Flushes but does not commit — the caller owns the transaction.
    """
    by_window: dict[SlateWindow, list[League]] = {}
    for league in leagues:
        by_window.setdefault(window_for(league), []).append(league)

    discovered: list[Gameweek] = []
    for window, sharing in by_window.items():
        for starts_on in upcoming_slate_dates(today, window, horizon):
            slate = await provider.fetch_slate(window, starts_on)
            if not slate.fixtures:
                continue
            for league in sharing:
                discovered.append(await sync_slate(db, league, slate))
    return discovered


async def refresh_slate(
    db: AsyncSession, provider: OddsProvider, league: League, starts_on: date
) -> Gameweek | None:
    """Fetch one league's card for ``starts_on`` and upsert it as a round.

    Returns the synced round, or ``None`` when the provider carries no qualifying
    fixtures (so the periodic job never leaves an empty round behind, e.g. out of
    season). Flushes but does not commit — the scheduler job owns the transaction.
    """
    slate = await provider.fetch_slate(window_for(league), starts_on)
    if not slate.fixtures:
        return None
    return await sync_slate(db, league, slate)


async def lock_due_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Flip every open round whose lock has passed to ``locked``.

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
        .order_by(Gameweek.starts_on)
    )
    return list(result.scalars().all())


async def current_open_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Every still-open round whose lock is in the future — the ones to remind for.

    A list, not one row. Before Batch 14 there was a single global round so "the
    current one" was well defined; now every league has its own, and returning one
    would silently deny reminders to every league but that one.
    """
    result = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.status == GameweekStatus.open,
            Gameweek.locks_at_utc > now,
        )
        .order_by(Gameweek.starts_on.desc())
    )
    return list(result.scalars().all())


class MissingPickMember(BaseModel):
    """A member who still owes a pick for a gameweek — one pick-reminder recipient."""

    player_id: str
    display_name: str
    timezone: str
    league_id: str
    league_name: str


async def members_missing_picks(db: AsyncSession, gameweek: Gameweek) -> list[MissingPickMember]:
    """Members of *this round's league* with no pick for it — the reminder recipients.

    Filtered to ``gameweek.league_id``. Before Batch 14 a round was global, and this
    query had no league filter at all, so a reminder for one round was sent to every
    member of every league in the database. Excludes deleted memberships/leagues and
    inactive/deleted profiles.
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
            LeagueMembership.league_id == gameweek.league_id,
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
