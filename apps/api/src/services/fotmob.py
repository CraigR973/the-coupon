"""FotMob as the football-data source — the third implementation of the port.

ADR 0007. api-football's Free plan carries no part of the current season, which is
why `teams`, `team_aliases`, `matches` and `standings` have never held a row in any
environment. FotMob does carry it, including the six English step 6-7 divisions that
are 49% of this product's card and that every free alternative stops short of.

Nothing about ADR 0003's architecture changes: the port, the
ingestion-never-in-the-request-path rule, standings stored as published, and the alias
layer all stand. Only the source behind them moves.

Two shapes make this adapter different from :mod:`src.services.api_football`.

**One request carries both halves.** ``/api/data/leagues?id=<id>`` returns the table
*and* every match for the season. api-football needs two calls per competition; this
needs one per *league id*, and one league id can serve four of our competitions. The
payload is therefore memoised for the life of the client — get that wrong and a
thirty-competition sweep quadruples its own request count against a source that
publishes no quota and would notice.

**One league id carries several competitions, and only the table says which.** For a
combined id the payload sets ``composite: true`` and splits the table into
``data.tables``, one group per real division. ``fixtures.allMatches`` does **not**:
it is a flat list with no division marker on a match at all. The split is recovered
from the table groups, which carry integer team ids, so a match is attributed by its
home team's id — identity, never name similarity. Measured against the live payload
for ``8944`` on 2026-08-20: 1104/1104 matches attributed, 67/67 finished matches
attributed, and 67/67 finished matches had both teams inside the same division.

That last property is why this is safe. ``team_matching``'s fuzzy stage is scoped to a
single division precisely so it cannot put a Southern Central club in the Isthmian
table; attributing by id means it is never asked to.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx
import structlog

from src.services.football_provider import (
    CompetitionKey,
    FixtureState,
    FootballDataAPIError,
    FootballDataProvider,
    LeagueTable,
    MatchResult,
    MatchState,
    TableRow,
    TeamRef,
)
from src.services.fotmob_health import fotmob_health

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

BASE_URL = "https://www.fotmob.com"

#: The path that works. ``/api/leagues?id=<id>`` — the one every public wrapper uses —
#: answered 404 on 2026-08-20 while this one answered 200. There is no version, no
#: deprecation notice and no changelog, so a 404 here is treated as an error rather
#: than as "this competition has no table"; see :meth:`FotMobProvider._league`.
LEAGUE_PATH = "/api/data/leagues"

#: odds-api.io names a country ``England`` or ``England Amateur``; FotMob uses a
#: three-letter code. Without this, country-blind name matching puts Scotland's
#: League One into England's (id 108) — verified against the live catalogue, and the
#: exact defect class Batch 37 fixed for the other provider.
_COUNTRY_CODES: dict[str, str] = {
    "england": "ENG",
    "scotland": "SCO",
    "northern ireland": "NIR",
    "wales": "WAL",
}

#: Competitions FotMob does not name the way the odds provider does, plus every
#: combined id. The second element is the **group** ``leagueId`` inside a composite
#: payload, or ``None`` when the id is a single division.
#:
#: Read from the live catalogue on 2026-08-20, not inferred from a spelling rule.
_COMPETITION_OVERRIDES: dict[str, tuple[str, int | None]] = {
    # 8944 — National League North and South share one id.
    "england-amateur-national-league-north": ("8944", 940360),
    "england-amateur-national-league-south": ("8944", 940374),
    # 8947 — four of our divisions behind one id.
    "england-amateur-southern-league-premier-division-central": ("8947", 941117),
    "england-amateur-southern-league-premier-division-south": ("8947", 941118),
    "england-amateur-northern-premier-league-premier-division": ("8947", 941116),
    "england-amateur-isthmian-league-premier-division": ("8947", 941109),
    # 9545 — the Highland League with both Lowland divisions. Only Highland is on
    # our card; the Lowland groups are listed in the payload and simply unused.
    "scotland-highland-league": ("9545", 1000001473),
}

#: Cups. FotMob carries their fixtures but publishes no table, and neither does
#: anything else — a cup has no standings to have. Naming them here keeps the sweep
#: from logging a resolution failure for a competition that was never resolvable.
_NO_TABLE: frozenset[str] = frozenset(
    {
        "england-efl-cup",
        "scotland-league-cup-group-c",
        "england-amateur-u21-premier-league-cup-group-g",
    }
)


def _normalise(name: str) -> str:
    """Compare competition names without punctuation or filler."""
    lowered = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return " ".join(w for w in lowered.split() if w not in {"fc", "afc", "the"})


def _country_code(competition: CompetitionKey) -> str | None:
    """``ENG`` / ``SCO`` / ``NIR`` for a competition, or ``None``.

    ``England Amateur`` is a country to odds-api.io and a qualifier to everyone else,
    so the trailing word is dropped before the lookup.
    """
    country = competition.country.strip().lower()
    if not country:
        return None
    if country.endswith(" amateur"):
        country = country[: -len(" amateur")]
    return _COUNTRY_CODES.get(country)


def season_param(season: int) -> str:
    """``2026`` → ``2026/2027``.

    The port names a season by its starting year; FotMob answers
    ``selectedSeason: '2026/2027'`` and expects the same form on the way in.
    """
    return f"{season}/{season + 1}"


def _team_ref(row: dict[str, Any]) -> TeamRef | None:
    """A table row or match side as a :class:`TeamRef`, or ``None`` if unusable."""
    team_id = row.get("id")
    name = (row.get("name") or "").strip()
    if team_id is None or not name:
        return None
    return TeamRef(
        provider_team_id=str(team_id),
        name=name,
        short_name=(row.get("shortName") or "").strip(),
    )


def _split_score(score: str | None) -> tuple[int | None, int | None]:
    """``"1 - 2"`` → ``(1, 2)``. Anything else → ``(None, None)``.

    Deliberately tolerant: a score that does not parse leaves the match unscored
    rather than failing the division, which matters on a source that can change shape
    without telling anyone.
    """
    if not score:
        return None, None
    parts = re.findall(r"\d+", score)
    if len(parts) != 2:
        return None, None
    return int(parts[0]), int(parts[1])


#: FotMob's ``status.reason.longKey`` for a match that will never be replayed. Its
#: ``cancelled`` flag is raised for postponements too — far more often, in fact — so the
#: prose is the only thing that separates "moved to a Tuesday" from "not happening".
_CALLED_OFF_FOR_GOOD = frozenset({"cancelled", "abandoned"})


def _match_state(status: dict[str, Any]) -> MatchState:
    """Read one FotMob status block as a :class:`MatchState`.

    Order matters. ``cancelled`` is tested first because FotMob leaves ``finished`` and
    ``started`` false on a called-off match, so every other branch would answer
    "scheduled" for a game that is not going to be played — which is the failure mode
    Batch 64 already found on the slate side, where a postponed fixture kept its
    original kick-off and looked perfectly healthy.
    """
    if status.get("cancelled"):
        reason = str((status.get("reason") or {}).get("longKey") or "").lower()
        return MatchState.CANCELLED if reason in _CALLED_OFF_FOR_GOOD else MatchState.POSTPONED
    if status.get("finished"):
        return MatchState.FINISHED
    if status.get("started"):
        return MatchState.LIVE
    return MatchState.SCHEDULED


def _status_text(status: dict[str, Any], state: MatchState) -> str:
    """The provider's own words for a state, for the one column that keeps them.

    ``Match.status`` is display text and always has been ("FT", "PP", a live minute).
    It is not what anything filters on — :class:`MatchState` is — so an unrecognised
    reason is passed through rather than mapped, and a scheduled match simply has
    nothing to say.
    """
    reason = str((status.get("reason") or {}).get("short") or "")
    if reason:
        return reason[:24]
    if state is MatchState.LIVE:
        return str((status.get("liveTime") or {}).get("short") or "LIVE")[:24]
    if state is MatchState.FINISHED:
        return "FT"
    return ""


@dataclass(frozen=True)
class _ParsedMatch:
    """One row of ``fixtures.allMatches`` after the parts every caller needs are read.

    Extracted in Batch 110. Three methods walked this list with the same twenty lines of
    attribution, team-ref and kick-off parsing and differed only in which matches they
    kept; a fourth copy for the season list would have been the point at which one of
    them quietly stopped agreeing with the others about which division a club is in.
    """

    provider_match_id: str
    status: dict[str, Any]
    home: TeamRef
    away: TeamRef
    kickoff: datetime

    @property
    def state(self) -> MatchState:
        return _match_state(self.status)

    @property
    def scores(self) -> tuple[int | None, int | None]:
        return _split_score(self.status.get("scoreStr"))


def _scores_from(row: dict[str, Any]) -> tuple[int, int]:
    """A table row's ``"7-0"`` goals-for/against pair, defaulting to zeros."""
    for_, against = _split_score(row.get("scoresStr"))
    return for_ or 0, against or 0


