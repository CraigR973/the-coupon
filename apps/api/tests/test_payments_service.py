"""Batch 207 — the payments service boots only against the schema it was built for.

ADR 0009 option B puts the Monzo token in a second Railway process on the API's database.
The API migrates on boot; this process must never migrate, and must refuse to start at any
revision other than the single head bundled in its image. These hold that, without a
database where they can, and against the migrated test database where they cannot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from src.payments_service import app as payments_app
from src.payments_service.boot import (
    PaymentsBootRefused,
    applied_revision,
    bundled_head,
    verify,
)

_API = Path(__file__).resolve().parents[1]
_ROOT = _API.parents[1]
_RAILWAY_IAC = _ROOT / ".railway" / "railway.ts"
_PACKAGE = _API / "src" / "payments_service"

#: A DSN that cannot connect and says so immediately — port 1 is refused, not timed out.
#: The password is a marker: it must never appear in a refusal.
_UNREACHABLE = "postgresql+asyncpg://nobody:hunter2-marker@127.0.0.1:1/nothing"


def _newest_migration_on_disk() -> str:
    """Taken from filenames rather than Alembic's graph, so the two are independent."""
    versions = _ROOT / "migrations" / "versions"
    return sorted(p.name.split("_")[0] for p in versions.glob("[0-9]*.py"))[-1]


def _reads(revision: str) -> Any:
    async def read(_database_url: str) -> str:
        return revision

    return read


def _environ(**overrides: str) -> dict[str, str]:
    return {"DATABASE_URL": "postgresql+asyncpg://unused", **overrides}


# ── The revision check ────────────────────────────────────────────────────────


def test_the_bundled_head_is_the_newest_migration_on_disk() -> None:
    assert bundled_head() == _newest_migration_on_disk()


async def test_a_database_at_the_bundled_head_boots() -> None:
    head = bundled_head()
    assert await verify(_environ(), read_revision=_reads(head)) == head


async def test_a_database_behind_the_image_refuses_and_says_to_ship_the_api_first() -> None:
    head = bundled_head()
    behind = f"{int(head) - 1:03d}"
    with pytest.raises(PaymentsBootRefused) as refused:
        await verify(_environ(), read_revision=_reads(behind))

    message = str(refused.value)
    assert f"at migration {behind}" in message
    assert f"built for {head}" in message
    assert "ship the API first" in message
    assert "The database has not been touched." in message


async def test_a_database_ahead_of_the_image_refuses() -> None:
    ahead = f"{int(bundled_head()) + 1:03d}"
    with pytest.raises(PaymentsBootRefused, match=f"at migration {ahead}"):
        await verify(_environ(), read_revision=_reads(ahead))


async def test_an_unreadable_revision_refuses_without_echoing_the_dsn() -> None:
    async def explode(database_url: str) -> str:
        raise OSError(f"could not connect to {database_url}")

    with pytest.raises(PaymentsBootRefused) as refused:
        await verify(_environ(DATABASE_URL=_UNREACHABLE), read_revision=explode)

    assert "OSError" in str(refused.value)
    assert "hunter2-marker" not in str(refused.value)


async def test_an_unset_database_url_refuses_before_reading_anything() -> None:
    async def never(_database_url: str) -> str:
        raise AssertionError("no read without a DATABASE_URL")

    with pytest.raises(PaymentsBootRefused, match="DATABASE_URL is not set"):
        await verify({"DATABASE_URL": "  "}, read_revision=never)


@pytest.mark.parametrize("declared", ["2", "3"])
async def test_more_than_one_replica_refuses(declared: str) -> None:
    with pytest.raises(PaymentsBootRefused, match=f"declares {declared} replicas"):
        await verify(_environ(DEPLOY_REPLICA_COUNT=declared), read_revision=_reads(bundled_head()))


async def test_an_unreadable_replica_declaration_refuses() -> None:
    with pytest.raises(PaymentsBootRefused, match="not an integer"):
        await verify(_environ(DEPLOY_REPLICA_COUNT="one"), read_revision=_reads(bundled_head()))


