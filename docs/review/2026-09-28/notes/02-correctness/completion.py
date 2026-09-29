"""CORR-14 re-drive (Batch 130) and the self-deletion path (Batch 136), over HTTP.

A. L1 (5 members): Alice, Bob, Carol, Dan pick; Erin LEAVES (DELETE /membership).
   Expect one completion row, empty final_picker_name, a "N/N picked — all picks are in"
   push to the league; then Bob moves his pick -> no second completion, no re-attribution.
B. L3 (12 members): R01..R11 pick; R12 DELETES HIS OWN ACCOUNT (POST /me/delete).
   Batch 130's rule says the round is now complete and must announce itself once,
   attributed to the transition. Then R05 moves his pick.
"""

import asyncio

import httpx
import lib
from sqlalchemy import text

from src.database import AsyncSessionLocal


async def completions(slug: str) -> list:
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(
            "select c.final_picker_name, c.member_count, c.delivered_at is not null as delivered "
            "from gameweek_completions c join gameweeks g on g.id=c.gameweek_id "
            "join leagues l on l.id=g.league_id where l.slug=:s"), {"s": slug})).all()


async def main() -> None:
    toks = await lib.tokens()
    async with httpx.AsyncClient(timeout=60, base_url=lib.API) as c:
        def h(n: str) -> dict:
            return {"Authorization": f"Bearer {toks[n]}"}

        async def slate(slug: str, who: str) -> list[tuple[str, str, str]]:
            cur = (await c.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=h(who))).json()
            return [(f["fixture_id"], s["market"], s["outcome"]) for f in cur["fixtures"] for s in f["selections"]]

        async def pick(slug: str, who: str, sel: tuple[str, str, str]) -> int:
            r = await c.post(f"/api/v1/leagues/{slug}/picks", headers=h(who),
                             json={"fixture_id": sel[0], "market": sel[1], "outcome": sel[2]})
            return r.status_code

        await c.delete("/__corr/pushes")
        # ── A: leave ────────────────────────────────────────────────────────────
        sels = await slate("l1-defaults", "Alice")
        codes = [await pick("l1-defaults", n, sels[i]) for i, n in enumerate(["Alice", "Bob", "Carol", "Dan"])]
        lib.out("completion", f"A: L1 picks by Alice,Bob,Carol,Dan -> {codes}; completions {await completions('l1-defaults')}")
        await asyncio.sleep(1)
        await c.delete("/__corr/pushes")
        r = await c.delete("/api/v1/leagues/l1-defaults/membership", headers=h("Erin"))
        await asyncio.sleep(1)
        pushes = (await c.get("/__corr/pushes")).json()
        lib.out("completion", f"A: Erin leaves -> {r.status_code}; completions {await completions('l1-defaults')}")
        lib.out("completion", f"A: pushes {[ (p['endpoint'].rsplit('/',1)[1], p['body']) for p in pushes]}")
        await c.delete("/__corr/pushes")
        code = await pick("l1-defaults", "Bob", sels[5])
        await asyncio.sleep(1)
        pushes = (await c.get("/__corr/pushes")).json()
        lib.out("completion", f"A: Bob moves pick -> {code}; completions {await completions('l1-defaults')}; pushes {[p['body'] for p in pushes][:2]} (x{len(pushes)})")

        # ── B: self-deletion ────────────────────────────────────────────────────
        sels = await slate("l3-race-sel", "R01")
        codes = [await pick("l3-race-sel", f"R{n:02d}", sels[n]) for n in range(1, 12)]
        lib.out("completion", f"B: L3 picks by R01..R11 -> {codes}; completions {await completions('l3-race-sel')}")
        await asyncio.sleep(1)
        await c.delete("/__corr/pushes")
        r = await c.post("/api/v1/me/delete", headers=h("R12"), json={"pin": "1234"})
        await asyncio.sleep(1)
        pushes = (await c.get("/__corr/pushes")).json()
        async with AsyncSessionLocal() as db:
            prog = (await db.execute(text(
                "select count(*) filter (where p.is_active and p.deleted_at is null) as active, "
                "count(pk.id) filter (where p.is_active and p.deleted_at is null) as picked "
                "from league_memberships m join profiles p on p.id=m.player_id "
                "left join picks pk on pk.player_id=m.player_id and pk.league_id=m.league_id "
                "where m.league_id=(select id from leagues where slug='l3-race-sel') and m.deleted_at is null"))).one()
        lib.out("completion", f"B: R12 deletes own account -> {r.status_code}; active members {prog.active}, picked {prog.picked}; completions {await completions('l3-race-sel')}; pushes {len(pushes)}")
        await c.delete("/__corr/pushes")
        code = await pick("l3-race-sel", "R05", sels[20])
        await asyncio.sleep(1)
        pushes = (await c.get("/__corr/pushes")).json()
        lib.out("completion", f"B: R05 moves pick -> {code}; completions {await completions('l3-race-sel')}")
        lib.out("completion", f"B: pushes after R05's move: {sorted({p['body'] for p in pushes})} (x{len(pushes)})")
        cur = (await c.post("/api/v1/leagues/l3-race-sel/picks", headers=h("R05"),
                            json={"fixture_id": sels[20][0], "market": sels[20][1], "outcome": sels[20][2]})).json()
        lib.out("completion", f"B: submit response progress after re-pick: picked {cur.get('picked_count')}/{cur.get('member_count')} all_picked={cur.get('all_picked')}")


asyncio.run(main())
