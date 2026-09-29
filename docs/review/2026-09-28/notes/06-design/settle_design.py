"""Phase C: a genuinely settled round in the-coupon, with a void leg and an erased member.

Run with the gate's venv while stack_design.py is up (restarted with --keep-data so the
in-memory pick budget is fresh):

    ~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/06-design/settle_design.py

1. Alice picks Arsenal and Hana picks BTTS No over HTTP (real submissions).
2. Kai (holding the Arsenal v Chelsea draw) deletes his own account over HTTP
   (POST /api/v1/me/delete) — the anonymisation Batch 136 ships; his pick stays.
3. POST /__e2e/lock locks the round exactly as the scheduler would.
4. In process, with the app's own service: a FakeBetfair built from the same canned data,
   its books closed with these results, then settle_gameweek_via_provider():
     EPL match odds     Arsenal WINNER               -> Alice won; Jo (Chelsea) and Kai (draw) lost
     EPL BTTS           Yes REMOVED, No WINNER        -> Ivan (Yes) VOID; Hana (No) won
     SL2 match odds     Forfar WINNER                 -> Bob (Brechin) and Lee (draw) lost
     SL2 BTTS           Yes WINNER                    -> Carol won
Scratch database only; nothing reaches a live provider.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
STATE = json.loads((SCRATCH / "stack-design.json").read_text())
API = STATE["api"]
os.environ.update(
    DATABASE_URL=STATE["database_url"],
    JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters",
    JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters",
    SCHEDULER_ENABLED="false",
    ODDS_PROVIDER="fake",
)
os.environ.pop("ENVIRONMENT", None)
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

from sqlalchemy import select, text  # noqa: E402

from src.database import AsyncSessionLocal  # noqa: E402
from src.models.gameweek import Gameweek  # noqa: E402
from src.models.league import League  # noqa: E402
from src.models.pick import Pick  # noqa: E402
from src.services.betfair import FakeBetfair  # noqa: E402
from src.services.scoring import settle_gameweek_via_provider  # noqa: E402

PIN = "1234"


def call(path: str, body: dict | None = None, token: str | None = None, method: str = "POST") -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else b""
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", method=method, data=data if method != "GET" else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def set_books(fb: FakeBetfair, market: str, statuses: dict[int, str]) -> None:
    book = fb._books[market]
    runners = [r.model_copy(update={"status": statuses.get(r.selectionId, "LOSER")}) for r in book.runners]
    fb._books[market] = book.model_copy(update={"status": "CLOSED", "runners": runners})


async def main() -> dict:
    out: dict = {}
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM rate_limit_counters"))
        await db.commit()
    tok = {}
    for name in ("Alice", "Hana", "Kai", "Ivan"):
        s, body = call("/api/v1/auth/login", {"display_name": name, "pin": PIN})
        tok[name] = body["access_token"]
    s, slate = call("/api/v1/leagues/the-coupon/gameweek/current", token=tok["Alice"], method="GET")
    sel = {(f["home"], x["market"], x["outcome"]): (f["fixture_id"], x) for f in slate["fixtures"] for x in f["selections"]}

    def pick(who: str, key: tuple[str, str, str]) -> None:
        fid, x = sel[key]
        s, b = call("/api/v1/leagues/the-coupon/picks",
                    {"fixture_id": fid, "market": x["market"], "outcome": x["outcome"], "odds": x["odds"]},
                    token=tok[who])
        out[f"pick {who} {key}"] = f"{s} {b.get('runner_name') if isinstance(b, dict) else b}"

    pick("Alice", ("Arsenal", "MATCH_ODDS", "HOME"))
    pick("Hana", ("Arsenal", "BOTH_TEAMS_TO_SCORE", "NO"))
    s, b = call("/api/v1/me/delete", {"pin": PIN}, token=tok["Kai"])
    out["Kai deletes own account"] = f"{s} {b}"
    out["lock"] = call("/__e2e/lock")
    fb = FakeBetfair.with_sample_data()
    set_books(fb, "1.100000001", {1001: "WINNER"})
    set_books(fb, "1.100000002", {30246: "REMOVED", 58948: "WINNER"})
    set_books(fb, "1.100000003", {2001: "WINNER"})
    set_books(fb, "1.100000004", {30246: "WINNER"})
    async with AsyncSessionLocal() as db:
        league = (await db.execute(select(League).where(League.slug == "the-coupon"))).scalar_one()
        gw = (await db.execute(select(Gameweek).where(Gameweek.league_id == league.id).order_by(Gameweek.starts_on.desc()))).scalars().first()
        resolved = await settle_gameweek_via_provider(db, fb, gw)
        await db.commit()
        out["settle"] = {"gameweek": str(gw.id), "resolved": resolved, "status": gw.status.value}
        picks = (await db.execute(select(Pick).where(Pick.gameweek_id == gw.id))).scalars().all()
        out["picks"] = sorted(f"{p.runner_name} {p.odds_at_pick} {p.status.value} {p.points_awarded}" for p in picks)
    return out


print(json.dumps(asyncio.run(main()), indent=2, default=str))
