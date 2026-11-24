"""Unpriced group endpoints. Provider acquisition is intentionally absent."""

import uuid

from fastapi import APIRouter, Request

from src.database import AsyncSessionLocal
from src.rate_limit import limiter, per_user_key
from src.routers.two_game_protocol import GameRoute, GameUser
from src.services.two_game_entry import GroupChoice, RemovePick
from src.services.two_game_group import GroupEntries, GroupEntry, GroupGameView

router = APIRouter(prefix="/api/v1/leagues", tags=["group game"], route_class=GameRoute)


def group_entries() -> GroupEntries:
    return GroupEntries(AsyncSessionLocal)


@router.get("/{league_id}/weeks/{week_id}/games/group", response_model=GroupGameView)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_group_game(
    request: Request, league_id: uuid.UUID, week_id: uuid.UUID, player: GameUser
) -> GroupGameView:
    return await group_entries().view(league_id, week_id, player.id)


@router.get("/{league_id}/weeks/{week_id}/games/group/pick", response_model=GroupEntry)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_group_pick(
    request: Request, league_id: uuid.UUID, week_id: uuid.UUID, player: GameUser
) -> GroupEntry:
    return await group_entries().get_pick(league_id, week_id, player.id)


@router.put("/{league_id}/weeks/{week_id}/games/group/pick", response_model=GroupEntry)
async def put_group_pick(
    request: Request,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    body: GroupChoice,
    player: GameUser,
) -> GroupEntry:
    return await group_entries().save(league_id, week_id, player.id, body)


@router.delete("/{league_id}/weeks/{week_id}/games/group/pick", response_model=GroupEntry)
async def delete_group_pick(
    request: Request,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    body: RemovePick,
    player: GameUser,
) -> GroupEntry:
    """Batch 234: withdraw the caller's own contribution; replayable by operation id."""
    return await group_entries().remove(league_id, week_id, player.id, body)
