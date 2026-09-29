"""EXPLAIN (ANALYZE, BUFFERS) of the SQL the app actually runs for retirement and settle.

Captures statements + parameters while the real service functions run against the stress
shape, then explains each SELECT twice: as the planner chooses, and with seq scans
disabled (to prove the Batch 146 indexes are usable at all). Writes explain-stress.txt.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import event, select, text  # noqa: E402

from src.database import AsyncSessionLocal, engine  # noqa: E402
from src.models.league import League  # noqa: E402
from src.services.gameweek import retire_stranded_rounds, settleable_gameweeks  # noqa: E402
from src.services.scoring import pending_event_ids  # noqa: E402

HERE = Path(__file__).resolve().parent
CAPTURED: list[tuple[str, object]] = []


def grab(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
    if statement.lstrip().upper().startswith("SELECT"):
        CAPTURED.append((statement, parameters))


async def main() -> None:
    out: list[str] = []
    async with AsyncSessionLocal() as db:
        counts = (await db.execute(text(
            "select (select count(*) from picks), (select count(*) from gameweeks)"))).one()
        out.append(f"shape: picks={counts[0]} gameweeks={counts[1]}")
        league = (await db.execute(select(League).where(League.slug == "stress-50"))).scalar_one()
        event.listen(engine.sync_engine, "before_cursor_execute", grab)
        CAPTURED.clear()
        await retire_stranded_rounds(db, league, date(2026, 9, 29), 2)
        retire_sql = list(CAPTURED)
        CAPTURED.clear()
        rounds = await settleable_gameweeks(db, datetime(2026, 10, 3, 18, 0))
        await pending_event_ids(db, rounds)
        settle_sql = list(CAPTURED)
        event.remove(engine.sync_engine, "before_cursor_execute", grab)
        await db.rollback()
        out.append(f"settleable rounds at 3 Oct 18:00: {len(rounds)}")

    async with engine.connect() as conn:
        for label, captured in (("RETIREMENT", retire_sql), ("SETTLE SWEEP", settle_sql)):
            for statement, params in captured:
                flat = " ".join(statement.split())
                out.append(f"\n=== {label}: {flat[:600]}")
                for mode in ("planner's choice", "enable_seqscan=off"):
                    await conn.exec_driver_sql(
                        "set enable_seqscan = " + ("off" if "off" in mode else "on"))
                    rows = (await conn.exec_driver_sql(
                        "EXPLAIN (ANALYZE, BUFFERS) " + statement, params)).all()
                    out.append(f"--- {mode}")
                    out.extend(r[0] for r in rows)
        await conn.exec_driver_sql("set enable_seqscan = on")
    (HERE / "explain-stress.txt").write_text("\n".join(out) + "\n")
    text_out = "\n".join(out)
    for idx in ("ix_picks_gameweek_id", "ix_gameweeks_starts_on", "Seq Scan on picks",
                "Seq Scan on gameweeks"):
        print(f"{idx}: {text_out.count(idx)} occurrences")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
