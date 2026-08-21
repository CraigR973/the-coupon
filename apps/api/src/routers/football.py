"""Football data — league tables and previous results, drawn from the whole fixture pool.

``GET /api/v1/football/tables``  — a table per competition we hold data for.
``GET /api/v1/football/results`` — the latest finished matches across them.

The other half of Batch 16 is inline rather than here: each fixture on the pick screen
carries its two clubs' positions and form (``GameweekSlateResponse.fixtures[].context``).

**Neither endpoint calls a provider.** Everything comes from ``teams`` / ``matches`` /
``standings``, which the scheduled ingestion job fills. API-Football's free plan allows a
hundred requests a *day*, so a read path that could reach upstream would be exhausted by
one member refreshing — the mistake the odds side had to build a whole cache to undo.

**Untied from a league in Batch 51.** Both routes used to hang off ``/leagues/{slug}`` and
narrow to the competitions that league plays, which was never what the screen is for: a
member opens it to look at football, not at the subset of football their own card happens
to cover. The data was never league-scoped in the first place — :func:`pooled_competitions`
walks the shared pool and the ingested tables carry no league anywhere in them — so this
costs nothing upstream. Only the read narrowed, and now it does not.

Authentication still applies, but membership does not: a league table is public
information, and with the competition selection out of the picture there is no league
configuration left to protect.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.config import settings
from src.database import get_db
from src.services.football_data import (
    CompetitionTable,
    ResultEntry,
    league_tables,
    pooled_competitions,
    recent_results,
    season_or_default,
)

router = APIRouter(prefix="/api/v1/football", tags=["football"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/tables", response_model=list[CompetitionTable])
async def competition_tables(
    player: CurrentUser,
    db: Db,
    season: int | None = None,
) -> list[CompetitionTable]:
    """League tables for every competition in the pool, in position order.

    ``season`` names the season by its starting year (2026-27 is ``2026``); it defaults to
    the configured one, or the season today falls in. Competitions with nothing stored —
    a cup, a division the provider does not carry, a season not yet ingested — are
    omitted, so an empty list means "no football data yet" rather than an error.

    "Every competition" means every one some league's card has covered, which is what the
    pool holds; it is not every competition in Britain.

    Each row carries the matches behind its form line (Batch 53), on the same
    ``football_form_matches`` setting the pick screen uses, and for one more query over
    the whole read — see :func:`~src.services.football_data.league_tables`.
    """
    competitions = await pooled_competitions(db)
    wanted = season_or_default(season or settings.football_season)
    return await league_tables(
        db, competitions, wanted, form_matches=settings.football_form_matches
    )


@router.get("/results", response_model=list[ResultEntry])
async def previous_results(
    player: CurrentUser,
    db: Db,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> list[ResultEntry]:
    """The most recent finished matches across the pool's competitions, newest first.

    Capped at 100 by the query constraint; omitting ``limit`` means "the configured page
    size", so the client does not have to know it.
    """
    competitions = await pooled_competitions(db)
    return await recent_results(
        db, competitions, limit=limit or settings.football_recent_results_limit
    )
