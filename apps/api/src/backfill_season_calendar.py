"""Preview or apply deployment-wide season calendars (Batch 113).

The migration creates an empty ``season_calendars`` table. This script is the explicit
owner action that turns the current per-league names into one deployment-wide football
calendar. Its first run must be ``--dry-run``: every visible move is printed with league,
date and old/new Gameweek labels, and no row is written. ``--apply`` stores only the
season anchors; ``Gameweek.number``, picks, settlement and points are untouched.

Run with::

    python -m src.backfill_season_calendar --dry-run
    python -m src.backfill_season_calendar --apply
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.pick import Pick
from src.models.season_calendar import SeasonCalendar
from src.services.football_provider import season_for
from src.services.season_calendar import canonical_saturday, labels_for_dates


class BackfillError(RuntimeError):
    """The stored rounds do not admit one unambiguous calendar."""


@dataclass(frozen=True)
class CalendarChange:
    season: int
    anchor: date
    already_stored: bool


@dataclass(frozen=True)
class RoundChange:
    league: str
    starts_on: date
    was: str
    now: str
    pick_count: int

    @property
    def changing(self) -> bool:
        return self.was != self.now


async def plan(db: AsyncSession) -> tuple[list[CalendarChange], list[RoundChange]]:
    rows = (
        await db.execute(
            select(Gameweek, League.name, func.count(Pick.id))
            .join(League, League.id == Gameweek.league_id)
            .outerjoin(Pick, Pick.gameweek_id == Gameweek.id)
            .group_by(Gameweek.id, League.name)
            .order_by(Gameweek.starts_on, League.name)
        )
    ).all()
    if not rows:
        raise BackfillError("no rounds exist; there is no season anchor to derive")

    by_season: dict[int, list[tuple[Gameweek, str, int]]] = {}
    for gameweek, league_name, pick_count in rows:
        by_season.setdefault(season_for(gameweek.starts_on), []).append(
            (gameweek, league_name, pick_count)
        )

    calendars: list[CalendarChange] = []
    round_changes: list[RoundChange] = []
    for season, season_rows in sorted(by_season.items()):
        stored = await db.get(SeasonCalendar, season)
        anchor = (
            stored.week_one_anchor
            if stored is not None
            else min(canonical_saturday(gameweek.starts_on) for gameweek, _, _ in season_rows)
        )
        calendar = stored or SeasonCalendar(
            season=season,
            week_one_anchor=anchor,
            extra_weeks=[],
        )
        calendars.append(
            CalendarChange(season=season, anchor=anchor, already_stored=stored is not None)
        )
        labels = labels_for_dates(calendar, {gameweek.starts_on for gameweek, _, _ in season_rows})
        for gameweek, league_name, pick_count in season_rows:
            now = labels[gameweek.starts_on]
            was = (
                now
                if stored is not None
                else (
                    str(gameweek.number)
                    if gameweek.number is not None
                    else gameweek.starts_on.isoformat()
                )
            )
            round_changes.append(
                RoundChange(
                    league=league_name,
                    starts_on=gameweek.starts_on,
                    was=was,
                    now=now,
                    pick_count=pick_count,
                )
            )
    return calendars, round_changes


async def apply(db: AsyncSession) -> tuple[list[CalendarChange], list[RoundChange]]:
    calendars, rounds = await plan(db)
    for change in calendars:
        if change.already_stored:
            continue
        db.add(
            SeasonCalendar(
                season=change.season,
                week_one_anchor=change.anchor,
                extra_weeks=[],
            )
        )
    await db.flush()

    for change in calendars:
        stored = await db.get(SeasonCalendar, change.season)
        if stored is None or stored.week_one_anchor != change.anchor:
            raise BackfillError(f"season {change.season} did not store anchor {change.anchor}")
    return calendars, rounds


def _describe(calendars: list[CalendarChange], rounds: list[RoundChange]) -> str:
    lines = ["season calendars:"]
    for calendar in calendars:
        verb = "already stored" if calendar.already_stored else "would store"
        lines.append(f"    {calendar.season}: week 1 = {calendar.anchor} ({verb})")
    lines.append("round labels that move:")
    moving = [round_change for round_change in rounds if round_change.changing]
    if not moving:
        lines.append("    none")
    for round_change in moving:
        played = f", {round_change.pick_count} pick(s)" if round_change.pick_count else ""
        lines.append(
            f"    {round_change.league} · {round_change.starts_on}: "
            f"was Gameweek {round_change.was} -> now Gameweek {round_change.now}{played}"
        )
    lines.append(f"unchanged round labels: {len(rounds) - len(moving)}")
    return "\n".join(lines)


async def _run(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not apply_changes:
            calendars, rounds = await plan(db)
            print(_describe(calendars, rounds))
            print("\nDRY RUN — nothing written.")
            return
        calendars, rounds = await apply(db)
        await db.commit()
        print(_describe(calendars, rounds))
        print(f"\nAPPLIED at {datetime.now(UTC).isoformat()}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report every move; write nothing")
    group.add_argument("--apply", action="store_true", help="store the season calendar")
    args = parser.parse_args()
    asyncio.run(_run(apply_changes=bool(args.apply)))


if __name__ == "__main__":
    main()
