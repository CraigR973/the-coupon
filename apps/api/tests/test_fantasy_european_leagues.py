"""Fantasy's European top flights (Batch 255), the parts that need no database.

Owner decision, 26 Nov 2026: Fantasy also plays the Spanish, Italian, German and French top
flights, for every two-game league and with no switch; Group and legacy rounds stay British.
The slugs and FotMob identities here are the live ones: the slugs read from odds-api.io's
catalogue on 2026-11-11 and its 28 Nov census on 2026-11-26, the FotMob ids and country codes
from its catalogue the same night — including the three same-named leagues in other countries
that make the country scope matter.

The database-backed halves — the census linking Fantasy, Group and legacy rounds, and the
Fantasy read and save — sit with their harnesses in ``test_two_game_discovery.py`` and
``test_two_game_fantasy.py``.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from src.services.competitions import (
    FANTASY_ONLY_COMPETITIONS,
    census_keeps,
    is_fantasy_only,
    plays_competition,
)
from src.services.football_provider import CompetitionKey
from src.services.fotmob import FotMobProvider
from src.services.odds_api import OddsApiProvider
from src.services.odds_provider import OddsProviderAPIError

LALIGA = "spain-laliga"
SERIE_A = "italy-serie-a"
BUNDESLIGA = "germany-bundesliga"
LIGUE_1 = "france-ligue-1"

#: A Saturday far enough ahead that nothing real can collide with it.
SATURDAY = date(2180, 1, 8)


# ── The rule ───────────────────────────────────────────────────────────────────


def test_exactly_the_four_top_flights_are_fantasy_only() -> None:
    assert FANTASY_ONLY_COMPETITIONS == {LALIGA, SERIE_A, BUNDESLIGA, LIGUE_1}
    for slug in (LALIGA, SERIE_A, BUNDESLIGA, LIGUE_1):
        assert is_fantasy_only(slug)
    # Their own countries' other competitions are not taken because they share a prefix.
    for slug in ("spain-laliga-2", "italy-serie-b", "germany-2-bundesliga", "france-ligue-2"):
        assert not is_fantasy_only(slug)
    # Nor are the same-named leagues elsewhere.
    for slug in ("austria-bundesliga", "brazil-brasileiro-serie-a", "algeria-ligue-1"):
        assert not is_fantasy_only(slug)
    assert is_fantasy_only("  Spain-LaLiga  ")
    assert not is_fantasy_only("")


def test_the_census_keeps_the_played_uk_competitions_and_the_four() -> None:
    assert census_keeps("england-premier-league")
    assert census_keeps("scotland-league-two")
    assert census_keeps("england-amateur-national-league-north")
    # The trim still applies to British competitions.
    assert not census_keeps("northern-ireland-premiership")
    assert not census_keeps("england-amateur-isthmian-league-premier-division")
    for slug in (LALIGA, SERIE_A, BUNDESLIGA, LIGUE_1):
        assert census_keeps(slug)
    for slug in ("spain-laliga-2", "ukraine-premier-league", "austria-bundesliga", ""):
        assert not census_keeps(slug)


@pytest.mark.parametrize("selected", [None, frozenset({"scotland-premiership"})])
def test_the_four_belong_to_fantasy_alone_whatever_the_league_list_says(selected) -> None:
    for slug in (LALIGA, SERIE_A, BUNDESLIGA, LIGUE_1):
        assert plays_competition("fantasy", slug, selected)
        assert not plays_competition("group", slug, selected)
        assert not plays_competition("legacy", slug, selected)


def test_every_other_competition_follows_the_league_list_as_before() -> None:
    for kind in ("legacy", "group", "fantasy"):
        assert plays_competition(kind, "england-premier-league", None)
        listed = frozenset({"scotland-premiership"})
        assert plays_competition(kind, "scotland-premiership", listed)
        assert not plays_competition(kind, "england-premier-league", listed)


# ── The census ─────────────────────────────────────────────────────────────────


def _event(event_id: str, slug: str, name: str, hour: int, **values: str) -> dict:
    return {
        "id": event_id,
        "home": f"Home {event_id}",
        "away": f"Away {event_id}",
        "date": f"{SATURDAY.isoformat()}T{hour:02d}:00:00Z",
        "status": "pending",
        "league": {"name": name, "slug": slug},
        **values,
    }


def _census(rows: list[dict], calls: list[str]) -> OddsApiProvider:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=rows)

    return OddsApiProvider(
        "synthetic-not-a-real-key",
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(handle)
        ),
    )


@pytest.mark.asyncio
async def test_one_census_page_carries_the_four_and_drops_everything_else_abroad() -> None:
    calls: list[str] = []
    rows = [
        _event("uk", "england-premier-league", "England - Premier League", 15),
        _event("laliga", LALIGA, "Spain - LaLiga", 15),
        _event("serie-a", SERIE_A, "Italy - Serie A", 17),
        _event("bundesliga", BUNDESLIGA, "Germany - Bundesliga", 14),
        _event("ligue-1", LIGUE_1, "France - Ligue 1", 19),
        _event("second-tier", "spain-laliga-2", "Spain - LaLiga 2", 15),
        _event("ukraine", "ukraine-premier-league", "Ukraine - Premier League", 15),
        _event("namesake", "austria-bundesliga", "Austria - Bundesliga", 15),
    ]
    provider = _census(rows, calls)
    page = await provider.fetch_census_page(SATURDAY)
    await provider.close()
    kept = {fixture.provider_event_id: fixture for fixture in page.fixtures}
    assert set(kept) == {"uk", "laliga", "serie-a", "bundesliga", "ligue-1"}
    assert kept["laliga"].competition_id == LALIGA
    assert kept["laliga"].competition == "Spain - LaLiga"
    assert page.complete and page.raw_count == len(rows)
    assert calls == ["/events"], "the four cost no request beyond the one census page"


@pytest.mark.asyncio
async def test_an_incomplete_european_event_is_skipped_and_never_fails_the_page() -> None:
    """An addition must never stop the British card; a British event still fails the page."""
    calls: list[str] = []
    broken = _event("broken", BUNDESLIGA, "Germany - Bundesliga", 14, home="", away="")
    rows = [_event("uk", "england-premier-league", "England - Premier League", 15), broken]
    provider = _census(rows, calls)
    page = await provider.fetch_census_page(SATURDAY)
    await provider.close()
    assert [fixture.provider_event_id for fixture in page.fixtures] == ["uk"]
    assert page.complete

    british = _event("bad-uk", "england-premier-league", "England - Premier League", 15)
    british.update(home="", away="")
    provider = _census([british], calls)
    with pytest.raises(OddsProviderAPIError, match="UK census event is incomplete"):
        await provider.fetch_census_page(SATURDAY)
    await provider.close()


# ── FotMob, for each club's table position and form ───────────────────────────

#: Read from FotMob's live catalogue on 2026-11-26: each name exists in another country too.
EUROPE_CATALOGUE = {
    "leagues": [
        {"ccode": "ESP", "leagues": [{"id": 87, "name": "LaLiga"}]},
        {"ccode": "ITA", "leagues": [{"id": 55, "name": "Serie A"}]},
        {"ccode": "GER", "leagues": [{"id": 54, "name": "Bundesliga"}]},
        {"ccode": "FRA", "leagues": [{"id": 53, "name": "Ligue 1"}]},
        {"ccode": "ECU", "leagues": [{"id": 246, "name": "Serie A"}]},
        {"ccode": "AUT", "leagues": [{"id": 38, "name": "Bundesliga"}]},
        {"ccode": "ALG", "leagues": [{"id": 516, "name": "Ligue 1"}]},
    ]
}


@pytest.mark.asyncio
async def test_fotmob_finds_each_top_flight_in_its_own_country() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/data/allLeagues":
            return httpx.Response(200, json=EUROPE_CATALOGUE)
        return httpx.Response(404, json={"error": "not found"})

    provider = FotMobProvider(
        client=httpx.AsyncClient(
            base_url="https://www.fotmob.com", transport=httpx.MockTransport(handle)
        )
    )
    expected = {
        LALIGA: ("Spain - LaLiga", "87"),
        SERIE_A: ("Italy - Serie A", "55"),
        BUNDESLIGA: ("Germany - Bundesliga", "54"),
        LIGUE_1: ("France - Ligue 1", "53"),
    }
    for slug, (name, league_id) in expected.items():
        assert await provider.league_id_for(CompetitionKey(slug=slug, name=name)) == league_id
    await provider.close()
