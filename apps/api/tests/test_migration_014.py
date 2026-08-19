"""Migration 014's backfill, against a real database.

Batch 41. ``alembic upgrade head`` on an empty database proves the DDL parses; this
proves the part that carries meaning — that existing rounds come out numbered per
league, per season, in ``starts_on`` order. The season expression is written in SQL
rather than imported from :func:`src.services.football_provider.season_for`, so it is
the one thing that can silently disagree with the application, and this is what
holds the two together.

Like ``test_migration_012``, it builds and drops its **own** database so it cannot
disturb the suite's shared one. Skipped unless ``DATABASE_URL`` is set.
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

OWNER = uuid.uuid4()
LEAGUE_A = uuid.uuid4()
LEAGUE_B = uuid.uuid4()


def _url_for(database: str) -> str:
    return (
        make_url(os.environ["DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def _alembic_config(url: str) -> Config:
    config = Config(str(_ALEMBIC_INI))
    os.environ["DATABASE_URL"] = url  # migrations/env.py reads it from the environment
    return config


async def _migrate(config: Config, revision: str, *, down: bool = False) -> None:
    runner = command.downgrade if down else command.upgrade
    await asyncio.to_thread(runner, config, revision)


@pytest_asyncio.fixture
async def scratch_engine() -> AsyncIterator[AsyncEngine]:
    """A database of this test's own, dropped afterwards whatever happens."""
    original = os.environ["DATABASE_URL"]
    name = f"coupon_mig014_{uuid.uuid4().hex[:12]}"
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


async def _seed_pre_014(engine: AsyncEngine) -> None:
    """Two leagues of rounds spanning a season boundary, inserted out of date order.

    Insertion order is deliberately not date order: the backfill must number by
    ``starts_on``, not by however the rows happen to sit in the heap.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO profiles (id, display_name, pin_hash, role) "
                "VALUES (:id, :name, 'x', 'player')"
            ),
            {"id": OWNER, "name": f"owner-{uuid.uuid4().hex[:6]}"},
        )
        for league in (LEAGUE_A, LEAGUE_B):
            await conn.execute(
                text(
                    "INSERT INTO leagues (id, slug, name, created_by) "
                    "VALUES (:id, :slug, :slug, :owner)"
                ),
                {"id": league, "slug": f"pre014-{uuid.uuid4().hex[:6]}", "owner": OWNER},
            )

        rounds = [
            # League A, season 2026 (July 2026 - June 2027), inserted middle-first.
            (LEAGUE_A, date(2026, 9, 5)),
            (LEAGUE_A, date(2026, 8, 8)),
            (LEAGUE_A, date(2027, 1, 16)),
            # League A, season 2027 — restarts at 1.
            (LEAGUE_A, date(2027, 8, 14)),
            # League B numbers independently of A.
            (LEAGUE_B, date(2026, 8, 8)),
            (LEAGUE_B, date(2026, 8, 15)),
        ]
        for league, starts_on in rounds:
            await conn.execute(
                text(
                    "INSERT INTO gameweeks (id, league_id, starts_on, status, locks_at_utc) "
                    "VALUES (:id, :league, :starts_on, 'open', :locks_at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "league": league,
                    "starts_on": starts_on,
                    "locks_at": datetime.combine(starts_on, time(13, 30)),
                },
            )


async def _numbers(engine: AsyncEngine, league: uuid.UUID) -> list[tuple[str, int | None]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT starts_on, number FROM gameweeks "
                "WHERE league_id = :league ORDER BY starts_on"
            ),
            {"league": league},
        )
        return [(str(row.starts_on), row.number) for row in rows.all()]


async def test_014_numbers_each_league_season_from_one(scratch_engine: AsyncEngine) -> None:
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "013")
    await _seed_pre_014(scratch_engine)
    await _migrate(config, "014")

    assert await _numbers(scratch_engine, LEAGUE_A) == [
        ("2026-08-08", 1),
        ("2026-09-05", 2),
        ("2027-01-16", 3),  # January is still season 2026 — the rollover is July
        ("2027-08-14", 1),  # a new season restarts at 1
    ]
    # A second league's numbering is its own; the same Saturday is Gameweek 1 in both.
    assert await _numbers(scratch_engine, LEAGUE_B) == [
        ("2026-08-08", 1),
        ("2026-08-15", 2),
    ]


async def test_014_downgrade_drops_the_column(scratch_engine: AsyncEngine) -> None:
    """Losing the numbering is recoverable: it is a pure function of league and date."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "013")
    await _seed_pre_014(scratch_engine)
    await _migrate(config, "014")
    await _migrate(config, "013", down=True)

    async with scratch_engine.connect() as conn:
        columns = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'gameweeks'"
            )
        )
        assert "number" not in {row.column_name for row in columns.all()}
        surviving = await conn.execute(
            text("SELECT count(*) AS n FROM gameweeks WHERE league_id = :league"),
            {"league": LEAGUE_A},
        )
        assert surviving.one().n == 4, "downgrade must not lose rounds"
