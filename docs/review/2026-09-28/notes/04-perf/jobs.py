"""Scheduler table and per-job cost at the stress shape.

1. The registered jobs as create_scheduler() builds them: trigger, misfire grace,
   coalesce, max_instances, and every job firing in the same minute on Sat 3 Oct.
2. Each job run once against the stress shape with an instant fake provider (the
   database and CPU floor, as on 13 Sep): statements and milliseconds, with uptime.
Writes jobs.json. Read-only apart from what the jobs themselves write (they are
idempotent at this shape: settle resolves nothing because the fake returns no results).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
sys.argv = [sys.argv[0], "jobs"]
import measure_api as m  # noqa: E402  (PricedFake + statement recorder on the app engine)
import src.scheduler as sched  # noqa: E402
from src.config import settings  # noqa: E402
from src.services.football_session import football_session  # noqa: E402
from src.services.odds_cache import CachingOddsProvider  # noqa: E402
from src.services.odds_session import odds_session  # noqa: E402

HERE = Path(__file__).resolve().parent
LON = ZoneInfo("Europe/London")


async def table() -> dict:
    s = sched.create_scheduler()
    s.start(paused=True)  # pending jobs only get their defaults once the scheduler starts
    jobs = []
    fires: dict[str, list[str]] = defaultdict(list)
    start = datetime(2026, 10, 3, 0, 0, tzinfo=LON)
    for job in s.get_jobs():
        jobs.append({"id": job.id, "trigger": str(job.trigger), "misfire_grace_time": job.misfire_grace_time,
                     "coalesce": job.coalesce, "max_instances": job.max_instances})
        prev = None
        t = start
        while True:
            nxt = job.trigger.get_next_fire_time(prev, t)
            if nxt is None or nxt >= start + timedelta(days=1):
                break
            fires[nxt.astimezone(LON).strftime("%H:%M")].append(job.id)
            prev, t = nxt, nxt + timedelta(seconds=1)
    s.shutdown(wait=False)
    shared = {k: v for k, v in sorted(fires.items()) if len(v) > 1}
    return {"jobs": jobs, "saturday_minutes_with_2plus_jobs": shared,
            "jobs_without_misfire_grace": [j["id"] for j in jobs if j["misfire_grace_time"] in (None, 1)]}


async def costs() -> dict:
    cache = CachingOddsProvider(m.FAKE, ttl_seconds=settings.odds_cache_ttl_seconds)
    odds_session._client = cache  # type: ignore[attr-defined]
    odds_session._validated_at = datetime.now(UTC)  # type: ignore[attr-defined]

    async def none():  # noqa: ANN202
        return None

    football_session.acquire = none  # type: ignore[method-assign]
    # Put the clock after the 3 Oct lock so lock/settle have rounds to consider.
    after_lock = datetime(2026, 10, 3, 17, 0)
    sched._utc_now = lambda: after_lock  # type: ignore[attr-defined]
    sched._uk_today = lambda: after_lock.date()  # type: ignore[attr-defined]
    out = {}
    for name in ("run_lock_gameweeks", "run_open_gameweeks", "run_settle_gameweeks", "run_pick_reminders",
                 "run_warm_odds_marker", "run_discover_fixtures", "run_refresh_slate", "run_live_scores",
                 "run_sync_football_data", "run_prune_refresh_tokens", "run_prune_rate_limit_counters",
                 "run_connection_warmup"):
        m.REC.statements.clear()
        t0 = time.perf_counter()
        ok = await getattr(sched, name)()
        ms = (time.perf_counter() - t0) * 1000
        out[name] = {"ok": ok, "stmts": len(m.REC.statements), "ms": round(ms, 1)}
    return out


async def main() -> None:
    result = {"uptime": subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip(),
              "table": await table(), "costs_at_stress_shape": await costs()}
    (HERE / "jobs.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps(result["table"]["jobs_without_misfire_grace"]))
    print(json.dumps(result["table"]["saturday_minutes_with_2plus_jobs"]))
    for k, v in result["costs_at_stress_shape"].items():
        print(k, v)
    print(result["uptime"])
    await m.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
