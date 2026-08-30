"""One definition of "a date inside the season being played", for tests that seed rounds.

Batch 96 gave the standings table a season boundary, and in doing so turned every
``date.today() - timedelta(days=N)`` in this suite into a date that is in the current
season for most of the year and in the *previous* one for the first weeks of July. A test
that seeds "eight weeks ago", settles it and reads the live table would then pass or fail
by the day it happened to be run — which is worse than a test that is simply wrong,
because it is one that is wrong for a fortnight each summer and right again afterwards.

Two shapes, for the two ways a test can be pinned to the calendar:

* :func:`season_anchor` for rounds seeded relative to *now*. It hands back a day with
  room behind it for the whole run, so the boundary never falls in the middle of one.
* :func:`season_week` for rounds at fixed offsets, which used to be written against a
  hard-coded year and stopped meaning "this season" the moment that year passed.

Tests pinned to canned provider data on a fixed date — ``SAMPLE_SATURDAY``, the August
2026 backfill — do neither, and instead name the season that data belongs to when they
read a table. Their dates are the point of those tests and must not move.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.services.football_provider import current_season
from src.services.gameweek import season_bounds


def season_anchor(*, days_of_room: int) -> date:
    """A day in the season being played with ``days_of_room`` days of it behind them.

    Ordinarily today, which is what these tests meant by "N days ago" before there was a
    boundary to fall over. Only in the opening weeks of a season — when today does not
    have that many days of season behind it — does the anchor move forward, and then just
    far enough that the whole run still lands inside one season.

    A settled round dated slightly ahead of today is harmless in the window where that
    happens: the aggregate selects on the round's *status*, never on whether its date has
    passed.
    """
    first_day, last_day = season_bounds(current_season())
    anchor = max(date.today(), first_day + timedelta(days=days_of_room))
    assert anchor <= last_day, "a season is longer than any run a test seeds"
    return anchor


def season_week(week: int, *, season: int | None = None) -> date:
    """The day ``week`` weeks into a season — by default the one being played.

    For fixtures written as "round 0, round 1, round 2": the offsets are what the test
    cares about and the year is not, so the year should not have been written down.
    """
    first_day, last_day = season_bounds(current_season() if season is None else season)
    day = first_day + timedelta(weeks=week)
    assert first_day <= day <= last_day, "a seeded round must stay inside the season it names"
    return day


def same_weekday_in_current_season(day: date) -> date:
    """``day`` moved into the season being played, keeping its weekday.

    For the canned slate: ``SAMPLE_SATURDAY`` is a fixed 2026 date because the canned
    catalogues quote that kick-off, so from July 2027 it is a past season and a test
    reading figures back off the live leaderboard would start asserting zeroes. The
    weekday is preserved because a league's window is configured for a day of the week —
    a round moved onto a Tuesday is a different fixture entirely.
    """
    first_day, last_day = season_bounds(current_season())
    if first_day <= day <= last_day:
        return day
    # The second such weekday of the season: far enough in that a round seeded a week
    # earlier, as some tests do, is still inside it.
    ahead = (day.weekday() - first_day.weekday()) % 7
    return first_day + timedelta(days=ahead + 7)
