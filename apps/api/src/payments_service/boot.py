"""Batch 207 — the payments service starts only against the schema it was built for.

The API migrates on boot (``nixpacks.toml``'s ``alembic upgrade head``), which is safe only
because it is the one process doing it. The payments service is a second process on the
same database, so it must never migrate, and it must not run against a schema it was not
built for: a ledger write shaped for revision 028 against a database at 029 is a quiet
corruption, where a refused boot is loud and leaves everything untouched.

So the boot compares the database's ``alembic_version`` with the single head bundled in
this image and refuses on any difference, in either direction. A database behind the image
means the API has not shipped this commit yet; one ahead means this service is stale. Both
are fixed the same way: ship the API first, then this service, from the same commit.

It also refuses above one replica. Nothing here migrates, but Batch 208's token refresh
rotates the refresh token, and two processes refreshing at once would revoke each other.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.migration_guard import MigrationOnBootUnsafe, declared_replica_count

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

DATABASE_URL_ENV = "DATABASE_URL"

RevisionReader = Callable[[str], Awaitable[str]]


class PaymentsBootRefused(RuntimeError):
    """Raised instead of starting when this process could not trust the schema."""


def bundled_head(alembic_ini: Path = ALEMBIC_INI) -> str:
    """The one migration head this image carries. Two heads is itself a refusal."""
    heads = ScriptDirectory.from_config(Config(str(alembic_ini))).get_heads()
    if len(heads) != 1:
        raise PaymentsBootRefused(
            f"this image carries {len(heads)} migration heads, so there is no single "
            "revision it was built for."
        )
    return heads[0]


async def applied_revision(database_url: str) -> str:
    """The revision the database reports. Reads one row; never writes."""
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        # Supabase's transaction-mode pooler does not support prepared statements.
        connect_args={"prepared_statement_cache_size": 0},
    )
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revisions = result.scalars().all()
    finally:
        await engine.dispose()
    if len(revisions) != 1:
        raise PaymentsBootRefused(
            f"the database reports {len(revisions)} applied revisions, not one."
        )
    return str(revisions[0])


def check_revision(expected: str, applied: str) -> None:
    """Refuse unless the database is at exactly the revision this image was built for."""
    if applied == expected:
        return
    raise PaymentsBootRefused(
        f"the database is at migration {applied} but this image was built for {expected}. "
        "The payments service never migrates: ship the API first, whose boot applies "
        "migrations, then this service from the same commit. The database has not been "
        "touched."
    )


async def verify(
    environ: Mapping[str, str] | None = None,
    *,
    read_revision: RevisionReader = applied_revision,
    alembic_ini: Path = ALEMBIC_INI,
) -> str:
    """Every precondition for starting, in order. Returns the revision it agreed on."""
    values = os.environ if environ is None else environ
    try:
        replicas = declared_replica_count(values)
    except MigrationOnBootUnsafe as unreadable:
        raise PaymentsBootRefused(str(unreadable)) from None
    if replicas != 1:
        raise PaymentsBootRefused(
            f"this deployment declares {replicas} replicas; the payments service must run "
            "as exactly one process."
        )

    database_url = values.get(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise PaymentsBootRefused(f"{DATABASE_URL_ENV} is not set.")

    expected = bundled_head(alembic_ini)
    try:
        applied = await read_revision(database_url)
    except PaymentsBootRefused:
        raise
    except Exception as failure:
        # The exception's own text can carry the DSN, password and all, so only its type
        # is reported.
        raise PaymentsBootRefused(
            f"could not read the database's migration revision ({type(failure).__name__}), "
            "so this image cannot know the schema matches it."
        ) from None
    check_revision(expected, applied)
    return expected
