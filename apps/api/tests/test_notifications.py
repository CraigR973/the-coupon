"""Tests for push subscription endpoints and push_notification_service."""

from __future__ import annotations

import base64
import os
import socket
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from src.auth import get_current_user
from src.config import settings
from src.database import get_db
from src.main import app
from src.models.notification import NotificationPreferences, PushSubscription
from src.models.profile import Profile
from src.services.push_notification_service import (
    PUSH_SEND_TIMEOUT_SECONDS,
    _is_quiet,
    _send_push_sync,
    send_notification,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _user(display_name: str = "Alice") -> MagicMock:
    p = MagicMock(spec=Profile)
    p.id = uuid.uuid4()
    p.display_name = display_name
    p.is_active = True
    p.deleted_at = None
    p.role = "player"
    return p


def _db_with(mock_db: AsyncMock):  # type: ignore[no-untyped-def]
    async def _override():  # type: ignore[no-untyped-def]
        yield mock_db

    return _override


def _sub(user_id: uuid.UUID, endpoint: str = "https://fcm.example/push/abc") -> MagicMock:
    s = MagicMock(spec=PushSubscription)
    s.id = uuid.uuid4()
    s.user_id = user_id
    s.subscription = {"endpoint": endpoint, "keys": {"auth": "x", "p256dh": "y"}}
    s.is_active = True
    s.failed_send_count = 0
    s.last_used_at = None
    return s


def _prefs(user_id: uuid.UUID, **overrides: Any) -> MagicMock:
    p = MagicMock(spec=NotificationPreferences)
    p.user_id = user_id
    p.global_mute = False
    p.quiet_hours_start = None
    p.quiet_hours_end = None
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


# ── Unit tests: _is_quiet ─────────────────────────────────────────────────────


class TestIsQuiet:
    def test_no_quiet_hours_never_quiet(self) -> None:
        prefs = _prefs(uuid.uuid4())
        assert _is_quiet(prefs, datetime(2026, 6, 1, 23, 0)) is False

    def test_quiet_within_overnight_range(self) -> None:
        prefs = _prefs(uuid.uuid4())
        prefs.quiet_hours_start = datetime(2000, 1, 1, 23, 0)
        prefs.quiet_hours_end = datetime(2000, 1, 1, 7, 0)
        assert _is_quiet(prefs, datetime(2026, 6, 1, 23, 30)) is True

    def test_not_quiet_outside_range(self) -> None:
        prefs = _prefs(uuid.uuid4())
        prefs.quiet_hours_start = datetime(2000, 1, 1, 23, 0)
        prefs.quiet_hours_end = datetime(2000, 1, 1, 7, 0)
        assert _is_quiet(prefs, datetime(2026, 6, 1, 12, 0)) is False

    def test_daytime_window(self) -> None:
        prefs = _prefs(uuid.uuid4())
        prefs.quiet_hours_start = datetime(2000, 1, 1, 9, 0)
        prefs.quiet_hours_end = datetime(2000, 1, 1, 17, 0)
        assert _is_quiet(prefs, datetime(2026, 6, 1, 10, 0)) is True
        assert _is_quiet(prefs, datetime(2026, 6, 1, 8, 0)) is False


# ── Unit tests: send_notification ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_notification_skips_when_no_vapid() -> None:
    session = AsyncMock()
    with (
        patch.object(settings, "vapid_private_key", ""),
        patch.object(settings, "vapid_public_key", ""),
    ):
        sent = await send_notification(session, uuid.uuid4(), title="T", body="B")
    assert sent == 0


@pytest.mark.asyncio
async def test_send_notification_suppressed_when_global_mute() -> None:
    user_id = uuid.uuid4()
    prefs = _prefs(user_id, global_mute=True)

    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prefs))

    with (
        patch.object(settings, "vapid_private_key", "private"),
        patch.object(settings, "vapid_public_key", "public"),
    ):
        sent = await send_notification(session, user_id, title="T", body="B")
    assert sent == 0


