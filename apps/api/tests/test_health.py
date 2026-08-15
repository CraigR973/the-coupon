from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _newest_migration_revision() -> str:
    """Highest revision on disk, taken from filenames rather than Alembic's graph.

    Deriving it independently is the point: if a new migration is added whose
    `down_revision` does not chain, Alembic reports two heads and the endpoint
    stops matching this.
    """
    versions = Path(__file__).resolve().parents[3] / "migrations" / "versions"
    return sorted(p.name.split("_")[0] for p in versions.glob("[0-9]*.py"))[-1]


# R8.1 — /health returns sha field


async def test_health_ok_has_sha(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "sha" in data


async def test_health_sha_from_env(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.routers.health as h

    monkeypatch.setattr(h.settings, "railway_git_commit_sha", "abc1234")
    response = await client.get("/api/v1/health")
    assert response.json()["sha"] == "abc1234"


async def test_health_sha_unknown_when_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.routers.health as h

    monkeypatch.setattr(h.settings, "railway_git_commit_sha", None)
    response = await client.get("/api/v1/health")
    assert response.json()["sha"] == "unknown"


# R8.3 — /health reports the migration head bundled in the image


async def test_health_reports_bundled_migration_head(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.json()["migration"] == _newest_migration_revision()


async def test_health_migration_unknown_when_scripts_unreadable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import src.routers.health as h

    h.bundled_migration_head.cache_clear()
    monkeypatch.setattr(h, "_ALEMBIC_INI", tmp_path / "absent.ini")
    try:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["migration"] == "unknown"
    finally:
        h.bundled_migration_head.cache_clear()


# R8.2 — /health/ready returns 503 when DB is unreachable


async def test_ready_db_ok(client: AsyncClient) -> None:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    result = Mock()
    result.scalars.return_value.all.return_value = ["011"]
    mock_session.execute = AsyncMock(return_value=result)

    with patch("src.routers.health.AsyncSessionLocal", return_value=mock_session):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["db"] == "ok"
    assert data["migration"] == "011"


async def test_ready_stays_green_when_version_table_is_missing(client: AsyncClient) -> None:
    """A version probe must never be able to turn a healthy service red."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def execute(statement: object) -> Mock:
        if "alembic_version" in str(statement):
            raise Exception('relation "alembic_version" does not exist')
        return Mock()

    mock_session.execute = AsyncMock(side_effect=execute)

    with patch("src.routers.health.AsyncSessionLocal", return_value=mock_session):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["migration"] == "unknown"


async def test_ready_db_down_returns_503(client: AsyncClient) -> None:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.routers.health.AsyncSessionLocal", return_value=mock_session):
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["db"] == "unreachable"
