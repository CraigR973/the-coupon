"""The request-path odds cache — the thing that keeps the pick page inside the quota.

``fetch_odds`` runs on every pick-page load and every pick submission, while odds-api.io's
free plan allows 100 requests/hour and 500/day. These tests pin the property that makes
that survivable: upstream traffic is a function of *time*, not of how many members are
looking.

The clock is injected, so nothing here sleeps.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    SATURDAY_THREE_PM,
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderError,
    OddsProviderRateLimited,
    Outcome,
    Selection,
    Slate,
    SlateFixture,
    SlateWindow,
)


def _odds(event_id: str, price: str = "2.00") -> FixtureOdds:
    return FixtureOdds(
        provider_event_id=event_id,
        home="Airdrieonians",
        away="East Kilbride",
        selections=[
            Selection(
                market=Market.MATCH_ODDS,
                outcome=Outcome.HOME,
                runner_name="Airdrieonians",
                price=Decimal(price),
            )
        ],
    )


class _CountingProvider(OddsProvider):
    """Records every upstream call and which events each one asked for."""

    def __init__(self, *, priced: set[str] | None = None) -> None:
        self.odds_calls: list[list[str]] = []
        self.slate_calls = 0
        #: One entry per slate call — the narrowing it was given, or ``None`` for all UK.
        self.slate_competition_ids: list[list[str] | None] = []
        self.settle_calls = 0
        self.competition_calls = 0
        self.login_calls = 0
        self.closed = False
        self.priced = priced
        self.price = "2.00"
        #: When set, every ``fetch_odds`` raises it — the provider having a bad afternoon.
        self.odds_error: Exception | None = None

    async def login(self) -> str:
        self.login_calls += 1
        return "token"

    async def keep_alive(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        self.slate_calls += 1
        self.slate_competition_ids.append(
            None if competition_ids is None else sorted(competition_ids)
        )
        return Slate(
            starts_on=starts_on,
            fixtures=[
                SlateFixture(
                    provider_event_id="a",
                    home="Airdrieonians",
                    away="East Kilbride",
                    kickoff_utc=datetime(2026, 8, 8, 14, 0, tzinfo=UTC),
                    competition="Scotland - League One",
                    competition_id="scotland-league-one",
                )
            ],
        )

    async def fetch_competitions(self) -> list[Competition]:
        self.competition_calls += 1
        return [
            Competition(competition_id="scotland-league-one", competition="Scotland - League One")
        ]

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        self.odds_calls.append(list(event_ids))
        if self.odds_error is not None:
            raise self.odds_error
        return [_odds(e, self.price) for e in event_ids if self.priced is None or e in self.priced]

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        self.settle_calls += 1
        return [
            EventSettlement(provider_event_id=e, status="finished", settled=True) for e in event_ids
        ]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cache(inner: OddsProvider, clock: _Clock, ttl: float = 300.0) -> CachingOddsProvider:
    return CachingOddsProvider(inner, ttl_seconds=ttl, clock=clock)


# ── The rate-limit property ────────────────────────────────────────────────────


async def test_repeated_pick_page_loads_issue_one_upstream_call() -> None:
    """Fifteen members refreshing the slate must not become fifteen upstream calls."""
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())
    slate = [f"evt-{n}" for n in range(40)]

    for _ in range(15):
        odds = await cache.fetch_odds(slate)
        assert len(odds) == 40

    assert len(inner.odds_calls) == 1
    assert inner.odds_calls[0] == slate


async def test_pick_submission_is_served_from_the_slate_batch() -> None:
    """A submission asks for one event; the page load already paid for it."""
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    await cache.fetch_odds(["a", "b", "c"])  # pick page
    [single] = await cache.fetch_odds(["b"])  # submission

    assert single.provider_event_id == "b"
    assert len(inner.odds_calls) == 1


async def test_concurrent_cold_loads_collapse_into_one_call() -> None:
    """Fifteen simultaneous loads of a cold cache must not stampede the provider."""
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    results = await asyncio.gather(*(cache.fetch_odds(["a", "b"]) for _ in range(15)))

    assert all(len(r) == 2 for r in results)
    assert len(inner.odds_calls) == 1


async def test_unpriced_event_is_not_re_requested() -> None:
    """An unpriced fixture would otherwise cost a request on every single page load."""
    inner = _CountingProvider(priced={"a"})
    cache = _cache(inner, _Clock())

    first = await cache.fetch_odds(["a", "b"])
    second = await cache.fetch_odds(["a", "b"])

    assert [o.provider_event_id for o in first] == ["a"]
    assert [o.provider_event_id for o in second] == ["a"]
    assert len(inner.odds_calls) == 1


# ── Freshness ──────────────────────────────────────────────────────────────────


async def test_entries_refresh_after_the_ttl() -> None:
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])
    clock.advance(299)
    await cache.fetch_odds(["a"])
    assert len(inner.odds_calls) == 1

    clock.advance(2)  # now past the TTL
    inner.price = "3.50"
    [refreshed] = await cache.fetch_odds(["a"])

    assert len(inner.odds_calls) == 2
    assert refreshed.selections[0].price == Decimal("3.50")


async def test_only_stale_events_are_re_fetched() -> None:
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])
    clock.advance(200)
    await cache.fetch_odds(["a", "b"])  # only "b" is cold
    assert inner.odds_calls[1] == ["b"]

    clock.advance(150)  # "a" is now stale, "b" is not
    await cache.fetch_odds(["a", "b"])
    assert inner.odds_calls[2] == ["a"]


async def test_results_are_ordered_and_deduplicated() -> None:
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    odds = await cache.fetch_odds(["c", "a", "b", "a"])

    assert [o.provider_event_id for o in odds] == ["a", "b", "c"]
    assert inner.odds_calls[0] == ["c", "a", "b"]  # de-duplicated upstream


async def test_empty_request_touches_nothing() -> None:
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())
    assert await cache.fetch_odds([]) == []
    assert inner.odds_calls == []


# ── Everything else passes straight through ────────────────────────────────────


async def test_slate_and_settlement_are_not_cached() -> None:
    """Both are scheduler-driven and must see fresh data on every run."""
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    await cache.fetch_slate(SATURDAY_THREE_PM, date(2026, 8, 8))
    await cache.fetch_slate(SATURDAY_THREE_PM, date(2026, 8, 8))
    await cache.settle(["a"])
    await cache.settle(["a"])

    assert inner.slate_calls == 2
    assert inner.settle_calls == 2


async def test_the_competition_catalogue_is_delegated_uncached() -> None:
    """The decorator must not swallow the catalogue — the picker reads it through here.

    Uncached on purpose: ``OddsApiProvider`` already memoises ``/leagues`` on the client,
    so a TTL here would only add an expiry that one does not have.
    """
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    first = await cache.fetch_competitions()
    await cache.fetch_competitions()

    assert [c.competition_id for c in first] == ["scotland-league-one"]
    assert inner.competition_calls == 2


async def test_lifecycle_is_delegated_and_close_drops_the_cache() -> None:
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    assert await cache.login() == "token"
    await cache.fetch_odds(["a"])
    await cache.close()

    assert inner.closed is True
    assert cache.inner is inner

    inner.closed = False
    await cache.fetch_odds(["a"])
    assert len(inner.odds_calls) == 2  # cache was cleared on close


async def test_invalidate_forces_a_refetch() -> None:
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    await cache.fetch_odds(["a"])
    cache.invalidate()
    await cache.fetch_odds(["a"])

    assert len(inner.odds_calls) == 2


# ── Batch 11: the per-call freshness ceiling ──────────────────────────────────


async def test_max_age_tightens_the_ttl_for_one_call() -> None:
    """A caller that needs a fresher price than the TTL allows gets one."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=3600.0)

    await cache.fetch_odds(["a"])
    clock.advance(120)

    # Well inside the 3600s TTL, so a browse is still served from cache…
    await cache.fetch_odds(["a"])
    assert len(inner.odds_calls) == 1

    # …but a pick submission asking for a price no older than 60s pays for a refetch.
    await cache.fetch_odds(["a"], max_age_seconds=60)
    assert len(inner.odds_calls) == 2


