"""Seed the lens-02 world in the scratch DB, then build rounds with the scheduler's own job.

Leagues (deliberately different):
  l1-defaults  Sat 15:00, lock 30, MATCH_ODDS only, selection scope, all UK
  l2-friday    Fri 19:00-22:00, lock 60, both markets, EPL+Championship only, fixture scope
  l3-race-sel  defaults, selection scope, 12 race members (concurrency)
  l4-race-fix  defaults but fixture scope, the same 12 race members
Members: Alice (L1 admin, L2), Bob, Carol, Dan (America/New_York, L1+L2),
Erin (Australia/Sydney), Gina (L2 admin), Hank (America/New_York), Ivy (UTC),
R01..R12 (L3+L4), Root (site admin, in no league). PIN 1234 for everyone.

Then `run_discover_fixtures()` (the 06:00 job) with the rich fake behind odds_session.
"""

from __future__ import annotations

import asyncio

import lib  # noqa: F401  (must be first)
from sqlalchemy import select, text

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek
from src.models.league import League, PickMarket, PickScope
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.scheduler import run_discover_fixtures

PIN = hash_pin("1234")

PEOPLE = {
    "Alice": "Europe/London",
    "Bob": "Europe/London",
    "Carol": "Europe/London",
    "Dan": "America/New_York",
    "Erin": "Australia/Sydney",
    "Gina": "Europe/London",
    "Hank": "America/New_York",
    "Ivy": "UTC",
    **{f"R{n:02d}": "Europe/London" for n in range(1, 13)},
}


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE TABLE profiles, leagues, fixtures, season_calendars CASCADE"))
        people = {
            name: Profile(display_name=name, pin_hash=PIN, role=UserRole.player, timezone=tz)
            for name, tz in PEOPLE.items()
        }
        people["Root"] = Profile(display_name="Root", pin_hash=PIN, role=UserRole.admin, timezone="Europe/London")
        db.add_all(people.values())
        await db.flush()

        l1 = League(slug="l1-defaults", name="League One (defaults)", created_by=people["Alice"].id,
                    offered_markets=[PickMarket.MATCH_ODDS], pick_scope=PickScope.selection)
        l2 = League(slug="l2-friday", name="League Two (Friday)", created_by=people["Gina"].id,
                    slate_start_weekday=4, slate_start_minute=19 * 60, slate_end_weekday=4,
                    slate_end_minute=22 * 60, lock_offset_minutes=60,
                    offered_markets=[PickMarket.MATCH_ODDS, PickMarket.BOTH_TEAMS_TO_SCORE],
                    competitions=[{"slug": "england-premier-league", "name": "English Premier League"},
                                  {"slug": "england-championship", "name": "English Championship"}],
                    pick_scope=PickScope.fixture)
        l3 = League(slug="l3-race-sel", name="Race (selection)", created_by=people["R01"].id,
                    pick_scope=PickScope.selection)
        l4 = League(slug="l4-race-fix", name="Race (fixture)", created_by=people["R01"].id,
                    pick_scope=PickScope.fixture)
        db.add_all([l1, l2, l3, l4])
        await db.flush()

        def m(league: League, name: str, admin: bool = False) -> LeagueMembership:
            return LeagueMembership(league_id=league.id, player_id=people[name].id,
                                    role=LeagueMemberRole.admin if admin else LeagueMemberRole.player)

        db.add_all([m(l1, "Alice", True), m(l1, "Bob"), m(l1, "Carol"), m(l1, "Dan"), m(l1, "Erin")])
        db.add_all([m(l2, "Gina", True), m(l2, "Alice"), m(l2, "Dan"), m(l2, "Hank"), m(l2, "Ivy")])
        for n in range(1, 13):
            db.add_all([m(l3, f"R{n:02d}", n == 1), m(l4, f"R{n:02d}", n == 1)])
        await db.commit()

    fake = lib.use_rich_fake()
    ok = await run_discover_fixtures()
    lib.out("seed", f"run_discover_fixtures -> {ok}; provider calls {dict(fake.calls)}")

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(League.slug, Gameweek.starts_on, Gameweek.status, Gameweek.locks_at_utc,
                   Gameweek.picks_open_at_utc, Gameweek.number)
            .join(Gameweek, Gameweek.league_id == League.id)
            .order_by(League.slug, Gameweek.starts_on)
        )
        for r in rows.all():
            lib.out("seed", f"  {r.slug:12} {r.starts_on} {r.status.value:9} locks {r.locks_at_utc} opens {r.picks_open_at_utc} n={r.number}")
        cal = (await db.execute(text("select season, week_one_anchor, extra_weeks from season_calendars"))).all()
        lib.out("seed", f"  season_calendars: {cal}")


asyncio.run(main())
