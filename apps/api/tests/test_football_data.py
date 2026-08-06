"""Football-data ingestion and reads (Batch 16).

The constraint this whole batch is shaped around is a number: API-Football's free plan
allows **100 requests a day**, a fifth of the odds source's. So the request arithmetic is
asserted here rather than left in a comment — a competition costs two requests, a run is
capped at a number of competitions, and the cap is only safe because they rotate.

The other half is the round trip a member actually sees. The odds provider spells a club
"Arsenal" and the football provider spells it "Arsenal FC", and a form line has to survive
that. :class:`~src.services.fake_football.FakeFootballData` is deliberately spelled the
second way, so every ingestion test here exercises the reconciliation layer too.

Postgres-backed from the ingestion section onwards, because everything below it is a claim
about which rows exist afterwards.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.standing import Standing
from src.services.fake_football import (
    ARSENAL,
    CHELSEA,
    LIVERPOOL,
    SAMPLE_EPL,
    SAMPLE_SEASON,
    SAMPLE_SL2,
    FakeFootballData,
)
from src.services.football_data import (
    CompetitionSync,
    FormMatch,
    backfill_season,
    fixture_context,
    form_string,
    league_tables,
    pooled_competitions,
    recent_results,
    season_or_default,
    sync_competition,
    sync_football_data,
)
from src.services.football_provider import (
    CompetitionKey,
    FootballDataAPIError,
    FormResult,
    LeagueTable,
    MatchResult,
    current_season,
)

# The odds provider names every league "<Country> - <Competition>", and the fake looks its
# canned data up by the second half — so these are the names a real slate would carry.
EPL_NAME = f"England - {SAMPLE_EPL}"
SL2_NAME = f"Scotland - {SAMPLE_SL2}"


# ── Season naming and form strings (no database) ───────────────────────────────


def _form_match(result: FormResult) -> FormMatch:
    return FormMatch(
        match_id=str(uuid.uuid4()),
        kickoff_utc=datetime(2026, 5, 2, 14, 0),
        opponent="Someone",
        home=True,
        goals_for=1 if result is FormResult.WIN else 0,
        goals_against=1 if result is FormResult.LOSS else 0,
        result=result,
    )


def test_an_explicit_season_is_taken_as_given() -> None:
    """Backfilling a finished season is why this is configurable at all."""
    assert season_or_default(2025) == 2025


def test_no_configured_season_means_the_one_today_falls_in() -> None:
    assert season_or_default(None) == current_season()


def test_a_form_line_prints_the_newest_match_last() -> None:
    """Matches arrive newest-first, because that is the order they are trimmed in; every
    football table in the world prints them the other way round."""
    newest_first = [
        _form_match(FormResult.WIN),
        _form_match(FormResult.DRAW),
        _form_match(FormResult.LOSS),
    ]
    assert form_string(newest_first) == "LDW"


def test_a_club_with_no_finished_matches_has_no_form_line() -> None:
    assert form_string([]) == ""


# ── Postgres-backed ────────────────────────────────────────────────────────────

pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


class CountingFootballData(FakeFootballData):
    """The canned provider with its upstream requests counted.

    Each method here is one request against a hundred-a-day allowance, so the call log is
    the thing under test rather than an implementation detail. ``unavailable`` makes a
    competition fail outright, which is how a provider that has stopped carrying one
    division is simulated.
    """

    def __init__(
        self,
        *,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        results: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        season: int = SAMPLE_SEASON,
    ) -> None:
        super().__init__(tables=tables, results=results, season=season)
        self.table_calls: list[str] = []
        self.result_calls: list[str] = []
        self.unavailable: set[str] = set()

    @property
    def requests(self) -> int:
        return len(self.table_calls) + len(self.result_calls)

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        self.table_calls.append(competition.slug)
        if competition.slug in self.unavailable:
            raise FootballDataAPIError(f"no route to {competition.slug}")
        return await super().fetch_table(competition, season)

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        self.result_calls.append(competition.slug)
        if competition.slug in self.unavailable:
            raise FootballDataAPIError(f"no route to {competition.slug}")
        return await super().fetch_results(competition, season, since=since, until=until)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Rolls back on exit — ingestion flushes, so rows are visible here and vanish after."""
    async with AsyncSessionLocal() as s:
        try:
            yield s
        finally:
            await s.rollback()


def _epl(tag: str) -> CompetitionKey:
    return CompetitionKey(slug=f"england-premier-league-{tag}", name=EPL_NAME)


