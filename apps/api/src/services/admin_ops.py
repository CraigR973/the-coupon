"""What an admin can trigger by hand, and what it costs to trigger it.

Batch 69. The value is measurable in work already done by hand: Batch 64 opened with a
Motherwell pick returned manually and twelve fixtures removed manually, and Batch 68 is a
backfill performed directly against the database. Every one of those is a screen that did
not exist.

Two rules shape this module.

**A manual trigger runs the same coroutine the scheduler runs.** Not a reimplementation of
it, not a variant with an extra argument — the exact callable, taken from the same registry
``src.run_scheduled`` exposes to an external cron. That is what makes "a manual settlement
produces the same rows as the scheduled path" true by construction rather than by test.

**A manual trigger spends a shared, rate-limited budget, and the screen has to say so.**
odds-api.io allows roughly 100 requests an hour across the whole deployment and the
scheduler's own jobs are sized against it, so an admin refreshing a slate by hand at 14:00
on a Saturday can 429 the refresh that matters — silently, because exhaustion looks exactly
like a quiet afternoon: picks stay pending and the week never finishes. Each job therefore
carries an estimate of what a run costs, and the ones that cost anything draw down the very
same bucket the ad-hoc slate fetch already uses.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.config import settings
from src.models.pick import PickMarket, PickOutcome
from src.run_scheduled import JOBS
from src.services.odds_provider import EventSettlement, Market, Outcome, OutcomeResult

#: One ``/events`` call per UK competition is what a single slate walk costs. Measured on
#: the launch Saturday, 2026-08-04: 131 qualifying 15:00 kick-offs across 30 UK
#: competitions. ``tests/test_request_budget.py`` holds the same figure and is where the
#: arithmetic against the 100/hour plan lives.
REQUESTS_PER_SLATE_WALK = 30


@dataclass(frozen=True)
class ManualJob:
    """One scheduled job an admin may run now, with the price of running it.

    ``provider_requests`` is an estimate of the upstream calls a run makes against
    odds-api.io's metered plan — ``0`` for a job that touches only the database, or only
    FotMob, which needs no key and has no rate limit to protect. It is shown on the button
    rather than discovered afterwards, because the cost of pressing it is exactly what an
    admin cannot see from the outcome.
    """

    key: str
    label: str
    summary: str
    provider_requests: int

    @property
    def spends_budget(self) -> bool:
        return self.provider_requests > 0

    @property
    def budget_units(self) -> int:
        """How many hits this job costs the shared provider bucket.

        The bucket is denominated in **slate walks**, because that is what the limit it
        shares was sized against: ``PROVIDER_SLATE_FETCH_LIMIT`` allows two an hour and an
        ad-hoc fetch is one walk of the thirty UK competitions. A job that costs two walks
        must therefore be charged twice, or the limit under-counts it — discovery at the
        default two-week horizon walks the card twice, and charging it once would let an
        admin spend sixty requests an hour against a bucket sized for thirty.

        Rounded up, so a job that costs less than a walk still costs something. Nothing
        upstream is free to ask for twice.
        """
        return math.ceil(self.provider_requests / REQUESTS_PER_SLATE_WALK)

    @property
    def run(self) -> Callable[[], Awaitable[bool]]:
        """The coroutine the scheduler and the cron entry point both call."""
        return JOBS[self.key]


def manual_jobs() -> tuple[ManualJob, ...]:
    """The jobs offered on the Sync screen, in the order they run in a normal week.

    Deliberately not every entry in :data:`~src.run_scheduled.JOBS`. ``backup`` is
    excluded because it writes a file to the container's disk and an admin pressing it
    from a phone has nowhere to put the result; ``football-backfill`` is excluded because
    it is a one-off whole-season pull that belongs behind a shell rather than a button.
    Both remain available to the cron entry point.

    Discovery's estimate scales with ``slate_horizon_weeks`` because it walks every
    cadence date in the horizon, where a refresh walks only the next one.
    """
    return (
        ManualJob(
            key="discover-fixtures",
            label="Discover fixtures",
            summary="Build every league's upcoming rounds from the odds provider.",
            provider_requests=REQUESTS_PER_SLATE_WALK * settings.slate_horizon_weeks,
        ),
        ManualJob(
            key="refresh-slate",
            label="Refresh this week's slate",
            summary="Top up the next round's card and prices before it locks.",
            provider_requests=REQUESTS_PER_SLATE_WALK,
        ),
        ManualJob(
            key="open",
            label="Open due rounds",
            summary="Flip any scheduled round whose announced opening has passed.",
            provider_requests=0,
        ),
        ManualJob(
            key="lock",
            label="Lock due rounds",
            summary="Flip any round past its deadline. Picks are already refused by then.",
            provider_requests=0,
        ),
        ManualJob(
            key="settle",
            label="Settle locked rounds",
            summary="Ask the odds provider for results and award points.",
            # One batched ``/odds`` call covers ten events, and the job asks only about
            # fixtures with a pick still pending — so a normal week is one or two calls
            # and a full 131-fixture card is fourteen. Costed at the worst case, because
            # an estimate that flatters the button is worse than no estimate.
            provider_requests=14,
        ),
        ManualJob(
            key="sync-football",
            label="Sync football data",
            summary="Refresh tables, results and form. Free — FotMob is unmetered.",
            provider_requests=0,
        ),
        ManualJob(
            key="remind",
            label="Send pick reminders",
            summary="Nudge members of any open round who still owe a pick.",
            provider_requests=0,
        ),
    )


def job_by_key(key: str) -> ManualJob | None:
    return next((job for job in manual_jobs() if job.key == key), None)


#: A scoreline decides both markets The Coupon offers, so an admin types a result rather
#: than a set of market/outcome verdicts. Anything derived here is derived once.
def settlement_from_score(
    provider_event_id: str, home_goals: int, away_goals: int
) -> EventSettlement:
    """Turn a final score into the settlement the scoring path already understands.

    The manual results screen exists because the odds provider sometimes never resolves a
    fixture — Batch 64's phantom Scottish Premiership round is exactly that — and the
    round then hangs unsettled forever. What it must **not** do is introduce a second way
    of scoring a pick: the value returned here goes into
    :func:`~src.services.scoring.settle_gameweek` unchanged, so a hand-entered result and
    a provider-supplied one write identical ``picks`` rows and award identical points.

    Both markets are marked settled, because a final score is a final answer to both. A
    score is not an opinion about only one of them.
    """
    match_winner = (
        Outcome.HOME
        if home_goals > away_goals
        else Outcome.AWAY
        if away_goals > home_goals
        else Outcome.DRAW
    )
    both_scored = home_goals > 0 and away_goals > 0
    outcomes = [
        OutcomeResult(market=Market.MATCH_ODDS, outcome=outcome, won=outcome == match_winner)
        for outcome in (Outcome.HOME, Outcome.DRAW, Outcome.AWAY)
    ] + [
        OutcomeResult(
            market=Market.BOTH_TEAMS_TO_SCORE,
            outcome=outcome,
            won=(outcome == Outcome.YES) == both_scored,
        )
        for outcome in (Outcome.YES, Outcome.NO)
    ]
    return EventSettlement(
        provider_event_id=provider_event_id,
        status="closed",
        settled=True,
        void=False,
        settled_markets=[Market.MATCH_ODDS, Market.BOTH_TEAMS_TO_SCORE],
        outcomes=outcomes,
    )


def voided_settlement(provider_event_id: str) -> EventSettlement:
    """A fixture that was never played: every pick on it scores nothing and loses nothing.

    The same shape :func:`~src.services.scoring.resolve_pick` already reads for a
    postponed or abandoned event, so a hand-voided fixture and a provider-voided one are
    indistinguishable in ``picks``.
    """
    return EventSettlement(
        provider_event_id=provider_event_id,
        status="postponed",
        settled=True,
        void=True,
    )


#: The markets a hand-entered score can decide, mirrored from the pick side so a league
#: offering a market this cannot settle would fail loudly at import rather than quietly at
#: settlement time.
assert {m.value for m in PickMarket} == {m.value for m in Market}
assert {o.value for o in PickOutcome} == {o.value for o in Outcome}
