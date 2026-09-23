"""Batch 160 — the gauge measures the plan, not a fraction of it.

The plan counter was charged **only** from the odds cache's own refills, on
``fetch_odds``. ``fetch_slate``, ``fetch_competitions`` and ``settle`` are separate
provider entry points and none of them reached it, so the gauge saw roughly **127 of a
Saturday's 283** requests.

That is not a reporting problem. Two things read the gauge and act on it:

* the cache's widening valve, which slackens the freshness ceiling as the remaining
  budget falls — against a number that was too small, it slackened too late; and
* the **50-request reserve that protects the pick path** (Batch 114), built so a member
  could still freeze a price on a busy morning. It was reserving against a number that
  missed half the spend, so the hour it thought it was protecting had already gone.

These drive a real :class:`CachingOddsProvider` against a provider that counts its own
upstream requests exactly the way ``OddsApiProvider`` does — one ``/events`` per
competition walked, one ``/events/{id}`` per settlement, one ``/leagues`` for the
catalogue (memoised per client), and one ``/odds/multi`` per ten events.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime

import pytest

from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    OddsProvider,
    OddsProviderError,
    Slate,
    SlateFixture,
    SlateWindow,
)
from tests.test_odds_cache import _Clock, _odds

pytestmark = pytest.mark.asyncio

EVENTS_PER_ODDS_REQUEST = 10

#: The live catalogue, measured 2026-09-12 — what an unnarrowed slate walk costs.
CATALOGUE = [f"comp-{n}" for n in range(41)]
#: What the daily run narrows to.
POOLED = CATALOGUE[:20]


class _PlanCountingProvider(OddsProvider):
    """Counts its own upstream requests the way the real client does.

    Deliberately not a mock of the cache's arithmetic: it counts what an HTTP client
    would actually send, so a test that compares the two is comparing two independent
    answers rather than one answer with itself.
    """

    def __init__(self, *, priced: set[str] | None = None) -> None:
        self.requests_made = 0
        self.priced = priced
        self._catalogue_fetched = False

    async def login(self) -> str:
        return "token"

    async def keep_alive(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        wanted = set(competition_ids) if competition_ids is not None else None
        walked = [c for c in CATALOGUE if wanted is None or c in wanted]
        self.requests_made += len(walked)  # one /events per competition
        return Slate(
            starts_on=starts_on,
            fixtures=[
                SlateFixture(
                    provider_event_id=f"{competition}-1",
                    home="Home",
                    away="Away",
                    kickoff_utc=datetime(2026, 9, 5, 14, 0, tzinfo=UTC),
                    competition=competition,
                    competition_id=competition,
                )
                for competition in walked
            ],
        )

    async def fetch_competitions(self) -> list[Competition]:
        # `OddsApiProvider._all_leagues` is memoised on the client, so only the first
        # call of a process pays. "Usually free" is not "free", and this is why.
        if not self._catalogue_fetched:
            self.requests_made += 1
            self._catalogue_fetched = True
        return [Competition(competition_id=c, competition=c) for c in CATALOGUE]

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        distinct = list(dict.fromkeys(event_ids))
        self.requests_made += len(distinct)  # one /events/{id} each
        return [
            EventSettlement(provider_event_id=e, status="finished", settled=True) for e in distinct
        ]

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        self.requests_made += math.ceil(len(event_ids) / EVENTS_PER_ODDS_REQUEST)
        return [_odds(event) for event in event_ids if self.priced is None or event in self.priced]


def _window() -> SlateWindow:
    return SlateWindow(start_weekday=5, start_minute=15 * 60, end_weekday=5, end_minute=15 * 60)


# ── The gauge ──────────────────────────────────────────────────────────────────


async def test_a_full_saturday_leaves_the_counter_and_the_provider_agreeing() -> None:
    """The finding, as one number against another.

    Every entry point a Saturday uses, in the order a Saturday uses them: the catalogue
    for the competition picker, two windows of discovery, the odds sweeps members cause,
    and the settlement pass that evening.
    """
    clock = _Clock()
    events = [f"ev{n}" for n in range(60)]
    inner = _PlanCountingProvider(priced=set(events))
    cache = CachingOddsProvider(inner, ttl_seconds=60.0, clock=clock)

    await cache.fetch_competitions()
    for _ in range(2):  # two windows
        await cache.fetch_slate(_window(), date(2026, 9, 5), competition_ids=POOLED)
    await cache.fetch_odds(events)
    clock.advance(120)
    await cache.fetch_odds(events)
    await cache.settle(events)

    assert cache.budget().day_used == inner.requests_made
    assert cache.budget().hour_used == inner.requests_made


async def test_the_gauge_used_to_miss_most_of_that_saturday() -> None:
    """How much it missed, stated as a number rather than as a claim.

    The odds sweeps are the only part the counter ever saw. Everything else — the
    catalogue, both discovery walks and the settlement pass — went unrecorded.
    """
    clock = _Clock()
    events = [f"ev{n}" for n in range(60)]
    inner = _PlanCountingProvider(priced=set(events))
    cache = CachingOddsProvider(inner, ttl_seconds=60.0, clock=clock)

    await cache.fetch_competitions()
    for _ in range(2):
        await cache.fetch_slate(_window(), date(2026, 9, 5), competition_ids=POOLED)
    after_uncharged_paths = inner.requests_made

    await cache.fetch_odds(events)
    await cache.settle(events)
    total = inner.requests_made

    odds_only = math.ceil(len(events) / EVENTS_PER_ODDS_REQUEST)
    assert cache.budget().day_used == total
    # What the old gauge would have shown, against what the plan actually spent.
    assert odds_only < total / 2, "the uncharged entry points were the larger half"
    assert after_uncharged_paths == 1 + 2 * len(POOLED)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        ("competitions", 1),
        ("slate_narrowed", len(POOLED)),
        ("slate_full", len(CATALOGUE)),
        ("settle", 7),
    ],
)
async def test_each_entry_point_is_charged_what_it_spends(call: str, expected: int) -> None:
    """One per entry point, so a regression names which door was left open."""
    clock = _Clock()
    inner = _PlanCountingProvider()
    cache = CachingOddsProvider(inner, ttl_seconds=60.0, clock=clock)

    if call == "competitions":
        await cache.fetch_competitions()
    elif call == "slate_narrowed":
        await cache.fetch_slate(_window(), date(2026, 9, 5), competition_ids=POOLED)
    elif call == "slate_full":
        await cache.fetch_slate(_window(), date(2026, 9, 5))
    else:
        await cache.settle([f"ev{n}" for n in range(7)])

    assert cache.budget().day_used == expected
    assert cache.budget().day_used == inner.requests_made


async def test_a_call_that_raises_is_still_charged() -> None:
    """A 429 is the moment the count matters most: the requests were sent regardless."""

    class _Failing(_PlanCountingProvider):
        async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
            self.requests_made += 3
            raise OddsProviderError("provider fell over mid-sweep")

    clock = _Clock()
    inner = _Failing()
    cache = CachingOddsProvider(inner, ttl_seconds=60.0, clock=clock)

    with pytest.raises(OddsProviderError):
        await cache.settle([f"ev{n}" for n in range(9)])

    assert cache.budget().day_used == 3


# ── The reserve that reads the gauge ───────────────────────────────────────────


async def test_the_pick_reserve_refuses_at_the_real_boundary() -> None:
    """Batch 114's reserve, measured against a gauge that can now see the spend.

    The reserve holds **browsing** back once the hour has only its allowance left, so
    the action with a deadline still has one — the pick path is deliberately exempt.
    Spending the hour on discovery used to be invisible to it: browsing carried on until
    the *odds* spend alone reached the boundary, by which time the plan was long gone.
    """
    clock = _Clock()
    inner = _PlanCountingProvider(priced={"ev0"})
    cache = CachingOddsProvider(
        inner,
        ttl_seconds=60.0,
        clock=clock,
        hourly_request_limit=100,
        pick_reserve_requests=50,
    )

    # Two unnarrowed discovery walks: 82 requests, and not one of them odds.
    for _ in range(2):
        await cache.fetch_slate(_window(), date(2026, 9, 5))
    assert cache.budget().hour_used == 2 * len(CATALOGUE)
    assert cache.budget().hour_remaining <= 50

    # Browsing is withheld: no upstream request is made at all, and the screen falls
    # through to whatever the cache already holds rather than failing.
    spent_before_browse = inner.requests_made
    browsed = await cache.fetch_odds_best_effort(["ev0"])
    assert inner.requests_made == spent_before_browse, "browsing spent from the reserve"
    assert browsed.odds == []

    # And the path the reserve exists for is still served.
    priced = await cache.fetch_odds(["ev0"])
    assert [o.provider_event_id for o in priced] == ["ev0"]
    assert inner.requests_made > spent_before_browse


async def test_the_reserve_still_lets_browsing_through_while_the_hour_has_room() -> None:
    """The other side of the boundary, so the reserve is not simply always refusing."""
    clock = _Clock()
    inner = _PlanCountingProvider(priced={"ev0"})
    cache = CachingOddsProvider(
        inner,
        ttl_seconds=60.0,
        clock=clock,
        hourly_request_limit=100,
        pick_reserve_requests=50,
    )

    await cache.fetch_slate(_window(), date(2026, 9, 5), competition_ids=POOLED)
    assert cache.budget().hour_remaining > 50

    spent = inner.requests_made
    browsed = await cache.fetch_odds_best_effort(["ev0"])
    assert inner.requests_made == spent + 1, "browsing was withheld while the hour had room"
    assert [o.provider_event_id for o in browsed.odds] == ["ev0"]


async def test_without_the_discovery_spend_the_reserve_would_not_have_fired() -> None:
    """The defect stated as a difference.

    The same browse, the same hour, the same reserve — and the only thing that changed
    is whether the discovery walks were counted. Before this batch they were not, so the
    gauge read zero and browsing was let through onto a plan that had 18 requests left.
    """
    clock = _Clock()
    inner = _PlanCountingProvider(priced={"ev0"})
    cache = CachingOddsProvider(
        inner,
        ttl_seconds=60.0,
        clock=clock,
        hourly_request_limit=100,
        pick_reserve_requests=50,
    )

    for _ in range(2):
        await cache.fetch_slate(_window(), date(2026, 9, 5))

    # What the provider has actually spent, versus what the old gauge would have seen.
    assert inner.requests_made == 82
    assert cache.budget().hour_used == 82
    old_gauge_would_have_read = 0
    assert (
        cache.budget().hour_limit - old_gauge_would_have_read > 50
    ), "with the walks uncounted the reserve has no reason to hold anything back"
    assert cache.budget().hour_remaining == 18
