"""Profile pictures: the validation that runs, the re-encoder, and the backends.

Batch 42 wrote the validation while nothing could store a byte, so the refusal behind it
covered for everything. Batch 44 removed that cover: uploads reach a real backend when
one is configured, and the gate that matters is no longer the magic-byte prefix — which
proves a header — but :func:`reencode_avatar`, which decodes the payload and writes a new
file from the pixels.

Each test asserts the *specific* rejection rather than "not a 200", which a blanket 503
would satisfy vacuously. The constructed images here are real ones built by Pillow, not
header stubs, because a header stub can no longer get past the decoder — which is the
whole point of the batch.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from src.auth import create_access_token, hash_pin
from src.database import get_db
from src.main import app
from src.models.profile import OddsFormat, Profile, UserRole
from src.services.avatar_storage import (
    MAX_DIMENSION,
    AvatarRejected,
    AvatarStorage,
    AvatarStorageError,
    AvatarStorageUnavailable,
    SupabaseAvatarStorage,
    UnconfiguredAvatarStorage,
    avatar_storage,
    reencode_avatar,
    sniff_image_type,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 64


def _image(
    fmt: str = "PNG",
    size: tuple[int, int] = (64, 64),
    mode: str = "RGB",
    **save_kwargs: object,
) -> bytes:
    """A genuine encoded image — what a member actually uploads."""
    buf = io.BytesIO()
    Image.new(mode, size, color=1 if mode == "1" else "red").save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


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
    """The default posture: a real picture, decoded fine, and nowhere to put it."""
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=_image(),
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Profile pictures are not enabled yet"


async def test_a_png_header_in_front_of_junk_is_refused(client: AsyncClient) -> None:
    """The case Batch 42 could not defend against and named as the blocker.

    These bytes pass every header check — declared ``image/png``, and they genuinely
    begin with the PNG signature — and they are not an image. Before the decoder existed
    the 503 hid this; now it is a 400 and it is the decoder saying so.
    """
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.post(
            "/api/v1/auth/me/avatar",
            content=PNG + b"<?php echo 1; ?>",
            headers={**_auth(user), "Content-Type": "image/png"},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "That file could not be read as an image"


# ── The re-encoder ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_every_accepted_format_is_re_encoded_as_webp(fmt: str) -> None:
    """Whatever arrives, one stored shape — so there is one decoder path to reason about."""
    out = reencode_avatar(_image(fmt))
    with Image.open(io.BytesIO(out)) as image:
        assert image.format == "WEBP"


def test_the_output_is_written_from_pixels_not_copied() -> None:
    """The payload does not survive: bytes appended behind a valid image are gone."""
    smuggled = b"<script>alert(1)</script>"
    out = reencode_avatar(_image() + smuggled)
    assert smuggled not in out


def test_a_large_picture_is_scaled_down_and_keeps_its_shape() -> None:
    out = reencode_avatar(_image(size=(1600, 800)))
    with Image.open(io.BytesIO(out)) as image:
        assert max(image.size) == MAX_DIMENSION
        assert image.size == (MAX_DIMENSION, MAX_DIMENSION // 2)


def test_a_small_picture_is_not_scaled_up() -> None:
    out = reencode_avatar(_image(size=(32, 32)))
    with Image.open(io.BytesIO(out)) as image:
        assert image.size == (32, 32)


def test_exif_is_applied_and_then_dropped() -> None:
    """A phone writes orientation into EXIF and a location beside it.

    The rotation has to happen *before* the tag is discarded, or a picture taken in
    portrait is stored on its side. Nothing of the EXIF block survives into the output,
    which is how the location goes too.
    """
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise on display
    exif[0x010E] = "taken at home"  # ImageDescription — stands in for anything personal
    original = _image("JPEG", size=(100, 50), exif=exif.tobytes())

    out = reencode_avatar(original)
    with Image.open(io.BytesIO(out)) as image:
        assert image.size == (50, 100)  # transposed, not merely tagged
        assert not image.getexif()
    assert b"taken at home" not in out


def test_a_decompression_bomb_is_refused_before_it_is_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A few kilobytes that decode to hundreds of megabytes.

    The size cap bounds what *arrives*; it says nothing about what a decoder allocates.
    ``Image.open`` reads the header only, so the dimensions are known while refusing is
    still cheap — and that ordering is the entire defence.
    """
    import src.services.avatar_storage as storage_module

    monkeypatch.setattr(storage_module, "MAX_PIXELS", 1_000_000)
    bomb = _image(size=(4000, 4000), mode="1")
    assert len(bomb) < 100_000  # tiny on the wire, 16 megapixels decoded

    with pytest.raises(AvatarRejected):
        reencode_avatar(bomb)


def test_an_image_format_outside_the_allowlist_is_refused() -> None:
    """Read from the file's own header, not from what the caller declared."""
    with pytest.raises(AvatarRejected):
        reencode_avatar(_image("GIF"))


def test_a_truncated_image_is_refused() -> None:
    with pytest.raises(AvatarRejected):
        reencode_avatar(_image()[:40])


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


# ── The Supabase backend ──────────────────────────────────────────────────────


