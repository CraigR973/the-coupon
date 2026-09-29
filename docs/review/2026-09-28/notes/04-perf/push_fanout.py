"""PERF-10 re-drive and the pool question, over real HTTP to perf_push_app on :8141.

1. latency: one pick in the 12-member league and one in the 50-member league; time to the
   HTTP response vs time until every other member's send has happened (SENDS_FILE lines),
   and that each eligible member got exactly one send.
2. concurrency: K members of the 50-member league submit at once; while their fan-outs run,
   GET /api/v1/health/ready (one pooled connection) is timed and /__perf/pool sampled.

Writes push-fanout.json. Mutates the scratch DB (adds subscriptions and picks).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.auth import create_access_token  # noqa: E402
from src.database import engine  # noqa: E402
from src.models.profile import UserRole  # noqa: E402

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:8141"
SENDS = Path(os.environ["SENDS_FILE"])


async def setup() -> dict:
    async with engine.begin() as conn:
        await conn.execute(text("delete from push_subscriptions"))
        await conn.execute(text(
            "insert into push_subscriptions (id, user_id, subscription) select gen_random_uuid(), p.id, "
            "jsonb_build_object('endpoint', 'https://push.invalid/' || p.id::text, 'keys', '{}'::jsonb) "
            "from profiles p"))
        rows = (await conn.execute(text(
            "select l.slug, p.display_name, p.id, p.role, "
            "exists(select 1 from picks k join gameweeks g on g.id=k.gameweek_id where k.player_id=p.id "
            "and g.league_id=l.id and g.status='open') as picked "
            "from leagues l join league_memberships m on m.league_id=l.id join profiles p on p.id=m.player_id "
            "where l.slug in ('the-coupon','stress-50') order by p.display_name"))).all()
        free = {}
        for slug in ("the-coupon", "stress-50"):
            free[slug] = [str(f) for (f,) in (await conn.execute(text(
                "select gf.fixture_id from gameweek_fixtures gf join gameweeks g on g.id=gf.gameweek_id "
                "join leagues l on l.id=g.league_id where l.slug=:s and g.status='open' and gf.fixture_id not in "
                "(select fixture_id from picks where gameweek_id=g.id) order by gf.fixture_id"), {"s": slug})).all()]
    members = {}
    for slug, name, pid, role, picked in rows:
        members.setdefault(slug, []).append({"name": name, "token": create_access_token(pid, UserRole(role)),
                                             "picked": picked, "id": str(pid)})
    return {"members": members, "free": free}


def sends() -> list[str]:
    return SENDS.read_text().splitlines() if SENDS.exists() else []


async def submit(client: httpx.AsyncClient, slug: str, member: dict, fixture: str) -> tuple[int, float, float]:
    t0 = time.perf_counter()
    r = await client.post(f"{API}/api/v1/leagues/{slug}/picks",
                          headers={"Authorization": f"Bearer {member['token']}"},
                          json={"fixture_id": fixture, "market": "MATCH_ODDS", "outcome": "HOME", "odds": "2.10"})
    return r.status_code, (time.perf_counter() - t0) * 1000, time.time()


async def wait_sends(n: int, timeout: float = 60) -> float:
    t0 = time.time()
    while len(sends()) < n and time.time() - t0 < timeout:
        await asyncio.sleep(0.05)
    return time.time()


async def main() -> None:
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    state = await setup()
    out: dict = {"uptime_start": subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()}
    async with httpx.AsyncClient(timeout=60) as client:
        for slug in ("the-coupon", "stress-50"):
            members = state["members"][slug]
            picker = next(m for m in members if not m["picked"])
            SENDS.write_text("")
            status, ms, done = await submit(client, slug, picker, state["free"][slug].pop())
            expected = len(members) - 1
            finished = await wait_sends(expected)
            lines = sends()
            endpoints = [line.split(" ", 1)[1] for line in lines]
            out[f"latency_{slug}"] = {
                "members": len(members), "status": status, "response_ms": round(ms, 1),
                "fanout_finished_after_response_s": round(finished - done, 2),
                "sends": len(lines), "expected": expected,
                "distinct_recipients": len(set(endpoints)),
                "picker_told": any(picker["id"] in e for e in endpoints)}
            picker["picked"] = True
        # Concurrency: K unpicked stress members at once, then probe the pool.
        members = [m for m in state["members"]["stress-50"] if not m["picked"]][:k]
        SENDS.write_text("")
        t0 = time.perf_counter()
        tasks = [asyncio.create_task(submit(client, "stress-50", m, state["free"]["stress-50"].pop()))
                 for m in members]
        results = await asyncio.gather(*tasks)
        after_submits = (time.perf_counter() - t0) * 1000
        samples = []
        for _ in range(6):
            p0 = time.perf_counter()
            ready = await client.get(f"{API}/api/v1/health/ready")
            ready_ms = (time.perf_counter() - p0) * 1000
            pool = (await client.get(f"{API}/__perf/pool")).json()
            samples.append({"ready_status": ready.status_code, "ready_ms": round(ready_ms, 1), **pool})
            await asyncio.sleep(1)
        out["concurrent"] = {
            "k": len(members), "submit_statuses": sorted(r[0] for r in results),
            "submit_ms_max": round(max(r[1] for r in results), 1),
            "all_submits_answered_ms": round(after_submits, 1), "probes": samples}
        await wait_sends(len(members) * 49, timeout=120)
        out["concurrent"]["sends_total"] = len(sends())
    out["uptime_end"] = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    (HERE / "push-fanout.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out)[:3000])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
