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

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.two_game import ProviderSnapshot, TwoGame, TwoGameFixture, TwoGameRollout
from src.services.gameweek import PICKABLE_STATES
from src.services.odds_provider import VOID_STATUSES


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
    #: Fresh completed new-format census progress is independent of row creation.
    hours_since_usable_discovery: float | None = None

    @property
    def stale(self) -> bool:
        """Whether legacy creation and usable new-format discovery have stopped.

        A deployment with **no rounds at all** is stale. That is not a degenerate case to
        guard away: a deployment whose discovery has never once succeeded is the worst
        version of exactly this fault, and reading it as healthy is how it stays hidden.
        """
        ages = [
            age
            for age in (self.hours_since_newest_round, self.hours_since_usable_discovery)
            if age is not None
        ]
        if not ages:
            return True
        return min(ages) >= self.stale_after_hours

    @property
    def silent_leagues(self) -> bool:
        return bool(self.leagues_without_open_round)

    @property
    def alarm(self) -> bool:
        """Either alarm. What the job logs on, and what the dashboard colours on."""
        return self.stale or self.silent_leagues


async def discovery_health(
    db: AsyncSession,
    now: datetime,
    *,
    stale_after_hours: float,
    provider_source: str | None = None,
) -> DiscoveryHealth:
    """Two legacy queries plus one enabled-only evidence query, no provider I/O.

    ``now`` is passed rather than taken so the caller's clock decides — the dashboard's,
    the job's, or a test's.
    """
    newest = (
        await db.execute(select(func.max(Gameweek.created_at)).where(Gameweek.format == "legacy"))
    ).scalar_one_or_none()
    from src.config import settings

    new_leagues: set[uuid.UUID] = set()
    usable_hours = None
    if settings.two_games_enabled:
        evidence = list(
            await db.execute(
                select(
                    TwoGame.league_id,
                    func.max(TwoGame.created_at),
                    func.max(ProviderSnapshot.observed_at),
                )
                .join(Gameweek, Gameweek.id == TwoGame.week_id)
                .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
                .join(League, League.id == TwoGame.league_id)
                .join(TwoGameFixture, TwoGameFixture.game_id == TwoGame.id)
                .join(Fixture, Fixture.id == TwoGameFixture.fixture_id)
                .join(ProviderSnapshot, ProviderSnapshot.fixture_id == TwoGameFixture.fixture_id)
                .where(
                    TwoGameRollout.enabled.is_(True),
                    TwoGameRollout.suspended.is_(False),
                    Gameweek.starts_on >= TwoGameRollout.first_week,
                    TwoGame.coverage_state == "complete",
                    TwoGame.locks_at > now,
                    TwoGame.status.in_(("scheduled", "open")),
                    League.deleted_at.is_(None),
                    ProviderSnapshot.key.like("fixture-state:v1:%"),
                    ProviderSnapshot.payload["source"].astext
                    == (provider_source or settings.odds_provider.value),
                    ProviderSnapshot.observed_at <= now,
                    or_(
                        and_(TwoGame.kind == "group", Fixture.kickoff_utc == TwoGame.window_start),
                        and_(
                            TwoGame.kind == "fantasy",
                            Fixture.kickoff_utc >= TwoGame.window_start,
                            Fixture.kickoff_utc < TwoGame.window_end,
                        ),
                    ),
                    func.lower(func.trim(ProviderSnapshot.payload["status"].astext)).notin_(
                        VOID_STATUSES
                    ),
                )
                .group_by(TwoGame.league_id)
            )
        )
        new_leagues = {row[0] for row in evidence}
        if evidence:
            newest = max([row[1] for row in evidence] + ([newest] if newest is not None else []))
            observed = max(row[2] for row in evidence)
            usable_hours = (now - observed).total_seconds() / 3600.0
    hours = None if newest is None else (now - newest).total_seconds() / 3600.0

    claimable = (
        select(Gameweek.league_id)
        .where(
            Gameweek.format == "legacy",
            Gameweek.status.in_(PICKABLE_STATES),
            Gameweek.locks_at_utc > now,
        )
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
                League.id.notin_(new_leagues),
            )
            .group_by(League.id, League.slug, League.name)
            .order_by(League.slug)
        )
    ).all()

    return DiscoveryHealth(
        newest_round_created_at=newest,
        hours_since_newest_round=hours,
        stale_after_hours=stale_after_hours,
        hours_since_usable_discovery=usable_hours,
        leagues_without_open_round=tuple(
            SilentLeague(league_id=league_id, slug=slug, name=name, members=members)
            for league_id, slug, name, members in rows
        ),
    )
