"""odds-api.io provider — the odds source for The Coupon, priced by one bookmaker.

Replaces the Betfair Exchange (ADR 0002). Two reasons, both blocking:

* The Exchange never priced the Scottish lower divisions the owner requires — those are
  a Betfair *Sportsbook* product, and ``SportsAPING`` serves the Exchange only.
* The Exchange refuses the production login with ``BETTING_RESTRICTED_LOCATION`` from
  every region the deployment platform offers.

odds-api.io aggregates 265+ bookmakers and carries all four Scottish divisions, the full
English pyramid, Wales, and Northern Ireland. Prices come from **one** bookmaker —
Bet365 by owner decision — because the game scores by odds, so mixing books would make a
member's score depend on who priced their fixture rather than on the risk they took.

Three differences from the Exchange shape the code here:

* **Prices are strings.** They become :class:`~decimal.Decimal`, never ``float``, because
  they are frozen onto ``picks.odds_at_pick`` and multiplied to award points.
* **There is no settlement feed.** ``/events/{id}`` reports ``status`` and ``scores``, so
  Match Odds is derived by comparing the two numbers and Both Teams To Score from both
  being non-zero (:func:`~src.services.odds_provider.outcomes_from_score`). Settlement
  reads the *events* endpoint, never the odds ones — those carry only what is still
  priced and drop the scores the moment a fixture finishes.
* **Requests are rate-limited** — 100/hour and 500/day on the free plan — so odds are
  fetched in batches and served through :class:`~src.services.odds_cache.CachingOddsProvider`
  rather than hitting the API once per pick-page load.

Leagues are *discovered*, never hardcoded. Matching a provider's own vocabulary by exact
string has caused three separate defects in this project (Betfair's certlogin field names,
its sponsored English competition names, and a division allow-list that starved the
slate), so the UK set is derived from each league's own country and name.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from src.config import settings
from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderAuthError,
    Outcome,
    OutcomeResult,
    Selection,
    Slate,
    SlateFixture,
    SlateWindow,
    as_utc,
    is_void_status,
    iso_z,
    outcomes_from_score,
    split_event_name,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://api.odds-api.io/v3"
SPORT_FOOTBALL = "football"

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0  # seconds
_TIMEOUT = 30.0

# ``/odds/multi`` takes a comma-separated id list and rejects more than ten ids with
# ``400 {"error":"Maximum 10 eventIds allowed"}`` — measured against the live API on
# 2026-08-04. Chunking at the cap is what makes a full slate a handful of requests
# instead of one per fixture, which matters against a 100/hour budget: the launch
# Saturday carries 131 qualifying fixtures.
_MULTI_ODDS_CHUNK = 10

# The four home nations as odds-api.io labels them. Verified against the live catalogue on
# 2026-08-04: 728 football leagues, none of which carry a ``country`` field, so the country
# is read off the *name*, which is always ``"<Country> - <Competition>"``.
UK_COUNTRIES: frozenset[str] = frozenset(
    {
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "united kingdom",
        "great britain",
        "gb",
        "uk",
    }
)

# Some countries split their lower tiers under a qualified heading — "England Amateur -
# National League North", and the same pattern for Austria, Denmark, Germany, Sweden and
# Turkiye. Stripping the qualifier is what keeps England's amateur tiers in the slate;
# without it the live catalogue silently loses eight competitions, including National
# League North and South, which are exactly the divisions that fill a Saturday card.
_COUNTRY_QUALIFIERS: tuple[str, ...] = ("amateur",)

# Matching is *exact* after that normalisation, never a prefix test: "Ukraine" begins with
# "uk" and would otherwise be read as a British competition.

# Market names, matched case-insensitively. The first spelling in each tuple is the one
# recorded from the live API on 2026-08-04; the rest are defensive aliases that cost
# nothing because matching is exact per entry.
_MATCH_ODDS_NAMES: frozenset[str] = frozenset(
    {"ml", "moneyline", "money line", "1x2", "match odds", "match winner", "full time result"}
)
_BTTS_NAMES: frozenset[str] = frozenset(
    {"both teams to score", "both teams to score?", "btts", "both teams score"}
)

# Event lifecycle. The live vocabulary, sampled across 227 football events on 2026-08-04,
# is exactly ``pending`` → ``live`` → ``settled``, plus ``cancelled``. The other spellings
# are defensive and cost nothing because matching is exact per entry. Unknown values are
# treated as *not settled*, so a vocabulary change leaves picks pending for the
# Sunday/Monday retries rather than silently voiding them.
#
# Settlement timing, measured in the same sample: fixtures reach ``settled`` from roughly
# **two hours** after kick-off (13 of 13 in the 2-4h bucket, 9 of 11 in 4-6h). A 15:00
# kick-off is therefore settled well before the scheduler's first 18:00 Saturday run, and
# the Sunday/Monday retries are slack rather than load-bearing.
_FINISHED_STATUSES: frozenset[str] = frozenset(
    {"settled", "finished", "ended", "complete", "completed", "ft", "full time", "closed"}
)
# The void vocabulary moved to ``odds_provider.VOID_STATUSES`` in Batch 49: discovery now
# reads the same words settlement does, so a fixture taken off an open round and a pick
# voided after it was due to be played cannot disagree about what a postponement is.
# ``live`` is deliberately in neither set — not finished here, not void there. An in-play
# fixture carries a *partial* score, so treating a score's presence as a result would
# settle a match at half time.


# ── Raw odds-api.io response models ────────────────────────────────────────────
# Only the fields we consume are modelled; unknown keys are ignored by pydantic.
# Field aliases accept every spelling the API and its official SDK are known to use,
# because this adapter was written against recorded shapes rather than a live session.


class OANamedSlug(BaseModel):
    """The ``{name, slug}`` pair the API nests for an event's sport and league."""

    name: str = ""
    slug: str = ""


