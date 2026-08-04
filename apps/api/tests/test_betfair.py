"""Tests for the Betfair adapter.

The core acceptance is the domain logic exercised against ``FakeBetfair`` — slate,
odds snapshot, and settlement. The live :class:`Betfair` client's HTTP layer (interactive
login / keepAlive, JSON-RPC parsing, error + retry handling) is driven with an
``httpx.MockTransport`` so nothing here touches a real Betfair session.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.betfair import (
    _BETTING_BASE_URL,
    _IDENTITY_BASE_URL,
    SAMPLE_ARSENAL_SEL,
    SAMPLE_BRECHIN_SEL,
    SAMPLE_BTTS_YES_SEL,
    SAMPLE_CHELSEA_SEL,
    SAMPLE_DRAW_SEL,
    SAMPLE_EPL_BTTS_MKT,
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    TARGET_COMPETITION_NAMES,
    Betfair,
    BetfairAPIError,
    BetfairAuthError,
    FakeBetfair,
    Market,
    Outcome,
)


def test_target_competitions_include_betfair_sponsored_english_names() -> None:
    """Betfair lists the three English divisions under sponsored names.

    Confirmed against the live competition list on 2026-08-04. Dropping these
    silently hides every Championship, League 1, and League 2 fixture, because
    competition matching is exact rather than fuzzy.
    """
    for name in (
        "English Sky Bet Championship",
        "English Sky Bet League 1",
        "English Sky Bet League 2",
    ):
        assert name in TARGET_COMPETITION_NAMES, f"{name} missing — English coverage would be lost"


def test_target_competitions_are_matched_case_insensitively_without_duplicates() -> None:
    folded = [n.strip().casefold() for n in TARGET_COMPETITION_NAMES]
    assert len(folded) == len(set(folded)), "duplicate competition names differing only by case"


# ══ FakeBetfair — slate ═════════════════════════════════════════════════════════


class TestFetchSlate:
    async def test_returns_only_saturday_3pm_fixtures(self) -> None:
        slate = await FakeBetfair.with_sample_data().fetch_slate(SAMPLE_SATURDAY)

        assert slate.saturday == date(2026, 8, 1)
        # Two 15:00 kick-offs; the 12:30 "Liverpool v Everton" decoy is dropped.
        matchups = [(f.home, f.away) for f in slate.fixtures]
        assert matchups == [
            ("Arsenal", "Chelsea"),
            ("Forfar Athletic", "Brechin City"),
        ]
        assert not any(f.home == "Liverpool" for f in slate.fixtures)

    async def test_fixture_fields_are_populated(self) -> None:
        slate = await FakeBetfair.with_sample_data().fetch_slate(SAMPLE_SATURDAY)

        epl = next(f for f in slate.fixtures if f.betfair_event_id == SAMPLE_EPL_EVENT_ID)
        assert epl.competition == "English Premier League"
        assert epl.home == "Arsenal"
        assert epl.away == "Chelsea"
        # 15:00 BST is 14:00Z.
        assert epl.kickoff_utc == datetime.fromisoformat("2026-08-01T14:00:00+00:00")

    async def test_covers_scottish_lower_league(self) -> None:
        # The whole reason for Betfair: it prices the Scottish lower divisions.
        slate = await FakeBetfair.with_sample_data().fetch_slate(SAMPLE_SATURDAY)

        sl2 = next(f for f in slate.fixtures if f.betfair_event_id == SAMPLE_SL2_EVENT_ID)
        assert sl2.competition == "Scottish League Two"
        assert (sl2.home, sl2.away) == ("Forfar Athletic", "Brechin City")

    async def test_non_target_competition_is_ignored(self) -> None:
        # "Spanish La Liga" is in the canned competitions but not a target division.
        slate = await FakeBetfair.with_sample_data().fetch_slate(SAMPLE_SATURDAY)
        assert all(
            f.competition in {"English Premier League", "Scottish League Two"}
            for f in slate.fixtures
        )


# ══ FakeBetfair — odds snapshot ═════════════════════════════════════════════════


class TestFetchOdds:
    async def test_maps_match_odds_and_btts_outcomes(self) -> None:
        [fixture] = await FakeBetfair.with_sample_data().fetch_odds([SAMPLE_EPL_EVENT_ID])

        assert fixture.betfair_event_id == SAMPLE_EPL_EVENT_ID
        by_key = {(s.market, s.outcome): s for s in fixture.selections}

        home = by_key[(Market.MATCH_ODDS, Outcome.HOME)]
        assert home.runner_name == "Arsenal"
        assert home.betfair_selection_id == SAMPLE_ARSENAL_SEL
        assert home.betfair_market_id == SAMPLE_EPL_MATCH_ODDS_MKT
        assert home.back_price == 1.9

        assert by_key[(Market.MATCH_ODDS, Outcome.AWAY)].betfair_selection_id == SAMPLE_CHELSEA_SEL
        assert by_key[(Market.MATCH_ODDS, Outcome.AWAY)].back_price == 4.3
        assert by_key[(Market.MATCH_ODDS, Outcome.DRAW)].betfair_selection_id == SAMPLE_DRAW_SEL
        assert by_key[(Market.MATCH_ODDS, Outcome.DRAW)].runner_name == "The Draw"

        assert by_key[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)].back_price == 1.8
        assert by_key[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)].back_price == 2.05

    async def test_only_offers_selections_betfair_prices(self) -> None:
        # The Scottish BTTS "No" runner has no back offers → must not be offered.
        [fixture] = await FakeBetfair.with_sample_data().fetch_odds([SAMPLE_SL2_EVENT_ID])
        by_key = {(s.market, s.outcome): s for s in fixture.selections}

        assert (Market.BOTH_TEAMS_TO_SCORE, Outcome.YES) in by_key
        assert (Market.BOTH_TEAMS_TO_SCORE, Outcome.NO) not in by_key
        # Match Odds is fully priced.
        assert by_key[(Market.MATCH_ODDS, Outcome.HOME)].betfair_selection_id == SAMPLE_FORFAR_SEL
        assert by_key[(Market.MATCH_ODDS, Outcome.AWAY)].betfair_selection_id == SAMPLE_BRECHIN_SEL

    async def test_returns_one_entry_per_event(self) -> None:
        odds = await FakeBetfair.with_sample_data().fetch_odds(
            [SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID]
        )
        assert {o.betfair_event_id for o in odds} == {SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID}

    async def test_empty_event_list_returns_empty(self) -> None:
        assert await FakeBetfair.with_sample_data().fetch_odds([]) == []


# ══ FakeBetfair — settlement ════════════════════════════════════════════════════


class TestSettle:
    async def test_open_market_is_not_settled(self) -> None:
        # Before Betfair closes the market, settle() reports it unsettled with no winner.
        [settlement] = await FakeBetfair.with_sample_data().settle([SAMPLE_EPL_MATCH_ODDS_MKT])
        assert settlement.settled is False
        assert settlement.status == "OPEN"
        assert settlement.winners == []

    async def test_closed_market_reports_winner(self) -> None:
        fake = FakeBetfair.with_sample_data()
        fake.close_markets(
            {
                SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
                SAMPLE_EPL_BTTS_MKT: SAMPLE_BTTS_YES_SEL,
            }
        )

        settlements = {
            s.betfair_market_id: s
            for s in await fake.settle([SAMPLE_EPL_MATCH_ODDS_MKT, SAMPLE_EPL_BTTS_MKT])
        }

        match_odds = settlements[SAMPLE_EPL_MATCH_ODDS_MKT]
        assert match_odds.settled is True
        assert match_odds.status == "CLOSED"
        assert match_odds.winners == [SAMPLE_ARSENAL_SEL]

        runners = {r.betfair_selection_id: r for r in match_odds.runners}
        assert runners[SAMPLE_ARSENAL_SEL].won is True
        assert runners[SAMPLE_CHELSEA_SEL].won is False
        assert runners[SAMPLE_CHELSEA_SEL].status == "LOSER"
        assert runners[SAMPLE_DRAW_SEL].won is False

        assert settlements[SAMPLE_EPL_BTTS_MKT].winners == [SAMPLE_BTTS_YES_SEL]

    async def test_settle_empty_returns_empty(self) -> None:
        assert await FakeBetfair.with_sample_data().settle([]) == []

    async def test_full_flow_open_odds_then_settle(self) -> None:
        # Snapshot odds while open, then close and settle — one fake, realistic lifecycle.
        fake = FakeBetfair.with_sample_data()
        [fixture] = await fake.fetch_odds([SAMPLE_SL2_EVENT_ID])
        home = next(
            s
            for s in fixture.selections
            if (s.market, s.outcome) == (Market.MATCH_ODDS, Outcome.HOME)
        )

        fake.close_markets({home.betfair_market_id: home.betfair_selection_id})
        [settlement] = await fake.settle([home.betfair_market_id])
        assert settlement.settled is True
        assert settlement.winners == [home.betfair_selection_id]


class TestFakeAuth:
    async def test_keep_alive_requires_login(self) -> None:
        fake = FakeBetfair.with_sample_data()
        with pytest.raises(BetfairAuthError):
            await fake.keep_alive()

        assert await fake.login() == "FAKE-SESSION-TOKEN"
        await fake.keep_alive()  # no longer raises


# ══ Live Betfair client — HTTP layer via MockTransport ══════════════════════════


def _ok_login(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"token": "SESSION-1", "product": "APP", "status": "SUCCESS", "error": ""}
    )


def _client(
    betting_handler: httpx.MockTransport | None = None,
    identity_handler: httpx.MockTransport | None = None,
) -> Betfair:
    identity = httpx.AsyncClient(
        transport=identity_handler or httpx.MockTransport(_ok_login), base_url=_IDENTITY_BASE_URL
    )
    betting = httpx.AsyncClient(
        transport=betting_handler or httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
        base_url=_BETTING_BASE_URL,
    )
    return Betfair("app-key", "user", "pass", identity_client=identity, betting_client=betting)


def _rpc_result(result: list[dict[str, Any]]) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda _r: httpx.Response(200, json={"jsonrpc": "2.0", "result": result, "id": 1})
    )


class TestLiveLogin:
    async def test_login_success_stores_token(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["app_key"] = request.headers.get("X-Application", "")
            seen["body"] = request.content.decode()
            return _ok_login(request)

        client = _client(identity_handler=httpx.MockTransport(handler))
        token = await client.login()

        assert token == "SESSION-1"
        assert seen["app_key"] == "app-key"
        assert "username=user" in seen["body"]  # form-encoded credentials
        assert "password=pass" in seen["body"]

    async def test_login_failure_raises(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"token": "", "status": "FAIL", "error": "INVALID_USERNAME_OR_PASSWORD"},
            )

        client = _client(identity_handler=httpx.MockTransport(handler))
        with pytest.raises(BetfairAuthError, match="INVALID_USERNAME_OR_PASSWORD"):
            await client.login()

    async def test_certificate_login_uses_noninteractive_endpoint(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["host"] = request.url.host
            if request.url.path == "/api/certlogin":
                # The real certlogin endpoint returns sessionToken/loginStatus,
                # not the token/status pair the interactive endpoint uses.
                # Verified against the live endpoint on 2026-08-03.
                return httpx.Response(
                    200, json={"sessionToken": "CERT-SESSION-1", "loginStatus": "SUCCESS"}
                )
            return httpx.Response(
                200,
                json={"token": "SESSION-2", "status": "SUCCESS", "error": ""},
            )

        identity = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=_IDENTITY_BASE_URL,
        )
        client = Betfair(
            "app-key",
            "user",
            "pass",
            cert_file="/tmp/betfair.crt",
            key_file="/tmp/betfair.key",
            identity_client=identity,
            betting_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
                base_url=_BETTING_BASE_URL,
            ),
        )

        token = await client.login()
        assert seen["path"] == "/api/certlogin"
        assert seen["host"] == "identitysso-cert.betfair.com"
        # The certlogin field names must actually be parsed, not silently
        # defaulted to empty and reported as "Betfair login failed: UNKNOWN".
        assert token == "CERT-SESSION-1"
        await client.keep_alive()
        assert seen["path"] == "/api/keepAlive"
        assert seen["host"] == "identitysso.betfair.com"
        await client.close()

    async def test_certificate_login_rejects_failed_login_status(self) -> None:
        """A failed certlogin must surface its real loginStatus, not UNKNOWN."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"sessionToken": "", "loginStatus": "CERT_AUTH_REQUIRED"}
            )

        client = Betfair(
            "app-key",
            "user",
            "pass",
            cert_file="/tmp/betfair.crt",
            key_file="/tmp/betfair.key",
            identity_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=_IDENTITY_BASE_URL
            ),
            betting_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
                base_url=_BETTING_BASE_URL,
            ),
        )
        with pytest.raises(BetfairAuthError, match="CERT_AUTH_REQUIRED"):
            await client.login()
        await client.close()

    async def test_keep_alive_refreshes_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/login":
                return _ok_login(request)
            return httpx.Response(
                200, json={"token": "SESSION-2", "status": "SUCCESS", "error": ""}
            )

        client = _client(identity_handler=httpx.MockTransport(handler))
        await client.login()
        await client.keep_alive()
        # keepAlive rotated the session token; the next RPC must carry the new one.
        assert client._require_token() == "SESSION-2"

    async def test_keep_alive_failure_clears_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/login":
                return _ok_login(request)
            return httpx.Response(200, json={"status": "FAIL", "error": "NO_SESSION"})

        client = _client(identity_handler=httpx.MockTransport(handler))
        await client.login()
        with pytest.raises(BetfairAuthError, match="NO_SESSION"):
            await client.keep_alive()
        with pytest.raises(BetfairAuthError, match="Not logged in"):
            client._require_token()


