"""Profile pictures: the validation that runs, and the refusal behind it (Batch 42).

No object store is configured in any environment, so ``POST /auth/me/avatar`` answers
503 everywhere. That makes the validation in front of it the part worth pinning: it is
written now, and it must still be correct on the day a backend is wired and the refusal
stops covering for it. Each test therefore asserts the *specific* rejection rather than
"not a 200", which a blanket 503 would satisfy vacuously.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth import create_access_token, hash_pin
from src.database import get_db
from src.main import app
from src.models.profile import OddsFormat, Profile, UserRole
from src.services.avatar_storage import (
    AvatarStorageUnavailable,
    UnconfiguredAvatarStorage,
    sniff_image_type,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 64


def _make_user(role: UserRole = UserRole.player) -> Profile:
    p = MagicMock(spec=Profile)
    p.id = uuid.uuid4()
    p.display_name = "Test User"
    p.pin_hash = hash_pin("1234")
    p.role = role
    p.timezone = "UTC"
    p.odds_format = OddsFormat.decimal
    p.is_active = True
    p.failed_login_count = 0
    p.locked_until = None
    p.deleted_at = None
    p.avatar_url = None
    return p


def _stub_db(user: Profile) -> AsyncMock:
    """A session that answers every lookup with this one profile."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=user)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@asynccontextmanager
async def _override_db(db: AsyncMock) -> AsyncGenerator[None, None]:
    async def _get_db() -> AsyncGenerator[AsyncMock, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(user: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


# ── Magic-byte sniffing ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("data", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_sniff_recognises_each_allowed_format(data: bytes, expected: str) -> None:
    assert sniff_image_type(data) == expected


def test_sniff_does_not_mistake_other_riff_containers_for_webp() -> None:
    """``RIFF`` alone is also WAV and AVI — the WEBP half of the signature is required."""
    assert sniff_image_type(WAV) is None


def test_sniff_rejects_bytes_that_are_not_an_image() -> None:
    assert sniff_image_type(b"<?php echo 1; ?>") is None
    assert sniff_image_type(b"") is None


# ── The endpoint's validation ─────────────────────────────────────────────────


async def test_a_disallowed_content_type_is_refused(client: AsyncClient) -> None:
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=b"GIF89a" + b"\x00" * 32,
            headers={**_auth(user), "Content-Type": "image/gif"},
        )
    assert resp.status_code == 415


async def test_bytes_that_contradict_the_declared_type_are_refused(client: AsyncClient) -> None:
    """A declared content-type is a claim; the leading bytes are the evidence."""
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=b"<?php echo 1; ?>" + b"\x00" * 32,
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


async def test_an_oversized_image_is_refused(client: AsyncClient) -> None:
    from src.config import settings

    user = _make_user()
    oversized = PNG + b"\x00" * (settings.avatar_max_bytes + 1)
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=oversized,
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 413


async def test_an_empty_body_is_refused(client: AsyncClient) -> None:
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=b"",
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 400


async def test_a_valid_image_still_fails_closed_with_no_backend(client: AsyncClient) -> None:
    """The whole feature, as shipped: everything valid, and nowhere to put it."""
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=PNG,
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Profile pictures are not enabled yet"


async def test_a_member_can_always_clear_their_own_picture(client: AsyncClient) -> None:
    """Clearing is a null on a column, so it works while uploading does not.

    A member must be able to take their own picture down in the window where the upload
    path is disabled — otherwise enabling a backend would be a one-way door.
    """
    user = _make_user()
    user.avatar_url = "https://example.test/avatar.png"
    async with _override_db(_stub_db(user)):
        resp = await client.delete("/api/v1/auth/me/avatar", headers=_auth(user))

    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    assert user.avatar_url is None


async def test_removing_another_members_picture_requires_a_site_admin(
    client: AsyncClient,
) -> None:
    """An avatar follows a member into every league, so it is not a league admin's call."""
    player = _make_user()
    async with _override_db(_stub_db(player)):
        resp = await client.delete(
            f"/api/v1/auth/players/{uuid.uuid4()}/avatar", headers=_auth(player)
        )
    assert resp.status_code == 403


async def test_a_site_admin_can_remove_a_members_picture(client: AsyncClient) -> None:
    admin = _make_user(role=UserRole.admin)
    admin.avatar_url = "https://example.test/theirs.png"
    async with _override_db(_stub_db(admin)):
        resp = await client.delete(f"/api/v1/auth/players/{admin.id}/avatar", headers=_auth(admin))
    assert resp.status_code == 204
    assert admin.avatar_url is None


# ── The port itself ───────────────────────────────────────────────────────────


async def test_the_unconfigured_backend_refuses_writes_but_allows_removal() -> None:
    storage = UnconfiguredAvatarStorage()
    with pytest.raises(AvatarStorageUnavailable):
        await storage.put(player_id="p1", data=PNG, media_type="image/png")
    # Deleting must be a no-op rather than an error, so clearing a column never blocks.
    assert await storage.delete(player_id="p1") is None
