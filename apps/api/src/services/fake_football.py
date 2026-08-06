"""Canned football data — the tests' and staging's source of tables, results and form.

The counterpart to :class:`~src.services.betfair.FakeBetfair`, and deliberately shaped to
fit it: the clubs are exactly the ones on the canned slate (Arsenal v Chelsea, Forfar
Athletic v Brechin City), so the staging story shows a real table and real form beside the
fixtures a member can actually pick.

The clubs are spelled here the way a *different* provider would spell them — "Arsenal FC"
against the slate's "Arsenal" — because that mismatch is the point. If the fake used
identical strings, the reconciliation layer would be exercised by nothing and the first
real spelling difference would be found in production.

The canned season is 2025 (i.e. 2025-26), ending in May 2026, while the canned slate is
the opening Saturday of 2026-27. That is the ordinary opening-day situation: what a member
sees on the first weekend is last season's final table and the results behind it. Set
``FOOTBALL_SEASON=2025`` to point ingestion at it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Self

from src.services.football_provider import (
    CompetitionKey,
    FootballDataProvider,
    LeagueTable,
    MatchResult,
    TableRow,
)
from src.services.team_matching import normalise_name

#: The season the canned data describes — 2025-26, ending May 2026.
SAMPLE_SEASON = 2025

SAMPLE_EPL = "English Premier League"
SAMPLE_SL2 = "Scottish League Two"

#: ``(provider id, name)``. The names carry the "FC" the canned slate omits, so the
#: reconciliation layer is doing real work every time this data is ingested.
ARSENAL = ("af-42", "Arsenal FC")
CHELSEA = ("af-49", "Chelsea FC")
LIVERPOOL = ("af-40", "Liverpool FC")
SPURS = ("af-47", "Tottenham Hotspur FC")
EVERTON = ("af-45", "Everton FC")
FORFAR = ("af-901", "Forfar Athletic FC")
BRECHIN = ("af-902", "Brechin City FC")
ELGIN = ("af-903", "Elgin City FC")
STRANRAER = ("af-904", "Stranraer FC")


class FakeFootballData(FootballDataProvider):
    """In-memory football-data provider returning canned tables and results.

    Tables and results are keyed by the **normalised competition name**, not by a slug, so
    the same fake serves both the Betfair-style numeric competition ids the canned slate
    uses and odds-api.io's slugs.

    Season and date filtering are real rather than ignored: ingestion decides what to ask
    for, and a fake that answered everything regardless would let a wrong request pass.
    """

    def __init__(
        self,
        *,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        results: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        season: int = SAMPLE_SEASON,
    ) -> None:
        self._tables = {normalise_name(k): list(v) for k, v in (tables or {}).items()}
        self._results = {normalise_name(k): list(v) for k, v in (results or {}).items()}
        self._season = season
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        rows = self._tables.get(normalise_name(competition.competition_name))
        if not rows or season != self._season:
            return None
        return LeagueTable(
            competition=competition,
            season=season,
            rows=[TableRow.model_validate(row) for row in rows],
        )

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        raw = self._results.get(normalise_name(competition.competition_name))
        if not raw or season != self._season:
            return []
        matches = [
            MatchResult.model_validate({**row, "competition": competition, "season": season})
            for row in raw
        ]
        return sorted(
            (m for m in matches if _within(m.kickoff_utc.date(), since, until)),
            key=lambda m: (m.kickoff_utc, m.provider_match_id),
        )

    @classmethod
    def with_sample_data(cls) -> Self:
        """A realistic canned season for the two competitions on the canned slate.

        ``Self`` rather than the class itself so a subclass — the tests' request-counting
        one — keeps its own type through this constructor.
        """
        return cls(tables=_SAMPLE_TABLES, results=_SAMPLE_RESULTS, season=SAMPLE_SEASON)


def _within(day: date, since: date | None, until: date | None) -> bool:
    if since is not None and day < since:
        return False
    return not (until is not None and day > until)


def _row(
    position: int,
    team: tuple[str, str],
    played: int,
    won: int,
    drawn: int,
    lost: int,
    goals_for: int,
    goals_against: int,
    form: str,
) -> dict[str, Any]:
    return {
        "position": position,
        "team": {"provider_team_id": team[0], "name": team[1]},
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "points": won * 3 + drawn,
        "form": form,
    }


def _match(
    match_id: str,
    day: str,
    home: tuple[str, str],
    away: tuple[str, str],
    home_goals: int,
    away_goals: int,
) -> dict[str, Any]:
    return {
        "provider_match_id": match_id,
        "kickoff_utc": datetime.fromisoformat(f"{day}T14:00:00").replace(tzinfo=UTC),
        "home": {"provider_team_id": home[0], "name": home[1]},
        "away": {"provider_team_id": away[0], "name": away[1]},
        "home_goals": home_goals,
        "away_goals": away_goals,
        "finished": True,
        "status": "FT",
    }


# ── Canned season 2025-26 ──────────────────────────────────────────────────────

_SAMPLE_TABLES: dict[str, list[dict[str, Any]]] = {
    SAMPLE_EPL: [
        _row(1, ARSENAL, 38, 26, 8, 4, 84, 32, "WWDWW"),
        _row(2, CHELSEA, 38, 23, 7, 8, 71, 40, "WLWDW"),
        _row(3, LIVERPOOL, 38, 22, 9, 7, 78, 41, "DWWLW"),
        _row(4, SPURS, 38, 19, 8, 11, 66, 51, "LWDWL"),
        _row(5, EVERTON, 38, 12, 11, 15, 44, 52, "DLLDW"),
    ],
    SAMPLE_SL2: [
        _row(1, FORFAR, 36, 20, 8, 8, 58, 39, "WDWWL"),
        _row(2, BRECHIN, 36, 18, 9, 9, 52, 41, "LWDWW"),
        _row(3, ELGIN, 36, 15, 10, 11, 47, 45, "DDWLW"),
        _row(4, STRANRAER, 36, 9, 7, 20, 33, 61, "LLDLW"),
    ],
}

_SAMPLE_RESULTS: dict[str, list[dict[str, Any]]] = {
    SAMPLE_EPL: [
        _match("af-m-101", "2026-04-11", ARSENAL, EVERTON, 3, 0),
        _match("af-m-102", "2026-04-11", CHELSEA, LIVERPOOL, 1, 1),
        _match("af-m-103", "2026-04-18", LIVERPOOL, ARSENAL, 2, 2),
        _match("af-m-104", "2026-04-18", SPURS, CHELSEA, 0, 2),
        _match("af-m-105", "2026-04-25", ARSENAL, SPURS, 2, 1),
        _match("af-m-106", "2026-04-25", EVERTON, CHELSEA, 1, 3),
        _match("af-m-107", "2026-05-02", CHELSEA, ARSENAL, 0, 1),
        _match("af-m-108", "2026-05-02", LIVERPOOL, EVERTON, 4, 0),
    ],
    SAMPLE_SL2: [
        _match("af-m-201", "2026-04-11", FORFAR, ELGIN, 2, 0),
        _match("af-m-202", "2026-04-11", BRECHIN, STRANRAER, 3, 1),
        _match("af-m-203", "2026-04-18", ELGIN, BRECHIN, 1, 1),
        _match("af-m-204", "2026-04-18", STRANRAER, FORFAR, 0, 2),
        _match("af-m-205", "2026-04-25", FORFAR, BRECHIN, 1, 2),
        _match("af-m-206", "2026-05-02", BRECHIN, ELGIN, 2, 2),
    ],
}


def sample_competitions() -> Iterable[str]:
    """The competition names the canned data covers — used by tests and seeds."""
    return (SAMPLE_EPL, SAMPLE_SL2)
