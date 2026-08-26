"""Batch 80 — form on the leaderboard.

Every figure the table carried was a season aggregate: ``standings_by_league`` collapses
every settled pick into one row per member, so somebody who has scored nothing since July
and somebody who has won the last four rounds read identically on all of them.

The two things worth pinning here are the ones that would be quietly wrong rather than
loudly broken: a **void** round is neither a win nor a loss and must not vanish from the
run, and the run must be sliced by the database rather than by Python, or a leaderboard's
cost grows with how long the league has been playing.

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
from src.services.scoring import RECENT_FORM_ROUNDS, standings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


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
    league = League(
        slug=f"b80-{uuid.uuid4().hex[:8]}",
        name=f"B80 {uuid.uuid4().hex[:4]}",
        created_by=members[0].id,
    )
    db.add(league)
    await db.flush()
    for person in members:
        db.add(LeagueMembership(league_id=league.id, player_id=person.id))
    await db.flush()
    return league


async def _settled_round(db: AsyncSession, league: League, *, days_ago: int) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=date.today() - timedelta(days=days_ago),
        status=GameweekStatus.settled,
        locks_at_utc=_now() - timedelta(days=days_ago + 1),
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
    status: PickStatus,
    points: int | None = None,
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
            odds_at_pick=Decimal("2.00"),
            points_awarded=points,
            status=status,
        )
    )
    await db.flush()


async def _row(db: AsyncSession, league: League, person: Profile):  # noqa: ANN202
    table = await standings(db, league.id)
    return next(row for row in table if row.player_id == str(person.id))


async def test_a_void_round_is_neither_a_win_nor_a_loss_and_stays_in_the_run(
    session: AsyncSession,
) -> None:
    """Dropping it would make three rounds look like two and shift every pip along."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    for days_ago, status, points in (
        (15, PickStatus.won, 20),
        (8, PickStatus.void, None),
        (1, PickStatus.lost, None),
    ):
        gameweek = await _settled_round(session, league, days_ago=days_ago)
        await _pick(session, league, gameweek, alice, status=status, points=points)
    await session.flush()

    run = (await _row(session, league, alice)).recent_form

    assert [entry.status for entry in run] == ["lost", "void", "won"], "most recent first"
    assert [entry.points for entry in run] == [0, 0, 20]


async def test_the_run_covers_the_last_five_and_the_newest_is_first(
    session: AsyncSession,
) -> None:
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    for week in range(8):
        gameweek = await _settled_round(session, league, days_ago=(8 - week) * 7)
        await _pick(session, league, gameweek, alice, status=PickStatus.won, points=week)
    await session.flush()

    run = (await _row(session, league, alice)).recent_form

    assert len(run) == RECENT_FORM_ROUNDS
    assert [entry.points for entry in run] == [7, 6, 5, 4, 3], "newest first, oldest dropped"
    assert run[0].starts_on > run[-1].starts_on


async def test_a_member_with_fewer_rounds_than_the_window_gets_what_they_have(
    session: AsyncSession,
) -> None:
    """No padding: a member who has played twice has a run of two, not three blanks."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    for days_ago in (8, 1):
        gameweek = await _settled_round(session, league, days_ago=days_ago)
        await _pick(session, league, gameweek, alice, status=PickStatus.won, points=20)
    await session.flush()

    assert len((await _row(session, league, alice)).recent_form) == 2


async def test_a_member_who_has_never_picked_has_an_empty_run(session: AsyncSession) -> None:
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    league = await _league(session, [alice, bob])
    gameweek = await _settled_round(session, league, days_ago=1)
    await _pick(session, league, gameweek, alice, status=PickStatus.won, points=20)
    await session.flush()

    assert (await _row(session, league, bob)).recent_form == []


async def test_an_unsettled_round_is_not_form_yet(session: AsyncSession) -> None:
    """A pick that has not been resolved says nothing about how the member is playing."""
    alice = await _profile(session, "alice")
    league = await _league(session, [alice])
    settled = await _settled_round(session, league, days_ago=8)
    await _pick(session, league, settled, alice, status=PickStatus.won, points=20)
    running = Gameweek(
        league_id=league.id,
        starts_on=date.today(),
        status=GameweekStatus.locked,
        locks_at_utc=_now() - timedelta(hours=1),
    )
    session.add(running)
    await session.flush()
    await _pick(session, league, running, alice, status=PickStatus.pending)
    await session.flush()

    run = (await _row(session, league, alice)).recent_form

    assert [entry.status for entry in run] == ["won"]


async def test_one_leagues_form_never_leaks_into_another(session: AsyncSession) -> None:
    """A member plays several leagues at once and each is its own game."""
    alice = await _profile(session, "alice")
    first = await _league(session, [alice])
    second = await _league(session, [alice])
    first_round = await _settled_round(session, first, days_ago=1)
    await _pick(session, first, first_round, alice, status=PickStatus.won, points=50)
    second_round = await _settled_round(session, second, days_ago=1)
    await _pick(session, second, second_round, alice, status=PickStatus.lost)
    await session.flush()

    assert [e.points for e in (await _row(session, first, alice)).recent_form] == [50]
    assert [e.status for e in (await _row(session, second, alice)).recent_form] == ["lost"]


async def test_the_standings_query_count_does_not_grow_with_the_league(
    session: AsyncSession,
) -> None:
    """Two queries for a table, whatever its size: the aggregate, and the form window.

    The run is sliced by ``row_number()`` in the database rather than by truncating a
    season in Python, so this holds as the league keeps playing as well as as it grows.
    """
    people = [await _profile(session, f"p{n}") for n in range(6)]
    league = await _league(session, people)
    for week in range(6):
        gameweek = await _settled_round(session, league, days_ago=(6 - week) * 7)
        for person in people:
            await _pick(session, league, gameweek, person, status=PickStatus.won, points=10)
    await session.flush()

    counted: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        counted.append(statement)

    from sqlalchemy import event

    # `get_bind()` on an AsyncSession hands back the *sync* Engine underneath it, which
    # is the one the event system listens on.
    sync_engine = session.get_bind()
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        table = await standings(session, league.id)
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)

    assert len(table) == 6
    assert all(len(row.recent_form) == RECENT_FORM_ROUNDS for row in table)
    selects = [s for s in counted if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2, f"expected the aggregate and the form window, got {selects}"
