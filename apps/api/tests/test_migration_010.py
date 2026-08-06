"""Migration 010's columns and defaults, against a real database.

``alembic upgrade head`` on an empty database proves the DDL parses. This proves
the part that matters for Batch 15: an *existing* league — one written before 010
— comes out the other side on exactly the old behaviour (all UK leagues, both
markets), and the offered-market set cannot be emptied.

Like ``test_migration_009``, it builds and drops its **own** database so it cannot
disturb the suite's shared one. Skipped unless ``DATABASE_URL`` is set.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

OWNER = uuid.uuid4()
LEAGUE = uuid.uuid4()


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
    name = f"coupon_mig010_{uuid.uuid4().hex[:12]}"
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


async def _seed_pre_010(engine: AsyncEngine) -> None:
    """One league, written before the config columns exist."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO profiles (id, display_name, pin_hash, role) "
                "VALUES (:id, :name, 'x', 'player')"
            ),
            {"id": OWNER, "name": f"owner-{uuid.uuid4().hex[:6]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO leagues (id, slug, name, created_by) "
                "VALUES (:id, :slug, :slug, :owner)"
            ),
            {"id": LEAGUE, "slug": f"pre010-{uuid.uuid4().hex[:6]}", "owner": OWNER},
        )


async def test_010_defaults_reproduce_the_pre_batch_behaviour(scratch_engine: AsyncEngine) -> None:
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "009")
    await _seed_pre_010(scratch_engine)
    await _migrate(config, "010")

    async with scratch_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT competitions, offered_markets FROM leagues WHERE id = :id"),
                {"id": LEAGUE},
            )
        ).one()
        assert row.competitions is None, "an existing league defaults to the all-UK group"
        assert list(row.offered_markets) == [
            "MATCH_ODDS",
            "BOTH_TEAMS_TO_SCORE",
        ], "and to both markets, exactly as before Batch 15"


async def test_010_forbids_an_empty_offered_market_set(scratch_engine: AsyncEngine) -> None:
    """The check keeps a league from offering no market at all."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "010")

    async with scratch_engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO profiles (id, display_name, pin_hash, role) "
                "VALUES (:id, :name, 'x', 'player')"
            ),
            {"id": OWNER, "name": f"owner-{uuid.uuid4().hex[:6]}"},
        )
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO leagues (slug, name, created_by, offered_markets) "
                    "VALUES (:slug, :slug, :owner, ARRAY[]::pick_market[])"
                ),
                {"slug": f"empty-{uuid.uuid4().hex[:6]}", "owner": OWNER},
            )


async def test_010_downgrade_drops_the_columns(scratch_engine: AsyncEngine) -> None:
    """The way out of a bad deploy has to be real."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "009")
    await _seed_pre_010(scratch_engine)
    await _migrate(config, "010")
    await _migrate(config, "009", down=True)

    async with scratch_engine.connect() as conn:
        remaining = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'leagues' "
                        "AND column_name IN ('competitions', 'offered_markets')"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [], "both columns are gone after downgrade"
        # The league itself survived the round-trip.
        survived = (
            await conn.execute(text("SELECT count(*) FROM leagues WHERE id = :id"), {"id": LEAGUE})
        ).scalar_one()
        assert survived == 1
