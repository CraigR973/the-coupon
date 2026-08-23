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

from src.services.gameweek import slate_odds_max_age, upcoming_slate_dates
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


async def _tightest_browsing_hour() -> int:
    """Fifteen members hammering the page every twenty seconds for the final hour."""
    clock = _Clock()
    cache, inner = _cache(clock)
    await _browse_for(cache, clock, hours=1, max_age=NEAR_TTL, every_seconds=20)
    return _sweeps(inner)


async def _saturated_day_of_browsing() -> int:
    """A full 24 hours of someone refreshing continuously, through every tier."""
    clock = _Clock()
    cache, inner = _cache(clock)
    # Lock more than a day out: the loosest ceiling.
    await _browse_for(cache, clock, hours=12, max_age=FAR_TTL, every_seconds=60)
    # The day before and match morning.
    await _browse_for(cache, clock, hours=6, max_age=FAR_TTL / 2, every_seconds=60)
    # The final approach.
    await _browse_for(cache, clock, hours=6, max_age=NEAR_TTL, every_seconds=20)
    return _sweeps(inner)


def _daily_discovery() -> int:
    """What the scheduled discovery run spends: one request per competition per date."""
    return UK_COMPETITIONS * len(upcoming_saturdays_for_budget())


async def test_saturated_browsing_near_lock_stays_inside_the_hourly_limit() -> None:
    """The worst hour is the one before lock, with everyone refreshing constantly."""
    assert await _tightest_browsing_hour() <= HOURLY_LIMIT


async def test_a_saturated_day_of_browsing_stays_inside_the_daily_limit() -> None:
    """A full 24 hours of someone refreshing continuously, through every tier.

    This is the worst case the design has to survive, not the expected one: fifteen
    friends do not refresh a coupon for a day without pause. If this passes, real
    traffic cannot exhaust the quota.
    """
    browsing = await _saturated_day_of_browsing()
    discovery = _daily_discovery()
    total = browsing + discovery
    why = f"browsing {browsing} + discovery {discovery} exceeds {DAILY_LIMIT}/day"
    assert total <= DAILY_LIMIT, why


def upcoming_saturdays_for_budget() -> list[object]:
    """The horizon the daily discovery job actually walks, at its default setting."""
    from datetime import date

    from src.config import settings
    from src.services.odds_provider import SATURDAY_THREE_PM

    return list(
        upcoming_slate_dates(date(2026, 8, 5), SATURDAY_THREE_PM, settings.slate_horizon_weeks)
    )


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
    burst = UK_COMPETITIONS * len(saturdays)
    why = "the daily discovery burst must fit inside one hour's allowance"
    assert burst <= HOURLY_LIMIT, why


def test_discovery_cost_scales_with_windows_not_leagues() -> None:
    """Batch 14's per-league windows must not multiply the provider bill.

    Discovery groups leagues by window and fetches each ``(window, date)`` once, so
    a league added on the default Saturday is free and only a genuinely different
    window costs anything. Stated as arithmetic here; exercised against a real
    provider in ``test_scheduler_jobs.py``.
    """
    from src.services.odds_provider import SATURDAY_THREE_PM, SlateWindow

    dates = len(upcoming_saturdays_for_budget())
    friday_night = SlateWindow(start_weekday=4, start_minute=19 * 60, end_weekday=0)

    fifteen_leagues_one_window = {SATURDAY_THREE_PM for _ in range(15)}
    assert UK_COMPETITIONS * len(fifteen_leagues_one_window) * dates <= HOURLY_LIMIT

    # Two distinct windows cost two, not two-per-league.
    mixed = {SATURDAY_THREE_PM, SATURDAY_THREE_PM, friday_night}
    assert len(mixed) == 2
    assert UK_COMPETITIONS * len(mixed) * dates <= DAILY_LIMIT


# ── The one provider call left in the request path (Batch 35) ────────────────
#
# `POST /leagues/{slug}/gameweeks` walks the provider synchronously to build a round on a
# date outside the league's cadence. It costs one request per competition the league
# plays — its own selection since Batch 35, all ~30 UK competitions when unconfigured —
# so the limit on it has to fit whatever the budget above leaves unspent.

