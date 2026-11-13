"""Counted implementation timelines; cold quotes deliberately receive no sharing discount.

These finite scenarios are load evidence, not live entitlement/coverage promises.
100 memberships can span leagues; the existing per-league member limit is unchanged.
"""

from __future__ import annotations

import asyncio
import math
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.config import settings
from src.models.two_game import ProviderAttempt, ProviderRefusal, ProviderSnapshot
from src.services.provider_budget import ProviderBudgetRefused, provider_category
from src.services.two_game_quotes import SharedQuotes
from src.services.two_game_storage import london_utc
from tests.test_two_game_discovery import WEEK, CensusSource


@pytest_asyncio.fixture
async def capacity_source(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    source = CensusSource(db_engine)
    try:
        yield source
    finally:
        await source.close()


def quotes(source: CensusSource) -> SharedQuotes:
    return SharedQuotes(
        source.sessions,
        source.client,
        source=source.source,
        bookmaker="Bet365",
        clock=source.clock,
    )


async def cold_requests(source: CensusSource, count: int, label: str) -> tuple[int, int]:
    cache = quotes(source)

    async def one(index: int) -> bool:
        try:
            view = await cache.get_fresh(f"{source.source}-{label}-{index}")
            assert view.odds is not None and view.age_seconds == 0 and not view.degraded
            return True
        except ProviderBudgetRefused:
            return False

    # Real independent database callers contend for the same meter. Limit transport
    # concurrency, not membership or accepted slots, to the fixture's connection pool.
    semaphore = asyncio.Semaphore(12)

    async def bounded(index: int) -> bool:
        async with semaphore:
            return await one(index)

    results = await asyncio.gather(*(bounded(index) for index in range(count)))
    return sum(results), len(results) - sum(results)


async def opening_checks(source: CensusSource) -> None:
    with provider_category("opening"):
        for _ in range(5):
            await source.client.fetch_census_page(WEEK + timedelta(days=7))


@pytest.mark.asyncio
@pytest.mark.parametrize("members,requested", [(14, 85), (30, 177), (100, 600)])
async def test_counted_noon_rush_reports_overload_without_reducing_membership(
    capacity_source, members, requested, record_property
):
    source = capacity_source
    source.clock.now = london_utc(WEEK, 12)
    await opening_checks(source)
    accepted, refused = await cold_requests(source, requested, f"rush-{members}")
    assert (accepted, refused) == (85, requested - 85)
    assert len(source.calls) == 90
    view = await source.budget.view()
    assert (view.spent_hour, view.spent_day, view.remaining_hour) == (90, 90, 0)
    async with source.sessions() as db:
        refusals = list(
            await db.scalars(select(ProviderRefusal).where(ProviderRefusal.meter == source.source))
        )
        assert len(refusals) == refused
    record_property(
        "timeline",
        {
            "memberships": members,
            "cold_foreground_requested": requested,
            "opening_calls": 5,
            "foreground_admitted": accepted,
            "refused": refused,
            "actual_http": len(source.calls),
            "quote_age_seconds": 0,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("members,early,refused", [(14, 28, 0), (30, 56, 0), (100, 85, 90)])
async def test_counted_weekday_spread_and_next_week_noon_has_explicit_refusals(
    capacity_source, members, early, refused, record_property
):
    source = capacity_source
    weekday_admitted = 0
    # Each membership saves six slots and one cold replacement. Spread across five
    # days, at most ten memberships per two-hour slot; no six-slot cap is reduced.
    for day in range(5):
        todays = list(range(day, members, 5))
        for start in range(0, len(todays), 10):
            source.clock.now = london_utc(WEEK - timedelta(days=5 - day), 9 + 2 * (start // 10))
            admitted, rejected = await cold_requests(
                source, 7 * len(todays[start : start + 10]), f"day-{day}-{start}"
            )
            assert rejected == 0
            weekday_admitted += admitted
    assert weekday_admitted == members * 7
    source.clock.now = london_utc(WEEK, 12)
    await opening_checks(source)
    admitted, rejected = await cold_requests(source, 7 * math.ceil(members / 4), "early-next")
    assert (admitted, rejected) == (early, refused)
    assert len(source.calls) == members * 7 + early + 5
    record_property(
        "timeline",
        {
            "memberships": members,
            "weekday_http": weekday_admitted,
            "early_next_http": admitted,
            "opening_http": 5,
            "refused": rejected,
            "total_http": len(source.calls),
            "quote_age_seconds": 0,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sizes", [(77, 120), (264, 264)])
async def test_two_large_cards_persist_queue_and_report_six_hour_coverage_failure(
    capacity_source, record_property, sizes
):
    source = capacity_source
    await source.league()
    source.clock.now = london_utc(WEEK - timedelta(days=5), 9)
    for week, size in enumerate(sizes):
        for index in range(size):
            source.event(f"large-{week}-{index}", WEEK + timedelta(weeks=week), 15)
    worker = source.worker()
    started = source.clock.now
    for _ in range(48 * 10):
        await worker.run(prepare=False if source.clock.now > started else True)
        source.clock.now += timedelta(minutes=6)
    async with source.sessions() as db:
        attempts = list(
            await db.scalars(
                select(ProviderAttempt.reserved_at)
                .where(ProviderAttempt.meter == source.source)
                .order_by(ProviderAttempt.reserved_at)
            )
        )
        refusals = list(
            await db.scalars(select(ProviderRefusal).where(ProviderRefusal.meter == source.source))
        )
        snapshots = list(
            await db.scalars(
                select(ProviderSnapshot).where(
                    ProviderSnapshot.key.like("quote:v1:%"),
                    ProviderSnapshot.payload["provider"].astext == source.source,
                )
            )
        )
    assert len(snapshots) == sum(sizes)
    assert len(attempts) == len(source.calls)
    for at in attempts:
        assert sum(at - timedelta(hours=1) < stamp <= at for stamp in attempts) <= 10
        assert sum(at - timedelta(days=1) < stamp <= at for stamp in attempts) <= 120
    if sizes == (264, 264):
        assert len(refusals) > 0
    else:
        assert len(refusals) == 0
    ages = [(source.clock.now - row.observed_at).total_seconds() for row in snapshots]
    if sizes == (264, 264):
        assert max(ages) > 6 * 3600
    views = await quotes(source).peek_many(
        [str(row.payload["odds"]["provider_event_id"]) for row in snapshots]
    )
    if sizes == (264, 264):
        assert any(view.degraded for view in views.values())
    before = len(source.calls)
    # Browsing this backlog never spends another refill request.
    await quotes(source).peek_many(list(views))
    assert len(source.calls) == before
    record_property(
        "timeline",
        {
            "card_fixtures": list(sizes),
            "hours": 48,
            "actual_http": len(source.calls),
            "refusals": len(refusals),
            "oldest_snapshot_seconds": max(ages),
            "six_hour_coverage": "unaccepted",
        },
    )