@pytest.mark.asyncio
async def test_send_notification_delivers_when_no_prefs() -> None:
    """No preferences row → defaults (not muted), should attempt delivery."""
    user_id = uuid.uuid4()
    sub = _sub(user_id)

    session = AsyncMock()
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # prefs
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sub])))),
    ]

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync"),
    ):
        sent = await send_notification(session, user_id, title="Title", body="Body")

    assert sent == 1


@pytest.mark.asyncio
async def test_send_notification_suppressed_during_quiet_hours() -> None:
    user_id = uuid.uuid4()
    prefs = _prefs(
        user_id,
        quiet_hours_start=datetime(2000, 1, 1, 9, 0),
        quiet_hours_end=datetime(2000, 1, 1, 17, 0),
    )

    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prefs))

    with (
        patch.object(settings, "vapid_private_key", "private"),
        patch.object(settings, "vapid_public_key", "public"),
        patch(
            "src.services.push_notification_service._utc_now",
            return_value=datetime(2026, 6, 1, 10, 0),
        ),
    ):
        sent = await send_notification(session, user_id, title="T", body="B")
    assert sent == 0


@pytest.mark.asyncio
async def test_send_notification_quiet_hours_use_user_timezone() -> None:
    user_id = uuid.uuid4()
    prefs = _prefs(
        user_id,
        quiet_hours_start=datetime(2000, 1, 1, 23, 0),
        quiet_hours_end=datetime(2000, 1, 1, 7, 0),
    )

    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=prefs))

    with (
        patch.object(settings, "vapid_private_key", "private"),
        patch.object(settings, "vapid_public_key", "public"),
    ):
        sent = await send_notification(
            session,
            user_id,
            title="T",
            body="B",
            timezone_name="Europe/London",
            now_utc=datetime(2026, 6, 20, 22, 30),
        )
    assert sent == 0


@pytest.mark.asyncio
async def test_send_notification_auto_disables_after_3_failures() -> None:
    from pywebpush import WebPushException

    user_id = uuid.uuid4()
    sub = _sub(user_id)
    sub.failed_send_count = 2
    prefs = _prefs(user_id)

    session = AsyncMock()
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=prefs)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sub])))),
    ]

    def _fail(*_: Any, **__: Any) -> None:
        raise WebPushException("410 Gone")

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync", side_effect=_fail),
    ):
        sent = await send_notification(session, user_id, title="T", body="B")

    assert sent == 0
    assert sub.is_active is False
    assert sub.failed_send_count == 3


# ── HTTP endpoint tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_vapid_public_key() -> None:
    with patch.object(settings, "vapid_public_key", "test-vapid-key"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/push/vapid-public-key")
    assert r.status_code == 200
    assert r.json()["vapid_public_key"] == "test-vapid-key"


@pytest.mark.asyncio
async def test_get_vapid_public_key_503_when_not_configured() -> None:
    with patch.object(settings, "vapid_public_key", ""):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/push/vapid-public-key")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_subscribe_push() -> None:
    user = _user()
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/push/subscribe",
                json={
                    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
                    "keys": {"auth": "aaa", "p256dh": "bbb"},
                    "device_hint": "Chrome/120",
                },
            )
        assert r.status_code == 201
        assert r.json()["status"] == "subscribed"
        mock_db.add.assert_called_once()
    finally:
        app.dependency_overrides.clear()


# ── Batch 82: the subscribe endpoint is an SSRF sink unless it is validated ────


