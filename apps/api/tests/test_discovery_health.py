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
from unittest.mock import AsyncMock

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
from src.services.discovery_health import DiscoveryHealth, SilentLeague, discovery_health

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


# ── Batch 129: the alarm reaches a person ─────────────────────────────────────
#
# Batch 119 built these two reads because no round was created by any scheduled job for
# a week and nothing surfaced it — then routed them to the admin dashboard and the logs,
# both of which need somebody to go and look. The week this exists for is the proof that
# nobody does.
#
# What the alarm *detects* is untouched here. Only where it arrives is new.


async def _site_admin(db: AsyncSession) -> Profile:
    admin = Profile(
        display_name=f"adm-{uuid.uuid4().hex[:8]}", pin_hash=hash_pin("1234"), role=UserRole.admin
    )
    db.add(admin)
    await db.flush()
    return admin


def _fresh_cooldown() -> str:
    """A bucket key nothing else has spent, so each test starts with its allowance."""
    from src.services import notification_triggers

    return f"{notification_triggers.DISCOVERY_SILENCE_ALERT_KEY}:{uuid.uuid4().hex[:8]}"


@needs_db
async def test_a_stale_deployment_pushes_once_and_not_every_run(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finding: an alarm nobody is told about, and one nobody can mute."""
    from src.services import notification_triggers

    monkeypatch.setattr(notification_triggers, "DISCOVERY_SILENCE_ALERT_KEY", _fresh_cooldown())
    sent: list[tuple[uuid.UUID, str]] = []

    async def _record(_s: object, user_id: uuid.UUID, title: str, *_a: object, **_k: object) -> int:
        sent.append((user_id, title))
        return 1

    monkeypatch.setattr(notification_triggers, "send_notification", _record)

    admin = await _site_admin(session)
    league = await _league_with_members(session, 3)
    await _round(
        session,
        league,
        date(2026, 9, 5),
        status=GameweekStatus.locked,
        locks_at=NOW - timedelta(days=6),
        created_at=NOW - timedelta(days=30),
    )
    await session.flush()

    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)
    assert health.alarm, "the fixture is not the condition this test is about"

    first = await notification_triggers.notify_discovery_silence(session, health)
    told_on_the_first_run = list(sent)
    second = await notification_triggers.notify_discovery_silence(session, health)

    assert first is True, "the alarm never reached anybody"
    assert second is False, "it would alert on every run, which is how an alert gets muted"
    # Every *active site admin* is told, and this admin is one of them. Asserted as
    # membership rather than as an exact list: `_admin_players` reads the whole
    # deployment, and a shared test database holds every other module's admins too.
    told_ids = [user_id for user_id, _ in told_on_the_first_run]
    assert admin.id in told_ids
    assert len(told_ids) == len(set(told_ids)), "somebody was told twice in one run"
    assert all("stopped building rounds" in title for _, title in told_on_the_first_run)
    # And the second run added nothing at all.
    assert sent == told_on_the_first_run


@needs_db
async def test_a_healthy_deployment_pushes_nothing(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side, so the alarm is not simply always firing."""
    from src.services import notification_triggers

    monkeypatch.setattr(notification_triggers, "DISCOVERY_SILENCE_ALERT_KEY", _fresh_cooldown())
    sent: list[uuid.UUID] = []

    async def _record(_s: object, user_id: uuid.UUID, *_a: object, **_k: object) -> int:
        sent.append(user_id)
        return 1

    monkeypatch.setattr(notification_triggers, "send_notification", _record)

    await _site_admin(session)
    league = await _league_with_members(session, 3)
    await _round(
        session,
        league,
        date(2026, 9, 12),
        status=GameweekStatus.open,
        locks_at=NOW + timedelta(days=1),
        created_at=NOW - timedelta(hours=2),
    )
    await session.flush()

    # This league is not one of the ones going without — asserted the way the rest of
    # this module does, because `discovery_health` reads the **whole deployment** and a
    # shared test database always holds somebody else's silent league.
    live = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)
    assert league.slug not in {entry.slug for entry in live.leagues_without_open_round}

    # And a healthy read sends nothing, which the trigger decides for itself rather than
    # trusting its caller to have checked.
    healthy = DiscoveryHealth(
        newest_round_created_at=NOW - timedelta(hours=2),
        hours_since_newest_round=2.0,
        stale_after_hours=STALE_AFTER,
        leagues_without_open_round=(),
    )
    assert healthy.alarm is False
    assert await notification_triggers.notify_discovery_silence(session, healthy) is False
    assert sent == []