def _sl2(tag: str) -> CompetitionKey:
    return CompetitionKey(slug=f"scotland-league-two-{tag}", name=SL2_NAME)


def _cup(tag: str) -> CompetitionKey:
    """A competition the provider carries nothing for — a cup has no table at all."""
    return CompetitionKey(slug=f"england-county-cup-{tag}", name="England - Some County Cup")


def _table_of(*clubs: tuple[str, str]) -> dict[str, list[dict[str, Any]]]:
    """A hand-built Premier League table, for asserting what a *shorter* one does."""
    return {
        SAMPLE_EPL: [
            {
                "position": position,
                "team": {"provider_team_id": provider_id, "name": name},
                "played": 10,
                "won": 5,
                "drawn": 2,
                "lost": 3,
                "goals_for": 15,
                "goals_against": 10,
                "points": 17,
                "form": "WDLWW",
            }
            for position, (provider_id, name) in enumerate(clubs, start=1)
        ]
    }


async def _pool(
    session: AsyncSession,
    competition: CompetitionKey,
    *,
    kickoff: datetime,
    teams: Sequence[tuple[str, str]] = (("Arsenal", "Chelsea"),),
) -> list[Fixture]:
    """Put fixtures in the shared pool, spelled the way the *odds* provider spells them."""
    rows = [
        Fixture(
            provider_event_id=f"ev-{uuid.uuid4().hex[:12]}",
            home=home,
            away=away,
            kickoff_utc=kickoff,
            competition=competition.name,
            competition_id=competition.slug,
        )
        for home, away in teams
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def _run(
    session: AsyncSession,
    provider: CountingFootballData,
    *,
    today: date,
    limit: int,
) -> list[CompetitionSync]:
    return await sync_football_data(
        session, provider, season=SAMPLE_SEASON, limit=limit, lookback_days=30, today=today
    )


async def _stored_table(session: AsyncSession, competition: CompetitionKey) -> list[Standing]:
    rows = await session.execute(
        select(Standing)
        .where(Standing.competition_id == competition.slug)
        .order_by(Standing.position)
    )
    return list(rows.scalars().all())


async def _as_of(session: AsyncSession, competition: CompetitionKey) -> datetime:
    rows = await session.execute(
        select(Standing.updated_at).where(Standing.competition_id == competition.slug)
    )
    return max(rows.scalars().all())


# Far enough ahead that the pool a run sees is only ever the one the test built.
FUTURE_TODAY = date(2030, 6, 15)
FUTURE_KICKOFF = datetime(2030, 6, 12, 14, 0)


# ── The request budget ─────────────────────────────────────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_competition_costs_two_upstream_requests(session: AsyncSession) -> None:
    """One table and one results page — the unit the per-run cap counts.

    Thirty competitions is therefore sixty requests, plus the adapter's one catalogue
    lookup, which is what makes a full daily sweep fit inside a hundred.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()

    await sync_competition(session, provider, epl, SAMPLE_SEASON)

    assert provider.requests == 2
    assert provider.table_calls == [epl.slug]
    assert provider.result_calls == [epl.slug]


@pytest_db
@pytest.mark.asyncio
async def test_a_run_is_capped_and_takes_the_never_synced_competitions_first(
    session: AsyncSession,
) -> None:
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF)
    provider = CountingFootballData.with_sample_data()

    first = await _run(session, provider, today=FUTURE_TODAY, limit=1)
    second = await _run(session, provider, today=FUTURE_TODAY, limit=1)

    assert len(first) == 1
    assert len(second) == 1
    assert {first[0].competition_id, second[0].competition_id} == {epl.slug, sl2.slug}
    assert provider.requests == 4  # two competitions × two requests, nothing spent twice


@pytest_db
@pytest.mark.asyncio
async def test_the_tail_keeps_rotating_once_every_competition_has_been_synced(
    session: AsyncSession,
) -> None:
    """The cap is only safe while the ordering keeps moving.

    After the first pass there are no never-synced competitions left to sort to the front,
    so the rotation rests entirely on a re-sync advancing ``standings.updated_at``. If it
    did not, the head of the list would be refreshed every morning and everything past the
    cap would never be looked at again — the exact starvation the ordering exists to stop.
    """
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF)
    provider = CountingFootballData.with_sample_data()

    picked = [
        (await _run(session, provider, today=FUTURE_TODAY, limit=1))[0].competition_id
        for _ in range(4)
    ]

    assert picked[0] != picked[1], "the first pass must reach both"
    assert picked[2] == picked[0], "then come back to the one synced longest ago"
    assert picked[3] == picked[1], "and keep alternating rather than starving one"


@pytest_db
@pytest.mark.asyncio
async def test_re_syncing_a_table_advances_its_as_of_time(session: AsyncSession) -> None:
    """The screens print this as "as of", so it has to mean "when we last asked" — not
    "when we first stored a row", which is what an unstamped ``updated_at`` would give."""
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()

    await sync_competition(session, provider, epl, SAMPLE_SEASON)
    first = await _as_of(session, epl)
    await sync_competition(session, provider, epl, SAMPLE_SEASON)
    second = await _as_of(session, epl)

    assert second > first


@pytest_db
@pytest.mark.asyncio
async def test_the_pool_orders_never_synced_competitions_ahead_of_synced_ones(
    session: AsyncSession,
) -> None:
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin City"),))
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    ordered = [
        competition.slug
        for competition in await pooled_competitions(session, since=date(2030, 6, 1))
        if competition.slug in {epl.slug, sl2.slug}
    ]

    assert ordered == [sl2.slug, epl.slug]


# ── What ingestion writes ──────────────────────────────────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_table_is_replaced_rather_than_merged(session: AsyncSession) -> None:
    """A club that leaves the table has to leave the stored one.

    Expulsion and restructuring are rare, and that is exactly when a stale row is most
    visible: it would sit in the listing forever at whatever position it last held.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)
    assert len(await _stored_table(session, epl)) == 5

    shortened = CountingFootballData(tables=_table_of(ARSENAL, CHELSEA, LIVERPOOL))
    await sync_competition(session, shortened, epl, SAMPLE_SEASON)

    remaining = await _stored_table(session, epl)
    assert [row.position for row in remaining] == [1, 2, 3]


