"""Statement counts, row volume and bytes for the hot endpoints, in process.

Load-independent evidence first: SQL statements per request (a before_cursor_execute
listener on the app's own engine), rows returned, response bytes with and without
`Accept-Encoding: gzip`. DB milliseconds are recorded but are load-dependent.

Statements are split at the moment the final response body is sent, so a
BackgroundTasks fan-out (Batch 162) is counted separately from the member's request.

    DATABASE_URL=... python measure_api.py <label> [--timings N]

Run with the gate's venv and PYTHONPATH=apps/api. Writes `api-<label>.json` beside itself.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("JWT_ACCESS_SECRET", "review-access-secret-with-at-least-32-characters")
os.environ.setdefault("JWT_REFRESH_SECRET", "review-refresh-secret-with-at-least-32-characters")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ODDS_PROVIDER"] = "fake"
os.environ.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:4340")
os.environ.pop("ENVIRONMENT", None)
assert "python_PostgresServer" in os.environ["DATABASE_URL"], "scratch DB only"
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event, select, text  # noqa: E402

from src.auth import create_access_token  # noqa: E402
from src.database import AsyncSessionLocal, engine  # noqa: E402
from src.deps import get_odds_provider, get_optional_odds_provider  # noqa: E402
from src.main import app  # noqa: E402
from src.models.profile import Profile  # noqa: E402
from src.services.odds_provider import (  # noqa: E402
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    Outcome,
    Selection,
    Slate,
)


class PricedFake(OddsProvider):
    """Prices every event it is asked about: Match Odds H/D/A and BTTS Yes/No."""

    def __init__(self) -> None:
        self.odds_calls = 0

    async def login(self) -> str:
        return ""

    async def keep_alive(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch_slate(self, window, starts_on, *, competition_ids=None) -> Slate:  # noqa: ANN001
        return Slate(starts_on=starts_on, fixtures=[])

    async def fetch_competitions(self) -> list[Competition]:
        return []

    async def fetch_odds(self, event_ids, *, max_age_seconds=None) -> list[FixtureOdds]:  # noqa: ANN001
        self.odds_calls += 1
        out = []
        for ev in event_ids:
            home, away = f"Home {ev}", f"Away {ev}"
            out.append(FixtureOdds(provider_event_id=ev, home=home, away=away, selections=[
                Selection(market=Market.MATCH_ODDS, outcome=Outcome.HOME, runner_name=home, price=Decimal("2.10")),
                Selection(market=Market.MATCH_ODDS, outcome=Outcome.DRAW, runner_name="The Draw", price=Decimal("3.40")),
                Selection(market=Market.MATCH_ODDS, outcome=Outcome.AWAY, runner_name=away, price=Decimal("3.25")),
                Selection(market=Market.BOTH_TEAMS_TO_SCORE, outcome=Outcome.YES, runner_name="Yes", price=Decimal("1.83")),
                Selection(market=Market.BOTH_TEAMS_TO_SCORE, outcome=Outcome.NO, runner_name="No", price=Decimal("1.95")),
            ]))
        return out

    async def settle(self, event_ids) -> list[EventSettlement]:  # noqa: ANN001
        return []


FAKE = PricedFake()
app.dependency_overrides[get_odds_provider] = lambda: FAKE
app.dependency_overrides[get_optional_odds_provider] = lambda: FAKE


class Recorder:
    def __init__(self) -> None:
        self.statements: list[tuple[str, float, int]] = []
        self._start: float | None = None
        self.body_at_index: int | None = None

    def before(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG002
        self._start = time.perf_counter()

    def after(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG002
        ms = (time.perf_counter() - (self._start or time.perf_counter())) * 1000
        rows = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        self.statements.append((statement, ms, rows))


REC = Recorder()
event.listen(engine.sync_engine, "before_cursor_execute", REC.before)
event.listen(engine.sync_engine, "after_cursor_execute", REC.after)


class BodyMark:
    """Marks the statement index when the final body message leaves the app."""

    def __init__(self, inner) -> None:  # noqa: ANN001
        self.inner = inner

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        async def marked(message):  # noqa: ANN001
            if message["type"] == "http.response.body" and not message.get("more_body"):
                if REC.body_at_index is None:
                    REC.body_at_index = len(REC.statements)
            await send(message)

        await self.inner(scope, receive, marked)


async def tokens() -> dict[str, tuple[str, str]]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Profile))).scalars().all()
        return {p.display_name: (str(p.id), create_access_token(p.id, p.role)) for p in rows}


async def one(client: AsyncClient, method: str, url: str, token: str, body=None, gzip=True):  # noqa: ANN001
    REC.statements.clear()
    REC.body_at_index = None
    headers = {"Authorization": f"Bearer {token}"}
    headers["Accept-Encoding"] = "gzip" if gzip else "identity"
    t0 = time.perf_counter()
    resp = await client.request(method, url, headers=headers, json=body)
    wall = (time.perf_counter() - t0) * 1000
    stmts = list(REC.statements)
    split = REC.body_at_index if REC.body_at_index is not None else len(stmts)
    return {
        "status": resp.status_code,
        "stmts": split,
        "background_stmts": len(stmts) - split,
        "rows": sum(r for _, _, r in stmts[:split]),
        "db_ms": round(sum(ms for _, ms, _ in stmts[:split]), 1),
        "wall_ms": round(wall, 1),
        "bytes_raw": len(resp.content),
        "bytes_wire": resp.num_bytes_downloaded,
        "content_encoding": resp.headers.get("content-encoding"),
        "vary": resp.headers.get("vary"),
        "json": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None,
        "sql": [s for s, _, _ in stmts[:split]],
    }


async def main() -> None:
    label = sys.argv[1]
    timings = int(sys.argv[sys.argv.index("--timings") + 1]) if "--timings" in sys.argv else 0
    toks = await tokens()
    async with AsyncSessionLocal() as db:
        slugs = [r for (r,) in (await db.execute(text("select slug from leagues order by slug"))).all()]
        open_fixture = (await db.execute(text(
            "select gf.fixture_id from gameweek_fixtures gf join gameweeks g on g.id=gf.gameweek_id "
            "join leagues l on l.id=g.league_id where l.slug='the-coupon' and g.status='open' "
            "and gf.fixture_id not in (select fixture_id from picks p where p.gameweek_id=g.id) "
            "order by gf.fixture_id limit 1"))).scalar()
    results: dict[str, dict] = {}
    transport = ASGITransport(app=BodyMark(app))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        plan = [
            ("home summary (Solo, 1 league)", "GET", "/api/v1/me/cross-league-summary", "Solo", None),
            ("home summary (Alice, 3 leagues)", "GET", "/api/v1/me/cross-league-summary", "Alice", None),
            ("current round / slate (264 fixtures)", "GET", "/api/v1/leagues/the-coupon/gameweek/current", "Alice", None),
            ("combined coupon", "GET", "/api/v1/leagues/the-coupon/coupon", "Alice", None),
            ("standings (no season)", "GET", "/api/v1/leagues/the-coupon/standings", "Alice", None),
            ("standings (season 2026)", "GET", "/api/v1/leagues/the-coupon/standings?season=2026", "Alice", None),
            ("results", "GET", "/api/v1/leagues/the-coupon/results", "Alice", None),
            ("rounds list", "GET", "/api/v1/leagues/the-coupon/gameweeks", "Alice", None),
            ("seasons", "GET", "/api/v1/leagues/the-coupon/seasons", "Alice", None),
            ("league detail", "GET", "/api/v1/leagues/the-coupon", "Alice", None),
            ("leagues mine", "GET", "/api/v1/leagues/mine", "Alice", None),
            ("account export (Alice)", "GET", "/api/v1/me/export", "Alice", None),
        ]
        if "stress-50" in slugs:
            plan += [
                ("home summary (Stress 02, 50-member league)", "GET", "/api/v1/me/cross-league-summary", "Stress 02", None),
                ("current round / slate, stress league", "GET", "/api/v1/leagues/stress-50/gameweek/current", "Stress 02", None),
                ("combined coupon, stress league", "GET", "/api/v1/leagues/stress-50/coupon", "Stress 02", None),
                ("standings (no season), stress", "GET", "/api/v1/leagues/stress-50/standings", "Stress 02", None),
                ("standings (season 2025), stress", "GET", "/api/v1/leagues/stress-50/standings?season=2025", "Stress 02", None),
                ("results, stress", "GET", "/api/v1/leagues/stress-50/results", "Stress 02", None),
                ("rounds list, stress", "GET", "/api/v1/leagues/stress-50/gameweeks", "Stress 02", None),
                ("seasons, stress", "GET", "/api/v1/leagues/stress-50/seasons", "Stress 02", None),
                ("account export (Stress 02, 40 settled picks)", "GET", "/api/v1/me/export", "Stress 02", None),
            ]
        for name, method, url, who, body in plan:
            r = await one(client, method, url, toks[who][1], body)
            ident = await one(client, method, url, toks[who][1], body, gzip=False)
            r["bytes_identity"] = ident["bytes_raw"]
            r["stmts_second_call"] = ident["stmts"]
            if timings:
                walls = []
                for _ in range(timings):
                    walls.append((await one(client, method, url, toks[who][1], body))["wall_ms"])
                walls.sort()
                r["p50_ms"] = round(statistics.median(walls), 1)
                r["p95_ms"] = round(walls[max(0, int(len(walls) * 0.95) - 1)], 1)
            results[name] = r
        # Pick submit — one real claim on the open round (writes).
        if open_fixture:
            body = {"fixture_id": str(open_fixture), "market": "MATCH_ODDS", "outcome": "HOME", "odds": "2.10"}
            who = "Solo"
            r = await one(client, "POST", "/api/v1/leagues/the-coupon/picks", toks[who][1], body)
            results["pick submit (Solo, 12-member league)"] = r
    out = {
        "label": label,
        "uptime": subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip(),
        "results": {k: {kk: vv for kk, vv in v.items() if kk not in ("json", "sql")} for k, v in results.items()},
    }
    (HERE / f"api-{label}.json").write_text(json.dumps(out, indent=2, default=str))
    (HERE / f"api-{label}-sql.txt").write_text("\n\n".join(
        f"## {k}  ({v['stmts']} stmts)\n" + "\n".join(f"{i+1}. {' '.join(s.split())[:400]}" for i, s in enumerate(v["sql"]))
        for k, v in results.items()))
    print(f"{'endpoint':52s} st bg stmt rows  db_ms  identity  wire   enc")
    for k, v in results.items():
        print(f"{k:52s} {v['status']} {v['background_stmts']:2d} {v['stmts']:4d} {v['rows']:5d} {v['db_ms']:6.1f} "
              f"{v.get('bytes_identity', 0):8d} {v['bytes_wire']:6d} {v['content_encoding']}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
