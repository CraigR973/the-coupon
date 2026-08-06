"""Process-wide football-data client — built once, closed on shutdown.

The counterpart to :mod:`src.services.odds_session`, and deliberately much thinner. There
is no keep-alive because both implementations are key-authenticated, and there is no cache
in front because **nothing reads through this in the request path**: ingestion writes
``teams`` / ``matches`` / ``standings`` on the scheduler's clock and every screen reads
those tables. Against a 100/day allowance that is not an optimisation, it is the design.

``acquire`` returns ``None`` when no provider is configured, which is the default. That is
not an error — an unconfigured deployment simply ingests nothing, and the football screens
show whatever is already stored (usually nothing). It keeps Batch 16 from becoming a new
required secret for an already-sealed production environment.
"""

from __future__ import annotations

import asyncio

import structlog

from src.config import Environment, FootballDataProviderName, settings
from src.services.api_football import ApiFootballProvider
from src.services.fake_football import FakeFootballData
from src.services.football_provider import FootballDataError, FootballDataProvider

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def build_football_provider() -> FootballDataProvider | None:
    """Construct the configured provider, or ``None`` when ingestion is switched off.

    Raises :class:`~src.services.football_provider.FootballDataError` when the selection
    is not usable — ``fake`` in production, or a live provider with no key.
    """
    if settings.football_data_provider == FootballDataProviderName.none:
        return None
    if settings.football_data_provider == FootballDataProviderName.fake:
        if settings.environment == Environment.production:
            raise FootballDataError("Fake football-data provider is forbidden in production")
        return FakeFootballData.with_sample_data()
    return ApiFootballProvider.from_settings()


class FootballDataSession:
    """A single shared football-data client, created on first use.

    An :class:`asyncio.Lock` serialises construction so a burst of concurrent callers
    builds at most one client — which matters more than it looks, because the client
    memoises the provider's league catalogue and throwing that away costs a request from
    a hundred-a-day budget.
    """

    def __init__(self) -> None:
        self._client: FootballDataProvider | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> FootballDataProvider | None:
        """The shared client, or ``None`` when no provider is configured."""
        async with self._lock:
            if self._client is None:
                self._client = build_football_provider()
                if self._client is not None:
                    log.info(
                        "football data session established",
                        provider=settings.football_data_provider.value,
                    )
            return self._client

    async def close(self) -> None:
        """Close the client (app shutdown). Safe to call when never established."""
        async with self._lock:
            if self._client is not None:
                await self._client.close()
                self._client = None


#: Module-level singleton shared by the scheduler jobs.
football_session = FootballDataSession()
