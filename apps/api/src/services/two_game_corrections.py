"""Shared manual truth, serialised across legacy and both independent games."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.two_game import FantasyPick, GroupPick, ProviderSnapshot
from src.services.odds_provider import EventSettlement
from src.services.scoring import resolve_pick, resolve_status
from src.services.two_game_results import recompute_game
from src.services.two_game_settlement import result_key, result_lock, settlement_locks


@dataclass
class Correction:
    checked: int = 0
    legacy: list[dict[str, Any]] = field(default_factory=list)
    fantasy: list[dict[str, Any]] = field(default_factory=list)
    group: list[dict[str, Any]] = field(default_factory=list)
    by_league: dict[tuple[uuid.UUID, str], list[dict[str, Any]]] = field(default_factory=dict)
    legacy_pick_ids: list[uuid.UUID] = field(default_factory=list)


class CorrectionScopeChanged(Exception):
    """A new affected league appeared while ordered locks were being acquired."""


async def correct_shared_fixture(
    db: AsyncSession, fixture_id: uuid.UUID, settlement: EventSettlement, now: datetime
) -> Correction:
    models: tuple[type[Pick] | type[GroupPick] | type[FantasyPick], ...] = (
        Pick,
        GroupPick,
        FantasyPick,
    )
    leagues: set[uuid.UUID] = set()
    for model in models:
        leagues |= set(
            await db.scalars(
                select(model.league_id)
                .join(League, League.id == model.league_id)
                .where(
                    model.fixture_id == fixture_id,
                    League.deleted_at.is_(None),
                )
            )
        )
    await settlement_locks(db, list(leagues))
    await result_lock(db, fixture_id)
    for model in models:
        current_leagues = set(
            await db.scalars(
                select(model.league_id)
                .join(League, League.id == model.league_id)
                .where(model.fixture_id == fixture_id, League.deleted_at.is_(None))
            )
        )
        if not current_leagues <= leagues:
            raise CorrectionScopeChanged
    result = Correction()
    games: set[uuid.UUID] = set()
    for model in models:
        rows = (
            await db.execute(
                select(model, League.slug)
                .join(League, League.id == model.league_id)
                .where(
                    model.fixture_id == fixture_id,
                    model.status != "pending",
                    League.deleted_at.is_(None),
                )
                .order_by(model.id)
                .with_for_update(of=model)
                .execution_options(populate_existing=True)
            )
        ).all()
        for pick, slug in rows:
            result.checked += 1
            prior_status = pick.status.value if isinstance(pick, Pick) else pick.status
            if isinstance(pick, GroupPick):
                verdict = resolve_status(
                    PickMarket(pick.market), PickOutcome(pick.outcome), settlement
                )
                if verdict is None or verdict.value == prior_status:
                    continue
                pick.status = verdict.value
                change = dict(
                    pick_id=str(pick.id),
                    league_slug=slug,
                    week_id=str(pick.week_id),
                    game_id=str(pick.game_id),
                    status_before=prior_status,
                    status=pick.status,
                )
                result.group.append(change)
                games.add(pick.game_id)
            else:
                odds = pick.odds_at_pick if isinstance(pick, Pick) else pick.frozen_odds
                resolution = resolve_pick(
                    PickMarket(pick.market), PickOutcome(pick.outcome), odds, settlement
                )
                if resolution is None or (resolution.status.value, resolution.points) == (
                    prior_status,
                    pick.points_awarded,
                ):
                    continue
                before_points = pick.points_awarded
                pick.status = (
                    resolution.status if isinstance(pick, Pick) else resolution.status.value
                )
                pick.points_awarded = resolution.points
                change = dict(
                    pick_id=str(pick.id),
                    league_slug=slug,
                    status_before=prior_status,
                    points_before=before_points,
                    status=resolution.status.value,
                    points=resolution.points,
                )
                if isinstance(pick, Pick):
                    result.legacy.append(change)
                    result.legacy_pick_ids.append(pick.id)
                else:
                    change.update(
                        week_id=str(pick.week_id), game_id=str(pick.game_id), slot=pick.slot
                    )
                    result.fantasy.append(change)
                    games.add(pick.game_id)
            result.by_league.setdefault((pick.league_id, slug), []).append(change)
    # Shared fixture input alone becomes global manual truth. Identical repeated
    # input advances only when canonical truth or a resolved claim actually changes.
    state = await db.get(ProviderSnapshot, result_key(fixture_id), populate_existing=True)
    payload = dict(state.payload) if state else {}
    entered = settlement.model_dump(mode="json")
    if result.checked and (
        payload.get("authority") != "manual"
        or payload.get("settlement") != entered
        or bool(result.by_league)
    ):
        payload.update(
            authority="manual", settlement=entered, generation=int(payload.get("generation", 0)) + 1
        )
        if state is None:
            db.add(
                ProviderSnapshot(
                    key=result_key(fixture_id),
                    fixture_id=fixture_id,
                    payload=payload,
                    observed_at=now,
                    expires_at=datetime.max,
                )
            )
        else:
            state.payload, state.observed_at = payload, now
    await db.flush()
    for game_id in sorted(games):
        await recompute_game(db, game_id, now)
    # Stage legacy correction text after its rows are updated, using the existing
    # recipient/copy policy. Delivery is handled after the caller's commit.
    if result.legacy_pick_ids:
        from src.services.two_game_events import stage_legacy_corrections

        await stage_legacy_corrections(db, result.legacy_pick_ids, now, int(payload["generation"]))
    return result
