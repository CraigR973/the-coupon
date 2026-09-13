"""Deployment-wide football weeks and the calendar site admins control.

The league-owned ``Gameweek.number`` remains an internal ordinal. Public labels are
derived in bulk from one stored anchor per season, so a Friday league and a Saturday
league call the same Wednesday-to-Tuesday football week the same thing.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.pick import Pick
from src.models.season_calendar import SeasonCalendar
from src.services.football_provider import season_for


def season_bounds(season: int) -> tuple[date, date]:
    """The first and last dates of a season, named by its starting year."""
    return date(season, 7, 1), date(season + 1, 6, 30)


def season_label(season: int) -> str:
    """How season ``2026`` is written on a screen: ``2026/27``."""
    return f"{season}/{(season + 1) % 100:02d}"


def canonical_saturday(day: date) -> date:
    """The Saturday at the centre of ``day``'s Wednesday-to-Tuesday football week."""
    since_wednesday = (day.weekday() - 2) % 7
    return day - timedelta(days=since_wednesday) + timedelta(days=3)


def week_number(anchor: date, day: date) -> int:
    """The anchored football-week number for ``day``, clamped at week 1."""
    return max(1, ((canonical_saturday(day) - anchor).days // 7) + 1)


def _suffix(ordinal: int) -> str:
    if ordinal <= 1:
        return ""
    value = ordinal
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("a") + remainder) + letters
    return letters


def format_week(number: int, ordinal: int = 1) -> str:
    """The API value a client prefixes with ``Gameweek``: ``6`` or ``6b``."""
    return f"{number}{_suffix(ordinal)}"


def _occurrence(calendar: SeasonCalendar, day: date) -> date:
    return day if day in set(calendar.extra_weeks) else canonical_saturday(day)


def labels_for_dates(calendar: SeasonCalendar, round_dates: Collection[date]) -> dict[date, str]:
    """Public week values for dates in one season.

    The canonical Saturday is the regular occurrence. Declared extra dates join it in
    chronological order, so an extra Wednesday is the bare number and the weekend is
    ``b``; an extra Sunday is ``b``. Dates before a stored anchor stay in week 1 and are
    separated the same way rather than moving the anchor.
    """
    dates = set(round_dates)
    numbers = {day: week_number(calendar.week_one_anchor, day) for day in dates}
    occurrences: dict[int, set[date]] = {}

    for number in set(numbers.values()):
        occurrences.setdefault(number, set()).add(
            calendar.week_one_anchor + timedelta(weeks=number - 1)
        )
    for extra in calendar.extra_weeks:
        number = week_number(calendar.week_one_anchor, extra)
        occurrences.setdefault(number, set()).add(extra)
        occurrences[number].add(calendar.week_one_anchor + timedelta(weeks=number - 1))
    for day, number in numbers.items():
        occurrences.setdefault(number, set()).add(_occurrence(calendar, day))

    ordinals = {
        (number, occurrence): ordinal
        for number, values in occurrences.items()
        for ordinal, occurrence in enumerate(sorted(values), start=1)
    }
    return {
        day: format_week(numbers[day], ordinals[(numbers[day], _occurrence(calendar, day))])
        for day in dates
    }


async def calendar_for(db: AsyncSession, season: int) -> SeasonCalendar | None:
    return await db.get(SeasonCalendar, season)


async def ensure_calendar_for_new_season(
    db: AsyncSession, starts_on: date
) -> SeasonCalendar | None:
    """Create a future season's first calendar, but never guess over legacy history.

    Batch 113 ships the production backfill as a separate owner action. If a season
    already has rounds and no calendar, silently anchoring it from a later discovery run
    would perform that action through the scheduler. Only a genuinely empty season may
    establish itself here, after ``sync_slate`` has already proved the new round playable.
    """
    season = season_for(starts_on)
    existing = await calendar_for(db, season)
    if existing is not None:
        return existing
    first_day, last_day = season_bounds(season)
    count = await db.scalar(
        select(func.count())
        .select_from(Gameweek)
        .where(Gameweek.starts_on >= first_day, Gameweek.starts_on <= last_day)
    )
    if count:
        return None
    await db.execute(
        insert(SeasonCalendar)
        .values(season=season, week_one_anchor=canonical_saturday(starts_on), extra_weeks=[])
        .on_conflict_do_nothing(index_elements=[SeasonCalendar.season])
    )
    await db.flush()
    return await calendar_for(db, season)


async def labels_for_gameweeks(db: AsyncSession, gameweeks: Sequence[Any]) -> dict[uuid.UUID, str]:
    """Public labels for a response's rounds, derived without an N+1 query."""
    if not gameweeks:
        return {}
    wanted_seasons = {season_for(gameweek.starts_on) for gameweek in gameweeks}
    rows = await db.execute(select(SeasonCalendar).where(SeasonCalendar.season.in_(wanted_seasons)))
    calendars = {calendar.season: calendar for calendar in rows.scalars().all()}
    if not calendars:
        return {}

    clauses = [
        and_(
            Gameweek.starts_on >= season_bounds(season)[0],
            Gameweek.starts_on <= season_bounds(season)[1],
        )
        for season in calendars
    ]
    deployment_rows = (await db.execute(select(Gameweek).where(or_(*clauses)))).scalars().all()
    dates_by_season: dict[int, set[date]] = {season: set() for season in calendars}
    for gameweek in deployment_rows:
        season = season_for(gameweek.starts_on)
        if season in dates_by_season:
            dates_by_season[season].add(gameweek.starts_on)
    labels = {
        season: labels_for_dates(calendar, dates_by_season[season])
        for season, calendar in calendars.items()
    }
    return {
        gameweek.id: labels[season][gameweek.starts_on]
        for gameweek in gameweeks
        if (season := season_for(gameweek.starts_on)) in labels
        and gameweek.starts_on in labels[season]
    }


async def extra_weeks_between(db: AsyncSession, first: date, last: date) -> set[date]:
    """Every declared global extra date inside an inclusive discovery horizon."""
    seasons = range(season_for(first), season_for(last) + 1)
    rows = await db.execute(select(SeasonCalendar).where(SeasonCalendar.season.in_(seasons)))
    return {
        extra
        for calendar in rows.scalars().all()
        for extra in calendar.extra_weeks
        if first <= extra <= last
    }


@dataclass(frozen=True)
class CalendarWeek:
    starts_on: date
    label: str
    is_extra: bool


def listed_weeks(calendar: SeasonCalendar) -> list[CalendarWeek]:
    """The season calendar as the admin console reads it."""
    _first, last = season_bounds(calendar.season)
    canonical: list[date] = []
    cursor = calendar.week_one_anchor
    while cursor <= last:
        canonical.append(cursor)
        cursor += timedelta(weeks=1)
    extras = set(calendar.extra_weeks)
    values = set(canonical) | extras
    labels = labels_for_dates(calendar, values)
    return [
        CalendarWeek(starts_on=day, label=labels[day], is_extra=day in extras)
        for day in sorted(values)
    ]


async def move_anchor(db: AsyncSession, season: int, anchor: date) -> SeasonCalendar:
    """Move an unsettled season's anchor; settled history makes it immutable."""
    if anchor.weekday() != 5 or season_for(anchor) != season:
        raise ValueError("ANCHOR_MUST_BE_A_SATURDAY_IN_SEASON")
    calendar = (
        await db.execute(
            select(SeasonCalendar).where(SeasonCalendar.season == season).with_for_update()
        )
    ).scalar_one_or_none()
    if calendar is None:
        first_day, last_day = season_bounds(season)
        has_rounds = await db.scalar(
            select(func.count())
            .select_from(Gameweek)
            .where(Gameweek.starts_on >= first_day, Gameweek.starts_on <= last_day)
        )
        if has_rounds:
            raise LookupError("SEASON_CALENDAR_REQUIRES_BACKFILL")
        calendar = SeasonCalendar(season=season, week_one_anchor=anchor, extra_weeks=[])
        db.add(calendar)
        await db.flush()
        return calendar
    if calendar.week_one_anchor == anchor:
        return calendar
    first_day, last_day = season_bounds(season)
    settled = await db.scalar(
        select(func.count())
        .select_from(Gameweek)
        .where(
            Gameweek.starts_on >= first_day,
            Gameweek.starts_on <= last_day,
            Gameweek.status == GameweekStatus.settled,
        )
    )
    if settled:
        raise PermissionError("SEASON_ANCHOR_LOCKED")
    calendar.week_one_anchor = anchor
    await db.flush()
    return calendar


async def declare_extra_week(db: AsyncSession, season: int, starts_on: date) -> SeasonCalendar:
    if season_for(starts_on) != season:
        raise ValueError("EXTRA_WEEK_OUTSIDE_SEASON")
    calendar = (
        await db.execute(
            select(SeasonCalendar).where(SeasonCalendar.season == season).with_for_update()
        )
    ).scalar_one_or_none()
    if calendar is None:
        raise LookupError("SEASON_CALENDAR_NOT_FOUND")
    canonical_dates = {week.starts_on for week in listed_weeks(calendar) if not week.is_extra}
    if starts_on in canonical_dates:
        raise ValueError("EXTRA_WEEK_IS_ALREADY_CANONICAL")
    calendar.extra_weeks = sorted(set(calendar.extra_weeks) | {starts_on})
    await db.flush()
    return calendar


async def withdraw_extra_week(db: AsyncSession, season: int, starts_on: date) -> SeasonCalendar:
    calendar = (
        await db.execute(
            select(SeasonCalendar).where(SeasonCalendar.season == season).with_for_update()
        )
    ).scalar_one_or_none()
    if calendar is None:
        raise LookupError("SEASON_CALENDAR_NOT_FOUND")
    if starts_on not in calendar.extra_weeks:
        raise LookupError("EXTRA_WEEK_NOT_FOUND")
    pick_exists = await db.scalar(
        select(func.count())
        .select_from(Gameweek)
        .join(Pick, Pick.gameweek_id == Gameweek.id)
        .where(Gameweek.starts_on == starts_on)
    )
    if pick_exists:
        raise PermissionError("EXTRA_WEEK_HAS_PICKS")
    calendar.extra_weeks = [day for day in calendar.extra_weeks if day != starts_on]
    await db.flush()
    return calendar
