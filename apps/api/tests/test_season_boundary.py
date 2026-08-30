"""Batch 96 — the season boundary, and the archive on the far side of it.

``standings_by_league`` called its result a "Season table" and aggregated every settled
pick a league had ever played. A league in its third year therefore read as one table
three years long: nobody could win a season, because no season ever ended.

The boundary is the definition round numbering already uses —
:func:`~src.services.gameweek.season_bounds` over
:func:`~src.services.football_provider.season_for` — so a round cannot be in one season
for its number and another for the leaderboard. Everything here is about the two ways a
date filter can be wrong rather than about arithmetic, because the points maths is
untouched:

**The boundary is on the join, not on a ``WHERE``.** A member whose only pick was last
season is still a member of this one, on nought, and a filter written the obvious way
would delete them from the table instead of zeroing them. That is the difference between
a leaderboard that says "you have not scored yet" and one that says you are not in the
league, and it is asserted directly.

**Form must stop at the boundary too.** A run reaching back past it describes rounds the
total beside it does not count, and on the opening weekend it would fill four of its five
pips with last season's results.

Dates are derived from ``season_bounds`` rather than from ``date.today()`` offsets: a
round "a week ago" is in the previous season for the first week of July, which would make
these tests pass or fail depending on the day they were run.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.football_provider import current_season
from src.services.gameweek import season_bounds, seasons_played
from src.services.scoring import (
    RECENT_FORM_ROUNDS,
    Standing,
    recent_form_by_league,
    standings,
    standings_by_league,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

THIS_SEASON = current_season()
LAST_SEASON = THIS_SEASON - 1


def _in_season(season: int, *, week: int) -> date:
    """A date ``week`` weeks into ``season``, whatever season is being played today.

    Anchored on the season's own first day so the test data straddles the boundary by
    construction rather than by luck of the calendar.
    """
    first_day, last_day = season_bounds(season)
    day = first_day + timedelta(weeks=week)
    assert first_day <= day <= last_day, "test data must stay inside the season it names"
    return day


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _profile(db: AsyncSession, name: str) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, members: list[Profile]) -> League:
    tag = uuid.uuid4().hex[:8]
    league = League(slug=f"b96-{tag}", name=f"B96 {tag}", created_by=members[0].id)
    db.add(league)
    await db.flush()
    for person in members:
        db.add(LeagueMembership(league_id=league.id, player_id=person.id))
    await db.flush()
    return league


async def _settled_round(db: AsyncSession, league: League, *, on: date) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=on,
        status=GameweekStatus.settled,
        locks_at_utc=_now() - timedelta(days=1),
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


async def _pick(
    db: AsyncSession,
    league: League,
    gameweek: Gameweek,
    person: Profile,
    *,
    status: PickStatus = PickStatus.won,
    points: int | None = 20,
    odds: str = "2.00",
) -> None:
    fixture = Fixture(
        provider_event_id=f"ev-{uuid.uuid4().hex[:10]}",
        home="Forfar",
        away="Brechin",
        kickoff_utc=_now(),
        competition="Scottish League 2",
        competition_id="scotland-league-two",
    )
    db.add(fixture)
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    db.add(
        Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            fixture_id=fixture.id,
            player_id=person.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar",
            odds_at_pick=Decimal(odds),
            points_awarded=points if status is PickStatus.won else None,
            status=status,
        )
    )
    await db.flush()


def _row(table: list[Standing], person: Profile) -> Standing:
    return next(row for row in table if row.player_id == str(person.id))


# ── The boundary ──────────────────────────────────────────────────────────────


async def test_a_round_from_last_season_is_out_of_the_live_table_and_in_the_archived_one(
    session: AsyncSession,
) -> None:
    """The Verification's first bullet: excluded from one table, present in the other.

    Both halves matter. Dropping last season from the live table is only half a season
    boundary — the other half is that the season the member played is still readable
    afterwards, which is what makes this an archive rather than a deletion.
    """
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    old_round = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=10))
    await _pick(session, league, old_round, alice, points=31)
    await session.flush()

    live = _row(await standings(session, league.id), alice)
    archived = _row(await standings(session, league.id, season=LAST_SEASON), alice)

    assert live.total_points == 0, "last season's points are not this season's"
    assert live.picks_played == 0
    assert archived.total_points == 31, "and they have not been thrown away"
    assert archived.picks_played == 1
    assert archived.picks_won == 1


async def test_a_member_who_only_played_last_season_is_still_in_this_season_on_nought(
    session: AsyncSession,
) -> None:
    """The boundary zeroes a member; it must not delete them.

    This is the whole reason the filter sits in the join rather than in a ``WHERE``.
    Written as a ``WHERE`` on the round's date, the aggregate would find no pick row for
    Bob and drop him from the league he is still a member of — a leaderboard that has
    quietly lost a player reads as a bug in membership, not as a season having started.
    """
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    league = await _league(session, [alice, bob])

    old_round = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=20))
    await _pick(session, league, old_round, bob, points=90)
    new_round = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=2))
    await _pick(session, league, new_round, alice, points=15)
    await session.flush()

    live = await standings(session, league.id)

    assert {row.display_name for row in live} == {alice.display_name, bob.display_name}
    assert _row(live, bob).total_points == 0
    assert _row(live, bob).picks_played == 0
    # And last season's runaway leader does not out-rank this season's only scorer.
    assert _row(live, alice).rank == 1
    assert _row(live, bob).rank == 2


async def test_a_league_spanning_the_boundary_totals_correctly_on_both_sides(
    session: AsyncSession,
) -> None:
    """The Verification's second bullet, with the same picks read twice.

    Every figure is recomputed from what was written rather than compared against a
    second copy of the same SQL, so this proves the boundary partitions the picks — no
    round counted twice, none dropped between the two tables.
    """
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])

    last_season_points = [31, 24, 18]
    for week, points in enumerate(last_season_points, start=5):
        gameweek = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=week))
        await _pick(session, league, gameweek, alice, points=points)

    this_season_points = [12, 45]
    for week, points in enumerate(this_season_points, start=1):
        gameweek = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=week))
        await _pick(session, league, gameweek, alice, points=points)
    await session.flush()

    live = _row(await standings(session, league.id), alice)
    archived = _row(await standings(session, league.id, season=LAST_SEASON), alice)

    assert live.total_points == sum(this_season_points)
    assert live.picks_played == len(this_season_points)
    assert live.best_return == max(this_season_points)
    assert archived.total_points == sum(last_season_points)
    assert archived.picks_played == len(last_season_points)
    assert archived.best_return == max(last_season_points)
    # Neither table is the other's leftovers: together they are every pick, once.
    assert live.picks_played + archived.picks_played == 5


async def test_the_last_round_of_a_season_and_the_first_of_the_next_land_either_side(
    session: AsyncSession,
) -> None:
    """The two days the boundary actually falls between — 30 June and 1 July."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    _, last_day = season_bounds(LAST_SEASON)
    first_day, _ = season_bounds(THIS_SEASON)
    assert last_day + timedelta(days=1) == first_day, "the seasons abut, with no gap"

    june = await _settled_round(session, league, on=last_day)
    await _pick(session, league, june, alice, points=7)
    july = await _settled_round(session, league, on=first_day)
    await _pick(session, league, july, alice, points=11)
    await session.flush()

    assert _row(await standings(session, league.id), alice).total_points == 11
    assert _row(await standings(session, league.id, season=LAST_SEASON), alice).total_points == 7


