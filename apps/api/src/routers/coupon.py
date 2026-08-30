"""League-wide read views derived from picks: the combined coupon and the standings.

* ``GET /api/v1/leagues/{slug}/coupon``    — everyone's picks for a gameweek stacked
  into one accumulator (legs + combined odds). Defaults to the latest; pass
  ``gameweek_id`` to read back through the season.
* ``GET /api/v1/leagues/{slug}/standings`` — the leaderboard for one season: the one
  being played, or a past one by ``?season=``.
* ``GET /api/v1/leagues/{slug}/seasons``   — which seasons this league has a table for,
  newest first. The index the archived tables are reached through.
* ``GET /api/v1/leagues/{slug}/results``   — every settled round, newest first, each
  with its winner, points and combined-coupon outcome.

All computed on demand from ``picks`` by :mod:`src.services.coupon` /
:mod:`src.services.scoring`.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import LeagueMemberDep
from src.services.coupon import Coupon, build_coupon
from src.services.gameweek import SeasonSummary, resolve_gameweek, seasons_played
from src.services.scoring import GameweekResult, Standing, gameweek_results, standings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["coupon"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{slug}/coupon", response_model=Coupon)
async def combined_coupon(
    slug: str, league: LeagueMemberDep, db: Db, gameweek_id: str | None = None
) -> Coupon:
    gameweek = await resolve_gameweek(db, league.id, gameweek_id)
    return await build_coupon(db, league.id, gameweek)


#: The seasons a request may ask for. Bounded because ``season_bounds`` builds a
#: ``date`` from the number and ``date(99999, 7, 1)`` is a ``ValueError`` — a 500 for
#: what is a malformed request, which is the shape Batch 57 spent itself correcting.
SeasonQuery = Annotated[int | None, Query(ge=2000, le=2100)]


@router.get("/{slug}/standings", response_model=list[Standing])
async def league_standings(
    slug: str, league: LeagueMemberDep, db: Db, season: SeasonQuery = None
) -> list[Standing]:
    """The season table. No ``season`` means the one being played, never all of them."""
    return await standings(db, league.id, season=season)


@router.get("/{slug}/seasons", response_model=list[SeasonSummary])
async def league_seasons(slug: str, league: LeagueMemberDep, db: Db) -> list[SeasonSummary]:
    """Which seasons have a table, newest first — always at least the current one."""
    return await seasons_played(db, league.id)


@router.get("/{slug}/results", response_model=list[GameweekResult])
async def league_results(slug: str, league: LeagueMemberDep, db: Db) -> list[GameweekResult]:
    return await gameweek_results(db, league.id)
