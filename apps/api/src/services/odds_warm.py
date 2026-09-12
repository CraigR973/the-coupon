"""Teach the deployment which fixtures a bookmaker prices, before a member has to.

Batch 115, folded into Batch 119. Batch 114 gave the deployment somewhere to persist what
it learns (``fixtures.odds_unpriced_since_utc``, revision ``023``) and left exactly one
thing that writes it: :func:`~src.services.odds_pricing.record_observations`, called from
``current_gameweek``. So the only thing that teaches the deployment anything is **an
authenticated member opening a pick screen**.

Measured against production a week after ``023`` applied: ``odds_checked_at_utc`` was
``never`` across all 1,003 fixtures, and zero were marked. Two causes, and Batch 119 found
the second:

* nobody had opened a card since the marker shipped, and
* every sweep that *did* run was degraded by the ``/odds/multi`` chunk defect, so
  ``observed`` was empty and ``record_observations`` correctly wrote nothing.

The consequence falls exactly where Batch 114 was written to defend. The **first** member
to open a card on a match morning pays the whole cold sweep — ``ceil(264 / 10) = 27``
requests against a 100/hour plan — in the hour everyone else is trying to pick, and every
member after them picks for free off what that one member bought.

This module is the same ``askable`` / ``fetch_odds_best_effort`` / ``record_observations``
loop the card runs, called from a job with no member waiting on it.

**The cost, stated rather than implied.** A brand-new round costs one full sweep wherever
it is paid. Warming it means paying that on the job *and* a cheaper priced-only sweep when
the first member arrives, so the daily total rises by roughly one sweep per new round.
What it buys is the removal of that spike from the hour before a lock. The daily cap has
the room and the hourly one does not, which is the whole reason the tiers are shaped as
they are. Steady state is cheaper still: the marker persists, and only the re-check cadence
re-pays.

**A degraded pass writes nothing**, on the same evidence rule the card uses. That is not a
detail — it is the rule that kept the marker honest through a week of failing sweeps, and
it is why a rate-limited warm pass costs the deployment nothing but the requests it already
spent.

*A known ambiguity, accepted deliberately.* ``record_observations`` writes nothing at all
for a fixture that was priced and still is — that is the steady state of every sweep, and
touching those rows would put hundreds of pointless updates behind every card load. The
cost is that "never swept" and "swept, everything priced" are indistinguishable in the
data, which cost real time in the Batch 119 investigation. Recording a sweep timestamp per
*round* would resolve it and needs a column, so it is deferred rather than taken here:
Batch 119 carries no migration by design, because a migration is irreversible in this
deployment and rollback is what makes its shipment safe. The ambiguity is bounded in the
meantime by this job — once it runs on a schedule, "never swept" stops being a state a
healthy deployment is ever in.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.services.gameweek import fixtures_for
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_pricing import askable, record_observations
from src.services.odds_provider import OddsProvider, OddsSnapshot

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def warm_round(
    db: AsyncSession,
    provider: OddsProvider,
    gameweek: Gameweek,
    now: datetime,
    *,
    recheck_seconds: float,
    max_age_seconds: float | None = None,
) -> int:
    """Sweep one round's askable fixtures and write what comes back. Returns rows changed.

    Identical in every respect to what a card load does, which is the point: a manual
    settlement produces the same rows as the scheduled path, and so should this. It flushes
    through the ORM and leaves the commit to the caller.

    Returns ``0`` without a request when the round has nothing askable — a round already
    learned inside its re-check window is a no-op, not a second sweep.
    """
    fixtures = await fixtures_for(db, gameweek.id)
    asked = askable(fixtures, now, recheck_seconds=recheck_seconds)
    if not asked:
        return 0

    event_ids = [fixture.provider_event_id for fixture in asked]
    if isinstance(provider, CachingOddsProvider):
        snapshot: OddsSnapshot = await provider.fetch_odds_best_effort(
            event_ids, max_age_seconds=max_age_seconds
        )
    else:
        # A provider with no cache in front cannot report what it observed, so nothing is
        # written. Warming is a *cache*-shaped operation; an uncached provider in a test
        # gets the no-op rather than a marker written on weaker evidence than the card's.
        log.debug("warm pass skipped: provider is not cached", fixtures=len(asked))
        return 0

    if snapshot.degraded and not snapshot.observed:
        log.warning("warm pass degraded, wrote nothing", gameweek_id=str(gameweek.id))
        return 0

    changed = record_observations(
        asked, snapshot.observed, {odds.provider_event_id for odds in snapshot.odds}, now
    )
    log.info(
        "odds marker warmed",
        gameweek_id=str(gameweek.id),
        fixtures=len(fixtures),
        asked=len(asked),
        observed=len(snapshot.observed),
        priced=len(snapshot.odds),
        marked=changed,
        degraded=snapshot.degraded,
    )
    return changed
