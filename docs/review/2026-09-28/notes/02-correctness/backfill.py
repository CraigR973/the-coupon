"""Season-calendar backfill dry-run (Batch 113) against a SEPARATE scratch database only.

Creates `backfill_check` in the corr pgserver cluster, migrates it, seeds a production-
shaped 2026/27 history (docs/backfills/2026-season-calendar.md): a Saturday league played
8 Aug-26 Sep numbered 1-8, settled with picks; a second league on its own window whose
rounds were numbered by its own count (29 Aug = 1, 5 Sep = 3 after a retired gap);
plus a DELETED league whose only round is 1 Aug (the edge: does a deleted league move
the anchor?). Then runs the real module: --dry-run, --apply (scratch only), --dry-run.
"""

import asyncio
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

import asyncpg
import lib
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.auth import hash_pin
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome, PickScope, PickStatus
from src.models.profile import Profile, UserRole

OUT = "backfill"
BASE = lib.STATE["database_url"]
URL = BASE.replace("/postgres?", "/backfill_check?")


def run(*args: str) -> str:
    env = dict(os.environ, DATABASE_URL=URL, PYTHONPATH=lib.API_DIR)
    r = subprocess.run([sys.executable, *args], cwd=lib.API_DIR, env=env, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip() + f"\n(exit {r.returncode})"


async def main() -> None:
    admin = await asyncpg.connect(BASE.replace("postgresql+asyncpg://", "postgresql://"))
    await admin.execute("drop database if exists backfill_check")
    await admin.execute("create database backfill_check")
    await admin.close()
    lib.out(OUT, "alembic: " + run("-m", "alembic", "upgrade", "head").splitlines()[-1])

    engine = create_async_engine(URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        owner = Profile(display_name="Owner", pin_hash=hash_pin("1234"), role=UserRole.admin)
        db.add(owner)
        await db.flush()
        hibs = League(slug="saturday-league", name="Saturday League", created_by=owner.id)
        mccann = League(slug="own-window", name="Own Window League", created_by=owner.id,
                        slate_start_weekday=5, slate_start_minute=12 * 60 + 30, slate_end_weekday=5, slate_end_minute=12 * 60 + 30)
        gone = League(slug="deleted-test", name="Deleted Test League", created_by=owner.id, deleted_at=datetime(2026, 8, 2))
        db.add_all([hibs, mccann, gone])
        await db.flush()
        fx = Fixture(provider_event_id="bf-1", home="H", away="A", kickoff_utc=datetime(2026, 8, 8, 14),
                     competition="EPL", competition_id="england-premier-league")
        db.add(fx)
        await db.flush()

        def gw(lg, d, n, settled=True):
            return Gameweek(league_id=lg.id, starts_on=d, locks_at_utc=datetime(d.year, d.month, d.day, 13, 30),
                            status=GameweekStatus.settled if settled else GameweekStatus.open, number=n)

        rounds = [gw(hibs, date(2026, 8, 8) + timedelta(weeks=i), i + 1, settled=i < 7) for i in range(8)]
        rounds += [gw(mccann, date(2026, 8, 29), 1), gw(mccann, date(2026, 9, 5), 3)]
        rounds += [gw(gone, date(2026, 8, 1), 1)]
        db.add_all(rounds)
        await db.flush()
        for r in rounds[:7] + rounds[8:10]:
            db.add(Pick(league_id=r.league_id, gameweek_id=r.id, player_id=owner.id, fixture_id=fx.id,
                        market=PickMarket.MATCH_ODDS, outcome=PickOutcome.HOME, runner_name="H", odds_at_pick=2,
                        status=PickStatus.won, points_awarded=20, pick_scope=PickScope.selection))
        await db.commit()
    await engine.dispose()

    lib.out(OUT, "=== --dry-run ===\n" + run("-m", "src.backfill_season_calendar", "--dry-run"))
    lib.out(OUT, "=== --apply (scratch DB backfill_check only) ===\n" + run("-m", "src.backfill_season_calendar", "--apply"))
    lib.out(OUT, "=== --dry-run again ===\n" + run("-m", "src.backfill_season_calendar", "--dry-run"))

    admin = await asyncpg.connect(BASE.replace("postgresql+asyncpg://", "postgresql://"))
    await admin.execute("drop database backfill_check")
    await admin.close()


asyncio.run(main())
