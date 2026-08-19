"""API-Football (api-sports.io) — the football-data source: tables, results, and form.

The second provider Batch 16 needs. odds-api.io prices fixtures and publishes nothing
else, so every table, previous result and run of form comes from here.

Chosen because coverage is the binding constraint, exactly as it was for the odds source.
The game's slate is the whole British card — all four Scottish divisions, England's
pyramid down through the National Leagues, Wales and Northern Ireland — and the obvious
alternative (football-data.org) carries twelve competitions on its free tier, none of them
the lower British divisions. Picking it would have reproduced the Betfair failure: a
provider that serves the top of the game and starves the rest of the slate. See
``docs/adr/0003-api-football-as-the-football-data-provider.md``.

Three things shape the code here:

* **The free plan allows 100 requests a *day* and 10 requests a minute.** That is a
  fifth of the odds source's daily allowance, so nothing here may run in the request
  path. Ingestion writes ``teams`` / ``matches`` / ``standings`` on a schedule and every
  screen reads those. :mod:`src.services.football_data` owns the budget arithmetic.
* **Competitions are matched, not configured.** This provider has never heard of
  odds-api.io's slugs, so a :class:`~src.services.football_provider.CompetitionKey` is
  resolved against its own catalogue by country and name, reusing the same normalisation
  the team layer uses. A competition it does not carry resolves to ``None`` and is simply
  skipped — an unmatched division must not take the ingestion run down.
* **Errors arrive with HTTP 200.** The API reports quota, key and parameter problems in
  an ``errors`` field on an otherwise successful response, so the status code alone is
  not a health check.

Written against the documented v3 response shapes. **It has not been run against the live
API from this machine** — outbound requests to sports APIs are blocked here, and the live
probe is the owner's to run (as it was for odds-api.io, where three live-only shape
surprises were found). Every field is therefore read defensively: unknown keys are
ignored, absent ones fall back, and a payload that cannot be understood is logged and
dropped rather than raised.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.config import settings
from src.services.football_provider import (
    CompetitionKey,
    FootballDataAPIError,
    FootballDataAuthError,
    FootballDataProvider,
    LeagueTable,
    MatchResult,
    TableRow,
    TeamRef,
)
from src.services.team_matching import (
    MATCH_MARGIN,
    MATCH_THRESHOLD,
    normalise_name,
    similarity,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://v3.football.api-sports.io"

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0  # seconds
_TIMEOUT = 30.0
#: ``/fixtures`` pages at 100 entries. A British division is 380-1200 matches a season, so
#: the backfill needs several; the cap stops a paging bug from spending a day's quota.
_MAX_PAGES = 12

# Country-name qualifiers odds-api.io appends to lower tiers ("England Amateur - National
# League North"). Stripped so the country matches this provider's plain "England". Mirrors
# `_COUNTRY_QUALIFIERS` in the odds adapter — the same catalogue quirk, seen from the
# other side.
_COUNTRY_QUALIFIERS: tuple[str, ...] = ("amateur",)

# odds-api.io competition slug -> this provider's league id, for the divisions the two
# catalogues simply do not name alike. Both sides were read from the live catalogues on
# 2026-08-19, not inferred from a spelling rule.
#
# These are not a workaround for a badly-tuned threshold. "Southern League, Premier
# Division South" and "Non League Premier - Southern South" share four tokens of five and
# still only reach 0.800, below `MATCH_THRESHOLD` — while the *wrong* answer, England's
# actual Premier League, used to clear it on a subset bonus. No threshold resolves two
# providers' naming conventions by ratio alone; naming them is the honest fix.
#
# Only the divisions name-matching cannot resolve are listed. `england-national-league`
# and the two National League regional slugs normalise to an exact match and need no
# entry — adding them would imply they were broken.
_COMPETITION_OVERRIDES: dict[str, str] = {
    # England Amateur - Isthmian League, Premier Division -> Non League Premier - Isthmian
    "england-amateur-isthmian-league-premier-division": "58",
    # England Amateur - Northern Premier League, Premier Division
    #   -> Non League Premier - Northern
    "england-amateur-northern-premier-league-premier-division": "59",
    # England Amateur - Southern League, Premier Division Central
    #   -> Non League Premier - Southern Central
    "england-amateur-southern-league-premier-division-central": "931",
    # England Amateur - Southern League, Premier Division South
    #   -> Non League Premier - Southern South
    "england-amateur-southern-league-premier-division-south": "60",
}

# Fixture status codes, from the documented v3 vocabulary. Finished covers the three ways
# a result becomes final; void covers the ways a match produces none. Anything else —
# `NS`, `1H`, `HT`, `2H`, `ET`, `LIVE` — is not a result yet, and an unknown code is
# treated the same way, so a vocabulary change leaves a match pending rather than
# recording a half-time score as final.
_FINISHED_STATUSES: frozenset[str] = frozenset({"ft", "aet", "pen"})
_VOID_STATUSES: frozenset[str] = frozenset({"pst", "canc", "abd", "susp", "int", "awd", "wo"})
_TRANSIENT_BODY_ERROR_KEYS: frozenset[str] = frozenset({"ratelimit"})


class _TransientAPIError(FootballDataAPIError):
    """A 200-body error that should use the same retry path as 429/5xx."""


# ── Raw API-Football response models ───────────────────────────────────────────
# Only the consumed fields are modelled; unknown keys are ignored by pydantic.


class AFModel(BaseModel):
    """Base for every raw payload model: a key present as ``null`` reads as absent.

    Every field below carries a default, which covers a key this provider omits. A key
    present as ``null`` is a *different* shape, and pydantic rejects it against a
    non-optional annotation however good the default is. That distinction is what kept the
    football screens empty in production: ``/leagues`` returns ``"code": null`` for the
    countryless competitions, one entry failed validation, and the whole catalogue went
    with it.

    Dropping nulls before validation collapses the two shapes into one, so "absent ones
    fall back" holds for both. It changes nothing for the genuinely optional fields —
    ``goals.home`` on a match not yet played already defaults to ``None``, whether the key
    is missing or null.
    """

    @model_validator(mode="before")
    @classmethod
    def _null_reads_as_absent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class AFTeam(AFModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = ""
    name: str = ""


class AFGoals(AFModel):
    home: int | None = None
    away: int | None = None


class AFCountry(AFModel):
    name: str = ""
    code: str = ""


class AFLeague(AFModel):
    """A competition in the catalogue, or the league block on a fixture."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = ""
    name: str = ""
    #: On ``/fixtures`` this is a bare string; on ``/leagues`` the country is a sibling
    #: object, so both spellings are accepted.
    country: str = ""


