"""The API-Football adapter, against the documented v3 response shapes.

Everything runs over ``httpx.MockTransport``; nothing here touches the live API. That is
not only hygiene — outbound requests to this provider are blocked from the development
machine, so the live probe belongs to the owner. The odds source taught what that costs:
three shapes there differed from the documentation and each would have taken the batch
down alone. So the adapter reads every field defensively, and these tests pin the
defences rather than a happy path.

The headline cases are the two the documentation does not make obvious:

* a failure arrives with **HTTP 200** and an ``errors`` object, so a quota exhaustion
  must not read as "this competition has no table";
* ``standings`` is a list *of lists*, one per group.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

import src.services.api_football as api_football
from src.services.api_football import (
    DEFAULT_BASE_URL,
    ApiFootballProvider,
    _country_key,
)
from src.services.football_provider import (
    CompetitionKey,
    FootballDataAPIError,
    FootballDataAuthError,
)

SCOTLAND_L2 = CompetitionKey(slug="scotland-league-two", name="Scotland - League Two")
ENGLAND_NLN = CompetitionKey(
    slug="england-amateur-national-league-north", name="England Amateur - National League North"
)
UNCARRIED = CompetitionKey(slug="mars-super-league", name="Mars - Super League")

SEASON = 2025

# ── Documented v3 payloads ────────────────────────────────────────────────────

LEAGUES: dict[str, Any] = {
    "get": "leagues",
    "errors": [],
    "results": 4,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "league": {"id": 181, "name": "League Two", "type": "League"},
            "country": {"name": "Scotland", "code": "SC"},
        },
        {
            "league": {"id": 180, "name": "Championship", "type": "League"},
            "country": {"name": "Scotland", "code": "SC"},
        },
        # England names its regional feeders with a dash; the odds source qualifies the
        # *country* instead ("England Amateur"). Both have to fold to the same thing.
        {
            "league": {"id": 267, "name": "National League - North", "type": "League"},
            "country": {"name": "England", "code": "GB"},
        },
        # A different country's identically named division — the reason matching is
        # scoped by country before it looks at the name at all.
        {
            "league": {"id": 62, "name": "League Two", "type": "League"},
            "country": {"name": "France", "code": "FR"},
        },
    ],
}

# The live catalogue as production actually returned it: the countryless competitions
# carry `"code": null` rather than omitting the key, and one of them is enough to matter
# because every competition shares this parse. Kept as a separate payload from `LEAGUES`
# so the happy path still pins the documented shape.
LEAGUES_WITH_NULLS: dict[str, Any] = {
    "get": "leagues",
    "errors": [],
    "results": 3,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "league": {"id": 15, "name": "FIFA Club World Cup", "type": "Cup"},
            "country": {"name": "World", "code": None, "flag": None},
        },
        {
            "league": {"id": 181, "name": "League Two", "type": "League"},
            "country": {"name": "Scotland", "code": "SC"},
        },
        # A row that is unreadable whatever nulls are dropped: `league` is not an object.
        {"league": "Premiership", "country": {"name": "Scotland", "code": "SC"}},
    ],
}

STANDINGS: dict[str, Any] = {
    "get": "standings",
    "errors": [],
    "results": 1,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "league": {
                "id": 181,
                "name": "League Two",
                "country": "Scotland",
                "season": 2025,
                # A list *of lists* — one inner list per group.
                "standings": [
                    [
                        {
                            "rank": 1,
                            "team": {"id": 901, "name": "Forfar Athletic"},
                            "points": 68,
                            "goalsDiff": 19,
                            "form": "WDWWL",
                            "all": {
                                "played": 36,
                                "win": 20,
                                "draw": 8,
                                "lose": 8,
                                "goals": {"for": 58, "against": 39},
                            },
                        },
                        {
                            "rank": 2,
                            "team": {"id": 902, "name": "Brechin City"},
                            "points": 63,
                            "goalsDiff": 11,
                            "form": "LWDWW",
                            "all": {
                                "played": 36,
                                "win": 18,
                                "draw": 9,
                                "lose": 9,
                                "goals": {"for": 52, "against": 41},
                            },
                        },
                    ]
                ],
            }
        }
    ],
}

FIXTURES: dict[str, Any] = {
    "get": "fixtures",
    "errors": [],
    "results": 3,
    "paging": {"current": 1, "total": 1},
    "response": [
        {
            "fixture": {
                "id": 1180001,
                "date": "2026-04-11T14:00:00+00:00",
                "status": {"short": "FT", "long": "Match Finished"},
            },
            "league": {"id": 181, "name": "League Two", "country": "Scotland", "season": 2025},
            "teams": {
                "home": {"id": 901, "name": "Forfar Athletic"},
                "away": {"id": 903, "name": "Elgin City"},
            },
            "goals": {"home": 2, "away": 0},
        },
        # Not started — carries a null score that must not be recorded as 0-0.
        {
            "fixture": {
                "id": 1180002,
                "date": "2026-04-18T14:00:00+00:00",
                "status": {"short": "NS", "long": "Not Started"},
            },
            "league": {"id": 181, "name": "League Two", "country": "Scotland", "season": 2025},
            "teams": {
                "home": {"id": 903, "name": "Elgin City"},
                "away": {"id": 902, "name": "Brechin City"},
            },
            "goals": {"home": None, "away": None},
        },
        # In play — carries a *partial* score, which is the trap.
        {
            "fixture": {
                "id": 1180003,
                "date": "2026-04-25T14:00:00+00:00",
                "status": {"short": "2H", "long": "Second Half"},
            },
            "league": {"id": 181, "name": "League Two", "country": "Scotland", "season": 2025},
            "teams": {
                "home": {"id": 902, "name": "Brechin City"},
                "away": {"id": 901, "name": "Forfar Athletic"},
            },
            "goals": {"home": 1, "away": 1},
        },
    ],
}


def _provider(handler: Any) -> ApiFootballProvider:
    client = httpx.AsyncClient(base_url=DEFAULT_BASE_URL, transport=httpx.MockTransport(handler))
    return ApiFootballProvider("test-key", client=client)


def _router(routes: dict[str, Any], *, record: list[httpx.Request] | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(request)
        for path, payload in routes.items():
            if request.url.path.endswith(path):
                if isinstance(payload, httpx.Response):
                    return payload
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"errors": ["unrouted"]})

    return handler


# ── Competition matching ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_competition_resolves_within_its_own_country() -> None:
    """France also has a "League Two"; only Scotland's may match a Scottish slug."""
    async with _provider(_router({"/leagues": LEAGUES})) as provider:
        assert await provider.league_id_for(SCOTLAND_L2) == "181"


