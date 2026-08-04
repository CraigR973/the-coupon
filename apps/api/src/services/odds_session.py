"""Process-wide odds provider — built once, kept warm, and cached in front.

Batch 3 authenticated to the odds source on *every* request. This module owns a single
shared client instead: it establishes the session once, keeps it warm (a Betfair session
idle-times-out; a key-authenticated odds-api.io client cannot), and re-authenticates
transparently if it lapses. Both the FastAPI request path (``deps.get_odds_provider``)
and the scheduler jobs draw from the same instance.

The client handed out is wrapped in
:class:`~src.services.odds_cache.CachingOddsProvider`, which is what keeps the pick page
inside odds-api.io's 100/hour and 500/day quota — ``fetch_odds`` runs in the request path,
so without it fifteen members refreshing would exhaust the day's requests.

Which provider is built comes from ``ODDS_PROVIDER``; ``fake`` is refused in production
exactly as the retired ``BF_FAKE_MODE`` was. The session is created lazily on first use
and closed on app shutdown (``main.lifespan``). Tests override ``deps.get_odds_provider``
so this module is bypassed in the request path; its own logic is covered by
:mod:`tests.test_odds_session`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from src.config import Environment, OddsProviderName, settings
from src.services.betfair import Betfair, FakeBetfair
from src.services.odds_api import OddsApiProvider
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import OddsProvider, OddsProviderError

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Re-validate the session with keepAlive at most this often. A Betfair session lapses after a
# spell of inactivity, so anything staler than this is refreshed before it's handed out; a
# burst of requests inside the window reuses the live session without extra identity calls.
_KEEPALIVE_AFTER = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(UTC)


def build_provider() -> OddsProvider:
    """Construct the configured provider (uncached, unauthenticated).

    Raises :class:`~src.services.odds_provider.OddsProviderError` when the selection is
    not usable — ``fake`` in production, or a live provider with no credentials.
    """
    if settings.odds_provider == OddsProviderName.fake:
        if settings.environment == Environment.production:
            raise OddsProviderError("Fake odds provider is forbidden in production")
        return FakeBetfair.with_sample_data()
    if settings.odds_provider == OddsProviderName.betfair:
        return Betfair.from_settings()
    return OddsApiProvider.from_settings()


class OddsProviderSession:
    """A single shared, kept-warm odds client with a cache in front.

    :meth:`acquire` returns a ready client, first re-validating (or re-establishing) the
    session when it has gone stale. An :class:`asyncio.Lock` serialises the login /
    keepAlive so a burst of concurrent callers triggers at most one authentication.
    """

    def __init__(self) -> None:
        self._client: CachingOddsProvider | None = None
        self._validated_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> OddsProvider:
        """Return a ready client, (re)authenticating or refreshing as needed.

        Raises :class:`~src.services.odds_provider.OddsProviderError` when the provider
        cannot be used (unconfigured, or unreachable) — the caller maps that to a 503.
        """
        async with self._lock:
            now = _now()
            if self._client is None:
                await self._login(now)
            elif self._validated_at is None or now - self._validated_at > _KEEPALIVE_AFTER:
                await self._refresh(now)
            assert self._client is not None  # _login sets it or raises
            return self._client

    async def _login(self, now: datetime) -> None:
        client = CachingOddsProvider(build_provider(), ttl_seconds=settings.odds_cache_ttl_seconds)
        await client.login()
        self._client = client
        self._validated_at = now
        log.info("odds provider session established", provider=settings.odds_provider.value)

    async def _refresh(self, now: datetime) -> None:
        client = self._client
        assert client is not None
        try:
            await client.keep_alive()
            self._validated_at = now
        except OddsProviderError as exc:
            # Session lapsed — drop it and authenticate afresh so the caller still gets a
            # usable client (or a clean OddsProviderError if re-login also fails). Cached
            # odds go with it: a lapsed session is exactly when a stale price is suspect.
            log.warning("odds provider keepAlive failed; re-authenticating", error=repr(exc))
            await client.close()
            self._client = None
            self._validated_at = None
            await self._login(now)

    async def close(self) -> None:
        """Close the client (app shutdown). Safe to call when never established."""
        async with self._lock:
            if self._client is not None:
                await self._client.close()
                self._client = None
                self._validated_at = None


# Module-level singleton shared by the request path and the scheduler jobs.
odds_session = OddsProviderSession()
