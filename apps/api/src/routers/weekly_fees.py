"""Explicit week fee projection; browsing never materialises future charges."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.models.gameweek import Gameweek
from src.models.league import League
from src.rate_limit import limiter, per_user_key
from src.routers.two_game_protocol import GameRoute
from src.services.provider_budget import utc_now
from src.services.weekly_fees import (
    WeekFee,
    _active_membership,
    _rollout,
    financial_lock,
    project_fees,
)

router = APIRouter(prefix="/api/v1/leagues", tags=["weekly fees"], route_class=GameRoute)


@router.get("/{league_id}/weeks/{week_id}/fee", response_model=WeekFee)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_week_fee(
    request: Request,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeekFee:
    if await _active_membership(db, league_id, player.id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No accessible weekly fee target"},
        )
    # Deletion/roster/billing use this same lock. Resolve fresh access facts after
    # waiting, then keep the projection consistent through the request transaction.
    await financial_lock(db, league_id)
    rollout = await _rollout(db, league_id)
    week = await db.get(Gameweek, week_id, populate_existing=True)
    if (
        rollout is None
        or week is None
        or week.league_id != league_id
        or await _active_membership(db, league_id, player.id) is None
    ):
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No accessible weekly fee target"},
        )
    league = await db.get(League, league_id, populate_existing=True)
    if league is None or league.deleted_at is not None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No accessible weekly fee target"},
        )
    if week.format != "two_game":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": "This week uses the legacy coupon",
                "week_id": str(week_id),
                "destination": f"/leagues/{league.slug}/predictions?gw={week_id}#coupon",
            },
        )
    if week.starts_on < rollout.first_week:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "No accessible weekly fee target"},
        )
    return (await project_fees(db, league, player.id, week.starts_on, utc_now())).for_week(week)
