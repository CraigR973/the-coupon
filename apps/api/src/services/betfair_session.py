"""Process-wide cached Betfair session.

Batch 3 logged into Betfair on *every* request — ``deps.get_betfair_adapter`` built and
authenticated a fresh :class:`~src.services.betfair.Betfair` per call, which is wasteful and
courts Betfair's login throttle. This module owns a single shared live client instead: it
logs in once, keeps the session warm with ``keepAlive`` (a Betfair session idle-times-out),
and re-authenticates transparently if the session lapses. Both the FastAPI request path
(``deps.get_betfair_adapter``) and the Batch 4 scheduler jobs draw from the same session.

The session is created lazily on first use and closed on app shutdown (``main.lifespan``).
Tests override ``deps.get_betfair_adapter`` with ``FakeBetfair`` so this module is bypassed
in the request path; its own logic is covered by :mod:`tests.test_betfair_session`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from src.services.betfair import Betfair, BetfairAdapter, BetfairError

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Re-validate the session with keepAlive at most this often. A Betfair session lapses after a
# spell of inactivity, so anything staler than this is refreshed before it's handed out; a
# burst of requests inside the window reuses the live session without extra identity calls.
_KEEPALIVE_AFTER = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(UTC)


class BetfairSession:
    """A single shared, kept-warm live Betfair client.

    :meth:`acquire` returns a logged-in adapter, first re-validating (or re-establishing)
    the session when it has gone stale. An :class:`asyncio.Lock` serialises the login /
    keepAlive so a burst of concurrent callers triggers at most one authentication.
    """

    def __init__(self) -> None:
        self._client: Betfair | None = None
        self._validated_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> BetfairAdapter:
        """Return a logged-in client, (re)authenticating or refreshing as needed.

        Raises :class:`~src.services.betfair.BetfairError` when login is impossible (no
        credentials configured, or Betfair unreachable) — the caller maps that to a 503.
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
        client = Betfair.from_settings()
        await client.login()
        self._client = client
        self._validated_at = now
        log.info("betfair session established")

    async def _refresh(self, now: datetime) -> None:
        client = self._client
        assert client is not None
        try:
            await client.keep_alive()
            self._validated_at = now
        except BetfairError as exc:
            # Session lapsed — drop it and authenticate afresh so the caller still gets a
            # live client (or a clean BetfairError if re-login also fails).
            log.warning("betfair keepAlive failed; re-authenticating", error=repr(exc))
            await client.close()
            self._client = None
            self._validated_at = None
            await self._login(now)

    async def close(self) -> None:
        """Close the live client (app shutdown). Safe to call when never established."""
        async with self._lock:
            if self._client is not None:
                await self._client.close()
                self._client = None
                self._validated_at = None


# Module-level singleton shared by the request path and the scheduler jobs.
betfair_session = BetfairSession()
