"""Migration 009's backfill, exercised against a real pre-009 database.

`alembic upgrade head` on an empty database proves the DDL parses; it proves
nothing at all about the data migration, because there is no data to migrate.
Batch 14 moves every pick and fixture in the schema, so the backfill is the part
that can actually lose someone's season.

This builds a throwaway database, migrates it to `008`, writes the shapes that
only exist before the split — one global gameweek shared by two leagues, and the
same real match stored twice under two different gameweeks — then upgrades and
asserts what came out the other side.

Skipped unless ``DATABASE_URL`` is set, like every other Postgres-backed test.
It creates and drops its **own** database rather than using the suite's, so it
cannot disturb tests that share the migrated one.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, time
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

# Two leagues, one shared Saturday, and the same match stored under two gameweeks.
EARLY_DATE = date(2026, 8, 8)
LATE_DATE = date(2026, 8, 15)

LEAGUE_ONE = uuid.uuid4()
LEAGUE_TWO = uuid.uuid4()
OWNER = uuid.uuid4()
PLAYER_TWO = uuid.uuid4()
GAMEWEEK_EARLY = uuid.uuid4()
GAMEWEEK_LATE = uuid.uuid4()
FIXTURE_A = uuid.uuid4()  # event E1 on the early gameweek
FIXTURE_B = uuid.uuid4()  # event E2 on the early gameweek
FIXTURE_A_AGAIN = uuid.uuid4()  # event E1 *again*, on the late gameweek — a duplicate
PICK_ONE = uuid.uuid4()
PICK_TWO = uuid.uuid4()


def _url_for(database: str) -> str:
    """Swap only the database name, leaving everything else intact.

    Parsed rather than string-spliced because a `pgserver` URL carries its unix
    socket directory in a query parameter, and that path contains the separator
    naive splicing would cut on.
    """
    return (
        make_url(os.environ["DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def _alembic_config(url: str) -> Config:
    config = Config(str(_ALEMBIC_INI))
    # migrations/env.py reads DATABASE_URL from the environment, not the ini.
    os.environ["DATABASE_URL"] = url
    return config


async def _migrate(config: Config, revision: str, *, down: bool = False) -> None:
    """Run alembic off the event loop.

    ``migrations/env.py`` drives its own ``asyncio.run``, which cannot nest inside
    the loop pytest-asyncio is already running. A worker thread has no loop of its
    own, so the migration runs there exactly as it does from the command line.
    """
    runner = command.downgrade if down else command.upgrade
    await asyncio.to_thread(runner, config, revision)


@pytest_asyncio.fixture
async def scratch_engine() -> AsyncIterator[AsyncEngine]:
    """A database of this test's own, dropped afterwards whatever happens."""
    original = os.environ["DATABASE_URL"]
    name = f"coupon_mig_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()

    engine = create_async_engine(_url_for(name), future=True)
    try:
        yield engine
    finally:
        await engine.dispose()
        os.environ["DATABASE_URL"] = original
        admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin.dispose()


