"""Scores while a round is being played, and the two rules that bound them.

Batch 72, and the only item on the post-launch list that is an enhancement rather than a
defect. It is affordable because the source is already here: FotMob ships in production
for tables, results and form, **needs no key and has no rate limit to protect**, and
Batch 67 already built the fixture-to-match join a live score would be read through.
Nothing new is contracted and no budget is spent.

**Live scores are display only and must not touch settlement.** The odds provider settles
picks, in market and outcome terms, through :func:`~src.services.scoring.settle_gameweek`.
A second source that also moved ``Pick.status`` would be two authorities on one fact, and
the failure mode is a member watching points be awarded and then withdrawn. FotMob may say
what the score is; only ``EventSettlement`` says what a pick did. Nothing in this module
writes to ``picks``, and a test asserts it.

**Polling belongs on the scheduler, bounded to leagues with a round actually in play.**
Not on the request path — ``routers/football.py`` opens by describing that mistake, where
a read that could reach upstream is exhausted by one member refreshing. And not
unconditionally: a Tuesday morning has nothing being played, so a poll then is a request
nobody asked for against a source nobody is paying for. :func:`competitions_in_play` is
what makes the quiet case cost zero.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture
from src.services.football_data import sync_results
from src.services.football_provider import CompetitionKey, FootballDataProvider
from src.services.gameweek import in_play

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass
class LiveSweep:
    """What one poll did, in the terms the log line needs.

    ``rounds_in_play`` is on here rather than derived, because zero is the answer that
    matters: it is the difference between "polled and found nothing" and "did not poll",
    and only the first of those costs a request.
    """

    rounds_in_play: int = 0
    competitions: list[str] = field(default_factory=list)
    matches_updated: int = 0
    unavailable: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "rounds_in_play": self.rounds_in_play,
            "competitions": len(self.competitions),
            "matches_updated": self.matches_updated,
            "unavailable": len(self.unavailable),
        }


async def competitions_in_play(
    db: AsyncSession, now: datetime
) -> tuple[list[uuid.UUID], list[CompetitionKey]]:
    """The rounds being played right now, and the competitions their fixtures are in.

    "In play" is :func:`~src.services.gameweek.in_play` — Batch 65's definition, reused
    rather than restated: locked, not settled, and inside the grace measured from the
    close of the league's own window. That last clause is what stops a round the provider
    never resolves from making this poll run forever; without it, Batch 64's phantom
    Premiership round would have kept a competition being fetched every ten minutes for
    the rest of the season.

    An empty competition list is the ordinary answer — most hours of most weeks — and the
    caller must treat it as "make no request at all" rather than as "fetch nothing".
    """
    rounds = (await db.execute(select(Gameweek.id).where(in_play(now)))).scalars().all()
    if not rounds:
        return [], []
    rows = (
        await db.execute(
            select(Fixture.competition_id, Fixture.competition)
            .join(GameweekFixture, GameweekFixture.fixture_id == Fixture.id)
            .where(GameweekFixture.gameweek_id.in_(rounds), Fixture.competition_id != "")
            .distinct()
        )
    ).all()
    return list(rounds), [CompetitionKey(slug=slug, name=name) for slug, name in rows]


async def poll_live_scores(
    db: AsyncSession,
    provider: FootballDataProvider,
    *,
    season: int,
    now: datetime,
    limit: int,
) -> LiveSweep:
    """Refresh the running score for every competition an in-play round is drawing on.

    Writes through :func:`~src.services.football_data.sync_results`, the same function the
    daily sweep uses, so a live score and a final one land in ``matches`` by one path.
    ``finished`` stays false while a match is running, which keeps the partial score out
    of the results screen, the form line and Batch 67's settled scorelines — all three
    gate on it.

    A competition the source does not carry answers with an empty list rather than
    raising, and one whose request fails is recorded and skipped: the round renders
    without scores, which is the required degradation rather than a caveat.

    Flushes but does not commit — the caller owns the transaction.
    """
    sweep = LiveSweep()
    rounds, competitions = await competitions_in_play(db, now)
    sweep.rounds_in_play = len(rounds)
    if not competitions:
        return sweep

    for competition in competitions[:limit]:
        try:
            live = await provider.fetch_live_scores(competition, season)
        except Exception:  # noqa: BLE001 — one division must not cost the others theirs
            log.warning("live scores unavailable", competition=competition.slug, exc_info=True)
            sweep.unavailable.append(competition.slug)
            continue
        sweep.competitions.append(competition.slug)
        if live:
            sweep.matches_updated += await sync_results(db, live)
    return sweep
