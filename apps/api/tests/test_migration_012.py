"""Migration 012's columns, enum value and check, against a real database.

``alembic upgrade head`` on an empty database proves the DDL parses. This proves
the parts that matter for Batch 27: a league and a round written *before* 012 come
out the other side on exactly the old behaviour (no announced opening, claimable
from publication), the new ``scheduled`` state is usable, a claim period that would
close before it opened is refused, and the downgrade — which cannot drop an enum
value — still gets back to the pre-batch shape without losing a round.

Like ``test_migration_010``, it builds and drops its **own** database so it cannot
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
GAMEWEEK = uuid.uuid4()


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
    name = f"coupon_mig012_{uuid.uuid4().hex[:12]}"
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


async def _seed_owner(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO profiles (id, display_name, pin_hash, role) "
                "VALUES (:id, :name, 'x', 'player')"
            ),
            {"id": OWNER, "name": f"owner-{uuid.uuid4().hex[:6]}"},
        )


async def _seed_pre_012(engine: AsyncEngine) -> None:
    """One league and one round, both written before the pick-open columns exist."""
    await _seed_owner(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO leagues (id, slug, name, created_by) "
                "VALUES (:id, :slug, :slug, :owner)"
            ),
            {"id": LEAGUE, "slug": f"pre012-{uuid.uuid4().hex[:6]}", "owner": OWNER},
        )
        await conn.execute(
            text(
                "INSERT INTO gameweeks (id, league_id, starts_on, status, locks_at_utc) "
                "VALUES (:id, :league, DATE '2026-08-08', 'open', TIMESTAMP '2026-08-08 13:30')"
            ),
            {"id": GAMEWEEK, "league": LEAGUE},
        )


async def test_012_leaves_existing_rows_on_the_pre_batch_behaviour(
    scratch_engine: AsyncEngine,
) -> None:
    """No backfill: NULL on both columns *is* "claimable as soon as it is published"."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "011")
    await _seed_pre_012(scratch_engine)
    await _migrate(config, "012")

    async with scratch_engine.connect() as conn:
        league = (
            await conn.execute(
                text("SELECT pick_open_offset_minutes FROM leagues WHERE id = :id"),
                {"id": LEAGUE},
            )
        ).one()
        assert league.pick_open_offset_minutes is None, "no league announces an opening"
        round_ = (
            await conn.execute(
                text("SELECT status, picks_open_at_utc FROM gameweeks WHERE id = :id"),
                {"id": GAMEWEEK},
            )
        ).one()
        assert round_.picks_open_at_utc is None
        assert round_.status == "open", "an existing round stays claimable"


async def test_012_admits_the_scheduled_state(scratch_engine: AsyncEngine) -> None:
    """The new enum value has to be writable, not merely declared."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "011")
    await _seed_pre_012(scratch_engine)
    await _migrate(config, "012")

    async with scratch_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE gameweeks SET status = 'scheduled', "
                "picks_open_at_utc = TIMESTAMP '2026-08-01 14:00' WHERE id = :id"
            ),
            {"id": GAMEWEEK},
        )
    async with scratch_engine.connect() as conn:
        status = (
            await conn.execute(
                text("SELECT status FROM gameweeks WHERE id = :id"), {"id": GAMEWEEK}
            )
        ).scalar_one()
        assert status == "scheduled"


async def test_012_forbids_a_claim_period_that_closes_before_it_opens(
    scratch_engine: AsyncEngine,
) -> None:
    """Picks opening later than they lock is a round that could never be played."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "012")
    await _seed_owner(scratch_engine)

    async with scratch_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO leagues "
                    "(slug, name, created_by, lock_offset_minutes, pick_open_offset_minutes) "
                    "VALUES (:slug, :slug, :owner, 30, 29)"
                ),
                {"slug": f"bad-{uuid.uuid4().hex[:6]}", "owner": OWNER},
            )


async def test_012_admits_a_league_that_announces_no_opening(
    scratch_engine: AsyncEngine,
) -> None:
    """NULL is "no opening", not an offset of zero, so the check must not catch it."""
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "012")
    await _seed_owner(scratch_engine)

    async with scratch_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO leagues (slug, name, created_by, lock_offset_minutes) "
                "VALUES (:slug, :slug, :owner, 30)"
            ),
            {"slug": f"unset-{uuid.uuid4().hex[:6]}", "owner": OWNER},
        )


async def test_012_downgrade_restores_the_pre_batch_shape(scratch_engine: AsyncEngine) -> None:
    """The way out of a bad deploy has to be real — enum value included.

    PostgreSQL has no ``DROP VALUE``, so the downgrade rebuilds the type. A round
    left ``scheduled`` maps to ``open``, which is how the older code reads a round
    that exists at all.
    """
    url = str(scratch_engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)
    await _migrate(config, "011")
    await _seed_pre_012(scratch_engine)
    await _migrate(config, "012")
    async with scratch_engine.begin() as conn:
        await conn.execute(
            text("UPDATE gameweeks SET status = 'scheduled' WHERE id = :id"), {"id": GAMEWEEK}
        )
    await _migrate(config, "011", down=True)

    async with scratch_engine.connect() as conn:
        remaining = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE (table_name, column_name) IN "
                        "(('leagues', 'pick_open_offset_minutes'), "
                        "('gameweeks', 'picks_open_at_utc'))"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [], "both columns are gone after downgrade"

        values = (
            (
                await conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum "
                        "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                        "WHERE typname = 'gameweek_status' ORDER BY enumsortorder"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert list(values) == ["open", "locked", "settled"]

        status = (
            await conn.execute(
                text("SELECT status FROM gameweeks WHERE id = :id"), {"id": GAMEWEEK}
            )
        ).scalar_one()
        assert status == "open", "a scheduled round survives as the state that precedes it"
