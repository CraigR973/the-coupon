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
from sqlalchemy import String, cast, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.deps import LeagueMemberDep
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.models.two_game import FantasyPick
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
    format: str = "legacy"
    game_kind: str = "legacy"
    game_id: str | None = None
    slot: int | None = None
    destination: str | None = None
    frozen_odds: str | None = None


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
    # Batch 70's pick-shape figures, taken from the same `Standing` the leaderboard
    # renders. Optional with defaults, because the web app deploys ahead of the API.
    picks_priced: int = 0
    cumulative_odds: float = 0.0
    average_odds: float | None = None
    points_per_pick: float | None = None
    best_return: int | None = None
    longshot_picks: int = 0
    favourite_picks: int = 0
    longshot_odds: float = 3.0
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
        # Read off the row rather than recomputed here. It used to be recomputed, which
        # is how a profile and a leaderboard end up a rounding step apart.
        win_rate_pct=row.win_rate_pct,
        picks_priced=row.picks_priced,
        cumulative_odds=row.cumulative_odds,
        average_odds=row.average_odds,
        points_per_pick=row.points_per_pick,
        best_return=row.best_return,
        longshot_picks=row.longshot_picks,
        favourite_picks=row.favourite_picks,
        longshot_odds=row.longshot_odds,
        history=await _settled_history(db, league.id, target, league.slug),
    )


async def _settled_history(
    db: AsyncSession, league_id: uuid.UUID, player_id: uuid.UUID, slug: str
) -> list[SettledPick]:
    """Resolved legs behind the mixed totals, including partially resolved Fantasy weeks.

    Legacy history keeps its existing all-season scope and fields. Group has no
    priced/scoring history. A leg need not wait for the whole Fantasy week to finalise.
    """
    legacy = select(
        Pick.gameweek_id,
        Pick.fixture_id,
        cast(Pick.market, String).label("market"),
        cast(Pick.outcome, String).label("outcome"),
        Pick.runner_name,
        Pick.odds_at_pick.label("odds"),
        cast(Pick.status, String).label("status"),
        Pick.points_awarded,
        literal("legacy").label("format"),
        literal(None).label("game_id"),
        literal(None).label("slot"),
    ).where(
        Pick.league_id == league_id,
        Pick.player_id == player_id,
        Pick.status.in_(_SETTLED),
    )
    fantasy = select(
        FantasyPick.week_id.label("gameweek_id"),
        FantasyPick.fixture_id,
        FantasyPick.market,
        FantasyPick.outcome,
        FantasyPick.runner_name,
        FantasyPick.frozen_odds.label("odds"),
        FantasyPick.status,
        FantasyPick.points_awarded,
        literal("two_game").label("format"),
        FantasyPick.game_id,
        FantasyPick.slot,
    ).where(
        FantasyPick.league_id == league_id,
        FantasyPick.player_id == player_id,
        FantasyPick.status.in_(("won", "lost", "void")),
    )
    legs = union_all(legacy, fantasy).subquery("history_legs")
    rows = await db.execute(
        select(legs, Fixture, Gameweek)
        .join(Fixture, Fixture.id == legs.c.fixture_id)
        .join(Gameweek, Gameweek.id == legs.c.gameweek_id)
        .order_by(Gameweek.starts_on.desc(), Fixture.kickoff_utc, Fixture.id)
    )
    history = []
    for row in rows.mappings():
        fixture, gameweek = row["Fixture"], row["Gameweek"]
        is_legacy = row["format"] == "legacy"
        history.append(
            SettledPick(
                gameweek_id=str(gameweek.id),
                starts_on=gameweek.starts_on.isoformat(),
                fixture_id=str(fixture.id),
                home=fixture.home,
                away=fixture.away,
                competition=fixture.competition,
                market=row["market"],
                outcome=row["outcome"],
                runner_name=row["runner_name"],
                odds=float(row["odds"]),
                status=row["status"],
                points_awarded=row["points_awarded"],
                format=row["format"],
                game_kind="legacy" if is_legacy else "fantasy",
                game_id=str(row["game_id"]) if row["game_id"] is not None else None,
                slot=row["slot"],
                destination=(
                    f"/leagues/{slug}/predictions?gw={gameweek.id}#coupon"
                    if is_legacy
                    else f"/leagues/{league_id}/weeks/{gameweek.id}/fantasy"
                ),
                frozen_odds=None if is_legacy else format(row["odds"], "f"),
            )
        )
    return history
