"""Reach a played match's scoreline from a coupon leg.

Batch 67. A member looking at a round that has been played wants the *result*, and the
scoreline is the one thing the product never had to hand: ``fixtures`` carries
``provider_event_id``, ``home``, ``away``, ``kickoff_utc`` and the competition, and **no
goals of any kind**. The odds provider settles in market and outcome terms —
``EventSettlement`` has ``settled_markets`` and ``outcomes``, no scores — so a won leg
knows it won and not by what.

Scores live on ``matches``, on the football-data side, keyed by ``teams`` rows rather than
by the fixture's free-text names. The two records are deliberately not joined by a foreign
key (see :class:`~src.models.match.Match`): the providers' event ids share no namespace,
and a fixture postponed out of its window still becomes a match when it is eventually
played. So the only route from a leg to a scoreline is the name-based one, through
:mod:`src.services.team_matching`'s pair rule — the same tool Batch 64 built for the
FotMob slate cross-check.

**A wrong join prints a false scoreline against a real member's pick.** So this fails to
*no score shown* rather than to a guess, exactly as Batch 64 fails open: both ends of the
fixture must clear :data:`~src.services.team_matching.PAIR_THRESHOLD`, the date chooses
between candidates rather than the name score, and anything still ambiguous resolves to
nothing.

**Resolved per read; the link is not persisted.** Recorded here because it was the batch's
one real design decision. Persisting would add a column and a backfill and make the answer
stable, at the cost of a migration against a database with no restore point; resolving
costs one extra query on a screen nobody hammers — the coupon is read a handful of times a
week per league, not per request. It also means a *corrected* alias row takes effect on the
next read rather than needing the stored link rebuilt, which matters because the alias
layer is the thing most likely to need correcting. If Batch 72's live scores make this hot,
the shape to reach for is a cache in front of it, not a column.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.models.fixture import Fixture
from src.models.match import Match
from src.models.team import Team
from src.services.odds_provider import UK_TZ
from src.services.team_matching import PAIR_THRESHOLD, pair_score

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: How far either side of a fixture's own kick-off a candidate match may sit.
#:
#: Wide enough to survive the ordinary reasons the two records disagree about *when* —
#: a kick-off moved for television, a provider storing local time, a Friday-night game
#: whose UK date differs from the round's — and narrow enough that a league's home-and-away
#: pair, which matches both ends by name just as well, is never in the same window.
CANDIDATE_WINDOW = timedelta(days=3)


class Scoreline(BaseModel):
    """A played match's final score, as the coupon shows it."""

    home_goals: int
    away_goals: int


def _uk_date(moment: datetime) -> date:
    """A stored naive-UTC kick-off as the UK calendar date a member would call it.

    The two records store the same instant, but a 20:00 UTC Friday kick-off is Friday in
    London and a 23:30 one is Saturday, so comparing raw dates would separate matches the
    member thinks of as the same night.
    """
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    return aware.astimezone(UK_TZ).date()


async def scorelines_for(
    db: AsyncSession, fixtures: Sequence[Fixture]
) -> dict[uuid.UUID, Scoreline]:
    """The final score for each fixture that can be resolved to a finished match.

    Keyed by ``fixtures.id``. A fixture that resolves to nothing — a competition the
    football source does not carry, a club whose name will not match, two candidates the
    date cannot separate — is simply **absent**, and every caller must render that as no
    score rather than as a zero or an error.

    One query per competition rather than one per fixture: a coupon is fifteen legs
    across a handful of divisions, and the candidate pool for a division is small once
    bounded by :data:`CANDIDATE_WINDOW`.

    Only ``finished`` matches count. An in-play match carries a partial score, and
    printing a running scoreline against a *settled* pick would say the round is still
    moving when it is over. Live scores are Batch 72 and read a different gate.
    """
    if not fixtures:
        return {}

    by_competition: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.competition_id:
            by_competition[fixture.competition_id].append(fixture)

    home_team = aliased(Team)
    away_team = aliased(Team)
    resolved: dict[uuid.UUID, Scoreline] = {}
    unresolved = 0

    for competition_id, group in by_competition.items():
        kickoffs = [f.kickoff_utc for f in group]
        rows = (
            await db.execute(
                select(Match, home_team.name, away_team.name)
                .join(home_team, home_team.id == Match.home_team_id)
                .join(away_team, away_team.id == Match.away_team_id)
                .where(
                    Match.competition_id == competition_id,
                    Match.finished.is_(True),
                    Match.home_goals.is_not(None),
                    Match.away_goals.is_not(None),
                    Match.kickoff_utc >= min(kickoffs) - CANDIDATE_WINDOW,
                    Match.kickoff_utc <= max(kickoffs) + CANDIDATE_WINDOW,
                )
            )
        ).all()
        candidates = [(match, home, away) for match, home, away in rows]
        if not candidates:
            unresolved += len(group)
            continue

        for fixture in group:
            scoreline = _resolve(fixture, candidates)
            if scoreline is None:
                unresolved += 1
            else:
                resolved[fixture.id] = scoreline

    if unresolved:
        log.info(
            "scorelines unresolved",
            resolved=len(resolved),
            unresolved=unresolved,
            fixtures=len(fixtures),
        )
    return resolved


def _resolve(fixture: Fixture, rows: Sequence[tuple[Match, str, str]]) -> Scoreline | None:
    """The one finished match this fixture means, or ``None`` when that is not certain.

    Name first, then date — never the other way round, and never name score alone. A
    home-and-away pair inside one season matches both ends equally well, so picking the
    *best* name score would be picking arbitrarily between two correct-looking answers;
    the date is what tells them apart. Batch 64 learned the same lesson in the opposite
    direction, where choosing by name compared the card against a fixture six months away.
    """
    named = [
        (match, home, away)
        for match, home, away in rows
        if pair_score(fixture.home, fixture.away, home, away) >= PAIR_THRESHOLD
    ]
    if not named:
        return None

    wanted = _uk_date(fixture.kickoff_utc)
    same_day = [row for row in named if _uk_date(row[0].kickoff_utc) == wanted]
    # Falling back to the whole named set is what lets a game moved by a day still show
    # its score — the query already bounds those to :data:`CANDIDATE_WINDOW`, which is
    # narrower than any league's home-and-away gap.
    candidates = same_day or named
    if len(candidates) > 1:
        # Two matches this fixture could equally be. Batch 64's rule: an ambiguous
        # answer is worse than none, because the wrong one is indistinguishable from
        # the right one to the member reading it.
        log.info(
            "scoreline ambiguous",
            fixture=f"{fixture.home} v {fixture.away}",
            candidates=len(candidates),
        )
        return None

    match = candidates[0][0]
    if match.home_goals is None or match.away_goals is None:
        return None
    return Scoreline(home_goals=match.home_goals, away_goals=match.away_goals)
