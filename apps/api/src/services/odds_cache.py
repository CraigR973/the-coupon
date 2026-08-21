"""A short-lived odds cache sitting between the request path and the provider.

``fetch_odds`` is called *in the request path* — once per pick-page load
(``routers/gameweek.py``) and once per pick submission (``routers/picks.py``). Against the
Betfair Exchange that was merely wasteful. Against odds-api.io it is a correctness
problem: the free plan allows 100 requests/hour and 500/day, and fifteen members
refreshing the pick page would exhaust the daily quota before Saturday lunchtime.

This wrapper makes upstream traffic a function of *time*, not of how many members are
looking. Entries are keyed per event, so:

* a slate refresh populates every fixture in one batch, and the pick submissions that
  follow are served from that same batch;
* an event the provider does not price is cached as *not priced*, so an unpriced fixture
  is not re-requested on every page load;
* an :class:`asyncio.Lock` serialises refills, so fifteen simultaneous loads of a cold
  cache produce one upstream call rather than fifteen.

Slate and settlement are not cached: both are scheduler-driven, run a handful of times a
day, and must see fresh data when they do run.

Batch 48 added the other thing a cache is good for. The entries survive an upstream
failure — they are merely past their TTL — so ``fetch_odds_best_effort`` serves the last
known prices to the pick screen instead of letting a provider ``429`` become a ``500``.
``fetch_odds`` itself still raises, because the price frozen onto a pick is scored on.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date

import structlog

from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    OddsProvider,
    OddsProviderError,
    OddsSnapshot,
    Slate,
    SlateWindow,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _Entry:
    """One event's cached odds. ``odds`` is ``None`` when the provider prices nothing."""

    odds: FixtureOdds | None
    stored_at: float


class CachingOddsProvider(OddsProvider):
    """Wraps any provider, serving ``fetch_odds`` from a per-event TTL cache.

    ``ttl_seconds`` is the freshness bound on a price a member can be scored on, traded
    off against the provider's quota. The measured launch Saturday carries 131 qualifying
    fixtures, which the provider serves ten per request, so one full refresh costs 14
    calls and the hourly cost is ``14 * 3600 / ttl``. See ``Settings.odds_cache_ttl_seconds``
    for the budget arithmetic.
    """

    def __init__(
        self,
        inner: OddsProvider,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    @property
    def inner(self) -> OddsProvider:
        """The wrapped provider — for tests and for logging which source is live."""
        return self._inner

    # -- lifecycle (delegated) -------------------------------------------------

    async def login(self) -> str:
        return await self._inner.login()

    async def keep_alive(self) -> None:
        await self._inner.keep_alive()

    async def close(self) -> None:
        self._entries.clear()
        await self._inner.close()

    # -- uncached domain operations -------------------------------------------

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        return await self._inner.fetch_slate(window, starts_on, competition_ids=competition_ids)

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return await self._inner.settle(event_ids)

    async def fetch_competitions(self) -> list[Competition]:
        # Delegated without a TTL of its own. The catalogue turns over between seasons,
        # not between page loads, and the wrapped provider already memoises it per client
        # (``OddsApiProvider._all_leagues``), so a second cache here would duplicate that
        # while adding an expiry the underlying one does not have.
        return await self._inner.fetch_competitions()

    # -- the cached one --------------------------------------------------------

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        """Return odds for the given events, fetching only the ones that have gone stale.

        The result carries an entry per event the provider prices, in the same order the
        underlying provider would return them (sorted by event id), so callers cannot tell
        a cached response from a fresh one.

        ``max_age_seconds`` tightens (never loosens) the TTL for this call. Browsing the
        slate accepts a stale-ish price; freezing one onto a pick does not, and paying for
        that freshness on the single fixture being picked costs one request rather than a
        sweep of the whole card.

        Raises whatever the wrapped provider raises. That is the pick path's contract —
        see :meth:`fetch_odds_best_effort` for the browsing one.
        """
        return (await self._snapshot(event_ids, max_age_seconds, best_effort=False)).odds

    async def fetch_odds_best_effort(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> OddsSnapshot:
        """The same read, serving the last known prices when the refresh fails.

        This is the whole reason the cache is the right place for Batch 48's fix: when the
        upstream call raises, the entries are still sitting here, merely past their TTL.
        Falling through to them costs the pick screen its freshness instead of its
        availability, and the ``degraded`` flag is what lets the client say so rather than
        presenting stale numbers as current.

        An empty cache degrades to no prices at all, which still renders the fixtures.
        """
        return await self._snapshot(event_ids, max_age_seconds, best_effort=True)

    async def _snapshot(
        self, event_ids: Sequence[str], max_age_seconds: float | None, *, best_effort: bool
    ) -> OddsSnapshot:
        """Refill what has gone stale, then answer from the entries — both callers' body."""
        wanted = list(dict.fromkeys(event_ids))
        if not wanted:
            return OddsSnapshot(odds=[], degraded=False)

        ttl = self._ttl if max_age_seconds is None else min(self._ttl, max_age_seconds)
        degraded = False

        async with self._lock:
            now = self._clock()
            stale = [event_id for event_id in wanted if self._stale(event_id, now, ttl)]
            if stale:
                try:
                    fetched = await self._inner.fetch_odds(stale)
                except OddsProviderError as exc:
                    if not best_effort:
                        raise
                    # The stale entries stay exactly as they are, so the next call tries
                    # upstream again — a provider that recovers is served fresh prices on
                    # the next page load rather than on the next TTL boundary.
                    degraded = True
                    log.warning(
                        "odds refresh failed, serving cached",
                        requested=len(wanted),
                        stale=len(stale),
                        error=repr(exc),
                    )
                else:
                    by_event = {o.provider_event_id: o for o in fetched}
                    stored_at = self._clock()
                    for event_id in stale:
                        self._entries[event_id] = _Entry(by_event.get(event_id), stored_at)
                    log.debug(
                        "odds cache refill", requested=len(wanted), fetched_upstream=len(stale)
                    )

            results = [
                entry.odds
                for entry in (self._entries.get(event_id) for event_id in wanted)
                if entry is not None and entry.odds is not None
            ]

        results.sort(key=lambda o: o.provider_event_id)
        return OddsSnapshot(odds=results, degraded=degraded)

    def _stale(self, event_id: str, now: float, ttl: float) -> bool:
        entry = self._entries.get(event_id)
        return entry is None or now - entry.stored_at >= ttl

    def invalidate(self) -> None:
        """Drop every cached entry — used when a session is re-established."""
        self._entries.clear()
