"""CORR-17 (Batch 147) re-drive and the clock-change boundaries.

1. The real pick_reminders trigger from create_scheduler(), iterated across 24-26 Oct 2026
   and 27-29 Mar 2027; at every fire instant, gameweeks_due_a_reminder() against rounds
   locking every 15 minutes across both change nights (rolled back). Each lock must be
   selected exactly once.
2. Lock instants the calendar writes either side of both changes, and what a New York
   member is told (_lock_label) in the week London and New York are 4h apart.
3. CORR-05 still holds: a window starting inside the missing / repeated hour is refused.
"""

import asyncio
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import httpx
import lib
from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.scheduler import create_scheduler
from src.services.gameweek import gameweeks_due_a_reminder
from src.services.notification_triggers import _lock_label
from src.services.odds_provider import SlateWindow

OUT = "dst"


async def reminders(start: datetime, end: datetime, lock_from: datetime, lock_to: datetime) -> None:
    trig = create_scheduler().get_job("pick_reminders").trigger
    fires = []
    t = trig.get_next_fire_time(None, start.replace(tzinfo=UTC))
    while t and t < end.replace(tzinfo=UTC):
        fires.append(t.astimezone(UTC).replace(tzinfo=None))
        t = trig.get_next_fire_time(t, t + timedelta(seconds=1))
    gaps = {b - a for a, b in zip(fires, fires[1:])}
    lib.out(OUT, f"trigger {trig}; {len(fires)} fires {fires[0]}..{fires[-1]}; distinct gaps {sorted(str(g) for g in gaps)}")
    async with AsyncSessionLocal() as db:
        lg = (await db.execute(select(League).limit(1))).scalar_one()
        made = {}
        lock = lock_from
        i = 0
        while lock <= lock_to:
            gw = Gameweek(league_id=lg.id, starts_on=date(2030, 1, 1) + timedelta(days=i), locks_at_utc=lock,
                          status=GameweekStatus.open, number=900 + i)
            db.add(gw)
            made[lock] = gw
            lock += timedelta(minutes=15)
            i += 1
        await db.flush()
        ids = {gw.id: lk for lk, gw in made.items()}
        hits: Counter = Counter()
        for f in fires:
            for gw in await gameweeks_due_a_reminder(db, f):
                if gw.id in ids:
                    hits[ids[gw.id]] += 1
        await db.rollback()
    bad = {str(lk): hits.get(lk, 0) for lk in made if hits.get(lk, 0) != 1}
    lib.out(OUT, f"locks {lock_from}..{lock_to} every 15 min ({len(made)} rounds): reminded exactly once = {len(made) - len(bad)}; not once: {bad or 'none'}")


async def main() -> None:
    # Fall back: 01:00 BST 25 Oct 2026 (00:00Z) -> 01:00 GMT (01:00Z). The repeated local hour is 00:00-02:00Z.
    await reminders(datetime(2026, 10, 24, 12), datetime(2026, 10, 26, 12), datetime(2026, 10, 24, 20), datetime(2026, 10, 25, 12))
    # Spring forward: 01:00 GMT 28 Mar 2027 (01:00Z) -> 02:00 BST.
    await reminders(datetime(2027, 3, 27, 12), datetime(2027, 3, 29, 12), datetime(2027, 3, 27, 20), datetime(2027, 3, 28, 12))

    sat, fri = SlateWindow(), SlateWindow(4, 19 * 60 + 45, 4, 19 * 60 + 45, 60)
    sun = SlateWindow(6, 13 * 60, 6, 16 * 60, 30)
    for w, d in ((sat, date(2026, 10, 24)), (sun, date(2026, 10, 25)), (fri, date(2026, 10, 30)), (sat, date(2026, 10, 31)),
                 (sat, date(2027, 3, 27)), (sun, date(2027, 3, 28)), (sat, date(2027, 4, 3))):
        lk = w.locks_at(d)
        lib.out(OUT, f"{d:%a %d %b %Y} window {w.start_minute // 60:02d}:{w.start_minute % 60:02d} lock-{w.lock_offset_minutes}: lock {lk}Z; "
                     f"London {_lock_label(lk, 'Europe/London')}, New York {_lock_label(lk, 'America/New_York')}, Sydney {_lock_label(lk, 'Australia/Sydney')}")

    toks = await lib.tokens()
    async with httpx.AsyncClient(timeout=30, base_url=lib.API) as c:
        for body in ({"slate_start_weekday": 6, "slate_start_minute": 90, "slate_end_weekday": 6, "slate_end_minute": 90},
                     {"slate_start_weekday": 6, "slate_start_minute": 60, "slate_end_weekday": 6, "slate_end_minute": 60},
                     {"slate_start_weekday": 6, "slate_start_minute": 180, "slate_end_weekday": 6, "slate_end_minute": 180, "lock_offset_minutes": 90}):
            r = await c.patch("/api/v1/leagues/l5-sat-empty", headers={"Authorization": f"Bearer {toks['Alice']}"}, json=body)
            lib.out(OUT, f"CORR-05 PATCH {body} -> {r.status_code} {str(r.json().get('detail'))[:140]}")


asyncio.run(main())
