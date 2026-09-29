"""CORR-09 / CORR-13 re-drive (Batch 121) and the settle guard's other edge.

L5 Sat -> Fri mid-week, stray holds NO pick   : stray must be retired.
L6 Sat -> Fri mid-week, stray holds Bob's pick : stray kept, reported, never scored;
                                                 exactly one scoring round and one label.
L7 Fri, settles Fri 2 Oct, THEN Fri -> Sat     : is the new Saturday round (same football
                                                 week, the league's own weekday now) pickable
                                                 and does it ever settle?
Discovery/settlement are the services the scheduler jobs call, with a chosen `today`/`now`.
Picks and window edits are over HTTP.
"""

import asyncio
from datetime import date, datetime

import httpx
import lib
from sqlalchemy import select, text

from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile
from src.services.gameweek import discover_fixtures
from src.services.scoring import settle_gameweeks_via_provider, standings

FAKE = lib.FAKE
FRI = dict(slate_start_weekday=4, slate_start_minute=19 * 60, slate_end_weekday=4, slate_end_minute=22 * 60, lock_offset_minutes=60)
SAT = dict(slate_start_weekday=5, slate_start_minute=15 * 60, slate_end_weekday=5, slate_end_minute=15 * 60, lock_offset_minutes=30)


async def rounds(slug: str) -> list:
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(
            "select g.starts_on, g.status, (select count(*) from picks p where p.gameweek_id=g.id) as picks "
            "from gameweeks g join leagues l on l.id=g.league_id where l.slug=:s order by g.starts_on"), {"s": slug})).all()


async def discover(slugs: list[str], today: date) -> None:
    async with AsyncSessionLocal() as db:
        leagues = list((await db.execute(select(League).where(League.slug.in_(slugs)))).scalars())
        await discover_fixtures(db, FAKE, leagues, today, 2, commit_each=True)
        await db.commit()


async def settle(slug: str, starts_on: date, now: datetime) -> dict:
    """Lock (as lock_due_gameweeks does) and settle one round via the provider path."""
    async with AsyncSessionLocal() as db:
        gw = (await db.execute(select(Gameweek).join(League).where(League.slug == slug, Gameweek.starts_on == starts_on))).scalar_one()
        if gw.status in (GameweekStatus.open, GameweekStatus.scheduled) and gw.locks_at_utc <= now:
            gw.status = GameweekStatus.locked
        res = await settle_gameweeks_via_provider(db, FAKE, [gw])
        await db.commit()
        return {"resolved": res.get(gw.id, 0), "status": gw.status.value}


