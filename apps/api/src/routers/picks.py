"""Pick submission — the weekly land-grab.

``POST /api/v1/leagues/{slug}/picks`` submits (or, before lock, changes) the caller's one
pick for the gameweek. The endpoint snapshots the odds itself, so the frozen price is
authoritative rather than client-supplied, and it enforces both game rules:

* one pick per member per gameweek (a re-pick updates in place, freeing the old selection);
* no two members holding the same claim (first-come; a taken claim → 409).

How much a claim covers is the league's ``pick_scope``: one ``(fixture, market,
outcome)`` under the original ``selection`` rule, or the entire game under ``fixture``.
The refusal is ``SELECTION_TAKEN`` or ``FIXTURE_TAKEN`` accordingly.

The unique constraints on ``picks`` are the race backstop — a concurrent grab that slips
past the pre-check trips ``IntegrityError`` and is reported as a conflict.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.deps import LeagueMemberDep, OddsProviderDep
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League, PickScope
from src.models.pick import Pick, PickMarket, PickOutcome
from src.rate_limit import limiter, per_user_key
from src.services.gameweek import is_open_for_picks
from src.services.odds_provider import Selection

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["picks"])

Db = Annotated[AsyncSession, Depends(get_db)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── Schemas ─────────────────────────────────────────────────────────────────────


class SubmitPickRequest(BaseModel):
    fixture_id: str
    market: PickMarket
    outcome: PickOutcome


class PickResponse(BaseModel):
    id: str
    league_id: str
    gameweek_id: str
    fixture_id: str
    home: str
    away: str
    competition: str
    market: str
    outcome: str
    runner_name: str
    odds: float
    status: str
    points_awarded: int | None


def _to_response(pick: Pick, fixture: Fixture) -> PickResponse:
    return PickResponse(
        id=str(pick.id),
        league_id=str(pick.league_id),
        gameweek_id=str(pick.gameweek_id),
        fixture_id=str(fixture.id),
        home=fixture.home,
        away=fixture.away,
        competition=fixture.competition,
        market=pick.market.value,
        outcome=pick.outcome.value,
        runner_name=pick.runner_name,
        odds=float(pick.odds_at_pick),
        status=pick.status.value,
        points_awarded=pick.points_awarded,
    )


# ── Submit / change a pick ────────────────────────────────────────────────────


@router.post("/{slug}/picks", response_model=PickResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/hour", key_func=per_user_key)
async def submit_pick(
    request: Request,
    slug: str,
    body: SubmitPickRequest,
    player: CurrentUser,
    league: LeagueMemberDep,
    provider: OddsProviderDep,
    db: Db,
) -> PickResponse:
    fixture = await _resolve_fixture(body.fixture_id, db)
    gameweek = await db.get(Gameweek, fixture.gameweek_id)
    if gameweek is None:  # FK guarantees this, but keep mypy + runtime honest
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gameweek not found")
    if not is_open_for_picks(gameweek, _now()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PICKS_LOCKED")

    selection = await _snapshot_selection(provider, fixture, body.market, body.outcome)

    # Pre-check: has another member already claimed this? How much of the fixture a
    # claim covers is the league's choice — one selection, or the whole game.
    conflict_detail = await _claim_conflict(db, league, gameweek, fixture, body, player.id)
    if conflict_detail is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_detail)

    # One pick per member per gameweek: update in place if they already have one.
    existing = await db.execute(
        select(Pick).where(
            Pick.league_id == league.id,
            Pick.gameweek_id == gameweek.id,
            Pick.player_id == player.id,
        )
    )
    pick = existing.scalar_one_or_none()
    if pick is None:
        pick = Pick(league_id=league.id, gameweek_id=gameweek.id, player_id=player.id)
        db.add(pick)
    _apply_selection(pick, fixture, body, selection, league.pick_scope)

    try:
        await db.commit()
    except IntegrityError:
        # A concurrent grab won the claim (or the member's pick) between pre-check
        # and commit — the unique constraints are the source of truth.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_taken_detail(league))
    await db.refresh(pick)

    log.info(
        "pick submitted",
        league_id=str(league.id),
        gameweek_id=str(gameweek.id),
        player_id=str(player.id),
        selection=f"{body.market.value}:{body.outcome.value}",
    )
    return _to_response(pick, fixture)


# ── Read: my pick for a gameweek ──────────────────────────────────────────────


@router.get("/{slug}/gameweeks/{gameweek_id}/pick", response_model=PickResponse | None)
async def my_pick(
    slug: str,
    gameweek_id: str,
    player: CurrentUser,
    league: LeagueMemberDep,
    db: Db,
) -> PickResponse | None:
    result = await db.execute(
        select(Pick, Fixture)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.league_id == league.id,
            Pick.gameweek_id == gameweek_id,
            Pick.player_id == player.id,
        )
    )
    row = result.first()
    if row is None:
        return None
    pick, fixture = row
    return _to_response(pick, fixture)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _resolve_fixture(fixture_id: str, db: AsyncSession) -> Fixture:
    fixture = await db.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")
    return fixture


async def _snapshot_selection(
    provider: OddsProviderDep,
    fixture: Fixture,
    market: PickMarket,
    outcome: PickOutcome,
) -> Selection:
    """Fetch the fixture's odds and return the chosen priced selection.

    Enforces the *only offer what the provider prices* rule: an outcome that isn't
    currently offered (unpriced or missing) is rejected rather than stored at a stale
    price. The price may come from the provider's short-lived cache — bounded by
    ``ODDS_CACHE_TTL_SECONDS`` — which is the trade the provider's rate limit forces.
    """
    odds = await provider.fetch_odds([fixture.provider_event_id])
    for fixture_odds in odds:
        for selection in fixture_odds.selections:
            if selection.market.value == market.value and selection.outcome.value == outcome.value:
                return selection
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SELECTION_NOT_AVAILABLE"
    )


def _taken_detail(league: League) -> str:
    """The conflict code for a claim this league's rule refuses."""
    return "FIXTURE_TAKEN" if league.pick_scope is PickScope.fixture else "SELECTION_TAKEN"