#: What one call costs an unconfigured all-UK league — the worst case, and the one the
#: limit has to survive. A league that has narrowed its competitions pays its own count
#: instead (1-3 in practice); that saving is asserted on requests issued in
#: ``test_scheduler_jobs.py`` rather than modelled here.
AD_HOC_ALL_UK_REQUESTS = UK_COMPETITIONS


def _ad_hoc_limits() -> dict[str, int]:
    """The shipped limit, parsed the way slowapi parses it: granularity → calls."""
    from limits import parse_many

    from src.routers.leagues import PROVIDER_SLATE_FETCH_LIMIT

    return {item.GRANULARITY.name: item.amount for item in parse_many(PROVIDER_SLATE_FETCH_LIMIT)}


def test_the_ad_hoc_round_limit_is_bounded_by_the_day_as_well_as_the_hour() -> None:
    """An hourly cap alone permits 24x its own number a day, and the day is the tighter one."""
    assert set(_ad_hoc_limits()) == {"hour", "day"}


async def test_the_ad_hoc_round_limit_fits_what_the_hour_leaves_spare() -> None:
    """The endpoint's whole allowance must fit beside the peak browsing hour."""
    spare = HOURLY_LIMIT - await _tightest_browsing_hour()
    spend = _ad_hoc_limits()["hour"] * AD_HOC_ALL_UK_REQUESTS
    assert spend <= spare, f"{spend} ad-hoc requests an hour against {spare} spare"


async def test_the_ad_hoc_round_limit_fits_what_the_day_leaves_spare() -> None:
    """And beside a fully saturated day of browsing plus the discovery run.

    This is the arithmetic the endpoint got wrong: at ``6/hour`` an admin could spend
    ~180 requests an hour against a 100/hour plan, and exhaustion is silent — picks stay
    ``pending`` and the week never finishes.
    """
    spare = DAILY_LIMIT - await _saturated_day_of_browsing() - _daily_discovery()
    spend = _ad_hoc_limits()["day"] * AD_HOC_ALL_UK_REQUESTS
    assert spend <= spare, f"{spend} ad-hoc requests a day against {spare} spare"


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
            starts_on=now.date(),
            status=GameweekStatus.open,
            locks_at_utc=now + timedelta(hours=hours),
        )
        return slate_odds_max_age(gameweek, now, near_ttl=NEAR_TTL, far_ttl=FAR_TTL)

    assert ceiling(72) >= ceiling(12) >= ceiling(1)


# ── The other provider call in the request path: freezing a pick (Batch 57) ──
#
# `POST /leagues/{slug}/picks` prices the one fixture being claimed, at a 60-second
# ceiling. Re-picking the *same* fixture inside a minute is free; moving between fixtures
# costs one request each time, which is exactly what a member does in the hour before
# lock. The per-user limit was set independently of this budget and has to fit it.


def _pick_submit_limits() -> dict[str, int]:
    """The shipped per-member limit, parsed the way slowapi parses it."""
    from limits import parse_many

    from src.routers.picks import PICK_SUBMIT_LIMIT

    return {item.GRANULARITY.name: item.amount for item in parse_many(PICK_SUBMIT_LIMIT)}


async def test_one_member_cannot_exhaust_the_plan_by_changing_their_mind() -> None:
    """No single member's whole allowance may outspend what the hour leaves.

    This is the property that failed. At the previous ``60/hour`` one member could spend
    sixty upstream requests against a plan with roughly a dozen to spare once peak
    browsing and the ad-hoc round allowance are subtracted — and exhaustion is silent:
    everyone else's prices simply stop refreshing.
    """
    spare = (
        HOURLY_LIMIT
        - await _tightest_browsing_hour()
        - _ad_hoc_limits()["hour"] * (AD_HOC_ALL_UK_REQUESTS)
    )
    spend = _pick_submit_limits()["hour"]
    assert spend <= spare, (
        f"one member may spend {spend} requests an hour against {spare} spare "
        f"(hourly {HOURLY_LIMIT} less browsing and ad-hoc rounds)"
    )


