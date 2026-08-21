"""The odds port — what The Coupon needs from any odds source, in its own vocabulary.

The game needs four things from a provider, and nothing else:

* ``fetch_slate(saturday)``  — that Saturday's British 15:00 kick-offs → :class:`Slate`.
* ``fetch_odds(event_ids)``  — the Match Odds + BTTS selections the provider actually
  prices → :class:`FixtureOdds`.
* ``settle(event_ids)``      — the finished result per event → :class:`EventSettlement`.
* ``fetch_competitions()``   — the competitions it carries → :class:`Competition`, which
  is what a league admin's competition picker offers.

plus a ``login`` / ``keep_alive`` / ``close`` lifecycle, which a session-based provider
uses and a key-based one no-ops.

Everything here is expressed in *the game's* terms — market, outcome, price — never a
provider's. That is the point of the port: a pick is identified by ``(fixture, market,
outcome)``, which is exactly the uniqueness rule the leaderboard already enforces, so no
provider identifier needs to survive into settlement. Betfair market/selection ids used
to leak all the way into the ``picks`` table; revision ``005`` removed them.

Implementations:

* :class:`~src.services.odds_api.OddsApiProvider` — odds-api.io priced by a single
  bookmaker (Bet365). The production source.
* :class:`~src.services.betfair.Betfair` — the Betfair Exchange, retained as a fallback.
* :class:`~src.services.betfair.FakeBetfair` — canned data for tests and staging.

See ``docs/adr/0002-replace-betfair-exchange-with-odds-api-io.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ── Slate rule ─────────────────────────────────────────────────────────────────

UK_TZ = ZoneInfo("Europe/London")
SATURDAY = 5  # date.weekday(): Monday=0 … Saturday=5
KICKOFF_HOUR = 15  # 15:00 UK local — "one Saturday's 3pm kick-offs"

MARKET_MATCH_ODDS = "MATCH_ODDS"
MARKET_BTTS = "BOTH_TEAMS_TO_SCORE"


# ── Exceptions ─────────────────────────────────────────────────────────────────


class OddsProviderError(Exception):
    """Base error for any odds-provider failure."""


class OddsProviderAuthError(OddsProviderError):
    """Authentication failed, or an operation was attempted before authenticating."""


class OddsProviderAPIError(OddsProviderError):
    """The provider returned an error, or a response we cannot use."""


# ── Domain models ──────────────────────────────────────────────────────────────


class Market(StrEnum):
    MATCH_ODDS = MARKET_MATCH_ODDS
    BOTH_TEAMS_TO_SCORE = MARKET_BTTS


class Outcome(StrEnum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"


class Selection(BaseModel):
    """One offerable pick — a market + outcome the provider currently prices.

    ``price`` is a :class:`~decimal.Decimal` rather than a float because it is frozen
    onto ``picks.odds_at_pick`` (``Numeric(6, 2)``) and then multiplied to award points.
    odds-api.io returns prices as strings; parsing them through ``float`` first would
    reintroduce binary rounding into a value the player is scored on.
    """

    market: Market
    outcome: Outcome
    runner_name: str
    price: Decimal


class FixtureOdds(BaseModel):
    """The priced selections for a single fixture (across Match Odds + BTTS)."""

    provider_event_id: str
    home: str
    away: str
    selections: list[Selection]


@dataclass(frozen=True)
class OddsSnapshot:
    """Prices for a set of events, and whether the source was actually reachable.

    ``degraded`` is true when these are whatever could be salvaged from a *failed*
    refresh — last known prices, or none at all — rather than a live answer. It is the
    browsing path's return type alone: freezing a price onto a pick calls
    :meth:`OddsProvider.fetch_odds`, which raises rather than degrading.
    """

    odds: list[FixtureOdds]
    degraded: bool


class Competition(BaseModel):
    """One competition a provider carries — a catalogue entry, not a fixture.

    The field names match :class:`SlateFixture`'s pair deliberately: what an admin ticks
    in the picker is the same identifier a fixture is later tagged with, so a stored
    selection can be compared against a slate without a translation step.
    """

    competition_id: str
    competition: str


class SlateFixture(BaseModel):
    """One British match inside a league's slate window."""

    provider_event_id: str
    home: str
    away: str
    kickoff_utc: datetime
    competition: str
    competition_id: str