class TestLiveRpc:
    async def test_rpc_requires_login(self) -> None:
        client = _client()
        with pytest.raises(BetfairAuthError, match="Not logged in"):
            await client.list_competitions(event_type_id="1")

    async def test_list_market_catalogue_parses_response(self) -> None:
        catalogue = {
            "marketId": "1.234",
            "marketName": "Match Odds",
            "description": {"marketType": "MATCH_ODDS"},
            "event": {"id": "e1", "name": "A v B", "openDate": "2026-08-01T14:00:00.000Z"},
            "runners": [
                {"selectionId": 1, "runnerName": "A", "sortPriority": 1},
                {"selectionId": 2, "runnerName": "B", "sortPriority": 2},
            ],
        }
        client = _client(betting_handler=_rpc_result([catalogue]))
        await client.login()

        [parsed] = await client.list_market_catalogue(event_ids=["e1"], market_types=["MATCH_ODDS"])
        assert parsed.marketId == "1.234"
        assert parsed.description is not None
        assert parsed.description.marketType == "MATCH_ODDS"
        assert [r.runnerName for r in parsed.runners] == ["A", "B"]

    async def test_rpc_error_envelope_raises(self) -> None:
        handler = httpx.MockTransport(
            lambda _r: httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "error": {"code": -32099, "message": "APP_KEY_INVALID"},
                    "id": 1,
                },
            )
        )
        client = _client(betting_handler=handler)
        await client.login()
        with pytest.raises(BetfairAPIError, match="APP_KEY_INVALID"):
            await client.list_competitions(event_type_id="1")

    async def test_rpc_retries_on_server_error(self) -> None:
        calls = {"n": 0}

        def handler(_r: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": 1})

        client = _client(betting_handler=httpx.MockTransport(handler))
        await client.login()
        with patch("src.services.betfair.asyncio.sleep", new_callable=AsyncMock):
            result = await client.list_market_book(market_ids=["1.1"])

        assert result == []
        assert calls["n"] == 2  # first 503 retried, second call succeeded

    async def test_end_to_end_slate_over_mock_transport(self) -> None:
        # Prove the live client's primitives feed the shared domain logic: a full
        # listCompetitions → listEvents → fetch_slate round-trip over JSON-RPC.
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            if "listCompetitions" in body:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "result": [{"competition": {"id": "c1", "name": "Scottish League Two"}}],
                        "id": 1,
                    },
                )
            if "listEvents" in body:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "result": [
                            {
                                "event": {
                                    "id": "e9",
                                    "name": "Forfar Athletic v Brechin City",
                                    "countryCode": "GB",
                                    "openDate": "2026-08-01T14:00:00.000Z",
                                }
                            },
                            # Same 15:00 UK kick-off, but not a British match — the
                            # country rule must drop it.
                            {
                                "event": {
                                    "id": "e10",
                                    "name": "Hobro v AB",
                                    "countryCode": "DK",
                                    "openDate": "2026-08-01T14:00:00.000Z",
                                }
                            },
                        ],
                        "id": 1,
                    },
                )
            raise AssertionError(f"unexpected RPC body: {body}")

        client = _client(betting_handler=httpx.MockTransport(handler))
        await client.login()
        slate = await client.fetch_slate(date(2026, 8, 1))

        assert len(slate.fixtures) == 1
        assert slate.fixtures[0].competition == "Scottish League Two"
        assert slate.fixtures[0].home == "Forfar Athletic"
        assert all(f.home != "Hobro" for f in slate.fixtures)

    async def test_slate_includes_any_british_competition(self) -> None:
        """The slate is defined by country and kick-off, not a division allow-list.

        A League Cup tie must be offerable: on 2026-08-08 the cup and the National
        League were the entire British 15:00 card.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            if "listCompetitions" in body:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "result": [
                            {"competition": {"id": "c9", "name": "English Football League Cup"}}
                        ],
                        "id": 1,
                    },
                )
            if "listEvents" in body:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "result": [
                            {
                                "event": {
                                    "id": "e11",
                                    "name": "Burnley v Notts Co",
                                    "countryCode": "GB",
                                    "openDate": "2026-08-01T14:00:00.000Z",
                                }
                            }
                        ],
                        "id": 1,
                    },
                )
            raise AssertionError(f"unexpected RPC body: {body}")

        client = _client(betting_handler=httpx.MockTransport(handler))
        await client.login()
        slate = await client.fetch_slate(date(2026, 8, 1))

        assert [f.competition for f in slate.fixtures] == ["English Football League Cup"]
        assert slate.fixtures[0].home == "Burnley"
