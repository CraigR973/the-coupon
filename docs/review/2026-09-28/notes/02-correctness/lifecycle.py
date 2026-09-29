"""Two leagues through lock -> settle -> standings -> coupon -> results -> summary, then
pick correction (134) and self-deletion (136) and what each does to every surface.

State coming in (from seed + completion.py): L1 Sat 3 Oct has picks by Alice, Bob, Carol,
Dan (Erin left). L2 Fri 2 Oct (fixture scope) has none yet.
Jobs: run_lock_gameweeks / run_settle_gameweeks with the scheduler clock pinned, the rich
fake behind odds_session, pushes captured in this process. Reads over HTTP.
"""

import asyncio
import json
from datetime import date, datetime
from unittest import mock

import httpx
import lib
from sqlalchemy import select, text

import src.scheduler as sched
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome, PickScope, PickStatus
from src.models.profile import Profile

FAKE = lib.use_rich_fake()
PUSHES = lib.capture_pushes()
OUT = "lifecycle"


def o(msg: str) -> None:
    lib.out(OUT, msg)


async def main() -> None:
    toks = await lib.tokens()
    async with AsyncSessionLocal() as db:
        ids = {p.display_name: p.id for p in (await db.execute(select(Profile))).scalars()}
        l2 = (await db.execute(select(League).where(League.slug == "l2-friday"))).scalar_one()
        await db.execute(text("update league_memberships set notification_muted=true where league_id=:l and player_id=:p"),
                         {"l": l2.id, "p": ids["Ivy"]})
        # A past-season (2025/26) settled L1 round, so there is an archive to check after Bob leaves.
        l1 = (await db.execute(select(League).where(League.slug == "l1-defaults"))).scalar_one()
        await db.execute(text("delete from gameweeks where league_id=:l and starts_on='2026-05-02'"), {"l": l1.id})
        fx = (await db.execute(select(Fixture).where(Fixture.provider_event_id == "past-1"))).scalar_one_or_none()
        if fx is None:
            fx = Fixture(provider_event_id="past-1", home="Old Home", away="Old Away",
                         kickoff_utc=datetime(2026, 5, 2, 14, 0), competition="English Premier League",
                         competition_id="england-premier-league")
            db.add(fx)
        gw = Gameweek(league_id=l1.id, starts_on=date(2026, 5, 2), locks_at_utc=datetime(2026, 5, 2, 13, 30),
                      status=GameweekStatus.settled, number=99)
        db.add(gw)
        await db.flush()
        db.add_all([
            Pick(league_id=l1.id, gameweek_id=gw.id, player_id=ids["Bob"], fixture_id=fx.id, market=PickMarket.MATCH_ODDS,
                 outcome=PickOutcome.HOME, runner_name="Old Home", odds_at_pick=2.5, status=PickStatus.won,
                 points_awarded=25, pick_scope=PickScope.selection),
            Pick(league_id=l1.id, gameweek_id=gw.id, player_id=ids["Alice"], fixture_id=fx.id, market=PickMarket.MATCH_ODDS,
                 outcome=PickOutcome.AWAY, runner_name="Old Away", odds_at_pick=3.0, status=PickStatus.lost,
                 points_awarded=0, pick_scope=PickScope.selection),
        ])
        await db.commit()

    async with httpx.AsyncClient(timeout=60, base_url=lib.API) as c:
        def h(n: str) -> dict:
            return {"Authorization": f"Bearer {toks[n]}"}

        async def get(path: str, who: str):
            r = await c.get(path, headers=h(who))
            return r.json()

        # ── L2 picks, with a fixture-scope conflict ─────────────────────────────
        cur = await get("/api/v1/leagues/l2-friday/gameweek/current", "Gina")
        l2_gw = cur["gameweek_id"]
        fx2 = [f["fixture_id"] for f in cur["fixtures"]]
        o(f"L2 round {cur['starts_on']} fixtures on card: {len(fx2)} ({[f['competition'] for f in cur['fixtures']]})")
        for who, i, mk, oc in (("Gina", 0, "MATCH_ODDS", "HOME"), ("Alice", 1, "BOTH_TEAMS_TO_SCORE", "YES"), ("Dan", 2, "MATCH_ODDS", "AWAY")):
            r = await c.post("/api/v1/leagues/l2-friday/picks", headers=h(who), json={"fixture_id": fx2[i], "market": mk, "outcome": oc})
            o(f"L2 {who} {mk}/{oc} fixture {i} -> {r.status_code}")
        r = await c.post("/api/v1/leagues/l2-friday/picks", headers=h("Hank"), json={"fixture_id": fx2[0], "market": "BOTH_TEAMS_TO_SCORE", "outcome": "NO"})
        o(f"L2 Hank BTTS/NO on Gina's fixture (fixture scope) -> {r.status_code} {r.json().get('detail')}")
        r = await c.post("/api/v1/leagues/l1-defaults/picks", headers=h("Carol"), json={"fixture_id": fx2[0], "market": "MATCH_ODDS", "outcome": "HOME"})
        o(f"L1 Carol picks an L2-only Friday fixture -> {r.status_code} {r.json().get('detail')}")

    # ── Results: L2 Gina loses, Alice (BTTS yes) wins, Dan (away) wins; L1: Carol's fixture VOID ─
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "select l.slug, pr.display_name, f.provider_event_id, p.market, p.outcome, p.odds_at_pick "
            "from picks p join leagues l on l.id=p.league_id join profiles pr on pr.id=p.player_id "
            "join fixtures f on f.id=p.fixture_id where l.slug in ('l1-defaults','l2-friday') and p.status='pending'"))).all()
    for r in rows:
        o(f"  pick {r.slug} {r.display_name}: {r.provider_event_id} {r.market}/{r.outcome} @ {r.odds_at_pick}")
    carol_eid = next(r.provider_event_id for r in rows if r.slug == "l1-defaults" and r.display_name == "Carol")
    FAKE.void(carol_eid)
    by_eid = {}
    for r in rows:
        by_eid.setdefault(r.provider_event_id, []).append(r)
    for eid, ps in by_eid.items():
        if eid == carol_eid:
            continue
        first = ps[0]
        if first.display_name == "Gina":
            FAKE.result(eid, 0, 1)  # Gina had HOME -> loses
        elif first.market == "BOTH_TEAMS_TO_SCORE":
            FAKE.result(eid, 2, 2)
        elif first.outcome == "AWAY":
            FAKE.result(eid, 0, 2)
        elif first.outcome == "DRAW":
            FAKE.result(eid, 1, 1)
        else:
            FAKE.result(eid, 2, 0)
    for f in lib.richfake.fixtures():  # everything else on 2/3 Oct: a home win
        if f["openDate"].startswith(("2026-10-02", "2026-10-03")) and f["id"] not in by_eid and f["id"] != carol_eid:
            FAKE.result(f["id"], 1, 0)

    # ── Lock and settle with the scheduler's own jobs, clock pinned to Sat 3 Oct 20:00 UTC ─
    with mock.patch.object(sched, "_utc_now", lambda: datetime(2026, 10, 3, 20, 0)):
        o(f"run_lock_gameweeks -> {await sched.run_lock_gameweeks()}")
        o(f"run_settle_gameweeks -> {await sched.run_settle_gameweeks()}")
        n1 = len(PUSHES)
        o(f"run_settle_gameweeks (again) -> {await sched.run_settle_gameweeks()}; new pushes on the re-run: {len(PUSHES) - n1}")
    for p in PUSHES:
        if p.get("data", {}).get("type") == "round_settled":
            o(f"  settle push -> {p['endpoint'].rsplit('/', 1)[1]:6} [{p['title']}] {p['body']}")
    json.dump(PUSHES, open(lib.NOTES / "out" / "lifecycle-pushes.json", "w"), indent=1)

    async with httpx.AsyncClient(timeout=60, base_url=lib.API) as c:
        def h(n: str) -> dict:
            return {"Authorization": f"Bearer {toks[n]}"}

        async def get(path: str, who: str):
            return (await c.get(path, headers=h(who))).json()

        async def surfaces(tag: str) -> None:
            gl = await get("/api/v1/leagues/l1-defaults/gameweeks", "Alice")
            l1_gw = next(g["gameweek_id"] for g in gl if g["starts_on"] == "2026-10-03")
            cp = await get(f"/api/v1/leagues/l1-defaults/coupon?gameweek_id={l1_gw}", "Alice")
            o(f"[{tag}] L1 coupon: legs {cp['leg_count']} void {cp.get('void_leg_count')} combined {cp['combined_odds']} all_won {cp['all_won']} :: "
              + ", ".join(f"{lg['player_name']} {lg['status']} {lg['odds']} {lg['points_awarded']}" for lg in cp["legs"]))
            res = await get("/api/v1/leagues/l1-defaults/results", "Alice")
            o(f"[{tag}] L1 results: " + " | ".join(f"{r['starts_on']} legs {r['leg_count']} combined {r['combined_odds']} winners {r['winner_names']} {r['winner_points']} won {r.get('picks_won')}" for r in res))
            for who in ("Alice", "Carol", "Dan"):
                s = await get("/api/v1/me/cross-league-summary", who)
                pl = {e["slug"]: e for e in s["per_league"]}
                lr = pl.get("l1-defaults", {}).get("last_result") or {}
                o(f"[{tag}] {who} summary: pts {s['total_points']} won {s['picks_won']}/{s['picks_played']} priced {s.get('picks_priced')} win_rate {s['win_rate_pct']} | L1 last_result legs {lr.get('leg_count')} combined {lr.get('combined_odds')} my_pick {(lr.get('my_pick') or {}).get('status')} | keys has avg_rank: {'avg_rank' in s}")
            for slug in ("l1-defaults", "l2-friday"):
                st = await get(f"/api/v1/leagues/{slug}/standings", "Alice")
                o(f"[{tag}] {slug} standings: " + ", ".join(f"#{r['rank']} {r['display_name']} {r['total_points']} ({r['picks_won']}/{r['picks_played']}, rate {r['win_rate_pct']})" for r in st))
            arch = await get("/api/v1/leagues/l1-defaults/standings?season=2025", "Alice")
            o(f"[{tag}] L1 archive 2025/26: " + ", ".join(f"#{r['rank']} {r['display_name']} {r['total_points']}" for r in arch))
            prof = await get(f"/api/v1/leagues/l1-defaults/players/{ids_http['Carol']}/profile", "Alice")
            o(f"[{tag}] Carol's L1 profile win_rate {prof.get('win_rate_pct')} won {prof.get('picks_won')}/{prof.get('picks_played')}")

        async with AsyncSessionLocal() as db:
            ids_http = {p.display_name: str(p.id) for p in (await db.execute(select(Profile))).scalars()}
        await surfaces("after settle")

        # ── Pick correction (Batch 134) ───────────────────────────────────────────
        await c.delete("/__corr/pushes")
        async with AsyncSessionLocal() as db:
            pk = {r.display_name: r for r in (await db.execute(text(
                "select pr.display_name, p.id, p.status, p.points_awarded, p.market, p.outcome from picks p join profiles pr on pr.id=p.player_id "
                "join gameweeks g on g.id=p.gameweek_id join leagues l on l.id=p.league_id where l.slug='l1-defaults' and g.starts_on='2026-10-03'"))).all()}
        o(f"L1 picks before correction: {[(n, r.status, r.points_awarded, r.outcome) for n, r in pk.items()]}")
        # The true result of Bob's fixture: whichever score flips his result.
        bob = pk["Bob"]
        flip = {"HOME": (0, 1), "AWAY": (1, 0), "DRAW": (2, 1)} if bob.status == "won" else {"HOME": (3, 0), "AWAY": (0, 3), "DRAW": (1, 1)}
        hg, ag = flip[bob.outcome]
        body = {"home_goals": hg, "away_goals": ag, "reason": "provider mis-settled Bob's fixture"}
        r1 = await c.post(f"/api/v1/admin/picks/{bob.id}/correct", headers=h("Root"), json=body)
        r2 = await c.post(f"/api/v1/admin/picks/{bob.id}/correct", headers=h("Root"), json=body)
        o(f"correct Bob {hg}-{ag}: {r1.status_code} {r1.json()} ; repeat: {r2.status_code} changed={r2.json().get('changed')}")
        r3 = await c.post(f"/api/v1/admin/picks/{bob.id}/correct", headers=h("Alice"), json=body)
        o(f"league admin (not site admin) correcting: {r3.status_code}")
        # Two admins correcting Dan's pick at once, with different results.
        dan = pk["Dan"]
        a = {"home_goals": 5, "away_goals": 0, "reason": "admin A says home"}
        b = {"home_goals": 0, "away_goals": 5, "reason": "admin B says away"}
        ra, rb = await asyncio.gather(
            c.post(f"/api/v1/admin/picks/{dan.id}/correct", headers=h("Root"), json=a),
            c.post(f"/api/v1/admin/picks/{dan.id}/correct", headers=h("Root"), json=b))
        o(f"concurrent corrections of Dan: A {ra.status_code} {ra.json()} | B {rb.status_code} {rb.json()}")
        async with AsyncSessionLocal() as db:
            audits = (await db.execute(text("select changes->>'reason', changes->'before', changes->'after' from audit_log where changes->>'action'='pick_corrected' order by timestamp"))).all()
            final = (await db.execute(text("select status, points_awarded from picks where id=:i"), {"i": dan.id})).one()
        o(f"audit rows: {audits}")
        o(f"Dan final: {tuple(final)}")
        o(f"pushes sent by the corrections: {(await c.get('/__corr/pushes')).json()}")
        await surfaces("after correction")

        # ── Bob deletes his account (Batch 136) ───────────────────────────────────
        r = await c.post("/api/v1/me/delete", headers=h("Bob"), json={"pin": "1234"})
        o(f"Bob deletes his account -> {r.status_code}")
        await surfaces("after Bob erased")


asyncio.run(main())
