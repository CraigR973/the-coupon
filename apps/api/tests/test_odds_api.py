"""Tests for the odds-api.io provider, against payloads captured from the live v3 API.

Every payload below was recorded on 2026-08-04 — the leagues catalogue, the five
``Scotland - League One`` fixtures for 2026-08-08, and Bet365's prices for one of them.
Three of its shapes are not what the ADR or the provider's own SDK implied, and each one
would have taken the batch down on its own:

* ``id`` is a JSON **number**, and ``league`` a nested ``{name, slug}`` object;
* leagues carry **no** ``country`` field, and England's lower tiers sit under
  ``"England Amateur - …"``;
* a settled fixture keeps ``status`` on ``/odds`` but loses its ``scores``, so settlement
  has to read ``/events/{id}``.

The headline case is :func:`test_scottish_league_one_fixture_reaches_the_slate` — the
exact fixture the Betfair Exchange could not serve, which is why this provider exists.

Everything runs over ``httpx.MockTransport``; nothing here touches the live API.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.odds_api import (
    DEFAULT_BASE_URL,
    OALeague,
    OddsApiProvider,
    _decimal_price,
    _is_uk,
    _market_of,
)
from src.services.odds_provider import (
    SATURDAY_THREE_PM,
    Market,
    OddsProviderAPIError,
    OddsProviderAuthError,
    Outcome,
    is_void_status,
)

SATURDAY = date(2026, 8, 8)

# ── Payloads captured from the live API, 2026-08-04 ───────────────────────────

# `/leagues?sport=football` returned 728 entries shaped exactly like these: {name, slug,
# eventsCount}. No `id`, and no `country` — the country is only ever in the name.
LEAGUES: list[dict[str, Any]] = [
    {"name": "Scotland - League One", "slug": "scotland-league-one", "eventsCount": 61},
    {"name": "Scotland - League Two", "slug": "scotland-league-two", "eventsCount": 55},
    {"name": "England - Premier League", "slug": "england-premier-league", "eventsCount": 90},
    # England's lower tiers sit under a qualified heading. Reading the country as the
    # whole prefix drops eight competitions, National League North and South among them.
    {
        "name": "England Amateur - National League North",
        "slug": "england-amateur-national-league-north",
        "eventsCount": 180,
    },
    {"name": "Wales - Cymru Premier", "slug": "wales-cymru-premier", "eventsCount": 60},
    {
        "name": "Northern Ireland - Premiership",
        "slug": "northern-ireland-premiership",
        "eventsCount": 90,
    },
    # "Ukraine" begins with "uk": a prefix test would read this as British.
    {"name": "Ukraine - Premier League", "slug": "ukraine-premier-league", "eventsCount": 60},
    {"name": "Spain - La Liga", "slug": "spain-la-liga", "eventsCount": 90},
]

# `/events?sport=football&league=scotland-league-one` for the launch Saturday. `id` is a
# number, `league` is nested, and a *pending* fixture already carries a 0-0 `scores`.
SL1_EVENTS: list[dict[str, Any]] = [
    {
        "id": 72203846,
        "home": "Airdrieonians FC",
        "away": "East Kilbride FC",
        "homeId": 2367,
        "awayId": 170622,
        "date": "2026-08-08T14:00:00Z",
        "sport": {"name": "Football", "slug": "football"},
        "league": {"name": "Scotland - League One", "slug": "scotland-league-one"},
        "status": "pending",
        "scores": {"home": 0, "away": 0},
    },
    # Decoy: same day, wrong kick-off. The Saturday-15:00 rule must drop it.
    {
        "id": 72203848,
        "home": "East Fife FC",
        "away": "Cove Rangers FC",
        "date": "2026-08-08T11:30:00Z",
        "league": {"name": "Scotland - League One", "slug": "scotland-league-one"},
        "status": "pending",
        "scores": {"home": 0, "away": 0},
    },
]

EPL_EVENTS: list[dict[str, Any]] = [
    {
        "id": 72203900,
        "home": "Arsenal",
        "away": "Chelsea",
        "date": "2026-08-08T14:00:00Z",
        "league": {"name": "England - Premier League", "slug": "england-premier-league"},
        "status": "pending",
        "scores": {"home": 0, "away": 0},
    }
]

# A called-off fixture, on a route the other slate tests leave empty. Two of the 1,599
# fixtures the live API listed for 2026-08-22 came back exactly like this (measured
# 2026-08-21) — the shape Batch 49 acts on before lock rather than at settlement.
CYMRU_EVENTS: list[dict[str, Any]] = [
    {
        "id": 72204100,
        "home": "Connah's Quay Nomads",
        "away": "The New Saints",
        "date": "2026-08-08T14:00:00Z",
        "league": {"name": "Wales - Cymru Premier", "slug": "wales-cymru-premier"},
        "status": "cancelled",
        "scores": {"home": 0, "away": 0},
    }
]

NLN_EVENTS: list[dict[str, Any]] = [
    {
        "id": 72203960,
        "home": "Chester FC",
        "away": "Southport FC",
        "date": "2026-08-08T14:00:00Z",
        "league": {
            "name": "England Amateur - National League North",
            "slug": "england-amateur-national-league-north",
        },
        "status": "pending",
        "scores": {"home": 0, "away": 0},
    }
]

# `/odds?eventId=72203846&bookmakers=Bet365`. Bet365 returned 28 markets; the ones this
# game does not use are kept here verbatim because they are what the market matcher has to
# reject — note "Both Teams To Score HT" and "…2H", which a loose match would take as BTTS.
AIRDRIE_ODDS: dict[str, Any] = {
    "id": 72203846,
    "home": "Airdrieonians FC",
    "away": "East Kilbride FC",
    "date": "2026-08-08T14:00:00Z",
    "league": {"name": "Scotland - League One", "slug": "scotland-league-one"},
    "status": "pending",
    "bookmakers": {
        "Bet365": [
            {"name": "ML", "odds": [{"home": "4.333", "draw": "3.750", "away": "1.650"}]},
            {"name": "Draw No Bet", "odds": [{"home": "3.500", "away": "1.285"}]},
            {"name": "Spread", "odds": [{"hdp": 0.75, "home": "1.950", "away": "1.850"}]},
            {"name": "Totals", "odds": [{"hdp": 2.75, "over": "1.975", "under": "1.825"}]},
            {"name": "Both Teams To Score", "odds": [{"yes": "1.800", "no": "1.909"}]},
            {"name": "Both Teams To Score HT", "odds": [{"yes": "4.333", "no": "1.200"}]},
            {"name": "Both Teams To Score 2H", "odds": [{"yes": "3.400", "no": "1.300"}]},
            {"name": "Correct Score", "odds": [{"label": "0-0", "odds": "12.000"}]},
        ],
        # A second Bet365 feed and a second book: neither may be blended in, because the
        # game scores by odds.
        "Bet365 (no latency)": [
            {"name": "ML", "odds": [{"home": "4.500", "draw": "3.800", "away": "1.600"}]}
        ],
    },
    "urls": {"Bet365": "https://www.bet365.com/#/AC/B1/C1/D8/E198889227/F3/I1/"},
}


SL1 = "scotland-league-one"
AIRDRIE_ID = "72203846"

SLATE_ROUTES: dict[Any, Any] = {
    "/leagues": LEAGUES,
    ("events", SL1): SL1_EVENTS,
    ("events", "scotland-league-two"): [],
    ("events", "england-premier-league"): EPL_EVENTS,
    ("events", "england-amateur-national-league-north"): NLN_EVENTS,
    ("events", "wales-cymru-premier"): [],
    ("events", "northern-ireland-premiership"): [],
}


def _provider(handler: httpx.MockTransport, *, bookmaker: str = "Bet365") -> OddsApiProvider:
    return OddsApiProvider(
        "test-key",
        bookmaker=bookmaker,
        client=httpx.AsyncClient(transport=handler, base_url=DEFAULT_BASE_URL),
    )


def _routed(
    routes: dict[Any, Any], *, record: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    """A transport dispatching on path, recording every request it serves."""

    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(request)
        path = request.url.path.removeprefix("/v3")
        if path.startswith("/events/"):
            key = ("event", path.removeprefix("/events/"))
            if key not in routes:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=routes[key])
        if path == "/events":
            return httpx.Response(
                200, json=routes.get(("events", request.url.params.get("league", "")), [])
            )
        if path in routes:
            return httpx.Response(200, json=routes[path])
        raise AssertionError(f"unexpected path: {request.url}")

    return httpx.MockTransport(handler)


# ── Slate ──────────────────────────────────────────────────────────────────────


class TestFetchSlate:
    async def test_scottish_league_one_fixture_reaches_the_slate(self) -> None:
        """The exact case the Exchange could not serve — ADR 0002's reason to exist."""
        slate = await _provider(_routed(SLATE_ROUTES)).fetch_slate(SATURDAY_THREE_PM, SATURDAY)

        airdrie = next(f for f in slate.fixtures if f.provider_event_id == AIRDRIE_ID)
        assert airdrie.competition == "Scotland - League One"
        assert (airdrie.home, airdrie.away) == ("Airdrieonians FC", "East Kilbride FC")
        assert airdrie.competition_id == SL1
        assert airdrie.kickoff_utc.isoformat() == "2026-08-08T14:00:00+00:00"

    async def test_numeric_event_id_becomes_a_string(self) -> None:
        """`id` is a JSON number. Without coercion every event fails validation."""
        slate = await _provider(_routed(SLATE_ROUTES)).fetch_slate(SATURDAY_THREE_PM, SATURDAY)
        assert all(isinstance(f.provider_event_id, str) for f in slate.fixtures)
        assert AIRDRIE_ID in {f.provider_event_id for f in slate.fixtures}

    async def test_english_amateur_tiers_are_covered(self) -> None:
        """ "England Amateur - National League North" is England, not a country of its own.

        Reading the whole name prefix as the country drops eight competitions from the
        live catalogue — including the two National League divisions that fill a Saturday.
        """
        slate = await _provider(_routed(SLATE_ROUTES)).fetch_slate(SATURDAY_THREE_PM, SATURDAY)
        assert "England Amateur - National League North" in {f.competition for f in slate.fixtures}

    async def test_carries_each_fixtures_status_verbatim(self) -> None:
        """The status is what lets a postponement be caught before lock (Batch 49).

        ``fetch_slate`` used to build a ``SlateFixture`` from the teams and the kick-off
        and drop the rest of the payload, so the only thing that ever read a status was
        settlement — hours after the round had been played.
        """
        routes = {**SLATE_ROUTES, ("events", "wales-cymru-premier"): CYMRU_EVENTS}
        slate = await _provider(_routed(routes)).fetch_slate(SATURDAY_THREE_PM, SATURDAY)

        by_id = {f.provider_event_id: f for f in slate.fixtures}
        assert by_id[AIRDRIE_ID].status == "pending"
        assert not is_void_status(by_id[AIRDRIE_ID].status)
        assert by_id["72204100"].status == "cancelled"
        assert is_void_status(by_id["72204100"].status)

    async def test_drops_non_saturday_3pm_kickoffs(self) -> None:
        slate = await _provider(_routed(SLATE_ROUTES)).fetch_slate(SATURDAY_THREE_PM, SATURDAY)
        assert all(f.provider_event_id != "72203848" for f in slate.fixtures)

    async def test_asks_only_about_british_leagues(self) -> None:
        record: list[httpx.Request] = []
        slate = await _provider(_routed(SLATE_ROUTES, record=record)).fetch_slate(
            SATURDAY_THREE_PM, SATURDAY
        )

        requested = {r.url.params.get("league") for r in record if r.url.path.endswith("/events")}
        assert "spain-la-liga" not in requested
        # "Ukraine" starts with "uk" — a prefix test would pull it into the slate.
        assert "ukraine-premier-league" not in requested
        assert all("Spain" not in f.competition for f in slate.fixtures)

    async def test_league_catalogue_is_fetched_once_per_client(self) -> None:
        """The catalogue changes between seasons, not between refreshes."""
        record: list[httpx.Request] = []
        provider = _provider(_routed(SLATE_ROUTES, record=record))
        await provider.fetch_slate(SATURDAY_THREE_PM, SATURDAY)
        await provider.fetch_slate(SATURDAY_THREE_PM, SATURDAY)

        assert len([r for r in record if r.url.path.endswith("/leagues")]) == 1

    async def test_sends_the_api_key_and_saturday_window(self) -> None:
        record: list[httpx.Request] = []
        await _provider(_routed(SLATE_ROUTES, record=record)).fetch_slate(
            SATURDAY_THREE_PM, SATURDAY
        )

        events_request = next(r for r in record if r.url.path.endswith("/events"))
        assert events_request.url.params["apiKey"] == "test-key"
        assert events_request.url.params["sport"] == "football"
        # 2026-08-08 in UK local time is 23:00Z the previous day under BST.
        assert events_request.url.params["from"] == "2026-08-07T23:00:00Z"
        assert events_request.url.params["to"] == "2026-08-08T23:00:00Z"