async def _claim_conflict(
    db: AsyncSession,
    league: League,
    gameweek: Gameweek,
    fixture: Fixture,
    body: SubmitPickRequest,
    player_id: uuid.UUID,
) -> str | None:
    """The conflict code if another member already holds this claim, else ``None``.

    Under ``selection`` scope only the exact ``(fixture, market, outcome)`` is
    contested. Under ``fixture`` scope any pick on the game blocks, which is the
    whole point of the rule. The caller's own pick never conflicts with itself —
    a re-pick to the same claim is a no-op update, not a grab.
    """
    conditions = [
        Pick.league_id == league.id,
        Pick.gameweek_id == gameweek.id,
        Pick.fixture_id == fixture.id,
    ]
    if league.pick_scope is PickScope.selection:
        conditions += [Pick.market == body.market, Pick.outcome == body.outcome]

    result = await db.execute(select(Pick.player_id).where(*conditions))
    holders = set(result.scalars().all())
    if holders - {player_id}:
        return _taken_detail(league)
    return None


def _apply_selection(
    pick: Pick,
    fixture: Fixture,
    body: SubmitPickRequest,
    selection: Selection,
    scope: PickScope,
) -> None:
    """Write the frozen snapshot onto a new or re-picked row.

    ``(fixture, market, outcome)`` is the whole identity of a pick — the same key the
    league's uniqueness constraint uses and the one settlement resolves against — so no
    provider identifier is stored alongside it.

    ``scope`` is copied from the league because the fixture-level unique index is
    partial on this column: a PostgreSQL index predicate cannot join to ``leagues``.
    """
    pick.fixture_id = fixture.id
    pick.market = body.market
    pick.outcome = body.outcome
    pick.runner_name = selection.runner_name
    pick.odds_at_pick = selection.price
    pick.pick_scope = scope
