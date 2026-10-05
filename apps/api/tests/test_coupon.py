"""Pure combined-accumulator maths (no database).

The combined coupon price is the product of every leg's frozen odds. ``build_coupon``
(the DB assembly) is covered in ``test_picks_flow.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.models.pick import PickStatus
from src.services.coupon import accumulator, combined_odds


def test_combined_odds_is_the_product_to_two_dp() -> None:
    # 1.90 × 1.95 × 2.40 = 8.892 → 8.89
    assert combined_odds([Decimal("1.90"), Decimal("1.95"), Decimal("2.40")]) == Decimal("8.89")


def test_combined_odds_single_leg() -> None:
    assert combined_odds([Decimal("4.30")]) == Decimal("4.30")


def test_combined_odds_empty_is_one() -> None:
    assert combined_odds([]) == Decimal("1.00")


def test_combined_odds_keeps_every_cent_past_the_default_context() -> None:
    assert combined_odds([Decimal("3.32")] * 50) == Decimal("113999825143316519753879208.99")


@pytest.mark.parametrize(
    ("odds", "expected"),
    [
        ([Decimal("2.40"), Decimal("4.30"), Decimal("1.90")], Decimal("19.61")),  # 19.608
        ([Decimal("1.50"), Decimal("1.50")], Decimal("2.25")),
    ],
)
def test_combined_odds_rounds_half_up(odds: list[Decimal], expected: Decimal) -> None:
    assert combined_odds(odds) == expected


def test_the_accumulator_prices_only_the_legs_that_ran() -> None:
    """Batch 186: production's `53.01 = 3.75 x 1.90 x 3.10(void) x 2.40`, priced once."""
    price = accumulator(
        [
            (Decimal("3.75"), PickStatus.won),
            (Decimal("1.90"), PickStatus.lost),
            (Decimal("3.10"), PickStatus.void),
            (Decimal("2.40"), PickStatus.void),
        ]
    )

    # 3.75 x 1.90 = 7.125 -> 7.13, half up; the two voids are counted, not multiplied.
    assert (price.combined_odds, price.void_leg_count) == (Decimal("7.13"), 2)


def test_an_accumulator_of_pending_legs_prices_every_one() -> None:
    """Only void leaves the product: a leg still to play is part of the bet."""
    price = accumulator([(Decimal("2.00"), PickStatus.pending), (Decimal("1.50"), PickStatus.won)])

    assert (price.combined_odds, price.void_leg_count) == (Decimal("3.00"), 0)