class TestFetchCompetitions:
    """Batch 21 — the admin picker's catalogue, sourced here instead of from `fixtures`."""

    async def test_lists_every_uk_competition_the_provider_carries(self) -> None:
        competitions = await _provider(_routed(SLATE_ROUTES)).fetch_competitions()

        assert {c.competition_id for c in competitions} == {
            "england-amateur-national-league-north",
            "england-premier-league",
            "northern-ireland-premiership",
            SL1,
            "scotland-league-two",
            "wales-cymru-premier",
        }
        # The slug is what `/events?league=` and a stored selection both key on; the name
        # is what the admin reads, and the list arrives name-ordered for the picker.
        by_id = {c.competition_id: c.competition for c in competitions}
        assert by_id[SL1] == "Scotland - League One"
        assert [c.competition for c in competitions] == sorted(c.competition for c in competitions)

    async def test_excludes_competitions_outside_the_home_nations(self) -> None:
        """Same `_is_uk` rule the slate uses — a picker entry the slate ignores is a trap."""
        competitions = await _provider(_routed(SLATE_ROUTES)).fetch_competitions()

        ids = {c.competition_id for c in competitions}
        assert "spain-la-liga" not in ids
        # "Ukraine" begins with "uk"; a prefix test would offer it.
        assert "ukraine-premier-league" not in ids

    async def test_offers_competitions_no_slate_has_ever_pooled(self) -> None:
        """The defect Batch 21 fixes, in one comparison.

        Three of these six competitions have fixtures on the canned Saturday, so a
        `fixtures`-derived catalogue could only ever offer those three — and none at all
        before a league's first slate ran. The provider's catalogue offers all six.
        """
        provider = _provider(_routed(SLATE_ROUTES))
        competitions = await provider.fetch_competitions()
        slate = await provider.fetch_slate(SATURDAY_THREE_PM, SATURDAY)

        pooled = {f.competition_id for f in slate.fixtures}
        offered = {c.competition_id for c in competitions}

        assert pooled < offered
        assert "scotland-league-two" in offered - pooled

    async def test_costs_one_request_and_none_at_all_after_a_slate(self) -> None:
        """`_all_leagues` is memoised per client, so the picker is free on the common path."""
        record: list[httpx.Request] = []
        provider = _provider(_routed(SLATE_ROUTES, record=record))

        await provider.fetch_competitions()
        assert len(record) == 1 and record[0].url.path.endswith("/leagues")

        await provider.fetch_slate(SATURDAY_THREE_PM, SATURDAY)
        before = len(record)
        await provider.fetch_competitions()
        await provider.fetch_competitions()
        assert len(record) == before


