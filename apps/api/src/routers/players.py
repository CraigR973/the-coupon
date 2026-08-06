"""A member's record within one leaderboard.

``GET /api/v1/leagues/{slug}/players/{player_id}/profile`` returns their season
figures and the picks behind them.

**Per-league, deliberately.** Picks are league-scoped — a member in three leagues has
three records — so a career-wide profile would have to either sum leagues with
different rules (Batch 10 made the claim rule per-league) or pick one arbitrarily.
Framing the profile the way the data is framed keeps it honest, and the league
switcher is already how a member moves between their records.

Nothing here is new information: standings already publish every member's totals to
the league, and the combined coupon already names who holds which selection. This
assembles both around one person.
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import LeagueMemberDep
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.services.scoring import standings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["players"])

Db = Annotated[AsyncSession, Depends(get_db)]

# A settled pick is one the season table counts: won, lost, or void.
_SETTLED = (PickStatus.won, PickStatus.lost, PickStatus.void)


class SettledPick(BaseModel):
    """One resolved pick — a row of the member's history."""

    gameweek_id: str
    starts_on: str
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


class PlayerProfile(BaseModel):
    player_id: str
    display_name: str
    # Season figures, taken from the same computation the leaderboard displays so
    # the two can never disagree.
    total_points: int
    picks_played: int
    picks_won: int
    rank: int
    # Wins as a percentage of settled picks, rounded to a whole number. `None`
    # rather than 0 when nothing has settled — an untested record is not a bad one.
    win_rate_pct: int | None
    history: list[SettledPick]


@router.get("/{slug}/players/{player_id}/profile", response_model=PlayerProfile)
async def player_profile(
    slug: str,
    player_id: str,
    league: LeagueMemberDep,
    db: Db,
) -> PlayerProfile:
    """One member's record in this league: season figures plus every settled pick."""
    try:
        target = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    membership = await db.execute(
        select(LeagueMembership.id).where(
            LeagueMembership.league_id == league.id,
            LeagueMembership.player_id == target,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player is not in this league"
        )

    table = await standings(db, league.id)
    row = next((s for s in table if s.player_id == str(target)), None)
    if row is None:  # a member with a standings row is guaranteed by the check above
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    return PlayerProfile(
        player_id=row.player_id,
        display_name=row.display_name,
        total_points=row.total_points,
        picks_played=row.picks_played,
        picks_won=row.picks_won,
        rank=row.rank,
        win_rate_pct=(round(100 * row.picks_won / row.picks_played) if row.picks_played else None),
        history=await _settled_history(db, league.id, target),
    )


async def _settled_history(
    db: AsyncSession, league_id: uuid.UUID, player_id: uuid.UUID
) -> list[SettledPick]:
    """Every resolved pick this member has made in this league, newest first.

    Pending picks are excluded: before a gameweek settles, a member's pick is
    already visible on the coupon, and listing it here would be a second, worse
    copy of that view.
    """
    rows = await db.execute(
        select(Pick, Fixture, Gameweek)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .join(Gameweek, Gameweek.id == Pick.gameweek_id)
        .where(
            Pick.league_id == league_id,
            Pick.player_id == player_id,
            Pick.status.in_(_SETTLED),
        )
        .order_by(Gameweek.starts_on.desc(), Fixture.kickoff_utc)
    )
    return [
        SettledPick(
            gameweek_id=str(gameweek.id),
            starts_on=gameweek.starts_on.isoformat(),
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
        for pick, fixture, gameweek in rows.all()
    ]
