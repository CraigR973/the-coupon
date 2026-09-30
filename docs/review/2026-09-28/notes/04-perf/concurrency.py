"""Wall-clock timings over real HTTP to the one-worker perf API on :8140 (stress shape).

Sequential p50/p95 (n=20) for the hot endpoints, then 20 concurrent home summaries
(PERF-02's figure was 1,254 ms each). Waits for a 1-minute load average under 4 before
each block and records uptime. Writes timings.json.
"""
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from src.auth import create_access_token  # noqa: E402
from src.database import AsyncSessionLocal, engine  # noqa: E402
from src.models.profile import Profile  # noqa: E402

API = "http://127.0.0.1:8140"
HERE = Path(__file__).resolve().parent


async def quiet(max_wait: float = 600) -> str:
    t0 = time.time()
    while os.getloadavg()[0] >= 4 and time.time() - t0 < max_wait:
        await asyncio.sleep(15)
    return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        alice = (await db.execute(select(Profile).where(Profile.display_name == "Alice"))).scalar_one()
        stress = (await db.execute(select(Profile).where(Profile.display_name == "Stress 02"))).scalar_one()
    h = {"Authorization": f"Bearer {create_access_token(alice.id, alice.role)}", "Accept-Encoding": "gzip"}
    hs = {"Authorization": f"Bearer {create_access_token(stress.id, stress.role)}", "Accept-Encoding": "gzip"}
    out: dict = {"sequential": {}}
    plan = [("home summary (Alice, 3 leagues)", "/api/v1/me/cross-league-summary", h),
            ("current round (264 fully priced)", "/api/v1/leagues/the-coupon/gameweek/current", h),
            ("standings", "/api/v1/leagues/the-coupon/standings", h),
            ("standings, stress league", "/api/v1/leagues/stress-50/standings", hs),
            ("rounds list, stress league", "/api/v1/leagues/stress-50/gameweeks", hs),
            ("combined coupon", "/api/v1/leagues/the-coupon/coupon", h)]
    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        for name, path, headers in plan:
            uptime = await quiet()
            await c.get(path, headers=headers)  # warm
            walls = []
            for _ in range(20):
                t0 = time.perf_counter()
                r = await c.get(path, headers=headers)
                walls.append((time.perf_counter() - t0) * 1000)
            walls.sort()
            out["sequential"][name] = {"status": r.status_code, "p50_ms": round(statistics.median(walls), 1),
                                       "p95_ms": round(walls[18], 1), "uptime": uptime}
        uptime = await quiet()
        async def one() -> float:
            t0 = time.perf_counter()
            await c.get("/api/v1/me/cross-league-summary", headers=h)
            return (time.perf_counter() - t0) * 1000
        walls = sorted(await asyncio.gather(*[one() for _ in range(20)]))
        out["concurrent_20_home_summaries"] = {"p50_ms": round(statistics.median(walls), 1),
                                               "p95_ms": round(walls[18], 1), "max_ms": round(walls[-1], 1),
                                               "uptime": uptime}
    (HERE / "timings.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
