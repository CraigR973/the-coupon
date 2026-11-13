"""Shared quote freshness, transport accounting and lease-owner failure oracles."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.models.two_game import ProviderSnapshot
from src.services.odds_api import OddsApiProvider
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    FixtureOdds,
    Market,
    OddsProviderAPIError,
    OddsProviderError,
    Outcome,
)
from src.services.provider_budget import BudgetPolicy, ProviderBudget, ProviderBudgetRefused
from src.services.two_game_quotes import SharedQuotes


@dataclass
class Clock:
    now: datetime = datetime(2026, 11, 20, 11)

    def __call__(self) -> datetime:
        return self.now


class Source:
    def __init__(self, db_engine, *, hourly: int = 90) -> None:
        self.clock = Clock()
        self.calls: list[list[str]] = []
        self.price = "2.15"
        self.priced = True
        self.send_unpriced_rows = False
        self.status = 200
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.block_first = False
        self.sessions = async_sessionmaker(db_engine, expire_on_commit=False)
        self.budget = ProviderBudget(
            self.sessions,
            meter=f"quotes-{uuid.uuid4().hex}",
            policy=BudgetPolicy(hourly=hourly),
            clock=self.clock,
        )
        self.client = OddsApiProvider(
            "synthetic-not-an-account-key",
            budget=self.budget,
            client=httpx.AsyncClient(
                base_url="https://synthetic.invalid", transport=httpx.MockTransport(self.dispatch)
            ),
        )
        self.source = f"test-{uuid.uuid4().hex[:12]}"

    async def dispatch(self, request: httpx.Request) -> httpx.Response:
        ids = (request.url.params.get("eventIds") or request.url.params.get("eventId") or "").split(
            ","
        )
        self.calls.append(ids)
        price = self.price
        if self.block_first and len(self.calls) == 1:
            self.entered.set()
            await self.release.wait()
        payload = [
            {
                "id": event,
                "home": "Home",
                "away": "Away",
                "bookmakers": {
                    "Bet365": [
                        {"name": "ML", "odds": [{"home": price, "draw": "3.10", "away": "4.00"}]}
                    ]
                }
                if self.priced
                else {},
            }
            for event in ids
        ]
        if not self.priced and not self.send_unpriced_rows:
            payload = []
        return httpx.Response(
            self.status, json=payload if self.status == 200 else {"error": "synthetic"}
        )

    def cache(self, provider=None) -> SharedQuotes:
        return SharedQuotes(
            self.sessions,
            provider or self.client,
            source=self.source,
            bookmaker="Bet365",
            clock=self.clock,
        )

    async def close(self) -> None:
        self.release.set()
        await self.client.close()


def event() -> str:
    return f"synthetic-{uuid.uuid4().hex}"


def home_price(odds: FixtureOdds) -> Decimal:
    # Selection order is not the port contract; address the intended market/outcome.
    return next(
        selection.price
        for selection in odds.selections
        if selection.market == Market.MATCH_ODDS and selection.outcome == Outcome.HOME
    )


@pytest.mark.asyncio
async def test_q8_concurrent_members_share_one_committed_fresh_quote(db_engine) -> None:
    source = Source(db_engine)
    source.block_first = True
    caches = [source.cache() for _ in range(4)]
    target = event()
    first = asyncio.create_task(caches[0].get_fresh(target))
    try:
        await asyncio.wait_for(source.entered.wait(), 3)
        rest = [asyncio.create_task(cache.get_fresh(target)) for cache in caches[1:]]
        await asyncio.sleep(0.05)
        source.release.set()
        views = await asyncio.gather(first, *rest)
        assert len(source.calls) == (await source.budget.view()).spent_hour == 1
        assert all(v.odds is not None and home_price(v.odds) == Decimal("2.15") for v in views)
        assert len({v.observed_at for v in views}) == 1
    finally:
        source.release.set()
        await first
        await source.close()


@pytest.mark.asyncio
async def test_restart_reuses_positive_through_60_seconds_and_refetches_after(db_engine) -> None:
    source = Source(db_engine)
    target = event()
    try:
        first = await source.cache().get_fresh(target)
        source.clock.now += timedelta(seconds=60)
        assert (await source.cache().get_fresh(target)).observed_at == first.observed_at
        assert len(source.calls) == 1
        source.clock.now += timedelta(microseconds=1)
        source.price = "3.25"
        changed = await source.cache().get_fresh(target)
        assert changed.odds is not None and home_price(changed.odds) == Decimal("3.25")
        assert len(source.calls) == 2 and changed.observed_at > first.observed_at
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_browse_age_is_read_only_and_exhaustion_cannot_freeze_stale_positive(
    db_engine,
) -> None:
    source = Source(db_engine, hourly=1)
    target = event()
    cache = source.cache()
    try:
        assert (await cache.peek_many([target]))[target].availability == "pending"
        assert source.calls == []
        old = await cache.get_fresh(target)
        source.clock.now += timedelta(seconds=61)
        browse = (await cache.peek_many([target]))[target]
        assert browse.age_seconds == 61 and browse.odds == old.odds
        with pytest.raises(ProviderBudgetRefused):
            await cache.get_fresh(target)
        assert len(source.calls) == 1
        kept = (await cache.peek_many([target]))[target]
        assert kept.observed_at == old.observed_at and kept.odds == old.odds
        assert kept.degraded
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_new_negative_recheck_does_not_change_the_legacy_six_hour_negative_cache(
    db_engine,
) -> None:
    source = Source(db_engine)
    source.priced = False
    target = event()
    legacy = CachingOddsProvider(
        source.client,
        ttl_seconds=300,
        unpriced_ttl_seconds=6 * 3600,
        clock=lambda: source.clock.now.timestamp(),
    )
    cache = source.cache(legacy)
    try:
        assert await legacy.fetch_odds([target]) == []
        with pytest.raises(OddsProviderAPIError):
            await cache.get_fresh(target)
        assert len(source.calls) == 2
        source.priced = True
        source.clock.now += timedelta(seconds=299)
        with pytest.raises(OddsProviderAPIError):
            await source.cache().get_fresh(target)
        assert len(source.calls) == 2
        source.clock.now += timedelta(seconds=1)
        assert (await source.cache().get_fresh(target)).odds is not None
        assert len(source.calls) == 3
        assert await legacy.fetch_odds([target]) == []
        assert len(source.calls) == 3
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_one_ten_fixture_chunk_is_one_actual_request_and_browse_never_refills(
    db_engine,
) -> None:
    source = Source(db_engine)
    targets = [event() for _ in range(10)]
    cache = source.cache()
    try:
        views = await cache.refresh_many(targets)
        assert len(views) == 10 and all(v.odds is not None for v in views.values())
        assert len(source.calls) == 1 and len(source.calls[0]) == 10
        assert (await source.budget.view()).spent_hour == 1
        assert len(await cache.peek_many(targets)) == 10 and len(source.calls) == 1
        with pytest.raises(ValueError):
            await cache.refresh_many([*targets, event()])
        assert len(source.calls) == 1
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_expired_owner_response_cannot_overwrite_the_new_owner_or_return_old_price(
    db_engine,
) -> None:
    source = Source(db_engine)
    source.block_first = True
    target = event()
    old = asyncio.create_task(source.cache().get_fresh(target))
    try:
        await asyncio.wait_for(source.entered.wait(), 3)
        source.clock.now += timedelta(seconds=46)
        source.price = "3.30"
        newer = await source.cache().get_fresh(target)
        source.release.set()
        old_response = await old
        for view in (newer, old_response, (await source.cache().peek_many([target]))[target]):
            assert view.odds is not None and home_price(view.odds) == Decimal("3.30")
        assert len(source.calls) == (await source.budget.view()).spent_hour == 2
    finally:
        source.release.set()
        await old
        await source.close()


@pytest.mark.asyncio
async def test_cancelled_owner_leaves_spend_and_lease_until_restart_expiry(db_engine) -> None:
    source = Source(db_engine)
    source.block_first = True
    target = event()
    cache = source.cache()
    pending = asyncio.create_task(cache.get_fresh(target))
    try:
        await asyncio.wait_for(source.entered.wait(), 3)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        async with source.sessions() as db:
            row = await db.get(ProviderSnapshot, cache.key(target))
            assert row is not None and row.lease_token is not None
        claimed, _, _ = await source.cache()._claim([target], force=False, opening_at=None)
        assert claimed == {} and len(source.calls) == 1
        assert (await source.budget.view()).spent_hour == 1
        source.clock.now += timedelta(seconds=46)
        assert (await source.cache().get_fresh(target)).odds is not None
        assert len(source.calls) == (await source.budget.view()).spent_hour == 2
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_failed_refresh_retains_previous_observation_but_never_returns_it_for_a_pick(
    db_engine,
) -> None:
    source = Source(db_engine)
    target = event()
    cache = source.cache()
    try:
        before = await cache.get_fresh(target)
        source.clock.now += timedelta(seconds=61)
        source.status = 403
        with pytest.raises(OddsProviderError):
            await cache.get_fresh(target)
        kept = (await cache.peek_many([target]))[target]
        assert kept.odds == before.odds and kept.observed_at == before.observed_at
        assert kept.age_seconds == 61 and kept.degraded
        assert len(source.calls) == (await source.budget.view()).spent_hour == 2
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_source_and_bookmaker_identity_cannot_alias_through_colons(db_engine) -> None:
    source = Source(db_engine)
    try:
        first = SharedQuotes(source.sessions, source.client, source="fake", bookmaker="A:B")
        second = SharedQuotes(source.sessions, source.client, source="fake", bookmaker="A")
        assert first.key("C") != second.key("B:C")
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_unpriced_fixture_shaped_response_is_a_durable_negative_too(db_engine) -> None:
    source = Source(db_engine)
    source.priced = False
    source.send_unpriced_rows = True
    target = event()
    cache = source.cache()
    try:
        with pytest.raises(OddsProviderAPIError):
            await cache.get_fresh(target)
        view = (await cache.peek_many([target]))[target]
        assert view.availability == "unavailable" and view.odds is None
        assert view.age_seconds == 0 and view.observed_at == source.clock.now
        with pytest.raises(OddsProviderAPIError):
            await source.cache().get_fresh(target)
        assert len(source.calls) == (await source.budget.view()).spent_hour == 1
    finally:
        await source.close()