class AFCatalogueEntry(AFModel):
    """One ``/leagues`` entry: the league, its country, and the seasons carried."""

    league: AFLeague = AFLeague()
    country: AFCountry = AFCountry()


class AFStatus(AFModel):
    short: str = ""
    long: str = ""


class AFFixtureBlock(AFModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = ""
    date: datetime | None = None
    status: AFStatus = AFStatus()


class AFFixture(AFModel):
    """One ``/fixtures`` entry."""

    fixture: AFFixtureBlock = AFFixtureBlock()
    league: AFLeague = AFLeague()
    teams: dict[str, AFTeam] = {}
    goals: AFGoals = AFGoals()


class AFAll(AFModel):
    """The played/won/drawn/lost block of a standings row."""

    played: int = 0
    win: int = 0
    draw: int = 0
    lose: int = 0
    goals: dict[str, int] = {}


class AFStandingRow(AFModel):
    rank: int = 0
    team: AFTeam = AFTeam()
    points: int = 0
    form: str = ""
    all: AFAll = Field(default_factory=AFAll)


class AFStandingsLeague(AFModel):
    """The league block of a ``/standings`` response.

    ``standings`` is a list *of lists*: one inner list per group. Most British divisions
    have exactly one; a league with groups (the National League's regional feeders are
    modelled as separate competitions, but cup group stages are not) yields several, and
    they are concatenated in order so positions stay as published within each group.
    """

    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = ""
    name: str = ""
    country: str = ""
    season: int = 0
    standings: list[list[AFStandingRow]] = []


class AFStandingsEntry(AFModel):
    league: AFStandingsLeague = Field(default_factory=AFStandingsLeague)


# ── Parsing helpers ────────────────────────────────────────────────────────────


def _country_key(name: str) -> str:
    """Normalise a country for comparison, dropping odds-api.io's tier qualifiers."""
    head = normalise_name(name)
    for qualifier in _COUNTRY_QUALIFIERS:
        if head.endswith(f" {qualifier}"):
            head = head[: -(len(qualifier) + 1)].strip()
    return head


def _team_ref(team: AFTeam) -> TeamRef | None:
    """A usable :class:`TeamRef`, or ``None`` when the payload names no club."""
    if not team.id or not team.name.strip():
        return None
    return TeamRef(provider_team_id=team.id, name=team.name.strip())


def _finished(status: str) -> bool:
    return status.strip().casefold() in _FINISHED_STATUSES


def _void(status: str) -> bool:
    return status.strip().casefold() in _VOID_STATUSES


# ── The provider ───────────────────────────────────────────────────────────────


class ApiFootballProvider(FootballDataProvider):
    """Live API-Football client.

    A custom ``client`` can be injected to drive the HTTP layer with a mock transport in
    tests. Authentication is a header key, so there is no session to establish; the only
    lifecycle is :meth:`close`.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise FootballDataAuthError("API-Football key not configured (FOOTBALL_API_KEY)")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=_TIMEOUT,
            headers={"x-apisports-key": api_key},
        )
        self._catalogue: list[AFCatalogueEntry] | None = None
        #: Resolved ``CompetitionKey.slug`` → this provider's league id (``None`` = not
        #: carried). Memoised for the client's life so a run costs one catalogue request
        #: however many competitions it syncs.
        self._league_ids: dict[str, str | None] = {}

    @classmethod
    def from_settings(cls) -> ApiFootballProvider:
        """Build a client from ``FOOTBALL_API_KEY`` / ``FOOTBALL_API_BASE_URL`` (env)."""
        return cls(settings.football_api_key, base_url=settings.football_api_base_url)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ApiFootballProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # -- domain operations -----------------------------------------------------

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        """The competition's table, or ``None`` when this provider does not carry it."""
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return None
        payload = await self._get("/standings", {"league": league_id, "season": str(season)})
        rows: list[TableRow] = []
        for item in _responses(payload):
            entry = AFStandingsEntry.model_validate(item)
            for group in entry.league.standings:
                for raw in group:
                    team = _team_ref(raw.team)
                    if team is None or raw.rank <= 0:
                        continue
                    rows.append(
                        TableRow(
                            position=raw.rank,
                            team=team,
                            played=raw.all.played,
                            won=raw.all.win,
                            drawn=raw.all.draw,
                            lost=raw.all.lose,
                            goals_for=raw.all.goals.get("for", 0),
                            goals_against=raw.all.goals.get("against", 0),
                            points=raw.points,
                            form=raw.form.strip()[:10],
                        )
                    )
        if not rows:
            log.info(
                "api-football table empty",
                competition=competition.slug,
                season=season,
                league_id=league_id,
            )
            return None
        return LeagueTable(competition=competition, season=season, rows=rows)

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        """Matches in the season, optionally bounded — the season backfill unbounded.

        ``from``/``to`` are only sent when given: API-Football rejects one without the
        other, and an unbounded season query is exactly what the backfill wants.
        """
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return []
        params: dict[str, str] = {"league": league_id, "season": str(season)}
        if since is not None and until is not None:
            params["from"] = since.isoformat()
            params["to"] = until.isoformat()

        results: list[MatchResult] = []
        page = 1
        while page <= _MAX_PAGES:
            payload = await self._get("/fixtures", {**params, "page": str(page)})
            for item in _responses(payload):
                match = self._match_result(AFFixture.model_validate(item), competition, season)
                if match is not None:
                    results.append(match)
            total = _total_pages(payload)
            if page >= total:
                break
            page += 1
        results.sort(key=lambda m: (m.kickoff_utc, m.provider_match_id))
        return results

    def _match_result(
        self, fixture: AFFixture, competition: CompetitionKey, season: int
    ) -> MatchResult | None:
        """One fixture payload as a :class:`MatchResult`, or ``None`` when unusable."""
        if not fixture.fixture.id or fixture.fixture.date is None:
            return None
        home = _team_ref(fixture.teams.get("home", AFTeam()))
        away = _team_ref(fixture.teams.get("away", AFTeam()))
        if home is None or away is None:
            log.warning("api-football fixture without both teams", match_id=fixture.fixture.id)
            return None
        status = fixture.fixture.status.short.strip()
        finished = _finished(status) and fixture.goals.home is not None
        if _void(status):
            # A postponed or abandoned match is a real event with no result. Recorded so a
            # blank in a club's run of results is explicable rather than missing.
            finished = False
        return MatchResult(
            provider_match_id=fixture.fixture.id,
            competition=competition,
            season=season,
            kickoff_utc=fixture.fixture.date,
            home=home,
            away=away,
            home_goals=fixture.goals.home if finished else None,
            away_goals=fixture.goals.away if finished else None,
            finished=finished,
            status=status[:24],
        )

    # -- competition matching --------------------------------------------------

    async def league_id_for(self, competition: CompetitionKey) -> str | None:
        """This provider's league id for one of our competitions, or ``None``.

        Matched on country first, then name similarity within that country, using the
        same normalisation and threshold the team layer uses. Scoping by country is what
        makes the name comparison safe: "Premier League" and "Premiership" exist in
        several nations, and comparing across all of them would resolve arbitrarily.

        Memoised per client, misses included — a competition this provider does not carry
        must not be looked up again on every run.
        """
        if competition.slug in self._league_ids:
            return self._league_ids[competition.slug]

        override = _COMPETITION_OVERRIDES.get(competition.slug)
        if override is not None:
            log.info(
                "api-football competition resolved by override",
                competition=competition.slug,
                league_id=override,
            )
            self._league_ids[competition.slug] = override
            return override

        country = _country_key(competition.country)
        wanted = normalise_name(competition.competition_name)
        scored: list[tuple[float, str]] = []
        for entry in await self._all_leagues():
            entry_country = _country_key(entry.country.name or entry.league.country)
            if country and entry_country != country:
                continue
            if not entry.league.id:
                continue
            # `allow_subset=False`: see `similarity`. A generic short competition name is a
            # subset of every longer one that contains its words, and the bonus made
            # "Premier League" beat the actual division.
            score = similarity(wanted, normalise_name(entry.league.name), allow_subset=False)
            scored.append((score, entry.league.id))

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        best_score = scored[0][0] if scored else 0.0
        runner_up = scored[1][0] if len(scored) > 1 else 0.0

        resolved: str | None = None
        if scored and best_score >= MATCH_THRESHOLD and best_score - runner_up >= MATCH_MARGIN:
            resolved = scored[0][1]
        if resolved is None:
            # A miss stays a miss. An unmatched competition costs one empty screen; a
            # wrongly matched one writes another division's tables and clubs against it,
            # and `upsert_teams` then moves those clubs' competition_id, which spreads.
            log.info(
                "api-football competition unmatched",
                competition=competition.slug,
                country=country,
                best_score=round(best_score, 3),
                runner_up=round(runner_up, 3),
            )
        self._league_ids[competition.slug] = resolved
        return resolved

    async def _all_leagues(self) -> list[AFCatalogueEntry]:
        """The whole league catalogue, fetched once per client.

        One unfiltered request returns every competition the plan carries. Filtering by
        country instead would cost one request per country, and the catalogue changes
        between seasons rather than between runs — against a 100/day allowance, fetching
        it once is the difference between affordable and not.

        An entry that cannot be read is dropped rather than raised, and the entries that
        survive are memoised anyway. Both halves are load-bearing, and for a reason
        production demonstrated: this is the one parse every competition shares, so a
        single unreadable row fails the entire sweep rather than one division, and raising
        before the assignment leaves the memo empty — which turned one row into a fresh
        ``/leagues`` request per competition, twenty-one in a morning, and no data written.
        Per-competition parses need no such tolerance; ``sync_football_data`` already
        isolates a failure to its own competition.
        """
        if self._catalogue is None:
            payload = await self._get("/leagues", {})
            entries: list[AFCatalogueEntry] = []
            dropped = 0
            for item in _responses(payload):
                try:
                    entries.append(AFCatalogueEntry.model_validate(item))
                except ValidationError as exc:
                    dropped += 1
                    log.warning("api-football catalogue entry unreadable", error=str(exc)[:200])
            self._catalogue = entries
            log.info("api-football catalogue loaded", leagues=len(entries), dropped=dropped)
        return self._catalogue

    # -- transport -------------------------------------------------------------

    async def _get(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        """GET a v3 endpoint with retries, returning the decoded body.

        Retries the transient cases — network errors, ``429``/``rateLimit`` from the
        minute quota, and 5xx — with exponential backoff. A ``401``/``403`` is an
        unusable key and raises immediately rather than burning retries against a 100/day
        plan.

        The body is then checked for the ``errors`` field, because this API reports quota
        and parameter failures **with HTTP 200**. Treating a 200 as success would turn
        "you are out of requests for today" into "this competition has no table", and
        every screen would quietly empty out instead of alerting.
        """
        backoff = _INITIAL_BACKOFF
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.get(path, params=dict(params))
            except httpx.RequestError as exc:
                if attempt == _MAX_RETRIES:
                    raise FootballDataAPIError(
                        f"api-football network error after {_MAX_RETRIES} retries: {exc!r}"
                    ) from exc
                log.warning(
                    "api-football network error", path=path, attempt=attempt, error=repr(exc)
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code in (401, 403):
                raise FootballDataAuthError(
                    f"api-football rejected the API key ({response.status_code})"
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == _MAX_RETRIES:
                    raise FootballDataAPIError(
                        f"api-football {path} failed with status {response.status_code} "
                        f"after {_MAX_RETRIES} retries"
                    )
                log.warning(
                    "api-football transient error",
                    path=path,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            if response.status_code >= 400:
                raise FootballDataAPIError(
                    f"api-football {path} unexpected status {response.status_code}: "
                    f"{response.text[:200]}"
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise FootballDataAPIError(
                    f"api-football {path} returned a non-JSON body: {response.text[:200]}"
                ) from exc
            if not isinstance(body, dict):
                raise FootballDataAPIError(f"api-football {path} returned {type(body).__name__}")
            try:
                _raise_for_errors(path, body)
            except _TransientAPIError as exc:
                if attempt == _MAX_RETRIES:
                    raise FootballDataAPIError(
                        f"api-football {path} returned transient errors "
                        f"after {_MAX_RETRIES} retries: {exc}"
                    ) from exc
                log.warning(
                    "api-football transient body error",
                    path=path,
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            return body

        raise FootballDataAPIError(  # pragma: no cover — loop always returns or raises
            f"api-football {path} exhausted retries"
        )


# ── Response-shape helpers ─────────────────────────────────────────────────────


def _raise_for_errors(path: str, body: Mapping[str, Any]) -> None:
    """Raise when a 200 response carries an ``errors`` payload.

    ``errors`` is ``[]`` on success but an **object** on failure — ``{"token": "..."}``
    for a bad key, ``{"requests": "..."}`` when the daily allowance is gone,
    ``{"rateLimit": "..."}`` when the minute allowance is gone — so an empty list and
    an empty dict both mean "fine". A key or plan complaint is an auth error so it is not
    retried; minute-rate complaints are transient; anything else is an API error.
    """
    errors = body.get("errors")
    if not errors:
        return
    if isinstance(errors, dict):
        detail = "; ".join(f"{key}: {value}" for key, value in errors.items())
        keys = {str(key).casefold() for key in errors}
    else:
        detail = "; ".join(str(item) for item in errors)
        keys = set()
    if keys & {"token", "plan", "subscription", "access"}:
        raise FootballDataAuthError(f"api-football {path} rejected the key/plan: {detail[:200]}")
    if keys & _TRANSIENT_BODY_ERROR_KEYS:
        raise _TransientAPIError(f"api-football {path} returned errors: {detail[:200]}")
    raise FootballDataAPIError(f"api-football {path} returned errors: {detail[:200]}")


def _responses(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ``response`` array, tolerating a single object or a missing key."""
    payload = body.get("response")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _total_pages(body: Mapping[str, Any]) -> int:
    """``paging.total``, defaulting to a single page when absent or malformed."""
    paging = body.get("paging")
    if isinstance(paging, dict):
        total = paging.get("total")
        if isinstance(total, int) and total > 0:
            return total
    return 1
