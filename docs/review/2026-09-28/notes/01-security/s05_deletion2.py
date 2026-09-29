"""Batch 136 part 2: a real deletion (v2), then everything that should be gone, and a
re-registrant under the freed name. v2 is used because erin's per-user delete limit was
spent by the wrong-PIN probe in s04 (5/hour, in-memory)."""

import asyncio
import json
import os
import sys
from decimal import Decimal

from lib import SCRATCH, M, call, ids, login, note, section

state = json.loads((SCRATCH / "stack-sec.json").read_text())
os.environ["DATABASE_URL"] = state["database_url"]
os.environ.setdefault("JWT_ACCESS_SECRET", "review-access-secret-with-at-least-32-characters")
os.environ.setdefault("JWT_REFRESH_SECRET", "review-refresh-secret-with-at-least-32-characters")
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
import uuid  # noqa: E402

from sqlalchemy import select, text  # noqa: E402

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

# NullPool: each asyncio.run() below is a fresh loop, and pooled asyncpg connections
# cannot cross loops.
AsyncSessionLocal = async_sessionmaker(create_async_engine(state["database_url"], poolclass=NullPool))
from src.models.gameweek import GameweekFixture  # noqa: E402
from src.models.pick import Pick, PickOutcome, PickStatus  # noqa: E402
from src.models.league import PickMarket  # noqa: E402

A = M["leagues"]["a"]
V2 = ids("v2")


async def q(sql: str, **params):
    async with AsyncSessionLocal() as db:
        return (await db.execute(text(sql), params)).all()


async def seed_settled_pick() -> None:
    async with AsyncSessionLocal() as db:
        gw = uuid.UUID(A["gameweek_id"])
        if (await db.execute(select(Pick.id).where(Pick.player_id == uuid.UUID(V2)))).first():
            return  # idempotent on re-run
        fx = (await db.execute(select(GameweekFixture.fixture_id).where(GameweekFixture.gameweek_id == gw).limit(1))).scalar_one()
        db.add(Pick(league_id=uuid.UUID(A["id"]), gameweek_id=gw, fixture_id=fx, player_id=uuid.UUID(V2),
                    market=PickMarket.BOTH_TEAMS_TO_SCORE, outcome=PickOutcome.YES, runner_name="Yes",
                    odds_at_pick=Decimal("1.80"), status=PickStatus.won, points_awarded=18))
        await db.commit()


section("136 delete for real: v2")
asyncio.run(seed_settled_pick())
r = login("V2", "1234", xff="10.0.136.12")
acc, ref = r.json()["access_token"], r.json()["refresh_token"]
call("POST", "/api/v1/push/subscribe", bearer=acc,
     body={"endpoint": "https://fcm.googleapis.com/fcm/send/v2-device", "keys": {"p256dh": "x", "auth": "y"}})
call("PUT", f"/api/v1/leagues/{A['slug']}/members/me/display-name", bearer=acc, body={"display_name_override": "Vee Two"})
before = asyncio.run(q("SELECT count(*) FROM refresh_tokens WHERE user_id = :i", i=V2))
note(f"  refresh tokens before: {before}")
call("POST", "/api/v1/me/delete", bearer=acc, body={"pin": "1234"})

section("136 after deletion")
call("GET", "/api/v1/auth/me", bearer=acc)
call("POST", "/api/v1/auth/refresh", body={"refresh_token": ref}, quiet_body=False)
login("V2", "1234", xff="10.0.136.3")
rows = asyncio.run(q("SELECT display_name, pin_hash IS NULL, is_active, deleted_at IS NOT NULL FROM profiles WHERE id = :i", i=V2))
note(f"  profile row: {rows}")
for t in ["refresh_tokens", "push_subscriptions", "league_join_requests", "notification_preferences"]:
    col = "player_id" if t == "league_join_requests" else "user_id"
    note(f"  {t} rows for v2: {asyncio.run(q(f'SELECT count(*) FROM {t} WHERE {col} = :i', i=V2))}")
note(f"  memberships kept: {asyncio.run(q('SELECT league_id, role, deleted_at, display_name_override FROM league_memberships WHERE player_id = :i', i=V2))}")
note(f"  picks kept: {asyncio.run(q('SELECT status, points_awarded FROM picks WHERE player_id = :i', i=V2))}")
st = call("GET", f"/api/v1/leagues/{A['slug']}/standings", "alice", quiet_body=True).json()
note(f"  league A standings names: {[s['display_name'] for s in st]}")
blob = json.dumps(st)
note(f"  'V2' in standings: {'\"V2\"' in blob}; 'Vee Two' in standings: {'Vee Two' in blob}; v2 id in standings: {V2 in blob}")
prof = call("GET", f"/api/v1/leagues/{A['slug']}/players/{V2}/profile", "alice", quiet_body=True)
note(f"  profile of deleted member by id: {prof.status_code} name={prof.json().get('display_name') if prof.status_code == 200 else None}")
mem = call("GET", f"/api/v1/leagues/{A['slug']}/members", "alice", quiet_body=True).json()
note(f"  roster contains deleted member id: {any(m['id'] == V2 for m in mem)}")
lg = call("GET", f"/api/v1/leagues/{A['slug']}", "alice", quiet_body=True).json()
note(f"  league A member_count={lg['member_count']} roster length={len(lg['members'])}")
audit = call("GET", f"/api/v1/leagues/{A['slug']}/audit-log?page_size=100", "alice", quiet_body=True).json()
ablob = json.dumps(audit)
note(f"  'V2'/'Vee Two' anywhere in league A audit log: {'\"V2\"' in ablob or 'Vee Two' in ablob}")

section("136 re-registration under the freed name")
r = call("POST", "/api/v1/auth/register", body={"display_name": "V2", "pin": "8351"},
         headers={"X-Forwarded-For": "10.0.136.4"}, quiet_body=True)
if r.status_code == 201:
    new = r.json()
    note(f"  new id {new['player']['id']} (old {V2}); same id: {new['player']['id'] == V2}")
    na = new["access_token"]
    call("GET", "/api/v1/leagues/mine", bearer=na)
    ex = call("GET", "/api/v1/me/export", bearer=na, quiet_body=True).json()
    note(f"  re-registrant export: leagues={ex['leagues']} picks={ex['picks']} push={ex['push_devices']}")
    call("GET", f"/api/v1/leagues/{A['slug']}/standings", bearer=na)
    call("GET", "/api/v1/me/cross-league-summary", bearer=na, quiet_body=True)
