"""The display-name uniqueness race, against a real database.

Batch 83. ``/auth/register`` compares names case-insensitively; until migration 017
the constraint behind it (``uq_profiles_display_name``) compared them
case-sensitively, so the "backstop" only ever caught an exact-case race. Two
concurrent registrations for "Dave" and "dave" both passed the pre-check, both
passed the constraint, and both committed.

Mocking cannot show this. The whole defect lives in what Postgres does when two
transactions insert between one another's SELECT and COMMIT, so every test here runs
against a migrated database and is skipped without ``DATABASE_URL``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.database import AsyncSessionLocal
from src.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """Put back the loggers ``alembic``'s ``env.py`` switches off on its way past.

    ``migrations/env.py:20`` calls ``fileConfig(config.config_file_name)``, and
    ``logging.config.fileConfig`` defaults to ``disable_existing_loggers=True`` — so
    running a migration in-process sets ``disabled = True`` on every logger configured
    before it, ``httpx`` included, for the rest of the session.

    ``test_migration_012`` and ``test_migration_014`` have always done this. They get
    away with it only because their filenames sort *after*
    ``test_logging_config.py``, which asserts httpx actually emits its request line;
    this module sorts before it and would otherwise break it. Restoring here keeps that
    accident from mattering either way.
    """
    manager = logging.Logger.manager
    before = {
        name: logger.disabled
        for name, logger in manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }
    try:
        yield
    finally:
        for name, was_disabled in before.items():
            logger = manager.loggerDict.get(name)
            if isinstance(logger, logging.Logger):
                logger.disabled = was_disabled


def _variant_pair() -> tuple[str, str]:
    """A name and the same name in another case, unique to this run.

    The tag is lowercase hex, so the two strings differ *only* in the leading word —
    which is the whole point: anything else and the test would pass on a case-sensitive
    constraint too.
    """
    tag = uuid.uuid4().hex[:10]
    return f"Dave{tag}", f"dave{tag}"


async def _delete_profiles(*names: str) -> None:
    """Remove what a test committed, children first — the suite shares this database."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "DELETE FROM refresh_tokens WHERE user_id IN "
                "(SELECT id FROM profiles WHERE display_name = ANY(:names))"
            ),
            {"names": list(names)},
        )
        await session.execute(
            text("DELETE FROM profiles WHERE display_name = ANY(:names)"), {"names": list(names)}
        )
        await session.commit()


# ── The race itself, over HTTP ────────────────────────────────────────────────


async def test_concurrent_case_variant_registrations_leave_exactly_one_account() -> None:
    """Two registrations for "Dave" and "dave" in flight together: one wins, one is told no.

    Both requests get their own session out of ``get_db``, so this is a genuine race
    rather than two calls sharing a transaction. Whichever way the interleaving falls —
    the pre-check catching it, or the index catching it after the pre-check missed — the
    invariant is the same and is what this asserts: the database ends up holding one
    account, not two, and the loser is refused rather than shown a 500.
    """
    upper, lower = _variant_pair()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first, second = await asyncio.gather(
                client.post("/api/v1/auth/register", json={"display_name": upper, "pin": "3719"}),
                client.post("/api/v1/auth/register", json={"display_name": lower, "pin": "8264"}),
            )

        codes = sorted([first.status_code, second.status_code])
        assert codes == [201, 409], f"expected one win and one refusal, got {codes}"

        async with AsyncSessionLocal() as session:
            held = await session.execute(
                text("SELECT count(*) FROM profiles WHERE lower(display_name) = lower(:name)"),
                {"name": upper},
            )
            assert held.scalar_one() == 1
    finally:
        await _delete_profiles(upper, lower)


# ── The backstop on its own, with the race taken out of the picture ───────────


