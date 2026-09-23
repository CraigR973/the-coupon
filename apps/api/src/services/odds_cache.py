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

Batch 114 made three of those sentences true that were only nearly true, after the plan
was exhausted at 08:06 on a match morning with a lock five hours away:

* **"not re-requested on every page load"** was bounded by the *same* TTL a real price
  gets, so a fixture the bookmaker will never price was re-bought twice an hour. It now
  has its own far longer ceiling. The persistent half of that fact — so a restart does not
  re-spend it — is ``fixtures.odds_unpriced_since_utc``, written by the caller from
  :attr:`OddsSnapshot.observed`.
* **a ``429`` cost one request per attempt.** Batch 57 stopped *retrying* one, but nothing
  stopped the next caller from spending another against the same empty budget — a member
  tapping twice inside a second bought two. A short cooldown now serves the cache
  instead, and refuses the pick path without calling upstream.
* **nothing counted what had been spent**, so an exhausted plan and a five-hour-old card
  looked identical from outside. The counters below are what the admin dashboard reads,
  what reserves a floor of the hour for the pick path, and what widens the browse ceiling
  as the remaining budget falls — so freshness degrades along a slope rather than stopping
  at a cliff nobody can see.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator, Callable, Collection, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date

import structlog

from src.services.odds_provider import (
    EVENTS_PER_ODDS_REQUEST,
    Competition,
    EventSettlement,
    FixtureOdds,
    OddsProvider,
    OddsProviderBadRequest,
    OddsProviderError,
    OddsProviderRateLimited,
    OddsSnapshot,
    Slate,
    SlateWindow,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_HOUR = 3600.0
_DAY = 86400.0


@dataclass(frozen=True)
class _Entry:
    """One event's cached odds. ``odds`` is ``None`` when the provider prices nothing."""

    odds: FixtureOdds | None
    stored_at: float


@dataclass(frozen=True)
class OddsBudget:
    """What the plan has left, as this process has counted it.

    An *estimate* of the provider's own accounting, not a copy of it: it counts what this
    process sent and knows nothing of another instance, of the scheduled jobs' slate
    requests, or of what the plan thought before this process started. That is enough for
    the two things it is used for — reserving a floor for the pick path and widening the
    browse ceiling — because both fail safe: an undercount spends into a ``429``, which
    the cooldown already handles, and an overcount serves a slightly staler card.
    """

    hour_used: int
    day_used: int
    hour_limit: int
    day_limit: int
    #: Seconds left on the ``429`` cooldown, or ``None`` when upstream is not suppressed.
    rate_limited_for: float | None

    @property
    def hour_remaining(self) -> int:
        return max(0, self.hour_limit - self.hour_used)

    @property
    def day_remaining(self) -> int:
        return max(0, self.day_limit - self.day_used)


class CachingOddsProvider(OddsProvider):
    """Wraps any provider, serving ``fetch_odds`` from a per-event TTL cache.

    ``ttl_seconds`` is the freshness bound on a price a member can be scored on, traded
    off against the provider's quota. The provider serves ten events per request, so a
    full sweep of a round costs ``ceil(fixtures / 10)`` calls and the hourly cost is
    ``sweep * 3600 / ttl``. See ``Settings.odds_cache_ttl_seconds`` for the budget
    arithmetic and ``tests/test_request_budget.py`` for it asserted against this class.

    ``unpriced_ttl_seconds`` is the same bound for the *absence* of a price, which is a
    far more durable fact and gets a far longer ceiling. It defaults to ``ttl_seconds``,
    which is the pre-Batch-114 behaviour, so a caller that does not care keeps it.

    ``isolation_requests`` is how many extra requests one refill may spend finding the
    expired id inside a chunk the provider refused (Batch 119, :meth:`_isolate`). It
    defaults to ``0`` — a refused chunk simply loses its ten their prices, which is the
    isolation this batch is mainly about; the production session passes
    ``ODDS_ISOLATION_REQUESTS`` so the dead id is also recorded rather than re-asked.
    """

    def __init__(
        self,
        inner: OddsProvider,
        *,
        ttl_seconds: float,
        unpriced_ttl_seconds: float | None = None,
        rate_limited_cooldown_seconds: float = 0.0,
        hourly_request_limit: int | None = None,
        daily_request_limit: int | None = None,
        pick_reserve_requests: int = 0,
        events_per_request: int = EVENTS_PER_ODDS_REQUEST,
        isolation_requests: int = 0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._unpriced_ttl = ttl_seconds if unpriced_ttl_seconds is None else unpriced_ttl_seconds
        self._cooldown = rate_limited_cooldown_seconds
        self._hour_limit = hourly_request_limit
        self._day_limit = daily_request_limit
        self._reserve = pick_reserve_requests
        self._events_per_request = max(1, events_per_request)
        self._isolation_requests = max(0, isolation_requests)
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()
        #: Monotonic timestamps of upstream odds requests, newest last. Pruned to a day.
        self._spent: list[float] = []
        self._rate_limited_until: float | None = None

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
        # One ``/events`` request per competition walked, which is where the whole cost
        # of this call sits. The estimate is the fallback for a provider that cannot
        # report its own spend; the real one can, and then this is exact.
        estimate = len(set(competition_ids)) if competition_ids is not None else 1
        async with self._charging(estimate=estimate):
            return await self._inner.fetch_slate(window, starts_on, competition_ids=competition_ids)

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        # One ``/events/{id}`` lookup per distinct event: settlement is read from the
        # event itself, not from the odds endpoints, which carry only what is still priced.
        async with self._charging(estimate=len(dict.fromkeys(event_ids))):
            return await self._inner.settle(event_ids)

    async def fetch_competitions(self) -> list[Competition]:
        # Delegated without a TTL of its own. The catalogue turns over between seasons,
        # not between page loads, and the wrapped provider already memoises it per client
        # (``OddsApiProvider._all_leagues``), so a second cache here would duplicate that
        # while adding an expiry the underlying one does not have.
        #
        # Charged all the same, because "usually free" is not "free": the first call of a
        # process pays for the catalogue, and that request is as real as any other.
        async with self._charging(estimate=1):
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

        degraded = False
        observed: frozenset[str] = frozenset()

        async with self._lock:
            now = self._clock()
            self._prune(now)
            ttl = self._ceiling(max_age_seconds, for_pick=not best_effort)
            stale = [event_id for event_id in wanted if self._stale(event_id, now, ttl)]
            if stale:
                refusal = self._refuse_upstream(now, for_pick=not best_effort)
                if refusal is not None:
                    # Not a failure to reach the provider — a decision not to ask it. The
                    # pick path is told why; browsing falls through to the entries, which
                    # is the same shape as Batch 48's fallback and for the same reason.
                    if not best_effort:
                        raise refusal
                    degraded = isinstance(refusal, OddsProviderRateLimited)
                    log.info(
                        "odds refresh withheld",
                        requested=len(wanted),
                        stale=len(stale),
                        reason=str(refusal),
                    )
                else:
                    observed, degraded = await self._refill(stale, now, best_effort=best_effort)

            results = [
                entry.odds
                for entry in (self._entries.get(event_id) for event_id in wanted)
                if entry is not None and entry.odds is not None
            ]

        results.sort(key=lambda o: o.provider_event_id)
        return OddsSnapshot(odds=results, degraded=degraded, observed=observed)

    async def _refill(
        self, stale: Sequence[str], now: float, *, best_effort: bool
    ) -> tuple[frozenset[str], bool]:
        """Ask upstream for ``stale`` and store the answer. Returns (observed, degraded).

        Charged to the budget whatever the outcome, because the request left either way —
        that is the whole reason a ``429`` needs a cooldown rather than a retry.

        **One request at a time since Batch 119, and the chunking moved here to make that
        possible.** ``/odds/multi`` answers ``400 One or more eventIds not found`` when
        *any* id in a chunk of ten has expired, and odds-api.io expires an id once its
        match has been played. Asking for the whole card in one call meant one dead
        fixture cost every fixture its price: production logged ``fixtures=202 priced=0``
        three times in one evening, with the degraded banner, on a settled round.

        The chunk is the unit the provider bills *and* the unit a ``400`` destroys, and
        this is the only layer that can say so — :attr:`OddsSnapshot.observed` is computed
        here, and marking a whole rejected chunk unpriced would take nine pickable
        fixtures off the card to record one dead one. So a rejected chunk yields no
        entries and is excluded from ``observed``; every other chunk is untouched.

        The wrapped provider still chunks internally for a caller that hands it more than
        one request's worth directly. Nothing is asked twice: the chunks below are the
        same size it would have used.
        """
        self._charge(now, len(stale))
        observed: set[str] = set()
        rejected: list[Sequence[str]] = []
        degraded = False

        for chunk in self._chunks(stale):
            try:
                fetched = await self._inner.fetch_odds(chunk)
            except OddsProviderRateLimited as exc:
                # The quota is already spent, so the one thing that cannot help is another
                # request. Hold every caller off upstream until it has had a chance to roll
                # over; the entries below are what everyone is served in the meantime.
                self._rate_limited_until = now + self._cooldown
                log.warning(
                    "odds provider rate limited, holding off",
                    stale=len(stale),
                    cooldown_seconds=self._cooldown,
                    error=repr(exc),
                )
                if not best_effort:
                    raise
                return frozenset(observed), True
            except OddsProviderBadRequest as exc:
                if not best_effort:
                    raise
                # At least one id in this chunk is gone, and the answer does not say
                # which. Nothing here is evidence about any of them.
                rejected.append(chunk)
                degraded = True
                log.warning("odds chunk rejected", size=len(chunk), error=str(exc))
                continue
            except OddsProviderError as exc:
                if not best_effort:
                    raise
                # The stale entries stay exactly as they are, so the next call tries
                # upstream again — a provider that recovers is served fresh prices on
                # the next page load rather than on the next TTL boundary. That reason
                # holds for a blip and not for a `429`, which is why the branch above
                # is separate.
                degraded = True
                log.warning(
                    "odds refresh failed, serving cached", stale=len(chunk), error=repr(exc)
                )
                continue
            self._store(chunk, fetched)
            observed.update(chunk)

        if rejected:
            isolated, held_off = await self._isolate(rejected, now)
            observed.update(isolated)
            degraded = degraded or held_off

        log.debug(
            "odds cache refill",
            fetched_upstream=len(stale),
            observed=len(observed),
            rejected_chunks=len(rejected),
        )
        # Everything in `observed` got a definite answer, price or no price. That is what
        # makes it safe for the caller to write `fixtures.odds_unpriced_since_utc`.
        return frozenset(observed), degraded

    def _chunks(self, event_ids: Sequence[str]) -> list[Sequence[str]]:
        """``event_ids`` split into one upstream request's worth each."""
        size = self._events_per_request
        return [event_ids[start : start + size] for start in range(0, len(event_ids), size)]

    def _store(self, asked: Sequence[str], fetched: Sequence[FixtureOdds]) -> None:
        """Record one answered chunk — an entry per id, ``None`` where nothing is priced."""
        by_event = {odds.provider_event_id: odds for odds in fetched}
        stored_at = self._clock()
        for event_id in asked:
            self._entries[event_id] = _Entry(by_event.get(event_id), stored_at)

    async def _isolate(
        self, rejected: Sequence[Sequence[str]], now: float
    ) -> tuple[set[str], bool]:
        """Halve refused chunks until one id can be blamed. Returns (observed, held_off).

        Isolating the chunk keeps the card priced; this is what stops the dead id coming
        back tomorrow. A chunk that is refused is halved and both halves re-asked: a half
        that answers resolves its ids for good, and a half that is refused is halved
        again, down to a single id — and **a single id the provider refuses is a durable
        fact about that one fixture**. It is returned as ``observed`` with no price, which
        is precisely the evidence :func:`~src.services.odds_pricing.record_observations`
        writes ``fixtures.odds_unpriced_since_utc`` from, so ``askable`` stops spending a
        request on it until the bounded re-check falls due.

        **Bounded by design.** At most ``isolation_requests`` extra requests per refill —
        two by default — because this runs on the browsing path against a 100/hour plan.
        Two is enough: each refill halves the suspect set, so a chunk of ten is resolved
        in three refills and six requests, and the rest of the card is priced throughout.
        Spending an unbounded budget chasing a dead id would be the same mistake in the
        other direction.
        """
        budget = self._isolation_requests
        queue = [list(chunk) for chunk in rejected]
        observed: set[str] = set()
        while queue and budget > 0:
            chunk = queue.pop(0)
            halves = (
                [chunk] if len(chunk) == 1 else [chunk[: len(chunk) // 2], chunk[len(chunk) // 2 :]]
            )
            for half in halves:
                if budget <= 0:
                    queue.append(half)
                    break
                budget -= 1
                self._charge(now, len(half))
                try:
                    fetched = await self._inner.fetch_odds(half)
                except OddsProviderRateLimited as exc:
                    self._rate_limited_until = now + self._cooldown
                    log.warning(
                        "odds provider rate limited while isolating a rejected chunk",
                        cooldown_seconds=self._cooldown,
                        error=repr(exc),
                    )
                    return observed, True
                except OddsProviderBadRequest:
                    if len(half) == 1:
                        # The provider has now refused this id on its own. That is as
                        # definite as the API gets: the event does not exist.
                        self._entries[half[0]] = _Entry(None, self._clock())
                        observed.add(half[0])
                        log.info("odds event expired at the provider", event_id=half[0])
                        continue
                    queue.append(half)
                    continue
                except OddsProviderError as exc:
                    # Not evidence about these ids — leave them for the next refill.
                    log.warning("odds isolation probe failed", size=len(half), error=repr(exc))
                    continue
                self._store(half, fetched)
                observed.update(half)
        return observed, bool(queue)

    # -- freshness -------------------------------------------------------------

    def _ceiling(self, max_age_seconds: float | None, *, for_pick: bool) -> float:
        """How old an entry may be for this call, before the per-entry rules below.

        ``max_age_seconds`` tightens and never loosens, as it always has. The budget
        widens the *browsing* ceiling only: the pick path is the one action with a
        deadline and gets exactly the freshness it asked for.
        """
        ttl = self._ttl if max_age_seconds is None else min(self._ttl, max_age_seconds)
        if for_pick:
            return ttl
        return ttl * self._widening()

    def _widening(self) -> float:
        """How much to slacken browsing as the plan runs down — 1x, 2x, then 4x.

        Refreshing at full rate into a wall is what turned a busy morning into a refusal:
        the card kept asking at the near tier until the allowance was gone, and then
        nobody could pick at all. Slackening as the budget falls trades a slightly older
        browsed price — a price the member is no longer scored on blind, because the
        submit path refuses one that has moved — for the allowance still being there at
        lock.
        """
        remaining = self._remaining_fraction()
        if remaining is None or remaining >= 0.5:
            return 1.0
        if remaining >= 0.25:
            return 2.0
        return 4.0

    def _remaining_fraction(self) -> float | None:
        """The tighter of the hourly and daily allowances, as a fraction left.

        ``None`` when neither limit is configured, which is what a test or a deployment
        on an unmetered provider gets: no widening at all, exactly as before Batch 114.
        """
        budget = self.budget()
        fractions: list[float] = []
        if budget.hour_limit > 0:
            fractions.append(budget.hour_remaining / budget.hour_limit)
        if budget.day_limit > 0:
            fractions.append(budget.day_remaining / budget.day_limit)
        return min(fractions) if fractions else None

    def _stale(self, event_id: str, now: float, ttl: float) -> bool:
        """Whether this event needs asking about, at the ceiling its answer earns.

        A cached *absence* of a price gets the longer ceiling — it is a fact about what
        the bookmaker offers, not a number that moves, and on 2026-09-05 re-buying it
        every half hour for 103 fixtures was 22 requests an hour spent on the answer *no*.
        The longer ceiling wins even over a tightened ``max_age_seconds``: the pick path
        asking again inside a minute cannot discover a market that is not there, and the
        bounded re-check is what finds one a bookmaker opens late.
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return True
        ceiling = ttl if entry.odds is not None else max(ttl, self._unpriced_ttl)
        return now - entry.stored_at >= ceiling

    # -- budget ----------------------------------------------------------------

    def budget(self) -> OddsBudget:
        """What the plan has left, for the admin dashboard and the rules above."""
        now = self._clock()
        self._prune(now)
        cooling = self._rate_limited_until
        return OddsBudget(
            hour_used=sum(1 for sent in self._spent if now - sent < _HOUR),
            day_used=len(self._spent),
            hour_limit=self._hour_limit or 0,
            day_limit=self._day_limit or 0,
            rate_limited_for=(cooling - now if cooling is not None and cooling > now else None),
        )

    def _prune(self, now: float) -> None:
        """Drop spend older than a day, and a cooldown that has expired."""
        if self._spent and now - self._spent[0] >= _DAY:
            self._spent = [sent for sent in self._spent if now - sent < _DAY]
        if self._rate_limited_until is not None and now >= self._rate_limited_until:
            self._rate_limited_until = None

    def _charge(self, now: float, events: int) -> None:
        """Record what asking about ``events`` events costs, in *requests*."""
        self._charge_requests(now, math.ceil(events / self._events_per_request))

    def _charge_requests(self, now: float, requests: int) -> None:
        """Record ``requests`` upstream requests against the plan."""
        if requests > 0:
            self._spent.extend([now] * requests)

    def _inner_requests(self) -> int | None:
        """How many requests the wrapped provider says it has sent, if it counts them.

        ``OddsApiProvider`` counts at its single HTTP chokepoint, so the delta across a
        call is exactly what that call cost — including retries, and including the
        catalogue fetch a slate walk makes on the first call of a process. A provider
        that does not count (the fakes, Betfair) falls back to the caller's estimate.
        """
        counted = getattr(self._inner, "requests_made", None)
        return counted if isinstance(counted, int) else None

    @asynccontextmanager
    async def _charging(self, *, estimate: int) -> AsyncIterator[None]:
        """Charge the plan for whatever the wrapped call actually spends.

        Batch 160. The counter was charged **only** from :meth:`_refill`, so
        ``fetch_slate``, ``fetch_competitions`` and ``settle`` — three separate provider
        entry points — never reached it, and the gauge saw roughly 127 of a Saturday's
        283 requests. Both the cache's widening valve and the 50-request reserve that
        protects the pick path read that gauge, so the reserve Batch 114 built was
        reserving against a number that missed half the spend.

        Charged in ``finally`` because a call that raised still sent its requests; a
        ``429`` in particular is the moment the count matters most.
        """
        before = self._inner_requests()
        try:
            yield
        finally:
            after = self._inner_requests()
            spent = (after - before) if (before is not None and after is not None) else estimate
            self._charge_requests(self._clock(), max(spent, 0))

    def _refuse_upstream(self, now: float, *, for_pick: bool) -> OddsProviderError | None:
        """Why this call must not go upstream, or ``None`` if it may.

        Two reasons, and they bind differently on purpose. A ``429`` cooldown holds
        everybody, because the budget is gone and the pick path cannot conjure one — it is
        told so without spending another request on the same answer. The pick reserve
        holds *browsing* only: it exists precisely so the action with a deadline still has
        an allowance when a card someone left open has spent the rest of the hour.
        """
        if self._rate_limited_until is not None and now < self._rate_limited_until:
            return OddsProviderRateLimited(
                f"odds provider rate-limited, holding off for "
                f"{self._rate_limited_until - now:.0f}s"
            )
        if for_pick or not self._reserve or not self._hour_limit:
            return None
        if self.budget().hour_remaining <= self._reserve:
            log.info(
                "browse withheld to protect the pick reserve",
                reserve=self._reserve,
                hour_remaining=self.budget().hour_remaining,
            )
            return OddsProviderError("hourly allowance held for the pick path")
        return None

    def invalidate(self) -> None:
        """Drop every cached entry — used when a session is re-established.

        The spend counters and the cooldown deliberately survive: the plan does not
        forget what this process spent just because the session was rebuilt, and a
        re-login inside a ``429`` cooldown must not become a way to keep asking.
        """
        self._entries.clear()