async def test_the_real_reader_agrees_with_the_migrated_database(db_engine: AsyncEngine) -> None:
    """The one read the boot makes, against a database CI has upgraded to head."""
    database_url = db_engine.url.render_as_string(hide_password=False)
    assert await applied_revision(database_url) == bundled_head()
    assert await verify(_environ(DATABASE_URL=database_url)) == bundled_head()


# ── The process itself ────────────────────────────────────────────────────────


def test_the_process_exits_non_zero_before_binding_when_it_cannot_read_the_revision() -> None:
    environ = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "PORT", "DEPLOY_REPLICA_COUNT"}
    }
    environ["DATABASE_URL"] = _UNREACHABLE
    completed = subprocess.run(
        [sys.executable, "-m", "src.payments_service"],
        cwd=_API,
        env=environ,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 1, completed.stderr
    assert "payments boot refused" in completed.stderr
    assert "hunter2-marker" not in completed.stderr + completed.stdout
    assert "Uvicorn running" not in completed.stderr + completed.stdout


def _imports() -> list[str]:
    lines = []
    for path in _PACKAGE.glob("*.py"):
        lines += [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
    return lines


def test_the_payments_service_never_migrates() -> None:
    """Nothing in the package can apply a revision: Alembic's command API is never imported."""
    imports = _imports()
    assert imports, "the import scan found nothing, so it proves nothing"
    assert not [line for line in imports if "alembic.command" in line or "import command" in line]
    source = "\n".join(path.read_text() for path in _PACKAGE.glob("*.py"))
    assert "command.upgrade" not in source


def test_the_payments_service_never_imports_the_api_settings_or_app() -> None:
    """``src.config`` demands the API's secrets in production; ``src.main`` starts its scheduler."""
    imports = _imports()
    for forbidden in ("src.config", "src.main", "src.database", "src.scheduler", "src.routers"):
        assert not [line for line in imports if forbidden in line], forbidden


# ── The health pair ───────────────────────────────────────────────────────────


@pytest.fixture
async def client() -> Any:
    transport = ASGITransport(app=payments_app.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_reports_the_service_commit_and_bundled_head(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234")
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "payments",
        "sha": "abc1234",
        "migration": _newest_migration_on_disk(),
    }


async def test_health_sha_is_unknown_when_unstamped(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    assert (await client.get("/health")).json()["sha"] == "unknown"


async def test_ready_only_at_the_bundled_head(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused")
    head = bundled_head()

    monkeypatch.setattr(payments_app, "applied_revision", _reads(head))
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "db": "ok", "migration": head}

    behind = f"{int(head) - 1:03d}"
    monkeypatch.setattr(payments_app, "applied_revision", _reads(behind))
    stale = await client.get("/health/ready")
    assert stale.status_code == 503
    assert stale.json()["migration"] == behind
    assert stale.json()["expected"] == head


async def test_ready_is_red_when_the_database_is_unreachable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "db": "unreachable"}
    assert "hunter2-marker" not in response.text


# ── The declaration Railway is asked for ──────────────────────────────────────


def _json_constant(name: str) -> Any:
    source = _RAILWAY_IAC.read_text()
    marker = f"export const {name} = "
    start = source.index(marker) + len(marker)
    end = source.index(" as const;", start)
    return json.loads(source[start:end])


def test_the_payments_service_is_declared_as_one_process_that_never_migrates() -> None:
    deploy = _json_constant("PAYMENTS_DEPLOYMENT_INVARIANTS")
    assert deploy["startCommand"] == "python -m src.payments_service"
    assert "alembic" not in deploy["startCommand"]
    assert deploy["numReplicas"] == 1
    regions = deploy["multiRegionConfig"]
    assert sum(int(region["numReplicas"]) for region in regions.values()) == 1
    assert deploy["healthcheckPath"] == "/health/ready"


def test_the_payments_route_table_is_the_health_pair_and_the_monzo_routes() -> None:
    """Batch 207's health pair, and exactly the three Monzo routes Batch 208 adds."""
    paths = {getattr(route, "path", "") for route in payments_app.app.routes}
    assert paths == {
        "/health",
        "/health/ready",
        "/monzo/oauth/start",
        "/monzo/oauth/callback",
        "/monzo/webhook/{path_secret}",
    }
