"""Unit tests for the shared, kept-warm Betfair session and its use in ``deps``.

The session logs in once, refreshes with keepAlive after an inactivity window, and
re-authenticates transparently when a session lapses. A stub client stands in for the live
``Betfair`` client and ``_now`` is patched to drive the clock deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.services.betfair import BetfairAuthError, BetfairError
from src.services.betfair_session import _KEEPALIVE_AFTER, BetfairSession

BASE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class _StubClient:
    """Stand-in for the live ``Betfair`` client, counting auth calls."""

    def __init__(self, token: str = "TOKEN") -> None:
        self.token = token
        self.login_calls = 0
        self.keep_alive_calls = 0
        self.closed = False
        self.keep_alive_error: Exception | None = None

    async def login(self) -> str:
        self.login_calls += 1
        return self.token

    async def keep_alive(self) -> None:
        self.keep_alive_calls += 1
        if self.keep_alive_error is not None:
            raise self.keep_alive_error

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_acquire_logs_in_once_and_reuses_within_window() -> None:
    stub = _StubClient()
    session = BetfairSession()
    with (
        patch("src.services.betfair_session.Betfair.from_settings", return_value=stub),
        patch("src.services.betfair_session._now", return_value=BASE),
    ):
        first = await session.acquire()
        second = await session.acquire()
    assert first is stub and second is stub
    assert stub.login_calls == 1  # authenticated once
    assert stub.keep_alive_calls == 0  # within the window → no refresh


@pytest.mark.asyncio
async def test_acquire_keepalives_after_window() -> None:
    stub = _StubClient()
    session = BetfairSession()
    times = [BASE, BASE + _KEEPALIVE_AFTER + timedelta(seconds=1)]
    with (
        patch("src.services.betfair_session.Betfair.from_settings", return_value=stub),
        patch("src.services.betfair_session._now", side_effect=times),
    ):
        await session.acquire()  # login
        await session.acquire()  # stale → keepAlive, not a fresh login
    assert stub.login_calls == 1
    assert stub.keep_alive_calls == 1


@pytest.mark.asyncio
async def test_acquire_reauthenticates_when_keepalive_fails() -> None:
    stale = _StubClient("OLD")
    stale.keep_alive_error = BetfairAuthError("session expired")
    fresh = _StubClient("NEW")
    session = BetfairSession()
    times = [BASE, BASE + _KEEPALIVE_AFTER + timedelta(minutes=1)]
    with (
        patch("src.services.betfair_session.Betfair.from_settings", side_effect=[stale, fresh]),
        patch("src.services.betfair_session._now", side_effect=times),
    ):
        first = await session.acquire()  # login → stale
        second = await session.acquire()  # keepAlive fails → drop + re-login → fresh
    assert first is stale and second is fresh
    assert stale.keep_alive_calls == 1
    assert stale.closed is True  # the lapsed client is closed
    assert fresh.login_calls == 1  # re-authenticated on a new client


@pytest.mark.asyncio
async def test_acquire_propagates_login_failure() -> None:
    session = BetfairSession()
    with (
        patch(
            "src.services.betfair_session.Betfair.from_settings",
            side_effect=BetfairAuthError("credentials not configured"),
        ),
        patch("src.services.betfair_session._now", return_value=BASE),
        pytest.raises(BetfairAuthError),
    ):
        await session.acquire()


@pytest.mark.asyncio
async def test_close_is_safe_before_and_after_login() -> None:
    session = BetfairSession()
    await session.close()  # never established — no error

    stub = _StubClient()
    with (
        patch("src.services.betfair_session.Betfair.from_settings", return_value=stub),
        patch("src.services.betfair_session._now", return_value=BASE),
    ):
        await session.acquire()
        await session.close()
    assert stub.closed is True


# ── deps.get_betfair_adapter draws from the shared session ──────────────────────


@pytest.mark.asyncio
async def test_get_betfair_adapter_returns_shared_client() -> None:
    from src.deps import get_betfair_adapter

    sentinel = object()
    with patch("src.deps.betfair_session.acquire", new=AsyncMock(return_value=sentinel)):
        assert await get_betfair_adapter() is sentinel


@pytest.mark.asyncio
async def test_get_betfair_adapter_maps_betfair_error_to_503() -> None:
    from src.deps import get_betfair_adapter

    with patch(
        "src.deps.betfair_session.acquire", new=AsyncMock(side_effect=BetfairError("unreachable"))
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_betfair_adapter()
    assert exc_info.value.status_code == 503