@pytest.mark.asyncio
async def test_an_english_amateur_tier_matches_its_plain_english_league() -> None:
    """The odds source's "England Amateur" qualifier is the country, not the division."""
    async with _provider(_router({"/leagues": LEAGUES})) as provider:
        assert await provider.league_id_for(ENGLAND_NLN) == "267"


@pytest.mark.asyncio
async def test_an_uncarried_competition_resolves_to_none_rather_than_a_guess() -> None:
    async with _provider(_router({"/leagues": LEAGUES})) as provider:
        assert await provider.league_id_for(UNCARRIED) is None


@pytest.mark.asyncio
async def test_the_catalogue_is_fetched_once_per_client() -> None:
    """One unfiltered request serves every competition — the 100/day plan requires it."""
    calls: list[httpx.Request] = []
    async with _provider(_router({"/leagues": LEAGUES}, record=calls)) as provider:
        await provider.league_id_for(SCOTLAND_L2)
        await provider.league_id_for(ENGLAND_NLN)
        await provider.league_id_for(UNCARRIED)
        await provider.league_id_for(UNCARRIED)  # a miss is memoised too
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_null_country_code_does_not_empty_the_catalogue() -> None:
    """The live-only shape that kept the football screens blank in production.

    ``/leagues`` returns ``"code": null`` for the countryless competitions. A default
    covers an *absent* key, not a null one, so the entry failed validation — and because
    the whole catalogue was parsed in one comprehension, every British division went with
    it and nothing was ever written.
    """
    async with _provider(_router({"/leagues": LEAGUES_WITH_NULLS})) as provider:
        assert await provider.league_id_for(SCOTLAND_L2) == "181"


@pytest.mark.asyncio
async def test_an_unreadable_entry_is_dropped_rather_than_failing_the_sweep() -> None:
    """One bad row costs its own competition, not the other twenty-nine."""
    async with _provider(_router({"/leagues": LEAGUES_WITH_NULLS})) as provider:
        catalogue = await provider._all_leagues()
    assert [entry.league.id for entry in catalogue] == ["15", "181"]


