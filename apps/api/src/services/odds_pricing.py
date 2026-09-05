"""What the deployment has learned about which fixtures a bookmaker prices.

Batch 114, from a live outage. Members were refused with ``ODDS_UNAVAILABLE`` on the
morning of a match day, on a round whose lock was still five hours away, because the free
plan's 100 requests/hour was gone by 08:06. The round held **202 fixtures, 103 of them the
FA Cup qualifying round** — non-league ties from AFC Portchester down — and the sweep log
read ``fixtures=202 priced=99``. Bet365 priced not one of the 103. They cost 11 of the 21
requests in every sweep, and every one of them rendered on the card as a row no member
could ever pick.

Two rules live here, and the difference between them is the whole point of the module:

* :func:`askable` decides what a sweep *spends a request on*. A fixture the deployment has
  observed to be unpriced is left out until its re-check falls due, which is what takes
  those 103 out of the hourly bill.
* :func:`pickable` decides what the card *shows*. It reads the stored marker and **never**
  this request's fetch result — a provider we cannot reach is not evidence that a fixture
  has no price, and filtering on a failed sweep would blank the whole card exactly when it
  is least affordable.

:func:`record_observations` is the only thing that writes the marker, and it takes the
evidence explicitly (``observed``) rather than inferring it from what came back, so a
degraded sweep, a cached answer and a browse withheld to protect the pick reserve cannot
mark anything.

Two floors keep the filter honest, and both are here rather than at the call site because
they are properties of the rule and not of one screen:

* a fixture that becomes priceable reappears on the next re-check — the marker is bounded
  by ``ODDS_UNPRICED_RECHECK_SECONDS``, never permanent;
* a filter that would empty a round which has fixtures shows them unfiltered instead. An
  empty card is a worse answer than an honest one.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime, timedelta

import structlog

from src.models.fixture import Fixture

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def is_unpriced(fixture: Fixture) -> bool:
    """Whether the deployment has observed the bookmaker pricing nothing on this fixture."""
    return fixture.odds_unpriced_since_utc is not None


def askable(fixtures: Sequence[Fixture], now: datetime, *, recheck_seconds: float) -> list[Fixture]:
    """The fixtures worth spending a request on this sweep.

    Everything the deployment has not marked, plus any marked one whose re-check has come
    due. The second half is what stops the saving from becoming a trap: a bookmaker that
    opens a market on the morning of a match — which is exactly what happens to a cup tie
    once it draws a Premier League side — is found within ``recheck_seconds`` and the row
    comes back onto the card.

    A marked fixture with no ``odds_checked_at_utc`` is asked about immediately. That pair
    cannot occur through :func:`record_observations`, which always writes both; it is what
    a hand-edited row or a future backfill would leave, and asking is the safe reading.
    """
    due = now - timedelta(seconds=recheck_seconds)
    return [
        fixture
        for fixture in fixtures
        if not is_unpriced(fixture)
        or fixture.odds_checked_at_utc is None
        or fixture.odds_checked_at_utc <= due
    ]


def pickable(fixtures: Sequence[Fixture], *, claimed: Collection[str] = ()) -> list[Fixture]:
    """The fixtures the card should show, by the stored marker alone.

    ``claimed`` is the ids of fixtures somebody in this league already holds a pick on, and
    they are shown whatever the marker says. A bookmaker may withdraw a market hours after
    a member claimed it — the price is frozen on the pick and the claim stands — and a card
    that hid it would take a member's own selection off the screen they made it on, and
    take a rival's claim out of the land-grab everyone else is reading.

    Never returns an empty list for a round that has fixtures. A round whose every fixture
    is unpriced is a real state — a card drawn entirely from a qualifying round, or a
    marker written against a bookmaker that has since opened every market — and showing
    those fixtures unpriced tells a member what is happening. Showing nothing tells them
    the round is broken.
    """
    shown = [
        fixture for fixture in fixtures if not is_unpriced(fixture) or str(fixture.id) in claimed
    ]
    if fixtures and not shown:
        log.info("round is entirely unpriced, showing it unfiltered", fixtures=len(fixtures))
        return list(fixtures)
    return shown


def record_observations(
    fixtures: Sequence[Fixture],
    observed: Collection[str],
    priced: Collection[str],
    now: datetime,
) -> int:
    """Write what a sweep that actually reached the provider learned. Returns rows changed.

    ``observed`` is the set of provider event ids this sweep put a question to the provider
    about and got a definite answer for — :attr:`~src.services.odds_provider.OddsSnapshot.observed`.
    Anything outside it is left exactly as it was, which is what makes a degraded sweep,
    a cached answer, and a browse withheld for the pick reserve all no-ops here.

    ``priced`` is the subset that came back with selections. Present clears the marker;
    absent sets it. ``odds_checked_at_utc`` moves whenever the marker is involved — set,
    cleared, or confirmed — because it bounds the re-check rather than recording a
    verdict: a fixture that is still unpriced has been re-checked just as much as one that
    turned out priced.

    A fixture that was priced and still is writes **nothing**. That is the steady state of
    every sweep — 99 of the 202 on the round that prompted this batch — and touching those
    rows would put a couple of hundred pointless updates behind every card load.

    Mutates the ORM rows in place; the caller owns the transaction.
    """
    changed = 0
    for fixture in fixtures:
        if fixture.provider_event_id not in observed:
            continue
        was_unpriced = is_unpriced(fixture)
        if fixture.provider_event_id in priced:
            if not was_unpriced:
                continue
            fixture.odds_unpriced_since_utc = None
        elif not was_unpriced:
            # First observation of an absence. `since` is when the deployment learned it,
            # not when the bookmaker decided — nothing tells us the latter.
            fixture.odds_unpriced_since_utc = now
        fixture.odds_checked_at_utc = now
        changed += 1
    return changed
