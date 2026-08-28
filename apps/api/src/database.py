from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.models.base import Base  # noqa: F401 — re-exported for callers

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=10,
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
