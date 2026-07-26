"""Pure-function tests for gameweek date helpers (no DB)."""

from __future__ import annotations

from datetime import date

import pytest

from src.services.gameweek import compute_locks_at, upcoming_saturday


@pytest.mark.parametrize(
    "today",
    [
        date(2026, 7, 27),  # Monday
        date(2026, 7, 29),  # Wednesday
        date(2026, 7, 31),  # Friday
        date(2026, 8, 1),  # Saturday
        date(2026, 8, 2),  # Sunday
    ],
)
def test_upcoming_saturday_is_the_nearest_saturday_on_or_after(today: date) -> None:
    result = upcoming_saturday(today)
    assert result.weekday() == 5  # a Saturday
    assert result >= today  # never in the past
    assert (result - today).days < 7  # the nearest one


def test_upcoming_saturday_returns_same_day_on_a_saturday() -> None:
    saturday = date(2026, 8, 1)
    assert saturday.weekday() == 5
    assert upcoming_saturday(saturday) == saturday


def test_compute_locks_at_tracks_bst_and_gmt() -> None:
    """14:30 UK is 13:30Z in summer (BST) and 14:30Z in winter (GMT)."""
    august = compute_locks_at(date(2026, 8, 1))  # BST (UTC+1)
    assert (august.hour, august.minute) == (13, 30)
    december = compute_locks_at(date(2026, 12, 5))  # GMT (UTC+0)
    assert (december.hour, december.minute) == (14, 30)