async def test_max_age_never_loosens_the_ttl() -> None:
    """A caller cannot ask to be served something staler than the configured TTL."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])
    clock.advance(400)
    await cache.fetch_odds(["a"], max_age_seconds=86_400)
    assert len(inner.odds_calls) == 2, "the entry was past its TTL and had to be refetched"


async def test_a_fresh_entry_satisfies_a_tight_ceiling_without_refetching() -> None:
    """Freshness is a bound, not a command — an already-fresh price is reused."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=3600.0)

    await cache.fetch_odds(["a"], max_age_seconds=60)
    clock.advance(5)
    await cache.fetch_odds(["a"], max_age_seconds=60)
    assert len(inner.odds_calls) == 1


async def test_a_tight_ceiling_refetches_only_the_events_asked_for() -> None:
    """Freezing one pick must not sweep the whole card — that is the budget."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=3600.0)

    slate = [f"e{i}" for i in range(20)]
    await cache.fetch_odds(slate)
    clock.advance(120)
    await cache.fetch_odds(["e7"], max_age_seconds=60)

    assert inner.odds_calls[-1] == ["e7"]
    assert len(inner.odds_calls) == 2


# ── Batch 48: surviving a provider that refuses ───────────────────────────────
#
# The pick screen is the one every member opens, and until this batch its availability
# was wired straight to odds-api.io's rate limit: a `429` propagated out of `fetch_odds`
# and `GET /leagues/{slug}/gameweek/current` answered `500`. The entries are still here
# when a refresh fails — merely past their TTL — which is what makes the fallback free.


async def test_a_failed_refresh_serves_the_last_known_prices() -> None:
    """The whole fix: stale prices beat a broken screen."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a", "b"])  # warm
    clock.advance(400)  # both entries are now stale
    inner.odds_error = OddsProviderAPIError("odds-api.io /odds/multi rate-limited (429)")

    snapshot = await cache.fetch_odds_best_effort(["a", "b"])

    assert [o.provider_event_id for o in snapshot.odds] == ["a", "b"]
    assert snapshot.degraded is True
    assert len(inner.odds_calls) == 2, "it did try, and fell back when the try failed"


