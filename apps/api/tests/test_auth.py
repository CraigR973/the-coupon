"""Tests for auth endpoints, activation, and FastAPI auth dependencies."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import (
    create_access_token,
    create_refresh_token,
    hash_pin,
    hash_token,
    require_admin,
    verify_pin,
)
from src.config import settings
from src.database import get_db
from src.main import app
from src.models.profile import Profile, UserRole
from src.models.refresh_token import RefreshToken

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_user(
    role: UserRole = UserRole.player,
    failed: int = 0,
    locked_until: datetime | None = None,
    is_active: bool = True,
) -> Profile:
    p = MagicMock(spec=Profile)
    p.id = uuid.uuid4()
    p.display_name = "Test User"
    p.pin_hash = hash_pin("1234")
    p.role = role
    p.timezone = "UTC"
    p.is_active = is_active
    p.failed_login_count = failed
    p.locked_until = locked_until
    p.deleted_at = None
    return p


def _make_refresh_record(user_id: uuid.UUID, refresh_jwt: str) -> MagicMock:
    r = MagicMock(spec=RefreshToken)
    r.id = uuid.uuid4()
    r.user_id = user_id
    r.token_hash = hash_token(refresh_jwt)
    r.device_hint = "TestAgent"
    r.expires_at = _now() + timedelta(days=30)
    r.revoked_at = None
    return r


def _stub_db(execute_results: list) -> AsyncMock:
    """Build a mock AsyncSession with sequential execute() return values."""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()
    return mock_db


def _scalar(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


@asynccontextmanager
async def _override_db(mock_db: AsyncMock) -> AsyncGenerator[None, None]:
    """Temporarily override the get_db dependency."""

    async def _fake_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _fake_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Unit tests — bcrypt / JWT helpers
# ---------------------------------------------------------------------------


def test_hash_and_verify_pin() -> None:
    h = hash_pin("9876")
    assert verify_pin("9876", h)
    assert not verify_pin("0000", h)


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, UserRole.admin)
    payload = pyjwt.decode(token, settings.jwt_access_secret, algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"


def test_refresh_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    record_id = uuid.uuid4()
    token = create_refresh_token(user_id, record_id)
    payload = pyjwt.decode(token, settings.jwt_refresh_secret, algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["jti"] == str(record_id)


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------


async def test_login_success(client: AsyncClient) -> None:
    user = _make_user(role=UserRole.admin)
    mock_db = _stub_db([_scalar(user), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["player"]["role"] == "admin"
    assert data["player"]["display_name"] == "Test User"
    assert "email" not in data["player"]
    assert "avatar_url" not in data["player"]


async def test_login_wrong_pin(client: AsyncClient) -> None:
    user = _make_user()
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "0000"},
        )

    assert resp.status_code == 401


async def test_login_user_not_found(client: AsyncClient) -> None:
    mock_db = _stub_db([_scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "nobody", "pin": "1234"},
        )

    assert resp.status_code == 401


async def test_login_wrong_pin_returns_401(client: AsyncClient) -> None:
    """Wrong PIN always returns 401."""
    user = _make_user(failed=99)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_wrong_pin_updates_durable_counter(client: AsyncClient) -> None:
    user = _make_user(failed=1)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert user.failed_login_count == 2
    mock_db.commit.assert_awaited_once()


async def test_login_locks_profile_after_threshold(client: AsyncClient) -> None:
    user = _make_user(failed=4)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert user.failed_login_count == 5
    assert user.locked_until is not None


async def test_login_rejects_locked_profile(client: AsyncClient) -> None:
    user = _make_user(locked_until=_now() + timedelta(minutes=5))
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 423
    assert resp.json()["detail"] == "Too many failed attempts. Try again later."


async def test_login_rejects_inactive_profile(client: AsyncClient) -> None:
    user = _make_user(is_active=False)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 401


async def test_login_success_resets_durable_lockout(client: AsyncClient) -> None:
    user = _make_user(failed=2, locked_until=_now() - timedelta(minutes=1))
    mock_db = _stub_db([_scalar(user), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 200
    assert user.failed_login_count == 0
    assert user.locked_until is None


# ---------------------------------------------------------------------------
# Refresh endpoint
# ---------------------------------------------------------------------------


async def test_refresh_success(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)
    token_record = _make_refresh_record(user.id, refresh_jwt)
    token_record.id = record_id

    mock_db = _stub_db([_scalar(token_record), _scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_jwt  # rotation happened
    assert token_record.revoked_at is not None


async def test_refresh_invalid_token(client: AsyncClient) -> None:
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.jwt"},
        )

    assert resp.status_code == 401


async def test_refresh_revoked_token(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)

    mock_db = _stub_db([_scalar(None)])  # token not found / revoked

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout endpoint
# ---------------------------------------------------------------------------


async def test_logout_success(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)
    token_record = _make_refresh_record(user.id, refresh_jwt)

    mock_db = _stub_db([_scalar(token_record)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 204
    assert token_record.revoked_at is not None


async def test_logout_bad_token_still_204(client: AsyncClient) -> None:
    """Logout must always return 204 — even with a garbage token."""
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "garbage"},
        )

    assert resp.status_code == 204


async def test_activate_route_removed(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/activate", json={"code": "unknown-code"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth dependency — require_admin
# ---------------------------------------------------------------------------


async def test_require_admin_rejects_player_role() -> None:
    """require_admin raises 403 for a player-role token."""
    user = _make_user(role=UserRole.player)

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403


async def test_require_admin_passes_admin_role() -> None:
    """require_admin returns the user when role is admin."""
    user = _make_user(role=UserRole.admin)
    result = await require_admin(user)
    assert result is user


async def test_me_profile_rejects_device_token(client: AsyncClient) -> None:
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.get(
            "/api/v1/me/profile",
            headers={"Authorization": "Bearer raw-device-token"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


async def test_me_profile_rejects_expired_jwt_without_device_fallback(client: AsyncClient) -> None:
    user = _make_user(role=UserRole.admin)
    expired_jwt = pyjwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "exp": _now() - timedelta(minutes=1),
            "iat": _now() - timedelta(hours=1),
        },
        settings.jwt_access_secret,
        algorithm="HS256",
    )
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.get(
            "/api/v1/me/profile",
            headers={"Authorization": f"Bearer {expired_jwt}"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token expired"
