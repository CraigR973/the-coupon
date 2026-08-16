"""The slate window and the round helpers built on it (no DB).

Batch 14 replaced the Saturday-15:00 constants with a per-league
:class:`~src.services.odds_provider.SlateWindow`. These tests pin both ends of
that: that the default window still describes exactly the game the product
shipped with, and that a window spanning several days behaves sensibly.

Batch 27 added the other end of the claim period — when picks *open* — so they
also pin how that instant is derived, that it stays out of the window's identity
(and therefore out of the provider's request budget), and which of the two
refusals a round gives at each point in its life.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.services.gameweek import (
    initial_status,
    pick_refusal,
    picks_open_at,
    slate_odds_max_age,
    upcoming_slate_dates,
    window_for,
)
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


@pytest.mark.parametrize(
    "status", [GameweekStatus.scheduled, GameweekStatus.locked, GameweekStatus.settled]
)
def test_a_gameweek_that_is_not_open_gets_the_loosest_tier(status: GameweekStatus) -> None:
    """Nothing can move a frozen price, and nobody can freeze one before picks open."""
    now = datetime(2026, 8, 8, 0, 0)
    gameweek = _gameweek(status, now + timedelta(hours=1))
    assert slate_odds_max_age(gameweek, now, near_ttl=900.0, far_ttl=3600.0) == 3600.0


# ── When picks open (Batch 27) ───────────────────────────────────────────────

#: A week, in minutes — picks open as the *previous* week's window does.
A_WEEK = 7 * 24 * 60


def _league(**overrides: object) -> League:
    """A league carrying only the window columns these tests read."""
    return League(
        slate_start_weekday=SATURDAY,
        slate_start_minute=15 * 60,
        slate_end_weekday=SATURDAY,
        slate_end_minute=15 * 60,
        lock_offset_minutes=30,
        **overrides,
    )


def test_an_unconfigured_league_announces_no_opening() -> None:
    """The pre-Batch-27 rule: a round is claimable as soon as it is published."""
    assert picks_open_at(_league(pick_open_offset_minutes=None), date(2026, 8, 8)) is None


def test_picks_open_a_week_before_the_window_on_the_same_clock() -> None:
    """A week before Saturday 15:00 BST is the previous Saturday 15:00 — 14:00Z."""
    opens = picks_open_at(_league(pick_open_offset_minutes=A_WEEK), date(2026, 8, 8))
    assert opens == datetime(2026, 8, 1, 14, 0)


def test_the_pick_open_instant_tracks_bst_and_gmt() -> None:
    """Anchored in Europe/London, so December is an hour later in UTC than August."""
    december = picks_open_at(_league(pick_open_offset_minutes=A_WEEK), date(2026, 12, 12))
    assert december == datetime(2026, 12, 5, 15, 0)


def test_the_pick_open_offset_is_not_part_of_the_window_identity() -> None:
    """Two leagues differing only in when picks open must still share one fetch.

    ``discover_fixtures`` groups leagues by :class:`SlateWindow`, so a pick-open offset
    that reached the window would multiply the provider bill by the number of distinct
    announcements — the request budget under a configuration knob, which Batch 27 is
    explicitly not allowed to do.
    """
    early = window_for(_league(pick_open_offset_minutes=A_WEEK))
    late = window_for(_league(pick_open_offset_minutes=60))
    assert early == late
    assert len({early, late}) == 1


# ── The claim period, both ends ──────────────────────────────────────────────

NOW = datetime(2026, 8, 8, 12, 0)


def _round(
    status: GameweekStatus,
    *,
    locks_at: datetime,
    opens_at: datetime | None = None,
) -> Gameweek:
    return Gameweek(
        starts_on=locks_at.date(),
        status=status,
        locks_at_utc=locks_at,
        picks_open_at_utc=opens_at,
    )


@pytest.mark.parametrize(
    ("status", "opens_at", "expected"),
    [
        # No announced opening — unchanged from before the batch.
        (GameweekStatus.open, None, None),
        # Announced and passed: accepted, whatever the label says.
        (GameweekStatus.open, NOW - timedelta(minutes=1), None),
        (GameweekStatus.scheduled, NOW - timedelta(minutes=1), None),
        # Announced and still ahead: refused as *not yet*, not as over.
        (GameweekStatus.scheduled, NOW + timedelta(minutes=1), "PICKS_NOT_OPEN"),
        (GameweekStatus.open, NOW + timedelta(minutes=1), "PICKS_NOT_OPEN"),
        # Exactly on the instant counts as open — the announcement is a start, not a gap.
        (GameweekStatus.scheduled, NOW, None),
    ],
)
def test_the_opening_end_of_the_claim_period(
    status: GameweekStatus, opens_at: datetime | None, expected: str | None
) -> None:
    """Time decides, and ``status`` only says which rounds settlement has finished with.

    A ``scheduled`` round whose instant has passed must be accepted before the hourly
    open job relabels it, exactly as an ``open`` round past its lock is refused before
    the lock job does.
    """
    gameweek = _round(status, locks_at=NOW + timedelta(hours=2), opens_at=opens_at)
    assert pick_refusal(gameweek, NOW) == expected


@pytest.mark.parametrize("status", [GameweekStatus.locked, GameweekStatus.settled])
def test_a_finished_round_is_locked_not_unopened(status: GameweekStatus) -> None:
    """Even with an opening still ahead — a settled round is over, not pending."""
    gameweek = _round(
        status, locks_at=NOW + timedelta(hours=2), opens_at=NOW + timedelta(minutes=1)
    )
    assert pick_refusal(gameweek, NOW) == "PICKS_LOCKED"


def test_the_deadline_still_wins_over_an_opening_that_has_passed() -> None:
    gameweek = _round(
        GameweekStatus.open, locks_at=NOW - timedelta(minutes=1), opens_at=NOW - timedelta(days=7)
    )
    assert pick_refusal(gameweek, NOW) == "PICKS_LOCKED"


# ── The state a round is discovered in ───────────────────────────────────────


def test_a_round_discovered_before_its_opening_starts_scheduled() -> None:
    assert initial_status(NOW + timedelta(days=1), NOW) is GameweekStatus.scheduled


@pytest.mark.parametrize(
    "opens_at",
    [
        None,  # no announcement at all
        NOW - timedelta(minutes=1),  # an ad-hoc round created after its own opening
        NOW,
    ],
)
def test_a_round_that_is_already_claimable_starts_open(opens_at: datetime | None) -> None:
    """Otherwise the badge would read "not open" while the endpoint accepted picks."""
    assert initial_status(opens_at, NOW) is GameweekStatus.open