async def test_a_failed_refresh_with_a_cold_cache_serves_nothing_rather_than_raising() -> None:
    """No prices at all still renders the fixtures, which beats an error page."""
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())
    inner.odds_error = OddsProviderAPIError("upstream unreachable")

    snapshot = await cache.fetch_odds_best_effort(["a", "b"])

    assert snapshot.odds == []
    assert snapshot.degraded is True


async def test_a_failed_refresh_still_serves_the_entries_it_does_have() -> None:
    """A half-warm cache degrades by the fixture, not by the card."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])  # only "a" was ever priced
    clock.advance(400)
    inner.odds_error = OddsProviderAPIError("upstream unreachable")

    snapshot = await cache.fetch_odds_best_effort(["a", "b"])

    assert [o.provider_event_id for o in snapshot.odds] == ["a"]
    assert snapshot.degraded is True


async def test_a_healthy_refresh_is_never_reported_as_degraded() -> None:
    inner = _CountingProvider()
    cache = _cache(inner, _Clock())

    snapshot = await cache.fetch_odds_best_effort(["a"])

    assert [o.provider_event_id for o in snapshot.odds] == ["a"]
    assert snapshot.degraded is False


async def test_a_cache_hit_needs_no_provider_at_all_to_stay_healthy() -> None:
    """Inside the TTL nothing goes upstream, so a broken provider is invisible."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])
    inner.odds_error = OddsProviderAPIError("upstream unreachable")
    clock.advance(10)

    snapshot = await cache.fetch_odds_best_effort(["a"])

    assert [o.provider_event_id for o in snapshot.odds] == ["a"]
    assert snapshot.degraded is False
    assert len(inner.odds_calls) == 1