# ── Form (Batch 80) must not span it ──────────────────────────────────────────


async def test_recent_form_stops_at_the_boundary_rather_than_filling_from_last_season(
    session: AsyncSession,
) -> None:
    """The Verification's third bullet.

    The failure this pins is a quiet one: the run is a fixed five long, so a member two
    rounds into a new season would get five pips either way and three of them would be
    describing a season their points total no longer counts.
    """
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])

    for week in range(RECENT_FORM_ROUNDS):
        gameweek = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=week + 10))
        await _pick(session, league, gameweek, alice, points=99)

    for week, points in enumerate([12, 45], start=1):
        gameweek = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=week))
        await _pick(session, league, gameweek, alice, points=points)
    await session.flush()

    run = _row(await standings(session, league.id), alice).recent_form

    assert len(run) == 2, "two rounds played this season is a run of two, not a padded five"
    assert [entry.points for entry in run] == [45, 12], "most recent first"
    assert all(entry.points != 99 for entry in run)


async def test_an_archived_season_carries_the_form_of_that_season(
    session: AsyncSession,
) -> None:
    """The archive is the same table, so it is the same row — form included."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    for week, status in enumerate([PickStatus.won, PickStatus.lost, PickStatus.void], start=10):
        gameweek = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=week))
        await _pick(session, league, gameweek, alice, status=status, points=20)
    new_round = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=1))
    await _pick(session, league, new_round, alice)
    await session.flush()

    archived = _row(await standings(session, league.id, season=LAST_SEASON), alice)

    assert [entry.status for entry in archived.recent_form] == ["void", "lost", "won"]


async def test_the_form_query_alone_is_bounded_too(session: AsyncSession) -> None:
    """``recent_form_by_league`` is read directly by nothing today, but it is exported.

    Pinned separately from the table so that a future caller reaching for the run on its
    own cannot get an unbounded one back, which is how the boundary would come apart.
    """
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    old_round = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=30))
    await _pick(session, league, old_round, alice)
    await session.flush()

    assert await recent_form_by_league(session, [league.id]) == {}
    archived = await recent_form_by_league(session, [league.id], season=LAST_SEASON)
    assert len(archived[(league.id, alice.id)]) == 1


# ── The rewind (Batch 79) reads the same season as the table ──────────────────


async def test_the_rewound_table_is_bounded_by_the_same_season_as_the_live_one(
    session: AsyncSession,
) -> None:
    """``routers/me.py`` differences these two tables to say "you moved up two".

    If the boundary applied to one call and not the other, the movement would be
    differenced against a table nobody can open — last season's points minus this
    season's — and would disagree with the leaderboard the member taps through to.
    """
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    league = await _league(session, [alice, bob])

    old_round = await _settled_round(session, league, on=_in_season(LAST_SEASON, week=20))
    await _pick(session, league, old_round, bob, points=500)

    first = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=1))
    await _pick(session, league, first, alice, points=10)
    latest = await _settled_round(session, league, on=_in_season(THIS_SEASON, week=2))
    await _pick(session, league, latest, bob, points=40)
    await session.flush()

    now = (await standings_by_league(session, [league.id]))[league.id]
    before = (await standings_by_league(session, [league.id], [latest.id], with_form=False))[
        league.id
    ]

    # Bob wins the latest round and goes from behind Alice to ahead of her: up one.
    assert _row(before, bob).rank - _row(now, bob).rank == 1
    # Rewinding one round of this season must not uncover last season's 500 points.
    assert _row(before, bob).total_points == 0


# ── The archive's index ───────────────────────────────────────────────────────


async def test_seasons_played_lists_every_season_with_a_settled_round_newest_first(
    session: AsyncSession,
) -> None:
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    for season, rounds in ((LAST_SEASON, 2), (THIS_SEASON, 1)):
        for week in range(rounds):
            gameweek = await _settled_round(session, league, on=_in_season(season, week=week + 1))
            await _pick(session, league, gameweek, alice)
    await session.flush()

    listed = await seasons_played(session, league.id)

    assert [entry.season for entry in listed] == [THIS_SEASON, LAST_SEASON]
    assert [entry.rounds_settled for entry in listed] == [1, 2]
    assert [entry.is_current for entry in listed] == [True, False]


async def test_a_league_that_has_settled_nothing_still_offers_the_current_season(
    session: AsyncSession,
) -> None:
    """The selector opens on this season, so this season has to be in the list."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    await session.flush()

    listed = await seasons_played(session, league.id)

    assert [(entry.season, entry.rounds_settled) for entry in listed] == [(THIS_SEASON, 0)]
    assert listed[0].is_current


async def test_an_unsettled_round_does_not_open_a_season_in_the_archive(
    session: AsyncSession,
) -> None:
    """A season is archived by having been played, not by having been scheduled."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    session.add(
        Gameweek(
            league_id=league.id,
            starts_on=_in_season(LAST_SEASON, week=20),
            status=GameweekStatus.scheduled,
            locks_at_utc=_now() - timedelta(days=1),
        )
    )
    await session.flush()

    assert [entry.season for entry in await seasons_played(session, league.id)] == [THIS_SEASON]


async def test_one_leagues_seasons_are_not_anothers(session: AsyncSession) -> None:
    """A member plays several leagues at once and each is its own game."""
    alice = await _profile(session, "alice")
    first = await _league(session, [alice])
    second = await _league(session, [alice])
    old_round = await _settled_round(session, first, on=_in_season(LAST_SEASON, week=20))
    await _pick(session, first, old_round, alice)
    await session.flush()

    assert [entry.season for entry in await seasons_played(session, first.id)] == [
        THIS_SEASON,
        LAST_SEASON,
    ]
    assert [entry.season for entry in await seasons_played(session, second.id)] == [THIS_SEASON]
