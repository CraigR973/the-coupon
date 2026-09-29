"""CORR-11 / CORR-12 / CORR-16 re-drives (Batch 132; CORR-16 accepted).

CORR-11 over HTTP as the site admin (Root): extra week in the past, in a settled week,
and in a future unsettled week (then withdrawn).
CORR-12 in process, inside a transaction that is rolled back: season 2027 gets a Friday
league's round first and a Saturday league's earlier round second (and the reverse);
the anchor must be the earliest canonical Saturday either way.
CORR-16: labels for a Wed 30 Jun 2027 round vs the Sat 3 Jul 2027 four days later.
"""

import asyncio
from datetime import date, datetime

import httpx
import lib
from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models.league import League
from src.models.profile import Profile
from src.models.season_calendar import SeasonCalendar
from src.services.gameweek import sync_slate
from src.services.odds_provider import Slate, SlateFixture
from src.services.season_calendar import labels_for_gameweeks

OUT = "calendar"


def slate(day: date, hh: int, eid: str) -> Slate:
    return Slate(starts_on=day, fixtures=[SlateFixture(
        provider_event_id=eid, home="H" + eid, away="A" + eid, kickoff_utc=datetime(day.year, day.month, day.day, hh - 1, 0),
        competition="English Premier League", competition_id="england-premier-league")])


async def anchor_case(order: str) -> None:
    async with AsyncSessionLocal() as db:
        owner = (await db.execute(select(Profile).limit(1))).scalar_one()
        sat = League(slug=f"cal-sat-{order}", name="cal sat", created_by=owner.id)
        fri = League(slug=f"cal-fri-{order}", name="cal fri", created_by=owner.id, slate_start_weekday=4,
                     slate_start_minute=19 * 60, slate_end_weekday=4, slate_end_minute=22 * 60)
        db.add_all([sat, fri])
        await db.flush()
        steps = [(fri, slate(date(2027, 8, 13), 20, f"c27f-{order}")), (sat, slate(date(2027, 8, 7), 15, f"c27s-{order}"))]
        if order == "sat-first":
            steps.reverse()
        made = []
        for lg, sl in steps:
            gw = await sync_slate(db, lg, sl)
            made.append(gw)
            cal = await db.get(SeasonCalendar, 2027)
            lib.out(OUT, f"CORR-12 [{order}] synced {lg.slug} {sl.starts_on} -> 2027 anchor {cal.week_one_anchor if cal else None}")
        labels = await labels_for_gameweeks(db, made)
        lib.out(OUT, f"CORR-12 [{order}] labels: " + ", ".join(f"{g.starts_on}={labels.get(g.id)!r}" for g in made))
        # CORR-16: a rollover week, season 2026's last Wednesday and season 2027's first Saturday.
        if order == "fri-first":
            w = await sync_slate(db, sat, slate(date(2027, 6, 30), 15, "c-roll-wed"))
            s = await sync_slate(db, sat, slate(date(2027, 7, 3), 15, "c-roll-sat"))
            labels = await labels_for_gameweeks(db, [w, s])
            lib.out(OUT, f"CORR-16 rollover: Wed 2027-06-30 -> {labels.get(w.id)!r} (2026 calendar), Sat 2027-07-03 -> {labels.get(s.id)!r} (2027 calendar)")
        await db.rollback()


async def main() -> None:
    toks = await lib.tokens()
    h = {"Authorization": f"Bearer {toks['Root']}"}
    async with httpx.AsyncClient(timeout=30, base_url=lib.API) as c:
        for d, why in (("2026-09-26", "past Saturday+"), ("2026-09-23", "past Wednesday"),
                       ("2026-10-05", "Mon in the week whose round has settled"),
                       ("2026-10-14", "future Wednesday, unsettled week")):
            r = await c.post("/api/v1/admin/calendar/extra-weeks", headers=h, json={"season": 2026, "starts_on": d})
            lib.out(OUT, f"CORR-11 declare {d} ({why}) -> {r.status_code} {r.json().get('detail', '') if r.status_code != 200 else 'extras=' + str(r.json().get('extra_weeks'))}")
        r = await c.request("DELETE", "/api/v1/admin/calendar/extra-weeks", headers=h, json={"season": 2026, "starts_on": "2026-10-14"})
        lib.out(OUT, f"CORR-11 withdraw 2026-10-14 -> {r.status_code}")
    await anchor_case("fri-first")
    await anchor_case("sat-first")


asyncio.run(main())
