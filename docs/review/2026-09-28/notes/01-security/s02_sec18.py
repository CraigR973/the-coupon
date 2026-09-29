"""SEC-18 API half (Batch 123): does the per-source failure budget stop one address
locking a whole leaderboard?

One source (127.0.0.1, no X-Forwarded-For) sends five wrong PINs to each of v1..v5
inside one 15-minute window. Then each victim's lock state is read from the database
(so no further login attempts disturb the buckets), and confirmed over HTTP with the
correct PIN from a *different* source (X-Forwarded-For, which the local stack trusts
as the proxy's view; the per-(name, ip) bucket for 127.0.0.1 is spent by then).
"""

import asyncio
import json
import os
import sys
import time

from lib import SCRATCH, call, login, note, section, wait_for_fresh_window

state = json.loads((SCRATCH / "stack-sec.json").read_text())
os.environ["DATABASE_URL"] = state["database_url"]
os.environ.setdefault("JWT_ACCESS_SECRET", "review-access-secret-with-at-least-32-characters")
os.environ.setdefault("JWT_REFRESH_SECRET", "review-refresh-secret-with-at-least-32-characters")
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import select, text  # noqa: E402

from src.database import AsyncSessionLocal  # noqa: E402
from src.models.profile import Profile  # noqa: E402


async def lock_state() -> list[tuple]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Profile.display_name, Profile.failed_login_count, Profile.locked_until)
                .where(Profile.display_name.in_(["V1", "V2", "V3", "V4", "V5"]))
                .order_by(Profile.display_name)
            )
        ).all()
        buckets = (
            await db.execute(
                text("SELECT bucket_key, limit_item, hits FROM rate_limit_counters "
                     "WHERE bucket_key LIKE 'login-src:%' ORDER BY bucket_key")
            )
        ).all()
    return rows, buckets


section("SEC-18 API half: one source, five victims, five wrong PINs each")
wait_for_fresh_window(900, 180)
t0 = time.time()
for v in ["V1", "V2", "V3", "V4", "V5"]:
    codes = [login(v, "9173").status_code for _ in range(5)]
    note(f"  {v}: {codes}")
note(f"  25 requests in {time.time() - t0:.1f}s, same 15-minute window")

rows, buckets = asyncio.run(lock_state())
note("database after the run:")
for name, count, until in rows:
    note(f"  {name}: failed_login_count={count} locked_until={until}")
for b in buckets:
    note(f"  source bucket {b[0]} {b[1]} hits={b[2]}")

note("correct PIN for each victim, from a different source (XFF 10.20.30.40):")
for v in ["V1", "V2", "V3", "V4", "V5"]:
    login(v, "1234", xff="10.20.30.40")