class OALeague(BaseModel):
    """A competition.

    The live catalogue returns ``{name, slug, eventsCount}`` — there is no ``id`` and no
    ``country``. ``slug`` is what ``/events?league=`` expects, so it is accepted under the
    ``id`` alias and the country is derived from the name (see :func:`_country_of`).
    """

    id: str = Field("", validation_alias=AliasChoices("id", "slug", "leagueId", "key"))
    name: str = ""
    country: str = ""


class OAScore(BaseModel):
    """Full-time goals. The payload also carries a ``periods`` breakdown, which we ignore."""

    home: int = 0
    away: int = 0


class OAEvent(BaseModel):
    """One fixture. ``date`` is UTC with a ``Z`` suffix.

    ``id`` arrives as a JSON **number** (``72203846``) and ``league`` as a nested
    ``{name, slug}`` object, both verified live on 2026-08-04. ``coerce_numbers_to_str``
    is what lets the numeric id land in a ``str`` field; without it every event fails
    validation and the slate comes back empty.
    """

    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = Field("", validation_alias=AliasChoices("id", "eventId"))
    home: str = ""
    away: str = ""
    name: str = ""
    date: datetime | None = Field(
        None, validation_alias=AliasChoices("date", "startTime", "commence_time")
    )
    status: str = ""
    league: OANamedSlug | None = None
    scores: OAScore | None = Field(None, validation_alias=AliasChoices("scores", "score"))


class OAMarket(BaseModel):
    """One bookmaker's prices for one market.

    ``odds`` is a list because handicap and totals markets carry a line per entry; the
    two markets this game uses have a single entry, keyed by outcome name.
    """

    name: str = ""
    odds: list[dict[str, Any]] = []


class OAEventOdds(OAEvent):
    """An event *with* its per-bookmaker prices — what ``/odds`` returns.

    The same payload carries ``status`` and ``scores``, so one endpoint serves both the
    odds snapshot and settlement.
    """

    bookmakers: dict[str, list[OAMarket]] = {}


# ── Parsing helpers ────────────────────────────────────────────────────────────


