"""One dead fixture must not cost the card its prices. Batch 119.

``/odds/multi`` answers ``400 One or more eventIds not found`` when **any** id in the
chunk is unknown, and odds-api.io expires an id once its match has been played. Production
held 738 already-played fixtures in the pool and logged ``fixtures=202 priced=0`` three
times in one evening, with the degraded banner, on a settled round — twenty expired ids,
all matches played between 29 August and 5 September, taking every price on the card with
them.

Two properties are asserted here and they pull in opposite directions, which is why they
are in one module:

* **isolation** — a refused chunk costs its own ten their prices and nothing else, and
  crucially marks *nothing*: a chunk of ten refused for one dead id is not evidence that
  any particular fixture is unpriced, and treating it as evidence would take nine pickable
  fixtures off the card.
* **attribution** — the dead id still has to be found, or the same chunk is refused again
  tomorrow. A single id the provider refuses on its own *is* evidence, and it is recorded
  through Batch 114's marker so ``askable`` stops paying for it.

The second is bounded on purpose: this runs on the browsing path against a 100/hour plan.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import date
from decimal import Decimal

import pytest

from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderBadRequest,
    OddsProviderRateLimited,
    Outcome,
    Selection,
    Slate,
    SlateWindow,
)

pytestmark = pytest.mark.asyncio

CARD = [f"ev{index:03d}" for index in range(30)]
#: In the third chunk, so the first two are proof the rest of the card survives.
DEAD = "ev025"


def _odds(event_id: str) -> FixtureOdds:
    return FixtureOdds(
        provider_event_id=event_id,
        home="Home",
        away="Away",
        selections=[
            Selection(
                market=Market.MATCH_ODDS,
                outcome=Outcome.HOME,
                runner_name="Home",
                price=Decimal("2.00"),
            )
        ],
    )


class _ExpiringProvider(OddsProvider):
    """Refuses any request carrying an expired id, exactly as ``/odds/multi`` does."""

    def __init__(
        self, *, expired: set[str], error: type[OddsProviderAPIError] | None = None
    ) -> None:
        self.expired = expired
        self.error = error or OddsProviderBadRequest
        self.calls: list[list[str]] = []
        self.rate_limit_after: int | None = None

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
        return Slate(starts_on=starts_on, fixtures=[])

    async def fetch_competitions(self) -> list[Competition]:
        return []

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return []

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        self.calls.append(list(event_ids))
        if self.rate_limit_after is not None and len(self.calls) > self.rate_limit_after:
            raise OddsProviderRateLimited("odds-api.io /odds/multi rate-limited (429), not retried")
        dead = [event_id for event_id in event_ids if event_id in self.expired]
        if dead:
            raise self.error(
                "odds-api.io /odds/multi unexpected status 400: One or more eventIds not found"
            )
        return [_odds(event_id) for event_id in event_ids]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cache(inner: OddsProvider, clock: _Clock, *, isolation: int = 0) -> CachingOddsProvider:
    return CachingOddsProvider(inner, ttl_seconds=300.0, isolation_requests=isolation, clock=clock)


async def test_a_refused_chunk_costs_only_its_own_ten_their_prices() -> None:
    """The defect, in one assertion: twenty of thirty priced rather than none of thirty."""
    inner = _ExpiringProvider(expired={DEAD})
    snapshot = await _cache(inner, _Clock()).fetch_odds_best_effort(CARD)

    priced = {odds.provider_event_id for odds in snapshot.odds}
    assert len(priced) == 20, f"{len(priced)} of {len(CARD)} priced"
    assert priced == set(CARD[:20])
    assert snapshot.degraded, "the card is missing prices and the banner has to say so"


async def test_a_refused_chunk_marks_nothing() -> None:
    """Nine pickable fixtures must not be marked unpriced to record one dead one.

    ``observed`` is the evidence ``record_observations`` writes the marker from, so this is
    the assertion that stops the isolation from becoming a worse bug than the one it fixes.
    """
    inner = _ExpiringProvider(expired={DEAD})
    snapshot = await _cache(inner, _Clock()).fetch_odds_best_effort(CARD)

    assert snapshot.observed == set(CARD[:20])
    assert not snapshot.observed & set(CARD[20:])


async def test_the_expired_id_is_found_and_recorded_rather_than_re_asked() -> None:
    """Attribution: repeated sweeps halve the suspect chunk until one id can be blamed.

    Each refill halves what is still suspect and keeps the half that answered, so the ten-id
    chunk is resolved in three card loads and six requests — and what the deployment ends
    with is the dead id in ``observed`` with no price, which is exactly the evidence that
    writes ``fixtures.odds_unpriced_since_utc``.

    Successive loads inside one TTL window, which is the realistic shape: near a lock the
    card is reloaded every twenty seconds against a half-hour ceiling. The convergence is
    what makes it terminate — a half that answered is cached and drops out of the next
    load's stale set, so the suspect set only ever shrinks.
    """
    inner = _ExpiringProvider(expired={DEAD})
    clock = _Clock()
    cache = _cache(inner, clock, isolation=2)

    seen: set[str] = set()
    for _ in range(4):
        snapshot = await cache.fetch_odds_best_effort(CARD)
        seen |= snapshot.observed
        clock.advance(20.0)

    assert DEAD in seen, "the dead id was never attributed"
    final = await cache.fetch_odds_best_effort(CARD)
    assert DEAD not in {odds.provider_event_id for odds in final.odds}
    # And its nine chunk-mates are priced rather than collateral.
    assert set(CARD[20:]) - {DEAD} <= {odds.provider_event_id for odds in final.odds}
    assert not final.degraded, "once the dead id is cached as unpriced the card is whole again"


async def test_isolation_is_bounded_by_its_budget() -> None:
    """It runs on the browsing path, so it may not chase a dead id with the whole hour."""
    clock = _Clock()
    generous = _ExpiringProvider(expired={DEAD})
    await _cache(generous, clock, isolation=2).fetch_odds_best_effort(CARD)
    assert len(generous.calls) == 3 + 2, "three chunks plus exactly two isolation probes"

    off = _ExpiringProvider(expired={DEAD})
    await _cache(off, _Clock(), isolation=0).fetch_odds_best_effort(CARD)
    assert len(off.calls) == 3, "with no budget, isolation does not run at all"


async def test_a_transient_failure_attributes_nothing() -> None:
    """A ``500`` says nothing about any particular fixture, so nothing is marked.

    The whole reason ``400`` got its own exception type. A blip is worth asking again on the
    next page load; marking a fixture unpriced because the provider had a bad second would
    take it off the card for six hours.
    """
    inner = _ExpiringProvider(expired={DEAD}, error=OddsProviderAPIError)
    snapshot = await _cache(inner, _Clock(), isolation=2).fetch_odds_best_effort(CARD)

    assert snapshot.observed == set(CARD[:20])
    assert DEAD not in snapshot.observed
    assert len(inner.calls) == 3, "a transient failure is not isolated"


async def test_the_pick_path_still_raises() -> None:
    """Freezing a price onto a pick degrades to nothing — it refuses, as it always has."""
    inner = _ExpiringProvider(expired={DEAD})
    with pytest.raises(OddsProviderBadRequest):
        await _cache(inner, _Clock(), isolation=2).fetch_odds([DEAD])


async def test_a_rate_limit_during_isolation_stops_the_sweep() -> None:
    """The quota is gone; chasing a dead id into a ``429`` is the one thing that cannot help."""
    inner = _ExpiringProvider(expired={DEAD})
    inner.rate_limit_after = 3  # the three real chunks succeed, the first probe does not
    cache = _cache(inner, _Clock(), isolation=2)

    snapshot = await cache.fetch_odds_best_effort(CARD)
    assert snapshot.degraded
    assert len(inner.calls) == 4, "isolation stopped at the 429 rather than spending again"
    assert cache.budget().rate_limited_for is None or cache.budget().rate_limited_for >= 0


async def test_a_healthy_card_is_unchanged_by_any_of_this() -> None:
    """The steady state: one request per ten fixtures, everything observed, nothing degraded."""
    inner = _ExpiringProvider(expired=set())
    snapshot = await _cache(inner, _Clock(), isolation=2).fetch_odds_best_effort(CARD)

    assert len(inner.calls) == 3
    assert snapshot.observed == set(CARD)
    assert not snapshot.degraded
    assert len(snapshot.odds) == len(CARD)
