"""League management endpoints: create, read, update, delete, join, leave, discover."""

import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser, generate_join_code
from src.database import get_db
from src.deps import OddsProviderDep
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture
from src.models.league import (
    DEFAULT_LOCK_OFFSET_MINUTES,
    DEFAULT_OFFERED_MARKETS,
    SATURDAY,
    THREE_PM,
    League,
    LeaguePrivacy,
    PickMarket,
    PickScope,
)
from src.models.league_join_request import JoinRequestStatus, LeagueJoinRequest
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.pick import Pick, PickStatus
from src.models.profile import Profile, UserRole
from src.rate_limit import limiter, per_user_key
from src.services.gameweek import refresh_slate
from src.services.notification_triggers import notify_member_joined
from src.services.odds_provider import OddsProviderError

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["leagues"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return re.sub(r"-+", "-", s).strip("-")


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = _slugify(name)
    slug = base
    counter = 2
    while True:
        result = await db.execute(select(League.id).where(League.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{counter}"
        counter += 1


# ---------------------------------------------------------------------------
# Shared dependencies
# ---------------------------------------------------------------------------


async def _resolve_league(slug: str, db: AsyncSession) -> League:
    result = await db.execute(
        select(League).where(League.slug == slug, League.deleted_at.is_(None))
    )
    league = result.scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league


async def _resolve_active_membership(
    league_id: uuid.UUID, player_id: uuid.UUID, db: AsyncSession
) -> LeagueMembership | None:
    result = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.player_id == player_id,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _active_admin_count(league_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.role == LeagueMemberRole.admin,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    return result.scalar_one()


async def _active_member_count(league_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.deleted_at.is_(None),
        )
    )
    return result.scalar_one()


def _is_superadmin(player: Profile) -> bool:
    return player.role == UserRole.admin


async def require_league_admin(
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Profile, League]:
    """Dependency: resolves league and verifies caller is league admin or site superadmin."""
    league = await _resolve_league(slug, db)
    if _is_superadmin(player):
        return player, league
    membership = await _resolve_active_membership(league.id, player.id, db)
    if membership is None or membership.role != LeagueMemberRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="League admin required")
    return player, league


async def require_league_member(
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Profile, League]:
    """Dependency: resolves league and verifies caller is an active member."""
    league = await _resolve_league(slug, db)
    if _is_superadmin(player):
        return player, league
    membership = await _resolve_active_membership(league.id, player.id, db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="League membership required"
        )
    return player, league


LeagueAdminDep = Annotated[tuple[Profile, League], Depends(require_league_admin)]
LeagueMemberDep = Annotated[tuple[Profile, League], Depends(require_league_member)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


# The competition selection is a small value blob, not a relation, so it is bounded
# rather than paged: comfortably above the ~30 UK divisions the provider carries, and
# small enough that storing it inline on the league stays sensible.
MAX_COMPETITIONS = 40


class CompetitionRef(BaseModel):
    """One competition a league plays, by the provider's own slug plus a display name.

    ``slug`` is matched against ``fixtures.competition_id`` at link time; ``name`` is
    carried so the settings screen can label a selection without a provider round-trip.
    """

    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)


def _validate_competitions(value: list[CompetitionRef] | None) -> list[CompetitionRef] | None:
    """A competition selection is either *all UK* (``None``) or a non-empty, bounded list.

    An empty list would be a league that can never have a slate, which is a mistake
    rather than a choice — say ``None`` for "all UK leagues" instead.
    """
    if value is None:
        return None
    if not value:
        raise ValueError("competitions must be null (all UK leagues) or a non-empty list")
    if len(value) > MAX_COMPETITIONS:
        raise ValueError(f"at most {MAX_COMPETITIONS} competitions")
    return value


def _clean_markets(value: list[PickMarket]) -> list[PickMarket]:
    """De-duplicate an offered-market set, preserving order; reject the empty set."""
    seen: list[PickMarket] = []
    for market in value:
        if market not in seen:
            seen.append(market)
    if not seen:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="offered_markets must contain at least one market",
        )
    return seen


class CreateLeagueRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    privacy: LeaguePrivacy = LeaguePrivacy.private
    max_members: int = Field(default=15, ge=2, le=50)
    # Defaults to the original rule so a league's behaviour is never a surprise.
    pick_scope: PickScope = PickScope.selection
    # The weekly window. Defaults reproduce the Saturday 15:00 slate locking at 14:30;
    # editing them afterwards is Batch 15's admin surface.
    slate_start_weekday: int = Field(default=SATURDAY, ge=0, le=6)
    slate_start_minute: int = Field(default=THREE_PM, ge=0, le=1439)
    slate_end_weekday: int = Field(default=SATURDAY, ge=0, le=6)
    slate_end_minute: int = Field(default=THREE_PM, ge=0, le=1439)
    lock_offset_minutes: int = Field(default=DEFAULT_LOCK_OFFSET_MINUTES, ge=0)
    # ``None`` — the default — is "no announced opening": a round is claimable as soon
    # as discovery writes it, which is what every league did before Batch 27.
    pick_open_offset_minutes: int | None = Field(default=None, ge=0)
    # Config settable at creation and editable afterwards. ``competitions=None`` is the
    # group "all UK leagues"; ``offered_markets=None`` takes the default (both markets).
    competitions: list[CompetitionRef] | None = None
    offered_markets: list[PickMarket] | None = None

    @field_validator("competitions")
    @classmethod
    def _check_competitions(cls, value: list[CompetitionRef] | None) -> list[CompetitionRef] | None:
        return _validate_competitions(value)


class UpdateLeagueRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    privacy: LeaguePrivacy | None = None
    max_members: int | None = Field(default=None, ge=2, le=50)
    pick_scope: PickScope | None = None
    # The weekly window — each field independently editable (``None`` = unchanged).
    slate_start_weekday: int | None = Field(default=None, ge=0, le=6)
    slate_start_minute: int | None = Field(default=None, ge=0, le=1439)
    slate_end_weekday: int | None = Field(default=None, ge=0, le=6)
    slate_end_minute: int | None = Field(default=None, ge=0, le=1439)
    lock_offset_minutes: int | None = Field(default=None, ge=0)
    # Like ``competitions``, null is a *meaningful* value here — "stop announcing an
    # opening" — so this one is read from ``model_fields_set`` rather than treating
    # null as unchanged.
    pick_open_offset_minutes: int | None = Field(default=None, ge=0)
    # ``competitions`` needs "not provided" and "explicitly all UK (null)" to differ, so
    # it is read via ``model_fields_set`` in the handler rather than defaulting-to-unchanged.
    # ``offered_markets`` never has a meaningful null, so null there simply means unchanged.
    competitions: list[CompetitionRef] | None = None
    offered_markets: list[PickMarket] | None = None

    @field_validator("competitions")
    @classmethod
    def _check_competitions(cls, value: list[CompetitionRef] | None) -> list[CompetitionRef] | None:
        return _validate_competitions(value)


class SlateWindowOut(BaseModel):
    """The weekly window a league plays, as stored."""

    start_weekday: int
    start_minute: int
    end_weekday: int
    end_minute: int
    lock_offset_minutes: int
    # ``null`` = no announced opening; picks are claimable from discovery (Batch 27).
    pick_open_offset_minutes: int | None


def _window_out(league: League) -> SlateWindowOut:
    return SlateWindowOut(
        start_weekday=league.slate_start_weekday,
        start_minute=league.slate_start_minute,
        end_weekday=league.slate_end_weekday,
        end_minute=league.slate_end_minute,
        lock_offset_minutes=league.lock_offset_minutes,
        pick_open_offset_minutes=league.pick_open_offset_minutes,
    )


def _check_claim_period(pick_open_offset: int | None, lock_offset: int) -> None:
    """Reject a claim period that would close before it opened.

    Both offsets are measured back from the window opening, so the pick-open one has to
    be the larger. Checked on the *resulting* pair rather than the submitted field,
    because a PATCH that only moves the lock can invalidate an offset it never mentions
    — and the database's own check would surface that as a 500, not a 422.
    """
    if pick_open_offset is not None and pick_open_offset < lock_offset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pick_open_offset_minutes must be at least lock_offset_minutes",
        )