@pytest.mark.asyncio
async def test_a_catalogue_with_a_bad_row_is_still_memoised() -> None:
    """The quota half of the same defect.

    Raising before the memo is assigned costs a fresh ``/leagues`` request per competition
    — twenty-one of a hundred in one morning, for nothing.
    """
    calls: list[httpx.Request] = []
    async with _provider(_router({"/leagues": LEAGUES_WITH_NULLS}, record=calls)) as provider:
        await provider.league_id_for(SCOTLAND_L2)
        await provider.league_id_for(ENGLAND_NLN)
        await provider.league_id_for(UNCARRIED)
    assert len(calls) == 1


def test_country_qualifiers_fold_away() -> None:
    assert _country_key("England Amateur") == "england"
    assert _country_key("Northern-Ireland") == _country_key("Northern Ireland")


# ── Tables ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_table_is_read_out_of_the_nested_group_lists() -> None:
    routes = {"/leagues": LEAGUES, "/standings": STANDINGS}
    async with _provider(_router(routes)) as provider:
        table = await provider.fetch_table(SCOTLAND_L2, SEASON)
    assert table is not None
    assert table.competition == SCOTLAND_L2
    assert [row.position for row in table.rows] == [1, 2]
    leader = table.rows[0]
    assert leader.team.name == "Forfar Athletic"
    assert (leader.played, leader.won, leader.drawn, leader.lost) == (36, 20, 8, 8)
    assert (leader.goals_for, leader.goals_against, leader.points) == (58, 39, 68)
    assert leader.goal_difference == 19
    assert leader.form == "WDWWL"


@pytest.mark.asyncio
async def test_a_table_with_no_form_yet_still_reads() -> None:
    """A table published before a ball is kicked carries ``"form": null``.

    The same null-versus-absent trap as the catalogue's country code, on the shape a
    league's *opening* weeks return — so it would have emptied every table in August and
    quietly filled them later, which is the hardest kind of gap to attribute.
    """
    opening_day = {
        "get": "standings",
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "league": {
                    "id": 181,
                    "name": "League Two",
                    "country": "Scotland",
                    "season": 2026,
                    "standings": [
                        [
                            {
                                "rank": 1,
                                "team": {"id": 901, "name": "Forfar Athletic"},
                                "points": 0,
                                "goalsDiff": None,
                                "form": None,
                                "all": {
                                    "played": 0,
                                    "win": 0,
                                    "draw": 0,
                                    "lose": 0,
                                    "goals": {"for": 0, "against": 0},
                                },
                            }
                        ]
                    ],
                }
            }
        ],
    }
    routes = {"/leagues": LEAGUES, "/standings": opening_day}
    async with _provider(_router(routes)) as provider:
        table = await provider.fetch_table(SCOTLAND_L2, SEASON)
    assert table is not None
    assert [row.position for row in table.rows] == [1]
    assert table.rows[0].form == ""


@pytest.mark.asyncio
async def test_an_uncarried_competition_costs_no_standings_request() -> None:
    calls: list[httpx.Request] = []
    routes = {"/leagues": LEAGUES, "/standings": STANDINGS}
    async with _provider(_router(routes, record=calls)) as provider:
        assert await provider.fetch_table(UNCARRIED, SEASON) is None
    assert [c.url.path for c in calls] == ["/leagues"]


@pytest.mark.asyncio
async def test_an_empty_table_is_none_rather_than_an_empty_one() -> None:
    empty = {"errors": [], "response": [], "paging": {"current": 1, "total": 1}}
    routes = {"/leagues": LEAGUES, "/standings": empty}
    async with _provider(_router(routes)) as provider:
        assert await provider.fetch_table(SCOTLAND_L2, SEASON) is None


# ── Results ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_only_finished_matches_carry_a_score() -> None:
    """An in-play match has a *partial* score; recording it would freeze a half-time
    result as final, and a not-started one would become a goalless draw."""
    routes = {"/leagues": LEAGUES, "/fixtures": FIXTURES}
    async with _provider(_router(routes)) as provider:
        results = await provider.fetch_results(SCOTLAND_L2, SEASON)

    by_id = {r.provider_match_id: r for r in results}
    assert len(by_id) == 3

    finished = by_id["1180001"]
    assert finished.finished is True
    assert (finished.home_goals, finished.away_goals) == (2, 0)
    assert finished.home.name == "Forfar Athletic"

    for pending_id in ("1180002", "1180003"):
        pending = by_id[pending_id]
        assert pending.finished is False
        assert pending.home_goals is None
        assert pending.away_goals is None


