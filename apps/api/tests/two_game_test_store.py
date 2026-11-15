"""Isolate mixed-worker integration from unrelated committed baseline test history.

Every schema is migrated with the same Alembic revisions as the canonical gate.
No baseline fixture, data, oracle or gate is changed; the normal worker still
selects every eligible legacy and new league within its supplied database.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import conftest as baseline

baseline_db_engine = baseline.db_engine


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def result_store(baseline_db_engine):
    original = os.environ["DATABASE_URL"]
    name = f"coupon_results_{uuid.uuid4().hex[:12]}"
    target = make_url(original).set(database=name).render_as_string(hide_password=False)
    admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(target, pool_size=5, max_overflow=5)
    try:
        api = Path(__file__).resolve().parents[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
            cwd=api,
            env={**os.environ, "DATABASE_URL": target},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0, output.decode(errors="replace")
        yield engine
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": name},
            )
            await connection.execute(text(f'DROP DATABASE "{name}"'))
        await admin.dispose()


@pytest_asyncio.fixture
async def db_engine(result_store, monkeypatch):
    from sqlalchemy import delete

    from src import database, scheduler
    from src.models.rate_limit import RateLimitCounter
    from src.routers import two_game_protocol

    sessions = async_sessionmaker(result_store, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(two_game_protocol, "AsyncSessionLocal", sessions)
    async with sessions() as db, db.begin():
        await db.execute(delete(RateLimitCounter))
    yield result_store
