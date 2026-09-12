"""The two reads that would have caught a week of silence on day one. Batch 119.

No scheduled job created a round between 2026-09-04 20:21 and 2026-09-11. Throughout that
week the admin dashboard read healthy: the scheduler panel showed APScheduler running with
``discover_fixtures`` due at 06:00, and the stuck-rounds panel was empty because every
round the deployment held had already been played. Twelve members had nothing to play and
the only thing that surfaced it was somebody going looking.

Each test here builds the shape that was live at the time and asserts the alarm fires, then
builds the healthy shape beside it and asserts it does not. Postgres-backed, because both
reads are queries and a model of a query is not the thing that has to be right.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile, UserRole
from src.services.discovery_health import discovery_health

pytestmark = pytest.mark.asyncio

#: The reads are queries, so they need a database — but the two rules *about* the reads are
#: arithmetic, and losing those on a laptop without PostgreSQL would be a poor trade.
needs_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The threshold the deployment ships with: eight days, because a round *row* appears when
#: a new date enters the horizon — about once a week per league on a weekly cadence.
STALE_AFTER = 192.0

NOW = datetime(2026, 9, 11, 22, 0)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session that is always rolled back — nothing these tests write persists."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _league_with_members(db: AsyncSession, members: int) -> League:
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"owner-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    db.add(owner)
    await db.flush()
    league = League(slug=f"hlth-{tag}", name=f"Health {tag}", created_by=owner.id)
    db.add(league)
    await db.flush()
    for index in range(members):
        player = Profile(
            display_name=f"m{index}-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player
        )
        db.add(player)
        await db.flush()
        db.add(LeagueMembership(league_id=league.id, player_id=player.id))
    await db.flush()
    return league


async def _round(
    db: AsyncSession,
    league: League,
    starts_on: date,
    *,
    status: GameweekStatus,
    locks_at: datetime,
    created_at: datetime | None = None,
) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id, starts_on=starts_on, status=status, locks_at_utc=locks_at
    )
    if created_at is not None:
        gameweek.created_at = created_at
    db.add(gameweek)
    await db.flush()
    return gameweek


@needs_db
async def test_a_league_with_members_and_nothing_to_play_is_an_alarm(
    session: AsyncSession,
) -> None:
    """The fast read, and the exact shape 2-1 Hibs was in for a week.

    Its 5 September round existed and had settled; nothing had created the next one. The
    league had twelve members and not one claimable round, which is wrong the moment it is
    true rather than after a threshold.
    """
    league = await _league_with_members(session, 12)
    await _round(
        session,
        league,
        date(2026, 9, 5),
        status=GameweekStatus.settled,
        locks_at=datetime(2026, 9, 5, 13, 30),
        created_at=datetime(2026, 9, 4, 20, 21),
    )

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    silent = {entry.slug: entry for entry in health.leagues_without_open_round}
    assert league.slug in silent
    assert silent[league.slug].members == 12
    assert health.silent_leagues
    assert health.alarm


@needs_db
async def test_a_league_with_a_claimable_round_is_quiet(session: AsyncSession) -> None:
    """The healthy shape: a round ahead of its lock, whatever label the hourly jobs gave it.

    ``scheduled`` counts as well as ``open``. A round whose announced opening has not
    arrived is still something the league has to play, and treating it as silence would
    alarm every league that announces its openings in advance.
    """
    league = await _league_with_members(session, 12)
    await _round(
        session,
        league,
        date(2026, 9, 12),
        status=GameweekStatus.scheduled,
        locks_at=datetime(2026, 9, 12, 13, 30),
        created_at=NOW - timedelta(hours=1),
    )

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    assert league.slug not in {entry.slug for entry in health.leagues_without_open_round}


@needs_db
async def test_a_round_whose_lock_has_passed_is_not_something_to_play(
    session: AsyncSession,
) -> None:
    """Still labelled ``open`` because the hourly lock sweep has not run is not claimable.

    The predicate is the instant, not the label — the same rule the submit endpoint uses.
    A league whose only round locked an hour ago has nothing to play and must say so.
    """
    league = await _league_with_members(session, 12)
    await _round(
        session,
        league,
        date(2026, 9, 11),
        status=GameweekStatus.open,
        locks_at=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(days=2),
    )

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    assert league.slug in {entry.slug for entry in health.leagues_without_open_round}


@needs_db
async def test_a_league_with_no_members_is_not_an_alarm(session: AsyncSession) -> None:
    """Nobody is going without. An empty league with no round is a league, not an incident."""
    league = await _league_with_members(session, 0)

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    assert league.slug not in {entry.slug for entry in health.leagues_without_open_round}


@needs_db
async def test_a_deleted_league_is_not_an_alarm(session: AsyncSession) -> None:
    """A league that has been closed is not owed a round."""
    league = await _league_with_members(session, 12)
    league.deleted_at = NOW - timedelta(days=1)
    await session.flush()

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    assert league.slug not in {entry.slug for entry in health.leagues_without_open_round}


@needs_db
async def test_the_deployment_wide_read_is_the_newest_round_there_is(
    session: AsyncSession,
) -> None:
    """The second read, and the one that says *nothing at all* is being produced.

    Asserted against the database's own maximum rather than against a number, because the
    gate's database holds every other suite's rows and a fixed expectation would be a
    fixture of the test order. What has to be right is that the read is that maximum, and
    that ``stale`` is decided by comparing it to the threshold — which is checked from both
    sides so neither answer can be the constant one.
    """
    league = await _league_with_members(session, 12)
    await _round(
        session,
        league,
        date(2026, 9, 5),
        status=GameweekStatus.settled,
        locks_at=datetime(2026, 9, 5, 13, 30),
        created_at=datetime(2026, 9, 4, 20, 21),
    )
    newest = (await session.execute(select(func.max(Gameweek.created_at)))).scalar_one_or_none()
    assert newest is not None
    # The gate's database holds every other suite's rows, and some of them are stamped
    # "now". Read from an instant after the newest one there is, so the arithmetic is a
    # property of the code rather than of the test order.
    now = newest + timedelta(hours=50)

    health = await discovery_health(session, now, stale_after_hours=STALE_AFTER)
    assert health.newest_round_created_at == newest
    assert health.hours_since_newest_round == pytest.approx(50.0)

    quiet = await discovery_health(session, now, stale_after_hours=51.0)
    strict = await discovery_health(session, now, stale_after_hours=49.0)
    assert not quiet.stale
    assert strict.stale


async def test_a_deployment_with_no_rounds_at_all_is_stale(session: AsyncSession) -> None:
    """The worst version of this fault must not read as the healthiest.

    ``None`` is not "no news". A deployment whose discovery has never once succeeded has
    exactly the same symptom as one whose discovery stopped, and reading the absence of a
    round as fine is how it would stay hidden.
    """
    from src.services.discovery_health import DiscoveryHealth

    empty = DiscoveryHealth(
        newest_round_created_at=None,
        hours_since_newest_round=None,
        stale_after_hours=STALE_AFTER,
        leagues_without_open_round=(),
    )
    assert empty.stale
    assert empty.alarm


async def test_the_threshold_is_a_week_and_a_day_and_the_reason_is_the_cadence() -> None:
    """The shipped default, and why it cannot be a day.

    A round row appears when a new date enters the horizon — once a week per league on a
    weekly cadence — so a one-day threshold would alarm six mornings out of seven on a
    perfectly healthy deployment, and an alarm that cries wolf is the one nobody reads.
    """
    from src.config import settings

    assert settings.discovery_stale_after_hours == 192
    assert settings.discovery_stale_after_hours > 24 * 7
