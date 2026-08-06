"""The slate window and the round helpers built on it (no DB).

Batch 14 replaced the Saturday-15:00 constants with a per-league
:class:`~src.services.odds_provider.SlateWindow`. These tests pin both ends of
that: that the default window still describes exactly the game the product
shipped with, and that a window spanning several days behaves sensibly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.models.gameweek import Gameweek, GameweekStatus
from src.services.gameweek import slate_odds_max_age, upcoming_slate_dates
from src.services.odds_provider import SATURDAY_THREE_PM, SlateWindow

FRIDAY, SATURDAY, SUNDAY, MONDAY = 4, 5, 6, 0

# Friday 19:00 through Monday 22:00 — the arbitrary range Batch 15 offers.
LONG_WEEKEND = SlateWindow(
    start_weekday=FRIDAY,
    start_minute=19 * 60,
    end_weekday=MONDAY,
    end_minute=22 * 60,
    lock_offset_minutes=60,
)


# ── The default window is still the game we shipped ──────────────────────────


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
def test_the_default_window_opens_on_the_nearest_saturday(today: date) -> None:
    result = SATURDAY_THREE_PM.first_start_on_or_after(today)
    assert result.weekday() == SATURDAY
    assert result >= today  # never in the past
    assert (result - today).days < 7  # the nearest one


def test_the_default_window_starts_today_on_a_saturday() -> None:
    """Match-day refreshes must keep updating today's round, not skip a week."""
    saturday = date(2026, 8, 1)
    assert SATURDAY_THREE_PM.first_start_on_or_after(saturday) == saturday


def test_the_default_lock_tracks_bst_and_gmt() -> None:
    """14:30 UK is 13:30Z in summer (BST) and 14:30Z in winter (GMT)."""
    august = SATURDAY_THREE_PM.locks_at(date(2026, 8, 1))  # BST (UTC+1)
    assert (august.hour, august.minute) == (13, 30)
    december = SATURDAY_THREE_PM.locks_at(date(2026, 12, 5))  # GMT (UTC+0)
    assert (december.hour, december.minute) == (14, 30)


@pytest.mark.parametrize(
    ("kickoff_local", "expected"),
    [
        ("2026-08-01T15:00", True),  # the 15:00 Saturday itself
        ("2026-08-01T14:59", False),  # a minute early
        ("2026-08-01T15:01", False),  # a minute late
        ("2026-08-01T12:30", False),  # the lunchtime kick-off
        ("2026-08-02T15:00", False),  # Sunday at the same time
    ],
)
def test_the_default_window_admits_only_the_saturday_three_oclock(
    kickoff_local: str, expected: bool
) -> None:
    """The old ``is_saturday_kickoff`` rule, now expressed as a point range."""
    kickoff = datetime.fromisoformat(kickoff_local).replace(tzinfo=UTC) - timedelta(hours=1)
    assert SATURDAY_THREE_PM.contains(kickoff, date(2026, 8, 1)) is expected


def test_a_point_window_still_queries_a_whole_day() -> None:
    """Providers filter by range, so an instant has to be asked for as a day."""
    start, end = SATURDAY_THREE_PM.query_bounds(date(2026, 8, 1))
    assert (end - start) == timedelta(days=1)
    assert start < SATURDAY_THREE_PM.opens_at(date(2026, 8, 1)) < end


# ── A window spanning several days ───────────────────────────────────────────


def test_a_long_weekend_window_spans_to_the_following_monday() -> None:
    friday = date(2026, 8, 7)
    assert friday.weekday() == FRIDAY
    assert LONG_WEEKEND.span_days == 3
    assert LONG_WEEKEND.closes_at(friday).date() == date(2026, 8, 10)  # the Monday


@pytest.mark.parametrize(
    ("kickoff_local", "expected"),
    [
        ("2026-08-07T19:00", True),  # exactly as it opens
        ("2026-08-07T18:59", False),  # just before
        ("2026-08-08T15:00", True),  # the Saturday in the middle
        ("2026-08-09T20:00", True),  # Sunday evening
        ("2026-08-10T22:00", True),  # exactly as it closes
        ("2026-08-10T22:01", False),  # just after
        ("2026-08-11T19:00", False),  # the Tuesday after
    ],
)
def test_a_long_weekend_window_admits_everything_between_its_ends(
    kickoff_local: str, expected: bool
) -> None:
    kickoff = datetime.fromisoformat(kickoff_local).replace(tzinfo=UTC) - timedelta(hours=1)
    assert LONG_WEEKEND.contains(kickoff, date(2026, 8, 7)) is expected


def test_a_spanning_window_queries_every_day_it_touches() -> None:
    start, end = LONG_WEEKEND.query_bounds(date(2026, 8, 7))
    assert (end - start) == timedelta(days=4), "Friday through Monday inclusive"


def test_the_lock_offset_is_relative_to_the_window_opening() -> None:
    """An hour before Friday 19:00 is Friday 18:00 local, 17:00Z in BST."""
    locks = LONG_WEEKEND.locks_at(date(2026, 8, 7))
    assert (locks.hour, locks.minute) == (17, 0)


# ── The discovery horizon ────────────────────────────────────────────────────


def test_the_horizon_walks_forward_a_week_at_a_time() -> None:
    wednesday = date(2026, 8, 5)
    assert upcoming_slate_dates(wednesday, SATURDAY_THREE_PM, 3) == [
        date(2026, 8, 8),
        date(2026, 8, 15),
        date(2026, 8, 22),
    ]


def test_the_horizon_follows_the_leagues_own_weekday() -> None:
    """A Friday league discovers Fridays, not Saturdays."""
    assert upcoming_slate_dates(date(2026, 8, 5), LONG_WEEKEND, 2) == [
        date(2026, 8, 7),
        date(2026, 8, 14),
    ]


@pytest.mark.parametrize("count", [0, -1])
def test_the_horizon_always_yields_at_least_one(count: int) -> None:
    """A misconfigured horizon must still discover the coming round, not nothing."""
    assert upcoming_slate_dates(date(2026, 8, 5), SATURDAY_THREE_PM, count) == [date(2026, 8, 8)]


# ── Browsed-price freshness (Batch 11), unchanged by the split ───────────────


def _gameweek(status: GameweekStatus, locks_at: datetime) -> Gameweek:
    return Gameweek(starts_on=locks_at.date(), status=status, locks_at_utc=locks_at)


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
