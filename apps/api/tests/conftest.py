"""Shared pytest fixtures.

Tests that require a live Postgres database depend on the ``db_engine``
fixture.  They skip automatically when ``DATABASE_URL`` is not set so the
default unit-test job stays hermetic.  CI provides a Postgres service plus
``alembic upgrade head`` before running these tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Set required env vars before any src modules are imported."""
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("JWT_ACCESS_SECRET", "test-access-secret-for-unit-tests-only")
    os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh-secret-for-unit-tests-only")


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    """Reset in-memory rate-limit storage before every test for hermetic runs."""
    from src.rate_limit import limiter

    limiter._storage.reset()


@pytest.fixture(autouse=True)
def reset_fotmob_health() -> None:
    """Clear Batch 101's consecutive-failure tracker between tests.

    It is a module singleton for the same reason ``football_session`` is — one client, one
    process — so a test that drives five failed requests would otherwise leave the next
    one starting from an alert already raised.
    """
    from src.services.fotmob_health import fotmob_health

    fotmob_health.reset()


DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture(autouse=True)
async def reset_durable_rate_limits() -> AsyncIterator[None]:
    """The other half of the reset above, for the counters Batch 99 moved to Postgres.

    ``limiter._storage.reset()`` empties the in-process store and nothing else, so the
    login and PIN-reset buckets — which now live in a table on purpose — would carry
    across tests and surface as an unrelated test failing on the sixth login somebody
    else made. Emptied before *and* after, so a test that commits counters leaves the
    table as it found it whichever order the suite runs in.

    A no-op without ``DATABASE_URL``: in that mode nothing writes the table because
    nothing can reach it.
    """
    if not DATABASE_URL:
        yield
        return

    from src.database import AsyncSessionLocal
    from src.models.rate_limit import RateLimitCounter

    async def _empty() -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(RateLimitCounter))
            await session.commit()

    await _empty()
    try:
        yield
    finally:
        await _empty()


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set — Postgres-backed tests skipped")
    engine = create_async_engine(DATABASE_URL, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_conn(db_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Open a fresh connection per test and roll back on exit.

    Each test runs inside an auto-begun transaction.  Rolling back keeps
    the suite hermetic even when tests insert rows.
    """
    async with db_engine.connect() as conn:
        await conn.execute(text("UPDATE profiles SET deleted_at = now() WHERE deleted_at IS NULL"))
        try:
            yield conn
        finally:
            await conn.rollback()