class TestUkDetection:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Scotland - League One", True),
            ("Scotland - League Two", True),
            ("England - Premier League", True),
            ("England - National League", True),
            ("England Amateur - National League North", True),
            ("England Amateur - Isthmian League, Premier Division", True),
            ("Wales - Cymru Premier", True),
            ("Northern Ireland - Premiership", True),
            ("Scotland - Premier League 1, Women", True),
            # "Ukraine" begins with "uk"; "Germany Amateur" is still not British.
            ("Ukraine - Premier League", False),
            ("Germany Amateur - Regionalliga", False),
            ("Spain - La Liga", False),
        ],
    )
    def test_is_uk(self, name: str, expected: bool) -> None:
        assert _is_uk(OALeague(id="x", name=name)) is expected

    def test_every_uk_league_in_the_live_catalogue_is_matched(self) -> None:
        matched = {lg["slug"] for lg in LEAGUES if _is_uk(OALeague.model_validate(lg))}
        assert matched == {
            SL1,
            "scotland-league-two",
            "england-premier-league",
            "england-amateur-national-league-north",
            "wales-cymru-premier",
            "northern-ireland-premiership",
        }


# ── Odds ───────────────────────────────────────────────────────────────────────


class TestFetchOdds:
    async def test_maps_ml_and_btts_to_the_games_markets(self) -> None:
        [fixture] = await _provider(_routed({"/odds": AIRDRIE_ODDS})).fetch_odds([AIRDRIE_ID])

        assert fixture.provider_event_id == AIRDRIE_ID
        by_key = {(s.market, s.outcome): s for s in fixture.selections}
        assert by_key[(Market.MATCH_ODDS, Outcome.HOME)].price == Decimal("4.333")
        assert by_key[(Market.MATCH_ODDS, Outcome.DRAW)].price == Decimal("3.750")
        assert by_key[(Market.MATCH_ODDS, Outcome.AWAY)].price == Decimal("1.650")
        assert by_key[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)].price == Decimal("1.800")
        assert by_key[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)].price == Decimal("1.909")

    async def test_prices_are_decimal_not_float(self) -> None:
        """``odds_at_pick`` is Numeric(6, 2) and is multiplied to award points.

        Parsing "4.333" through float would store a binary approximation of a number the
        member is scored on.
        """
        [fixture] = await _provider(_routed({"/odds": AIRDRIE_ODDS})).fetch_odds([AIRDRIE_ID])

        home = next(s for s in fixture.selections if s.outcome is Outcome.HOME)
        assert isinstance(home.price, Decimal)
        assert str(home.price) == "4.333"

    async def test_runner_names_come_from_the_fixtures_own_teams(self) -> None:
        [fixture] = await _provider(_routed({"/odds": AIRDRIE_ODDS})).fetch_odds([AIRDRIE_ID])

        names = {(s.market, s.outcome): s.runner_name for s in fixture.selections}
        assert names[(Market.MATCH_ODDS, Outcome.HOME)] == "Airdrieonians FC"
        assert names[(Market.MATCH_ODDS, Outcome.AWAY)] == "East Kilbride FC"
        assert names[(Market.MATCH_ODDS, Outcome.DRAW)] == "The Draw"
        assert names[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)] == "Yes"

    async def test_uses_only_the_pinned_bookmaker(self) -> None:
        """ "Bet365 (no latency)" is a different feed and must not be blended in."""
        [fixture] = await _provider(_routed({"/odds": AIRDRIE_ODDS})).fetch_odds([AIRDRIE_ID])

        home = next(s for s in fixture.selections if s.outcome is Outcome.HOME)
        assert home.price == Decimal("4.333")  # Bet365, not the 4.500 alternative feed

    async def test_ignores_markets_the_game_does_not_offer(self) -> None:
        """Bet365 returns 28 markets; only two are offerable.

        "Both Teams To Score HT" and "…2H" are the trap: a substring match would take
        either one as the full-time BTTS market and price a pick off the wrong bet.
        """
        [fixture] = await _provider(_routed({"/odds": AIRDRIE_ODDS})).fetch_odds([AIRDRIE_ID])

        assert {s.market for s in fixture.selections} == {
            Market.MATCH_ODDS,
            Market.BOTH_TEAMS_TO_SCORE,
        }
        assert len(fixture.selections) == 5
        btts = {
            s.outcome: s.price for s in fixture.selections if s.market is Market.BOTH_TEAMS_TO_SCORE
        }
        assert btts == {Outcome.YES: Decimal("1.800"), Outcome.NO: Decimal("1.909")}

    async def test_only_offers_selections_the_provider_prices(self) -> None:
        """A thin lower-league market yields fewer selections rather than an error."""
        thin = {
            **AIRDRIE_ODDS,
            "bookmakers": {
                "Bet365": [
                    {"name": "ML", "odds": [{"home": "4.333", "draw": "3.750", "away": "1.650"}]},
                    {"name": "Both Teams To Score", "odds": [{"yes": "1.800", "no": None}]},
                ]
            },
        }
        [fixture] = await _provider(_routed({"/odds": thin})).fetch_odds([AIRDRIE_ID])

        offered = {(s.market, s.outcome) for s in fixture.selections}
        assert (Market.BOTH_TEAMS_TO_SCORE, Outcome.YES) in offered
        assert (Market.BOTH_TEAMS_TO_SCORE, Outcome.NO) not in offered

    async def test_unpriced_fixture_yields_no_selections(self) -> None:
        unpriced = {**AIRDRIE_ODDS, "bookmakers": {}}
        [fixture] = await _provider(_routed({"/odds": unpriced})).fetch_odds([AIRDRIE_ID])
        assert fixture.selections == []

    async def test_bookmaker_name_is_matched_case_insensitively(self) -> None:
        provider = _provider(_routed({"/odds": AIRDRIE_ODDS}), bookmaker="bet365")
        [fixture] = await provider.fetch_odds([AIRDRIE_ID])
        assert len(fixture.selections) == 5

    async def test_empty_event_list_makes_no_request(self) -> None:
        record: list[httpx.Request] = []
        assert await _provider(_routed({}, record=record)).fetch_odds([]) == []
        assert record == []

    async def test_several_events_are_batched_into_one_request(self) -> None:
        """Forty fixtures must cost a couple of requests, not forty, at 100/hour."""
        record: list[httpx.Request] = []
        multi = [AIRDRIE_ODDS, {**AIRDRIE_ODDS, "id": 72203900}]
        transport = _routed({"/odds/multi": multi}, record=record)

        odds = await _provider(transport).fetch_odds([AIRDRIE_ID, "72203900"])

        assert {o.provider_event_id for o in odds} == {AIRDRIE_ID, "72203900"}
        assert len(record) == 1
        assert record[0].url.path.endswith("/odds/multi")
        assert record[0].url.params["eventIds"] == f"{AIRDRIE_ID},72203900"
        assert record[0].url.params["bookmakers"] == "Bet365"


class TestPriceParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("4.333", Decimal("4.333")),
            ("1.01", Decimal("1.01")),
            (2.5, Decimal("2.5")),
            (3, Decimal("3")),
            (None, None),
            ("", None),
            ("N/A", None),
            ("not-a-price", None),
            ("1.00", None),  # not a price a back bet can be struck at
            ("0.5", None),
            (True, None),
        ],
    )
    def test_decimal_price(self, raw: object, expected: Decimal | None) -> None:
        assert _decimal_price(raw) == expected


class TestMarketNames:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("ML", Market.MATCH_ODDS),
            ("ml", Market.MATCH_ODDS),
            ("Match Odds", Market.MATCH_ODDS),
            ("Both Teams To Score", Market.BOTH_TEAMS_TO_SCORE),
            ("both teams to score", Market.BOTH_TEAMS_TO_SCORE),
            ("BTTS", Market.BOTH_TEAMS_TO_SCORE),
            # Real Bet365 markets that must not be mistaken for the two offerable ones.
            ("Both Teams To Score HT", None),
            ("Both Teams To Score 2H", None),
            ("Draw No Bet", None),
            ("Double Chance", None),
            ("Totals", None),
            ("Correct Score", None),
            ("", None),
        ],
    )
    def test_market_of(self, name: str, expected: Market | None) -> None:
        assert _market_of(name) == expected


