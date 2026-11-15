"""Independent game outcomes and versioned facts; no provider or notification I/O."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.two_game import FantasyPick, GroupPick, ProviderSnapshot, TwoGame, TwoGameEvent


def group_outcome(statuses: Sequence[str]) -> str:
    if not statuses:
        return "no_coupon"
    if "pending" in statuses:
        return "pending"
    if "lost" in statuses:
        return "lost"
    return "void" if all(value == "void" for value in statuses) else "won"


def fantasy_entry_status(statuses: Sequence[str]) -> str:
    return (
        "no_entry"
        if not statuses
        else "pending"
        if "pending" in statuses
        else "all_void"
        if all(value == "void" for value in statuses)
        else "scored"
    )


def fantasy_outcome(picks: Sequence[FantasyPick]) -> dict[str, Any]:
    statuses = [pick.status for pick in picks]
    result = fantasy_entry_status(statuses)
    return dict(
        entered=bool(picks),
        slots_filled=len(picks),
        entry_result=result,
        weekly_points=sum(pick.points_awarded or 0 for pick in picks),
        pending=sum(value == "pending" for value in statuses),
        won=sum(value == "won" for value in statuses),
        lost=sum(value == "lost" for value in statuses),
        void=sum(value == "void" for value in statuses),
    )


def weekly_winner_ids(members: Sequence[dict[str, Any]]) -> list[str]:
    """Final scored entries compete as a weekly sum; absent/all-void entries do not."""
    eligible = [member for member in members if member["entry_result"] == "scored"]
    if not eligible:
        return []
    highest = max(member["weekly_points"] for member in eligible)
    return sorted(member["player_id"] for member in eligible if member["weekly_points"] == highest)


async def recompute_game(db: AsyncSession, game_id: uuid.UUID, now: datetime) -> bool:
    """Caller holds the league lock; persist a semantic change and its final fact."""
    game = await db.scalar(
        select(TwoGame)
        .where(TwoGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None:
        return False
    payload: dict[str, Any]
    if game.kind == "group":
        group = list(
            await db.scalars(
                select(GroupPick).where(GroupPick.game_id == game.id).order_by(GroupPick.id)
            )
        )
        state = group_outcome([pick.status for pick in group])
        pending = any(pick.status == "pending" for pick in group)
        payload = dict(
            status=state,
            legs=[
                dict(pick_id=str(pick.id), player_id=str(pick.player_id), status=pick.status)
                for pick in group
            ],
        )
        boundary = game.window_start
    else:
        fantasy = list(
            await db.scalars(
                select(FantasyPick)
                .where(FantasyPick.game_id == game.id)
                .order_by(FantasyPick.player_id, FantasyPick.slot)
            )
        )
        owners = sorted({pick.player_id for pick in fantasy})
        members = [
            dict(
                player_id=str(owner),
                **fantasy_outcome([pick for pick in fantasy if pick.player_id == owner]),
            )
            for owner in owners
        ]
        pending = any(pick.status == "pending" for pick in fantasy)
        state = (
            "pending"
            if pending
            else "no_entry"
            if not fantasy
            else "all_void"
            if all(pick.status == "void" for pick in fantasy)
            else "scored"
        )
        payload = dict(
            status=state,
            members=members,
            legs=[
                dict(
                    pick_id=str(pick.id),
                    player_id=str(pick.player_id),
                    slot=pick.slot,
                    status=pick.status,
                    points=pick.points_awarded,
                )
                for pick in fantasy
            ],
        )
        boundary = game.window_end
    final = now >= boundary and not pending
    if game.kind == "fantasy":
        payload["winner_ids"] = weekly_winner_ids(payload["members"]) if final else []
    semantic = dict(**payload, final=final)
    signature = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    key = f"game-result:v1:{game.id}"
    previous = await db.get(ProviderSnapshot, key, populate_existing=True)
    if previous is not None and previous.payload.get("signature") == signature:
        if not final and now >= game.locks_at and game.status != "cancelled":
            game.status = "locked"
        return False
    was_final = game.finalized_at is not None
    game.result_status = state
    game.result_version += 1
    if game.status != "cancelled":
        game.status = "settled" if final else "locked" if now >= game.locks_at else game.status
    if final and game.finalized_at is None:
        game.finalized_at = now
    values = dict(signature=signature, **semantic)
    if previous is None:
        db.add(ProviderSnapshot(key=key, payload=values, observed_at=now, expires_at=datetime.max))
    else:
        previous.payload, previous.observed_at = values, now
    if final:
        db.add(
            TwoGameEvent(
                game_id=game.id,
                league_id=game.league_id,
                week_id=game.week_id,
                game_kind=game.kind,
                kind="game_corrected" if was_final else "game_result",
                version=game.result_version,
                payload=dict(**semantic, result_version=game.result_version),
            )
        )
    await db.flush()
    children = list(await db.scalars(select(TwoGame).where(TwoGame.week_id == game.week_id)))
    if len(children) == 2 and all(child.finalized_at is not None for child in children):
        parent = await db.get(Gameweek, game.week_id)
        if parent is not None and parent.status != GameweekStatus.settled:
            parent.status, parent.settled_at = GameweekStatus.settled, now
    return True