def _competitions_out(league: League) -> list[CompetitionRef] | None:
    """The league's competition selection, or ``None`` for the all-UK group."""
    if league.competitions is None:
        return None
    return [CompetitionRef(slug=c["slug"], name=c["name"]) for c in league.competitions]


def _markets_out(league: League) -> list[str]:
    """The league's offered markets as wire values, whatever the array column yields."""
    return [PickMarket(m).value for m in league.offered_markets]


class LeagueResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    privacy: str
    max_members: int
    pick_scope: str
    slate_window: SlateWindowOut
    competitions: list[CompetitionRef] | None
    offered_markets: list[str]
    member_count: int
    created_by: str
    created_at: datetime
    join_code: str | None = None


class LeagueSummaryResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    privacy: str
    max_members: int
    member_count: int
    my_role: str | None


class DiscoverLeagueResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    max_members: int
    member_count: int
    privacy: str


class DiscoverResponse(BaseModel):
    leagues: list[DiscoverLeagueResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------


def _audit(
    actor: Profile,
    action: ActionType,
    target_table: str,
    target_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    actor_type = ActorType.admin if _is_superadmin(actor) else ActorType.player
    return AuditLog(
        actor_id=actor.id,
        actor_type=actor_type,
        action_type=action,
        target_table=target_table,
        target_id=target_id,
        changes=changes,
    )


# ---------------------------------------------------------------------------
# Pick-scope transition
# ---------------------------------------------------------------------------


async def _apply_pick_scope_change(league: League, new_scope: PickScope, db: AsyncSession) -> None:
    """Restamp this league's unsettled picks with the new scope.

    ``picks.pick_scope`` is what the partial fixture-level unique index reads, so
    leaving old rows on the old scope would exempt them from the rule the league
    just adopted. Only ``pending`` picks are restamped: a settled gameweek was
    played under the rule in force at the time and is not rewritten.

    Tightening to ``fixture`` is refused when it would immediately be violated —
    two members already holding one game. Reporting that is far kinder than
    letting the index raise ``IntegrityError`` on an unrelated later write.
    """
    if new_scope is PickScope.fixture:
        clash = await db.execute(
            select(Pick.gameweek_id, Pick.fixture_id)
            .where(Pick.league_id == league.id, Pick.status == PickStatus.pending)
            .group_by(Pick.gameweek_id, Pick.fixture_id)
            .having(func.count() > 1)
        )
        if clash.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="PICK_SCOPE_CONFLICT",
            )

    await db.execute(
        update(Pick)
        .where(Pick.league_id == league.id, Pick.status == PickStatus.pending)
        .values(pick_scope=new_scope)
    )


# ---------------------------------------------------------------------------
# Privacy transition side effects
# ---------------------------------------------------------------------------


async def _cancel_pending_requests(league_id: uuid.UUID, db: AsyncSession) -> int:
    """Cancel all pending join requests for a league. Returns count cancelled."""
    result = await db.execute(
        select(LeagueJoinRequest).where(
            LeagueJoinRequest.league_id == league_id,
            LeagueJoinRequest.status == JoinRequestStatus.pending,
        )
    )
    requests = list(result.scalars().all())
    for req in requests:
        req.status = JoinRequestStatus.cancelled
        req.decided_at = _now()
    return len(requests)


async def _auto_approve_pending_requests(
    league_id: uuid.UUID, admin: Profile, db: AsyncSession
) -> int:
    """Auto-approve all pending join requests when switching to public_open.
    Creates/restores memberships for each requester. Returns count approved.
    """
    result = await db.execute(
        select(LeagueJoinRequest).where(
            LeagueJoinRequest.league_id == league_id,
            LeagueJoinRequest.status == JoinRequestStatus.pending,
        )
    )
    requests = list(result.scalars().all())
    for req in requests:
        req.status = JoinRequestStatus.approved
        req.decided_at = _now()
        req.decided_by = admin.id
        await _upsert_membership(league_id, req.player_id, db)
    return len(requests)


async def _upsert_membership(
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    db: AsyncSession,
    *,
    role: LeagueMemberRole = LeagueMemberRole.player,
) -> LeagueMembership:
    """Create or restore a soft-deleted membership row."""
    result = await db.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.player_id == player_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Restore soft-deleted row
        existing.deleted_at = None
        existing.joined_at = _now()
        existing.role = role
        existing.updated_at = _now()
        return existing
    membership = LeagueMembership(
        league_id=league_id,
        player_id=player_id,
        role=role,
        joined_at=_now(),
        created_at=_now(),
    )
    db.add(membership)
    return membership


# ---------------------------------------------------------------------------
# POST /api/v1/leagues  — create
# ---------------------------------------------------------------------------


@router.post("", response_model=LeagueResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour", key_func=per_user_key)
async def create_league(
    request: Request,
    body: CreateLeagueRequest,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeagueResponse:
    _check_claim_period(body.pick_open_offset_minutes, body.lock_offset_minutes)
    slug = await _unique_slug(db, body.name)
    markets = (
        _clean_markets(body.offered_markets)
        if body.offered_markets is not None
        else list(DEFAULT_OFFERED_MARKETS)
    )
    league = League(
        slug=slug,
        name=body.name,
        description=body.description,
        privacy=body.privacy,
        max_members=body.max_members,
        pick_scope=body.pick_scope,
        slate_start_weekday=body.slate_start_weekday,
        slate_start_minute=body.slate_start_minute,
        slate_end_weekday=body.slate_end_weekday,
        slate_end_minute=body.slate_end_minute,
        lock_offset_minutes=body.lock_offset_minutes,
        pick_open_offset_minutes=body.pick_open_offset_minutes,
        competitions=(
            [c.model_dump() for c in body.competitions] if body.competitions is not None else None
        ),
        offered_markets=markets,
        created_by=player.id,
        created_at=_now(),
        join_code=generate_join_code(),
    )
    db.add(league)
    await db.flush()  # populate league.id before FK reference

    membership = LeagueMembership(
        league_id=league.id,
        player_id=player.id,
        role=LeagueMemberRole.admin,
        joined_at=_now(),
        created_at=_now(),
    )
    db.add(membership)

    db.add(
        _audit(
            player,
            ActionType.league_created,
            "leagues",
            league.id,
            {"name": body.name, "privacy": body.privacy.value},
        )
    )

    await db.commit()
    await db.refresh(league)

    log.info("league created", league_id=str(league.id), slug=slug, player_id=str(player.id))
    return LeagueResponse(
        id=str(league.id),
        slug=league.slug,
        name=league.name,
        description=league.description,
        privacy=league.privacy.value,
        max_members=league.max_members,
        pick_scope=league.pick_scope.value,
        slate_window=_window_out(league),
        competitions=_competitions_out(league),
        offered_markets=_markets_out(league),
        member_count=1,
        created_by=str(league.created_by),
        created_at=league.created_at,
        join_code=league.join_code,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/leagues/mine
# ---------------------------------------------------------------------------


@router.get("/mine", response_model=list[LeagueSummaryResponse])
@limiter.limit("120/minute", key_func=per_user_key)
async def list_my_leagues(
    request: Request,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LeagueSummaryResponse]:
    result = await db.execute(
        select(League, LeagueMembership, func.count().label("member_count"))
        .join(LeagueMembership, LeagueMembership.league_id == League.id)
        .where(
            LeagueMembership.player_id == player.id,
            LeagueMembership.deleted_at.is_(None),
            League.deleted_at.is_(None),
        )
        .outerjoin(
            LeagueMembership.__table__.alias("all_members"),
            (LeagueMembership.__table__.alias("all_members").c.league_id == League.id)
            & (LeagueMembership.__table__.alias("all_members").c.deleted_at.is_(None)),
        )
        .group_by(League.id, LeagueMembership.id)
        .order_by(League.name)
    )
    rows = list(result.all())
    # Re-query member counts separately to keep the join simple
    out: list[LeagueSummaryResponse] = []
    for row in rows:
        league: League = row[0]
        membership: LeagueMembership = row[1]
        count = await _active_member_count(league.id, db)
        out.append(
            LeagueSummaryResponse(
                id=str(league.id),
                slug=league.slug,
                name=league.name,
                description=league.description,
                privacy=league.privacy.value,
                max_members=league.max_members,
                member_count=count,
                my_role=membership.role.value,
            )
        )
    return out


# ---------------------------------------------------------------------------
# GET /api/v1/leagues/discover
# ---------------------------------------------------------------------------


@router.get("/discover", response_model=DiscoverResponse)
@limiter.limit("60/minute", key_func=per_user_key)
async def discover_leagues(
    request: Request,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 20,
) -> DiscoverResponse:
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 50:
        page_size = 20

    # IDs of leagues caller is already in
    member_sub = (
        select(LeagueMembership.league_id)
        .where(
            LeagueMembership.player_id == player.id,
            LeagueMembership.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    member_count_sub = (
        select(func.count())
        .where(
            LeagueMembership.league_id == League.id,
            LeagueMembership.deleted_at.is_(None),
        )
        .correlate(League)
        .scalar_subquery()
    )

    base_q = select(League, member_count_sub.label("member_count")).where(
        League.privacy.in_([LeaguePrivacy.public_request, LeaguePrivacy.public_open]),
        League.deleted_at.is_(None),
        League.id.not_in(member_sub),
    )
    total_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = total_result.scalar_one()

    rows_result = await db.execute(
        base_q.order_by(member_count_sub.desc(), League.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = list(rows_result.all())

    leagues = [
        DiscoverLeagueResponse(
            id=str(row[0].id),
            slug=row[0].slug,
            name=row[0].name,
            description=row[0].description,
            max_members=row[0].max_members,
            member_count=row[1],
            privacy=(
                row[0].privacy.value if hasattr(row[0].privacy, "value") else str(row[0].privacy)
            ),
        )
        for row in rows
    ]
    return DiscoverResponse(leagues=leagues, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# GET /api/v1/leagues/by-code/{code}  — public, no auth required
# ---------------------------------------------------------------------------


class LeagueByCodeResponse(BaseModel):
    name: str
    member_count: int
    max_members: int
    privacy: str


@router.get("/by-code/{code}", response_model=LeagueByCodeResponse)
@limiter.limit("60/minute")
async def get_league_by_code(
    request: Request,
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeagueByCodeResponse:
    result = await db.execute(
        select(League).where(
            League.join_code == code.upper(),
            League.deleted_at.is_(None),
        )
    )
    league = result.scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    count = await _active_member_count(league.id, db)
    return LeagueByCodeResponse(
        name=league.name,
        member_count=count,
        max_members=league.max_members,
        privacy=league.privacy.value,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/leagues/{slug}
# ---------------------------------------------------------------------------


class MemberInfo(BaseModel):
    id: str
    display_name: str
    role: str
    joined_at: datetime
    avatar_url: str | None = None


class LeagueDetailResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    privacy: str
    max_members: int
    pick_scope: str
    slate_window: SlateWindowOut
    competitions: list[CompetitionRef] | None
    offered_markets: list[str]
    member_count: int
    created_by: str
    created_at: datetime
    join_code: str | None = None
    members: list[MemberInfo] | None  # None when caller is not a member


@router.get("/{slug}", response_model=LeagueDetailResponse)
@limiter.limit("120/minute", key_func=per_user_key)
async def get_league(
    request: Request,
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeagueDetailResponse:
    league = await _resolve_league(slug, db)

    # Check if caller is a member (or superadmin)
    is_member = _is_superadmin(player)
    if not is_member:
        m = await _resolve_active_membership(league.id, player.id, db)
        is_member = m is not None

    # Private leagues are not enumerable by non-members — return 404 to avoid
    # confirming the league's existence.
    if league.privacy == LeaguePrivacy.private and not is_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")

    member_count = await _active_member_count(league.id, db)

    members_out: list[MemberInfo] | None = None
    if is_member:
        result = await db.execute(
            select(LeagueMembership, Profile)
            .join(Profile, Profile.id == LeagueMembership.player_id)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.deleted_at.is_(None),
                Profile.deleted_at.is_(None),
            )
            .order_by(LeagueMembership.joined_at)
        )
        members_out = [
            MemberInfo(
                id=str(row[1].id),
                display_name=row[0].display_name_override or row[1].display_name,
                role=row[0].role.value,
                joined_at=row[0].joined_at,
                avatar_url=row[1].avatar_url,
            )
            for row in result.all()
        ]

    return LeagueDetailResponse(
        id=str(league.id),
        slug=league.slug,
        name=league.name,
        description=league.description,
        privacy=league.privacy.value,
        max_members=league.max_members,
        pick_scope=league.pick_scope.value,
        slate_window=_window_out(league),
        competitions=_competitions_out(league),
        offered_markets=_markets_out(league),
        member_count=member_count,
        created_by=str(league.created_by),
        created_at=league.created_at,
        join_code=league.join_code if is_member else None,
        members=members_out,
    )


# ---------------------------------------------------------------------------
# PATCH /api/v1/leagues/{slug}  — edit settings
# ---------------------------------------------------------------------------


@router.patch("/{slug}", response_model=LeagueResponse)
@limiter.limit("30/hour", key_func=per_user_key)
async def update_league(
    request: Request,
    slug: str,
    body: UpdateLeagueRequest,
    admin_ctx: LeagueAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeagueResponse:
    player, league = admin_ctx

    changes: dict[str, Any] = {}

    if body.name is not None and body.name != league.name:
        changes["name"] = {"from": league.name, "to": body.name}
        league.name = body.name

    if body.description is not None and body.description != league.description:
        changes["description"] = {"from": league.description, "to": body.description}
        league.description = body.description

    if body.max_members is not None and body.max_members != league.max_members:
        if body.max_members < await _active_member_count(league.id, db):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="max_members cannot be lower than current member count",
            )
        changes["max_members"] = {"from": league.max_members, "to": body.max_members}
        league.max_members = body.max_members

    if body.pick_scope is not None and body.pick_scope != league.pick_scope:
        await _apply_pick_scope_change(league, body.pick_scope, db)
        changes["pick_scope"] = {"from": league.pick_scope.value, "to": body.pick_scope.value}
        league.pick_scope = body.pick_scope

    # Weekly window — each of the five fields independently editable. Existing rounds
    # keep the ``locks_at_utc`` and ``picks_open_at_utc`` they were synced with; only
    # rounds discovered from now on use the new window, exactly as a window change has
    # always applied. That is what stops an edit moving a deadline members were told.
    window_fields = {
        "slate_start_weekday": body.slate_start_weekday,
        "slate_start_minute": body.slate_start_minute,
        "slate_end_weekday": body.slate_end_weekday,
        "slate_end_minute": body.slate_end_minute,
        "lock_offset_minutes": body.lock_offset_minutes,
    }
    for attr, new_value in window_fields.items():
        if new_value is not None and new_value != getattr(league, attr):
            changes[attr] = {"from": getattr(league, attr), "to": new_value}
            setattr(league, attr, new_value)

    # Pick-open offset — null means "stop announcing an opening", so it is read from
    # ``model_fields_set``. Validated against the lock offset *after* the block above,
    # because that block may just have moved the lock this has to clear.
    if "pick_open_offset_minutes" in body.model_fields_set:
        wanted_open = body.pick_open_offset_minutes
        _check_claim_period(wanted_open, league.lock_offset_minutes)
        if wanted_open != league.pick_open_offset_minutes:
            changes["pick_open_offset_minutes"] = {
                "from": league.pick_open_offset_minutes,
                "to": wanted_open,
            }
            league.pick_open_offset_minutes = wanted_open
    else:
        # A lock moved on its own must still leave a stored opening valid.
        _check_claim_period(league.pick_open_offset_minutes, league.lock_offset_minutes)

    # Offered markets — null means unchanged; a list replaces the set (deduped, non-empty).
    if body.offered_markets is not None:
        new_markets = _clean_markets(body.offered_markets)
        current_markets = _markets_out(league)
        wanted_markets = [m.value for m in new_markets]
        if wanted_markets != current_markets:
            changes["offered_markets"] = {"from": current_markets, "to": wanted_markets}
            league.offered_markets = new_markets

    # Competition selection — "not provided" and "explicitly all UK (null)" differ, so it
    # is read from ``model_fields_set`` rather than defaulting-to-unchanged like the rest.
    if "competitions" in body.model_fields_set:
        new_comps = (
            [c.model_dump() for c in body.competitions] if body.competitions is not None else None
        )
        if new_comps != league.competitions:
            changes["competitions"] = {"from": league.competitions, "to": new_comps}
            league.competitions = new_comps

    privacy_changed = body.privacy is not None and body.privacy != league.privacy
    if privacy_changed:
        old_privacy = league.privacy
        new_privacy = body.privacy
        assert new_privacy is not None

        # Transition side effects
        if new_privacy == LeaguePrivacy.private:
            # Cancel all pending join requests
            await _cancel_pending_requests(league.id, db)
        elif (
            old_privacy == LeaguePrivacy.public_request and new_privacy == LeaguePrivacy.public_open
        ):
            # Auto-approve pending requests
            member_count = await _active_member_count(league.id, db)
            if member_count < league.max_members:
                await _auto_approve_pending_requests(league.id, player, db)

        changes["privacy"] = {"from": old_privacy.value, "to": new_privacy.value}
        league.privacy = new_privacy

        db.add(_audit(player, ActionType.league_privacy_changed, "leagues", league.id, changes))
    elif changes:
        db.add(_audit(player, ActionType.league_updated, "leagues", league.id, changes))

    league.updated_at = _now()
    await db.commit()
    await db.refresh(league)

    member_count = await _active_member_count(league.id, db)
    return LeagueResponse(
        id=str(league.id),
        slug=league.slug,
        name=league.name,
        description=league.description,
        privacy=league.privacy.value,
        max_members=league.max_members,
        pick_scope=league.pick_scope.value,
        slate_window=_window_out(league),
        competitions=_competitions_out(league),
        offered_markets=_markets_out(league),
        member_count=member_count,
        created_by=str(league.created_by),
        created_at=league.created_at,
        join_code=league.join_code,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/leagues/{slug}/competitions  — the admin's competition catalogue
# ---------------------------------------------------------------------------


class CompetitionsResponse(BaseModel):
    """What the settings screen needs to render the competition picker.

    ``available`` is the catalogue to choose from — every UK competition the odds provider
    carries. ``all_uk`` is true when the league is on the default group; ``selected`` is
    its explicit list otherwise (empty when ``all_uk``). A stored selection the provider
    has since dropped stays in ``selected`` and is unioned back in by the picker, so it
    still shows as ticked rather than vanishing.
    """

    all_uk: bool
    available: list[CompetitionRef]
    selected: list[CompetitionRef]


async def _pooled_competitions(db: AsyncSession) -> list[CompetitionRef]:
    """The competitions discovery has already pooled into ``fixtures``.

    What the catalogue used to be built from, kept as the degraded answer when the
    provider cannot be reached: a subset of the real catalogue, but never worse than the
    behaviour this endpoint shipped with.
    """
    rows = await db.execute(
        select(Fixture.competition_id, Fixture.competition).distinct().order_by(Fixture.competition)
    )
    return [CompetitionRef(slug=slug_, name=name) for slug_, name in rows.all()]


@router.get("/{slug}/competitions", response_model=CompetitionsResponse)
@limiter.limit("60/minute", key_func=per_user_key)
async def league_competitions(
    request: Request,
    slug: str,
    admin_ctx: LeagueAdminDep,
    provider: OddsProviderDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompetitionsResponse:
    """The competition picker's catalogue, sourced from the odds provider.

    Batch 15 shipped the picker against ``SELECT DISTINCT … FROM fixtures``, which is only
    what discovery had already pooled — so a league whose slate had never run saw an empty
    list and could not narrow at all. The provider's own catalogue is the right source and
    costs nothing on the common path: it is one ``/leagues`` call, memoised on the shared
    client, not the per-competition ``/events`` fan-out the slate pays for.
    """
    _, league = admin_ctx
    try:
        available = [
            CompetitionRef(slug=c.competition_id, name=c.competition)
            for c in await provider.fetch_competitions()
        ]
    except OddsProviderError as exc:
        # The picker is how an admin *un*-narrows a league, so an upstream failure must not
        # lock them out of their own settings. Fall back to the pooled set.
        log.warning("competition catalogue unavailable; falling back to pooled", error=repr(exc))
        available = await _pooled_competitions(db)
    selected = _competitions_out(league)
    return CompetitionsResponse(
        all_uk=selected is None,
        available=available,
        selected=selected or [],
    )


# ---------------------------------------------------------------------------
# POST /api/v1/leagues/{slug}/gameweeks  — an ad-hoc round (e.g. Boxing Day)
# ---------------------------------------------------------------------------


# What an admin may spend on ad-hoc rounds, in the comment style `odds_cache_ttl_seconds`
# uses — because the number is arithmetic, not taste, and the next person to raise it
# should see the ceiling rather than rediscover it.
#
# One call walks the provider in the request path: one `/events` per competition the
# league plays. Since Batch 35 `refresh_slate` narrows that to the league's own selection,
# so a configured league pays 1-3 and only an unconfigured all-UK one still pays ~30 —
# which is the figure below, because the limit has to survive the worst case.
#
# What the rest of the budget leaves, measured against a real cache in
# `tests/test_request_budget.py` rather than modelled: the tightest hour is 28 of
# odds-api.io's 100, and a fully saturated day is 336 of browsing plus 60 of discovery
# against 500. So:
#
#   2/hour -> ~60 requests, inside the ~72 an hour leaves
#   3/day  -> ~90 requests, inside the ~104 a day leaves
#
# Both caps are needed. An hourly limit alone permits 24x its own number across a day,
# and the day is the tighter budget; a daily limit alone permits all of it inside the
# peak browsing hour. The previous `6/hour` allowed ~180 requests an hour against a
# 100/hour plan on its own. Exhaustion is **silent** — picks simply stay `pending` and
# the week never finishes — so raising either number means redoing the arithmetic above,
# not enlarging a constant.
AD_HOC_GAMEWEEK_LIMIT = "2/hour;3/day"


class CreateGameweekRequest(BaseModel):
    starts_on: date


class AdHocGameweekResponse(BaseModel):
    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: datetime
    # When picks open, or ``null`` when the league announces no opening (Batch 27).
    picks_open_at_utc: datetime | None
    # What members call this round — "Gameweek 12" (Batch 41). A one-off takes the next
    # number in the season rather than the position its date implies; see
    # ``next_gameweek_number``.
    number: int | None
    fixture_count: int
    # True when this call created the round; false when it refreshed an existing one.
    created: bool


@router.post(
    "/{slug}/gameweeks", response_model=AdHocGameweekResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(AD_HOC_GAMEWEEK_LIMIT, key_func=per_user_key)
async def create_gameweek(
    request: Request,
    slug: str,
    body: CreateGameweekRequest,
    admin_ctx: LeagueAdminDep,
    provider: OddsProviderDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdHocGameweekResponse:
    """Create a round on a date outside the league's normal cadence — Boxing Day, say.

    Fetches that date's slate with the league's own window (its kick-off times, anchored
    on the requested date, so the weekday need not be the league's usual one) and its
    competition selection, then upserts it as a round. This walks the provider in the
    request path — one ``/events`` request per competition *this league plays*, which
    since Batch 35 is its own selection rather than all ~30 UK competitions — so it is
    tightly rate-limited; it is an occasional admin action, not a hot path. See
    :data:`AD_HOC_GAMEWEEK_LIMIT` for the arithmetic behind the limit.

    The round is adopted by the scheduler like any other: ``open_due_gameweeks``,
    ``lock_due_gameweeks`` and settlement all select on status and instants with no date
    filter, and once it is inside the discovery horizon the refresh job revisits it (see
    :func:`~src.services.gameweek.discover_fixtures`).

    A date the provider carries no qualifying fixtures for (or one the league's competition
    selection excludes entirely) is a 422 rather than an empty round. A round already on
    the date is refreshed in place and returned with ``created=false``. A date in the past
    yields an already-locked, unpickable round — harmless, and simplest not to forbid.
    """
    player, league = admin_ctx

    existing = await db.execute(
        select(Gameweek.id).where(
            Gameweek.league_id == league.id, Gameweek.starts_on == body.starts_on
        )
    )
    already = existing.scalar_one_or_none()

    gameweek = await refresh_slate(db, provider, league, body.starts_on)
    if gameweek is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="NO_FIXTURES")
    await db.commit()
    await db.refresh(gameweek)

    count = await db.execute(select(func.count()).where(GameweekFixture.gameweek_id == gameweek.id))
    log.info(
        "ad-hoc gameweek synced",
        league_id=str(league.id),
        gameweek_id=str(gameweek.id),
        starts_on=str(body.starts_on),
        created=already is None,
        player_id=str(player.id),
    )
    return AdHocGameweekResponse(
        gameweek_id=str(gameweek.id),
        starts_on=gameweek.starts_on,
        status=gameweek.status.value,
        locks_at_utc=gameweek.locks_at_utc,
        picks_open_at_utc=gameweek.picks_open_at_utc,
        number=gameweek.number,
        fixture_count=count.scalar_one(),
        created=already is None,
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/leagues/{slug}  — soft delete
# ---------------------------------------------------------------------------


class DeleteLeagueRequest(BaseModel):
    confirm_name: str = Field(description="Caller must type the league name to confirm deletion")


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour", key_func=per_user_key)
async def delete_league(
    request: Request,
    slug: str,
    body: DeleteLeagueRequest,
    admin_ctx: LeagueAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    player, league = admin_ctx
    if body.confirm_name != league.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confirm_name does not match league name",
        )
    league.deleted_at = _now()
    league.updated_at = _now()
    db.add(_audit(player, ActionType.league_deleted, "leagues", league.id, {"name": league.name}))
    await db.commit()
    log.info("league deleted", league_id=str(league.id), slug=slug, player_id=str(player.id))


# ---------------------------------------------------------------------------
# POST /api/v1/leagues/{slug}/join
# ---------------------------------------------------------------------------


class JoinResponse(BaseModel):
    status: str  # "joined" or "pending"


@router.post("/{slug}/join", response_model=JoinResponse, status_code=status.HTTP_200_OK)
@limiter.limit("30/hour", key_func=per_user_key)
async def join_league(
    request: Request,
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JoinResponse:
    league = await _resolve_league(slug, db)

    if league.privacy == LeaguePrivacy.private:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PRIVATE_LEAGUE: join via invite only",
        )

    # Already a member?
    existing = await _resolve_active_membership(league.id, player.id, db)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ALREADY_MEMBER",
        )

    member_count = await _active_member_count(league.id, db)
    if member_count >= league.max_members:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LEAGUE_FULL",
        )

    if league.privacy == LeaguePrivacy.public_open:
        await _upsert_membership(league.id, player.id, db)
        db.add(_audit(player, ActionType.member_joined, "league_memberships", league.id))
        await notify_member_joined(db, player.display_name, league.name)
        await db.commit()
        log.info("league joined", league_id=str(league.id), player_id=str(player.id))
        return JoinResponse(status="joined")

    # public_request: create or reuse a pending join request
    existing_req_result = await db.execute(
        select(LeagueJoinRequest).where(
            LeagueJoinRequest.league_id == league.id,
            LeagueJoinRequest.player_id == player.id,
            LeagueJoinRequest.status == JoinRequestStatus.pending,
        )
    )
    if existing_req_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="JOIN_REQUEST_PENDING",
        )
    join_req = LeagueJoinRequest(
        league_id=league.id,
        player_id=player.id,
        status=JoinRequestStatus.pending,
        requested_at=_now(),
        created_at=_now(),
    )
    db.add(join_req)
    db.add(_audit(player, ActionType.join_request_created, "league_join_requests", league.id))
    await db.commit()
    log.info("join request created", league_id=str(league.id), player_id=str(player.id))
    return JoinResponse(status="pending")


# ---------------------------------------------------------------------------
# DELETE /api/v1/leagues/{slug}/membership  — leave
# ---------------------------------------------------------------------------


@router.delete("/{slug}/membership", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/hour", key_func=per_user_key)
async def leave_league(
    request: Request,
    slug: str,
    player: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    league = await _resolve_league(slug, db)
    membership = await _resolve_active_membership(league.id, player.id, db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not a member of this league",
        )

    # Last-admin protection
    if membership.role == LeagueMemberRole.admin:
        admin_count = await _active_admin_count(league.id, db)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="LAST_ADMIN: promote another member to admin before leaving",
            )

    membership.deleted_at = _now()
    membership.updated_at = _now()
    db.add(_audit(player, ActionType.member_left, "league_memberships", league.id))
    await db.commit()
    log.info("left league", league_id=str(league.id), player_id=str(player.id))