def _recording_client(
    handler: object = None, *, listed: list[str] | None = None
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """An httpx client that answers from a stub and keeps every request it was given."""
    seen: list[httpx.Request] = []

    def _respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "/object/list/" in str(request.url):
            names = [{"name": name} for name in (listed or [])]
            return httpx.Response(200, json=names)
        if callable(handler):
            return handler(request)
        return httpx.Response(200, json={})

    return httpx.AsyncClient(transport=httpx.MockTransport(_respond)), seen


def _supabase(client: httpx.AsyncClient) -> SupabaseAvatarStorage:
    return SupabaseAvatarStorage(
        base_url="https://proj.supabase.co",
        service_key="service-role-key",
        bucket="avatars",
        client=client,
    )


async def test_the_stored_key_cannot_be_derived_from_a_player_id() -> None:
    """The random half of the key *is* the access control.

    The bucket is public-read, so a URL that is guessable from a player id — and player
    ids are on every league page — would make every member's picture enumerable. Two
    uploads for the same member must not land on the same URL.
    """
    client, _ = _recording_client()
    storage = _supabase(client)

    first = await storage.put(player_id="p1", data=b"webp", media_type="image/png")
    second = await storage.put(player_id="p1", data=b"webp", media_type="image/png")

    assert first.startswith("https://proj.supabase.co/storage/v1/object/public/avatars/p1/")
    assert first != second


async def test_replacing_a_picture_removes_the_one_it_replaces() -> None:
    """Otherwise a URL that leaked keeps resolving after the member changed it."""
    client, seen = _recording_client(listed=["old.webp"])
    storage = _supabase(client)

    await storage.put(player_id="p1", data=b"webp", media_type="image/png")

    deletes = [r for r in seen if r.method == "DELETE"]
    assert len(deletes) == 1
    assert b"p1/old.webp" in deletes[0].content
    # And the removal happens before the write, so a failed upload cannot leave the
    # previous picture reachable at a URL the member meant to replace.
    assert [r.method for r in seen] == ["POST", "DELETE", "POST"]


async def test_a_refused_upload_raises_rather_than_returning_a_dead_url() -> None:
    def _refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "no"})

    client, _ = _recording_client(_refuse)
    with pytest.raises(AvatarStorageError):
        await _supabase(client).put(player_id="p1", data=b"webp", media_type="image/png")


async def test_a_failed_delete_does_not_stop_a_member_clearing_their_picture() -> None:
    """The column is nulled either way; an orphaned object nobody points at is not worth
    refusing a member's own removal over. It is logged rather than raised."""

    def _refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "no"})

    client, _ = _recording_client(_refuse, listed=["old.webp"])
    assert await _supabase(client).delete(player_id="p1") is None


async def test_deleting_nothing_sends_no_delete_at_all() -> None:
    client, seen = _recording_client(listed=[])
    await _supabase(client).delete(player_id="p1")
    assert [r.method for r in seen] == ["POST"]  # the list call, and nothing after it


async def test_the_service_key_travels_as_a_bearer_token_and_never_in_the_url() -> None:
    """odds-api.io put its key in a query string and httpx logged the URL for months
    (Batch 36). A header keeps this one out of every request line by construction."""
    client, seen = _recording_client()
    await _supabase(client).put(player_id="p1", data=b"webp", media_type="image/png")

    assert all("service-role-key" not in str(r.url) for r in seen)
    assert seen[-1].headers["authorization"] == "Bearer service-role-key"


# ── Selecting a backend ───────────────────────────────────────────────────────


def test_no_backend_is_selected_by_default() -> None:
    assert isinstance(avatar_storage(), UnconfiguredAvatarStorage)


def test_supabase_without_credentials_falls_back_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-configured deployment answers "not enabled yet", which is true, instead of
    500ing on every upload."""
    from src.config import settings

    monkeypatch.setattr(settings, "avatar_storage", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    assert isinstance(avatar_storage(), UnconfiguredAvatarStorage)


def test_supabase_is_selected_once_it_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "avatar_storage", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-role-key")
    selected = avatar_storage()
    assert isinstance(selected, SupabaseAvatarStorage)
    assert selected.enabled


# ── What the client is told ───────────────────────────────────────────────────


async def test_config_reports_uploads_off_by_default(client: AsyncClient) -> None:
    user = _make_user()
    async with _override_db(_stub_db(user)):
        resp = await client.get("/api/v1/config", headers=_auth(user))
    assert resp.status_code == 200
    assert resp.json() == {"avatar_uploads": False}


async def test_config_reports_uploads_on_once_a_backend_answers(client: AsyncClient) -> None:
    """What the web app mounts its upload control on."""
    user = _make_user()

    class _Enabled(AvatarStorage):
        enabled = True

        async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
            return "https://example.test/a.webp"

        async def delete(self, *, player_id: str) -> None:
            return None

    app.dependency_overrides[avatar_storage] = _Enabled
    try:
        async with _override_db(_stub_db(user)):
            resp = await client.get("/api/v1/config", headers=_auth(user))
    finally:
        app.dependency_overrides.pop(avatar_storage, None)

    assert resp.json() == {"avatar_uploads": True}


async def test_config_needs_a_signed_in_member(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/config")
    assert resp.status_code == 403
