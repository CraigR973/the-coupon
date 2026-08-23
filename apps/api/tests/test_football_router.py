"""The football-data endpoints (Batch 16, untied from a league in Batch 51).

``GET /football/tables`` and ``/football/results`` — the "own section" half of Batch 16,
the inline half being ``GameweekSlateResponse.fixtures[].context``.

Three things are worth an HTTP-level test rather than a service one. First, the **scope**:
these read the whole shared fixture pool, not the competitions the caller's own league
plays, which is the change Batch 51 made and the one a future refactor could silently
undo. Second, the gating: authentication still applies, membership no longer does — a
league table is public information, and with the competition selection out of the picture
there is no league configuration left to protect. Third, and most important, that
**neither endpoint can reach a provider** — against a hundred-requests-a-day allowance,
one member refreshing a screen that fetched upstream would exhaust the day before lunch,
so that is a property to pin rather than to remember.

Postgres-backed, and it commits: the endpoints open their own session, so rows only this
test's session could see would not exist as far as the app is concerned. Every seed is
keyed on a per-run tag, so repeated runs against one scratch database cannot collide —
and because the pool is shared, every assertion narrows to this run's own competitions
rather than to the length of the whole response.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.match import Match
from src.models.profile import Profile, UserRole
from src.models.standing import Standing
from src.models.team import Team, TeamAlias
from src.services.fake_football import SAMPLE_EPL, SAMPLE_SEASON, SAMPLE_SL2, FakeFootballData
from src.services.football_data import sync_competition
from src.services.football_provider import CompetitionKey

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

EPL_NAME = f"England - {SAMPLE_EPL}"
SL2_NAME = f"Scotland - {SAMPLE_SL2}"

TABLES_URL = "/api/v1/football/tables"
RESULTS_URL = "/api/v1/football/results"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


class Seed:
    """Two ingested competitions in the pool, and a league whose card covers only one."""

    def __init__(
        self,
        league: League,
        member: Profile,
        outsider: Profile,
        played: CompetitionKey,
        unplayed: CompetitionKey,
    ) -> None:
        self.league = league
        self.member = member
        self.outsider = outsider
        self.played = played
        self.unplayed = unplayed

    @property
    def competitions(self) -> tuple[CompetitionKey, CompetitionKey]:
        return (self.played, self.unplayed)

    @property
    def slugs(self) -> set[str]:
        return {competition.slug for competition in self.competitions}

    def auth(self, player: Profile) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(player.id, player.role)}"}

    def ours(self, entries: list[dict[str, object]]) -> list[dict[str, object]]:
        """Only the rows this run seeded — the pool is shared with every other test."""
        return [entry for entry in entries if entry["competition_id"] in self.slugs]


@pytest_asyncio.fixture
async def seed() -> AsyncIterator[Seed]:
    """A league playing one of two pooled competitions. Committed, then removed afterwards."""
    tag = uuid.uuid4().hex[:8]
    played = CompetitionKey(slug=f"england-premier-league-{tag}", name=EPL_NAME)
    unplayed = CompetitionKey(slug=f"scotland-league-two-{tag}", name=SL2_NAME)
    async with AsyncSessionLocal() as session:
        member = Profile(
            display_name=f"member-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player
        )
        outsider = Profile(
            display_name=f"outsider-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player
        )
        session.add_all([member, outsider])
        await session.flush()
        league = League(
            slug=f"football-{tag}",
            name=f"Football {tag}",
            created_by=member.id,
            # One division, explicitly chosen. Before Batch 51 that selection was also
            # the screen's scope; the point of these tests is that it no longer is.
            competitions=[{"slug": played.slug, "name": played.name}],
        )
        session.add(league)
        await session.flush()
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        # The pool is what the untied read walks, and it is fixtures that make a
        # competition part of it. The club spellings are the odds provider's ("Arsenal",
        # not "Arsenal FC"), so reconciliation is doing real work here as in production.
        session.add_all(
            [
                Fixture(
                    provider_event_id=f"ev-epl-{tag}",
                    home="Arsenal",
                    away="Chelsea",
                    kickoff_utc=datetime(2026, 8, 29, 14, 0),
                    competition=played.name,
                    competition_id=played.slug,
                ),
                Fixture(
                    provider_event_id=f"ev-sl2-{tag}",
                    home="Forfar Athletic",
                    away="Brechin City",
                    kickoff_utc=datetime(2026, 8, 29, 14, 0),
                    competition=unplayed.name,
                    competition_id=unplayed.slug,
                ),
            ]
        )
        provider = FakeFootballData.with_sample_data()
        for competition in (played, unplayed):
            await sync_competition(session, provider, competition, SAMPLE_SEASON)
        await session.commit()
        for row in (member, outsider, league):
            await session.refresh(row)

    try:
        yield Seed(league, member, outsider, played, unplayed)
    finally:
        async with AsyncSessionLocal() as session:
            await _tear_down(session, league, [played, unplayed], [member, outsider])
            await session.commit()


async def _tear_down(
    session: AsyncSession,
    league: League,
    competitions: list[CompetitionKey],
    players: list[Profile],
) -> None:
    """Committed rows have to be removed by hand — nothing else in the suite owns them.

    The fixtures matter as much as the rest now: a leaked one would leave a competition in
    the shared pool for every later run to read.
    """
    slugs = [competition.slug for competition in competitions]
    await session.execute(delete(Match).where(Match.competition_id.in_(slugs)))
    await session.execute(delete(Standing).where(Standing.competition_id.in_(slugs)))
    await session.execute(delete(TeamAlias).where(TeamAlias.competition_id.in_(slugs)))
    await session.execute(delete(Team).where(Team.competition_id.in_(slugs)))
    await session.execute(delete(Fixture).where(Fixture.competition_id.in_(slugs)))
    await session.execute(delete(LeagueMembership).where(LeagueMembership.league_id == league.id))
    await session.execute(delete(League).where(League.id == league.id))
    await session.execute(delete(Profile).where(Profile.id.in_([player.id for player in players])))


# ── Scope: the pool, not the caller's card ─────────────────────────────────────


@pytest.mark.asyncio
async def test_the_tables_cover_the_pool_not_the_leagues_own_division(
    client: AsyncClient, seed: Seed
) -> None:
    """The whole point of Batch 51: one division on the card, both in the tables."""
    response = await client.get(
        TABLES_URL, params={"season": SAMPLE_SEASON}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    assert {table["competition_id"] for table in seed.ours(response.json())} == seed.slugs


@pytest.mark.asyncio
async def test_the_results_cover_the_pool_too(client: AsyncClient, seed: Seed) -> None:
    response = await client.get(RESULTS_URL, params={"limit": 100}, headers=seed.auth(seed.member))

    assert response.status_code == 200
    assert {entry["competition_id"] for entry in seed.ours(response.json())} == seed.slugs


@pytest.mark.asyncio
async def test_a_player_in_no_league_at_all_reads_the_same_pool(
    client: AsyncClient, seed: Seed
) -> None:
    """Membership stopped gating this screen when it stopped being a league's screen."""
    response = await client.get(
        TABLES_URL, params={"season": SAMPLE_SEASON}, headers=seed.auth(seed.outsider)
    )

    assert response.status_code == 200
    assert {table["competition_id"] for table in seed.ours(response.json())} == seed.slugs