async def main() -> None:
    async with AsyncSessionLocal() as db:
        people = {p.display_name: p for p in (await db.execute(select(Profile))).scalars()}
        for slug, win in (("l5-sat-empty", SAT), ("l6-sat-picked", SAT), ("l7-fri-then-sat", FRI)):
            await db.execute(text("delete from leagues where slug=:s"), {"s": slug})
            lg = League(slug=slug, name=slug, created_by=people["Alice"].id, **win)
            db.add(lg)
            await db.flush()
            for n in ("Alice", "Bob", "Carol"):
                db.add(LeagueMembership(league_id=lg.id, player_id=people[n].id,
                                        role=LeagueMemberRole.admin if n == "Alice" else LeagueMemberRole.player))
        await db.commit()

    await discover(["l5-sat-empty", "l6-sat-picked", "l7-fri-then-sat"], date(2026, 9, 29))
    for s in ("l5-sat-empty", "l6-sat-picked", "l7-fri-then-sat"):
        lib.out("window", f"after first discovery {s}: {await rounds(s)}")

    toks = await lib.tokens()
    async with httpx.AsyncClient(timeout=60, base_url=lib.API) as c:
        def h(n: str) -> dict:
            return {"Authorization": f"Bearer {toks[n]}"}

        async def sels(slug: str, who: str, gid: str | None = None) -> list:
            url = f"/api/v1/leagues/{slug}/gameweek/current" + (f"?gameweek_id={gid}" if gid else "")
            cur = (await c.get(url, headers=h(who))).json()
            return cur["gameweek_id"], cur["starts_on"], [(f["fixture_id"], s["market"], s["outcome"]) for f in cur["fixtures"] for s in f["selections"]]

        async def pick(slug: str, who: str, sel: tuple) -> str:
            r = await c.post(f"/api/v1/leagues/{slug}/picks", headers=h(who),
                             json={"fixture_id": sel[0], "market": sel[1], "outcome": sel[2]})
            return f"{r.status_code} {r.json().get('detail', '') if r.status_code != 201 else ''}".strip()

        # L6: Bob picks the Saturday round BEFORE the change.
        gid6, so6, s6 = await sels("l6-sat-picked", "Bob")
        lib.out("window", f"L6 Bob picks Saturday {so6} -> {await pick('l6-sat-picked', 'Bob', s6[0])}")
        # L7: Bob and Carol pick Friday 2 Oct.
        gid7, so7, s7 = await sels("l7-fri-then-sat", "Bob")
        lib.out("window", f"L7 Bob, Carol pick {so7} -> {await pick('l7-fri-then-sat', 'Bob', s7[0])}, {await pick('l7-fri-then-sat', 'Carol', s7[4])}")

        # Mid-week (Wed 30 Sep) window change Sat -> Fri on L5 and L6.
        for s in ("l5-sat-empty", "l6-sat-picked"):
            r = await c.patch(f"/api/v1/leagues/{s}", headers=h("Alice"), json=FRI)
            lib.out("window", f"PATCH {s} -> Friday: {r.status_code}")
        await discover(["l5-sat-empty", "l6-sat-picked"], date(2026, 9, 30))
        for s in ("l5-sat-empty", "l6-sat-picked"):
            lib.out("window", f"after change + discovery {s}: {await rounds(s)}")
        gl = (await c.get("/api/v1/leagues/l6-sat-picked/gameweeks", headers=h("Bob"))).json()
        lib.out("window", "L6 labels: " + ", ".join(f"{g['starts_on']}={g.get('season_week')!r}" for g in gl))
        # Can Carol still claim on the stray Saturday round after the change?
        lib.out("window", f"L6 Carol picks on stray Saturday (after change) -> {await pick('l6-sat-picked', 'Carol', s6[1])}")
        # Alice picks the new Friday round.
        fri6 = next(g for g in gl if g["starts_on"] == "2026-10-02")
        _, _, f6 = await sels("l6-sat-picked", "Alice", fri6["id"] if "id" in fri6 else fri6.get("gameweek_id"))
        lib.out("window", f"L6 Alice picks Friday -> {await pick('l6-sat-picked', 'Alice', f6[0])}")

        # Results for every 2 Oct / 3 Oct fixture: home wins.
        for f in lib.richfake.fixtures():
            if f["openDate"].startswith(("2026-10-02", "2026-10-03")):
                FAKE.result(f["id"], 2, 1)

        # L7: settle Friday first (Fri 22:30 UTC), THEN change to Saturday and rediscover on Fri 2 Oct.
        lib.out("window", f"L7 settle Fri: {await settle('l7-fri-then-sat', date(2026, 10, 2), datetime(2026, 10, 2, 21, 30))}")
        r = await c.patch("/api/v1/leagues/l7-fri-then-sat", headers=h("Alice"), json=SAT)
        lib.out("window", f"PATCH l7 -> Saturday after Friday settled: {r.status_code}")
        await discover(["l7-fri-then-sat"], date(2026, 10, 2))
        lib.out("window", f"L7 after change + discovery: {await rounds('l7-fri-then-sat')}")
        gl7 = (await c.get("/api/v1/leagues/l7-fri-then-sat/gameweeks", headers=h("Bob"))).json()
        sat7 = next((g for g in gl7 if g["starts_on"] == "2026-10-03"), None)
        lib.out("window", "L7 labels: " + ", ".join(f"{g['starts_on']}={g.get('season_week')!r} {g.get('status')}" for g in gl7))
        if sat7:
            _, _, ss7 = await sels("l7-fri-then-sat", "Bob", sat7.get("id") or sat7.get("gameweek_id"))
            lib.out("window", f"L7 Bob, Carol pick new Saturday -> {await pick('l7-fri-then-sat', 'Bob', ss7[0])}, {await pick('l7-fri-then-sat', 'Carol', ss7[1])}")

    # Lock and settle everything on 2/3 Oct for L6 and L7 (Sat 18:00 UTC), twice (sweep retries).
    for attempt in (1, 2):
        for s, d in (("l6-sat-picked", date(2026, 10, 2)), ("l6-sat-picked", date(2026, 10, 3)), ("l7-fri-then-sat", date(2026, 10, 3))):
            lib.out("window", f"settle #{attempt} {s} {d}: {await settle(s, d, datetime(2026, 10, 3, 18, 0))}")
    for s in ("l6-sat-picked", "l7-fri-then-sat"):
        lib.out("window", f"final {s}: {await rounds(s)}")
        async with AsyncSessionLocal() as db:
            lg = (await db.execute(select(League).where(League.slug == s))).scalar_one()
            table = await standings(db, lg.id, season=2026)
            lib.out("window", f"standings {s}: " + ", ".join(f"{r.display_name} {r.total_points}pts/{r.picks_played}" for r in table))
            pend = (await db.execute(text("select pr.display_name, g.starts_on, p.status from picks p join profiles pr on pr.id=p.player_id join gameweeks g on g.id=p.gameweek_id where p.league_id=:l order by g.starts_on"), {"l": lg.id})).all()
            lib.out("window", f"picks {s}: {pend}")


asyncio.run(main())
