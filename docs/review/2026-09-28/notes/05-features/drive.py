"""Lens 05 drive, phase 1: set up two leagues and re-drive the prior slice over HTTP.

Against the scratch stack started by ../harness/stack.py --name features --api-port 8150
(PUBLIC_SIGNUP_ENABLED=false in its environment, FakeBetfair odds, scheduler off).
In-process parts run against the same scratch database with the app's own models and
services; where a send must be counted, `send_notification` is replaced by a recorder
and the route is called through an in-process ASGI client on the same database.

Run with the gate's venv:
  ~/.cache/the-coupon/ci-local-venv/bin/python drive.py | tee drive-output.txt
Nothing here touches production or a live provider.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

SCR = (
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
os.chdir(SCR)  # never let pydantic-settings read a repo .env
STATE = json.load(open(f"{SCR}/stack-features.json"))
os.environ.update(
    DATABASE_URL=STATE["database_url"],
    JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters",
    JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters",
    SCHEDULER_ENABLED="false",
    ODDS_PROVIDER="fake",
    FRONTEND_ORIGIN="http://127.0.0.1:8150",
    PUBLIC_SIGNUP_ENABLED="false",
)
os.environ.pop("ENVIRONMENT", None)
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import src.scheduler as scheduler  # noqa: E402
import src.services.notification_triggers as triggers  # noqa: E402
from src.auth import create_access_token, hash_pin  # noqa: E402
from src.database import AsyncSessionLocal  # noqa: E402
from src.main import app  # noqa: E402
from src.models.fixture import Fixture  # noqa: E402
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus  # noqa: E402
from src.models.league import League, PickMarket, PickScope  # noqa: E402
from src.models.league_membership import LeagueMembership  # noqa: E402
from src.models.notification import AuditLog  # noqa: E402
from src.models.pick import Pick, PickOutcome, PickStatus  # noqa: E402
from src.models.profile import Profile, UserRole  # noqa: E402
from src.services.betfair import (  # noqa: E402
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import sync_slate, window_for  # noqa: E402

API = STATE["api"]
DAVE_ID = uuid.UUID("39faae39-29a9-4c47-8905-109b2773f31b")  # rename_notice.RENAMED_PROFILE_IDS[2]
SENT: list[dict] = []


def out(label: str, value: object) -> None:
    print(f"## {label}")
    print(json.dumps(value, indent=1, default=str) if not isinstance(value, str) else value)


async def recorder(session, player_id, title, body, **kw):  # noqa: ANN001
    SENT.append({"player_id": str(player_id), "title": title, "body": body,
                 "type": (kw.get("data") or {}).get("type")})
    return 1


def now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def main() -> None:
    triggers.send_notification = recorder  # count, never deliver
    names: dict[str, str] = {}
    async with AsyncSessionLocal() as db:
        profiles = {p.display_name: p for p in (await db.execute(select(Profile))).scalars()}
        profiles["Alice"].role = UserRole.admin  # site admin for the correction/settle routes
        league_a = (await db.execute(select(League).where(League.slug == "the-coupon"))).scalar_one()
        dave = Profile(id=DAVE_ID, display_name="Dave", pin_hash=hash_pin("1234"),
                       role=UserRole.player, timezone="Europe/London")
        db.add(dave)
        await db.flush()
        db.add(LeagueMembership(league_id=league_a.id, player_id=dave.id))
        await db.commit()
        profiles["Dave"] = dave
        ids = {n: p.id for n, p in profiles.items()}
        roles = {n: p.role for n, p in profiles.items()}
        league_a_id = league_a.id
    for n, pid in ids.items():
        names[str(pid)] = n
    tok = {n: create_access_token(ids[n], roles[n]) for n in ids}

    def h(n: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tok[n]}"}

    async with httpx.AsyncClient(base_url=API, timeout=30) as c, httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://in-process", timeout=30
    ) as inproc:
        # ── League A picks (selection scope) ─────────────────────────────────────
        slate = (await c.get("/api/v1/leagues/the-coupon/gameweek/current", headers=h("Alice"))).json()
        gw_a = slate["gameweek_id"]
        fx = {f["home"]: f["fixture_id"] for f in slate["fixtures"]}
        epl, sl2 = fx["Arsenal"], fx["Forfar Athletic"]
        picks_a = [("Alice", epl, "HOME"), ("Bob", epl, "DRAW"), ("Carol", epl, "AWAY"),
                   ("Dave", sl2, "HOME")]
        res = []
        for n, f, o in picks_a:
            r = await c.post("/api/v1/leagues/the-coupon/picks", headers=h(n),
                             json={"fixture_id": f, "market": "MATCH_ODDS", "outcome": o})
            res.append((n, o, r.status_code, r.json().get("odds")))
        out("league A picks (who, outcome, status, frozen odds)", res)

        # ── League B: fixture scope, MATCH_ODDS only, created by Bob over HTTP ──────
        r = await c.post("/api/v1/leagues", headers=h("Bob"), json={
            "name": "Second League", "pick_scope": "fixture", "offered_markets": ["MATCH_ODDS"]})
        league_b = r.json()
        out("create league B", {"status": r.status_code, "slug": league_b.get("slug"),
                                "pick_scope": league_b.get("pick_scope")})
        for n in ("Alice", "Dave"):
            r = await c.post("/api/v1/leagues/join-by-code", headers=h(n),
                             json={"code": league_b["join_code"]})
            out(f"{n} joins B by code", {"status": r.status_code, "body": r.json()})
        async with AsyncSessionLocal() as db:
            lb = await db.get(League, uuid.UUID(league_b["id"]))
            fake = FakeBetfair.with_sample_data()
            gw = await sync_slate(db, lb, await fake.fetch_slate(window_for(lb), SAMPLE_SATURDAY))
            gw.status = GameweekStatus.open
            gw.locks_at_utc = now_naive() + timedelta(hours=2)
            await db.commit()
            gw_b = str(gw.id)
        slug_b = league_b["slug"]
        res = []
        for n, f in (("Bob", epl), ("Alice", sl2)):
            r = await c.post(f"/api/v1/leagues/{slug_b}/picks", headers=h(n),
                             json={"fixture_id": f, "market": "MATCH_ODDS", "outcome": "HOME"})
            res.append((n, r.status_code))
        out("league B picks (Dave deliberately has none)", res)

        # ── Carol mutes league A ────────────────────────────────────────────────
        r = await c.patch("/api/v1/notifications/preferences", headers=h("Carol"),
                          json={"league_mutes": {str(league_a_id): True}})
        out("Carol mutes league A", {"status": r.status_code,
                                      "leagues": r.json().get("leagues")})

        # ── FEAT-B08 path 1: the scheduled sweep ─────────────────────────────────
        r = await c.post("/__e2e/lock")
        fake_sweep = FakeBetfair.with_sample_data()
        fake_sweep.close_markets({SAMPLE_EPL_MATCH_ODDS_MKT: 1001,
                                  SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL})

        async def acquire():  # noqa: ANN202
            return fake_sweep

        scheduler.odds_session.acquire = acquire
        SENT.clear()
        ok = await scheduler.run_settle_gameweeks()
        sweep1 = [dict(s, who=names[s["player_id"]]) for s in SENT]
        out("B08 sweep run 1 (ok, sends)", {"ok": ok, "sends": sweep1})
        SENT.clear()
        ok = await scheduler.run_settle_gameweeks()
        out("B08 sweep run 2 — must send nothing", {"ok": ok, "sends": len(SENT)})

        # ── FEAT-B08 path 2: an admin's hand-entered results (league B) ────────────
        async with AsyncSessionLocal() as db:
            g = await db.get(Gameweek, uuid.UUID(gw_b))
            g.status = GameweekStatus.locked
            g.locks_at_utc = now_naive() - timedelta(seconds=1)
            await db.commit()
        SENT.clear()
        r = await inproc.post(f"/api/v1/admin/results/{gw_b}/settle", headers=h("Alice"), json={
            "results": [{"fixture_id": epl, "home_goals": 2, "away_goals": 1},
                        {"fixture_id": sl2, "home_goals": 0, "away_goals": 0}]})
        out("B08 manual settle league B", {"status": r.status_code, "body": r.json(),
                                           "sends": [dict(s, who=names[s["player_id"]]) for s in SENT]})

        # ── FEAT-A10: can a site admin even find the pick id? ─────────────────────
        own = (await c.get(f"/api/v1/leagues/the-coupon/gameweeks/{gw_a}/pick", headers=h("Bob"))).json()
        bob_pick = own["id"]
        out("Bob's own pick (only Bob can read its id)", own)
        sweep_paths = [
            "/api/v1/leagues/mine", "/api/v1/leagues/the-coupon",
            "/api/v1/leagues/the-coupon/gameweek/current", "/api/v1/leagues/the-coupon/gameweeks",
            f"/api/v1/leagues/the-coupon/coupon?gameweek_id={gw_a}",
            "/api/v1/leagues/the-coupon/standings", "/api/v1/leagues/the-coupon/results",
            f"/api/v1/leagues/the-coupon/players/{ids['Bob']}/profile",
            "/api/v1/leagues/the-coupon/members", "/api/v1/leagues/the-coupon/audit-log",
            "/api/v1/admin/dashboard", "/api/v1/admin/results/pending", "/api/v1/admin/players",
            "/api/v1/admin/leagues", "/api/v1/admin/invites", "/api/v1/me/cross-league-summary",
            "/api/v1/me/export",
        ]
        hits = {}
        for p in sweep_paths:
            r = await c.get(p, headers=h("Alice"))
            hits[p] = {"status": r.status_code, "contains_bob_pick_id": bob_pick in r.text}
        out("A10 every read a site admin has: does any return Bob's pick id?", hits)

        # ── FEAT-A10: correct it (in process so a send would be counted) ──────────
        SENT.clear()
        body = {"home_goals": 1, "away_goals": 1, "reason": "Provider score was wrong; it finished 1-1"}
        r1 = await inproc.post(f"/api/v1/admin/picks/{bob_pick}/correct", headers=h("Alice"), json=body)
        r2 = await inproc.post(f"/api/v1/admin/picks/{bob_pick}/correct", headers=h("Alice"), json=body)
        r3 = await inproc.post(f"/api/v1/admin/picks/{bob_pick}/correct", headers=h("Bob"), json=body)
        out("A10 correction", {"first": [r1.status_code, r1.json()], "repeat": [r2.status_code, r2.json()],
                               "as_member": [r3.status_code, r3.json()], "sends_to_anyone": len(SENT)})
        own2 = (await c.get(f"/api/v1/leagues/the-coupon/gameweeks/{gw_a}/pick", headers=h("Bob"))).json()
        out("A10 Bob's pick after correction — any field saying it was corrected?",
            {"keys_before": sorted(own), "keys_after": sorted(own2),
             "status": own2["status"], "points": own2["points_awarded"]})
        standings = (await c.get("/api/v1/leagues/the-coupon/standings", headers=h("Bob"))).json()
        out("A10 standings after correction", [(s.get("display_name"), s.get("total_points"))
                                               for s in standings])
        audit = (await c.get("/api/v1/leagues/the-coupon/audit-log", headers=h("Alice"))).json()
        out("A10 league A audit log (league admin view) after correction",
            {"total": audit["total"],
             "actions": [(e["action_type"], e["target_table"], (e["changes"] or {}).get("action"))
                         for e in audit["entries"]],
             "mentions_pick_corrected": "pick_corrected" in json.dumps(audit)})
        audit_b = (await c.get(f"/api/v1/leagues/{slug_b}/audit-log", headers=h("Bob"))).json()
        out("A10 league B audit log (its admin, Bob) after a site admin hand-settled it",
            {"total": audit_b["total"],
             "actions": [(e["action_type"], e["target_table"], (e["changes"] or {}).get("action"))
                         for e in audit_b["entries"]],
             "mentions_manual_settlement": "manual_settlement" in json.dumps(audit_b)})
        dash = (await c.get("/api/v1/admin/dashboard", headers=h("Alice"))).json()
        out("A10 site-admin dashboard recent audit (no reason, no league)",
            [(e["action_type"], e["target_table"], e["target_id"]) for e in dash["recent_audit"][:5]])
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(AuditLog).where(AuditLog.target_id == uuid.UUID(bob_pick)))).scalar_one()
            out("A10 the audit row that exists (database)", {"target_table": row.target_table,
                                                             "changes": row.changes})

        # ── FEAT-B07 API half (Carol is deleted through the UI in phase 2) ─────────
        r = await c.get("/api/v1/me/export", headers=h("Bob"))
        ex = r.json()
        out("B07 Bob export", {"status": r.status_code,
                               "content_disposition": r.headers.get("content-disposition"),
                               "top_level_keys": sorted(ex) if isinstance(ex, dict) else None,
                               "mentions_other_members": [n for n in ("Alice", "Carol", "Dave")
                                                          if n in r.text]})
        r_wrong = await c.post("/api/v1/me/delete", headers=h("Bob"), json={"pin": "9999"})
        r_sole = await c.post("/api/v1/me/delete", headers=h("Bob"), json={"pin": "1234"})
        r_site = await c.post("/api/v1/me/delete", headers=h("Alice"), json={"pin": "1234"})
        out("B07 refusals", {"wrong_pin": [r_wrong.status_code, r_wrong.json()],
                             "sole_admin_of_B": [r_sole.status_code, r_sole.json()],
                             "site_admin": [r_site.status_code, r_site.json()]})

        # ── FEAT-A11 API half (the dialog is dismissed in the browser in phase 2) ─────
        rd = await c.get("/api/v1/me/rename-notice", headers=h("Dave"))
        rb = await c.get("/api/v1/me/rename-notice", headers=h("Bob"))
        out("A11 rename notice", {"dave": [rd.status_code, rd.json()], "bob": [rb.status_code, rb.json()]})

        # ── FEAT-A12: signups closed ──────────────────────────────────────────────
        r1 = await c.post("/api/v1/auth/register", json={"display_name": "Newcomer", "pin": "4826"})
        r2 = await c.post("/api/v1/auth/register", json={"display_name": "x", "pin": "4826"})
        r3 = await c.get("/api/v1/config")
        inv = await c.post("/api/v1/leagues/the-coupon/invites", headers=h("Alice"),
                           json={"display_name_hint": "Newcomer"})
        r4 = await c.post("/api/v1/leagues/claim-invite", json={"token": inv.json().get("token")})
        out("A12 signups closed", {
            "register_valid": [r1.status_code, r1.json()],
            "register_invalid_name_still_403_so_state_is_public": [r2.status_code, r2.json()],
            "config_unauthenticated": [r3.status_code, r3.json()],
            "invite_created": inv.status_code,
            "claim_invite_without_account": [r4.status_code, r4.json()],
        })

        # ── FEAT-B09: a settled round from last season ────────────────────────────
        async with AsyncSessionLocal() as db:
            fixture = Fixture(provider_event_id="review05-old", home="Old Home", away="Old Away",
                              kickoff_utc=datetime(2026, 5, 2, 14, 0), competition="English Premier League",
                              competition_id="10932509")
            db.add(fixture)
            old = Gameweek(league_id=league_a_id, starts_on=date(2026, 5, 2),
                           status=GameweekStatus.settled, locks_at_utc=datetime(2026, 5, 2, 13, 30))
            db.add(old)
            await db.flush()
            db.add(GameweekFixture(gameweek_id=old.id, fixture_id=fixture.id))
            db.add(Pick(league_id=league_a_id, gameweek_id=old.id, fixture_id=fixture.id,
                        player_id=ids["Bob"], market=PickMarket.MATCH_ODDS, outcome=PickOutcome.HOME,
                        runner_name="Old Home", odds_at_pick=Decimal("2.00"), status=PickStatus.won,
                        points_awarded=20, pick_scope=PickScope.selection))
            await db.commit()
        res_all = (await c.get("/api/v1/leagues/the-coupon/results", headers=h("Bob"))).json()
        res_q = (await c.get("/api/v1/leagues/the-coupon/results?season=2026", headers=h("Bob"))).json()
        seasons = (await c.get("/api/v1/leagues/the-coupon/seasons", headers=h("Bob"))).json()
        st_now = (await c.get("/api/v1/leagues/the-coupon/standings", headers=h("Bob"))).json()
        st_old = (await c.get("/api/v1/leagues/the-coupon/standings?season=2025", headers=h("Bob"))).json()
        out("B09 results vs standings across a season boundary", {
            "results_starts_on": [r["starts_on"] for r in res_all],
            "results_with_season_2026_param": [r["starts_on"] for r in res_q],
            "seasons": [(s["label"], s["is_current"], s["rounds_settled"]) for s in seasons],
            "standings_current": [(s["display_name"], s["total_points"]) for s in st_now],
            "standings_2025": [(s["display_name"], s["total_points"]) for s in st_old],
        })


asyncio.run(main())
