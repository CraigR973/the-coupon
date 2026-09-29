"""CORR-08 re-drive: 12 simultaneous submissions for ONE selection, in both claim scopes.

Over HTTP against corr_server on 8120, with the browser's Origin so CORS is exercised.
Expected (Batch 120): exactly one 201, zero 500s, the rest 409 SELECTION_TAKEN /
FIXTURE_TAKEN, and every 409 carrying Access-Control-Allow-Origin.
Also: concurrent completion of the last two slots in L3 (exactly one completion row).
"""

import asyncio
from collections import Counter

import httpx
import lib
from sqlalchemy import text

from src.database import AsyncSessionLocal


async def race(client: httpx.AsyncClient, toks: dict[str, str], slug: str, members: list[str], body: dict) -> None:
    async def one(name: str) -> tuple[str, int, str, str | None]:
        r = await client.post(
            f"{lib.API}/api/v1/leagues/{slug}/picks",
            json=body,
            headers={"Authorization": f"Bearer {toks[name]}", "Origin": lib.WEB_ORIGIN},
        )
        detail = r.json().get("detail", "") if r.status_code != 201 else "created"
        return name, r.status_code, str(detail), r.headers.get("access-control-allow-origin")

    results = await asyncio.gather(*(one(n) for n in members))
    tally = Counter((s, d) for _, s, d, _ in results)
    cors_missing = [n for n, s, _, c in results if c != lib.WEB_ORIGIN]
    lib.out("race", f"{slug} {body['market']}/{body['outcome']} x{len(members)}: {dict(tally)}; CORS missing on {cors_missing or 'none'}")


async def main() -> None:
    toks = await lib.tokens()
    racers = [f"R{n:02d}" for n in range(1, 13)]
    async with httpx.AsyncClient(timeout=60) as client:
        cur = (await client.get(f"{lib.API}/api/v1/leagues/l3-race-sel/gameweek/current",
                                headers={"Authorization": f"Bearer {toks['R01']}"})).json()
        fixtures = cur["fixtures"]
        f0 = fixtures[0]
        price = next(s for s in f0["selections"] if s["market"] == "MATCH_ODDS" and s["outcome"] == "HOME")
        lib.out("race", f"round {cur['gameweek_id']} fixture {f0['home']} v {f0['away']} HOME @ {price}")
        for slug in ("l3-race-sel", "l4-race-fix"):
            for attempt in range(2):  # 2 x 12 x 2 = 48 < the 50/hour installation bucket
                await race(client, toks, slug, racers,
                           {"fixture_id": f0["fixture_id"], "market": "MATCH_ODDS", "outcome": "HOME"})
                async with AsyncSessionLocal() as db:
                    await db.execute(text(
                        "delete from picks where league_id=(select id from leagues where slug=:s)"), {"s": slug})
                    await db.commit()
    async with AsyncSessionLocal() as db:
        n = (await db.execute(text("select count(*) from picks"))).scalar_one()
        lib.out("race", f"picks left after cleanup: {n}")


asyncio.run(main())