class Slate(BaseModel):
    """A round's worth of fixtures — everything inside one league's window."""

    starts_on: date
    fixtures: list[SlateFixture]


class OutcomeResult(BaseModel):
    """Whether one market+outcome won, once its market has a final result."""

    market: Market
    outcome: Outcome
    won: bool


class EventSettlement(BaseModel):
    """The final result of one fixture, in market/outcome terms.

    ``settled_markets`` is what separates *not yet* from *nothing to award*: a pick whose
    market is absent stays pending, while a pick whose market settled but whose outcome
    never appears is void (a removed runner, or a market the provider stopped offering).
    ``void`` covers the whole-fixture case — postponed or abandoned — where every pick on
    the event scores nothing rather than losing.
    """

    provider_event_id: str
    status: str
    settled: bool
    void: bool = False
    settled_markets: list[Market] = []
    outcomes: list[OutcomeResult] = []


# ── Shared helpers ─────────────────────────────────────────────────────────────


def as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime (assume UTC for naive inputs)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_z(value: datetime) -> str:
    """Serialise to the ``…Z`` UTC form both providers' time filters expect."""
    return as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SlateWindow:
    """When a league's round runs — a range in UK local time, plus its lock.

    Batch 14 lifted this out of module constants so leagues can differ. The product
    shipped with a single Saturday 15:00 kick-off, which is this range with its start
    equal to its end; a league playing Friday 19:00 to Monday 22:00 is
    ``(FRIDAY, 19*60) → (MONDAY, 22*60)``. Weekdays follow ``date.weekday()``, minutes
    are from local midnight.

    Anchored in ``Europe/London`` throughout, so a window is correct under both BST
    and GMT — the season spans August (BST) to May (GMT).
    """

    start_weekday: int = SATURDAY
    start_minute: int = KICKOFF_HOUR * 60
    end_weekday: int = SATURDAY
    end_minute: int = KICKOFF_HOUR * 60
    lock_offset_minutes: int = 30

    @property
    def span_days(self) -> int:
        """Whole days from the window's start weekday to its end weekday."""
        return (self.end_weekday - self.start_weekday) % 7

    def first_start_on_or_after(self, today: date) -> date:
        """The next date this window opens on, today included."""
        return today + timedelta(days=(self.start_weekday - today.weekday()) % 7)

    def opens_at(self, starts_on: date) -> datetime:
        """Aware local instant the window opens for a round starting ``starts_on``."""
        return datetime(starts_on.year, starts_on.month, starts_on.day, tzinfo=UK_TZ) + timedelta(
            minutes=self.start_minute
        )

    def closes_at(self, starts_on: date) -> datetime:
        """Aware local instant the window closes — may be days after it opened."""
        end_day = starts_on + timedelta(days=self.span_days)
        return datetime(end_day.year, end_day.month, end_day.day, tzinfo=UK_TZ) + timedelta(
            minutes=self.end_minute
        )

    def utc_before_open(self, starts_on: date, minutes: int) -> datetime:
        """Naive-UTC instant ``minutes`` before this window opens on ``starts_on``.

        The anchor every per-league offset is measured from. Batch 27's pick-open
        instant is a second such offset and lives on the league rather than here, so a
        league that only differs by *when picks open* still hashes to the same window
        and shares one provider fetch (see ``discover_fixtures``).
        """
        local = self.opens_at(starts_on) - timedelta(minutes=minutes)
        return local.astimezone(UTC).replace(tzinfo=None)

    def locks_at(self, starts_on: date) -> datetime:
        """Naive-UTC instant picks lock: ``lock_offset_minutes`` before it opens."""
        return self.utc_before_open(starts_on, self.lock_offset_minutes)

    def query_bounds(self, starts_on: date) -> tuple[datetime, datetime]:
        """UTC [start, end) covering every local day the window touches.

        Deliberately wider than the window itself: providers filter by time range, so
        this asks for whole days and :meth:`contains` decides which of the returned
        kick-offs actually qualify. A window whose start equals its end would
        otherwise be an empty query.
        """
        start_local = datetime(starts_on.year, starts_on.month, starts_on.day, tzinfo=UK_TZ)
        end_local = start_local + timedelta(days=self.span_days + 1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    def contains(self, kickoff_utc: datetime, starts_on: date) -> bool:
        """True when a kick-off falls inside the window, endpoints included.

        Inclusive at both ends so the default point window — start equal to end —
        still matches the 15:00 kick-offs it describes.
        """
        local = as_utc(kickoff_utc).astimezone(UK_TZ)
        return self.opens_at(starts_on) <= local <= self.closes_at(starts_on)


#: The rule the product shipped with, and the default every league still gets.
SATURDAY_THREE_PM = SlateWindow()


def split_event_name(name: str) -> tuple[str, str] | None:
    """Split an event name ``"Home v Away"`` into ``(home, away)``.

    Both providers name football events home-first. Returns ``None`` when the name
    doesn't follow that shape so callers can degrade gracefully.
    """
    for separator in (" v ", " vs ", " @ "):
        if separator in name:
            home, _, away = name.partition(separator)
            home, away = home.strip(), away.strip()
            if home and away:
                return home, away
    return None


def match_odds_outcome(runner_name: str, home: str, away: str) -> Outcome:
    """Map a Match Odds runner to HOME / AWAY / DRAW.

    Match Odds has exactly three runners: the two team names and the draw. Anything that
    isn't the home or away team is the draw.
    """
    name = runner_name.strip().casefold()
    if name == home.strip().casefold():
        return Outcome.HOME
    if name == away.strip().casefold():
        return Outcome.AWAY
    return Outcome.DRAW


def btts_outcome(runner_name: str) -> Outcome | None:
    """Map a BTTS runner ("Yes" / "No") to YES / NO; ``None`` for anything unexpected."""
    name = runner_name.strip().casefold()
    if name == "yes":
        return Outcome.YES
    if name == "no":
        return Outcome.NO
    return None


def outcomes_from_score(home_goals: int, away_goals: int) -> list[OutcomeResult]:
    """Derive both markets' results from a final score.

    This is the substance of the odds-api.io migration. Betfair reported a winning runner
    directly from the Exchange market book; odds-api.io reports the score, so Match Odds
    comes from comparing the two numbers and Both Teams To Score from both being non-zero.
    Every outcome is reported — winners *and* losers — so a pick on a losing outcome is
    resolved as ``lost`` rather than mistaken for a missing market.
    """
    if home_goals > away_goals:
        winner = Outcome.HOME
    elif away_goals > home_goals:
        winner = Outcome.AWAY
    else:
        winner = Outcome.DRAW
    both_scored = home_goals > 0 and away_goals > 0
    return [
        OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.HOME, won=winner is Outcome.HOME),
        OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.DRAW, won=winner is Outcome.DRAW),
        OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.AWAY, won=winner is Outcome.AWAY),
        OutcomeResult(market=Market.BOTH_TEAMS_TO_SCORE, outcome=Outcome.YES, won=both_scored),
        OutcomeResult(market=Market.BOTH_TEAMS_TO_SCORE, outcome=Outcome.NO, won=not both_scored),
    ]


