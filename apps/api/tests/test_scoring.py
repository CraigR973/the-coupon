"""Pure scoring maths and settlement mapping (no database).

The ``round(odds × 10)`` points rule and the MarketSettlement→pick resolution are the
headline correctness of Batch 3, so they're unit-tested directly here; ``settle_gameweek``
and ``standings`` are exercised over real Postgres in ``test_picks_flow.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.models.pick import PickStatus
from src.services.betfair import MarketSettlement, RunnerSettlement
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
        (Decimal("1000.00"), 10000),  # a Betfair long shot
    ],
)
def test_points_for(odds: Decimal, expected: int) -> None:
    assert points_for(odds) == expected


# ── resolve_pick: map a settlement to (status, points) ────────────────────────


def _settlement(
    *, settled: bool, winners: list[int], runners: list[tuple[int, str]]
) -> MarketSettlement:
    return MarketSettlement(
        betfair_market_id="1.123",
        status="CLOSED" if settled else "OPEN",
        settled=settled,
        winners=winners,
        runners=[
            RunnerSettlement(betfair_selection_id=sel, status=st, won=(sel in winners))
            for sel, st in runners
        ],
    )


def test_resolve_pending_when_market_not_settled() -> None:
    s = _settlement(settled=False, winners=[], runners=[(1001, "ACTIVE")])
    assert resolve_pick(1001, Decimal("1.90"), s) is None


def test_resolve_won_scores_odds_times_ten() -> None:
    s = _settlement(settled=True, winners=[1001], runners=[(1001, "WINNER"), (1002, "LOSER")])
    result = resolve_pick(1001, Decimal("1.90"), s)
    assert result is not None
    assert result.status is PickStatus.won
    assert result.points == 19


def test_resolve_lost_scores_zero() -> None:
    s = _settlement(settled=True, winners=[1001], runners=[(1001, "WINNER"), (1002, "LOSER")])
    result = resolve_pick(1002, Decimal("4.30"), s)
    assert result is not None
    assert result.status is PickStatus.lost
    assert result.points == 0


def test_resolve_removed_runner_is_void() -> None:
    s = _settlement(settled=True, winners=[1001], runners=[(1001, "WINNER"), (1002, "REMOVED")])
    result = resolve_pick(1002, Decimal("4.30"), s)
    assert result is not None
    assert result.status is PickStatus.void
    assert result.points == 0


def test_resolve_absent_selection_is_void() -> None:
    # Selection vanished from the closed market (e.g. withdrawn) → void, not a loss.
    s = _settlement(settled=True, winners=[1001], runners=[(1001, "WINNER")])
    result = resolve_pick(9999, Decimal("2.50"), s)
    assert result is not None
    assert result.status is PickStatus.void
    assert result.points == 0


# ── enum parity: the Pick model's market/outcome mirror Betfair's ─────────────


def test_pick_enums_mirror_betfair_values() -> None:
    from src.models.pick import PickMarket, PickOutcome
    from src.services.betfair import Market, Outcome

    assert {m.value for m in PickMarket} == {m.value for m in Market}
    assert {o.value for o in PickOutcome} == {o.value for o in Outcome}
