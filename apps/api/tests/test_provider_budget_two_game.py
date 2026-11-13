"""Actual fake HTTP dispatches against durable concurrent PostgreSQL admission."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.models.two_game import ProviderAttempt, ProviderRefusal, ProviderWork
from src.services.odds_api import OddsApiProvider
from src.services.provider_budget import (
    BudgetPolicy,
    ProviderBudget,
    ProviderBudgetRefused,
    provider_category,
)


@dataclass
class Clock:
    now: datetime = datetime(2026, 11, 20, 10)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def meter(db_engine, clock: Clock, **policy: int) -> ProviderBudget:
    return ProviderBudget(
        async_sessionmaker(db_engine, expire_on_commit=False),
        meter=f"test-{uuid.uuid4().hex}",
        policy=BudgetPolicy(**policy),
        clock=clock,
    )


def provider(budget: ProviderBudget, calls: list[str]) -> OddsApiProvider:
    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=[])

    return OddsApiProvider(
        "synthetic-not-an-account-key",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )


@pytest.mark.asyncio
async def test_q1_clock_hour_does_not_reset_actual_transport_allowance(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=4, daily=20)
    calls: list[str] = []
    client = provider(budget, calls)
    try:
        clock.now = datetime(2026, 11, 20, 9, 59, 59)
        for _ in range(2):
            await client._get("/events", {})
        clock.now = datetime(2026, 11, 20, 10, 0, 1)
        for _ in range(2):
            await client._get("/odds", {})
        with pytest.raises(ProviderBudgetRefused) as refused:
            await client._get("/events", {})
        assert len(calls) == client.requests_made == 4
        assert refused.value.retry_at == datetime(2026, 11, 20, 10, 59, 59)
        clock.now = refused.value.retry_at - timedelta(microseconds=1)
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/events", {})
        clock.now += timedelta(microseconds=1)
        await client._get("/events", {})
        view = await budget.view()
        assert (len(calls), view.spent_hour, view.spent_day) == (5, 3, 5)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_q2_midnight_does_not_reset_rolling_day(db_engine, clock: Clock) -> None:
    budget = meter(db_engine, clock, hourly=10, daily=3)
    calls: list[str] = []
    client = provider(budget, calls)
    try:
        clock.now = datetime(2026, 11, 20, 23, 59, 59)
        await client._get("/events", {})
        await client._get("/events", {})
        clock.now = datetime(2026, 11, 21, 0, 0, 1)
        await client._get("/events", {})
        with pytest.raises(ProviderBudgetRefused) as refused:
            await client._get("/events", {})
        assert refused.value.retry_at == datetime(2026, 11, 21, 23, 59, 59)
        assert len(calls) == 3
        clock.now = refused.value.retry_at
        await client._get("/events", {})
        assert (await budget.view()).spent_day == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_q3_quote_dispatch_survives_business_rollback(db_engine, clock: Clock) -> None:
    budget = meter(db_engine, clock, hourly=1, daily=10)
    calls: list[str] = []
    client = provider(budget, calls)
    key = f"rolled-back-{uuid.uuid4().hex}"
    try:
        async with budget.sessions() as business:
            business.add(ProviderWork(key=key, kind="synthetic", payload={}, next_at=clock.now))
            await business.flush()
            await client._get("/odds", {})
            await business.rollback()
        async with budget.sessions() as restarted:
            assert await restarted.get(ProviderWork, key) is None
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/odds", {})
        assert len(calls) == 1 and (await budget.view()).spent_hour == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_q4_each_network_or_5xx_retry_is_admitted_and_charged(
    db_engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = meter(db_engine, clock, hourly=3, daily=10)
    calls: list[str] = []

    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.ConnectError("synthetic transport failure", request=request)
        return httpx.Response(503 if len(calls) == 2 else 200, json=[])

    monkeypatch.setattr("src.services.odds_api.asyncio.sleep", AsyncMock())
    client = OddsApiProvider(
        "synthetic-not-an-account-key",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    try:
        assert await client._get("/odds", {}) == []
        assert len(calls) == client.requests_made == (await budget.view()).spent_hour == 3
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/odds", {})
        assert len(calls) == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_retry_stops_before_dispatch_when_global_allowance_is_gone(
    db_engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = meter(db_engine, clock, hourly=2, daily=10)
    calls: list[str] = []

    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(503, json=[])

    monkeypatch.setattr("src.services.odds_api.asyncio.sleep", AsyncMock())
    client = OddsApiProvider(
        "synthetic",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    try:
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/odds", {})
        assert len(calls) == client.requests_made == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_q5_refused_admission_has_no_http_and_a_separate_committed_record(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=1, daily=10)
    await budget.admit()
    calls: list[str] = []
    client = provider(budget, calls)
    try:
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/odds", {})
        assert calls == [] and client.requests_made == 0
        async with budget.sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(ProviderAttempt)
                    .where(ProviderAttempt.meter == budget.meter)
                )
                == 1
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(ProviderRefusal)
                    .where(ProviderRefusal.meter == budget.meter)
                )
                == 1
            )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_q6_uncertain_reservation_and_cooldown_survive_restart(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=3, daily=10)
    reservation = await budget.admit()
    await budget.observe(reservation, 429, {"Retry-After": "600"})
    restarted = ProviderBudget(
        budget.sessions, policy=budget.policy, meter=budget.meter, clock=clock
    )
    with pytest.raises(ProviderBudgetRefused) as refused:
        await restarted.admit()
    assert refused.value.retry_at == clock.now + timedelta(minutes=10)
    assert (await restarted.view()).spent_hour == 1
    assert (await restarted.view()).remaining_hour == 0
    clock.now += timedelta(minutes=10)
    await restarted.admit()
    assert (await budget.view()).spent_hour == 2


@pytest.mark.asyncio
async def test_q7_concurrent_leagues_worker_and_retry_share_one_remaining_attempt(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=3, daily=10)
    calls: list[str] = []
    client = provider(budget, calls)
    try:
        await client._get("/events", {})
        await client._get("/events", {})
        barrier = asyncio.Barrier(4)

        async def request(category):
            with provider_category(category):
                await barrier.wait()
                return await client._get("/odds", {})

        results = await asyncio.gather(
            *(
                request(category)
                for category in ("foreground", "background", "legacy", "settlement")
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(r, ProviderBudgetRefused) for r in results) == 3
        assert sum(r == [] for r in results) == 1
        assert len(calls) == client.requests_made == (await budget.view()).spent_hour == 3
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_budget_lock_is_released_while_http_is_still_blocked(db_engine, clock: Clock) -> None:
    budget = meter(db_engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def dispatch(request: httpx.Request) -> httpx.Response:
        entered.set()
        await release.wait()
        return httpx.Response(200, json=[])

    client = OddsApiProvider(
        "synthetic",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    pending = asyncio.create_task(client._get("/odds", {}))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        another = await asyncio.wait_for(budget.admit("settlement"), 2)
        assert another.id is not None and not pending.done()
        assert (await budget.view()).spent_hour == 2
    finally:
        release.set()
        await pending
        await client.close()


@pytest.mark.asyncio
async def test_late_headers_never_increase_capacity_and_expired_reset_recovers(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=10, daily=20)
    first, second = await budget.admit(), await budget.admit()
    # One equally timestamped reservation must be deducted from this header.
    await budget.observe(second, 200, {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "120"})
    await budget.admit()
    await budget.observe(first, 200, {"X-RateLimit-Remaining": "9", "X-RateLimit-Reset": "120"})
    assert (await budget.view()).remaining_hour == 0
    with pytest.raises(ProviderBudgetRefused):
        await budget.admit()
    clock.now += timedelta(seconds=120)
    await budget.admit()
    await budget.observe(first, 200, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "120"})
    assert (await budget.view()).header_remaining is None
    assert (await budget.view()).spent_hour == 4


@pytest.mark.asyncio
async def test_background_spacing_is_durable_and_saturday_pause_is_not_a_quota_reset(
    db_engine, clock: Clock
) -> None:
    # Both Friday charges remain inside the rolling day at Saturday's pause.
    clock.now = datetime(2026, 11, 20, 11)
    budget = meter(db_engine, clock)
    await budget.admit("background")
    restarted = ProviderBudget(budget.sessions, meter=budget.meter, clock=clock)
    clock.now += timedelta(minutes=6) - timedelta(microseconds=1)
    with pytest.raises(ProviderBudgetRefused) as refused:
        await restarted.admit("background")
    assert refused.value.reason == "background_spacing"
    clock.now += timedelta(microseconds=1)
    await restarted.admit("background")
    clock.now = datetime(2026, 11, 21, 10)
    with pytest.raises(ProviderBudgetRefused) as paused:
        await restarted.admit("background")
    assert paused.value.retry_at == datetime(2026, 11, 21, 13)
    await restarted.admit("foreground")
    assert (await restarted.view()).spent_day == 3


@pytest.mark.asyncio
async def test_five_noon_attempts_are_shared_across_restarts_and_categories_remain_ceiling(
    db_engine, clock: Clock
) -> None:
    clock.now = datetime(2026, 11, 21, 12)
    budget = meter(db_engine, clock)
    for _ in range(5):
        await budget.admit("opening")
    restarted = ProviderBudget(budget.sessions, meter=budget.meter, clock=clock)
    with pytest.raises(ProviderBudgetRefused):
        await restarted.admit("opening")
    await restarted.admit("foreground")
    assert (await restarted.view()).spent_hour == 6


@pytest.mark.asyncio
async def test_backwards_wall_clock_cannot_refund_a_committed_reservation(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=1, daily=10)
    await budget.admit()
    clock.now -= timedelta(hours=2)
    restarted = ProviderBudget(
        budget.sessions, policy=budget.policy, meter=budget.meter, clock=clock
    )
    with pytest.raises(ProviderBudgetRefused):
        await restarted.admit()
    assert (await restarted.view()).spent_hour == 1


@pytest.mark.asyncio
async def test_enabled_constructors_meter_legacy_odds_and_all_betfair_transports(
    db_engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.config import settings
    from src.services.betfair import Betfair

    budget = meter(db_engine, clock, hourly=5, daily=20)
    monkeypatch.setattr(settings, "two_games_enabled", True)
    monkeypatch.setattr(ProviderBudget, "from_settings", classmethod(lambda cls: budget))
    monkeypatch.setattr("src.services.betfair.asyncio.sleep", AsyncMock())
    calls: list[str] = []
    rpc_attempts = 0

    async def dispatch(request: httpx.Request) -> httpx.Response:
        nonlocal rpc_attempts
        calls.append(request.url.path)
        if "login" in request.url.path.lower() or "keepAlive" in request.url.path:
            return httpx.Response(200, json={"loginStatus": "SUCCESS", "sessionToken": "synthetic"})
        if request.method == "POST":
            rpc_attempts += 1
            return httpx.Response(503 if rpc_attempts == 1 else 200, json={"result": []})
        return httpx.Response(200, json=[])

    def http() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        )

    # Certificate paths are synthetic: injected MockTransports never load or use them.
    betfair = Betfair(
        "synthetic-app",
        "synthetic-user",
        "synthetic-password",
        cert_file="synthetic.pem",
        key_file="synthetic.key",
        identity_client=http(),
        betting_client=http(),
    )
    odds = OddsApiProvider("synthetic-key", client=http())
    try:
        assert await betfair.login() == "synthetic"
        await betfair.keep_alive()
        assert await betfair._rpc("listCompetitions", {}) == []
        assert await odds._get("/events", {}) == []
        with pytest.raises(ProviderBudgetRefused):
            await betfair._rpc("listMarketBook", {})
        assert calls[0] == "/api/certlogin" and calls[1] == "/api/keepAlive"
        assert len(calls) == (await budget.view()).spent_hour == 5
        assert rpc_attempts == 2 and odds.requests_made == 1
    finally:
        await betfair.close()
        await odds.close()


@pytest.mark.parametrize("status,cooldown", [(401, 900), (403, 900), (429, 300)])
@pytest.mark.asyncio
async def test_real_refusal_response_cools_down_a_restarted_transport(
    db_engine, clock: Clock, status: int, cooldown: int
) -> None:
    from src.services.odds_provider import OddsProviderError

    budget = meter(db_engine, clock, hourly=10, daily=20)
    calls: list[str] = []

    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status, json={"error": "synthetic refusal"})

    first = OddsApiProvider(
        "synthetic-key",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    try:
        with pytest.raises(OddsProviderError):
            await first._get("/events", {})
    finally:
        await first.close()
    restarted = ProviderBudget(
        budget.sessions, policy=budget.policy, meter=budget.meter, clock=clock
    )
    second = OddsApiProvider(
        "synthetic-key",
        budget=restarted,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    try:
        with pytest.raises(ProviderBudgetRefused) as refusal:
            await second._get("/events", {})
        assert refusal.value.retry_at == clock.now + timedelta(seconds=cooldown)
        assert len(calls) == 1 and (await restarted.view()).spent_day == 1
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_first_header_accounts_for_concurrent_identically_timestamped_dispatch(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=10, daily=20)
    first_entered = asyncio.Event()
    both_entered = asyncio.Event()
    release_second = asyncio.Event()
    calls: list[str] = []

    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            first_entered.set()
            await both_entered.wait()
            remaining = "1"
        else:
            both_entered.set()
            await release_second.wait()
            remaining = "0"
        return httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": remaining, "X-RateLimit-Reset": "120"},
        )

    client = OddsApiProvider(
        "synthetic",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    first = asyncio.create_task(client._get("/events", {}))
    await asyncio.wait_for(first_entered.wait(), 3)
    second = asyncio.create_task(client._get("/odds", {}))
    try:
        await asyncio.wait_for(first, 3)
        assert not second.done()
        assert (await budget.view()).remaining_hour == 0
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/events", {})
        assert len(calls) == 2 and (await budget.view()).spent_hour == 2
    finally:
        release_second.set()
        await second
        await client.close()


@pytest.mark.asyncio
async def test_later_first_header_deducts_earlier_still_in_flight_request(
    db_engine, clock: Clock
) -> None:
    budget = meter(db_engine, clock, hourly=10, daily=20)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/events":
            entered.set()
            await release.wait()
        return httpx.Response(
            200, json=[], headers={"X-RateLimit-Remaining": "1", "X-RateLimit-Reset": "120"}
        )

    client = OddsApiProvider(
        "synthetic",
        budget=budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    earlier = asyncio.create_task(client._get("/events", {}))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        clock.now += timedelta(seconds=1)
        await client._get("/odds", {})
        assert not earlier.done()
        assert (await budget.view()).remaining_hour == 0
        with pytest.raises(ProviderBudgetRefused):
            await client._get("/odds", {})
        assert len(calls) == 2
    finally:
        release.set()
        await earlier
        await client.close()
