"""Pure combined-accumulator maths (no database).

The combined coupon price is the product of every leg's frozen odds. ``build_coupon``
(the DB assembly) is covered in ``test_picks_flow.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.services.coupon import combined_odds


def test_combined_odds_is_the_product_to_two_dp() -> None:
    # 1.90 × 1.95 × 2.40 = 8.892 → 8.89
    assert combined_odds([Decimal("1.90"), Decimal("1.95"), Decimal("2.40")]) == Decimal("8.89")


def test_combined_odds_single_leg() -> None:
    assert combined_odds([Decimal("4.30")]) == Decimal("4.30")


def test_combined_odds_empty_is_one() -> None:
    assert combined_odds([]) == Decimal("1.00")


@pytest.mark.parametrize(
    ("odds", "expected"),
    [
        ([Decimal("2.40"), Decimal("4.30"), Decimal("1.90")], Decimal("19.61")),  # 19.608
        ([Decimal("1.50"), Decimal("1.50")], Decimal("2.25")),
    ],
)
def test_combined_odds_rounds_half_up(odds: list[Decimal], expected: Decimal) -> None:
    assert combined_odds(odds) == expected
