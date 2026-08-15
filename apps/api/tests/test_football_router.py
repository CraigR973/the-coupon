"""The football-data endpoints (Batch 16).

``GET /leagues/{slug}/football/tables`` and ``.../football/results`` — the "own section"
half of the batch, the inline half being ``GameweekSlateResponse.fixtures[].context``.

Two things are worth an HTTP-level test rather than a service one. First, the gating: a
league table is public information, but the *competition selection* is a league's own
configuration, so both endpoints sit behind membership like every other league read.
Second, and more important, that **neither endpoint can reach a provider** — against a
hundred-requests-a-day allowance, one member refreshing a screen that fetched upstream
would exhaust the day before lunch, so that is a property to pin rather than to remember.

Postgres-backed, and it commits: the endpoints open their own session, so rows only this
test's session could see would not exist as far as the app is concerned. Every seed is
keyed on a per-run tag, so repeated runs against one scratch database cannot collide.
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
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.match import Match
from src.models.profile import Profile, UserRole
from src.models.standing import Standing
from src.models.team import Team, TeamAlias
from src.services.fake_football import SAMPLE_EPL, SAMPLE_SEASON, FakeFootballData
from src.services.football_data import sync_competition
from src.services.football_provider import CompetitionKey

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

EPL_NAME = f"England - {SAMPLE_EPL}"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


class Seed:
    """One league with an ingested competition, and the two players used to call it."""

    def __init__(
        self, league: League, member: Profile, outsider: Profile, competition: CompetitionKey
    ) -> None:
        self.league = league
        self.member = member
        self.outsider = outsider
        self.competition = competition

    @property
    def tables_url(self) -> str:
        return f"/api/v1/leagues/{self.league.slug}/football/tables"

    @property
    def results_url(self) -> str:
        return f"/api/v1/leagues/{self.league.slug}/football/results"

    def auth(self, player: Profile) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(player.id, player.role)}"}


@pytest_asyncio.fixture
async def seed() -> AsyncIterator[Seed]:
    """A league playing one ingested competition. Committed, then removed afterwards."""
    tag = uuid.uuid4().hex[:8]
    competition = CompetitionKey(slug=f"england-premier-league-{tag}", name=EPL_NAME)
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
            # An explicit selection, so the screen's scope is the admin's choice rather
            # than whatever rounds happen to have been built.
            competitions=[{"slug": competition.slug, "name": competition.name}],
        )
        session.add(league)
        await session.flush()
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        await sync_competition(
            session, FakeFootballData.with_sample_data(), competition, SAMPLE_SEASON
        )
        await session.commit()
        for row in (member, outsider, league):
            await session.refresh(row)

    try:
        yield Seed(league, member, outsider, competition)
    finally:
        async with AsyncSessionLocal() as session:
            await _tear_down(session, league, competition, [member, outsider])
            await session.commit()


async def _tear_down(
    session: AsyncSession,
    league: League,
    competition: CompetitionKey,
    players: list[Profile],
) -> None:
    """Committed rows have to be removed by hand — nothing else in the suite owns them."""
    await session.execute(delete(Match).where(Match.competition_id == competition.slug))
    await session.execute(delete(Standing).where(Standing.competition_id == competition.slug))
    await session.execute(delete(TeamAlias).where(TeamAlias.competition_id == competition.slug))
    await session.execute(delete(Team).where(Team.competition_id == competition.slug))
    await session.execute(delete(LeagueMembership).where(LeagueMembership.league_id == league.id))
    await session.execute(delete(League).where(League.id == league.id))
    await session.execute(delete(Profile).where(Profile.id.in_([player.id for player in players])))


# ── Tables ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_member_gets_a_table_per_competition_in_position_order(
    client: AsyncClient, seed: Seed
) -> None:
    response = await client.get(
        seed.tables_url, params={"season": SAMPLE_SEASON}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    (table,) = response.json()
    assert table["competition_id"] == seed.competition.slug
    assert [row["position"] for row in table["rows"]] == [1, 2, 3, 4, 5]
    assert table["rows"][0]["team"] == "Arsenal FC"
    assert table["rows"][0]["goal_difference"] == 84 - 32
    # "as of" — a stored table is only ever as current as the last ingestion run.
    assert datetime.fromisoformat(table["updated_at"])


@pytest.mark.asyncio
async def test_a_season_with_nothing_ingested_is_empty_rather_than_an_error(
    client: AsyncClient, seed: Seed
) -> None:
    """A deployment that has not run ingestion yet shows no football, not a 500."""
    response = await client.get(
        seed.tables_url, params={"season": SAMPLE_SEASON + 1}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_a_non_member_cannot_read_a_leagues_football_section(
    client: AsyncClient, seed: Seed
) -> None:
    response = await client.get(seed.tables_url, headers=seed.auth(seed.outsider))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_anonymous_caller_is_refused(client: AsyncClient, seed: Seed) -> None:
    # 403, not 401. `HTTPBearer` answers a missing Authorization header with 403
    # on the pinned fastapi==0.111.0; later versions changed it to 401. This
    # asserts what `requirements.txt` actually ships, which is what production
    # runs. Written against a newer FastAPI, it failed every CI run from Batch 16
    # (2026-08-06) to 2026-08-15 while passing locally — see scripts/ci-local.sh,
    # which now installs the pins so the two cannot diverge again.
    assert (await client.get(seed.tables_url)).status_code == 403


# ── Results ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_results_come_back_newest_first(client: AsyncClient, seed: Seed) -> None:
    response = await client.get(seed.results_url, headers=seed.auth(seed.member))

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 8
    assert [entry["kickoff_utc"] for entry in results] == sorted(
        (entry["kickoff_utc"] for entry in results), reverse=True
    )
    assert results[0]["home"] == "Chelsea FC"
    assert (results[0]["home_goals"], results[0]["away_goals"]) == (0, 1)


@pytest.mark.asyncio
async def test_the_result_limit_is_honoured(client: AsyncClient, seed: Seed) -> None:
    response = await client.get(
        seed.results_url, params={"limit": 3}, headers=seed.auth(seed.member)
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_the_result_limit_is_capped_by_the_endpoint(client: AsyncClient, seed: Seed) -> None:
    """Bounded at the signature so no caller can ask for the whole match table."""
    response = await client.get(
        seed.results_url, params={"limit": 500}, headers=seed.auth(seed.member)
    )

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
    """
    from src.services import football_session as session_module

    async def forbidden() -> None:
        raise AssertionError("the football read path must never acquire a provider")

    monkeypatch.setattr(session_module.football_session, "acquire", forbidden)

    tables = await client.get(seed.tables_url, headers=seed.auth(seed.member))
    results = await client.get(seed.results_url, headers=seed.auth(seed.member))

    assert tables.status_code == 200
    assert results.status_code == 200
