"""The odds port — what The Coupon needs from any odds source, in its own vocabulary.

The game needs three things from a provider, and nothing else:

* ``fetch_slate(saturday)`` — that Saturday's British 15:00 kick-offs → :class:`Slate`.
* ``fetch_odds(event_ids)`` — the Match Odds + BTTS selections the provider actually
  prices → :class:`FixtureOdds`.
* ``settle(event_ids)``     — the finished result per event → :class:`EventSettlement`.

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
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel

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


class SlateFixture(BaseModel):
    """One Saturday-15:00 British match."""

    provider_event_id: str
    home: str
    away: str
    kickoff_utc: datetime
    competition: str
    competition_id: str


class Slate(BaseModel):
    """A gameweek's worth of fixtures — one Saturday's 15:00 kick-offs."""

    saturday: date
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


def saturday_window(saturday: date) -> tuple[datetime, datetime]:
    """UTC [start, end) covering the whole of ``saturday`` in UK local time.

    Anchored in ``Europe/London`` so the window is correct under both BST and GMT — the
    season spans August (BST) to May (GMT).
    """
    start_local = datetime(saturday.year, saturday.month, saturday.day, tzinfo=UK_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def is_saturday_kickoff(kickoff_utc: datetime) -> bool:
    """True when the kick-off is 15:00 on a Saturday in UK local time."""
    local = as_utc(kickoff_utc).astimezone(UK_TZ)
    return local.weekday() == SATURDAY and local.hour == KICKOFF_HOUR and local.minute == 0


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

    Three domain operations plus a session lifecycle. Providers authenticated by an API
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
    async def fetch_slate(self, saturday: date) -> Slate:
        """Return that Saturday's British 15:00 kick-offs."""

    @abstractmethod
    async def fetch_odds(self, event_ids: Sequence[str]) -> list[FixtureOdds]:
        """Snapshot the priced Match Odds + BTTS selections for the given events."""

    @abstractmethod
    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        """Report the final result of each event, in market/outcome terms."""
