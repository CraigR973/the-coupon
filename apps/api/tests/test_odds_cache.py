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

from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    SATURDAY_THREE_PM,
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
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