def _decimal_price(value: object) -> Decimal | None:
    """Parse a price into ``Decimal``, or ``None`` when it isn't a usable price.

    Prices arrive as strings (``"4.75"``). ``Decimal(str(value))`` keeps the decimal value
    the bookmaker published; going via ``float`` would introduce binary rounding into the
    number a member is scored on. Anything not strictly greater than 1.0 is not a price a
    back bet can be struck at, so it is treated as unpriced.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() == "N/A":
            return None
    elif isinstance(value, int | float | Decimal):
        text = str(value)
    else:
        return None
    try:
        price = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if price <= 1:
        return None
    return price


def _market_of(name: str) -> Market | None:
    """Classify a provider market name; ``None`` for the markets this game ignores."""
    folded = name.strip().casefold()
    if folded in _MATCH_ODDS_NAMES:
        return Market.MATCH_ODDS
    if folded in _BTTS_NAMES:
        return Market.BOTH_TEAMS_TO_SCORE
    return None


def _country_of(league: OALeague) -> str:
    """The league's country, normalised for comparison.

    Prefers an explicit ``country`` field if the API ever grows one; today it always comes
    from the name's ``"<Country> - <Competition>"`` prefix, with any qualifier stripped so
    "England Amateur" reads as England.
    """
    if league.country.strip():
        head = league.country.strip().casefold()
    else:
        head = league.name.split(" - ", 1)[0].strip().casefold()
    for qualifier in _COUNTRY_QUALIFIERS:
        if head.endswith(f" {qualifier}"):
            head = head[: -(len(qualifier) + 1)].strip()
    return head


def _is_uk(league: OALeague) -> bool:
    """True when a league belongs to one of the four home nations."""
    return _country_of(league) in UK_COUNTRIES


def _teams(event: OAEvent) -> tuple[str, str] | None:
    """The ``(home, away)`` pair, from the explicit fields or a combined name."""
    home, away = event.home.strip(), event.away.strip()
    if home and away:
        return home, away
    if event.name:
        return split_event_name(event.name)
    return None


def _outcome_keys(market: Market) -> dict[str, Outcome]:
    if market is Market.MATCH_ODDS:
        return {"home": Outcome.HOME, "draw": Outcome.DRAW, "away": Outcome.AWAY}
    return {"yes": Outcome.YES, "no": Outcome.NO}


def _runner_name(market: Market, outcome: Outcome, home: str, away: str) -> str:
    """The label a member sees for a selection.

    Betfair supplied runner names; odds-api.io keys outcomes by position, so the display
    name is composed from the fixture's own team names to keep ``picks.runner_name``
    meaningful.
    """
    if market is Market.MATCH_ODDS:
        if outcome is Outcome.HOME:
            return home
        if outcome is Outcome.AWAY:
            return away
        return "The Draw"
    return "Yes" if outcome is Outcome.YES else "No"


def _chunked(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


# ── The provider ───────────────────────────────────────────────────────────────


class OddsApiProvider(OddsProvider):
    """Live odds-api.io client, pinned to a single bookmaker.

    A custom ``client`` can be injected to drive the HTTP layer with a mock transport in
    tests. Authentication is a query-string API key, so ``login`` / ``keep_alive`` have
    no session to manage and simply verify the key is present.
    """

    def __init__(
        self,
        api_key: str,
        *,
        bookmaker: str = "Bet365",
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise OddsProviderAuthError("odds-api.io key not configured (ODDS_API_KEY)")
        self._api_key = api_key
        self._bookmaker = bookmaker
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT)
        self._leagues: list[OALeague] | None = None

    @classmethod
    def from_settings(cls) -> OddsApiProvider:
        """Build a client from ``ODDS_API_KEY`` / ``ODDS_API_BOOKMAKER`` (env)."""
        return cls(
            settings.odds_api_key,
            bookmaker=settings.odds_api_bookmaker,
            base_url=settings.odds_api_base_url,
        )

    # -- lifecycle -------------------------------------------------------------

    async def login(self) -> str:
        """No session to establish — the key authenticates every request."""
        return ""

    async def keep_alive(self) -> None:
        """Nothing to refresh; a key-authenticated client cannot go stale."""

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> OddsApiProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # -- domain operations -----------------------------------------------------

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        """Every British kick-off inside ``window``, across every UK competition.

        The slate is defined by *country and kick-off time*, not by a list of divisions —
        a first-round cup Saturday is as playable as a league Saturday. UK leagues are
        discovered from the provider's own catalogue each run, so a renamed or newly
        carried division is picked up without a code change.

        The window is the league's, not a constant, since Batch 14. It is queried a
        whole day at a time and filtered precisely afterwards, because providers filter
        by range and the default window is a single instant.

        ``competition_ids`` narrows the catalogue *before* the ``/events`` fan-out,
        which is where the whole cost of this call sits: one request per league walked.
        The ``/leagues`` catalogue itself is memoised on the client, so narrowing does
        not save that one — it saves the ~30 that follow it.
        """
        from_utc, to_utc = window.query_bounds(starts_on)
        leagues = await self._uk_leagues()
        if competition_ids is not None:
            wanted = set(competition_ids)
            leagues = [lg for lg in leagues if lg.id in wanted]

        fixtures: list[SlateFixture] = []
        for league in leagues:
            events = await self._league_events(league.id, from_utc, to_utc)
            for event in events:
                if event.date is None or not window.contains(event.date, starts_on):
                    continue
                if not event.id:
                    continue
                teams = _teams(event)
                if teams is None:
                    log.warning("odds-api event name not parseable", event_id=event.id)
                    continue
                home, away = teams
                fixtures.append(
                    SlateFixture(
                        provider_event_id=event.id,
                        home=home,
                        away=away,
                        kickoff_utc=as_utc(event.date),
                        competition=league.name or league.id,
                        competition_id=league.id,
                        # ``/events`` reports a status on every entry — ``pending`` for
                        # the overwhelming majority, and the void words for the rest.
                        # Measured live on 2026-08-21: 2 of 1,599 fixtures on one date
                        # came back ``cancelled``. Dropping it here was what left a
                        # called-off match pickable until the evening settle sweep.
                        status=event.status,
                    )
                )

        fixtures.sort(key=lambda f: (f.competition, f.kickoff_utc, f.home))
        log.info(
            "odds-api slate fetched",
            starts_on=str(starts_on),
            uk_leagues=len(leagues),
            fixtures=len(fixtures),
        )
        return Slate(starts_on=starts_on, fixtures=fixtures)

    async def fetch_competitions(self) -> list[Competition]:
        """Every UK competition the provider carries, in name order.

        The same catalogue :meth:`fetch_slate` opens with, and the same ``_is_uk`` rule —
        roughly thirty of the live 728 — so the picker offers exactly the competitions a
        slate could ever draw from, including the ones this league has never played.

        This does not run into the slate's rate limit. The slate costs one ``/events`` per
        competition; this is :meth:`_all_leagues`, a single ``/leagues`` call memoised on
        the client, so opening the picker is free for the life of the process after the
        first fetch of either.
        """
        competitions = [
            Competition(competition_id=league.id, competition=league.name or league.id)
            for league in await self._uk_leagues()
        ]
        competitions.sort(key=lambda c: c.competition)
        return competitions

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        """Snapshot the Bet365-priced Match Odds + BTTS selections for the given events.

        Keeps the rule the Exchange adapter established — *only offer a selection the
        source actually prices* — so a thin lower-league BTTS market yields fewer
        selections rather than an error.
        """
        if not event_ids:
            return []
        odds: list[FixtureOdds] = []
        for payload in await self._event_odds(event_ids):
            teams = _teams(payload)
            if teams is None:
                log.warning("odds-api event name not parseable", event_id=payload.id)
                continue
            home, away = teams
            selections = self._selections_for(payload, home, away)
            odds.append(
                FixtureOdds(
                    provider_event_id=payload.id, home=home, away=away, selections=selections
                )
            )
        odds.sort(key=lambda o: o.provider_event_id)
        return odds

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        """Derive each event's result from its final score.

        The provider has no settlement feed, so a fixture is settled once its status is
        terminal *and* a score is present; both markets then resolve from that score. A
        cancelled or postponed fixture settles as ``void`` so its picks score nothing
        instead of losing. Anything else stays unsettled for the Sunday/Monday retries.

        Results come from ``/events/{id}``, **not** from the odds endpoints. Verified on
        2026-08-04: once a fixture settles, ``/odds`` returns it with ``status:
        "settled"`` but no ``scores`` key and no bookmakers, and ``/odds/multi`` drops it
        from the response entirely — both endpoints carry only what is still priced.
        Reading settlement from either one would leave every pick pending forever.
        """
        settlements: list[EventSettlement] = []
        for event_id in dict.fromkeys(event_ids):
            event = await self._event_by_id(event_id)
            if event is None:
                log.warning("odds-api event not found for settlement", event_id=event_id)
                settlements.append(
                    EventSettlement(provider_event_id=event_id, status="", settled=False)
                )
                continue
            settlements.append(_settlement_for(event))
        return settlements

    # -- mapping ---------------------------------------------------------------

    def _selections_for(self, payload: OAEventOdds, home: str, away: str) -> list[Selection]:
        """Priced selections for one event, from the pinned bookmaker only."""
        markets = _bookmaker_markets(payload.bookmakers, self._bookmaker)
        if not markets:
            return []

        selections: list[Selection] = []
        for raw in markets:
            market = _market_of(raw.name)
            if market is None:
                continue
            keys = _outcome_keys(market)
            for line in raw.odds:
                found = False
                for key, outcome in keys.items():
                    price = _decimal_price(line.get(key))
                    if price is None:  # unpriced → not offered
                        continue
                    found = True
                    selections.append(
                        Selection(
                            market=market,
                            outcome=outcome,
                            runner_name=_runner_name(market, outcome, home, away),
                            price=price,
                        )
                    )
                if found:
                    # The first entry carrying this market's outcome keys is the main
                    # line; later entries are handicap variants this game does not use.
                    break

        selections.sort(key=lambda s: (s.market.value, s.outcome.value))
        return selections

    # -- transport -------------------------------------------------------------

    async def _all_leagues(self) -> list[OALeague]:
        """The football league catalogue, fetched once per client.

        The catalogue changes between seasons, not between slate refreshes, so caching it
        on the shared client removes one request from every refresh.
        """
        if self._leagues is None:
            result = await self._get("/leagues", {"sport": SPORT_FOOTBALL})
            self._leagues = [OALeague.model_validate(item) for item in _as_items(result)]
        return self._leagues

    async def _uk_leagues(self) -> list[OALeague]:
        """The catalogue narrowed to the four home nations, entries without an id dropped.

        Shared by the slate and the competition catalogue so the picker can never offer a
        competition the slate would not consider, or hide one it would.
        """
        return [lg for lg in await self._all_leagues() if _is_uk(lg) and lg.id]

    async def _event_by_id(self, event_id: str) -> OAEvent | None:
        """One event with its ``status`` and ``scores`` — the settlement source.

        There is no batch form: ``/events`` ignores an ``eventIds`` filter and returns the
        whole book, so this is one request per fixture still awaiting a result. The settle
        job only asks about fixtures with *pending* picks, that set shrinks on each retry,
        and since Batch 31 it is de-duplicated across every round in a run, so a fixture
        two leagues both hold is bought once rather than once per league.

        Open question: ``/events`` for a whole window might carry ``scores`` for finished
        fixtures, which would make a Saturday one request instead of one per fixture — the
        way :meth:`_event_odds` already batches pricing. Unverified, because confirming it
        needs a live call and there is no key in the working tree.
        """
        result = await self._get(f"/events/{event_id}", {}, missing_ok=True)
        items = _as_items(result)
        if not items:
            return None
        event = OAEvent.model_validate(items[0])
        return event if event.id else None

    async def _league_events(
        self, league_id: str, from_utc: datetime, to_utc: datetime
    ) -> list[OAEvent]:
        result = await self._get(
            "/events",
            {
                "sport": SPORT_FOOTBALL,
                "league": league_id,
                "from": iso_z(from_utc),
                "to": iso_z(to_utc),
            },
        )
        return [OAEvent.model_validate(item) for item in _as_items(result)]

    async def _event_odds(self, event_ids: Sequence[str]) -> list[OAEventOdds]:
        """Odds (and status/scores) for the given events, batched.

        A single event uses ``/odds``; several use ``/odds/multi`` in chunks, so a
        forty-fixture slate costs two requests rather than forty.
        """
        ids = list(dict.fromkeys(event_ids))  # de-duplicate, preserve order
        payloads: list[OAEventOdds] = []
        if len(ids) == 1:
            result = await self._get("/odds", {"eventId": ids[0], "bookmakers": self._bookmaker})
            payloads = [OAEventOdds.model_validate(item) for item in _as_items(result)]
        else:
            for chunk in _chunked(ids, _MULTI_ODDS_CHUNK):
                result = await self._get(
                    "/odds/multi",
                    {"eventIds": ",".join(chunk), "bookmakers": self._bookmaker},
                )
                payloads.extend(OAEventOdds.model_validate(item) for item in _as_items(result))
        return [p for p in payloads if p.id]

    async def _get(
        self, path: str, params: Mapping[str, str], *, missing_ok: bool = False
    ) -> object:
        """GET a v3 endpoint with retries, returning the decoded JSON body.

        Retries the cases where trying again is the right answer — network errors and
        5xx — with exponential backoff. A ``401``/``403`` is an unusable key and raises
        immediately rather than burning retries against a rate-limited plan; a ``429``
        does the same, for the reason spelled out where it is raised.

        ``missing_ok`` turns a ``404`` into ``None`` for lookups where absence is a real
        answer: an event the provider no longer lists simply has no result yet, which
        must leave its picks pending rather than fail the whole settle run.
        """
        query = {**params, "apiKey": self._api_key}
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.get(path, params=query)
            except httpx.RequestError as exc:
                if attempt == _MAX_RETRIES:
                    raise OddsProviderAPIError(
                        f"odds-api.io network error after {_MAX_RETRIES} retries: {exc!r}"
                    ) from exc
                log.warning("odds-api network error", path=path, attempt=attempt, error=repr(exc))
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code in (401, 403):
                raise OddsProviderAuthError(
                    f"odds-api.io rejected the API key ({response.status_code})"
                )
            if response.status_code == 404 and missing_ok:
                return None
            if response.status_code == 429:
                # Never retried. ``429`` says the quota is already spent, and another
                # request is the one response guaranteed to keep it spent: retrying three
                # times with doubling backoff turned a single rate-limited slate load into
                # four upstream calls, which is how 2026-08-21's breach sustained itself
                # and slowed its own recovery. Fail fast and let the cache cover the gap
                # (``CachingOddsProvider.fetch_odds_best_effort``).
                log.warning("odds-api rate limited", path=path)
                raise OddsProviderAPIError(f"odds-api.io {path} rate-limited (429), not retried")
            if response.status_code >= 500:
                if attempt == _MAX_RETRIES:
                    raise OddsProviderAPIError(
                        f"odds-api.io {path} failed with status {response.status_code} "
                        f"after {_MAX_RETRIES} retries"
                    )
                log.warning(
                    "odds-api transient error",
                    path=path,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code >= 400:
                # Deliberately *not* `raise_for_status()`: its exception carries the full
                # request URL, and the API key travels in the query string, so a 4xx would
                # print the key into any traceback the platform logs. Only the path,
                # status, and body go into the message.
                raise OddsProviderAPIError(
                    f"odds-api.io {path} unexpected status {response.status_code}: "
                    f"{response.text[:200]}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise OddsProviderAPIError(
                    f"odds-api.io {path} returned a non-JSON body: {response.text[:200]}"
                ) from exc

        raise OddsProviderAPIError(  # pragma: no cover — loop always returns or raises
            f"odds-api.io {path} exhausted retries"
        )


# ── Response-shape helpers ─────────────────────────────────────────────────────


def _as_items(payload: object) -> list[dict[str, Any]]:
    """Normalise a v3 body to a list of objects.

    Endpoints return a bare array, a single object (``/odds`` for one event), or an array
    wrapped under ``data``/``events``/``results``. Accepting all three keeps a wrapper
    change from taking the slate down.
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "events", "results", "leagues", "odds"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [payload]
    return []