@pytest_db
@pytest.mark.asyncio
async def test_ingesting_the_same_results_twice_writes_no_duplicates(
    session: AsyncSession,
) -> None:
    """The daily window overlaps itself by design, so every run re-sees recent matches."""
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()

    first = await sync_competition(session, provider, epl, SAMPLE_SEASON)
    await sync_competition(session, provider, epl, SAMPLE_SEASON)

    assert first.matches == 8
    assert len(await recent_results(session, [epl], limit=100)) == 8


@pytest_db
@pytest.mark.asyncio
async def test_a_competition_the_provider_does_not_carry_is_reported_not_raised(
    session: AsyncSession,
) -> None:
    """No source covers every competition the odds provider prices, and a cup has no table
    at all. That is a coverage fact for the run's log, not a failure."""
    report = await sync_competition(
        session, CountingFootballData.with_sample_data(), _cup(uuid.uuid4().hex[:8]), SAMPLE_SEASON
    )

    assert report.carried is False
    assert report.table_rows == 0
    assert report.matches == 0


@pytest_db
@pytest.mark.asyncio
async def test_one_competitions_failure_does_not_take_the_run_down(session: AsyncSession) -> None:
    """A provider that has stopped carrying one division must not cost the others theirs."""
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin City"),))
    provider = CountingFootballData.with_sample_data()
    provider.unavailable.add(epl.slug)

    reports = await _run(session, provider, today=FUTURE_TODAY, limit=30)

    assert [report.competition_id for report in reports] == [sl2.slug]
    assert await _stored_table(session, sl2)


@pytest_db
@pytest.mark.asyncio
async def test_the_backfill_reaches_matches_the_daily_window_cannot(
    session: AsyncSession,
) -> None:
    """The window is what keeps the daily job cheap; the backfill is how history arrives."""
    epl = _epl(uuid.uuid4().hex[:8])
    day = date(2026, 5, 3)

    windowed = await sync_competition(
        session,
        CountingFootballData.with_sample_data(),
        epl,
        SAMPLE_SEASON,
        since=day - timedelta(days=1),
        until=day + timedelta(days=1),
    )
    assert windowed.matches == 2  # only the final Saturday

    (backfilled,) = await backfill_season(
        session,
        CountingFootballData.with_sample_data(),
        season=SAMPLE_SEASON,
        competitions=[epl],
    )
    assert backfilled.matches == 8  # the whole canned season