# ── Settlement (derived from the score, read from /events/{id}) ────────────────


def _event(status: str, scores: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": 72203846,
        "home": "Airdrieonians FC",
        "away": "East Kilbride FC",
        "date": "2026-08-08T14:00:00Z",
        "league": {"name": "Scotland - League One", "slug": SL1},
        "status": status,
    }
    if scores is not None:
        payload["scores"] = scores
    return payload


def _settled(home: int, away: int) -> dict[str, Any]:
    """A settled fixture, including the `periods` breakdown the live API returns."""
    return _event(
        "settled",
        {
            "home": home,
            "away": away,
            "periods": {"ft": {"home": home, "away": away}, "p1": {"home": 0, "away": 0}},
        },
    )


async def _settle_one(payload: dict[str, Any]) -> Any:
    provider = _provider(_routed({("event", AIRDRIE_ID): payload}))
    [settlement] = await provider.settle([AIRDRIE_ID])
    return settlement


class TestSettle:
    async def test_reads_events_not_odds(self) -> None:
        """Settlement must never read the odds endpoints.

        Verified live on 2026-08-04: once a fixture settles, `/odds` still returns it with
        `status: "settled"` but drops `scores` entirely, and `/odds/multi` omits it. A
        settle path built on either would leave every pick pending forever.
        """
        record: list[httpx.Request] = []
        provider = _provider(_routed({("event", AIRDRIE_ID): _settled(2, 0)}, record=record))
        [settlement] = await provider.settle([AIRDRIE_ID])

        assert settlement.settled is True
        assert [r.url.path for r in record] == [f"/v3/events/{AIRDRIE_ID}"]

    async def test_home_win(self) -> None:
        settlement = await _settle_one(_settled(2, 0))

        assert settlement.settled is True and settlement.void is False
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.MATCH_ODDS, Outcome.HOME)] is True
        assert results[(Market.MATCH_ODDS, Outcome.DRAW)] is False
        assert results[(Market.MATCH_ODDS, Outcome.AWAY)] is False

    async def test_away_win(self) -> None:
        settlement = await _settle_one(_settled(0, 3))
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.MATCH_ODDS, Outcome.AWAY)] is True
        assert results[(Market.MATCH_ODDS, Outcome.HOME)] is False

    async def test_draw(self) -> None:
        settlement = await _settle_one(_settled(1, 1))
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.MATCH_ODDS, Outcome.DRAW)] is True

    async def test_both_teams_scored(self) -> None:
        settlement = await _settle_one(_settled(2, 1))
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)] is True
        assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)] is False

    async def test_clean_sheet(self) -> None:
        settlement = await _settle_one(_settled(3, 0))
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)] is True
        assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)] is False

    async def test_goalless_draw_settles_both_markets(self) -> None:
        settlement = await _settle_one(_settled(0, 0))
        results = {(o.market, o.outcome): o.won for o in settlement.outcomes}
        assert results[(Market.MATCH_ODDS, Outcome.DRAW)] is True
        assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)] is True

    @pytest.mark.parametrize("status", ["cancelled", "postponed", "abandoned", "Cancelled"])
    async def test_cancelled_or_postponed_is_void(self, status: str) -> None:
        """A cancelled fixture still carries a 0-0 score, so status must be read first."""
        settlement = await _settle_one(_event(status, {"home": 0, "away": 0}))

        assert settlement.settled is True
        assert settlement.void is True
        assert settlement.outcomes == []

    async def test_pending_fixture_with_a_zero_score_is_not_settled(self) -> None:
        """Every unplayed fixture reports 0-0. Settling on a score's presence would
        resolve the entire slate as goalless draws before a ball is kicked."""
        settlement = await _settle_one(_event("pending", {"home": 0, "away": 0}))
        assert settlement.settled is False
        assert settlement.void is False

    async def test_live_fixture_is_not_settled(self) -> None:
        """An in-play fixture carries the score *so far* — settling would pay out at
        half time."""
        settlement = await _settle_one(
            _event("live", {"home": 1, "away": 0, "periods": {"p1": {"home": 1, "away": 0}}})
        )
        assert settlement.settled is False

    async def test_settled_without_a_score_stays_pending(self) -> None:
        """Fail safe: no score means retry on Sunday/Monday, never a silent void."""
        settlement = await _settle_one(_event("settled"))
        assert settlement.settled is False
        assert settlement.void is False

    async def test_unknown_status_is_not_settled(self) -> None:
        settlement = await _settle_one(_event("some-new-vocabulary", {"home": 1, "away": 0}))
        assert settlement.settled is False

    async def test_missing_event_is_reported_unsettled(self) -> None:
        provider = _provider(_routed({}))
        [settlement] = await provider.settle(["no-such-event"])
        assert settlement.provider_event_id == "no-such-event"
        assert settlement.settled is False

    async def test_settle_empty_returns_empty(self) -> None:
        assert await _provider(_routed({})).settle([]) == []

    async def test_duplicate_event_ids_are_requested_once(self) -> None:
        record: list[httpx.Request] = []
        provider = _provider(_routed({("event", AIRDRIE_ID): _settled(1, 0)}, record=record))
        settlements = await provider.settle([AIRDRIE_ID, AIRDRIE_ID])

        assert len(settlements) == 1
        assert len(record) == 1