# ── Tables ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_table_comes_back_in_position_order(client: AsyncClient, seed: Seed) -> None:
    response = await client.get(
        TABLES_URL, params={"season": SAMPLE_SEASON}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    (table,) = (t for t in response.json() if t["competition_id"] == seed.played.slug)
    assert [row["position"] for row in table["rows"]] == [1, 2, 3, 4, 5]
    assert table["rows"][0]["team"] == "Arsenal FC"
    assert table["rows"][0]["goal_difference"] == 84 - 32
    # "as of" — a stored table is only ever as current as the last ingestion run.
    assert datetime.fromisoformat(table["updated_at"])


@pytest.mark.asyncio
async def test_every_row_carries_the_matches_behind_its_form_line(
    client: AsyncClient, seed: Seed
) -> None:
    """Batch 53 — the pips on a table row open, so the endpoint has to serve what is
    behind them. One pip per match, both ways round: a row whose letters outnumbered its
    matches would open onto a panel that answers a different question."""
    response = await client.get(
        TABLES_URL, params={"season": SAMPLE_SEASON}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    (table,) = (t for t in response.json() if t["competition_id"] == seed.played.slug)
    assert all(len(row["recent"]) == len(row["form"]) for row in table["rows"])

    arsenal = next(row for row in table["rows"] if row["team"] == "Arsenal FC")
    newest = arsenal["recent"][0]
    assert (newest["opponent"], newest["home"]) == ("Chelsea FC", False)
    assert (newest["goals_for"], newest["goals_against"], newest["result"]) == (1, 0, "W")


@pytest.mark.asyncio
async def test_a_season_with_nothing_ingested_is_empty_rather_than_an_error(
    client: AsyncClient, seed: Seed
) -> None:
    """A deployment that has not run ingestion yet shows no football, not a 500."""
    response = await client.get(
        TABLES_URL, params={"season": SAMPLE_SEASON + 1}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    assert seed.ours(response.json()) == []


@pytest.mark.asyncio
async def test_an_anonymous_caller_is_refused(client: AsyncClient, seed: Seed) -> None:
    # 403, not 401. `HTTPBearer` answers a missing Authorization header with 403
    # on the pinned fastapi==0.111.0; later versions changed it to 401. This
    # asserts what `requirements.txt` actually ships, which is what production
    # runs. Written against a newer FastAPI, it failed every CI run from Batch 16
    # (2026-08-06) to 2026-08-15 while passing locally — see scripts/ci-local.sh,
    # which now installs the pins so the two cannot diverge again.
    assert (await client.get(TABLES_URL)).status_code == 403
    assert (await client.get(RESULTS_URL)).status_code == 403


@pytest.mark.asyncio
async def test_the_old_league_scoped_routes_are_gone(client: AsyncClient, seed: Seed) -> None:
    """Removed rather than left redirecting: two addresses for one screen is one too many."""
    stale = f"/api/v1/leagues/{seed.league.slug}/football/tables"

    assert (await client.get(stale, headers=seed.auth(seed.member))).status_code == 404


# ── Results ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_results_come_back_newest_first(client: AsyncClient, seed: Seed) -> None:
    response = await client.get(RESULTS_URL, params={"days": 14}, headers=seed.auth(seed.member))

    assert response.status_code == 200
    results = response.json()
    assert [entry["kickoff_utc"] for entry in results] == sorted(
        (entry["kickoff_utc"] for entry in results), reverse=True
    )
    ours = seed.ours(results)
    assert len(ours) == 14  # eight canned Premier League results, six Scottish
    assert ours[0]["kickoff_utc"].startswith("2026-05-02")


@pytest.mark.asyncio
async def test_a_day_of_results_means_every_competition_that_played(
    client: AsyncClient, seed: Seed
) -> None:
    """Batch 71 — the defect the owner reported, at the endpoint.

    The old flat row cap took the newest twenty matches across the whole pool, and the
    screen groups by day and then by competition, so most divisions fell off the end of a
    busy day. Production on 2026-08-23 held 145 finished matches on 2026-08-22 across 17
    competitions, and the newest twenty covered six.

    A day now means *the whole day*: every competition that played on it is present.
    """
    response = await client.get(RESULTS_URL, params={"days": 1}, headers=seed.auth(seed.member))

    assert response.status_code == 200
    ours = seed.ours(response.json())
    newest_day = ours[0]["kickoff_utc"][:10]
    assert {entry["kickoff_utc"][:10] for entry in ours} == {newest_day}
    # Both canned competitions played that day, and both are here — which is exactly what
    # a cap of one or two rows would have hidden.
    assert len({entry["competition_id"] for entry in ours}) == 2


@pytest.mark.asyncio
async def test_the_day_window_is_capped_by_the_endpoint(client: AsyncClient, seed: Seed) -> None:
    """Bounded at the signature so no caller can ask for the whole match table."""
    response = await client.get(RESULTS_URL, params={"days": 500}, headers=seed.auth(seed.member))

    assert response.status_code == 422


# ── The property the whole design rests on ─────────────────────────────────────


@pytest.mark.asyncio
async def test_neither_endpoint_can_reach_a_provider(
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read path is database-only, and has to stay that way.

    API-Football allows a hundred requests a *day*. A screen that fetched upstream would
    be exhausted by one member pulling to refresh — the mistake the odds side had to build
    a whole cache to undo. Booby-trapping the shared session turns "we remembered not to"
    into something that fails loudly the moment someone wires a provider in here.

    Untying the screen raised the stakes rather than lowering them: the read now spans
    every competition in the pool, so an upstream call here would multiply by all of them.
    """
    from src.services import football_session as session_module

    async def forbidden() -> None:
        raise AssertionError("the football read path must never acquire a provider")

    monkeypatch.setattr(session_module.football_session, "acquire", forbidden)

    tables = await client.get(TABLES_URL, headers=seed.auth(seed.member))
    results = await client.get(RESULTS_URL, headers=seed.auth(seed.member))

    assert tables.status_code == 200
    assert results.status_code == 200
