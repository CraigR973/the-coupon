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
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.match import Match
from src.models.standing import Standing
from src.models.team import Team
from src.services.fake_football import (
    ARSENAL,
    CHELSEA,
    EVERTON,
    LIVERPOOL,
    SAMPLE_EPL,
    SAMPLE_SEASON,
    SAMPLE_SL2,
    SPURS,
    FakeFootballData,
)
from src.services.football_data import (
    CompetitionSync,
    FootballSweep,
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
    sync_results,
    team_season_matches,
)
from src.services.football_provider import (
    CompetitionKey,
    FootballDataAPIError,
    FootballDataProvider,
    FormResult,
    LeagueTable,
    MatchResult,
    MatchState,
    TeamRef,
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

    async def fetch_season_matches(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        # Counted as the same one request `fetch_results` was: since Batch 110 the
        # ingestion asks for the season instead of a window, and for FotMob both are
        # the one payload the table already came from. The arithmetic below is unchanged
        # because the *number of requests* is what it was measuring.
        self.result_calls.append(competition.slug)
        if competition.slug in self.unavailable:
            raise FootballDataAPIError(f"no route to {competition.slug}")
        return await super().fetch_season_matches(competition, season)


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
    competition_spacing_seconds: float = 0.0,
    sleeper: Any = None,
) -> list[CompetitionSync]:
    """The reports a run produced. Callers here are about *what was ingested*; the
    run-level verdict Batch 45 added is exercised through :func:`_sweep` instead."""
    return (
        await _sweep(
            session,
            provider,
            today=today,
            limit=limit,
            competition_spacing_seconds=competition_spacing_seconds,
            sleeper=sleeper,
        )
    ).reports


async def _sweep(
    session: AsyncSession,
    provider: FootballDataProvider,
    *,
    today: date,
    limit: int,
    competition_spacing_seconds: float = 0.0,
    sleeper: Any = None,
) -> FootballSweep:
    kwargs: dict[str, Any] = {}
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    return await sync_football_data(
        session,
        provider,
        season=SAMPLE_SEASON,
        limit=limit,
        lookback_days=30,
        today=today,
        competition_spacing_seconds=competition_spacing_seconds,
        **kwargs,
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


@contextmanager
def counted_statements() -> Iterator[list[str]]:
    """Every SQL statement executed inside the block.

    The section above counts *upstream* requests because the provider allows a hundred a
    day. This counts database round trips for the same kind of reason: the football
    screen reads every competition in the pool in one call, so anything per-club in a
    read here is a query multiplied by twenty clubs and then by thirty divisions.
    """
    seen: list[str] = []

    def record(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", record)


# Far enough ahead that the pool a run sees is only ever the one the test built.
FUTURE_TODAY = date(2030, 6, 15)
FUTURE_KICKOFF = datetime(2030, 6, 12, 14, 0)


# ── The request budget ─────────────────────────────────────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_competition_costs_two_upstream_requests(session: AsyncSession) -> None:
    """One table and one match list — the unit the per-run cap counts.

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
async def test_a_scheduled_sweep_waits_between_competitions(session: AsyncSession) -> None:
    """Two upstream calls per competition need a gap to stay below ten a minute."""
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin City"),))
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    reports = await _run(
        session,
        CountingFootballData.with_sample_data(),
        today=FUTURE_TODAY,
        limit=2,
        competition_spacing_seconds=12.0,
        sleeper=record_sleep,
    )

    assert len(reports) == 2
    assert sleeps == [12.0]


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
    """Every run re-sees the whole season by design, so it had better be an upsert.

    The count moved from 8 to 11 in Batch 110: the sweep now writes the canned season's
    three unplayed fixtures as well as its eight results. ``recent_results`` still
    answers 8, which is the point — retention widened and no read did.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()

    first = await sync_competition(session, provider, epl, SAMPLE_SEASON)
    second = await sync_competition(session, provider, epl, SAMPLE_SEASON)

    assert first.matches == 11
    assert second.matches == 11
    stored = await session.execute(select(Match).where(Match.competition_id == epl.slug))
    assert len(stored.scalars().all()) == 11
    assert len(await recent_results(session, [epl], days=14, max_rows=100)) == 8


# ── What a whole run reports about itself (Batch 45) ──────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_sweep_where_every_competition_raised_reports_that_it_attempted_them(
    session: AsyncSession,
) -> None:
    """The shape the job could not see before.

    Every competition raising leaves ``reports`` empty — which is byte-for-byte what an
    empty fixture pool produces, and the opposite verdict. ``attempted`` is the only
    thing that separates them, which is why it is carried rather than derived.
    """
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin City"),))

    provider = CountingFootballData.with_sample_data()
    provider.unavailable = {epl.slug, sl2.slug}

    sweep = await _sweep(session, provider, today=FUTURE_TODAY, limit=30)

    assert sweep.attempted == 2
    assert sweep.reports == []
    assert sweep.failed == 2
    assert sweep.carried_nothing is True


@pytest_db
@pytest.mark.asyncio
async def test_a_sweep_that_reached_every_competition_and_carried_none_is_not_healthy(
    session: AsyncSession,
) -> None:
    """The 2026-08-20 production run, in miniature: nothing raised, nothing landed.

    Two cups have no table and no results, so every competition is reported honestly and
    ``carried`` is 0. That is indistinguishable from a healthy run with an empty card
    unless ``attempted`` is consulted.
    """
    tag = uuid.uuid4().hex[:8]
    first, second = _cup(f"{tag}a"), _cup(f"{tag}b")
    await _pool(session, first, kickoff=FUTURE_KICKOFF)
    await _pool(session, second, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin"),))

    sweep = await _sweep(
        session, CountingFootballData.with_sample_data(), today=FUTURE_TODAY, limit=30
    )

    assert sweep.attempted == 2
    assert len(sweep.reports) == 2  # reached, not raised
    assert sweep.failed == 0
    assert sweep.carried == 0
    assert sweep.carried_nothing is True


@pytest_db
@pytest.mark.asyncio
async def test_a_sweep_over_an_empty_card_is_not_a_failure(session: AsyncSession) -> None:
    """The legitimate zero-work run this must never be confused with."""
    sweep = await _sweep(
        session, CountingFootballData.with_sample_data(), today=FUTURE_TODAY, limit=0
    )

    assert sweep.attempted == 0
    assert sweep.carried_nothing is False


@pytest_db
@pytest.mark.asyncio
async def test_one_competition_carrying_keeps_a_sweep_healthy(session: AsyncSession) -> None:
    """The tolerance the sweep exists for, unchanged: one division the provider dropped
    must not cost the other its table, and the run is still a success."""
    tag = uuid.uuid4().hex[:8]
    epl, sl2 = _epl(tag), _sl2(tag)
    await _pool(session, epl, kickoff=FUTURE_KICKOFF)
    await _pool(session, sl2, kickoff=FUTURE_KICKOFF, teams=(("Forfar Athletic", "Brechin City"),))

    provider = CountingFootballData.with_sample_data()
    provider.unavailable = {sl2.slug}

    sweep = await _sweep(session, provider, today=FUTURE_TODAY, limit=30)

    assert sweep.attempted == 2
    assert sweep.failed == 1
    assert sweep.carried == 1
    assert sweep.carried_nothing is False


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
    """The window keeps a paging provider cheap; the backfill is how its history arrives.

    Respecified by Batch 110 rather than dropped. A source that can hand over the whole
    season in the request the table already cost — FotMob, which is production — is now
    asked for exactly that, so the window bounds nothing for it and the daily sweep is
    the backfill. A source that can only page results still gets the window it was tuned
    for, and for that one the original claim is unchanged; both halves are asserted here.
    """
    tag = uuid.uuid4().hex[:8]
    day = date(2026, 5, 3)

    class PagingProvider(CountingFootballData):
        """api-football's shape: results a page at a time, and no season list at all."""

        async def fetch_season_matches(
            self, competition: CompetitionKey, season: int
        ) -> list[MatchResult]:
            return []

    paging = _epl(f"{tag}-paging")
    windowed = await sync_competition(
        session,
        PagingProvider.with_sample_data(),
        paging,
        SAMPLE_SEASON,
        since=day - timedelta(days=1),
        until=day + timedelta(days=1),
    )
    assert windowed.matches == 2  # only the final Saturday

    (backfilled,) = (
        await backfill_season(
            session,
            PagingProvider.with_sample_data(),
            season=SAMPLE_SEASON,
            competitions=[paging],
        )
    ).reports
    assert backfilled.matches == 8  # the whole canned season, results only

    # And the source that can answer the season ignores the window, which is the point:
    # every fixture still to be played is outside any window ending today.
    whole = _epl(f"{tag}-whole")
    unwindowed = await sync_competition(
        session,
        CountingFootballData.with_sample_data(),
        whole,
        SAMPLE_SEASON,
        since=day - timedelta(days=1),
        until=day + timedelta(days=1),
    )
    assert unwindowed.matches == 11  # eight results and the three fixtures after them


# ── What the screens read back ─────────────────────────────────────────────────


@pytest_db
@pytest.mark.asyncio
async def test_a_table_comes_back_in_position_order(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    (table,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=5)

    assert [row.position for row in table.rows] == [1, 2, 3, 4, 5]
    assert table.rows[0].team == ARSENAL[1]
    assert table.rows[0].points == 26 * 3 + 8
    assert table.rows[0].goal_difference == 84 - 32
    assert table.updated_at is not None


@pytest_db
@pytest.mark.asyncio
async def test_a_table_row_opens_onto_the_matches_its_form_line_is_made_of(
    session: AsyncSession,
) -> None:
    """Batch 53 — the pips on a table row are now a disclosure, so what is behind them
    has to be the same football the letters describe."""
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    (table,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=5)

    arsenal = next(row for row in table.rows if row.team == ARSENAL[1])
    # Four canned matches, newest first: Chelsea (a), Spurs (h), Liverpool (a), Everton (h).
    assert [(match.opponent, match.home) for match in arsenal.recent] == [
        (CHELSEA[1], False),
        (SPURS[1], True),
        (LIVERPOOL[1], False),
        (EVERTON[1], True),
    ]
    # Goals are for-and-against from this club's side, whichever end it played at.
    assert (arsenal.recent[0].goals_for, arsenal.recent[0].goals_against) == (1, 0)
    assert (arsenal.recent[3].goals_for, arsenal.recent[3].goals_against) == (3, 0)
    # And the letters agree with the rows they open onto, rather than with the table
    # string the provider wrote from a different call.
    assert arsenal.form == form_string(arsenal.recent) == "WDWW"


@pytest_db
@pytest.mark.asyncio
async def test_form_on_a_table_is_trimmed_to_the_configured_number_of_matches(
    session: AsyncSession,
) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    (table,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=2)

    arsenal = next(row for row in table.rows if row.team == ARSENAL[1])
    assert [match.opponent for match in arsenal.recent] == [CHELSEA[1], SPURS[1]]
    assert arsenal.form == "WW"


@pytest_db
@pytest.mark.asyncio
async def test_a_whole_table_costs_one_query_for_its_form_however_many_clubs_it_holds(
    session: AsyncSession,
) -> None:
    """One statement for the table, one for every club's form — not one per club.

    A per-club form query would be invisible on the five-row canned table and ruinous on
    the real screen, which reads every division in the pool at once.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)
    await session.flush()  # so the read below is not counting an autoflush of ingestion

    with counted_statements() as statements:
        (table,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=5)

    assert len(table.rows) == 5
    assert all(row.recent for row in table.rows)
    assert len(statements) == 2

    with counted_statements() as without_form:
        (bare,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=0)

    assert [row.recent for row in bare.rows] == [[]] * 5
    assert len(without_form) == 1


@pytest_db
@pytest.mark.asyncio
async def test_a_club_with_a_table_line_but_no_stored_matches_keeps_its_pips_and_opens_nothing(
    session: AsyncSession,
) -> None:
    """The provider writes a form string on the table row itself, and it can outlive the
    matches behind it — a club ingested from `/standings` before any result was carried.
    The letters still show; the disclosure has nothing to open and the client leaves it
    inert rather than opening an empty panel."""
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData(tables=_table_of(("af-991", "Nowhere United")))
    await sync_competition(session, provider, epl, SAMPLE_SEASON)

    (table,) = await league_tables(session, [epl], SAMPLE_SEASON, form_matches=5)

    (row,) = table.rows
    assert row.recent == []
    assert row.form == "WDLWW"  # the string `_table_of` gave the provider


@pytest_db
@pytest.mark.asyncio
async def test_a_competition_with_nothing_stored_is_omitted_rather_than_empty(
    session: AsyncSession,
) -> None:
    """A cup round has no table, and a placeholder saying so on every screen is noise."""
    tag = uuid.uuid4().hex[:8]
    epl, cup = _epl(tag), _cup(tag)
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    tables = await league_tables(session, [epl, cup], SAMPLE_SEASON, form_matches=5)

    assert [table.competition_id for table in tables] == [epl.slug]


@pytest_db
@pytest.mark.asyncio
async def test_a_season_that_was_never_ingested_reads_empty(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    assert await league_tables(session, [epl], SAMPLE_SEASON + 1, form_matches=5) == []


@pytest_db
@pytest.mark.asyncio
async def test_recent_results_are_newest_first_and_bounded_by_days(
    session: AsyncSession,
) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)

    results = await recent_results(session, [epl], days=1, max_rows=100)

    assert [result.kickoff_utc for result in results] == sorted(
        (result.kickoff_utc for result in results), reverse=True
    )
    # One day means *one day of matches*, all of them, rather than one match.
    assert {result.kickoff_utc.date() for result in results} == {date(2026, 5, 2)}
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


# ── Batch 71: a busy Saturday, at the shape production actually holds ──────────
#
# Measured read-only against production on 2026-08-23: 567 finished matches across 18
# competitions, every one inside the 30-day lookback — so the *ingestion* was healthy,
# which Batch 45 is the reason to check rather than assume. 145 of them were on Saturday
# 2026-08-22 across 17 competitions, and the flat `limit=20` returned twenty rows
# covering **six**. Eleven divisions vanished off the end of a global row count, which is
# the "partially there" a member reported.
#
# Reconstructed here at that shape rather than asserted against production, because a
# test that needs a live database is a test that does not run.


async def _busy_day(session: AsyncSession, competitions: int, per_competition: int) -> date:
    """One Saturday played across many divisions, as a real card looks."""
    day = date(2026, 8, 22)
    for index in range(competitions):
        slug = f"busy-{uuid.uuid4().hex[:8]}"
        teams = []
        for side in ("home", "away"):
            team = Team(
                provider_team_id=f"t-{uuid.uuid4().hex[:10]}",
                name=f"{side.title()} {index}",
                normalised_name=f"{side} {index}",
                competition_id=slug,
            )
            session.add(team)
            teams.append(team)
        await session.flush()
        for match_index in range(per_competition):
            session.add(
                Match(
                    provider_match_id=f"m-{uuid.uuid4().hex[:10]}",
                    competition_id=slug,
                    competition=f"Busy Division {index}",
                    season=SAMPLE_SEASON,
                    kickoff_utc=datetime(2026, 8, 22, 14, 0) + timedelta(minutes=match_index),
                    home_team_id=teams[0].id,
                    away_team_id=teams[1].id,
                    home_goals=1,
                    away_goals=0,
                    finished=True,
                )
            )
    await session.flush()
    return day


@pytest_db
@pytest.mark.asyncio
async def test_one_busy_saturday_returns_every_competition_that_played(
    session: AsyncSession,
) -> None:
    """The defect, and the fix, at production's measured shape.

    Seventeen competitions, 145 matches, one day. A flat cap of twenty would return six
    divisions; a day window returns all seventeen.
    """
    await _busy_day(session, competitions=17, per_competition=9)
    keys = [
        CompetitionKey(slug=slug, name=name)
        for slug, name in (
            await session.execute(
                select(Match.competition_id, Match.competition)
                .where(Match.competition.like("Busy Division%"))
                .distinct()
            )
        ).all()
    ]

    results = await recent_results(session, keys, days=1, max_rows=400)

    assert len(results) == 17 * 9
    assert len({entry.competition_id for entry in results}) == 17


@pytest_db
@pytest.mark.asyncio
async def test_the_row_cap_is_a_backstop_and_not_a_page_size(session: AsyncSession) -> None:
    """It exists so a pathological ingestion cannot answer with everything.

    Set absurdly low here to prove it still bites; the shipped value is far above
    anything a real Saturday produces.
    """
    await _busy_day(session, competitions=17, per_competition=9)
    keys = [
        CompetitionKey(slug=slug, name=name)
        for slug, name in (
            await session.execute(
                select(Match.competition_id, Match.competition)
                .where(Match.competition.like("Busy Division%"))
                .distinct()
            )
        ).all()
    ]

    assert len(await recent_results(session, keys, days=1, max_rows=5)) == 5


@pytest_db
@pytest.mark.asyncio
async def test_the_window_counts_days_with_results_not_calendar_days(
    session: AsyncSession,
) -> None:
    """A Wednesday still answers with the weekend.

    Counting calendar days would empty the screen every midweek — production's own
    distribution has days holding one match and days holding 145.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    await sync_competition(session, CountingFootballData.with_sample_data(), epl, SAMPLE_SEASON)
    stored = (
        (await session.execute(select(Match).where(Match.competition_id == epl.slug)))
        .scalars()
        .all()
    )
    # Push the two oldest a month back, leaving a long gap behind the recent ones.
    for match in sorted(stored, key=lambda m: m.kickoff_utc)[:2]:
        match.kickoff_utc -= timedelta(days=30)
    await session.flush()

    # Finished only: since Batch 110 the store also holds fixtures nobody has played, and
    # `recent_results` has never claimed to return those.
    played = [m for m in stored if m.finished]
    days_present = {m.kickoff_utc.date() for m in played}
    results = await recent_results(session, [epl], days=len(days_present), max_rows=400)

    assert len(results) == len(played), "every day that has results is reachable"


@pytest_db
@pytest.mark.asyncio
async def test_reading_a_slate_of_no_fixtures_asks_the_database_nothing(
    session: AsyncSession,
) -> None:
    assert await fixture_context(session, [], season=SAMPLE_SEASON, form_matches=5) == {}
    assert await league_tables(session, [], SAMPLE_SEASON, form_matches=5) == []
    assert await recent_results(session, [], days=3, max_rows=10) == []


# ── The whole season, not just the played part (Batch 110) ────────────────────
#
# The store held finished matches and nothing else, because the FotMob adapter dropped
# every other kind on the way in. That is why it could not answer "what is this club
# playing next", which is the question Batch 111's team page is built on.


def _season_match(
    match_id: str,
    competition: CompetitionKey,
    *,
    day: str,
    home: tuple[str, str],
    away: tuple[str, str],
    state: MatchState,
    home_goals: int | None = None,
    away_goals: int | None = None,
    status: str = "",
) -> MatchResult:
    return MatchResult(
        provider_match_id=match_id,
        competition=competition,
        season=SAMPLE_SEASON,
        kickoff_utc=datetime.fromisoformat(f"{day}T14:00:00+00:00"),
        home=TeamRef(provider_team_id=home[0], name=home[1]),
        away=TeamRef(provider_team_id=away[0], name=away[1]),
        home_goals=home_goals,
        away_goals=away_goals,
        state=state,
        status=status,
    )


async def _team_id(session: AsyncSession, provider_team_id: str) -> uuid.UUID:
    found = await session.execute(select(Team.id).where(Team.provider_team_id == provider_team_id))
    return found.scalar_one()


@pytest_db
@pytest.mark.asyncio
async def test_a_sweep_keeps_the_fixtures_that_have_not_been_played(
    session: AsyncSession,
) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()

    await sync_competition(session, provider, epl, SAMPLE_SEASON)

    stored = await session.execute(select(Match).where(Match.competition_id == epl.slug))
    by_state: dict[str, int] = {}
    for match in stored.scalars().all():
        by_state[match.state] = by_state.get(match.state, 0) + 1
    assert by_state == {"finished": 8, "scheduled": 2, "postponed": 1}


@pytest_db
@pytest.mark.asyncio
async def test_a_fixture_becomes_a_result_in_place_rather_than_a_second_row(
    session: AsyncSession,
) -> None:
    """The whole reason the sync is an upsert on ``provider_match_id``.

    A match is seen many times before it is played, and the run that finds it finished
    is the same run that found it scheduled the day before. Every field is rewritten,
    which is what lets a postponement move a kick-off and then move it back.
    """
    epl = _epl(uuid.uuid4().hex[:8])
    scheduled = _season_match(
        "m-transition",
        epl,
        day="2026-05-09",
        home=ARSENAL,
        away=CHELSEA,
        state=MatchState.SCHEDULED,
    )
    await sync_results(session, [scheduled])

    live = scheduled.model_copy(
        update={"state": MatchState.LIVE, "home_goals": 1, "away_goals": 0, "status": "63"}
    )
    await sync_results(session, [live])
    mid = (
        await session.execute(select(Match).where(Match.provider_match_id == "m-transition"))
    ).scalar_one()
    assert (mid.state, mid.home_goals, mid.finished) == ("live", 1, False)

    full_time = scheduled.model_copy(
        update={
            "state": MatchState.FINISHED,
            "home_goals": 2,
            "away_goals": 1,
            "status": "FT",
        }
    )
    await sync_results(session, [full_time])

    rows = (
        (await session.execute(select(Match).where(Match.provider_match_id == "m-transition")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert (rows[0].state, rows[0].home_goals, rows[0].away_goals, rows[0].finished) == (
        "finished",
        2,
        1,
        True,
    )


@pytest_db
@pytest.mark.asyncio
async def test_a_postponement_can_be_rescheduled_back(session: AsyncSession) -> None:
    """A state that could only ever move one way would strand every called-off match."""
    epl = _epl(uuid.uuid4().hex[:8])
    off = _season_match(
        "m-off",
        epl,
        day="2026-05-09",
        home=ARSENAL,
        away=CHELSEA,
        state=MatchState.POSTPONED,
        status="PP",
    )
    await sync_results(session, [off])
    back_on = _season_match(
        "m-off",
        epl,
        day="2026-05-19",
        home=ARSENAL,
        away=CHELSEA,
        state=MatchState.SCHEDULED,
    )
    await sync_results(session, [back_on])

    row = (
        await session.execute(select(Match).where(Match.provider_match_id == "m-off"))
    ).scalar_one()
    assert row.state == "scheduled"
    assert row.kickoff_utc.date() == date(2026, 5, 19)


@pytest_db
@pytest.mark.asyncio
async def test_a_teams_season_reads_back_complete_and_in_order(session: AsyncSession) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()
    await sync_competition(session, provider, epl, SAMPLE_SEASON)
    arsenal = await _team_id(session, ARSENAL[0])

    season = await team_season_matches(session, arsenal, epl.slug, SAMPLE_SEASON)

    assert season is not None
    assert season.team == "Arsenal FC"
    assert season.competition_id == epl.slug
    kickoffs = [match.kickoff_utc for match in season.matches]
    assert kickoffs == sorted(kickoffs)
    # Five results and the two fixtures the canned season ends on.
    assert [match.state for match in season.matches] == [
        MatchState.FINISHED,
        MatchState.FINISHED,
        MatchState.FINISHED,
        MatchState.FINISHED,
        MatchState.SCHEDULED,
        MatchState.POSTPONED,
    ]


@pytest_db
@pytest.mark.asyncio
async def test_a_season_says_home_or_away_and_scores_it_from_that_club(
    session: AsyncSession,
) -> None:
    """``2-1`` means nothing until you know which side of it the club was on."""
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()
    await sync_competition(session, provider, epl, SAMPLE_SEASON)
    arsenal = await _team_id(session, ARSENAL[0])

    season = await team_season_matches(session, arsenal, epl.slug, SAMPLE_SEASON)
    assert season is not None
    away_day = next(m for m in season.matches if not m.home and m.opponent == "Chelsea FC")

    # af-m-107: Chelsea 0 Arsenal 1 — a win, read from the away side.
    assert (away_day.goals_for, away_day.goals_against) == (1, 0)
    assert away_day.result is FormResult.WIN


@pytest_db
@pytest.mark.asyncio
async def test_an_unplayed_fixture_carries_no_score_and_no_result(
    session: AsyncSession,
) -> None:
    epl = _epl(uuid.uuid4().hex[:8])
    provider = CountingFootballData.with_sample_data()
    await sync_competition(session, provider, epl, SAMPLE_SEASON)
    arsenal = await _team_id(session, ARSENAL[0])

    season = await team_season_matches(session, arsenal, epl.slug, SAMPLE_SEASON)
    assert season is not None
    upcoming = [m for m in season.matches if m.state is not MatchState.FINISHED]

    assert upcoming
    for match in upcoming:
        assert match.goals_for is None
        assert match.goals_against is None
        assert match.result is None


@pytest_db
@pytest.mark.asyncio
async def test_a_season_does_not_leak_another_competition_season_or_club(
    session: AsyncSession,
) -> None:
    """The three filters, each shown doing its job against data built to defeat it."""
    tag = uuid.uuid4().hex[:8]
    league, cup = _epl(tag), _cup(tag)
    await sync_results(
        session,
        [
            _season_match(
                f"m-{tag}-league",
                league,
                day="2026-05-09",
                home=ARSENAL,
                away=CHELSEA,
                state=MatchState.FINISHED,
                home_goals=1,
                away_goals=0,
                status="FT",
            ),
            _season_match(
                f"m-{tag}-other-club",
                league,
                day="2026-05-09",
                home=SPURS,
                away=EVERTON,
                state=MatchState.FINISHED,
                home_goals=2,
                away_goals=2,
                status="FT",
            ),
        ],
    )
    # Same club, same day, a different competition — and a different season of the same one.
    await sync_results(
        session,
        [
            _season_match(
                f"m-{tag}-cup",
                cup,
                day="2026-05-09",
                home=ARSENAL,
                away=CHELSEA,
                state=MatchState.FINISHED,
                home_goals=3,
                away_goals=0,
                status="FT",
            )
        ],
    )
    last_year = _season_match(
        f"m-{tag}-last-year",
        league,
        day="2025-05-09",
        home=ARSENAL,
        away=CHELSEA,
        state=MatchState.FINISHED,
        home_goals=4,
        away_goals=0,
        status="FT",
    )
    await sync_results(session, [last_year.model_copy(update={"season": SAMPLE_SEASON - 1})])
    arsenal = await _team_id(session, ARSENAL[0])

    season = await team_season_matches(session, arsenal, league.slug, SAMPLE_SEASON)

    assert season is not None
    assert [match.match_id for match in season.matches] == [
        str(
            (
                await session.execute(
                    select(Match.id).where(Match.provider_match_id == f"m-{tag}-league")
                )
            ).scalar_one()
        )
    ]


@pytest_db
@pytest.mark.asyncio
async def test_a_club_with_nothing_stored_is_an_empty_season_not_a_missing_one(
    session: AsyncSession,
) -> None:
    """A division ingested for the first time genuinely has this shape."""
    tag = uuid.uuid4().hex[:8]
    epl = _epl(tag)
    await sync_results(
        session,
        [
            _season_match(
                f"m-{tag}",
                epl,
                day="2026-05-09",
                home=ARSENAL,
                away=CHELSEA,
                state=MatchState.SCHEDULED,
            )
        ],
    )
    arsenal = await _team_id(session, ARSENAL[0])

    empty = await team_season_matches(session, arsenal, epl.slug, SAMPLE_SEASON + 5)

    assert empty is not None
    assert empty.matches == []
    assert empty.team == "Arsenal FC"


@pytest_db
@pytest.mark.asyncio
async def test_a_club_we_do_not_hold_is_not_a_season_at_all(session: AsyncSession) -> None:
    assert await team_season_matches(session, uuid.uuid4(), "england-premier-league", 2026) is None
