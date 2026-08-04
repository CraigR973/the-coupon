"""Unit tests for the shared, kept-warm odds session and its use in ``deps``.

The session builds the configured provider once, refreshes with keepAlive after an
inactivity window, and re-authenticates transparently when a session lapses. A stub client
stands in for a live provider and ``_now`` is patched to drive the clock deterministically.

What ``acquire`` hands out is the provider wrapped in
:class:`~src.services.odds_cache.CachingOddsProvider`, so the assertions reach through
``.inner`` — the wrapping is the thing that keeps the request path inside odds-api.io's
rate limit, so a test that saw the bare client would be testing the wrong object.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.config import Environment, OddsProviderName
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    EventSettlement,
    FixtureOdds,
    OddsProvider,
    OddsProviderAuthError,
    OddsProviderError,
    Slate,
)
from src.services.odds_session import _KEEPALIVE_AFTER, OddsProviderSession, build_provider

BASE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


class _StubClient(OddsProvider):
    """Stand-in for a live provider, counting auth calls."""

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

    async def fetch_slate(self, saturday: date) -> Slate:
        return Slate(saturday=saturday, fixtures=[])

    async def fetch_odds(self, event_ids: Sequence[str]) -> list[FixtureOdds]:
        return []

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return []


def _inner(provider: OddsProvider) -> OddsProvider:
    assert isinstance(provider, CachingOddsProvider)
    return provider.inner


async def test_acquire_builds_once_and_reuses_within_window() -> None:
    stub = _StubClient()
    session = OddsProviderSession()
    with (
        patch("src.services.odds_session.build_provider", return_value=stub),
        patch("src.services.odds_session._now", return_value=BASE),
    ):
        first = await session.acquire()
        second = await session.acquire()
    assert first is second
    assert _inner(first) is stub
    assert stub.login_calls == 1  # authenticated once
    assert stub.keep_alive_calls == 0  # within the window → no refresh


async def test_acquired_client_caches_odds() -> None:
    """The request path must never receive an uncached provider."""
    stub = _StubClient()
    session = OddsProviderSession()
    with (
        patch("src.services.odds_session.build_provider", return_value=stub),
        patch("src.services.odds_session._now", return_value=BASE),
    ):
        provider = await session.acquire()
    assert isinstance(provider, CachingOddsProvider)


async def test_acquire_keepalives_after_window() -> None:
    stub = _StubClient()
    session = OddsProviderSession()
    times = [BASE, BASE + _KEEPALIVE_AFTER + timedelta(seconds=1)]
    with (
        patch("src.services.odds_session.build_provider", return_value=stub),
        patch("src.services.odds_session._now", side_effect=times),
    ):
        await session.acquire()  # login
        await session.acquire()  # stale → keepAlive, not a fresh login
    assert stub.login_calls == 1
    assert stub.keep_alive_calls == 1


async def test_acquire_reauthenticates_when_keepalive_fails() -> None:
    stale = _StubClient("OLD")
    stale.keep_alive_error = OddsProviderAuthError("session expired")
    fresh = _StubClient("NEW")
    session = OddsProviderSession()
    times = [BASE, BASE + _KEEPALIVE_AFTER + timedelta(minutes=1)]
    with (
        patch("src.services.odds_session.build_provider", side_effect=[stale, fresh]),
        patch("src.services.odds_session._now", side_effect=times),
    ):
        first = await session.acquire()  # login → stale
        second = await session.acquire()  # keepAlive fails → drop + re-login → fresh
    assert _inner(first) is stale
    assert _inner(second) is fresh
    assert stale.keep_alive_calls == 1
    assert stale.closed is True  # the lapsed client is closed
    assert fresh.login_calls == 1  # re-authenticated on a new client


async def test_acquire_propagates_login_failure() -> None:
    session = OddsProviderSession()
    with (
        patch(
            "src.services.odds_session.build_provider",
            side_effect=OddsProviderAuthError("credentials not configured"),
        ),
        patch("src.services.odds_session._now", return_value=BASE),
        pytest.raises(OddsProviderAuthError),
    ):
        await session.acquire()


async def test_close_is_safe_before_and_after_login() -> None:
    session = OddsProviderSession()
    await session.close()  # never established — no error

    stub = _StubClient()
    with (
        patch("src.services.odds_session.build_provider", return_value=stub),
        patch("src.services.odds_session._now", return_value=BASE),
    ):
        await session.acquire()
        await session.close()
    assert stub.closed is True


# ── build_provider: ODDS_PROVIDER selects the source ───────────────────────────


def test_build_provider_defaults_to_odds_api() -> None:
    from src.services.odds_api import OddsApiProvider

    with patch("src.services.odds_session.settings") as fake_settings:
        fake_settings.odds_provider = OddsProviderName.oddsapi
        fake_settings.odds_api_key = "test-key"
        fake_settings.odds_api_bookmaker = "Bet365"
        fake_settings.odds_api_base_url = "https://api.odds-api.io/v3"
        with patch("src.services.odds_api.settings", fake_settings):
            provider = build_provider()
    assert isinstance(provider, OddsApiProvider)


def test_build_provider_fake_is_refused_in_production() -> None:
    """The same guard the retired ``BF_FAKE_MODE`` had — canned odds never ship live."""
    with patch("src.services.odds_session.settings") as fake_settings:
        fake_settings.odds_provider = OddsProviderName.fake
        fake_settings.environment = Environment.production
        with pytest.raises(OddsProviderError, match="forbidden in production"):
            build_provider()


def test_build_provider_fake_outside_production_returns_canned_data() -> None:
    from src.services.betfair import FakeBetfair

    with patch("src.services.odds_session.settings") as fake_settings:
        fake_settings.odds_provider = OddsProviderName.fake
        fake_settings.environment = Environment.staging
        provider = build_provider()
    assert isinstance(provider, FakeBetfair)


# ── deps.get_odds_provider draws from the shared session ───────────────────────


async def test_get_odds_provider_returns_shared_client() -> None:
    from src.deps import get_odds_provider

    sentinel = object()
    with patch("src.deps.odds_session.acquire", new=AsyncMock(return_value=sentinel)):
        assert await get_odds_provider() is sentinel


async def test_get_odds_provider_maps_provider_error_to_503() -> None:
    from src.deps import get_odds_provider

    with patch(
        "src.deps.odds_session.acquire",
        new=AsyncMock(side_effect=OddsProviderError("unreachable")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_odds_provider()
    assert exc_info.value.status_code == 503