def _is_bookmaker_variant(name: str, folded_wanted: str) -> bool:
    """Whether ``name`` is the pinned bookmaker published under a decorated key.

    The key must *continue* with a separator rather than with more name, so ``Bet365 (no
    latency)`` qualifies and a hypothetical ``Bet365Extra`` does not. That is what stops
    the loosening in :func:`_bookmaker_markets` from silently adopting a different brand
    whose name happens to begin with the pinned one.
    """
    candidate = name.strip().casefold()
    if not candidate.startswith(folded_wanted):
        return False
    rest = candidate[len(folded_wanted) :]
    return bool(rest) and not rest[0].isalnum()


def _bookmaker_markets(bookmakers: Mapping[str, list[OAMarket]], wanted: str) -> list[OAMarket]:
    """The pinned bookmaker's markets, including the feed variants it is published under.

    Three passes, loosening in order, because the provider spells one bookmaker more than
    one way. Exact first, then case-folded — bookmaker keys are case-sensitive in the API,
    the same class of exact-string hazard that hid three Betfair divisions.

    The third pass is the one that matters in production. odds-api.io publishes Bet365
    under **two** keys, and which one an event carries is not predictable: ``Bet365``
    holds the full book (~65 markets), while ``Bet365 (no latency)`` is a thinner, faster
    feed carrying only ``ML``. Measured live on 2026-08-22: three of the five Scottish
    Premiership fixtures on that day's card came back under ``(no latency)`` alone.
    Matching on equality dropped them, so a *priced* top-flight fixture rendered "Not
    priced yet" on the pick screen all day and could not be picked at all.

    When several variants match, the richest book wins. ``(no latency)`` prices only Match
    Odds, so preferring it over the full feed would silently cost the card its BTTS
    selections on every fixture that carries both.
    """
    if wanted in bookmakers:
        return bookmakers[wanted]
    folded = wanted.strip().casefold()
    for name, markets in bookmakers.items():
        if name.strip().casefold() == folded:
            return markets
    variants = [
        (name, markets)
        for name, markets in bookmakers.items()
        if _is_bookmaker_variant(name, folded)
    ]
    if not variants:
        return []
    # Richest book first, then by name so the choice is stable across identical payloads.
    variants.sort(key=lambda item: (-len(item[1]), item[0]))
    return variants[0][1]


