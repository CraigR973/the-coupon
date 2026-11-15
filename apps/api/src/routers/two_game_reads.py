"""All actionable targets and exact historical results, without provider acquisition."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from src.config import settings
from src.database import AsyncSessionLocal
from src.rate_limit import limiter, per_user_key
from src.routers.two_game_protocol import GameRoute, GameUser
from src.services.two_game_read_models import HomeGames, LeagueGames, WeekResults
from src.services.two_game_reads import GameReadRefused, GameReads

router = APIRouter(prefix="/api/v1", tags=["games"], route_class=GameRoute)


def game_reads() -> GameReads:
    return GameReads(AsyncSessionLocal, two_games_enabled=settings.two_games_enabled)


def refuse(error: GameReadRefused) -> HTTPException:
    return HTTPException(
        status_code=error.status,
        detail=dict(
            code=error.code,
            message="No accessible game target"
            if error.status == 404
            else "Check the requested history page",
        ),
    )


@router.get("/me/games", response_model=HomeGames)
@limiter.limit("120/minute", key_func=per_user_key)
async def home_games(
    request: Request, user: GameUser, season: Annotated[int | None, Query(ge=1, le=9998)] = None
) -> HomeGames:
    try:
        return await game_reads().read(user.id, season=season, page_size=5)
    except GameReadRefused as error:
        raise refuse(error) from error


@router.get("/leagues/{league_id}/games", response_model=LeagueGames)
@limiter.limit("120/minute", key_func=per_user_key)
async def league_games(
    request: Request,
    league_id: uuid.UUID,
    user: GameUser,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    season: Annotated[int | None, Query(ge=1, le=9998)] = None,
) -> LeagueGames:
    try:
        response = await game_reads().read(
            user.id, league_id=league_id, cursor=cursor, page_size=page_size, season=season
        )
        return response.leagues[0]
    except GameReadRefused as error:
        raise refuse(error) from error


@router.get("/leagues/{league_id}/weeks/{week_id}/results", response_model=WeekResults)
@limiter.limit("120/minute", key_func=per_user_key)
async def week_results(
    request: Request, league_id: uuid.UUID, week_id: uuid.UUID, user: GameUser
) -> WeekResults:
    try:
        return await game_reads().results(user.id, league_id, week_id)
    except GameReadRefused as error:
        raise refuse(error) from error
