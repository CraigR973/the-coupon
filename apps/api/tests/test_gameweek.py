"""Pure-function tests for gameweek date helpers (no DB)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.models.gameweek import Gameweek, GameweekStatus
from src.services.gameweek import (
    compute_locks_at,
    slate_odds_max_age,
    upcoming_saturday,
    upcoming_saturdays,
)


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


# ── Batch 11: discovery horizon and the browse-price freshness tiers ──────────


def test_upcoming_saturdays_walks_forward_a_week_at_a_time() -> None:
    wednesday = date(2026, 8, 5)
    assert upcoming_saturdays(wednesday, 3) == [
        date(2026, 8, 8),
        date(2026, 8, 15),
        date(2026, 8, 22),
    ]


def test_upcoming_saturdays_starts_from_today_on_a_saturday() -> None:
    saturday = date(2026, 8, 8)
    assert upcoming_saturdays(saturday, 2) == [date(2026, 8, 8), date(2026, 8, 15)]


@pytest.mark.parametrize("count", [0, -1])
def test_upcoming_saturdays_always_yields_at_least_one(count: int) -> None:
    """A misconfigured horizon must still discover this Saturday, not nothing."""
    assert upcoming_saturdays(date(2026, 8, 5), count) == [date(2026, 8, 8)]


def _gameweek(status: GameweekStatus, locks_at: datetime) -> Gameweek:
    return Gameweek(saturday_date=locks_at.date(), status=status, locks_at_utc=locks_at)


@pytest.mark.parametrize(
    ("hours_to_lock", "expected"),
    [
        (72, 3600.0),  # midweek — an hour-old price is fine to browse
        (25, 3600.0),
        (23, 1800.0),  # the day before
        (7, 1800.0),
        (5, 900.0),  # match morning
        (0.25, 900.0),
        (-1, 900.0),  # past lock but not yet flipped: still the tightest tier
    ],
)
def test_browse_price_freshness_tightens_towards_lock(
    hours_to_lock: float, expected: float
) -> None:
    now = datetime(2026, 8, 8, 0, 0)
    gameweek = _gameweek(GameweekStatus.open, now + timedelta(hours=hours_to_lock))
    assert slate_odds_max_age(gameweek, now, near_ttl=900.0, far_ttl=3600.0) == expected


@pytest.mark.parametrize("status", [GameweekStatus.locked, GameweekStatus.settled])
def test_a_closed_gameweek_gets_the_loosest_tier(status: GameweekStatus) -> None:
    """Nothing can move a frozen price, so re-fetching one buys nothing."""
    now = datetime(2026, 8, 8, 0, 0)
    gameweek = _gameweek(status, now + timedelta(hours=1))
    assert slate_odds_max_age(gameweek, now, near_ttl=900.0, far_ttl=3600.0) == 3600.0