class FotMobProvider(FootballDataProvider):
    """Tables, results and form from FotMob.

    Holds one memo per league id for the life of the client. ``FootballDataSession``
    keeps a single client per process, so a sweep pays one request for ``8947`` and
    serves all four of its competitions from it — both halves of the port included.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "the-coupon/1.0 (+https://the-coupon-production.vercel.app)"},
        )
        self._payloads: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls) -> FotMobProvider:
        """No key, and no setting to read — FotMob authenticates nothing."""
        return cls()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> FotMobProvider:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # -- resolution ------------------------------------------------------------

    async def league_id_for(self, competition: CompetitionKey) -> str | None:
        """FotMob's league id for one of our competitions, or ``None``.

        An override answers before the catalogue is touched, so an overridden
        competition costs no lookup. Otherwise the match is **country-scoped**: an
        exact name match inside the competition's own country, and nothing else. A
        near-miss returns ``None`` rather than a guess — the sweep reports a
        competition it could not resolve, which is honest, where a wrong id writes a
        wrong table that looks entirely well-formed.
        """
        override = _COMPETITION_OVERRIDES.get(competition.slug)
        if override is not None:
            return override[0]
        code = _country_code(competition)
        if code is None:
            return None
        wanted = _normalise(competition.competition_name)
        for entry in await self._catalogue():
            if entry.get("ccode") == code and _normalise(str(entry.get("name", ""))) == wanted:
                return str(entry.get("id"))
        return None

    async def _catalogue(self) -> list[dict[str, Any]]:
        """Every league FotMob lists, flattened and memoised.

        One request for the whole catalogue, like the other adapter: filtering server
        side would cost a request per country and the catalogue changes between
        seasons, not between runs.
        """
        if "__catalogue__" not in self._payloads:
            body = await self._get("/api/data/allLeagues", {})
            found: list[dict[str, Any]] = []
            seen: set[tuple[Any, Any]] = set()

            def walk(node: Any, code: str | None) -> None:
                if isinstance(node, dict):
                    here = node.get("ccode") or code
                    if isinstance(node.get("id"), int) and node.get("name"):
                        key = (node["id"], node["name"])
                        if key not in seen:
                            seen.add(key)
                            found.append({"id": node["id"], "name": node["name"], "ccode": here})
                    for value in node.values():
                        walk(value, here)
                elif isinstance(node, list):
                    for value in node:
                        walk(value, code)

            walk(body, None)
            self._payloads["__catalogue__"] = {"entries": found}
            log.info("fotmob catalogue loaded", leagues=len(found))
        return list(self._payloads["__catalogue__"]["entries"])

    # -- the one payload -------------------------------------------------------

    async def _league(
        self, league_id: str, season: int, *, refresh: bool = False
    ) -> dict[str, Any]:
        """The league payload, fetched at most once per id per client.

        The lock matters: a sweep can ask for ``8947`` four times in quick succession
        and without it each caller starts its own request, which is exactly the
        quadrupling this adapter exists to avoid.

        ``refresh`` exists for one caller and is load-bearing for it. The memo lives for
        the life of the client and the client is process-wide, so a *live* score read
        through the memo would return the same payload for as long as the process ran —
        polling every ten minutes and reporting half-time forever. It replaces the memo
        rather than bypassing it, so the fresher payload is what everything else sees
        too and the request is not paid for twice.
        """
        key = f"{league_id}:{season}"
        async with self._lock:
            if refresh or key not in self._payloads:
                self._payloads[key] = await self._get(
                    LEAGUE_PATH, {"id": league_id, "season": season_param(season)}
                )
            return self._payloads[key]

    def _groups(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """The table groups in a payload — one per real division.

        A single-division id has no ``tables``; it is normalised into a one-group list
        so both shapes read the same downstream.
        """
        tables = payload.get("table")
        if not isinstance(tables, list) or not tables:
            return []
        data = tables[0].get("data") if isinstance(tables[0], dict) else None
        if not isinstance(data, dict):
            return []
        groups = data.get("tables")
        if isinstance(groups, list) and groups:
            return [g for g in groups if isinstance(g, dict)]
        if isinstance(data.get("table"), dict):
            return [
                {
                    "leagueId": data.get("leagueId"),
                    "leagueName": data.get("leagueName"),
                    "table": data["table"],
                }
            ]
        return []

    def _group_for(
        self, payload: dict[str, Any], competition: CompetitionKey
    ) -> dict[str, Any] | None:
        """The one group belonging to ``competition``.

        Selected by the group id recorded in :data:`_COMPETITION_OVERRIDES` rather than
        by name, because the name is the thing that cannot be trusted across two
        vocabularies. A single-division payload has exactly one group and uses it.
        """
        groups = self._groups(payload)
        if not groups:
            return None
        override = _COMPETITION_OVERRIDES.get(competition.slug)
        if override is not None and override[1] is not None:
            for group in groups:
                if group.get("leagueId") == override[1]:
                    return group
            return None
        return groups[0] if len(groups) == 1 else None

    @staticmethod
    def _rows(group: dict[str, Any]) -> list[dict[str, Any]]:
        table = group.get("table")
        rows = table.get("all") if isinstance(table, dict) else None
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def _division_index(self, payload: dict[str, Any]) -> dict[str, int]:
        """Team id → the group id that team plays in.

        This is what makes a combined id safe. ``fixtures.allMatches`` carries no
        division marker, so every match is placed by looking its home team up here.
        """
        index: dict[str, int] = {}
        for group in self._groups(payload):
            group_id = group.get("leagueId")
            if group_id is None:
                continue
            for row in self._rows(group):
                if row.get("id") is not None:
                    index[str(row["id"])] = int(group_id)
        return index

    # -- the port --------------------------------------------------------------

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        """The competition's current table, or ``None`` when there is not one."""
        if competition.slug in _NO_TABLE:
            return None
        league_id = await self.league_id_for(competition)
        if league_id is None:
            log.info("fotmob competition unmatched", competition_id=competition.slug)
            return None
        payload = await self._league(league_id, season)
        group = self._group_for(payload, competition)
        if group is None:
            return None
        rows: list[TableRow] = []
        for position, row in enumerate(self._rows(group), start=1):
            team = _team_ref(row)
            if team is None:
                continue
            goals_for, goals_against = _scores_from(row)
            rows.append(
                TableRow(
                    position=int(row.get("idx") or position),
                    team=team,
                    played=int(row.get("played") or 0),
                    won=int(row.get("wins") or 0),
                    drawn=int(row.get("draws") or 0),
                    lost=int(row.get("losses") or 0),
                    goals_for=goals_for,
                    goals_against=goals_against,
                    points=int(row.get("pts") or 0),
                )
            )
        if not rows:
            return None
        return LeagueTable(competition=competition, season=season, rows=rows)

    def _parsed_matches(
        self, payload: dict[str, Any], competition: CompetitionKey
    ) -> list[_ParsedMatch]:
        """``fixtures.allMatches``, attributed to this competition and parsed.

        Drops anything that cannot be used at all — a row that is not an object, a club
        the payload does not identify, a kick-off that will not parse — and, for a
        composite id serving several divisions, anything belonging to one of the others.
        Filtering by *state* is the caller's job; this only says what is there.
        """
        matches = (payload.get("fixtures") or {}).get("allMatches")
        if not isinstance(matches, list):
            return []

        # Only a composite payload needs attributing; a single-division id owns
        # every match in its own list.
        override = _COMPETITION_OVERRIDES.get(competition.slug)
        wanted_group = override[1] if override else None
        index = self._division_index(payload) if wanted_group is not None else {}

        parsed: list[_ParsedMatch] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            status = match.get("status") or {}
            home, away = _team_ref(match.get("home") or {}), _team_ref(match.get("away") or {})
            if home is None or away is None:
                continue
            if wanted_group is not None and index.get(home.provider_team_id) != wanted_group:
                continue
            kickoff = _parse_utc(status.get("utcTime") or match.get("utcTime"))
            if kickoff is None:
                continue
            parsed.append(
                _ParsedMatch(
                    provider_match_id=str(match.get("id")),
                    status=status,
                    home=home,
                    away=away,
                    kickoff=kickoff,
                )
            )
        return parsed

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        """Finished matches for one competition, inside an optional date window.

        Shares the memoised payload with :meth:`fetch_table`, so asking for both costs
        one upstream request rather than the two api-football needs.
        """
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return []
        payload = await self._league(league_id, season)

        results: list[MatchResult] = []
        for parsed in self._parsed_matches(payload, competition):
            if parsed.state is not MatchState.FINISHED:
                continue
            if since is not None and parsed.kickoff.date() < since:
                continue
            if until is not None and parsed.kickoff.date() > until:
                continue
            home_goals, away_goals = parsed.scores
            results.append(
                MatchResult(
                    provider_match_id=parsed.provider_match_id,
                    competition=competition,
                    season=season,
                    kickoff_utc=parsed.kickoff,
                    home=parsed.home,
                    away=parsed.away,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    finished=True,
                    status=str((parsed.status.get("reason") or {}).get("short") or "FT"),
                )
            )
        return results

    async def fetch_live_scores(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        """Matches in progress right now, with the score so far (Batch 72).

        The same ``allMatches`` list :meth:`fetch_results` reads, filtered the other way:
        started, not finished, not called off. FotMob needs no key and has no rate limit
        to protect, which is the whole reason live scores are affordable at all — nothing
        new is contracted and no budget is spent.

        **Forces a payload refresh.** The memo is per client and the client is
        process-wide, so reading a live score through it would answer with whatever the
        first caller of the day saw.

        ``finished=False`` with a partial score is a deliberate combination:
        :func:`~src.services.football_data.sync_results` writes ``finished`` from
        ``result.finished and home_goals is not None``, so an in-play match stores its
        running score *and* stays out of every read that gates on ``finished`` — the
        results screen, the form line, and Batch 67's settled scorelines.
        """
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return []
        payload = await self._league(league_id, season, refresh=True)

        live: list[MatchResult] = []
        for parsed in self._parsed_matches(payload, competition):
            if parsed.state is not MatchState.LIVE:
                continue
            home_goals, away_goals = parsed.scores
            if home_goals is None or away_goals is None:
                # Kicked off but no score published yet. Nil-nil is a real scoreline and
                # "we do not know" is not, so this stays absent rather than becoming 0-0.
                continue
            live.append(
                MatchResult(
                    provider_match_id=parsed.provider_match_id,
                    competition=competition,
                    season=season,
                    kickoff_utc=parsed.kickoff,
                    home=parsed.home,
                    away=parsed.away,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    state=MatchState.LIVE,
                    status=str(parsed.status.get("liveTime", {}).get("short") or "LIVE")[:24],
                )
            )
        return live

    async def fetch_season_matches(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        """The competition's whole season — played, to be played, or called off.

        The same ``allMatches`` list :meth:`fetch_results` reads, unfiltered. That is the
        point: FotMob publishes the entire season in one payload, so a date window and a
        finished-only filter save **nothing upstream** — they only decide how much of
        what has already arrived gets written down. Until Batch 110 the answer was "the
        finished ones inside the last few days", which is why the store could not answer
        what a club is playing next.

        Shares the memo with :meth:`fetch_table` and :meth:`fetch_results`, so a sweep
        that asks for a table and a season pays for one request.

        Scores are ``None`` for anything unplayed, and a postponed match keeps its
        original kick-off because that is what the payload carries — the state is what
        says it is not happening then, which is the whole reason
        :class:`~src.services.football_provider.MatchState` exists.
        """
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return []
        payload = await self._league(league_id, season)

        matches: list[MatchResult] = []
        for parsed in self._parsed_matches(payload, competition):
            home_goals, away_goals = parsed.scores
            state = parsed.state
            matches.append(
                MatchResult(
                    provider_match_id=parsed.provider_match_id,
                    competition=competition,
                    season=season,
                    kickoff_utc=parsed.kickoff,
                    home=parsed.home,
                    away=parsed.away,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    state=state,
                    status=_status_text(parsed.status, state),
                )
            )
        return matches

    async def fetch_fixture_states(
        self, competition: CompetitionKey, season: int
    ) -> list[FixtureState]:
        """Every match FotMob lists for the competition, played or not, with its status.

        Shares the memoised payload with :meth:`fetch_table` and :meth:`fetch_results`, so
        a cross-check of a card that spans a competition already swept costs no request.

        Unlike :meth:`fetch_results` this keeps the cancelled ones — they are the entire
        point. ``status.cancelled`` is what marks a postponement, and it is the *only*
        thing that does: FotMob leaves ``utcTime`` at the original kick-off, so a
        postponed match reads as a perfectly healthy one on date alone.
        """
        league_id = await self.league_id_for(competition)
        if league_id is None:
            return []
        payload = await self._league(league_id, season)
        matches = (payload.get("fixtures") or {}).get("allMatches")
        if not isinstance(matches, list):
            matches = (payload.get("matches") or {}).get("allMatches")
        if not isinstance(matches, list):
            return []

        # Same attribution as fetch_results: a composite id carries several divisions.
        override = _COMPETITION_OVERRIDES.get(competition.slug)
        wanted_group = override[1] if override else None
        index = self._division_index(payload) if wanted_group is not None else {}

        states: list[FixtureState] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            status = match.get("status") or {}
            home, away = _team_ref(match.get("home") or {}), _team_ref(match.get("away") or {})
            if home is None or away is None:
                continue
            if wanted_group is not None and index.get(home.provider_team_id) != wanted_group:
                continue
            kickoff = _parse_utc(status.get("utcTime") or match.get("utcTime"))
            if kickoff is None:
                continue
            states.append(
                FixtureState(
                    home=home.name,
                    away=away.name,
                    kickoff_utc=kickoff,
                    cancelled=bool(status.get("cancelled")),
                    reason=str((status.get("reason") or {}).get("long") or ""),
                )
            )
        return states

    # -- transport -------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """One GET, with a 404 treated as an error rather than as absent data.

        That distinction is the whole point. The interface is undocumented and it
        moves — ``/api/leagues?id=47`` began answering 404 while ``/api/data/leagues``
        answered 200 — so a 404 read as "no table for this division" would turn a path
        change into twenty-one competitions quietly carrying nothing. Batch 45 makes a
        run that carries nothing fail; this keeps that signal truthful.
        """
        # Batch 101 records every outcome here because this is the one funnel every
        # FotMob request goes through — a signal taken anywhere else would miss whichever
        # of the three features happened not to be running.
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            fotmob_health.request_failed(status=None, reason=f"{path} unreachable: {exc}")
            raise FootballDataAPIError(f"fotmob {path} unreachable: {exc}") from exc
        if response.status_code >= 400:
            fotmob_health.request_failed(
                status=response.status_code,
                reason=f"{path} returned {response.status_code}.",
            )
            raise FootballDataAPIError(f"fotmob {path} returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            # A 200 that is not JSON is the shape changing under us — the interface is
            # undocumented and has moved before. Counted as a failure, not shrugged off.
            fotmob_health.request_failed(status=None, reason=f"{path} returned non-JSON.")
            raise FootballDataAPIError(f"fotmob {path} returned non-JSON") from exc
        if not isinstance(body, dict):
            fotmob_health.request_failed(
                status=None,
                reason=f"{path} returned {type(body).__name__}, not an object.",
            )
            raise FootballDataAPIError(
                f"fotmob {path} returned {type(body).__name__}, not an object"
            )
        fotmob_health.request_succeeded()
        return body


def _parse_utc(value: object) -> datetime | None:
    """``"2026-08-08T14:00:00Z"`` → an aware UTC datetime, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