async def test_a_recovered_provider_is_served_on_the_next_load() -> None:
    """A failed refresh must not restamp the entries, or recovery would wait a TTL."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])
    clock.advance(400)
    inner.odds_error = OddsProviderAPIError("upstream unreachable")
    assert (await cache.fetch_odds_best_effort(["a"])).degraded is True

    inner.odds_error = None
    inner.price = "4.00"
    snapshot = await cache.fetch_odds_best_effort(["a"])  # same instant, no TTL wait

    assert snapshot.degraded is False
    assert snapshot.odds[0].selections[0].price == Decimal("4.00")


async def test_the_pick_path_still_raises() -> None:
    """`fetch_odds` is what freezes a scored price; it must keep failing loudly."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a"])  # a warm, and now stale, entry to be tempted by
    clock.advance(400)
    inner.odds_error = OddsProviderAPIError("upstream unreachable")

    with pytest.raises(OddsProviderAPIError):
        await cache.fetch_odds(["a"])


async def test_an_uncached_provider_degrades_to_no_prices() -> None:
    """The port's own fallback, for any provider with nothing to fall back to."""
    inner = _CountingProvider()
    inner.odds_error = OddsProviderAPIError("upstream unreachable")

    snapshot = await inner.fetch_odds_best_effort(["a"])

    assert snapshot.odds == []
    assert snapshot.degraded is True


# ── Batch 114: what the absence of a price costs ──────────────────────────────
#
# The launch budget was sized on 131 fixtures the bookmaker *prices*. On 2026-09-05 an
# open round held 202, of which Bet365 priced none of the 103 FA Cup qualifying ties. They
# cost 11 requests of every 21-request sweep, and the hourly allowance was gone by 08:06 on
# a match morning with a lock five hours away.


def _budgeted(
    inner: OddsProvider,
    clock: _Clock,
    *,
    ttl: float = 300.0,
    unpriced_ttl: float | None = None,
    cooldown: float = 0.0,
    hourly: int | None = None,
    daily: int | None = None,
    reserve: int = 0,
) -> CachingOddsProvider:
    """A cache with Batch 114's knobs, defaulting to the pre-batch behaviour."""
    return CachingOddsProvider(
        inner,
        ttl_seconds=ttl,
        unpriced_ttl_seconds=unpriced_ttl,
        rate_limited_cooldown_seconds=cooldown,
        hourly_request_limit=hourly,
        daily_request_limit=daily,
        pick_reserve_requests=reserve,
        clock=clock,
    )


async def test_an_unpriced_event_is_re_asked_once_per_negative_ceiling() -> None:
    """Not once per sweep, which is what spent the plan on the answer *no*."""
    inner = _CountingProvider(priced={"a"})
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, unpriced_ttl=21600.0)

    # Six hours of sweeps at the 300s ceiling: 72 of them.
    for _ in range(72):
        await cache.fetch_odds(["a", "b"])
        clock.advance(300)

    priced_asks = sum(1 for call in inner.odds_calls if "a" in call)
    unpriced_asks = sum(1 for call in inner.odds_calls if "b" in call)
    assert priced_asks == 72, "the priced event keeps its own ceiling"
    assert unpriced_asks == 1, f"the unpriced one was re-asked {unpriced_asks} times in six hours"


async def test_the_negative_ceiling_still_expires() -> None:
    """A market a bookmaker opens late must still be found — the marker is not permanent."""
    inner = _CountingProvider(priced={"a"})
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, unpriced_ttl=21600.0)

    await cache.fetch_odds(["a", "b"])
    clock.advance(21600)
    inner.priced = {"a", "b"}
    result = await cache.fetch_odds(["a", "b"])

    assert [o.provider_event_id for o in result] == ["a", "b"]


async def test_a_tight_ceiling_cannot_shorten_the_negative_one() -> None:
    """The pick path asking again inside a minute cannot discover a market that is not there."""
    inner = _CountingProvider(priced={"a"})
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, unpriced_ttl=21600.0)

    await cache.fetch_odds(["a", "b"])
    clock.advance(60)
    await cache.fetch_odds(["b"], max_age_seconds=60.0)

    assert sum(1 for call in inner.odds_calls if "b" in call) == 1


async def test_the_unpriced_ceiling_defaults_to_the_ordinary_one() -> None:
    """A caller that passes nothing keeps exactly the behaviour that shipped before."""
    inner = _CountingProvider(priced={"a"})
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds(["a", "b"])
    clock.advance(300)
    await cache.fetch_odds(["a", "b"])

    assert sum(1 for call in inner.odds_calls if "b" in call) == 2


