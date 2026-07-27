"""The weekly pick screen — this Saturday's slate with live odds and taken selections.

``GET /api/v1/leagues/{slug}/gameweek/current`` returns the latest gameweek's fixtures,
each with the currently-priced Betfair selections, marking which are already grabbed in
this leaderboard (and which is the caller's own). It's a read view; grabbing happens via
``POST .../picks``.
"""

from datetime import date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.deps import BetfairDep, LeagueMemberDep
from src.models.fixture import Fixture
from src.models.pick import Pick
from src.models.profile import Profile
from src.services.betfair import FixtureOdds
from src.services.gameweek import latest_gameweek

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["gameweek"])

Db = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ─────────────────────────────────────────────────────────────────────


class SelectionOption(BaseModel):
    market: str
    outcome: str
    runner_name: str
    odds: float
    taken_by_player_id: str | None  # who holds it in this league (None = available)
    taken_by_name: str | None
    mine: bool


class FixtureSlate(BaseModel):
    fixture_id: str
    betfair_event_id: str
    home: str
    away: str
    competition: str
    kickoff_utc: datetime
    selections: list[SelectionOption]


class GameweekSlateResponse(BaseModel):
    gameweek_id: str
    saturday_date: date
    status: str
    locks_at_utc: datetime
    fixtures: list[FixtureSlate]


@router.get("/{slug}/gameweek/current", response_model=GameweekSlateResponse)
async def current_gameweek(
    slug: str,
    player: CurrentUser,
    league: LeagueMemberDep,
    adapter: BetfairDep,
    db: Db,
) -> GameweekSlateResponse:
    gameweek = await latest_gameweek(db)
    if gameweek is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No gameweek yet")

    fixtures_result = await db.execute(
        select(Fixture)
        .where(Fixture.gameweek_id == gameweek.id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )
    fixtures = list(fixtures_result.scalars().all())

    taken = await _taken_selections(db, league.id, gameweek.id)
    odds_by_event = await _live_odds(adapter, [f.betfair_event_id for f in fixtures])

    slate = [
        FixtureSlate(
            fixture_id=str(fixture.id),
            betfair_event_id=fixture.betfair_event_id,
            home=fixture.home,
            away=fixture.away,
            competition=fixture.competition,
            kickoff_utc=fixture.kickoff_utc,
            selections=_selection_options(
                fixture, odds_by_event.get(fixture.betfair_event_id), taken, player.id
            ),
        )
        for fixture in fixtures
    ]
    return GameweekSlateResponse(
        gameweek_id=str(gameweek.id),
        saturday_date=gameweek.saturday_date,
        status=gameweek.status.value,
        locks_at_utc=gameweek.locks_at_utc,
        fixtures=slate,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

# key: (fixture_id, market_value, outcome_value) -> (player_id, player_name)
_TakenMap = dict[tuple[str, str, str], tuple[str, str]]


async def _taken_selections(db: AsyncSession, league_id: object, gameweek_id: object) -> _TakenMap:
    result = await db.execute(
        select(Pick, Profile.display_name)
        .join(Profile, Profile.id == Pick.player_id)
        .where(Pick.league_id == league_id, Pick.gameweek_id == gameweek_id)
    )
    taken: _TakenMap = {}
    for pick, display_name in result.all():
        key = (str(pick.fixture_id), pick.market.value, pick.outcome.value)
        taken[key] = (str(pick.player_id), display_name)
    return taken


async def _live_odds(adapter: BetfairDep, event_ids: list[str]) -> dict[str, FixtureOdds]:
    if not event_ids:
        return {}
    odds = await adapter.fetch_odds(event_ids)
    return {o.betfair_event_id: o for o in odds}


def _selection_options(
    fixture: Fixture,
    fixture_odds: FixtureOdds | None,
    taken: _TakenMap,
    my_id: object,
) -> list[SelectionOption]:
    if fixture_odds is None:
        return []
    options: list[SelectionOption] = []
    for selection in fixture_odds.selections:
        key = (str(fixture.id), selection.market.value, selection.outcome.value)
        holder = taken.get(key)
        options.append(
            SelectionOption(
                market=selection.market.value,
                outcome=selection.outcome.value,
                runner_name=selection.runner_name,
                odds=selection.back_price,
                taken_by_player_id=holder[0] if holder else None,
                taken_by_name=holder[1] if holder else None,
                mine=holder is not None and holder[0] == str(my_id),
            )
        )
    return options
