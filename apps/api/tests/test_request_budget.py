"""The provider's rate limit, asserted as a property rather than trusted as a comment.

odds-api.io's free plan allows **100 requests/hour and 500/day**. Batch 11 split
fixture discovery (scheduled, cheap, ahead of time) from pricing (on demand, behind a
cache whose ceiling tightens as lock approaches), and this module holds that split to
the numbers.

The measured launch Saturday is the fixture: 131 qualifying 15:00 kick-offs across 30
UK competitions. Discovery therefore costs ~30 requests per Saturday walked; a full
odds sweep costs ``ceil(131 / 10) = 14``.

These tests count *upstream* calls through a real :class:`CachingOddsProvider`, so
they measure the thing that is actually rate-limited rather than a model of it.
"""

from __future__ import annotations

import math

from src.services.gameweek import slate_odds_max_age, upcoming_saturdays
from src.services.odds_cache import CachingOddsProvider
from tests.test_odds_cache import _Clock, _CountingProvider

HOURLY_LIMIT = 100
DAILY_LIMIT = 500

LAUNCH_SATURDAY_FIXTURES = 131
UK_COMPETITIONS = 30
EVENTS_PER_ODDS_REQUEST = 10

# Mirrors the defaults in `Settings`; asserted against them below so the two cannot
# drift apart silently.
FAR_TTL = 7200.0
NEAR_TTL = 1800.0
PICK_TTL = 60.0

SLATE = [f"ev{i}" for i in range(LAUNCH_SATURDAY_FIXTURES)]


def _sweeps(inner: _CountingProvider) -> int:
    """Upstream requests implied by the batched calls the provider received."""
    return sum(math.ceil(len(call) / EVENTS_PER_ODDS_REQUEST) for call in inner.odds_calls)


def _cache(clock: _Clock) -> tuple[CachingOddsProvider, _CountingProvider]:
    inner = _CountingProvider()
    return CachingOddsProvider(inner, ttl_seconds=FAR_TTL, clock=clock), inner


async def _browse_for(
    cache: CachingOddsProvider, clock: _Clock, *, hours: float, max_age: float, every_seconds: float
) -> None:
    """Simulate members loading the pick page every ``every_seconds`` for ``hours``."""
    for _ in range(int(hours * 3600 / every_seconds)):
        await cache.fetch_odds(SLATE, max_age_seconds=max_age)
        clock.advance(every_seconds)


async def test_saturated_browsing_near_lock_stays_inside_the_hourly_limit() -> None:
    """The worst hour is the one before lock, with everyone refreshing constantly."""
    clock = _Clock()
    cache, inner = _cache(clock)

    # Fifteen members hammering the page every twenty seconds for the final hour.
    await _browse_for(cache, clock, hours=1, max_age=NEAR_TTL, every_seconds=20)

    assert _sweeps(inner) <= HOURLY_LIMIT


async def test_a_saturated_day_of_browsing_stays_inside_the_daily_limit() -> None:
    """A full 24 hours of someone refreshing continuously, through every tier.

    This is the worst case the design has to survive, not the expected one: fifteen
    friends do not refresh a coupon for a day without pause. If this passes, real
    traffic cannot exhaust the quota.
    """
    clock = _Clock()
    cache, inner = _cache(clock)

    # Lock more than a day out: the loosest ceiling.
    await _browse_for(cache, clock, hours=12, max_age=FAR_TTL, every_seconds=60)
    # The day before and match morning.
    await _browse_for(cache, clock, hours=6, max_age=FAR_TTL / 2, every_seconds=60)
    # The final approach.
    await _browse_for(cache, clock, hours=6, max_age=NEAR_TTL, every_seconds=20)

    browsing = _sweeps(inner)
    discovery = UK_COMPETITIONS * len(upcoming_saturdays_for_budget())
    assert browsing + discovery <= DAILY_LIMIT, (
        f"browsing {browsing} + discovery {discovery} exceeds {DAILY_LIMIT}/day"
    )


def upcoming_saturdays_for_budget() -> list[object]:
    """The horizon the daily discovery job actually walks, at its default setting."""
    from datetime import date

    from src.config import settings

    return list(upcoming_saturdays(date(2026, 8, 5), settings.slate_horizon_weeks))


async def test_freezing_every_members_pick_costs_one_request_each() -> None:
    """The submit path buys freshness the browse path cannot afford — per fixture.

    Fifteen members freezing a price is fifteen single-event requests, not fifteen
    sweeps of the card. That asymmetry is the whole reason ``max_age_seconds`` exists.
    """
    clock = _Clock()
    cache, inner = _cache(clock)

    await cache.fetch_odds(SLATE, max_age_seconds=NEAR_TTL)  # one sweep to browse
    sweeps_after_browse = _sweeps(inner)

    for member in range(15):
        clock.advance(120)  # each member takes a couple of minutes to choose
        await cache.fetch_odds([SLATE[member]], max_age_seconds=PICK_TTL)

    assert _sweeps(inner) - sweeps_after_browse == 15


async def test_discovery_is_a_fixed_daily_cost_independent_of_traffic() -> None:
    """Discovery is scheduled, so its cost is the horizon — not how busy the app is."""
    saturdays = upcoming_saturdays_for_budget()
    assert UK_COMPETITIONS * len(saturdays) <= HOURLY_LIMIT, (
        "the daily discovery burst must fit inside one hour's allowance"
    )


def test_the_configured_defaults_are_the_ones_this_module_budgets_for() -> None:
    """The budget above is only meaningful if it describes the shipped settings."""
    from src.config import settings

    assert settings.odds_cache_ttl_seconds == FAR_TTL
    assert settings.odds_cache_near_ttl_seconds == NEAR_TTL
    assert settings.odds_cache_pick_ttl_seconds == PICK_TTL


def test_the_tiers_are_ordered_loosest_first() -> None:
    """A tighter ceiling nearer lock is the point; the ordering must not invert."""
    from datetime import datetime, timedelta

    from src.models.gameweek import Gameweek, GameweekStatus

    now = datetime(2026, 8, 8, 0, 0)

    def ceiling(hours: float) -> float:
        gameweek = Gameweek(
            saturday_date=now.date(),
            status=GameweekStatus.open,
            locks_at_utc=now + timedelta(hours=hours),
        )
        return slate_odds_max_age(gameweek, now, near_ttl=NEAR_TTL, far_ttl=FAR_TTL)

    assert ceiling(72) >= ceiling(12) >= ceiling(1)
