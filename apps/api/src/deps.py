"""Shared FastAPI dependencies."""

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import UserRole
from src.services.odds_provider import OddsProvider, OddsProviderError
from src.services.odds_session import odds_session

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def get_league_or_404(slug: str, db: AsyncSession) -> League:
    result = await db.execute(
        select(League).where(League.slug == slug, League.deleted_at.is_(None))
    )
    league = result.scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league


async def require_league_member(
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> League:
    """Resolve the league by slug and require the caller be an active member.

    Site admins bypass the membership check. Shared by the picks / gameweek / coupon
    routers (leagues.py keeps its own equivalents).
    """
    league = await get_league_or_404(slug, db)
    if player.role == UserRole.admin:
        return league
    membership = await db.execute(
        select(LeagueMembership.id).where(
            LeagueMembership.league_id == league.id,
            LeagueMembership.player_id == player.id,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="League membership required"
        )
    return league


LeagueMemberDep = Annotated[League, Depends(require_league_member)]


async def get_odds_provider() -> OddsProvider:
    """Return the shared, kept-warm odds client for odds snapshots / settlement.

    Overridden with ``FakeBetfair`` in tests. Draws from the process-wide
    :data:`~src.services.odds_session.odds_session` rather than authenticating per request
    (Batch 3 authenticated on every call), and the client it returns caches odds so the
    request path stays inside the provider's rate limit. A 503 (not 500) surfaces when the
    provider is unconfigured or unreachable, so a missing session degrades cleanly.
    """
    try:
        return await odds_session.acquire()
    except OddsProviderError as exc:
        log.warning("odds provider unavailable", error=repr(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Odds service unavailable"
        ) from exc


OddsProviderDep = Annotated[OddsProvider, Depends(get_odds_provider)]


async def shared_league_player_ids(
    requester_id: uuid.UUID, db: AsyncSession
) -> frozenset[uuid.UUID]:
    """IDs of all players who share ≥1 active league with requester (includes self).

    Always includes requester_id so a player can always read their own data.
    """
    requester_leagues_sq = (
        select(LeagueMembership.league_id)
        .where(
            LeagueMembership.player_id == requester_id,
            LeagueMembership.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    result = await db.execute(
        select(LeagueMembership.player_id)
        .where(
            LeagueMembership.league_id.in_(requester_leagues_sq),
            LeagueMembership.deleted_at.is_(None),
        )
        .distinct()
    )
    return frozenset(result.scalars().all()) | {requester_id}