async def test_index_refuses_a_case_variant_the_pre_check_never_saw() -> None:
    """The constraint refuses the collision even when nothing checked first.

    The test above can be satisfied by the pre-check alone, on an interleaving where one
    request commits before the other reads. This one writes straight to the table from two
    separate sessions, so the *only* thing that can refuse the second insert is migration
    017's functional index — which is the half that was missing.
    """
    upper, lower = _variant_pair()
    try:
        async with AsyncSessionLocal() as first:
            await first.execute(
                text(
                    "INSERT INTO profiles (id, display_name, pin_hash, role) "
                    "VALUES (:id, :name, 'x', 'player')"
                ),
                {"id": uuid.uuid4(), "name": upper},
            )
            await first.commit()

        async with AsyncSessionLocal() as second:
            with pytest.raises(IntegrityError):
                await second.execute(
                    text(
                        "INSERT INTO profiles (id, display_name, pin_hash, role) "
                        "VALUES (:id, :name, 'x', 'player')"
                    ),
                    {"id": uuid.uuid4(), "name": lower},
                )
                await second.commit()
    finally:
        await _delete_profiles(upper, lower)


# ── What the migration does to a database that already holds the duplicate ────


def _url_for(database: str) -> str:
    return (
        make_url(os.environ["DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )


async def _migrate(config: Config, revision: str) -> None:
    await asyncio.to_thread(command.upgrade, config, revision)


@pytest_asyncio.fixture
async def scratch_engine() -> AsyncIterator[AsyncEngine]:
    """A database of this test's own, dropped afterwards whatever happens."""
    original = os.environ["DATABASE_URL"]
    name = f"coupon_mig017_{uuid.uuid4().hex[:12]}"
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


async def test_upgrade_refuses_a_database_that_already_holds_a_collision(
    scratch_engine: AsyncEngine,
) -> None:
    """017 fails loudly on pre-existing case variants rather than picking a survivor.

    This migration runs on boot against a database this workstation cannot reach, so the
    refusal path is the one that has to be right: it must name the offending rows, or the
    service is down with a container log saying only "duplicate key value". Asserting on
    the message rather than on the exception type is the point of the test.
    """
    config = Config(str(_ALEMBIC_INI))
    os.environ["DATABASE_URL"] = _url_for(scratch_engine.url.database or "")
    await _migrate(config, "016")

    async with scratch_engine.begin() as conn:
        for name in ("Dave", "dave"):
            await conn.execute(
                text(
                    "INSERT INTO profiles (id, display_name, pin_hash, role) "
                    "VALUES (:id, :name, 'x', 'player')"
                ),
                {"id": uuid.uuid4(), "name": name},
            )

    with pytest.raises(RuntimeError, match="cannot make display names") as raised:
        await _migrate(config, "017")

    message = str(raised.value)
    assert "'dave'" in message, "the refusal must name the colliding name"
    assert "2 profiles" in message, "and say how many rows hold it"

    # Nothing was changed on the way out — the old constraint is still the live one.
    async with scratch_engine.connect() as conn:
        held = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'profiles'")
        )
        names = {row[0] for row in held}
    assert "uq_profiles_display_name" in names
    assert "uq_profiles_display_name_lower" not in names


async def test_upgrade_applies_cleanly_when_names_only_differ_beyond_case(
    scratch_engine: AsyncEngine,
) -> None:
    """The ordinary database — distinct names — takes 017 without complaint.

    Paired with the test above so a failure tells you *which* thing broke: the migration
    itself, or only its refusal path.
    """
    config = Config(str(_ALEMBIC_INI))
    os.environ["DATABASE_URL"] = _url_for(scratch_engine.url.database or "")
    await _migrate(config, "016")

    async with scratch_engine.begin() as conn:
        for name in ("Dave", "Marc", "Lewis"):
            await conn.execute(
                text(
                    "INSERT INTO profiles (id, display_name, pin_hash, role) "
                    "VALUES (:id, :name, 'x', 'player')"
                ),
                {"id": uuid.uuid4(), "name": name},
            )

    await _migrate(config, "017")

    async with scratch_engine.connect() as conn:
        held = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'profiles'")
        )
        names = {row[0] for row in held}
    assert "uq_profiles_display_name_lower" in names
    assert "uq_profiles_display_name" not in names
