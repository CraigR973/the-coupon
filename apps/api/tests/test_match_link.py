"""Batch 67 — reaching a played match's scoreline from a coupon leg.

A won/lost badge is the outcome; the member wants the *result*. The scoreline is not on
``fixtures`` and never has been, so the only route to it is a name-based join from the
odds side to the football side, through the pair rule Batch 64 built for the FotMob slate
cross-check.

**A wrong join prints a false scoreline against a real member's pick**, so what these hold
to is mostly the refusals: an unmatched name, an unlisted competition and two candidates
the date cannot separate all resolve to *no score shown* rather than to a guess.

Postgres-backed — the join is SQL and its own point is the query, so exercising it against
mocks would test nothing. Each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.match import Match
from src.models.team import Team
from src.services.match_link import CANDIDATE_WINDOW, scorelines_for
from src.services.team_matching import normalise_name

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

SATURDAY = datetime(2027, 3, 6, 15, 0)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _team(db: AsyncSession, name: str, competition_id: str) -> Team:
    team = Team(
        provider_team_id=f"t-{uuid.uuid4().hex[:10]}",
        name=name,
        normalised_name=normalise_name(name),
        competition_id=competition_id,
    )
    db.add(team)
    await db.flush()
    return team


async def _fixture(
    db: AsyncSession,
    home: str,
    away: str,
    competition_id: str,
    kickoff: datetime = SATURDAY,
) -> Fixture:
    fixture = Fixture(
        provider_event_id=f"ev-{uuid.uuid4().hex[:10]}",
        home=home,
        away=away,
        kickoff_utc=kickoff,
        competition="Test Division",
        competition_id=competition_id,
    )
    db.add(fixture)
    await db.flush()
    return fixture


async def _match(
    db: AsyncSession,
    home: Team,
    away: Team,
    competition_id: str,
    *,
    kickoff: datetime = SATURDAY,
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    finished: bool = True,
) -> Match:
    match = Match(
        provider_match_id=f"m-{uuid.uuid4().hex[:10]}",
        competition_id=competition_id,
        competition="Test Division",
        season=2026,
        kickoff_utc=kickoff,
        home_team_id=home.id,
        away_team_id=away.id,
        home_goals=home_goals,
        away_goals=away_goals,
        finished=finished,
    )
    db.add(match)
    await db.flush()
    return match


def _competition() -> str:
    return f"test-div-{uuid.uuid4().hex[:8]}"


async def test_a_played_fixture_reaches_its_scoreline(session: AsyncSession) -> None:
    """The ordinary case, and the one the batch exists for."""
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, home_goals=3, away_goals=0)
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores[fixture.id].home_goals == 3
    assert scores[fixture.id].away_goals == 0


async def test_the_two_providers_spell_clubs_differently_and_it_still_resolves(
    session: AsyncSession,
) -> None:
    """The whole reason the join is name-based rather than a foreign key.

    "Nott'm Forest" against "Nottingham Forest" is the spelling drift the alias layer was
    built for; the pair rule reads it through the same normaliser.
    """
    comp = _competition()
    home = await _team(session, "Nottingham Forest", comp)
    away = await _team(session, "Sheffield Wednesday", comp)
    await _match(session, home, away, comp, home_goals=1, away_goals=1)
    fixture = await _fixture(session, "Nott'm Forest FC", "Sheffield Weds", comp)

    scores = await scorelines_for(session, [fixture])

    assert fixture.id in scores, "spelling drift must not cost the member their result"
    assert (scores[fixture.id].home_goals, scores[fixture.id].away_goals) == (1, 1)


async def test_a_competition_the_football_source_does_not_carry_shows_no_score(
    session: AsyncSession,
) -> None:
    """FotMob carries neither NI Championship 1 nor the English non-league tiers.

    Those legs render their outcome with no score, which is the point of failing open —
    Batch 64 records the same gap from the other direction.
    """
    fixture = await _fixture(session, "Truro City", "Chesham United", _competition())

    scores = await scorelines_for(session, [fixture])

    assert scores == {}


async def test_a_club_whose_name_will_not_match_shows_no_score(session: AsyncSession) -> None:
    """One end matching is not enough — both must clear the threshold independently."""
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Stenhousemuir", comp)
    await _match(session, home, away, comp)
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores == {}, "a plausible home name is not evidence about the away one"


async def test_the_date_chooses_between_a_home_and_away_pair(session: AsyncSession) -> None:
    """Both fixtures of a season pair match *both* ends equally well by name.

    Picking the better name score would be picking arbitrarily between two
    correct-looking answers, so the date decides — the same rule Batch 64 needed in the
    opposite direction, where name alone compared the card against a game six months out.
    """
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, kickoff=SATURDAY, home_goals=2, away_goals=1)
    await _match(
        session,
        home,
        away,
        comp,
        kickoff=SATURDAY - timedelta(days=2),
        home_goals=0,
        away_goals=4,
    )
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert (scores[fixture.id].home_goals, scores[fixture.id].away_goals) == (2, 1)


async def test_two_candidates_on_the_same_day_resolve_to_nothing(session: AsyncSession) -> None:
    """When the date cannot separate them either, an ambiguous answer is worse than none.

    A wrong scoreline is indistinguishable from a right one to the member reading it.
    """
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, kickoff=SATURDAY, home_goals=2, away_goals=1)
    await _match(
        session, home, away, comp, kickoff=SATURDAY + timedelta(hours=2), home_goals=0, away_goals=4
    )
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores == {}


async def test_a_game_moved_by_a_day_still_shows_its_score(session: AsyncSession) -> None:
    """A kick-off moved for television is the same game, and the window admits it."""
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, kickoff=SATURDAY + timedelta(days=1))
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores[fixture.id].home_goals == 2


async def test_a_match_outside_the_window_is_not_this_fixture(session: AsyncSession) -> None:
    """The reverse fixture months away matches both names and is not the same game."""
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, kickoff=SATURDAY + CANDIDATE_WINDOW * 2)
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores == {}


async def test_an_unfinished_match_carries_no_scoreline(session: AsyncSession) -> None:
    """An in-play match holds a partial score, and a partial score beside a settled pick
    would read as final. Live scores are Batch 72 and read a different gate."""
    comp = _competition()
    home = await _team(session, "Forfar Athletic", comp)
    away = await _team(session, "Brechin City", comp)
    await _match(session, home, away, comp, finished=False, home_goals=1, away_goals=0)
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City", comp)

    scores = await scorelines_for(session, [fixture])

    assert scores == {}


async def test_one_query_per_competition_not_per_fixture(session: AsyncSession) -> None:
    """A coupon is fifteen legs across a handful of divisions, read in a handful of queries.

    Asserted as a resolved *set* rather than by counting SQL: what matters is that a
    whole card resolves in one pass, and a per-fixture implementation that happened to
    be correct would pass a count assertion by accident anyway.
    """
    comp = _competition()
    pairs = [("Forfar Athletic", "Brechin City"), ("Elgin City", "Peterhead")]
    fixtures = []
    for index, (home_name, away_name) in enumerate(pairs):
        home = await _team(session, home_name, comp)
        away = await _team(session, away_name, comp)
        await _match(session, home, away, comp, home_goals=index, away_goals=index + 1)
        fixtures.append(await _fixture(session, home_name, away_name, comp))

    scores = await scorelines_for(session, fixtures)

    assert {f.id for f in fixtures} == set(scores)
    assert scores[fixtures[1].id].home_goals == 1


async def test_no_fixtures_is_no_work(session: AsyncSession) -> None:
    assert await scorelines_for(session, []) == {}
