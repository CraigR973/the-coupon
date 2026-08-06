"""Football data — league tables and previous results, scoped to a league's competitions.

``GET /api/v1/leagues/{slug}/football/tables``  — a table per competition the league plays.
``GET /api/v1/leagues/{slug}/football/results`` — the latest finished matches across them.

The other half of Batch 16 is inline rather than here: each fixture on the pick screen
carries its two clubs' positions and form (``GameweekSlateResponse.fixtures[].context``).

**Neither endpoint calls a provider.** Everything comes from ``teams`` / ``matches`` /
``standings``, which the scheduled ingestion job fills. API-Football's free plan allows a
hundred requests a *day*, so a read path that could reach upstream would be exhausted by
one member refreshing — the mistake the odds side had to build a whole cache to undo.

Both are member-gated by ``LeagueMemberDep``, like every other league read. Nothing here
is private — a league table is public information — but the *competition selection* is a
league's own configuration, and gating consistently is cheaper to reason about than an
exception.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.deps import LeagueMemberDep
from src.services.football_data import (
    CompetitionTable,
    ResultEntry,
    league_competitions,
    league_tables,
    recent_results,
    season_or_default,
)

router = APIRouter(prefix="/api/v1/leagues", tags=["football"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{slug}/football/tables", response_model=list[CompetitionTable])
async def competition_tables(
    slug: str,
    league: LeagueMemberDep,
    db: Db,
    season: int | None = None,
) -> list[CompetitionTable]:
    """League tables for the competitions this league plays, in position order.

    ``season`` names the season by its starting year (2026-27 is ``2026``); it defaults to
    the configured one, or the season today falls in. Competitions with nothing stored —
    a cup, a division the provider does not carry, a season not yet ingested — are
    omitted, so an empty list means "no football data yet" rather than an error.
    """
    competitions = await league_competitions(db, league)
    wanted = season_or_default(season or settings.football_season)
    return await league_tables(db, competitions, wanted)


@router.get("/{slug}/football/results", response_model=list[ResultEntry])
async def previous_results(
    slug: str,
    league: LeagueMemberDep,
    db: Db,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> list[ResultEntry]:
    """The most recent finished matches in this league's competitions, newest first.

    Capped at 100 by the query constraint; omitting ``limit`` means "the configured page
    size", so the client does not have to know it.
    """
    competitions = await league_competitions(db, league)
    return await recent_results(
        db, competitions, limit=limit or settings.football_recent_results_limit
    )
