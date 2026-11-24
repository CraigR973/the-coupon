"""Explicit fantasy addresses; acquisition begins only inside an admitted save."""

import uuid

from fastapi import APIRouter, Request

from src.database import AsyncSessionLocal
from src.rate_limit import limiter, per_user_key
from src.routers.two_game_protocol import GameRoute, GameUser
from src.services.two_game_entry import RemovePick
from src.services.two_game_fantasy import (
    FantasyChoice,
    FantasyEntries,
    FantasyEntry,
    FantasyGameView,
)

router = APIRouter(prefix="/api/v1/leagues", tags=["fantasy game"], route_class=GameRoute)


def fantasy_entries() -> FantasyEntries:
    return FantasyEntries(AsyncSessionLocal)


@router.get("/{league_id}/weeks/{week_id}/games/fantasy", response_model=FantasyGameView)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_fantasy_game(
    request: Request, league_id: uuid.UUID, week_id: uuid.UUID, player: GameUser
) -> FantasyGameView:
    return await fantasy_entries().view(league_id, week_id, player.id)


@router.get("/{league_id}/weeks/{week_id}/games/fantasy/slots/{slot}", response_model=FantasyEntry)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_fantasy_slot(
    request: Request, league_id: uuid.UUID, week_id: uuid.UUID, slot: int, player: GameUser
) -> FantasyEntry:
    return await fantasy_entries().get_slot(league_id, week_id, player.id, slot)


@router.put("/{league_id}/weeks/{week_id}/games/fantasy/slots/{slot}", response_model=FantasyEntry)
async def put_fantasy_slot(
    request: Request,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    slot: int,
    body: FantasyChoice,
    player: GameUser,
) -> FantasyEntry:
    return await fantasy_entries().save(league_id, week_id, player.id, slot, body)


@router.delete(
    "/{league_id}/weeks/{week_id}/games/fantasy/slots/{slot}", response_model=FantasyEntry
)
async def delete_fantasy_slot(
    request: Request,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    slot: int,
    body: RemovePick,
    player: GameUser,
) -> FantasyEntry:
    """Batch 234: empty one of the caller's own slots; replayable by operation id."""
    return await fantasy_entries().remove(league_id, week_id, player.id, slot, body)
