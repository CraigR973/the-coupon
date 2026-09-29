"""Batch 136: account deletion and data export, attacked as an adversarial member.

Uses X-Forwarded-For to give each login its own source address: the local stack has no
proxy in front, so the rightmost XFF hop is what `client_address` reads (see SEC-03).
"""

import asyncio
import json
import os
import sys

from lib import SCRATCH, M, call, ids, login, note, section

state = json.loads((SCRATCH / "stack-sec.json").read_text())
os.environ["DATABASE_URL"] = state["database_url"]
os.environ.setdefault("JWT_ACCESS_SECRET", "review-access-secret-with-at-least-32-characters")
os.environ.setdefault("JWT_REFRESH_SECRET", "review-refresh-secret-with-at-least-32-characters")
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import text  # noqa: E402

from src.database import AsyncSessionLocal  # noqa: E402


async def q(sql: str, **params):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql), params)).all()


B = M["leagues"]["b"]
A = M["leagues"]["a"]

section("136 export: what bob's export contains")
r = call("GET", "/api/v1/me/export", "bob", quiet_body=True)
body = r.json()
note(f"  headers: content-disposition={r.headers.get('content-disposition')!r} cache-control={r.headers.get('cache-control')!r}")
note(f"  top-level keys: {sorted(body)}")
blob = json.dumps(body)
others = [n for n in ["Alice", "Carol", "Erin", "Dave", "Hank", "Sadie", "Gary"] if n in blob]
note(f"  other members' names present in bob's export: {others}")
note(f"  other members' ids present: {[k for k, v in M['actors'].items() if k != 'bob' and v['id'] in blob]}")
note("  no id parameter exists on /me/export or /me/delete (routes.tsv) — nothing to substitute")

section("136 delete: erin, who has a pick, a refresh token and a push subscription")
r = login("Erin", "1234", xff="10.0.136.1")
erin_access = r.json()["access_token"]
erin_refresh = r.json()["refresh_token"]
slate = call("GET", f"/api/v1/leagues/{B['slug']}/gameweek/current", bearer=erin_access, quiet_body=True).json()
fx = slate["fixtures"][0]
sel = next(s for s in fx["selections"] if s["market"] == "MATCH_ODDS" and s["outcome"] == "HOME")
call("POST", f"/api/v1/leagues/{B['slug']}/picks", bearer=erin_access,
     body={"fixture_id": fx["fixture_id"], "market": "MATCH_ODDS", "outcome": "HOME", "odds": sel["odds"]},
     quiet_body=True)
call("POST", "/api/v1/push/subscribe", bearer=erin_access,
     body={"endpoint": "https://fcm.googleapis.com/fcm/send/erin-device", "keys": {"p256dh": "x", "auth": "y"}})
note("wrong PIN x6 (limit is 5/hour, in-memory, per user):")
for pin in ["0001", "0002", "0003", "0004", "0005", "0006"]:
    call("POST", "/api/v1/me/delete", bearer=erin_access, body={"pin": pin})
prof = asyncio.run(q("SELECT failed_login_count, locked_until FROM profiles WHERE id = :i", i=ids("erin")))
note(f"  erin's failed_login_count/locked_until after 5 wrong delete PINs: {prof}")

note("site admin self-delete, and sole-admin refusal:")
call("POST", "/api/v1/me/delete", "sam", body={"pin": "1234"})
call("POST", "/api/v1/me/delete", "alice", body={"pin": "1234"})
