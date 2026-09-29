"""Concurrency: last two slots completing at once (L1, 3 active members, Sat 10 Oct), and a
pick racing its member's own account deletion (L2, Fri 9 Oct), over HTTP."""

import asyncio

import httpx
import lib
from sqlalchemy import text

from src.database import AsyncSessionLocal

OUT = "races2"


async def main() -> None:
    # The seed's discovery run walked only each window's nearest date (it logged
    # "discovery stopped on its own budget … per_walk=41 spent=82 walks_skipped=2" — CORR-24
    # on an empty pool), so L1 has no 10 Oct round yet. Run the 06:00 job again now the
    # pool is small.
    lib.use_rich_fake()
    from src.scheduler import run_discover_fixtures
    lib.out(OUT, f"run_discover_fixtures -> {await run_discover_fixtures()}")
    toks = await lib.tokens()
    async with httpx.AsyncClient(timeout=60, base_url=lib.API) as c:
        def h(n):
            return {"Authorization": f"Bearer {toks[n]}"}

        gl = (await c.get("/api/v1/leagues/l1-defaults/gameweeks", headers=h("Alice"))).json()
        gid = next(g["gameweek_id"] for g in gl if g["starts_on"] == "2026-10-10")
        cur = (await c.get(f"/api/v1/leagues/l1-defaults/gameweek/current?gameweek_id={gid}", headers=h("Alice"))).json()
        sels = [(f["fixture_id"], s["market"], s["outcome"]) for f in cur["fixtures"] for s in f["selections"]]
        body = lambda s: {"fixture_id": s[0], "market": s[1], "outcome": s[2]}  # noqa: E731
        r = await c.post("/api/v1/leagues/l1-defaults/picks", headers=h("Alice"), json=body(sels[0]))
        lib.out(OUT, f"L1 {cur['starts_on']}: Alice picks -> {r.status_code}")
        await c.delete("/__corr/pushes")
        ra, rb = await asyncio.gather(c.post("/api/v1/leagues/l1-defaults/picks", headers=h("Carol"), json=body(sels[3])),
                                      c.post("/api/v1/leagues/l1-defaults/picks", headers=h("Dan"), json=body(sels[6])))
        await asyncio.sleep(1.5)
        pushes = (await c.get("/__corr/pushes")).json()
        async with AsyncSessionLocal() as db:
            comp = (await db.execute(text("select final_picker_name, member_count from gameweek_completions where gameweek_id=:g"), {"g": cur["gameweek_id"]})).all()
        lib.out(OUT, f"Carol+Dan simultaneously -> {ra.status_code}/{rb.status_code}, all_picked {ra.json().get('all_picked')}/{rb.json().get('all_picked')}; completion rows {comp}; "
                     f"distinct push bodies {sorted({p['body'] for p in pushes})} (x{len(pushes)})")

        gl2 = (await c.get("/api/v1/leagues/l2-friday/gameweeks", headers=h("Hank"))).json()
        gid2 = next(g["gameweek_id"] for g in gl2 if g["starts_on"] == "2026-10-09")
        cur2 = (await c.get(f"/api/v1/leagues/l2-friday/gameweek/current?gameweek_id={gid2}", headers=h("Hank"))).json()
        f2 = cur2["fixtures"][0]
        rp, rd = await asyncio.gather(
            c.post("/api/v1/leagues/l2-friday/picks", headers=h("Hank"), json={"fixture_id": f2["fixture_id"], "market": "MATCH_ODDS", "outcome": "HOME"}),
            c.post("/api/v1/me/delete", headers=h("Hank"), json={"pin": "1234"}))
        async with AsyncSessionLocal() as db:
            held = (await db.execute(text("select pr.display_name, pr.deleted_at is not null from picks p join profiles pr on pr.id=p.player_id where p.gameweek_id=:g"), {"g": cur2["gameweek_id"]})).all()
        lib.out(OUT, f"L2 {cur2['starts_on']}: Hank's pick {rp.status_code} racing his deletion {rd.status_code}; picks on the round now {held}")
        r = await c.post("/api/v1/leagues/l2-friday/picks", headers=h("Ivy"), json={"fixture_id": f2["fixture_id"], "market": "BOTH_TEAMS_TO_SCORE", "outcome": "YES"})
        lib.out(OUT, f"Ivy then tries the same fixture (fixture scope) -> {r.status_code} {r.json().get('detail', '')}")


asyncio.run(main())