async def _seed_pre_009(engine: AsyncEngine) -> None:
    """Write the shapes that are only expressible before the split."""
    async with engine.begin() as conn:
        for player, name in ((OWNER, "Owner"), (PLAYER_TWO, "Second")):
            await conn.execute(
                text(
                    "INSERT INTO profiles (id, display_name, pin_hash, role) "
                    "VALUES (:id, :name, 'x', 'player')"
                ),
                {"id": player, "name": f"{name}-{uuid.uuid4().hex[:6]}"},
            )
        for league, slug in ((LEAGUE_ONE, "first"), (LEAGUE_TWO, "second")):
            await conn.execute(
                text(
                    "INSERT INTO leagues (id, slug, name, created_by) "
                    "VALUES (:id, :slug, :slug, :owner)"
                ),
                {"id": league, "slug": f"{slug}-{uuid.uuid4().hex[:6]}", "owner": OWNER},
            )
        await conn.execute(
            text(
                "INSERT INTO league_memberships (league_id, player_id) VALUES "
                "(:l1, :p1), (:l2, :p2)"
            ),
            {"l1": LEAGUE_ONE, "p1": OWNER, "l2": LEAGUE_TWO, "p2": PLAYER_TWO},
        )

        # One *global* gameweek per date — the thing 009 has to split.
        for gameweek, day in ((GAMEWEEK_EARLY, EARLY_DATE), (GAMEWEEK_LATE, LATE_DATE)):
            await conn.execute(
                text(
                    "INSERT INTO gameweeks (id, saturday_date, status, locks_at_utc) "
                    "VALUES (:id, :day, 'open', :locks_at)"
                ),
                {
                    "id": gameweek,
                    "day": day,
                    "locks_at": datetime.combine(day, time(13, 30)),
                },
            )

        for fixture, gameweek, event, home in (
            (FIXTURE_A, GAMEWEEK_EARLY, "E1", "Arsenal"),
            (FIXTURE_B, GAMEWEEK_EARLY, "E2", "Forfar Athletic"),
            (FIXTURE_A_AGAIN, GAMEWEEK_LATE, "E1", "Arsenal"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO fixtures (id, gameweek_id, provider_event_id, home, away, "
                    "kickoff_utc, competition, competition_id) "
                    "VALUES (:id, :gw, :event, :home, 'Someone', :kickoff, "
                    "'A League', 'a-league')"
                ),
                {
                    "id": fixture,
                    "gw": gameweek,
                    "event": event,
                    "home": home,
                    "kickoff": datetime.combine(EARLY_DATE, time(14, 0)),
                },
            )

        # Two leagues holding picks on the SAME global gameweek.
        for pick, league, player, fixture in (
            (PICK_ONE, LEAGUE_ONE, OWNER, FIXTURE_A),
            (PICK_TWO, LEAGUE_TWO, PLAYER_TWO, FIXTURE_B),
        ):
            await conn.execute(
                text(
                    "INSERT INTO picks (id, league_id, gameweek_id, fixture_id, player_id, "
                    "market, outcome, runner_name, odds_at_pick) "
                    "VALUES (:id, :league, :gw, :fixture, :player, 'MATCH_ODDS', 'HOME', "
                    "'Someone', 2.00)"
                ),
                {
                    "id": pick,
                    "league": league,
                    "gw": GAMEWEEK_EARLY,
                    "fixture": fixture,
                    "player": player,
                },
            )


async def test_009_gives_each_league_its_own_rounds_and_pools_the_fixtures(
    scratch_engine: AsyncEngine,
) -> None:
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "008")
    await _seed_pre_009(scratch_engine)
    await _migrate(config, "009")

    async with scratch_engine.connect() as conn:
        # ── Each league got its own round for each date ──────────────────────
        rounds = (
            await conn.execute(
                text("SELECT league_id, starts_on, id FROM gameweeks ORDER BY starts_on")
            )
        ).all()
        assert len(rounds) == 4, "two dates x two leagues"
        by_league_date = {(str(r.league_id), str(r.starts_on)): str(r.id) for r in rounds}
        for league in (LEAGUE_ONE, LEAGUE_TWO):
            for day in ("2026-08-08", "2026-08-15"):
                assert (str(league), day) in by_league_date, f"{league} missing {day}"

        # ── Every pick sits on its own league's round ────────────────────────
        picks = (
            await conn.execute(
                text(
                    "SELECT p.id, p.league_id, g.league_id AS gw_league "
                    "FROM picks p JOIN gameweeks g ON g.id = p.gameweek_id"
                )
            )
        ).all()
        assert len(picks) == 2
        for row in picks:
            assert row.league_id == row.gw_league, "a pick must sit on its own league's round"

        # ── The duplicate match collapsed into one pooled row ────────────────
        events = (
            (await conn.execute(text("SELECT provider_event_id FROM fixtures ORDER BY 1")))
            .scalars()
            .all()
        )
        assert events == ["E1", "E2"], "the same match stored twice must become one row"

        # ── …and it is still on both rounds that played it ───────────────────
        e1_rounds = (
            (
                await conn.execute(
                    text(
                        "SELECT DISTINCT g.starts_on FROM gameweek_fixtures gf "
                        "JOIN fixtures f ON f.id = gf.fixture_id "
                        "JOIN gameweeks g ON g.id = gf.gameweek_id "
                        "WHERE f.provider_event_id = 'E1' ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [str(d) for d in e1_rounds] == [
            "2026-08-08",
            "2026-08-15",
        ], "pooling must not lose the match from either round"

        # No pick was orphaned by the dedupe.
        orphans = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM picks p "
                    "LEFT JOIN fixtures f ON f.id = p.fixture_id WHERE f.id IS NULL"
                )
            )
        ).scalar_one()
        assert orphans == 0

        # ── Both leagues kept today's rule exactly ───────────────────────────
        windows = (
            await conn.execute(
                text(
                    "SELECT slate_start_weekday, slate_start_minute, slate_end_weekday, "
                    "slate_end_minute, lock_offset_minutes FROM leagues"
                )
            )
        ).all()
        assert len(windows) == 2
        for row in windows:
            assert tuple(row) == (5, 900, 5, 900, 30), "defaults must reproduce Saturday 15:00"


async def test_009_round_trips_back_to_a_global_gameweek(scratch_engine: AsyncEngine) -> None:
    """The downgrade has to be real, because it is the way out of a bad deploy."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "008")
    await _seed_pre_009(scratch_engine)
    await _migrate(config, "009")
    await _migrate(config, "008", down=True)

    async with scratch_engine.connect() as conn:
        # One global gameweek per date again, and fixtures re-owned by one.
        dates = (
            (await conn.execute(text("SELECT saturday_date FROM gameweeks ORDER BY 1")))
            .scalars()
            .all()
        )
        assert [str(d) for d in dates] == ["2026-08-08", "2026-08-15"]
        owned = (
            await conn.execute(text("SELECT count(*) FROM fixtures WHERE gameweek_id IS NULL"))
        ).scalar_one()
        assert owned == 0
        # Picks survived and still point at a real gameweek.
        dangling = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM picks p "
                    "LEFT JOIN gameweeks g ON g.id = p.gameweek_id WHERE g.id IS NULL"
                )
            )
        ).scalar_one()
        assert dangling == 0