async def _subscribe(endpoint: str) -> int:
    """POST one endpoint to /push/subscribe and return the status code."""
    user = _user()
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/api/v1/push/subscribe",
                json={"endpoint": endpoint, "keys": {"auth": "aaa", "p256dh": "bbb"}},
            )
        return r.status_code
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # plaintext
        "file:///etc/passwd",  # not even http
        "https://127.0.0.1/push",  # loopback
        "https://[::1]/push",  # loopback, v6
        "https://10.1.2.3/push",  # private range
        "https://172.16.4.5/push",  # private range
        "https://192.168.0.9/push",  # private range
        "https://169.254.169.254/latest/meta-data/",  # link-local: the metadata service
        "https://attacker.example.com/collect",  # off-allowlist name
        "https://fcm.googleapis.com.evil.example/x",  # allowlisted host as a prefix
        "https://evil.example/x?u=fcm.googleapis.com",  # allowlisted host in the query
        "https://fcm.googleapis.com@evil.example/x",  # allowlisted host as userinfo
        "https://notify.windows.com.evil.example/x",  # suffix match must not be loose
        "https://fcm.googleapis.com:8443/fcm/send/abc",  # allowlisted host, another service
        "https://web.push.apple.com:22/QABC123",  # allowlisted host, not even HTTPS's port
    ],
)
async def test_subscribe_rejects_untrusted_endpoint(endpoint: str) -> None:
    status_code = await _subscribe(endpoint)
    assert 400 <= status_code < 500, f"{endpoint} should have been refused"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc123",
        "https://updates.push.services.mozilla.com/wpush/v2/abc123",
        "https://web.push.apple.com/QABC123",
        "https://par02p.notify.windows.com/w/?token=abc",
        "https://fcm.googleapis.com:443/fcm/send/abc123",  # the default port, spelled out
    ],
)
async def test_subscribe_accepts_real_push_services(endpoint: str) -> None:
    assert await _subscribe(endpoint) == 201


@pytest.mark.asyncio
async def test_unsubscribe_push_deactivates() -> None:
    user = _user()
    sub = _sub(user.id)
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=sub))

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.request(
                "DELETE",
                "/api/v1/push/unsubscribe",
                json={"endpoint": "https://fcm.example/push/abc"},
            )
        assert r.status_code == 200
        assert sub.is_active is False
    finally:
        app.dependency_overrides.clear()


def _empty_leagues() -> MagicMock:
    """A ``db.execute`` result for ``_league_mutes`` with no rows to iterate."""
    return MagicMock(__iter__=MagicMock(return_value=iter([])))


@pytest.mark.asyncio
async def test_get_preferences_creates_defaults() -> None:
    user = _user()
    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # prefs lookup
        _empty_leagues(),  # _league_mutes
    ]

    async def _refresh(obj: Any) -> None:
        if isinstance(obj, NotificationPreferences):
            obj.global_mute = False
            obj.quiet_hours_start = None
            obj.quiet_hours_end = None

    mock_db.refresh = _refresh

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/notifications/preferences")
        assert r.status_code == 200
        data = r.json()
        assert data["global_mute"] is False
        assert data["leagues"] == []
        mock_db.add.assert_called_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_preferences() -> None:
    user = _user()
    prefs = MagicMock(spec=NotificationPreferences)
    prefs.user_id = user.id
    prefs.global_mute = False
    prefs.quiet_hours_start = None
    prefs.quiet_hours_end = None

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=prefs)),  # prefs lookup
        _empty_leagues(),  # _league_mutes
    ]

    async def _refresh(obj: Any) -> None:
        pass

    mock_db.refresh = _refresh

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                "/api/v1/notifications/preferences",
                json={
                    "global_mute": True,
                    "quiet_hours_start": "22:00",
                    "quiet_hours_end": "07:00",
                },
            )
        assert r.status_code == 200
        assert prefs.global_mute is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_preferences_includes_league_mutes() -> None:
    user = _user()
    prefs = MagicMock(spec=NotificationPreferences)
    prefs.user_id = user.id
    prefs.global_mute = False
    prefs.quiet_hours_start = None
    prefs.quiet_hours_end = None

    league_id = uuid.uuid4()
    league_row = MagicMock(id=league_id, notification_muted=True)
    league_row.name = "Friday League"

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=prefs)),  # prefs lookup
        MagicMock(__iter__=MagicMock(return_value=iter([league_row]))),  # _league_mutes
    ]

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/notifications/preferences")
        assert r.status_code == 200
        data = r.json()
        assert data["leagues"] == [
            {"league_id": str(league_id), "league_name": "Friday League", "muted": True}
        ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_preferences_updates_league_mute() -> None:
    user = _user()
    prefs = MagicMock(spec=NotificationPreferences)
    prefs.user_id = user.id
    prefs.global_mute = False
    prefs.quiet_hours_start = None
    prefs.quiet_hours_end = None

    league_id = uuid.uuid4()
    membership = MagicMock()
    membership.league_id = league_id
    membership.notification_muted = False

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=prefs)),  # prefs lookup
        MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(__iter__=MagicMock(return_value=iter([membership])))
            )
        ),
        _empty_leagues(),  # _league_mutes for the response
    ]

    async def _refresh(obj: Any) -> None:
        pass

    mock_db.refresh = _refresh

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _db_with(mock_db)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.patch(
                "/api/v1/notifications/preferences",
                json={"league_mutes": {str(league_id): True}},
            )
        assert r.status_code == 200
        assert membership.notification_muted is True
    finally:
        app.dependency_overrides.clear()