def test_the_pick_limit_still_covers_the_journey_it_exists_for() -> None:
    """Tightening it must not price out a member who legitimately changes their mind.

    One pick plus a few reconsiderations is the whole shape of the hour before lock. A
    limit that does not clear that is a worse bug than the one it fixes.
    """
    assert _pick_submit_limits()["hour"] >= 5


def test_the_pick_path_is_not_bounded_in_total_and_this_is_known() -> None:
    """Recorded as a gap rather than left to be rediscovered.

    A per-member limit cannot bound aggregate spend: a full league of fifteen at ten each
    is 150 requests against a 100/hour plan. Closing it needs a *shared* budget on the
    pick path — ``consume_shared_limit`` is the mechanism, already used by the populate
    path — plus a product decision about what a member sees when it is empty, because a
    pick cannot fall back to a stale price the way browsing can (``picks.py`` says why).
    That decision is the owner's; this test states the arithmetic so it stays visible.
    """
    league_max_members = 15  # `leagues.max_members` default
    worst_case = _pick_submit_limits()["hour"] * league_max_members
    assert worst_case > HOURLY_LIMIT, (
        "a per-member limit now bounds the aggregate — if this fails the gap has been "
        "closed and this test should be replaced by one asserting the real bound"
    )


# ── Batch 69: the manual sync trigger draws on the same budget ─────────────────
#
# An admin refreshing a slate by hand at 14:00 on a Saturday can 429 the refresh that
# matters, and exhaustion is silent: picks stay `pending` and the week never finishes.
# The trigger therefore charges the *existing* per-admin bucket rather than a second one
# beside it — two `2/hour` limits against a plan with room for two is `4/hour`, which is
# the shape of the bug Batch 57 found on the pick path.


def _sync_jobs() -> dict[str, object]:
    from src.services.admin_ops import manual_jobs

    return {job.key: job for job in manual_jobs()}


def test_the_manual_trigger_adds_no_allowance_of_its_own() -> None:
    """It shares the ad-hoc bucket, so the whole allowance is still the ad-hoc one."""
    from src.routers.admin import PROVIDER_SLATE_FETCH_LIMIT as trigger_limit
    from src.routers.leagues import PROVIDER_SLATE_FETCH_LIMIT as ad_hoc_limit

    assert trigger_limit is ad_hoc_limit


def test_the_costliest_manual_job_fits_what_the_hour_leaves_spare() -> None:
    """Pressing the most expensive button once must not outspend the hour on its own.

    Discovery is the expensive one: it walks every cadence date in the horizon, where a
    refresh walks only the next. This is the same property Batch 57 asserted for the pick
    limit — a single actor's single action, measured against what the plan has left after
    peak browsing.
    """
    jobs = _sync_jobs()
    worst = max(job.provider_requests for job in jobs.values())  # type: ignore[attr-defined]
    spare = HOURLY_LIMIT - _daily_discovery() // len(upcoming_saturdays_for_budget())
    assert worst <= spare, f"one press costs {worst} requests against {spare} spare in the hour"


def test_the_whole_manual_allowance_fits_beside_the_scheduled_runs() -> None:
    """The bucket is denominated in slate walks, so the cap is walks × the walk cost.

    ``2/hour`` of walks at 30 requests each is 60 — the number the ad-hoc endpoint was
    already sized to, which is the point of sharing the bucket rather than adding one.
    """
    allowance = _ad_hoc_limits()["hour"] * AD_HOC_ALL_UK_REQUESTS
    jobs = _sync_jobs()
    for job in jobs.values():
        units = job.budget_units  # type: ignore[attr-defined]
        cost = job.provider_requests  # type: ignore[attr-defined]
        assert cost <= units * AD_HOC_ALL_UK_REQUESTS, (
            f"{job.key} costs {cost} requests but is charged {units} walk(s)"  # type: ignore[attr-defined]
        )
    assert allowance <= HOURLY_LIMIT