def _settlement_for(payload: OAEvent) -> EventSettlement:
    """Turn one event payload into a settlement verdict.

    The status gate is doing real work here: a *pending* fixture is returned with
    ``scores: {home: 0, away: 0}`` and a *live* one with the score so far, so treating a
    score's presence as a result would settle every unplayed fixture as a goalless draw
    and every in-play one at whatever the score happened to be.
    """
    status = payload.status.strip()
    folded = status.casefold()

    if is_void_status(status):
        return EventSettlement(provider_event_id=payload.id, status=status, settled=True, void=True)

    if folded in _FINISHED_STATUSES and payload.scores is not None:
        return EventSettlement(
            provider_event_id=payload.id,
            status=status,
            settled=True,
            settled_markets=[Market.MATCH_ODDS, Market.BOTH_TEAMS_TO_SCORE],
            outcomes=outcomes_from_score(payload.scores.home, payload.scores.away),
        )

    if folded and folded not in _FINISHED_STATUSES:
        log.debug("odds-api event not final", event_id=payload.id, status=status)
    elif folded in _FINISHED_STATUSES:
        # Finished but no score yet — the scheduler's Sunday/Monday retries will catch it.
        log.warning("odds-api event finished without a score", event_id=payload.id)

    return EventSettlement(provider_event_id=payload.id, status=status, settled=False)


def outcome_results(outcomes: Iterable[OutcomeResult]) -> dict[tuple[Market, Outcome], bool]:
    """Index settled outcomes by ``(market, outcome)`` — used by scoring."""
    return {(o.market, o.outcome): o.won for o in outcomes}