@pytest.mark.asyncio
async def test_results_are_bounded_only_when_both_ends_are_given() -> None:
    """The API rejects a ``from`` without a ``to``, and the backfill wants neither."""
    calls: list[httpx.Request] = []
    routes = {"/leagues": LEAGUES, "/fixtures": FIXTURES}
    async with _provider(_router(routes, record=calls)) as provider:
        await provider.fetch_results(SCOTLAND_L2, SEASON)
        await provider.fetch_results(
            SCOTLAND_L2, SEASON, since=date(2026, 4, 1), until=date(2026, 5, 1)
        )
    unbounded, bounded = (c for c in calls if c.url.path == "/fixtures")
    assert "from" not in unbounded.url.params
    assert bounded.url.params["from"] == "2026-04-01"
    assert bounded.url.params["to"] == "2026-05-01"


@pytest.mark.asyncio
async def test_results_follow_paging() -> None:
    page_one = {**FIXTURES, "paging": {"current": 1, "total": 2}}
    page_two = {
        "errors": [],
        "paging": {"current": 2, "total": 2},
        "response": [
            {
                "fixture": {
                    "id": 1180004,
                    "date": "2026-05-02T14:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
                },
                "league": {"id": 181, "name": "League Two", "season": 2025},
                "teams": {
                    "home": {"id": 901, "name": "Forfar Athletic"},
                    "away": {"id": 902, "name": "Brechin City"},
                },
                "goals": {"home": 1, "away": 2},
            }
        ],
    }
    pages = iter([page_one, page_two])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/leagues":
            return httpx.Response(200, json=LEAGUES)
        return httpx.Response(200, json=next(pages))

    async with _provider(handler) as provider:
        results = await provider.fetch_results(SCOTLAND_L2, SEASON)
    assert "1180004" in {r.provider_match_id for r in results}


# ── Errors that arrive with HTTP 200 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_exhausted_quota_raises_rather_than_looking_like_no_data() -> None:
    """The response is a 200. Treating it as success empties every screen silently."""
    quota = {"errors": {"requests": "You have reached the request limit for the day"}}
    async with _provider(_router({"/leagues": quota})) as provider:
        with pytest.raises(FootballDataAPIError, match="request limit"):
            await provider.fetch_table(SCOTLAND_L2, SEASON)


@pytest.mark.asyncio
async def test_a_minute_rate_limit_reported_in_a_200_body_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limited = {"errors": {"rateLimit": "You have exceeded 10 requests per minute"}}
    calls: list[str] = []
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/leagues" and calls.count("/leagues") == 1:
            return httpx.Response(200, json=rate_limited)
        if request.url.path == "/leagues":
            return httpx.Response(200, json=LEAGUES)
        if request.url.path == "/standings":
            return httpx.Response(200, json=STANDINGS)
        return httpx.Response(404, json={"errors": ["unrouted"]})

    monkeypatch.setattr(api_football.asyncio, "sleep", fake_sleep)
    async with _provider(handler) as provider:
        table = await provider.fetch_table(SCOTLAND_L2, SEASON)

    assert table is not None
    assert calls == ["/leagues", "/leagues", "/standings"]
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_a_rejected_key_reported_in_a_200_body_is_an_auth_error() -> None:
    bad_key = {"errors": {"token": "Error/Missing application key."}}
    async with _provider(_router({"/leagues": bad_key})) as provider:
        with pytest.raises(FootballDataAuthError):
            await provider.fetch_table(SCOTLAND_L2, SEASON)


@pytest.mark.asyncio
async def test_a_401_raises_an_auth_error_without_retrying() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={})

    async with _provider(handler) as provider:
        with pytest.raises(FootballDataAuthError):
            await provider.fetch_table(SCOTLAND_L2, SEASON)
    assert len(calls) == 1  # an unusable key must not burn a 100/day allowance


@pytest.mark.asyncio
async def test_a_non_json_body_raises_a_clean_error() -> None:
    async with _provider(_router({"/leagues": httpx.Response(200, text="<html>nope")})) as provider:
        with pytest.raises(FootballDataAPIError, match="non-JSON"):
            await provider.fetch_table(SCOTLAND_L2, SEASON)


def test_an_empty_key_is_refused_at_construction() -> None:
    with pytest.raises(FootballDataAuthError):
        ApiFootballProvider("")
