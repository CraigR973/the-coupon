"""League-wide read views derived from picks: the combined coupon and the standings.

* ``GET /api/v1/leagues/{slug}/coupon``    — everyone's picks for the latest gameweek
  stacked into one accumulator (legs + combined odds).
* ``GET /api/v1/leagues/{slug}/standings`` — the season leaderboard.

Both are computed on demand from ``picks`` by :mod:`src.services.coupon` /
:mod:`src.services.scoring`.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import LeagueMemberDep
from src.services.coupon import Coupon, build_coupon
from src.services.gameweek import latest_gameweek
from src.services.scoring import Standing, standings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["coupon"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{slug}/coupon", response_model=Coupon)
async def combined_coupon(slug: str, league: LeagueMemberDep, db: Db) -> Coupon:
    gameweek = await latest_gameweek(db)
    if gameweek is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No gameweek yet")
    return await build_coupon(db, league.id, gameweek)


@router.get("/{slug}/standings", response_model=list[Standing])
async def league_standings(slug: str, league: LeagueMemberDep, db: Db) -> list[Standing]:
    return await standings(db, league.id)
