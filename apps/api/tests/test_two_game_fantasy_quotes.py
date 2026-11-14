"""New-format provenance and refresh-owner-only acquisition over counted HTTP."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from src.config import OddsProviderName, settings
from src.models.two_game import ProviderAttempt, ProviderSnapshot
from src.services.betfair import Betfair, FakeBetfair
from src.services.odds_api import OddsApiProvider
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import OddsProviderAPIError, OddsProviderBadRequest
from src.services.two_game_provider import (
    ProviderIdentity,
    acquire_matching,
    configured_identity,
    native_identity,
)
from src.services.two_game_quotes import QuoteSnapshots, SharedQuotes
from tests.test_two_game_quotes import Source, event


@pytest.mark.parametrize(
    ("name", "source", "bookmaker"),
    [
        (OddsProviderName.oddsapi, "oddsapi", "Synthetic Bookmaker"),
        (OddsProviderName.betfair, "betfair", "Betfair Exchange"),
        (OddsProviderName.fake, "fake", "Fake"),
    ],
)
def test_configured_identity_needs_no_client(name, source, bookmaker, monkeypatch):
    monkeypatch.setattr(settings, "odds_provider", name)
    monkeypatch.setattr(settings, "odds_api_bookmaker", "Synthetic Bookmaker")
    assert configured_identity() == ProviderIdentity(source, bookmaker)


@pytest.mark.asyncio
async def test_native_identity_uses_actual_clients_through_nested_legacy_caches():
    def forbidden(request):
        raise AssertionError("Identity resolution made an HTTP request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        odds = OddsApiProvider("synthetic-key", bookmaker="Actual Source", client=http)
        betfair = Betfair(
            "synthetic", "synthetic", "synthetic", identity_client=http, betting_client=http
        )
        assert native_identity(
            CachingOddsProvider(CachingOddsProvider(odds, ttl_seconds=60), ttl_seconds=60)
        ) == ProviderIdentity("oddsapi", "Actual Source")
        assert native_identity(betfair) == ProviderIdentity("betfair", "Betfair Exchange")
        assert native_identity(FakeBetfair()) == ProviderIdentity("fake", "Fake")
        with pytest.raises(OddsProviderAPIError):
            native_identity(object())


@pytest.mark.asyncio
async def test_production_acquisition_refuses_mismatched_identity(monkeypatch):
    from src.services.odds_session import odds_session

    calls = []

    async def acquire():
        calls.append(True)
        return FakeBetfair()

    monkeypatch.setattr(odds_session, "acquire", acquire)
    with pytest.raises(OddsProviderAPIError, match="provenance"):
        await acquire_matching(ProviderIdentity("betfair", "Betfair Exchange"))
    assert len(calls) == 1
    assert native_identity(
        await acquire_matching(ProviderIdentity("fake", "Fake"))
    ) == ProviderIdentity("fake", "Fake")


@pytest.mark.asyncio
async def test_lazy_acquire_is_zero_on_fresh_restarted_and_readonly_cache(db_engine):
    source = Source(db_engine)
    acquired = []

    async def acquire():
        acquired.append(True)
        return source.client

    def restarted():
        return SharedQuotes(
            source.sessions,
            acquire=acquire,
            source=source.source,
            bookmaker="Bet365",
            clock=source.clock,
        )

    key = event()
    try:
        first = await restarted().get_fresh(key)
        assert first.odds is not None
        reader = QuoteSnapshots(
            source.sessions, source=source.source, bookmaker="Bet365", clock=source.clock
        )
        async with source.sessions() as db, db.begin():
            # Same connection works even when the caller owns a transaction.
            assert (await reader.peek_many([key], db=db))[key].odds == first.odds
        assert (await restarted().get_fresh(key)).odds == first.odds
        assert len(acquired) == len(source.calls) == 1
        source.clock.now += timedelta(seconds=60, microseconds=1)
        await restarted().get_fresh(key)
        assert len(acquired) == len(source.calls) == 2
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_lazy_cold_coalescing_acquires_only_refresh_owner(db_engine):
    source = Source(db_engine)
    source.block_first = True
    acquired = []

    async def acquire():
        acquired.append(True)
        return source.client

    def cache():
        return SharedQuotes(
            source.sessions,
            acquire=acquire,
            source=source.source,
            bookmaker="Bet365",
            clock=source.clock,
        )

    key = event()
    first = asyncio.create_task(cache().get_fresh(key))
    second = None
    try:
        await asyncio.wait_for(source.entered.wait(), 5)
        second = asyncio.create_task(cache().get_fresh(key))
        await asyncio.sleep(0.1)
        source.release.set()
        a, b = await asyncio.gather(first, second)
        assert a.odds == b.odds
        assert len(acquired) == len(source.calls) == 1
    finally:
        source.release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
        await source.close()


@pytest.mark.asyncio
async def test_lazy_acquire_rejection_is_not_a_fixture_negative_and_releases_lease(db_engine):
    source = Source(db_engine)
    key = event()

    async def bad_login():
        raise OddsProviderBadRequest("synthetic login rejection")

    cache = SharedQuotes(
        source.sessions,
        acquire=bad_login,
        source=source.source,
        bookmaker="Bet365",
        clock=source.clock,
    )
    try:
        with pytest.raises(OddsProviderAPIError, match="acquisition"):
            await cache.get_fresh(key)
        async with source.sessions() as db:
            row = await db.get(ProviderSnapshot, cache.key(key))
            assert row.lease_token is row.negative_recheck_at is None
            assert row.payload["state"] == "pending"
        assert source.calls == []
        assert (await source.cache().get_fresh(key)).odds is not None
        assert len(source.calls) == 1
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_slow_acquire_holds_no_snapshot_lock_and_lost_lease_buys_no_price(db_engine):
    source = Source(db_engine)
    key = event()
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_acquire():
        entered.set()
        await release.wait()
        return source.client

    cache = SharedQuotes(
        source.sessions,
        acquire=slow_acquire,
        source=source.source,
        bookmaker="Bet365",
        clock=source.clock,
    )
    task = asyncio.create_task(cache.get_fresh(key))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        async with source.sessions() as db, db.begin():
            row = await asyncio.wait_for(
                db.scalar(
                    select(ProviderSnapshot)
                    .where(ProviderSnapshot.key == cache.key(key))
                    .with_for_update()
                ),
                2,
            )
            assert row.lease_token is not None
        source.clock.now += timedelta(seconds=46)
        newer = await source.cache().get_fresh(key)
        release.set()
        old_caller = await task
        assert old_caller.odds == newer.odds
        assert len(source.calls) == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await source.close()


@pytest.mark.asyncio
async def test_lazy_negative_cache_hit_does_not_acquire_again(db_engine):
    source = Source(db_engine)
    source.priced = False
    acquired = []

    async def acquire():
        acquired.append(True)
        return source.client

    cache = SharedQuotes(
        source.sessions,
        acquire=acquire,
        source=source.source,
        bookmaker="Bet365",
        clock=source.clock,
    )
    try:
        key = event()
        for _ in range(2):
            with pytest.raises(OddsProviderAPIError):
                await cache.get_fresh(key)
        assert len(acquired) == len(source.calls) == 1
    finally:
        await source.close()


@pytest.mark.asyncio
async def test_malformed_actual_provider_price_refuses_without_fixture_negative(db_engine):
    source = Source(db_engine)
    source.price = "NaN"
    key = event()
    cache = source.cache()
    try:
        with pytest.raises(OddsProviderAPIError):
            await cache.get_fresh(key)
        assert len(source.calls) == 1
        async with source.sessions() as db:
            row = await db.get(ProviderSnapshot, cache.key(key))
            assert row.lease_token is row.negative_recheck_at is None
    finally:
        await source.close()


@pytest.mark.parametrize("shape", ["json", "schema"])
@pytest.mark.asyncio
async def test_malformed_betfair_identity_http_is_not_a_fixture_negative(db_engine, shape):
    source = Source(db_engine)
    calls = []

    def dispatch(request):
        calls.append(request.url.path)
        return (
            httpx.Response(200, content=b"not-json")
            if shape == "json"
            else httpx.Response(200, json={"status": []})
        )

    http = httpx.AsyncClient(
        base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
    )
    provider = Betfair(
        "synthetic",
        "synthetic",
        "synthetic",
        identity_client=http,
        betting_client=http,
        budget=source.budget,
    )

    async def acquire():
        await provider.login()
        return provider

    quotes = SharedQuotes(
        source.sessions,
        acquire=acquire,
        source="betfair",
        bookmaker="Betfair Exchange",
        clock=source.clock,
    )
    key = event()
    try:
        with pytest.raises(OddsProviderAPIError):
            await quotes.get_fresh(key)
        assert calls == ["/api/login"]
        async with source.sessions() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(ProviderAttempt)
                .where(ProviderAttempt.meter == source.budget.meter)
            )
            row = await db.get(ProviderSnapshot, quotes.key(key))
            assert count == 1
            assert row.payload["state"] == "pending"
            assert row.lease_token is row.negative_recheck_at is None
    finally:
        await provider.close()
        await source.close()


@pytest.mark.asyncio
async def test_cancelled_actual_login_retains_spend_and_restarted_owner_does_not_acquire(db_engine):
    source = Source(db_engine)
    calls = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def dispatch(request):
        calls.append(request.url.path)
        entered.set()
        await release.wait()
        return httpx.Response(
            200, json={"loginStatus": "SUCCESS", "sessionToken": "synthetic-session"}
        )

    http = httpx.AsyncClient(
        base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
    )
    provider = Betfair(
        "synthetic",
        "synthetic",
        "synthetic",
        identity_client=http,
        betting_client=http,
        budget=source.budget,
    )

    async def acquire():
        await provider.login()
        return provider

    def restarted():
        return SharedQuotes(
            source.sessions,
            acquire=acquire,
            source="betfair",
            bookmaker="Betfair Exchange",
            clock=source.clock,
        )

    key = event()
    quotes = restarted()
    task = asyncio.create_task(quotes.get_fresh(key))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        async with source.sessions() as db, db.begin():
            row = await asyncio.wait_for(
                db.scalar(
                    select(ProviderSnapshot)
                    .where(ProviderSnapshot.key == quotes.key(key))
                    .with_for_update()
                ),
                2,
            )
            assert row.lease_token is not None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(OddsProviderAPIError):
            await restarted().get_fresh(key)
        assert calls == ["/api/login"]
        async with source.sessions() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(ProviderAttempt)
                .where(ProviderAttempt.meter == source.budget.meter)
            )
            row = await db.get(ProviderSnapshot, quotes.key(key))
            assert count == 1 and row.lease_token is not None
            assert row.negative_recheck_at is None
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await provider.close()
        await source.close()


@pytest.mark.asyncio
async def test_scheduler_factory_uses_native_exchange_identity_and_rejects_wrong_client(
    monkeypatch,
):
    from src import scheduler
    from src.services.odds_session import odds_session

    monkeypatch.setattr(settings, "odds_provider", OddsProviderName.betfair)
    monkeypatch.setattr(settings, "odds_api_bookmaker", "Bet365")

    async def acquire():
        return FakeBetfair()

    monkeypatch.setattr(odds_session, "acquire", acquire)
    worker = scheduler._two_game_discovery_worker()
    assert (worker.source, worker.bookmaker) == ("betfair", "Betfair Exchange")
    with pytest.raises(OddsProviderAPIError, match="provenance"):
        await worker.acquire()
