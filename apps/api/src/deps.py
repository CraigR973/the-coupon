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


async def _has_active_membership(league: League, player_id: uuid.UUID, db: AsyncSession) -> bool:
    membership = await db.execute(
        select(LeagueMembership.id).where(
            LeagueMembership.league_id == league.id,
            LeagueMembership.player_id == player_id,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    return membership.scalar_one_or_none() is not None


async def require_league_member(
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> League:
    """Resolve the league by slug and require the caller be an active member, **to read**.

    Site admins bypass the membership check, deliberately and only here: oversight means
    being able to look at any league without joining it and appearing on its table.

    Batch 125 split this in two, because the bypass covered writes as well. A site admin
    who had never joined could submit a pick, which **consumed a selection** from the
    league's pool — taking it from a genuine member. They appeared in no member list and
    no standing, and could not undo it by leaving, because there was nothing to leave.
    A write needs :func:`require_league_member_write`.
    """
    league = await get_league_or_404(slug, db)
    if player.role == UserRole.admin:
        return league
    if not await _has_active_membership(league, player.id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="League membership required"
        )
    return league


async def require_league_member_write(
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> League:
    """The same, for anything that changes the league's state. **No site-admin bypass.**

    Being able to see a league is not the same as being able to play in it. Site admins
    keep every read path they had; to act inside a league they join it like anybody else,
    which is also what makes the action attributable and reversible.
    """
    league = await get_league_or_404(slug, db)
    if not await _has_active_membership(league, player.id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="League membership required"
        )
    return league


LeagueMemberDep = Annotated[League, Depends(require_league_member)]
LeagueMemberWriteDep = Annotated[League, Depends(require_league_member_write)]


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


async def get_optional_odds_provider() -> OddsProvider | None:
    """The same shared client, but ``None`` rather than a 503 when there isn't one.

    For routes where the provider is a *sometimes* dependency. Creating a league
    populates its rounds from the fixture pool (Batch 47) and only reaches upstream for a
    window nothing has fetched yet, so resolving the provider eagerly would make league
    creation fail whenever odds-api.io is having a bad afternoon — wiring an availability
    the database could serve on its own to a third party's rate limit.

    Callers must treat ``None`` as "pool only" and still succeed.
    """
    try:
        return await odds_session.acquire()
    except OddsProviderError as exc:
        log.warning("odds provider unavailable", error=repr(exc))
        return None


OptionalOddsProviderDep = Annotated[OddsProvider | None, Depends(get_optional_odds_provider)]


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
