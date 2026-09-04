"""Batch 100 — migrate-on-boot refuses to run when more than one process could.

``nixpacks.toml`` starts the service with ``alembic upgrade head && uvicorn ...``, so
every boot migrates. That is correct only because ``.railway/railway.ts`` pins the service
to one replica; raise it and two containers apply the same DDL to the same database seconds
apart, with Alembic holding no lock of its own.

The constraint used to be a comment asking people to read it. These hold it instead —
both directions, because a guard that also refuses the single-replica path would simply
be an outage.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from src.migration_guard import (
    REPLICA_COUNT_ENV,
    MigrationOnBootUnsafe,
    assert_single_replica,
    declared_replica_count,
)

_API = Path(__file__).resolve().parents[1]
_ROOT = _API.parents[1]
_ALEMBIC_INI = _API / "alembic.ini"
_RAILWAY_IAC = _ROOT / ".railway" / "railway.ts"

#: A DSN that cannot connect and says so immediately — port 1 is refused, not timed out.
#: Used to prove *ordering*: the guard has to answer before anything reaches a database.
_UNREACHABLE = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"


# ── The guard itself ───────────────────────────────────────────────────────────


def test_the_guard_trips_above_one_replica() -> None:
    with pytest.raises(MigrationOnBootUnsafe) as raised:
        assert_single_replica({REPLICA_COUNT_ENV: "2"})

    message = str(raised.value)
    assert "2 replicas" in message
    # Whoever trips this needs to know two things: that nothing was applied, and that
    # the obvious alternative is a decision somebody already recorded.
    assert "The database has not been touched." in message
    assert "release step" in message


def test_the_single_replica_path_is_unchanged() -> None:
    """The half that matters every single deploy."""
    assert assert_single_replica({REPLICA_COUNT_ENV: "1"}) is None
    assert assert_single_replica({}) is None, "an unset declaration must mean one process"
    assert declared_replica_count({}) == 1


@pytest.mark.parametrize("value", ["one", "1.5", "", "  ", "0", "-1", "2 "])
def test_a_declaration_that_is_not_a_count_is_not_evidence_of_safety(value: str) -> None:
    """Anything unreadable raises rather than defaulting to the answer it hopes for.

    Except the genuinely absent ones — a blank variable is the same as no variable, which
    is what every local run and every CI job has.
    """
    if not value.strip():
        assert declared_replica_count({REPLICA_COUNT_ENV: value}) == 1
        return
    if value.strip().isdigit() and int(value) > 1:
        with pytest.raises(MigrationOnBootUnsafe):
            assert_single_replica({REPLICA_COUNT_ENV: value})
        return
    with pytest.raises(MigrationOnBootUnsafe):
        declared_replica_count({REPLICA_COUNT_ENV: value})


# ── The declaration has to match what Railway is actually asked for ────────────


def _deployment_invariants() -> dict[str, Any]:
    """Read the JSON-shaped constants consumed by the Railway IaC service graph."""
    source = _RAILWAY_IAC.read_text()
    marker = "export const DEPLOYMENT_INVARIANTS = "
    start = source.index(marker) + len(marker)
    end = source.index(" as const;", start)
    return json.loads(source[start:end])


def _effective_replica_count(deploy: dict[str, Any]) -> int:
    """Total processes ``.railway/railway.ts`` asks for, summed across regions.

    ``numReplicas`` is per-region. Two regions at one replica each is two processes
    booting and two ``alembic upgrade head`` runs, while ``numReplicas`` still reads 1 —
    which is exactly the shape a guard reading one field would miss.
    """
    default = int(deploy.get("numReplicas", 1))
    regions = deploy.get("multiRegionConfig") or {}
    if not regions:
        return default
    return sum(int(region.get("numReplicas", default)) for region in regions.values())


def _assert_declared_count_matches(deploy: dict[str, Any], declared: str) -> None:
    assert int(declared) == _effective_replica_count(deploy), (
        f"nixpacks.toml declares {REPLICA_COUNT_ENV}={declared} but .railway/railway.ts asks "
        "Railway for a different number of replicas — the boot guard would be checking "
        "a figure that is no longer true"
    )


def test_the_declared_count_matches_what_railway_is_actually_asked_for() -> None:
    """The guard reads the image's declaration; this is what keeps that declaration true."""
    nixpacks = tomllib.loads((_ROOT / "nixpacks.toml").read_text())
    _assert_declared_count_matches(
        _deployment_invariants(), nixpacks["variables"][REPLICA_COUNT_ENV]
    )


def test_a_divergent_image_declaration_is_rejected() -> None:
    """Prove the coupling fails closed instead of only exercising today's matching values."""
    with pytest.raises(AssertionError, match="different number of replicas"):
        _assert_declared_count_matches(_deployment_invariants(), "2")


def test_a_second_region_counts_even_though_num_replicas_still_reads_one() -> None:
    """The case the note never mentioned, asserted so the helper above cannot regress."""
    assert (
        _effective_replica_count(
            {
                "numReplicas": 1,
                "multiRegionConfig": {
                    "europe-west4-drams3a": {"numReplicas": 1},
                    "us-east4-eqdc4a": {"numReplicas": 1},
                },
            }
        )
        == 2
    )


# ── Through alembic, which is where it has to hold ─────────────────────────────


def _run_upgrade(replicas: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_API,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(_API),
            "DATABASE_URL": _UNREACHABLE,
            REPLICA_COUNT_ENV: replicas,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_alembic_refuses_before_it_reaches_the_database() -> None:
    """The guard runs from ``migrations/env.py``, ahead of the engine.

    Pointed at a DSN nothing answers on: if the guard did not run first this would fail
    with a connection error instead, so the message is what proves the ordering — and the
    ordering is the whole property. A migration refused after connecting has already had
    the chance to race the one it was refusing.
    """
    result = _run_upgrade("2")

    assert result.returncode != 0
    assert "Refusing to migrate" in result.stderr, result.stderr
    assert "The database has not been touched." in result.stderr, result.stderr
    assert (
        "Connect call failed" not in result.stderr
    ), "the guard has to answer before anything opens a connection"


def test_one_replica_still_gets_all_the_way_to_the_database() -> None:
    """The guard must not be the reason a normal boot fails.

    Same unreachable DSN, one replica: the run still fails, but on the connection rather
    than the guard — which is the proof that the single-replica path is untouched and
    goes on to do exactly what it did before.
    """
    result = _run_upgrade("1")

    assert result.returncode != 0
    assert "Refusing to migrate" not in result.stderr, result.stderr
    assert (
        "Connect call failed" in result.stderr or "connect" in result.stderr.lower()
    ), result.stderr