# ── Transport ──────────────────────────────────────────────────────────────────


class TestTransport:
    def test_missing_key_is_rejected_at_construction(self) -> None:
        with pytest.raises(OddsProviderAuthError, match="ODDS_API_KEY"):
            OddsApiProvider("")

    async def test_login_and_keep_alive_are_no_ops(self) -> None:
        provider = _provider(_routed({}))
        assert await provider.login() == ""
        await provider.keep_alive()  # no session to refresh

    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_rejected_key_raises_immediately(self, status_code: int) -> None:
        calls = {"n": 0}

        def handler(_r: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(status_code)

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(OddsProviderAuthError, match="rejected the API key"):
            await provider.fetch_odds([AIRDRIE_ID])
        assert calls["n"] == 1  # not retried — retries would burn a rate-limited quota

    async def test_a_rate_limited_response_is_not_retried(self) -> None:
        """Batch 48: retrying a ``429`` is the one thing guaranteed to keep it a ``429``.

        This used to be treated as transient alongside 5xx, so a single rate-limited
        slate load became four upstream calls with doubling backoff. On 2026-08-21 two
        diagnostic loads cost roughly 40-80 requests through that amplification and
        slowed their own recovery, while the pick screen answered ``500``.
        """
        calls = {"n": 0}

        def handler(_r: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(429)

        provider = _provider(httpx.MockTransport(handler))
        with patch("src.services.odds_api.asyncio.sleep", new_callable=AsyncMock) as slept:
            with pytest.raises(OddsProviderAPIError, match="429"):
                await provider.fetch_odds([AIRDRIE_ID])

        assert calls["n"] == 1, "one attempt, not four"
        assert slept.await_count == 0, "and no backoff spent waiting to make it worse"

    async def test_a_server_error_is_still_retried(self) -> None:
        """The other half of the split: a 5xx is the case where trying again is right."""
        calls = {"n": 0}

        def handler(_r: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, json=AIRDRIE_ODDS)

        provider = _provider(httpx.MockTransport(handler))
        with patch("src.services.odds_api.asyncio.sleep", new_callable=AsyncMock):
            odds = await provider.fetch_odds([AIRDRIE_ID])

        assert len(odds) == 1
        assert calls["n"] == 3

    async def test_persistent_server_error_raises(self) -> None:
        calls = {"n": 0}

        def handler(_r: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503)

        provider = _provider(httpx.MockTransport(handler))
        with patch("src.services.odds_api.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OddsProviderAPIError, match="503"):
                await provider.fetch_odds([AIRDRIE_ID])

        assert calls["n"] == 4, "the initial attempt plus _MAX_RETRIES"

    async def test_non_json_body_raises(self) -> None:
        provider = _provider(httpx.MockTransport(lambda _r: httpx.Response(200, text="<html>")))
        with pytest.raises(OddsProviderAPIError, match="non-JSON"):
            await provider.fetch_odds([AIRDRIE_ID])

    async def test_wrapped_list_bodies_are_accepted(self) -> None:
        """A `{"data": [...]}` wrapper must not take the slate down."""
        transport = _routed({"/leagues": {"data": LEAGUES}, ("events", SL1): []})
        provider = _provider(transport)
        leagues = await provider._all_leagues()
        assert [lg.id for lg in leagues] == [lg["slug"] for lg in LEAGUES]
