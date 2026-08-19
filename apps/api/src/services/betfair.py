"""Betfair Exchange adapter — a fallback odds source, and the canned data behind the tests.

**This is no longer the production odds source.** ADR 0002 replaced it with
:mod:`src.services.odds_api` for two blocking reasons:

* The Exchange does not price the Scottish lower divisions the owner requires. Those live
  on the Betfair *Sportsbook*, a different product; ``SportsAPING`` serves the Exchange
  only, so no configuration reaches them. Confirmed on 2026-08-04 by four independent
  checks — the full 98-competition list, competition ids 106 and 108-110, an unfiltered
  sweep of every soccer event that Saturday, and a text search on twenty lower-league
  clubs.
* The Exchange refuses the production login with ``BETTING_RESTRICTED_LOCATION``. The
  deployment platform serves only the Netherlands, the USA, and Singapore, and the
  Exchange is unavailable in all three.

An earlier version of this docstring claimed Scottish lower-division pricing as the reason
Betfair was chosen. That premise was wrong, and the coverage probe is what disproved it.

What remains here is still useful and still runs:

* :class:`Betfair` — the live client (certificate login + keepAlive, JSON-RPC over httpx),
  selectable with ``ODDS_PROVIDER=betfair`` as a fallback source.
* :class:`FakeBetfair` — canned catalogues and books backing every test and the staging /
  end-to-end flow, so the whole app is demo-able without any live session.

Both implement :class:`~src.services.odds_provider.OddsProvider`, so they speak the game's
vocabulary — market, outcome, price — rather than Betfair's. The Exchange's own nouns
(events → markets → runners, settlement by runner status ``WINNER``) stay behind the four
``list_*`` primitives and never reach the database; revision ``005`` removed the last
Betfair identifiers from ``fixtures`` and ``picks``.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog
from pydantic import AliasChoices, BaseModel, Field

from src.config import settings
from src.services.odds_provider import (
    MARKET_BTTS,
    MARKET_MATCH_ODDS,
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderAuthError,
    OddsProviderError,
    Outcome,
    OutcomeResult,
    Selection,
    Slate,
    SlateFixture,
    SlateWindow,
    as_utc,
    btts_outcome,
    iso_z,
    match_odds_outcome,
    split_event_name,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ── Betfair endpoints / constants ──────────────────────────────────────────────

_IDENTITY_BASE_URL = "https://identitysso.betfair.com"
_IDENTITY_CERT_BASE_URL = "https://identitysso-cert.betfair.com"
_BETTING_BASE_URL = "https://api.betfair.com"
_RPC_PATH = "/exchange/betting/json-rpc/v1"
_RPC_PREFIX = "SportsAPING/v1.0/"

SOCCER_EVENT_TYPE_ID = "1"
MARKET_TYPES: tuple[str, ...] = (MARKET_MATCH_ODDS, MARKET_BTTS)

_MARKET_CLOSED = "CLOSED"
_RUNNER_WINNER = "WINNER"
_RUNNER_REMOVED = "REMOVED"

# The slate rule: any British football kicking off at 15:00 on the Saturday, in any
# competition. Betfair tags events with an ISO country code, and "GB" covers the English,
# Scottish, Welsh, and Northern Irish games this league cares about.
#
# This replaced a fixed list of eight divisions on 2026-08-04. The list starved the
# slate whenever those divisions were not playing: on Saturday 2026-08-08 it produced
# two fixtures — six selections for a fifteen-member league — while the country rule
# produced thirty-eight fixtures and 114 selections, because that Saturday was League
# Cup first round plus a full National League card.
SLATE_COUNTRIES: frozenset[str] = frozenset({"GB"})

# Retained as an *optional* narrowing filter for callers that want specific divisions,
# and as documentation of Betfair's live competition naming. No longer applied by
# default — `fetch_slate` selects on country and kick-off time instead.
#
# Names are matched case-insensitively and *exactly*, so a name that does not appear
# verbatim in Betfair's competition list is silently skipped rather than erroring.
#
# The live coverage probe on 2026-08-04 confirmed Betfair carries the three English
# divisions below the Premier League under their **sponsored** names — "English Sky Bet
# Championship", "English Sky Bet League 1", "English Sky Bet League 2". The
# unsponsored spellings this set originally used matched nothing, so those three
# divisions would have been invisible all season.
#
# Both spellings are kept deliberately. Sponsor names change between seasons, and an
# unmatched entry costs nothing because matching is exact — it simply never fires.
#
# The Scottish League One / Two entries never matched anything and never will: those
# divisions are not on the Exchange at all. They are kept only so the shape of this set
# documents what was probed. odds-api.io is what actually prices them.
TARGET_COMPETITION_NAMES: frozenset[str] = frozenset(
    {
        # English — confirmed live 2026-08-04
        "English Premier League",
        "English Sky Bet Championship",
        "English Sky Bet League 1",
        "English Sky Bet League 2",
        # English — unsponsored fallbacks
        "English Championship",
        "English League 1",
        "English League 2",
        # Scottish — confirmed live 2026-08-04
        "Scottish Premiership",
        "Scottish Championship",
        # Scottish — never present on the Exchange; see the module docstring
        "Scottish League One",
        "Scottish League Two",
        "Scottish League 1",
        "Scottish League 2",
    }
)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0  # seconds
_TIMEOUT = 30.0


# ── Exceptions ─────────────────────────────────────────────────────────────────
# Subclasses of the provider-neutral errors so callers can catch either vocabulary.


class BetfairError(OddsProviderError):
    """Base error for Betfair adapter failures."""


class BetfairAuthError(OddsProviderAuthError, BetfairError):
    """Login / keepAlive failed, or an operation was attempted before login."""


class BetfairAPIError(OddsProviderAPIError, BetfairError):
    """The betting JSON-RPC API returned an error (or an unusable response)."""


# ── Raw Betfair response models (``BF*``) ──────────────────────────────────────
# Only the fields we consume are modelled; unknown keys are ignored by pydantic.


class BFIdentityResponse(BaseModel):
    """Response from ``identitysso`` login / keepAlive.

    The two identity endpoints disagree on field names, so both spellings are
    accepted:

    * ``/api/login`` and ``/api/keepAlive`` on ``identitysso`` return
      ``token`` / ``status``;
    * ``/api/certlogin`` on ``identitysso-cert`` returns ``sessionToken`` /
      ``loginStatus`` — verified against the live endpoint on 2026-08-03.

    Modelling only the first spelling silently parses a *successful* certificate
    login as an empty token with an empty status, which then surfaces as the
    misleading ``Betfair login failed: UNKNOWN``.
    """

    token: str = Field("", validation_alias=AliasChoices("token", "sessionToken"))
    product: str = ""
    status: str = Field("", validation_alias=AliasChoices("status", "loginStatus"))
    error: str = ""


class BFCompetition(BaseModel):
    id: str
    name: str


class BFCompetitionResult(BaseModel):
    competition: BFCompetition
    marketCount: int = 0
    competitionRegion: str = ""


class BFEvent(BaseModel):
    id: str
    name: str
    countryCode: str | None = None
    timezone: str | None = None
    openDate: datetime


class BFEventResult(BaseModel):
    event: BFEvent
    marketCount: int = 0


class BFRunnerCatalogue(BaseModel):
    selectionId: int
    runnerName: str
    handicap: float = 0.0
    sortPriority: int = 0


class BFMarketDescription(BaseModel):
    marketType: str = ""


class BFMarketCatalogue(BaseModel):
    marketId: str
    marketName: str = ""
    marketStartTime: datetime | None = None
    description: BFMarketDescription | None = None
    event: BFEvent | None = None
    runners: list[BFRunnerCatalogue] = []


class BFPriceSize(BaseModel):
    price: float
    size: float = 0.0


class BFExchangePrices(BaseModel):
    availableToBack: list[BFPriceSize] = []
    availableToLay: list[BFPriceSize] = []


class BFRunnerBook(BaseModel):
    selectionId: int
    status: str = ""  # ACTIVE, WINNER, LOSER, REMOVED, …
    ex: BFExchangePrices | None = None


class BFMarketBook(BaseModel):
    marketId: str
    status: str = ""  # OPEN, SUSPENDED, CLOSED, …
    runners: list[BFRunnerBook] = []


# ── Helpers (shared by both implementations via the base class) ─────────────────


def _market_type_code(catalogue: BFMarketCatalogue) -> str | None:
    """The market type of a catalogue entry (``MATCH_ODDS`` / ``BOTH_TEAMS_TO_SCORE``).

    Prefers ``description.marketType`` (exact, when the projection includes it); falls
    back to classifying by the market name.
    """
    if catalogue.description is not None and catalogue.description.marketType:
        return catalogue.description.marketType
    name = catalogue.marketName.strip().casefold()
    if name == "match odds":
        return MARKET_MATCH_ODDS
    if name in {"both teams to score", "both teams to score?"}:
        return MARKET_BTTS
    return None


def _best_back_price(runner: BFRunnerBook) -> Decimal | None:
    """The best available back price, or ``None`` when Betfair isn't pricing it.

    ``availableToBack`` is sorted best-first, so index 0 is the price a backer gets.
    ``None`` drives the *only offer selections the source prices* rule. The float the
    Exchange sends is converted via ``str`` so the stored price is the decimal Betfair
    displayed rather than its binary approximation.
    """
    if runner.ex is None or not runner.ex.availableToBack:
        return None
    return Decimal(str(runner.ex.availableToBack[0].price))


def _outcome_for(
    catalogue_runner: BFRunnerCatalogue, market: Market, home: str, away: str
) -> Outcome | None:
    if market is Market.MATCH_ODDS:
        return match_odds_outcome(catalogue_runner.runnerName, home, away)
    return btts_outcome(catalogue_runner.runnerName)


# ── Abstract adapter (domain logic lives here) ─────────────────────────────────


class BetfairAdapter(OddsProvider):
    """The port's three domain operations, built on four raw Betfair primitives.

    Subclasses implement only the primitives (``login`` / ``keep_alive`` and the four
    ``list_*`` calls); ``fetch_slate`` / ``fetch_odds`` / ``settle`` are concrete here so
    both the live client and the fake run identical domain logic.
    """

    # -- primitives (implemented by subclasses) --------------------------------

    @abstractmethod
    async def list_competitions(
        self,
        *,
        event_type_id: str,
        market_countries: Sequence[str] = (),
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
    ) -> list[BFCompetitionResult]: ...

    @abstractmethod
    async def list_events(
        self, *, competition_ids: Sequence[str], from_utc: datetime, to_utc: datetime
    ) -> list[BFEventResult]: ...

    @abstractmethod
    async def list_market_catalogue(
        self, *, event_ids: Sequence[str], market_types: Sequence[str]
    ) -> list[BFMarketCatalogue]: ...

    @abstractmethod
    async def list_market_book(self, *, market_ids: Sequence[str]) -> list[BFMarketBook]: ...

    # -- domain operations (shared) --------------------------------------------

    async def fetch_competitions(
        self, *, countries: Collection[str] = SLATE_COUNTRIES
    ) -> list[Competition]:
        """Every British competition the Exchange carries, in name order.

        The primitive :meth:`fetch_slate` opens with, minus the time bounds: the picker
        is choosing what a league plays in general, so a competition out of season this
        week still belongs in it. One request, and no ``listEvents`` fan-out.
        """
        results = await self.list_competitions(
            event_type_id=SOCCER_EVENT_TYPE_ID,
            market_countries=sorted({c.strip().upper() for c in countries}),
        )
        by_id = {r.competition.id: r.competition.name for r in results}
        competitions = [
            Competition(competition_id=cid, competition=name) for cid, name in by_id.items()
        ]
        competitions.sort(key=lambda c: c.competition)
        return competitions

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
        competition_names: Collection[str] | None = None,
        countries: Collection[str] = SLATE_COUNTRIES,
    ) -> Slate:
        """Return the kick-offs inside ``window`` across every qualifying competition.

        The slate is defined by *country and kick-off time*, not by a fixed list of
        divisions. Any British competition — league, cup, or non-league — counts, so a
        first-round League Cup Saturday is as playable as a league Saturday. Restricting
        to eight named divisions previously starved the slate: on 2026-08-08 it yielded
        two fixtures where the country rule yields thirty-eight.

        ``competition_ids`` is the port's narrowing argument — a league's stored
        selection, matched against the same ids a :class:`SlateFixture` is tagged with,
        applied before the ``listEvents`` fan-out that costs one request per
        competition. ``competition_names`` is the older name-matched form kept for
        callers that only have names; both are ``None`` (no restriction) by default.
        """
        from_utc, to_utc = window.query_bounds(starts_on)
        wanted_countries = {c.strip().upper() for c in countries}
        competitions = await self.list_competitions(
            event_type_id=SOCCER_EVENT_TYPE_ID,
            market_countries=sorted(wanted_countries),
            from_utc=from_utc,
            to_utc=to_utc,
        )
        if competition_ids is not None:
            wanted_ids = set(competition_ids)
            competitions = [c for c in competitions if c.competition.id in wanted_ids]
        if competition_names is not None:
            wanted_lower = {n.strip().casefold() for n in competition_names}
            competitions = [
                c for c in competitions if c.competition.name.strip().casefold() in wanted_lower
            ]
        targets = {c.competition.id: c.competition.name for c in competitions}

        fixtures: list[SlateFixture] = []
        for competition_id, competition_name in targets.items():
            events = await self.list_events(
                competition_ids=[competition_id], from_utc=from_utc, to_utc=to_utc
            )
            for result in events:
                event = result.event
                if not window.contains(event.openDate, starts_on):
                    continue
                # Enforce the country rule on the event as well as in the query. The
                # market-country filter narrows the request; this makes the outcome
                # deterministic and testable against canned data.
                if wanted_countries and (event.countryCode or "").upper() not in wanted_countries:
                    continue
                names = split_event_name(event.name)
                if names is None:
                    log.warning("betfair event name not parseable", event_name=event.name)
                    continue
                home, away = names
                fixtures.append(
                    SlateFixture(
                        provider_event_id=event.id,
                        home=home,
                        away=away,
                        kickoff_utc=as_utc(event.openDate),
                        competition=competition_name,
                        competition_id=competition_id,
                    )
                )

        fixtures.sort(key=lambda f: (f.competition, f.kickoff_utc, f.home))
        return Slate(starts_on=starts_on, fixtures=fixtures)

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        """Snapshot the priced Match Odds + BTTS selections for the given events.

        Applies the core rule — *only offer a selection the source actually prices* — so a
        thin lower-league BTTS market simply yields fewer selections rather than an error.
        """
        if not event_ids:
            return []

        by_event, book_by_market = await self._catalogue_and_books(event_ids)

        odds: list[FixtureOdds] = []
        for event_id, markets in by_event.items():
            event = markets[0].event
            assert event is not None  # markets are only grouped when event is present
            names = split_event_name(event.name)
            if names is None:
                log.warning("betfair event name not parseable", event_name=event.name)
                continue
            home, away = names

            selections: list[Selection] = []
            for catalogue in markets:
                selections.extend(self._selections_for(catalogue, book_by_market, home, away))
            selections.sort(key=lambda s: (s.market.value, s.outcome.value))
            odds.append(
                FixtureOdds(provider_event_id=event_id, home=home, away=away, selections=selections)
            )

        odds.sort(key=lambda o: o.provider_event_id)
        return odds

    async def _catalogue_and_books(
        self, event_ids: Sequence[str]
    ) -> tuple[dict[str, list[BFMarketCatalogue]], dict[str, BFMarketBook]]:
        """Fetch both markets for the events and index them by event and market id."""
        catalogues = await self.list_market_catalogue(
            event_ids=list(event_ids), market_types=list(MARKET_TYPES)
        )
        if not catalogues:
            return {}, {}
        books = await self.list_market_book(market_ids=[c.marketId for c in catalogues])
        book_by_market = {b.marketId: b for b in books}

        by_event: defaultdict[str, list[BFMarketCatalogue]] = defaultdict(list)
        for catalogue in catalogues:
            if catalogue.event is None:
                continue
            by_event[catalogue.event.id].append(catalogue)
        return dict(by_event), book_by_market

    @staticmethod
    def _selections_for(
        catalogue: BFMarketCatalogue,
        book_by_market: Mapping[str, BFMarketBook],
        home: str,
        away: str,
    ) -> list[Selection]:
        """Priced selections for one market, mapping runners to outcomes."""
        code = _market_type_code(catalogue)
        if code not in MARKET_TYPES:
            return []
        market = Market(code)
        book = book_by_market.get(catalogue.marketId)
        if book is None:
            return []
        price_by_selection = {r.selectionId: _best_back_price(r) for r in book.runners}

        selections: list[Selection] = []
        for runner in catalogue.runners:
            price = price_by_selection.get(runner.selectionId)
            if price is None:  # unpriced → not offered
                continue
            outcome = _outcome_for(runner, market, home, away)
            if outcome is None:
                continue
            selections.append(
                Selection(
                    market=market,
                    outcome=outcome,
                    runner_name=runner.runnerName,
                    price=price,
                )
            )
        return selections

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        """Report each event's result from its closed market books.

        A market contributes a result only once Betfair reports it ``CLOSED``, and a
        winning outcome is one whose runner status is ``WINNER``. A runner Betfair
        ``REMOVED`` is left out of ``outcomes`` entirely, which is what makes a pick on it
        void rather than lost — the same rule the Exchange settlement always used.
        """
        if not event_ids:
            return []

        by_event, book_by_market = await self._catalogue_and_books(event_ids)

        settlements: list[EventSettlement] = []
        for event_id in dict.fromkeys(event_ids):
            markets = by_event.get(event_id, [])
            settlements.append(
                self._settlement_for(event_id, markets, book_by_market)
                if markets
                else EventSettlement(provider_event_id=event_id, status="", settled=False)
            )
        return settlements

    @staticmethod
    def _settlement_for(
        event_id: str,
        markets: Sequence[BFMarketCatalogue],
        book_by_market: Mapping[str, BFMarketBook],
    ) -> EventSettlement:
        event = markets[0].event
        names = split_event_name(event.name) if event is not None else None
        home, away = names if names is not None else ("", "")

        settled_markets: list[Market] = []
        outcomes: list[OutcomeResult] = []
        statuses: list[str] = []

        for catalogue in markets:
            code = _market_type_code(catalogue)
            if code not in MARKET_TYPES:
                continue
            book = book_by_market.get(catalogue.marketId)
            if book is None:
                continue
            statuses.append(book.status)
            if book.status.upper() != _MARKET_CLOSED:
                continue
            market = Market(code)
            settled_markets.append(market)
            runner_books = {r.selectionId: r for r in book.runners}
            for runner in catalogue.runners:
                book_runner = runner_books.get(runner.selectionId)
                if book_runner is None or book_runner.status.upper() == _RUNNER_REMOVED:
                    continue  # absent from a settled market → the pick voids
                outcome = _outcome_for(runner, market, home, away)
                if outcome is None:
                    continue
                outcomes.append(
                    OutcomeResult(
                        market=market,
                        outcome=outcome,
                        won=book_runner.status.upper() == _RUNNER_WINNER,
                    )
                )

        return EventSettlement(
            provider_event_id=event_id,
            status=_MARKET_CLOSED if settled_markets else (statuses[0] if statuses else ""),
            settled=bool(settled_markets),
            settled_markets=settled_markets,
            outcomes=outcomes,
        )


# ── Live client ────────────────────────────────────────────────────────────────


class Betfair(BetfairAdapter):
    """Live Betfair client — certificate login + JSON-RPC over httpx.

    Custom ``identity_client`` / ``betting_client`` can be injected to drive the HTTP
    layer with a mock transport in tests.
    """

    def __init__(
        self,
        app_key: str,
        username: str,
        password: str,
        *,
        cert_file: str = "",
        key_file: str = "",
        identity_client: httpx.AsyncClient | None = None,
        betting_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_key = app_key
        self._username = username
        self._password = password
        self._cert_file = cert_file
        self._key_file = key_file
        self._identity = identity_client or httpx.AsyncClient(
            base_url=_IDENTITY_BASE_URL,
            timeout=_TIMEOUT,
            cert=(cert_file, key_file) if cert_file and key_file else None,
        )
        self._betting = betting_client or httpx.AsyncClient(
            base_url=_BETTING_BASE_URL, timeout=_TIMEOUT
        )
        self._session_token: str | None = None

    @classmethod
    def from_settings(cls) -> Betfair:
        """Build a client from ``BF_APP_KEY`` / ``BF_USER`` / ``BF_PASS`` (env)."""
        if not (settings.bf_app_key and settings.bf_user and settings.bf_pass):
            raise BetfairAuthError(
                "Betfair credentials not configured (BF_APP_KEY / BF_USER / BF_PASS)"
            )
        return cls(
            settings.bf_app_key,
            settings.bf_user,
            settings.bf_pass,
            cert_file=settings.bf_cert_file,
            key_file=settings.bf_key_file,
        )

    async def close(self) -> None:
        await self._identity.aclose()
        await self._betting.aclose()

    async def __aenter__(self) -> Betfair:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # -- auth ------------------------------------------------------------------

    async def login(self) -> str:
        path = (
            f"{_IDENTITY_CERT_BASE_URL}/api/certlogin"
            if self._cert_file and self._key_file
            else "/api/login"
        )
        try:
            response = await self._identity.post(
                path,
                data={"username": self._username, "password": self._password},
                headers={"X-Application": self._app_key, "Accept": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BetfairAuthError(f"Betfair login request failed: {exc!r}") from exc

        parsed = BFIdentityResponse.model_validate(response.json())
        if parsed.status != "SUCCESS" or not parsed.token:
            raise BetfairAuthError(
                f"Betfair login failed: {parsed.status or 'UNKNOWN'} {parsed.error}"
            )
        self._session_token = parsed.token
        log.info("betfair login succeeded")
        return parsed.token

    async def keep_alive(self) -> None:
        token = self._require_token()
        try:
            response = await self._identity.post(
                "/api/keepAlive",
                headers={
                    "X-Application": self._app_key,
                    "X-Authentication": token,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BetfairAuthError(f"Betfair keepAlive request failed: {exc!r}") from exc

        parsed = BFIdentityResponse.model_validate(response.json())
        if parsed.status != "SUCCESS":
            self._session_token = None
            raise BetfairAuthError(
                f"Betfair keepAlive failed: {parsed.status or 'UNKNOWN'} {parsed.error}"
            )
        if parsed.token:
            self._session_token = parsed.token

    def _require_token(self) -> str:
        if self._session_token is None:
            raise BetfairAuthError("Not logged in — call login() first")
        return self._session_token

    # -- primitives ------------------------------------------------------------

    async def list_competitions(
        self,
        *,
        event_type_id: str,
        market_countries: Sequence[str] = (),
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
    ) -> list[BFCompetitionResult]:
        market_filter: dict[str, Any] = {"eventTypeIds": [event_type_id]}
        if market_countries:
            market_filter["marketCountries"] = list(market_countries)
        if from_utc is not None and to_utc is not None:
            market_filter["marketStartTime"] = {"from": iso_z(from_utc), "to": iso_z(to_utc)}
        result = await self._rpc("listCompetitions", {"filter": market_filter})
        return [BFCompetitionResult.model_validate(item) for item in result]

    async def list_events(
        self, *, competition_ids: Sequence[str], from_utc: datetime, to_utc: datetime
    ) -> list[BFEventResult]:
        result = await self._rpc(
            "listEvents",
            {
                "filter": {
                    "eventTypeIds": [SOCCER_EVENT_TYPE_ID],
                    "competitionIds": list(competition_ids),
                    "marketStartTime": {"from": iso_z(from_utc), "to": iso_z(to_utc)},
                }
            },
        )
        return [BFEventResult.model_validate(item) for item in result]

    async def list_market_catalogue(
        self, *, event_ids: Sequence[str], market_types: Sequence[str]
    ) -> list[BFMarketCatalogue]:
        result = await self._rpc(
            "listMarketCatalogue",
            {
                "filter": {
                    "eventIds": list(event_ids),
                    "marketTypeCodes": list(market_types),
                },
                "marketProjection": [
                    "MARKET_DESCRIPTION",
                    "RUNNER_DESCRIPTION",
                    "EVENT",
                    "MARKET_START_TIME",
                ],
                "maxResults": 200,
                "sort": "FIRST_TO_START",
            },
        )
        return [BFMarketCatalogue.model_validate(item) for item in result]

    async def list_market_book(self, *, market_ids: Sequence[str]) -> list[BFMarketBook]:
        result = await self._rpc(
            "listMarketBook",
            {
                "marketIds": list(market_ids),
                "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
            },
        )
        return [BFMarketBook.model_validate(item) for item in result]

    # -- JSON-RPC transport ----------------------------------------------------

    async def _rpc(self, method: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """POST a single JSON-RPC call, with retries, and return its ``result`` list."""
        token = self._require_token()
        body = {"jsonrpc": "2.0", "method": f"{_RPC_PREFIX}{method}", "params": params, "id": 1}
        headers = {
            "X-Application": self._app_key,
            "X-Authentication": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._betting.post(_RPC_PATH, json=body, headers=headers)
            except httpx.RequestError as exc:
                if attempt == _MAX_RETRIES:
                    raise BetfairAPIError(
                        f"Network error after {_MAX_RETRIES} retries: {exc!r}"
                    ) from exc
                log.warning(
                    "betfair network error", method=method, attempt=attempt, error=repr(exc)
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == _MAX_RETRIES:
                    raise BetfairAPIError(
                        f"{method} failed with status {response.status_code} after "
                        f"{_MAX_RETRIES} retries"
                    )
                log.warning(
                    "betfair transient error",
                    method=method,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise BetfairAPIError(
                    f"{method} unexpected status {response.status_code}: {response.text[:200]}"
                ) from exc

            payload = response.json()
            if isinstance(payload, dict) and payload.get("error") is not None:
                raise BetfairAPIError(f"{method} JSON-RPC error: {payload['error']}")
            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, list):
                raise BetfairAPIError(f"{method} returned no result list: {str(payload)[:200]}")
            return result

        raise BetfairAPIError(
            f"{method} exhausted retries"
        )  # pragma: no cover — loop always returns/raises


# ── Fake client (canned catalogues/books) ──────────────────────────────────────


class FakeBetfair(BetfairAdapter):
    """In-memory adapter returning canned catalogues/books.

    Backs every test, the staging environment, and the mocked end-to-end flow — no live
    session required. Overrides only the primitives; the domain logic is inherited from
    :class:`BetfairAdapter`, so the fake exercises exactly the code the live client runs.
    """

    def __init__(
        self,
        *,
        competitions: Sequence[BFCompetitionResult] = (),
        events: Mapping[str, Sequence[BFEventResult]] | None = None,
        catalogues: Sequence[BFMarketCatalogue] = (),
        books: Sequence[BFMarketBook] = (),
        session_token: str = "FAKE-SESSION-TOKEN",
    ) -> None:
        self._competitions = list(competitions)
        self._events: dict[str, list[BFEventResult]] = {
            k: list(v) for k, v in (events or {}).items()
        }
        self._catalogues = list(catalogues)
        self._books = {b.marketId: b for b in books}
        self._session_token = session_token
        self._logged_in = False

    # -- primitives ------------------------------------------------------------

    async def login(self) -> str:
        self._logged_in = True
        return self._session_token

    async def keep_alive(self) -> None:
        if not self._logged_in:
            raise BetfairAuthError("Not logged in — call login() first")

    async def close(self) -> None:
        self._logged_in = False

    async def list_competitions(
        self,
        *,
        event_type_id: str,
        market_countries: Sequence[str] = (),
        from_utc: datetime | None = None,
        to_utc: datetime | None = None,
    ) -> list[BFCompetitionResult]:
        # The canned competitions carry no country of their own; the country rule is
        # enforced per event in fetch_slate, which is what the live filter narrows to.
        return list(self._competitions)

    async def list_events(
        self, *, competition_ids: Sequence[str], from_utc: datetime, to_utc: datetime
    ) -> list[BFEventResult]:
        results: list[BFEventResult] = []
        for competition_id in competition_ids:
            for result in self._events.get(competition_id, []):
                if from_utc <= as_utc(result.event.openDate) < to_utc:
                    results.append(result)
        return results

    async def list_market_catalogue(
        self, *, event_ids: Sequence[str], market_types: Sequence[str]
    ) -> list[BFMarketCatalogue]:
        wanted_events = set(event_ids)
        wanted_types = set(market_types)
        return [
            c
            for c in self._catalogues
            if c.event is not None
            and c.event.id in wanted_events
            and _market_type_code(c) in wanted_types
        ]

    async def list_market_book(self, *, market_ids: Sequence[str]) -> list[BFMarketBook]:
        return [self._books[m] for m in market_ids if m in self._books]

    # -- test helpers ----------------------------------------------------------

    def close_markets(self, winners: Mapping[str, int]) -> None:
        """Flip the given markets to ``CLOSED`` with one ``WINNER`` runner each.

        ``winners`` maps market id → the winning selection id; every other runner in that
        market becomes a ``LOSER``. Lets a test drive a fixture from open odds through to
        settlement on one fake object.
        """
        for market_id, winning_selection in winners.items():
            book = self._books.get(market_id)
            if book is None:
                continue
            self._books[market_id] = BFMarketBook(
                marketId=book.marketId,
                status=_MARKET_CLOSED,
                runners=[
                    BFRunnerBook(
                        selectionId=r.selectionId,
                        status=_RUNNER_WINNER if r.selectionId == winning_selection else "LOSER",
                        ex=r.ex,
                    )
                    for r in book.runners
                ],
            )

    @classmethod
    def with_sample_data(cls) -> FakeBetfair:
        """A realistic canned slate: a Premier League and a Scottish League Two fixture.

        * Both kick off Saturday 2026-08-01 15:00 UK (14:00Z under BST).
        * A decoy 12:30 lunchtime kick-off proves the Saturday-15:00 filter drops it.
        * The Scottish BTTS market has an unpriced "No" runner, proving the *only offer
          priced selections* rule.

        The Scottish fixture is canned data illustrating the lower-division case the game
        needs; the live Exchange never carried those divisions (see the module docstring),
        which is why odds-api.io is the production source.
        """
        return cls(**_sample_data())


# ── Canned sample data (reused by tests and the mocked e2e flow) ────────────────

# Stable ids so tests and the sample builder agree.
SAMPLE_SATURDAY = date(2026, 8, 1)
SAMPLE_EPL_ID = "10932509"
SAMPLE_SL2_ID = "10932510"

SAMPLE_EPL_EVENT_ID = "e-epl-1"
SAMPLE_SL2_EVENT_ID = "e-sl2-1"

# Match Odds selection ids
SAMPLE_ARSENAL_SEL = 1001
SAMPLE_CHELSEA_SEL = 1002
SAMPLE_DRAW_SEL = 58805
SAMPLE_FORFAR_SEL = 2001
SAMPLE_BRECHIN_SEL = 2002
SAMPLE_SL2_DRAW_SEL = 58805
# BTTS selection ids (Betfair uses the same 30246/58948 pair across BTTS markets)
SAMPLE_BTTS_YES_SEL = 30246
SAMPLE_BTTS_NO_SEL = 58948

# Market ids
SAMPLE_EPL_MATCH_ODDS_MKT = "1.100000001"
SAMPLE_EPL_BTTS_MKT = "1.100000002"
SAMPLE_SL2_MATCH_ODDS_MKT = "1.100000003"
SAMPLE_SL2_BTTS_MKT = "1.100000004"


def _sample_data() -> dict[str, Any]:
    """Build the canned catalogues/books for :meth:`FakeBetfair.with_sample_data`.

    Everything is round-tripped through ``model_validate`` on raw dicts so the fake holds
    genuine "canned catalogues/books", exercising the same parsing the live client uses.
    """
    kickoff_z = "2026-08-01T14:00:00.000Z"  # 15:00 BST
    lunchtime_z = "2026-08-01T11:30:00.000Z"  # 12:30 BST — decoy, must be filtered out

    competitions = [
        BFCompetitionResult.model_validate(
            {
                "competition": {"id": SAMPLE_EPL_ID, "name": "English Premier League"},
                "marketCount": 3,
            }
        ),
        BFCompetitionResult.model_validate(
            {"competition": {"id": SAMPLE_SL2_ID, "name": "Scottish League Two"}, "marketCount": 2}
        ),
        # A non-target competition that must be ignored even though it has Saturday games.
        BFCompetitionResult.model_validate(
            {"competition": {"id": "99999", "name": "Spanish La Liga"}, "marketCount": 9}
        ),
    ]

    epl_event = {
        "id": SAMPLE_EPL_EVENT_ID,
        "name": "Arsenal v Chelsea",
        "countryCode": "GB",
        "openDate": kickoff_z,
    }
    sl2_event = {
        "id": SAMPLE_SL2_EVENT_ID,
        "name": "Forfar Athletic v Brechin City",
        "countryCode": "GB",
        "openDate": kickoff_z,
    }
    events = {
        SAMPLE_EPL_ID: [
            BFEventResult.model_validate({"event": epl_event, "marketCount": 2}),
            # Decoy lunchtime kick-off — same competition, wrong time.
            BFEventResult.model_validate(
                {
                    "event": {
                        "id": "e-epl-decoy",
                        "name": "Liverpool v Everton",
                        "countryCode": "GB",
                        "openDate": lunchtime_z,
                    },
                    "marketCount": 2,
                }
            ),
        ],
        SAMPLE_SL2_ID: [BFEventResult.model_validate({"event": sl2_event, "marketCount": 2})],
    }

    catalogues = [
        BFMarketCatalogue.model_validate(
            {
                "marketId": SAMPLE_EPL_MATCH_ODDS_MKT,
                "marketName": "Match Odds",
                "description": {"marketType": MARKET_MATCH_ODDS},
                "event": epl_event,
                "runners": [
                    {"selectionId": SAMPLE_ARSENAL_SEL, "runnerName": "Arsenal", "sortPriority": 1},
                    {"selectionId": SAMPLE_CHELSEA_SEL, "runnerName": "Chelsea", "sortPriority": 2},
                    {"selectionId": SAMPLE_DRAW_SEL, "runnerName": "The Draw", "sortPriority": 3},
                ],
            }
        ),
        BFMarketCatalogue.model_validate(
            {
                "marketId": SAMPLE_EPL_BTTS_MKT,
                "marketName": "Both teams to Score",
                "description": {"marketType": MARKET_BTTS},
                "event": epl_event,
                "runners": [
                    {"selectionId": SAMPLE_BTTS_YES_SEL, "runnerName": "Yes", "sortPriority": 1},
                    {"selectionId": SAMPLE_BTTS_NO_SEL, "runnerName": "No", "sortPriority": 2},
                ],
            }
        ),
        BFMarketCatalogue.model_validate(
            {
                "marketId": SAMPLE_SL2_MATCH_ODDS_MKT,
                "marketName": "Match Odds",
                "description": {"marketType": MARKET_MATCH_ODDS},
                "event": sl2_event,
                "runners": [
                    {
                        "selectionId": SAMPLE_FORFAR_SEL,
                        "runnerName": "Forfar Athletic",
                        "sortPriority": 1,
                    },
                    {
                        "selectionId": SAMPLE_BRECHIN_SEL,
                        "runnerName": "Brechin City",
                        "sortPriority": 2,
                    },
                    {
                        "selectionId": SAMPLE_SL2_DRAW_SEL,
                        "runnerName": "The Draw",
                        "sortPriority": 3,
                    },
                ],
            }
        ),
        BFMarketCatalogue.model_validate(
            {
                "marketId": SAMPLE_SL2_BTTS_MKT,
                "marketName": "Both teams to Score",
                "description": {"marketType": MARKET_BTTS},
                "event": sl2_event,
                "runners": [
                    {"selectionId": SAMPLE_BTTS_YES_SEL, "runnerName": "Yes", "sortPriority": 1},
                    {"selectionId": SAMPLE_BTTS_NO_SEL, "runnerName": "No", "sortPriority": 2},
                ],
            }
        ),
    ]

    def _book(market_id: str, prices: Mapping[int, float | None]) -> BFMarketBook:
        runners: list[dict[str, Any]] = []
        for selection_id, price in prices.items():
            ex = {"availableToBack": [] if price is None else [{"price": price, "size": 120.0}]}
            runners.append({"selectionId": selection_id, "status": "ACTIVE", "ex": ex})
        return BFMarketBook.model_validate(
            {"marketId": market_id, "status": "OPEN", "runners": runners}
        )

    books = [
        _book(
            SAMPLE_EPL_MATCH_ODDS_MKT,
            {SAMPLE_ARSENAL_SEL: 1.9, SAMPLE_CHELSEA_SEL: 4.3, SAMPLE_DRAW_SEL: 3.75},
        ),
        _book(SAMPLE_EPL_BTTS_MKT, {SAMPLE_BTTS_YES_SEL: 1.8, SAMPLE_BTTS_NO_SEL: 2.05}),
        _book(
            SAMPLE_SL2_MATCH_ODDS_MKT,
            {SAMPLE_FORFAR_SEL: 2.4, SAMPLE_BRECHIN_SEL: 3.1, SAMPLE_SL2_DRAW_SEL: 3.2},
        ),
        # Thin lower-league BTTS: only "Yes" is priced; "No" has no back offers.
        _book(SAMPLE_SL2_BTTS_MKT, {SAMPLE_BTTS_YES_SEL: 1.95, SAMPLE_BTTS_NO_SEL: None}),
    ]

    return {
        "competitions": competitions,
        "events": events,
        "catalogues": catalogues,
        "books": books,
    }