@needs_db
async def test_the_push_names_the_leagues_going_without(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An alert that says only 'something is wrong' is one nobody can act on at 7am."""
    from src.services import notification_triggers

    monkeypatch.setattr(notification_triggers, "DISCOVERY_SILENCE_ALERT_KEY", _fresh_cooldown())
    bodies: list[str] = []

    async def _record(
        _s: object, _uid: uuid.UUID, _title: str, body: str, *_a: object, **_k: object
    ) -> int:
        bodies.append(body)
        return 1

    monkeypatch.setattr(notification_triggers, "send_notification", _record)

    await _site_admin(session)
    await session.flush()

    # Built rather than read. `discovery_health` reads the whole deployment, so in the
    # full suite the real read names whichever leagues other modules left silent — which
    # says nothing about the copy this test is here for.
    starved = DiscoveryHealth(
        newest_round_created_at=NOW - timedelta(days=30),
        hours_since_newest_round=720.0,
        stale_after_hours=STALE_AFTER,
        leagues_without_open_round=(
            SilentLeague(
                league_id=uuid.uuid4(), slug="quiet-ones", name="The Quiet Ones", members=4
            ),
            SilentLeague(league_id=uuid.uuid4(), slug="second", name="Second Division", members=9),
        ),
    )

    assert await notification_triggers.notify_discovery_silence(session, starved) is True
    assert bodies, "nothing was sent"
    assert "The Quiet Ones" in bodies[0]
    assert "(4)" in bodies[0], "the member count is what makes it urgent"
    assert "Second Division" in bodies[0]


@needs_db
async def test_the_push_does_not_list_every_starved_league(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A notification body is a tray entry, not a report."""
    from src.services import notification_triggers

    monkeypatch.setattr(notification_triggers, "DISCOVERY_SILENCE_ALERT_KEY", _fresh_cooldown())
    bodies: list[str] = []

    async def _record(
        _s: object, _uid: uuid.UUID, _title: str, body: str, *_a: object, **_k: object
    ) -> int:
        bodies.append(body)
        return 1

    monkeypatch.setattr(notification_triggers, "send_notification", _record)
    await _site_admin(session)
    await session.flush()

    many = DiscoveryHealth(
        newest_round_created_at=None,
        hours_since_newest_round=None,
        stale_after_hours=STALE_AFTER,
        leagues_without_open_round=tuple(
            SilentLeague(league_id=uuid.uuid4(), slug=f"l{n}", name=f"League {n}", members=n + 1)
            for n in range(9)
        ),
    )

    assert await notification_triggers.notify_discovery_silence(session, many) is True
    assert "League 0" in bodies[0]
    assert "and 6 more" in bodies[0]
    assert "League 8" not in bodies[0]


@needs_db
async def test_the_cooldown_is_durable_rather_than_in_process(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why it is a rate-limit counter and not a timer.

    The failure this alarm guards ran for a week. A cooldown held in process forgets on
    every release, and this deployment releases often — so the alert would come back with
    each one and be muted for exactly the wrong reason.
    """
    from src.models.rate_limit import RateLimitCounter
    from src.rate_limit import durable_bucket_key
    from src.services import notification_triggers

    key = _fresh_cooldown()
    monkeypatch.setattr(notification_triggers, "DISCOVERY_SILENCE_ALERT_KEY", key)
    monkeypatch.setattr(notification_triggers, "send_notification", AsyncMock(return_value=1))

    await _site_admin(session)
    await _league_with_members(session, 2)
    await session.flush()
    health = await discovery_health(session, NOW, stale_after_hours=STALE_AFTER)

    assert await notification_triggers.notify_discovery_silence(session, health) is True

    stored = await session.execute(
        select(func.count())
        .select_from(RateLimitCounter)
        .where(RateLimitCounter.bucket_key == durable_bucket_key(key))
    )
    assert stored.scalar_one() == 1, "the cooldown left nothing behind to survive a restart"