# ── Batch 142: a push service that never answers ───────────────────────────────


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _browser_keys() -> dict[str, str]:
    """A real ``keys`` pair, so the payload genuinely encrypts and the send genuinely
    reaches the network — the only place a hang can happen."""
    browser = ec.generate_private_key(ec.SECP256R1())
    point = browser.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"p256dh": _b64url(point), "auth": _b64url(os.urandom(16))}


def _vapid_private_key() -> str:
    server = ec.generate_private_key(ec.SECP256R1())
    return _b64url(server.private_numbers().private_value.to_bytes(32, "big"))


@contextmanager
def _push_service_that_never_answers() -> Iterator[str]:
    """A port that completes the TCP handshake and then says nothing, ever.

    The kernel accepts a connection into the listen backlog by itself, so the client's
    TLS hello goes out and waits — a push service that has hung, as opposed to one that is
    down, which refuses at once and was never the danger.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    try:
        yield f"https://127.0.0.1:{listener.getsockname()[1]}/push/hung"
    finally:
        listener.close()


def test_every_push_is_sent_with_a_timeout() -> None:
    """pywebpush defaults to none and hands ``None`` to ``requests``, which then waits."""
    with patch("src.services.push_notification_service.webpush") as push:
        _send_push_sync({"endpoint": "https://fcm.googleapis.com/x", "keys": {}}, "{}")
    assert push.call_args.kwargs["timeout"] == PUSH_SEND_TIMEOUT_SECONDS
    assert 0 < PUSH_SEND_TIMEOUT_SECONDS <= 10


@pytest.mark.asyncio
async def test_a_hanging_push_service_is_abandoned_at_the_timeout() -> None:
    """The row's verification: a hung push service does not hold the request.

    The bound is shortened so the test is quick; the call path is the real one — a real
    payload encrypted against real keys, sent to a socket that never replies. Without a
    timeout this call does not return at all.
    """
    user_id = uuid.uuid4()
    session = AsyncMock()
    with _push_service_that_never_answers() as endpoint:
        sub = _sub(user_id, endpoint)
        sub.subscription = {"endpoint": endpoint, "keys": _browser_keys()}
        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # prefs
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sub])))),
        ]
        with (
            patch.object(settings, "vapid_private_key", _vapid_private_key()),
            patch.object(settings, "vapid_public_key", "pub"),
            patch("src.services.push_notification_service.PUSH_SEND_TIMEOUT_SECONDS", 0.5),
            patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}),
            # The module's own logger, not structlog's capture: the app caches a logger on
            # first use, so a capture set up after an earlier test has logged sees nothing.
            patch("src.services.push_notification_service.log") as log,
        ):
            started = time.monotonic()
            sent = await send_notification(session, user_id, title="T", body="B")
            elapsed = time.monotonic() - started

    assert sent == 0, "nothing reached the member, so nothing may be counted as sent"
    events = [call.args[0] for call in log.warning.call_args_list]
    assert "push send timed out" in events, f"not a timeout: {log.mock_calls}"
    # At least the bound itself, which proves the service really hung rather than refused;
    # the ceiling is margin for a loaded machine, not a performance claim.
    assert 0.4 <= elapsed < 5, f"the send held the request for {elapsed:.2f}s"
    assert sub.failed_send_count == 0, "a hung push service is not a dead subscription"
