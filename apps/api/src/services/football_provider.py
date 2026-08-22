"""The football-data port — tables, results, and form, in The Coupon's own vocabulary.

A second source, alongside the odds port. odds-api.io prices fixtures and publishes
nothing else: no league table, no historical result, no form. Everything Batch 16 shows
therefore comes from a different provider, and this module is the boundary between the
two so neither one's vocabulary leaks into the app.

The game needs two things here, and nothing else:

* ``fetch_table(competition, season)``   — the current league table → :class:`LeagueTable`.
* ``fetch_results(competition, season)`` — finished matches with scores → :class:`MatchResult`.

Both take a :class:`CompetitionKey` rather than a provider league id, because a
competition is identified in this codebase by the **odds** provider's slug — that is what
``fixtures.competition_id`` holds. Resolving that to whatever the football-data provider
calls the same competition is the adapter's problem, not the caller's, and an adapter that
cannot resolve it returns ``None`` rather than guessing.

Unlike the odds port there is no session lifecycle beyond ``close``: both implementations
are key-authenticated, and the one thing a session bought on the Exchange (keep-alive) has
no analogue here.

**The read path never calls a provider.** Ingestion writes ``teams`` / ``matches`` /
``standings``; every screen reads those tables. That is deliberate — putting
``fetch_odds`` in the request path is what forced the whole caching apparatus in
:mod:`src.services.odds_cache`, and this source has a *daily* allowance an order of
magnitude smaller.

Implementations:

* :class:`~src.services.api_football.ApiFootballProvider` — API-Football (api-sports.io).
* :class:`~src.services.fake_football.FakeFootballData` — canned data for tests/staging.

See ``docs/adr/0003-api-football-as-the-football-data-provider.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel

#: A season is named by the calendar year it starts in — 2026-27 is ``2026``.
#: British football runs August to May, so July is a safe rollover point: no
#: competition in the slate is mid-season across it.
_SEASON_ROLLOVER_MONTH = 7


class FootballDataError(Exception):
    """Base error for any football-data provider failure."""


class FootballDataAuthError(FootballDataError):
    """Authentication failed, or an operation was attempted without a usable key."""


class FootballDataAPIError(FootballDataError):
    """The provider returned an error, or a response we cannot use."""


class FormResult(StrEnum):
    """One match from a team's point of view — the letters a form string is made of."""

    WIN = "W"
    DRAW = "D"
    LOSS = "L"


class CompetitionKey(BaseModel):
    """A competition as *this codebase* names it, which is how the odds source named it.

    ``slug`` is ``fixtures.competition_id`` (odds-api.io's league slug, e.g.
    ``scotland-league-one``) and ``name`` is ``fixtures.competition`` (e.g.
    ``Scotland - League One``). Both are carried because they are the only handles on a
    competition the app has, and an adapter needs the human name to match a catalogue
    entry that has never heard of the other provider's slug.
    """

    slug: str
    name: str

    @property
    def country(self) -> str:
        """The country half of ``"<Country> - <Competition>"``, or ``""``.

        odds-api.io names every league that way (verified across its 728-league
        catalogue in Batch 7), which makes the country free to recover here.
        """
        head, separator, _ = self.name.partition(" - ")
        return head.strip() if separator else ""

    @property
    def competition_name(self) -> str:
        """The competition half of the name, falling back to the whole thing."""
        _, separator, tail = self.name.partition(" - ")
        return tail.strip() if separator and tail.strip() else self.name.strip()


class TeamRef(BaseModel):
    """One club, as the football-data provider identifies it.

    ``provider_team_id`` is the stable key — team *names* are exactly what cannot be
    trusted across providers, which is the whole reason
    :mod:`src.services.team_matching` exists.
    """

    provider_team_id: str
    name: str
    short_name: str = ""


class TableRow(BaseModel):
    """One club's line in a league table."""

    position: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    #: The provider's own form string, most recent **last** (e.g. ``"LWWDW"``).
    #: Kept as published; the form The Coupon shows is derived from ``matches``
    #: instead, so a team with no table entry still gets one.
    form: str = ""

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


class LeagueTable(BaseModel):
    """A competition's current table for one season."""

    competition: CompetitionKey
    season: int
    rows: list[TableRow]


class MatchResult(BaseModel):
    """One played (or scheduled) match, with its score when there is one.

    Scores are ``None`` until the match finishes. ``finished`` is the gate rather than
    the presence of a score, for the same reason it is on the odds side: an in-play
    match carries a partial score, and treating that as a result would record a match
    at whatever it happened to be at half time.
    """

    provider_match_id: str
    competition: CompetitionKey
    season: int
    kickoff_utc: datetime
    home: TeamRef
    away: TeamRef
    home_goals: int | None = None
    away_goals: int | None = None
    finished: bool = False
    status: str = ""


class FixtureState(BaseModel):
    """Where a *scheduled* match stands, according to the football-data source.

    The counterpart to :class:`MatchResult`, which only describes matches that were
    played. This describes ones that have not been yet, and exists for a single question
    the odds provider cannot answer: **is this fixture still on?**

    ``cancelled`` is the provider's own postponement flag. It has to be carried
    separately from ``kickoff_utc`` because a postponed match keeps its *original*
    kick-off in FotMob's payload — the date alone cannot tell a postponement from a
    healthy fixture, which is exactly how two Premiership games survived a date-only
    cross-check and stayed pickable (Batch 64).
    """

    home: str
    away: str
    kickoff_utc: datetime
    cancelled: bool = False
    #: The provider's words for *why* — "Postponed", "Cancelled" — for the log line.
    reason: str = ""


def season_for(day: date) -> int:
    """The season a date falls in, named by its starting year.

    August 2026 and February 2027 are both season ``2026``.
    """
    return day.year if day.month >= _SEASON_ROLLOVER_MONTH else day.year - 1


def current_season() -> int:
    """The season today falls in."""
    return season_for(datetime.now(UTC).date())


def form_result(goals_for: int, goals_against: int) -> FormResult:
    """One team's result from a final score."""
    if goals_for > goals_against:
        return FormResult.WIN
    if goals_for < goals_against:
        return FormResult.LOSS
    return FormResult.DRAW


class FootballDataProvider(ABC):
    """What The Coupon requires of a football-data source."""

    @abstractmethod
    async def close(self) -> None:
        """Release any client resources held by the provider."""

    @abstractmethod
    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        """The competition's current table, or ``None`` when the provider lacks it.

        ``None`` is a real answer, not an error: no source carries every competition the
        odds provider prices, and a cup round has no table at all. The caller records
        nothing and the screens simply omit that competition.
        """

    @abstractmethod
    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        """Matches in the competition's season, optionally bounded by date.

        Unbounded is the season backfill; bounded is the scheduled top-up. Returns an
        empty list — never raises — for a competition the provider does not carry.
        """

    async def fetch_fixture_states(
        self, competition: CompetitionKey, season: int
    ) -> list[FixtureState]:
        """Every scheduled match this source lists for the competition, with its status.

        Deliberately **not** abstract, and defaulting to "I don't know". The one caller
        (:mod:`src.services.slate_verification`) treats an empty list as *no opinion* and
        leaves the card exactly as the odds provider gave it, so a provider that cannot
        answer this costs nothing beyond the cross-check it does not get. Only the FotMob
        adapter overrides it; api-football's free plan refuses the current season outright.

        Returns an empty list — never raises — for a competition it does not carry.
        """
        return []
