"""The payments service's own database sessions. Batch 208.

Not ``src.database``, which builds its engine from ``src.config`` and so demands the API's
secrets. Same database, same pooler rule, a much smaller pool: one process, one loop, the
occasional webhook.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        database_url,
        pool_size=2,
        max_overflow=2,
        pool_timeout=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        # Supabase's transaction-mode pooler does not support prepared statements.
        connect_args={"prepared_statement_cache_size": 0},
    )
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
