from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.models.base import Base  # noqa: F401 — re-exported for callers

# Batch 146. Was 10 + 10 overflow — up to 20 connections from **one** container, against
# a Postgres whose `max_connections` is 60 and which already carries about 15 backends of
# Supabase's own (measured 2026-09-23). A third of the instance's whole budget, reserved
# for a concurrency this deployment does not produce: one replica, 0.25 vCPU, one league.
#
# 5 + 5 keeps ten, which is still more than the scheduler and a Saturday-morning league
# can occupy at once, and halves the footprint on an instance that is not ours alone.
# `pool_timeout` is stated rather than left at its default so that exhausting the pool
# fails in ten seconds with a recognisable error instead of hanging for thirty.
engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
    # prepared_statement_cache_size=0: required for Supabase's transaction-mode
    # pooler (port 6543) which doesn't support prepared statements.
    connect_args={
        "prepared_statement_cache_size": 0,
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_limiter_db() -> AsyncGenerator[AsyncSession, None]:
    """A session for the durable rate-limit counters, separate from the request's own.

    Batch 99. A counter that shares the handler's transaction is not a counter: login
    rolls back on a bad PIN and commits on a good one, and an attempt has to be charged
    either way. Its own session also keeps the charge off the request's identity map, so
    an attempt is recorded even when the work behind it never reaches a commit.

    Same engine and pool as :func:`get_db` — this is a second transaction, not a second
    connection pool.
    """
    async with AsyncSessionLocal() as session:
        yield session
