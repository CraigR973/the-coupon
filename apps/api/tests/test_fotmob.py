"""The FotMob adapter (Batch 46, ADR 0007), against recorded payloads.

The payloads in ``fixtures/fotmob_payloads.json`` were captured from the live API on
2026-08-20 and trimmed — real shapes, real ids, fewer rows. They are recorded rather
than hand-written because the two things most likely to break this adapter are shapes
nobody would invent: a flat match list with no division marker, and a composite table
whose groups are the only thing that says which division a club is in.

`8944` is National League North and South behind one id. `9545` is the Highland League
with both Lowland divisions. `117` is a single division, the control.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.services.football_provider import CompetitionKey, FootballDataAPIError
from src.services.fotmob import FotMobProvider, season_param

PAYLOADS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "fotmob_payloads.json").read_text()
)

NL_NORTH = CompetitionKey(
    slug="england-amateur-national-league-north",
    name="England Amateur - National League North",
)
NL_SOUTH = CompetitionKey(
    slug="england-amateur-national-league-south",
    name="England Amateur - National League South",
)
HIGHLAND = CompetitionKey(slug="scotland-highland-league", name="Scotland - Highland League")
NATIONAL = CompetitionKey(slug="england-national-league", name="England - National League")
EFL_CUP = CompetitionKey(slug="england-efl-cup", name="England - EFL Cup")
SCO_LEAGUE_ONE = CompetitionKey(slug="scotland-league-one", name="Scotland - League One")
ENG_LEAGUE_ONE = CompetitionKey(slug="england-league-one", name="England - League One")

CATALOGUE = {
    "leagues": [
        {
            "ccode": "ENG",
            "leagues": [
                {"id": 47, "name": "Premier League"},
                {"id": 108, "name": "League One"},
                {"id": 117, "name": "National League"},
                {"id": 133, "name": "EFL Cup"},
            ],
        },
        {
            "ccode": "SCO",
            "leagues": [
                {"id": 64, "name": "Premiership"},
                {"id": 124, "name": "League One"},
            ],
        },
    ]
}


def _provider(counter: list[str] | None = None) -> FotMobProvider:
    """A provider wired to the recorded payloads, counting upstream calls."""

    def handle(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(str(request.url))
        if request.url.path == "/api/data/allLeagues":
            return httpx.Response(200, json=CATALOGUE)
        league_id = request.url.params.get("id")
        if league_id in PAYLOADS:
            return httpx.Response(200, json=PAYLOADS[league_id])
        return httpx.Response(404, json={"error": "not found"})

    client = httpx.AsyncClient(
        base_url="https://www.fotmob.com", transport=httpx.MockTransport(handle)
    )
    return FotMobProvider(client=client)


# ── The season boundary ───────────────────────────────────────────────────────


def test_the_port_names_a_season_by_its_starting_year_and_fotmob_does_not() -> None:
    assert season_param(2026) == "2026/2027"


# ── Resolution ────────────────────────────────────────────────────────────────


async def test_a_combined_competition_resolves_without_touching_the_catalogue() -> None:
    """An override answers first, so an overridden competition costs no lookup."""
    calls: list[str] = []
    provider = _provider(calls)
    assert await provider.league_id_for(NL_NORTH) == "8944"
    assert calls == []
    await provider.close()


async def test_scotlands_league_one_does_not_resolve_to_englands() -> None:
    """The defect this would otherwise repeat.

    Country-blind name matching put Scotland's League One on England's id 108 against
    the live catalogue — the same class of mistake Batch 37 fixed for api-football,
    and one that writes a wrong table that looks entirely well-formed.
    """
    provider = _provider()
    assert await provider.league_id_for(SCO_LEAGUE_ONE) == "124"
    assert await provider.league_id_for(ENG_LEAGUE_ONE) == "108"
    await provider.close()


async def test_an_unresolvable_competition_returns_none_rather_than_guessing() -> None:
    provider = _provider()
    unknown = CompetitionKey(slug="wales-cymru-premier", name="Wales - Cymru Premier")
    assert await provider.league_id_for(unknown) is None
    await provider.close()


# ── One id, several competitions ──────────────────────────────────────────────


async def test_two_competitions_behind_one_id_cost_one_request() -> None:
    """The memoisation that stops a sweep quadrupling its own request count."""
    calls: list[str] = []
    provider = _provider(calls)
    await provider.fetch_table(NL_NORTH, 2026)
    await provider.fetch_table(NL_SOUTH, 2026)
    await provider.fetch_results(NL_NORTH, 2026)
    await provider.fetch_results(NL_SOUTH, 2026)
    assert len(calls) == 1, calls  # no catalogue call either: both are overrides
    await provider.close()


async def test_each_group_lands_in_its_own_competition() -> None:
    """The correctness half: a National League North club must not appear in South."""
    provider = _provider()
    north = await provider.fetch_table(NL_NORTH, 2026)
    south = await provider.fetch_table(NL_SOUTH, 2026)
    assert north is not None and south is not None
    north_teams = {row.team.name for row in north.rows}
    south_teams = {row.team.name for row in south.rows}
    assert north_teams and south_teams
    assert north_teams.isdisjoint(south_teams)
    await provider.close()


async def test_the_group_is_chosen_by_id_not_by_name() -> None:
    """`9545` carries three groups and only one is ours; Lowland must not leak in."""
    provider = _provider()
    table = await provider.fetch_table(HIGHLAND, 2026)
    assert table is not None
    assert table.competition.slug == "scotland-highland-league"
    assert table.rows
    await provider.close()


async def test_a_single_division_id_needs_no_attribution() -> None:
    provider = _provider()
    table = await provider.fetch_table(NATIONAL, 2026)
    assert table is not None
    assert table.rows and table.rows[0].position == 1
    await provider.close()


# ── Results ───────────────────────────────────────────────────────────────────


async def test_results_are_attributed_by_team_id_not_by_name() -> None:
    """`fixtures.allMatches` is flat and carries no division marker at all.

    Every match is placed by looking its home team up in the index built from the
    table groups, so a combined id never hands `team_matching` the wrong scope.
    """
    provider = _provider()
    north = await provider.fetch_results(NL_NORTH, 2026)
    south = await provider.fetch_results(NL_SOUTH, 2026)
    assert north, "the recorded payload contains finished National League North matches"
    north_ids = {m.provider_match_id for m in north}
    south_ids = {m.provider_match_id for m in south}
    assert north_ids.isdisjoint(south_ids)
    for match in north:
        assert match.competition.slug == NL_NORTH.slug
        assert match.finished is True
    await provider.close()


async def test_a_finished_match_carries_its_score_and_an_aware_kickoff() -> None:
    provider = _provider()
    results = await provider.fetch_results(NATIONAL, 2026)
    assert results
    match = results[0]
    assert match.home_goals is not None and match.away_goals is not None
    assert match.kickoff_utc.tzinfo is not None
    assert match.kickoff_utc.utcoffset() == datetime.now(UTC).utcoffset()
    assert match.status
    await provider.close()


async def test_unfinished_matches_are_not_reported_as_results() -> None:
    """The recorded payload deliberately includes one unplayed fixture."""
    provider = _provider()
    results = await provider.fetch_results(NATIONAL, 2026)
    assert all(m.finished for m in results)
    total = len(PAYLOADS["117"]["fixtures"]["allMatches"])
    assert len(results) < total
    await provider.close()


async def test_the_date_window_bounds_what_is_returned() -> None:
    provider = _provider()
    everything = await provider.fetch_results(NATIONAL, 2026)
    assert everything
    day = everything[0].kickoff_utc.date()
    inside = await provider.fetch_results(NATIONAL, 2026, since=day, until=day)
    assert inside and all(m.kickoff_utc.date() == day for m in inside)
    outside = await provider.fetch_results(
        NATIONAL, 2026, since=date(2099, 1, 1), until=date(2099, 12, 31)
    )
    assert outside == []
    await provider.close()


async def test_table_and_results_share_one_request() -> None:
    """Both halves of the port come out of one payload.

    api-football needs a `/standings` and a `/fixtures` call per competition; this
    needs one. The catalogue call is excluded because it is paid once per client and
    an overridden competition skips it entirely.
    """
    calls: list[str] = []
    provider = _provider(calls)
    await provider.fetch_table(NATIONAL, 2026)
    await provider.fetch_results(NATIONAL, 2026)
    league_calls = [c for c in calls if "/api/data/leagues" in c]
    assert len(league_calls) == 1, calls
    await provider.close()


# ── Cups, and a moving interface ──────────────────────────────────────────────


async def test_a_cup_has_no_table_and_is_not_reported_as_a_failure() -> None:
    """A cup has no standings to have; asking for one is not an error."""
    calls: list[str] = []
    provider = _provider(calls)
    assert await provider.fetch_table(EFL_CUP, 2026) is None
    assert calls == []
    await provider.close()


async def test_a_moved_path_raises_rather_than_reading_as_an_absent_table() -> None:
    """The failure mode ADR 0007 exists to prevent.

    `/api/leagues?id=47` began answering 404 while `/api/data/leagues` answered 200.
    A 404 swallowed as "no table for this division" would turn a path change into
    twenty-one competitions quietly carrying nothing — and Batch 45's verdict only
    means something if this raises.
    """
    provider = _provider()
    missing = CompetitionKey(slug="england-premier-league", name="England - Premier League")
    with pytest.raises(FootballDataAPIError):
        await provider.fetch_table(missing, 2026)
    await provider.close()


async def test_a_non_json_answer_raises() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!doctype html><html>maintenance</html>")

    client = httpx.AsyncClient(
        base_url="https://www.fotmob.com", transport=httpx.MockTransport(handle)
    )
    provider = FotMobProvider(client=client)
    with pytest.raises(FootballDataAPIError):
        await provider.fetch_table(NATIONAL, 2026)
    await provider.close()