# ── What the screens read back ─────────────────────────────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_table_comes_back_in_position_order(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    (table,) = await league_tables(session, [epl], SAMPLE_SEASON)

    assert [row.position for row in table.rows] == [1, 2, 3, 4, 5]
    assert table.rows[0].team == ARSENAL[1]
    assert table.rows[0].points == 26 * 3 + 8
    assert table.rows[0].goal_difference == 84 - 32
    assert table.updated_at is not None


@pytest_db
@pytest.mark.asyncio
async def test_a_competition_with_nothing_stored_is_omitted_rather_than_empty(
    session: AsyncSession,
) -> None:
    """A cup round has no table, and a placeholder saying so on every screen is noise."""
    tag = uuid.uuid4().hex[:8]
    epl, cup = _epl(tag), _cup(tag)
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    tables = await league_tables(session, [epl, cup], SAMPLE_SEASON)

    assert [table.competition_id for table in tables] == [epl.slug]


@pytest_db
@pytest.mark.asyncio
async def test_a_season_that_was_never_ingested_reads_empty(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    assert await league_tables(session, [epl], SAMPLE_SEASON + 1) == []


@pytest_db
@pytest.mark.asyncio
async def test_recent_results_are_newest_first_and_capped(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    results = await recent_results(session, [epl], limit=3)

    assert len(results) == 3
    assert [result.kickoff_utc for result in results] == sorted(
        (result.kickoff_utc for result in results), reverse=True
    )
    assert results[0].kickoff_utc.date() == date(2026, 5, 2)
    assert (results[0].home, results[0].home_goals) == (CHELSEA[1], 0)
    assert (results[0].away, results[0].away_goals) == (ARSENAL[1], 1)


@pytest_db
@pytest.mark.asyncio
async def test_position_and_form_reach_a_fixture_across_the_spelling_difference(
    session: AsyncSession,
) -> None:
    """The inline half of the batch, end to end.

    The pool says "Arsenal"; the football provider says "Arsenal FC". Ingestion reconciles
    them once, on the scheduler's clock, and the pick screen gets a primary-key lookup.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    (fixture,) = await _pool(session, epl, kickoff=datetime(2026, 8, 8, 14, 0))
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    contexts = await fixture_context(session, [fixture], season=SAMPLE_SEASON, form_matches=5)

    context = contexts[str(fixture.id)]
    assert context.home is not None
    assert context.away is not None
    assert (context.home.name, context.home.position) == (ARSENAL[1], 1)
    assert (context.away.name, context.away.position) == (CHELSEA[1], 2)
    # Most recent last, and derived from `matches` rather than the table's own string.
    assert context.home.form == "WDWW"
    assert context.away.form == "DWWL"
    assert context.home.recent[0].opponent == CHELSEA[1]


@pytest_db
@pytest.mark.asyncio
async def test_form_is_trimmed_to_the_configured_number_of_matches(
    session: AsyncSession,
) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    (fixture,) = await _pool(session, epl, kickoff=datetime(2026, 8, 8, 14, 0))
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    contexts = await fixture_context(session, [fixture], season=SAMPLE_SEASON, form_matches=2)

    context = contexts[str(fixture.id)]
    assert context.home is not None
    assert len(context.home.recent) == 2
    assert context.home.form == "WW"


@pytest_db
@pytest.mark.asyncio
async def test_a_fixture_whose_clubs_are_unknown_simply_has_no_context(
    session: AsyncSession,
) -> None:
    """A form line is an enhancement, not a precondition for picking — so the fixture is
    absent from the map and the card renders exactly as it did before this batch."""
    epl = _epl(uuid.uuid4().hex[:8])
    kickoff = datetime(2026, 8, 8, 14, 0)
    (known,) = await _pool(session, epl, kickoff=kickoff)
    (unknown,) = await _pool(
        session, epl, kickoff=kickoff, teams=(("Ashton Athletic", "Runcorn Linnets"),)
    )
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    contexts = await fixture_context(
        session, [known, unknown], season=SAMPLE_SEASON, form_matches=5
    )

    assert str(known.id) in contexts
    assert str(unknown.id) not in contexts


@pytest_db
@pytest.mark.asyncio
async def test_reading_a_slate_of_no_fixtures_asks_the_database_nothing(
    session: AsyncSession,
) -> None:
    assert await fixture_context(session, [], season=SAMPLE_SEASON, form_matches=5) == {}
    assert await league_tables(session, [], SAMPLE_SEASON) == []
    assert await recent_results(session, [], limit=10) == []
