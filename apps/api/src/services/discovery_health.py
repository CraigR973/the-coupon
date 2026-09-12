"""Two reads that turn a silent scheduler into an alarm.

Batch 119. **No round was created by any scheduled job between 2026-09-04 20:21 and
2026-09-11** — a week in which 2-1 Hibs's twelve members had nothing to play and their
12 September round did not exist. The only thing that surfaced it was somebody going
looking.

Nothing on the admin dashboard could see it, and that is the actual defect; the arithmetic
that broke discovery is only its cause. The dashboard showed **stuck rounds** and
**scheduler state**, and both were healthy readings of a broken deployment: the scheduler
was running perfectly, firing `discover_fixtures` at 06:00 every morning, and every round
it held was in the past, so nothing was stuck.

The two reads here are what would have caught it, and each is one query against rows the
deployment already holds — no provider request, nothing to authenticate, safe on a
dashboard someone leaves open:

* :attr:`DiscoveryHealth.newest_round_created_at` — the newest round creation time across
  the whole deployment. A job that produces nothing for long enough is producing nothing.
* :attr:`DiscoveryHealth.leagues_without_open_round` — any league with members and no round
  they can still claim on. This is the fast one: it came true within hours of the
  5 September round locking, and would have fired on day one.

The first needs a generous threshold and the second needs none, and the reason is the
cadence. A round *row* appears when a new date enters the horizon, which on a weekly
cadence is about once a week per league however often discovery runs — so a day of silence
there is normal and a week is not. A league with members and nothing to play is wrong the
moment it is true.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.services.gameweek import PICKABLE_STATES


@dataclass(frozen=True)
class SilentLeague:
    """A league with members and nothing any of them can pick."""

    league_id: uuid.UUID
    slug: str
    name: str
    members: int


@dataclass(frozen=True)
class DiscoveryHealth:
    """What the deployment has produced lately, and who is going without.

    ``stale`` and ``silent_leagues`` are the two alarms. Both are *reads* — this type
    never writes, notifies or spends a request; it is the evidence, and what to do with it
    belongs to the dashboard and to the discovery job's own log line.
    """

    #: When the newest round in the deployment was created; ``None`` when there are none.
    newest_round_created_at: datetime | None
    #: Hours since that, or ``None`` when there are no rounds at all.
    hours_since_newest_round: float | None
    #: The threshold ``stale`` was decided against, so a reader need not guess.
    stale_after_hours: float
    #: Leagues with at least one member and no round still claimable.
    leagues_without_open_round: tuple[SilentLeague, ...]

    @property
    def stale(self) -> bool:
        """Whether round creation has stopped.

        A deployment with **no rounds at all** is stale. That is not a degenerate case to
        guard away: a deployment whose discovery has never once succeeded is the worst
        version of exactly this fault, and reading it as healthy is how it stays hidden.
        """
        if self.hours_since_newest_round is None:
            return True
        return self.hours_since_newest_round >= self.stale_after_hours

    @property
    def silent_leagues(self) -> bool:
        return bool(self.leagues_without_open_round)

    @property
    def alarm(self) -> bool:
        """Either alarm. What the job logs on, and what the dashboard colours on."""
        return self.stale or self.silent_leagues


async def discovery_health(
    db: AsyncSession, now: datetime, *, stale_after_hours: float
) -> DiscoveryHealth:
    """Take both reads. Two queries, no provider requests, no writes.

    ``now`` is passed rather than taken so the caller's clock decides — the dashboard's,
    the job's, or a test's.
    """
    newest = (await db.execute(select(func.max(Gameweek.created_at)))).scalar_one_or_none()
    hours = None if newest is None else (now - newest).total_seconds() / 3600.0

    claimable = (
        select(Gameweek.league_id)
        .where(Gameweek.status.in_(PICKABLE_STATES), Gameweek.locks_at_utc > now)
        .distinct()
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(
                League.id,
                League.slug,
                League.name,
                func.count(LeagueMembership.player_id).label("members"),
            )
            .join(LeagueMembership, LeagueMembership.league_id == League.id)
            .where(
                League.deleted_at.is_(None),
                LeagueMembership.deleted_at.is_(None),
                League.id.not_in(claimable),
            )
            .group_by(League.id, League.slug, League.name)
            .order_by(League.slug)
        )
    ).all()

    return DiscoveryHealth(
        newest_round_created_at=newest,
        hours_since_newest_round=hours,
        stale_after_hours=stale_after_hours,
        leagues_without_open_round=tuple(
            SilentLeague(league_id=league_id, slug=slug, name=name, members=members)
            for league_id, slug, name, members in rows
        ),
    )