async def test_only_a_real_answer_counts_as_evidence() -> None:
    """`observed` is what lets the caller write the persistent marker, so it must be exact."""
    inner = _CountingProvider(priced={"a"})
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0)

    fresh = await cache.fetch_odds_best_effort(["a", "b"])
    assert fresh.observed == {"a", "b"}, "both got a definite answer, price or no price"

    cached = await cache.fetch_odds_best_effort(["a", "b"])
    assert cached.observed == frozenset(), "a cache hit is not new evidence"

    clock.advance(300)
    inner.odds_error = OddsProviderAPIError("upstream unreachable")
    failed = await cache.fetch_odds_best_effort(["a", "b"])
    assert failed.degraded is True
    assert failed.observed == frozenset(), "a failed sweep is not evidence of anything"


# ── A 429 must stop costing requests ──────────────────────────────────────────


async def test_ten_retries_after_a_rate_limit_cost_one_request() -> None:
    """`72204256` was refused twice inside one second, each tap a fresh call.

    The cooldown is the difference between a rate limit costing one request and costing one
    per attempt — against a budget that is, by the provider's own account, already gone.
    """
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, cooldown=300.0)
    inner.odds_error = OddsProviderRateLimited("429")

    for _ in range(10):
        await cache.fetch_odds_best_effort(["a"])
        clock.advance(1)

    assert len(inner.odds_calls) == 1, f"ten retries cost {len(inner.odds_calls)} upstream calls"


async def test_the_eleventh_after_the_cooldown_costs_one_more() -> None:
    """Held off, not given up on — the quota does roll over and the card must recover."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, cooldown=300.0)
    inner.odds_error = OddsProviderRateLimited("429")

    for _ in range(10):
        await cache.fetch_odds_best_effort(["a"])
        clock.advance(1)
    clock.advance(300)
    inner.odds_error = None
    recovered = await cache.fetch_odds_best_effort(["a"])

    assert len(inner.odds_calls) == 2
    assert [o.provider_event_id for o in recovered.odds] == ["a"]
    assert recovered.degraded is False


async def test_the_pick_path_is_refused_inside_the_cooldown_without_calling_upstream() -> None:
    """It still raises — a pick may not freeze a price it could not confirm — but for free."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, cooldown=300.0)
    inner.odds_error = OddsProviderRateLimited("429")

    with pytest.raises(OddsProviderError):
        await cache.fetch_odds(["a"])
    calls_after_the_first = len(inner.odds_calls)
    with pytest.raises(OddsProviderRateLimited):
        await cache.fetch_odds(["a"])

    assert len(inner.odds_calls) == calls_after_the_first


async def test_an_ordinary_failure_keeps_trying_on_the_next_load() -> None:
    """Batch 48's reason holds for a blip and not for a `429`, so the two stay apart."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, cooldown=300.0)
    inner.odds_error = OddsProviderAPIError("upstream unreachable")

    for _ in range(3):
        await cache.fetch_odds_best_effort(["a"])
        clock.advance(1)

    assert len(inner.odds_calls) == 3


# ── Counting the budget, reserving it, and bending before breaking ────────────


async def test_the_budget_counts_requests_rather_than_events() -> None:
    """The plan is denominated in requests, and the provider carries ten events in one."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, hourly=100, daily=500)

    await cache.fetch_odds([f"ev{i}" for i in range(25)])

    budget = cache.budget()
    assert budget.hour_used == 3, "25 events is three requests, not 25"
    assert budget.day_used == 3
    assert budget.hour_remaining == 97
    assert budget.day_remaining == 497


async def test_the_hourly_count_rolls_off_and_the_daily_one_does_not() -> None:
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=60.0, hourly=100, daily=500)

    await cache.fetch_odds(["a"])
    clock.advance(3601)

    budget = cache.budget()
    assert budget.hour_used == 0
    assert budget.day_used == 1


