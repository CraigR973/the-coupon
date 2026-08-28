"""Refuse to migrate on boot unless exactly one process is doing it.

Batch 100. ``nixpacks.toml`` starts the service with ``alembic upgrade head &&
uvicorn ...``, so every boot migrates. That is correct — and *only* correct — because
``railway.toml`` pins the service to a single replica. Raise it and two containers run
``alembic upgrade head`` against the same database within a second of each other: both
read the same current revision, both try to apply the same DDL, and what happens next
depends on which statements happen to be transactional. Alembic takes no lock of its own.

Until this module the constraint was held by a comment asking people to read it. It is now
held by the boot: :func:`assert_single_replica` runs from ``migrations/env.py`` before
anything connects, so it guards ``alembic upgrade head`` however it is invoked — the start
command, a ``railway run``, or a hand-typed upgrade — rather than one line of one file.

**Where the number comes from.** ``DEPLOY_REPLICA_COUNT`` is baked into the image by
``nixpacks.toml``'s ``[variables]``, and ``tests/test_migration_guard.py`` asserts it
matches what ``railway.toml`` actually asks Railway for — including the multi-region case,
where two regions at one replica each is two processes even though ``numReplicas`` still
reads ``1``. So raising the replica count without noticing takes two mistakes: the
declaration has to be changed, and CI has to be ignored, and then the boot fails anyway.

**It fails the whole boot, deliberately.** The alternative the owner considered — skip the
migration and let a designated instance own it — needs an instance ordinal, and Railway
gives replicas a UUID rather than an index, so there is nobody to designate. A refused
boot is loud, is caught by the healthcheck, and leaves the database untouched; a raced
migration is quiet and leaves it in a state nothing can name.

Moving migrations to a separate release step is the real fix for wanting more than one
replica. That was considered and set aside on 2026-08-27; the message below says so, so
whoever trips this finds the decision rather than re-deriving it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

#: Baked into the image by ``nixpacks.toml``. Absent locally and in CI, where one process
#: is the only possibility, so the default is the safe answer rather than a guess.
REPLICA_COUNT_ENV = "DEPLOY_REPLICA_COUNT"

DEFAULT_REPLICA_COUNT = 1


class MigrationOnBootUnsafe(RuntimeError):
    """Raised instead of migrating when more than one process could be doing it."""


def declared_replica_count(environ: Mapping[str, str] | None = None) -> int:
    """How many replicas this deployment declares. Unset means one.

    A value that is not a positive integer raises rather than defaulting: a malformed
    declaration is not evidence that the precondition holds, and silently reading it as
    ``1`` would be the guard lying about the one thing it exists to check.
    """
    values = os.environ if environ is None else environ
    raw = values.get(REPLICA_COUNT_ENV, "").strip()
    if not raw:
        return DEFAULT_REPLICA_COUNT
    try:
        count = int(raw)
    except ValueError:
        raise MigrationOnBootUnsafe(
            f"{REPLICA_COUNT_ENV}={raw!r} is not an integer, so the migration guard cannot "
            "establish that only one process is migrating. Set it to the replica count "
            "railway.toml declares, or unset it."
        ) from None
    if count < 1:
        raise MigrationOnBootUnsafe(
            f"{REPLICA_COUNT_ENV}={raw!r} is not a replica count. Set it to the number "
            "railway.toml declares, or unset it."
        )
    return count


def assert_single_replica(environ: Mapping[str, str] | None = None) -> None:
    """Stop before ``alembic upgrade head`` when more than one replica would run it."""
    count = declared_replica_count(environ)
    if count == 1:
        return
    raise MigrationOnBootUnsafe(
        f"Refusing to migrate: this deployment declares {count} replicas and "
        "nixpacks.toml runs `alembic upgrade head` inside the web process, so every one "
        "of them would race the same upgrade against the same database. Alembic takes no "
        "lock of its own.\n"
        "Either return railway.toml to a single replica, or move migrations out of the "
        "start command into a release step that runs once — the second was considered and "
        "set aside on 2026-08-27, and choosing it now is a deliberate change, not a "
        "workaround for this message.\n"
        "The database has not been touched."
    )


if __name__ == "__main__":  # pragma: no cover - exercised through migrations/env.py
    assert_single_replica()
