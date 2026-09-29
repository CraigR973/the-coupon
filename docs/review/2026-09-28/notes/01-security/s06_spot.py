"""SEC-01..13 spot checks, Batch 134 (pick correction), Batch 132 (extra weeks)."""

import asyncio
import json
import os
import sys
import uuid

from lib import SCRATCH, M, call, ids, login, note, section

state = json.loads((SCRATCH / "stack-sec.json").read_text())
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

ENGINE_URL = state["database_url"]


async def _q(sql, params):
    eng = create_async_engine(ENGINE_URL, poolclass=NullPool)
    async with eng.connect() as c:
        rows = (await c.execute(text(sql), params)).all()
    await eng.dispose()
    return rows


def q(sql, **params):
    return asyncio.run(_q(sql, params))


section("SEC-04 lockout decays: V3 was locked at 08:00 UTC by s02; correct PIN now")
login("V3", "1234", xff="10.0.4.1")

section("SEC-01 PIN change revokes sessions")
r = login("V3", "1234", xff="10.0.1.1")
acc, ref = r.json()["access_token"], r.json()["refresh_token"]
call("PUT", "/api/v1/auth/me/pin", bearer=acc, body={"current_pin": "1234", "new_pin": "8351"})
call("POST", "/api/v1/auth/refresh", body={"refresh_token": ref}, quiet_body=True)

section("SEC-05 refresh reuse revokes the family")
r = login("V4", "1234", xff="10.0.5.1")
ref0 = r.json()["refresh_token"]
r1 = call("POST", "/api/v1/auth/refresh", body={"refresh_token": ref0}, quiet_body=True)
ref1 = r1.json()["refresh_token"]
call("POST", "/api/v1/auth/refresh", body={"refresh_token": ref0}, quiet_body=True)
call("POST", "/api/v1/auth/refresh", body={"refresh_token": ref1}, quiet_body=True)

section("SEC-06 correlation id")
for cid in ["not-a-uuid", "x" * 500, "3b0b6f4c-6b8e-4b0e-9d7e-3e3a1c2b9f10"]:
    r = call("GET", "/api/v1/health", headers={"X-Correlation-ID": cid}, quiet_body=True)
    note(f"  sent {cid[:40]!r} -> echoed {r.headers.get('x-correlation-id')}")

section("SEC-08 weak PIN refused at registration")
call("POST", "/api/v1/auth/register", body={"display_name": "Newbie", "pin": "1234"},
     headers={"X-Forwarded-For": "10.0.8.1"})

section("SEC-11 no-store on authenticated JSON")
for path in ["/api/v1/auth/me", "/api/v1/leagues/the-coupon/standings", "/api/v1/me/export",
             "/api/v1/leagues/the-coupon/gameweek/current"]:
    r = call("GET", path, "bob", quiet_body=True)
    note(f"  {path}: cache-control={r.headers.get('cache-control')!r} content-encoding={r.headers.get('content-encoding')!r}")

section("SEC-12 push endpoint allowlist")
for ep in ["http://fcm.googleapis.com/fcm/send/a", "https://127.0.0.1/a", "https://[::1]/a",
           "https://169.254.169.254/latest", "https://10.0.0.1/a", "https://fcm.googleapis.com.evil.example/a",
           "https://user@evil.example/a", "https://fcm.googleapis.com./a", "https://evilfcm.googleapis.com.example/a",
           "https://web.push.apple.com/a"]:
    r = call("POST", "/api/v1/push/subscribe", "bob",
             body={"endpoint": ep, "keys": {"p256dh": "x", "auth": "y"}}, quiet_body=True)

section("SEC-03 X-Forwarded-For read from the right")
for n in range(6):
    login("V5", "0000", xff=f"203.0.113.{n}, 10.9.9.9")
rows = q("SELECT bucket_key, hits FROM rate_limit_counters WHERE bucket_key LIKE 'login:v5:%' ORDER BY bucket_key")
note(f"  durable buckets for v5: {rows}")

section("SEC-02 PIN reset request is recorded and pages site admins")
call("POST", "/api/v1/auth/pin/reset-request", body={"display_name": "Bob"},
     headers={"X-Forwarded-For": "10.0.2.1"})
rows = q("SELECT action_type, changes FROM audit_log WHERE target_id = :i ORDER BY timestamp DESC LIMIT 1", i=uuid.UUID(ids("bob")))
note(f"  audit: {rows}")
note(f"  stack log lines: see stack-sec.api.log (admin notification attempts)")

section("Batch 134: pick correction")
pick = q("SELECT id, status, points_awarded FROM picks WHERE player_id = :i", i=uuid.UUID(ids("v2")))
note(f"  target: deleted member v2's settled pick {pick}")
pid = str(pick[0][0])
for who, body in [
    ("alice", {"home_goals": 0, "away_goals": 0, "reason": "league admin tries"}),
    ("bob", {"home_goals": 0, "away_goals": 0, "reason": "member tries"}),
    ("sam", {"home_goals": 100, "away_goals": 0, "reason": "too many goals"}),
    ("sam", {"home_goals": -1, "away_goals": 0, "reason": "negative"}),
    ("sam", {"home_goals": 1, "reason": "one score only"}),
    ("sam", {"home_goals": 1, "away_goals": 1, "reason": "x"}),
    ("sam", {"home_goals": 1, "away_goals": 1, "reason": "ok", "points_awarded": 999, "status": "won", "odds": 50}),
    ("sam", {"home_goals": 0, "away_goals": 0, "reason": "BTTS did not land"}),
    ("sam", {"home_goals": 0, "away_goals": 0, "reason": "repeat"}),
]:
    call("POST", f"/api/v1/admin/picks/{pid}/correct", who, body=body)
note(f"  pick now: {q('SELECT status, points_awarded FROM picks WHERE id = :i', i=uuid.UUID(pid))}")
rows = q("SELECT actor_id, action_type, target_table, changes FROM audit_log WHERE target_id = :i", i=uuid.UUID(pid))
note(f"  audit: {rows}")
lg = call("GET", "/api/v1/leagues/the-coupon/audit-log?page_size=100", "alice", quiet_body=True).json()
note(f"  correction visible in league A's audit log: {any((e.get('changes') or {}).get('action') == 'pick_corrected' for e in lg['entries'])}")
pending = q("SELECT id FROM picks WHERE status = 'pending' LIMIT 1")
if pending:
    call("POST", f"/api/v1/admin/picks/{pending[0][0]}/correct", "sam", body={"void": True, "reason": "pending pick"})

section("Batch 132: extra-week guards (site admin only; member/league admin refused in matrix)")
for body in [{"season": 2026, "starts_on": "2026-08-05"}, {"season": 2026, "starts_on": "2030-01-01"},
             {"season": 2026, "starts_on": "2026-11-11"}]:
    call("POST", "/api/v1/admin/calendar/extra-weeks", "sam", body=body)
    call("POST", "/api/v1/admin/calendar/extra-weeks", "alice", body=body)