# ── The port ───────────────────────────────────────────────────────────────────


class OddsProvider(ABC):
    """What The Coupon requires of an odds source.

    Four domain operations plus a session lifecycle. Providers authenticated by an API
    key implement ``login`` / ``keep_alive`` as no-ops; the shared session
    (:mod:`src.services.odds_session`) drives the lifecycle identically either way.
    """

    @abstractmethod
    async def login(self) -> str:
        """Establish a session and return its token (``""`` when none is needed)."""

    @abstractmethod
    async def keep_alive(self) -> None:
        """Refresh the current session so it doesn't time out."""

    @abstractmethod
    async def close(self) -> None:
        """Release any client resources held by the provider."""

    @abstractmethod
    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        """Return the British kick-offs inside ``window`` for the round on ``starts_on``.

        Takes the window rather than a bare date because since Batch 14 the slate rule
        is per-league: what counts as "this round's fixtures" is the league's setting,
        not a constant.

        ``competition_ids`` narrows the fetch itself to those competitions; ``None`` —
        the default, and what shared discovery always passes — is every UK competition
        the source carries. It is an argument rather than the caller filtering the
        result because the cost *is* the fan-out: one request per competition. Only a
        fetch nobody else shares may narrow it (see
        :func:`src.services.gameweek.refresh_slate`); narrowing a shared one would save
        one league's requests by denying another league its fixtures.
        """

    @abstractmethod
    async def fetch_competitions(self) -> list[Competition]:
        """Every competition this provider carries for the countries the game plays.

        The catalogue a league admin picks from. Deliberately *not* derived from stored
        fixtures: until Batch 21 it was, so a league whose slate had never run had
        nothing to tick and "all UK leagues" was the only usable setting.

        Abstract rather than a non-abstract default returning ``[]``, because an empty
        catalogue is indistinguishable from "this source carries nothing" and the picker
        would silently show the very emptiness this replaced. Every implementation
        answers for itself, and it is cheap on both: one already-memoised ``/leagues``
        call on odds-api.io, one ``listCompetitions`` on the Exchange.
        """

    @abstractmethod
    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        """Snapshot the priced Match Odds + BTTS selections for the given events.

        ``max_age_seconds`` is the caller's freshness ceiling: "do not serve me a
        price older than this". Providers that always go upstream satisfy any
        ceiling and ignore it; only :class:`~src.services.odds_cache.CachingOddsProvider`
        acts on it, tightening its TTL for the call. It exists because browsing the
        slate and freezing a price at pick time want very different freshness for
        very different costs against the provider's rate limit.
        """

    async def fetch_odds_best_effort(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> OddsSnapshot:
        """:meth:`fetch_odds` for the browsing path — degrades instead of raising.

        The pick screen is the one every member opens, and until Batch 48 its
        availability was wired straight to a third party's rate limit: a ``429`` from the
        provider propagated out of ``fetch_odds`` and the whole slate answered ``500``.
        Browsing tolerates far less than that. A slightly stale price beats a broken
        screen, and a card with *no* prices still shows the fixtures, which beats an
        error page. **Freezing a price onto a pick is the opposite case** and keeps
        calling :meth:`fetch_odds`, because a winner scores ``round(odds × 10)`` from
        that number and a price we could not confirm is a wrong score, not a degraded one.

        This default has nothing to fall back *to*, so it degrades to no prices at all.
        :class:`~src.services.odds_cache.CachingOddsProvider` overrides it with the
        entries it is already holding, and the provider handed to a request is always
        the cached one (``deps.get_odds_provider``), so that override is the live path.
        """
        try:
            odds = await self.fetch_odds(event_ids, max_age_seconds=max_age_seconds)
        except OddsProviderError as exc:
            log.warning("odds unavailable, serving none", events=len(event_ids), error=repr(exc))
            return OddsSnapshot(odds=[], degraded=True)
        return OddsSnapshot(odds=odds, degraded=False)

    @abstractmethod
    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        """Report the final result of each event, in market/outcome terms."""
