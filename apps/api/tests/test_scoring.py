"""Pure scoring maths and settlement mapping (no database).

The ``round(odds × 10)`` points rule and the EventSettlement→pick resolution are the
headline correctness of the scoring path, so they're unit-tested directly here;
``settle_gameweek`` and ``standings`` are exercised over real Postgres in
``test_picks_flow.py``.

A pick resolves on ``(market, outcome)`` against its fixture's settlement. Before ADR 0002
it resolved on a Betfair selection id stored on the pick; revision ``005`` dropped that
column because ``(fixture, market, outcome)`` already identifies a selection uniquely and
means the same thing whichever provider priced it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.models.pick import PickMarket, PickOutcome, PickStatus
from src.services.odds_provider import (
    EventSettlement,
    Market,
    Outcome,
    OutcomeResult,
    outcomes_from_score,
)
from src.services.scoring import points_for, resolve_pick

# ── points_for: round(odds × 10), half-up ─────────────────────────────────────


@pytest.mark.parametrize(
    ("odds", "expected"),
    [
        (Decimal("1.90"), 19),  # exact
        (Decimal("4.30"), 43),
        (Decimal("1.95"), 20),  # 19.5 → up
        (Decimal("2.05"), 21),  # 20.5 → up, NOT banker's-rounding 20
        (Decimal("3.75"), 38),  # 37.5 → up
        (Decimal("1.01"), 10),  # 10.1 → down
        (Decimal("1000.00"), 10000),  # a long shot
    ],
)
def test_points_for(odds: Decimal, expected: int) -> None:
    assert points_for(odds) == expected


# ── outcomes_from_score: both markets derived from one final score ────────────
# This is the substance of the migration: Betfair reported a winning runner, odds-api.io
# reports a score, so every result below is arithmetic on two integers.


@pytest.mark.parametrize(
    ("home_goals", "away_goals", "winner", "both_scored"),
    [
        (2, 0, Outcome.HOME, False),  # home win, clean sheet
        (0, 1, Outcome.AWAY, False),  # away win, clean sheet
        (1, 1, Outcome.DRAW, True),  # score draw
        (0, 0, Outcome.DRAW, False),  # goalless draw
        (3, 2, Outcome.HOME, True),  # home win, both scored
        (1, 4, Outcome.AWAY, True),  # away win, both scored
    ],
)
def test_outcomes_from_score(
    home_goals: int, away_goals: int, winner: Outcome, both_scored: bool
) -> None:
    results = {(o.market, o.outcome): o.won for o in outcomes_from_score(home_goals, away_goals)}

    # Exactly one Match Odds outcome wins, and it is the one the score implies.
    match_odds = {o: won for (m, o), won in results.items() if m is Market.MATCH_ODDS}
    assert match_odds == {
        Outcome.HOME: winner is Outcome.HOME,
        Outcome.DRAW: winner is Outcome.DRAW,
        Outcome.AWAY: winner is Outcome.AWAY,
    }

    assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.YES)] is both_scored
    assert results[(Market.BOTH_TEAMS_TO_SCORE, Outcome.NO)] is not both_scored


def test_every_outcome_is_reported_not_just_the_winners() -> None:
    """Losers must be present, or a losing pick would be mistaken for a missing market."""
    results = outcomes_from_score(2, 1)
    assert len(results) == 5  # HOME/DRAW/AWAY + YES/NO
    assert sum(1 for r in results if r.won) == 2  # the home win and BTTS yes


# ── resolve_pick: map a settlement to (status, points) ────────────────────────


def _settled(home_goals: int, away_goals: int) -> EventSettlement:
    return EventSettlement(
        provider_event_id="ev1",
        status="finished",
        settled=True,
        settled_markets=[Market.MATCH_ODDS, Market.BOTH_TEAMS_TO_SCORE],
        outcomes=outcomes_from_score(home_goals, away_goals),
    )


def test_resolve_pending_when_event_not_settled() -> None:
    unsettled = EventSettlement(provider_event_id="ev1", status="pending", settled=False)
    assert resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.HOME, Decimal("1.90"), unsettled) is None


def test_resolve_won_scores_odds_times_ten() -> None:
    result = resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.HOME, Decimal("1.90"), _settled(2, 0))
    assert result is not None
    assert result.status is PickStatus.won
    assert result.points == 19


def test_resolve_lost_scores_zero() -> None:
    result = resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.AWAY, Decimal("4.30"), _settled(2, 0))
    assert result is not None
    assert result.status is PickStatus.lost
    assert result.points == 0


def test_resolve_btts_yes_when_both_scored() -> None:
    result = resolve_pick(
        PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES, Decimal("1.75"), _settled(2, 1)
    )
    assert result is not None
    assert result.status is PickStatus.won
    assert result.points == 18  # 17.5 → up


def test_resolve_btts_no_on_a_clean_sheet() -> None:
    result = resolve_pick(
        PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.NO, Decimal("2.05"), _settled(3, 0)
    )
    assert result is not None
    assert result.status is PickStatus.won
    assert result.points == 21


def test_resolve_postponed_fixture_is_void() -> None:
    """A postponed or abandoned fixture voids every pick on it — it is not a loss."""
    voided = EventSettlement(provider_event_id="ev1", status="postponed", settled=True, void=True)
    result = resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.HOME, Decimal("1.90"), voided)
    assert result is not None
    assert result.status is PickStatus.void
    assert result.points == 0


def test_resolve_pending_when_only_the_other_market_settled() -> None:
    """A half-settled fixture must leave the unsettled market's picks pending, not void."""
    partial = EventSettlement(
        provider_event_id="ev1",
        status="CLOSED",
        settled=True,
        settled_markets=[Market.MATCH_ODDS],
        outcomes=[
            OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.HOME, won=True),
            OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.AWAY, won=False),
        ],
    )
    assert (
        resolve_pick(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES, Decimal("1.80"), partial)
        is None
    )
    won = resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.HOME, Decimal("1.90"), partial)
    assert won is not None and won.status is PickStatus.won


def test_resolve_absent_outcome_in_a_settled_market_is_void() -> None:
    """A selection withdrawn from a settled market → void, not a loss."""
    withdrawn = EventSettlement(
        provider_event_id="ev1",
        status="CLOSED",
        settled=True,
        settled_markets=[Market.MATCH_ODDS],
        outcomes=[OutcomeResult(market=Market.MATCH_ODDS, outcome=Outcome.HOME, won=True)],
    )
    result = resolve_pick(PickMarket.MATCH_ODDS, PickOutcome.DRAW, Decimal("2.50"), withdrawn)
    assert result is not None
    assert result.status is PickStatus.void
    assert result.points == 0


# ── enum parity: the Pick model's market/outcome mirror the port's ────────────


def test_pick_enums_mirror_provider_values() -> None:
    assert {m.value for m in PickMarket} == {m.value for m in Market}
    assert {o.value for o in PickOutcome} == {o.value for o in Outcome}