async def test_the_pick_reserve_holds_when_browsing_has_spent_the_hour() -> None:
    """Browsing has no deadline; freezing a price does. The floor is for the latter."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=1.0, hourly=10, daily=500, reserve=4)

    # Browse until the reserve binds. The TTL is a second, so every load goes upstream.
    for _ in range(20):
        await cache.fetch_odds_best_effort(["a"])
        clock.advance(2)
    spent_by_browsing = len(inner.odds_calls)
    assert cache.budget().hour_remaining <= 4, "the premise: browsing has run the hour down"

    await cache.fetch_odds(["a"], max_age_seconds=1.0)

    assert spent_by_browsing == 6, "browsing stops at the reserve rather than at the limit"
    assert len(inner.odds_calls) == spent_by_browsing + 1, "the pick path still gets through"


async def test_browsing_held_off_by_the_reserve_is_not_reported_as_degraded() -> None:
    """Rationing is not the source being unreachable, and the card must not say it is."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=1.0, hourly=10, daily=500, reserve=4)

    for _ in range(20):
        snapshot = await cache.fetch_odds_best_effort(["a"])
        clock.advance(2)

    assert snapshot.degraded is False
    assert [o.provider_event_id for o in snapshot.odds] == ["a"], "still served from cache"


async def test_the_browse_ceiling_widens_as_the_budget_falls() -> None:
    """Freshness should degrade along a slope the counters can explain, not stop at a cliff.

    Three bands, on the tighter of the two allowances: full rate above half the plan, then
    2x, then 4x. Refreshing at full rate into a wall is what turned a busy morning into a
    refusal — the card kept asking at the near tier until nothing was left for the picks.
    """
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, hourly=100, daily=500)

    await cache.fetch_odds_best_effort(["a"])
    clock.advance(301)
    await cache.fetch_odds_best_effort(["a"])
    assert len(inner.odds_calls) == 2, "at full budget a 301s-old entry is stale, as asked"

    # Past half the hour — 52 requests of 100 — so the ceiling doubles to 600s.
    await cache.fetch_odds([f"ev{i}" for i in range(500)])
    assert 0.25 <= cache.budget().hour_remaining / 100 < 0.5, "the premise of this band"
    calls = len(inner.odds_calls)
    clock.advance(400)
    await cache.fetch_odds_best_effort(["a"])
    assert len(inner.odds_calls) == calls, "400s is inside 2x, and 1x would have refreshed it"

    # Past three-quarters, and it doubles again to 1200s.
    await cache.fetch_odds([f"more{i}" for i in range(300)])
    assert cache.budget().hour_remaining / 100 < 0.25, "the premise of this band"
    calls = len(inner.odds_calls)
    clock.advance(400)
    await cache.fetch_odds_best_effort(["a"])
    assert len(inner.odds_calls) == calls, "the entry is 800s old and still inside 4x"


async def test_widening_is_off_when_no_limit_is_configured() -> None:
    """A test or an unmetered provider keeps exactly the pre-Batch-114 ceiling."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _cache(inner, clock, ttl=300.0)

    await cache.fetch_odds_best_effort(["a"])
    clock.advance(301)
    await cache.fetch_odds_best_effort(["a"])

    assert len(inner.odds_calls) == 2


async def test_the_pick_path_never_has_its_ceiling_widened() -> None:
    """It is the one action with a deadline; it gets the freshness it asked for."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, hourly=100, daily=500)

    await cache.fetch_odds([f"ev{i}" for i in range(800)])
    assert cache.budget().hour_remaining / 100 < 0.25, "the band where browsing would widen 4x"
    await cache.fetch_odds(["a"], max_age_seconds=60.0)
    calls = len(inner.odds_calls)
    clock.advance(61)
    await cache.fetch_odds(["a"], max_age_seconds=60.0)

    assert len(inner.odds_calls) == calls + 1


async def test_invalidate_does_not_forget_the_cooldown_or_the_spend() -> None:
    """A re-login must not become a way to keep asking a provider that said stop."""
    inner = _CountingProvider()
    clock = _Clock()
    cache = _budgeted(inner, clock, ttl=300.0, cooldown=300.0, hourly=100, daily=500)
    inner.odds_error = OddsProviderRateLimited("429")
    await cache.fetch_odds_best_effort(["a"])

    cache.invalidate()

    assert cache.budget().day_used == 1
    assert cache.budget().rate_limited_for == 300.0
    await cache.fetch_odds_best_effort(["a"])
    assert len(inner.odds_calls) == 1
