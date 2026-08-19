"""Endpoints scoped to the authenticated user (``/api/v1/me``).

Everything else in the API is read through one league: a slate, a coupon, a table and
a member's record all take a slug. That is right for the things a league owns, and
wrong for the two screens that are about the *member* — home, and their own profile —
because a member in three leagues has three of everything and no single slug is the
answer.

``GET /me/cross-league-summary`` is the read those screens share. It costs the same
five queries whether the caller is in one league or six.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.rate_limit import limiter, per_user_key
from src.services.coupon import combined_odds
from src.services.gameweek import current_round_order
from src.services.scoring import standings_by_league

router = APIRouter(prefix="/api/v1/me", tags=["me"])

Db = Annotated[AsyncSession, Depends(get_db)]

# Rank does not aggregate the way points do: first of three and first of fifteen are
# not the same achievement, and a two-person league is rank 1 by default. Leagues
# below this size are left out of the average so they cannot flatter it — they still
# appear in the breakdown, with their own rank, which is where that number means
# something. Ported from wc_2026_predictor along with the endpoint.
_MIN_MEMBERS_FOR_AVG = 3


class ProfileOut(BaseModel):
    id: str
    display_name: str
    role: str
    timezone: str
    odds_format: str


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: CurrentUser) -> ProfileOut:
    """Return the authenticated user's basic profile."""
    return ProfileOut(
        id=str(user.id),
        display_name=user.display_name,
        role=user.role.value,
        timezone=user.timezone,
        odds_format=user.odds_format.value,
    )


class MyPick(BaseModel):
    """The caller's own selection in a league's latest round."""

    fixture_id: str
    home: str
    away: str
    market: str
    outcome: str
    runner_name: str
    odds: float
    status: str


class CurrentRound(BaseModel):
    """A league's latest round as it concerns the caller — the home card's body.

    ``my_pick`` is ``None`` when they have not claimed a selection yet, which is the
    state the card exists to shout about while the round is still open.
    """

    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: datetime
    # When picks open, or ``null`` when the league announces no opening (Batch 27). The
    # card counts down to whichever of the two instants is next.
    picks_open_at_utc: datetime | None
    # The whole league's acca for the round, so the card can say what is riding on it.
    leg_count: int
    combined_odds: float
    my_pick: MyPick | None


class PerLeagueSummary(BaseModel):
    """One league the caller belongs to, and their record in it."""

    slug: str
    name: str
    member_count: int
    # From the league's own season table, so this can never disagree with the
    # leaderboard. `None` only if the table somehow has no row for a current member.
    rank: int | None
    total_points: int
    picks_played: int
    picks_won: int
    # `None` when the league has no rounds yet.
    current_round: CurrentRound | None


class CrossLeagueSummary(BaseModel):
    """The caller's season across every league they play.

    Points and win rate aggregate honestly: every league scores ``round(odds × 10)``
    off the same scale, so a total across three of them is a real number. Rank does
    not, hence ``avg_rank`` carrying its own guard (see ``_MIN_MEMBERS_FOR_AVG``) and
    the per-league breakdown carrying the ranks that do mean something.
    """

    avg_rank: float | None
    # How many leagues the average actually spans — without it a reader cannot tell
    # a mean over three leagues from one over the single league big enough to count.
    avg_rank_leagues: int
    total_points: int
    picks_played: int
    picks_won: int
    win_rate_pct: int | None
    leagues_count: int
    per_league: list[PerLeagueSummary]


@router.get("/cross-league-summary", response_model=CrossLeagueSummary)
@limiter.limit("120/minute", key_func=per_user_key)
async def cross_league_summary(
    request: Request,
    user: CurrentUser,
    db: Db,
) -> CrossLeagueSummary:
    """The caller's record across all their leagues, plus this week in each.

    Five fixed queries, none of them per league: the caller's memberships, member
    counts, every league's season table at once, each league's latest round, and the
    picks on those rounds. Adding a sixth league adds rows, not round trips.
    """
    membership_rows = (
        await db.execute(
            select(League.id, League.slug, League.name)
            .join(LeagueMembership, LeagueMembership.league_id == League.id)
            .where(
                LeagueMembership.player_id == user.id,
                LeagueMembership.deleted_at.is_(None),
                League.deleted_at.is_(None),
            )
            .order_by(League.name)
        )
    ).all()

    if not membership_rows:
        return CrossLeagueSummary(
            avg_rank=None,
            avg_rank_leagues=0,
            total_points=0,
            picks_played=0,
            picks_won=0,
            win_rate_pct=None,
            leagues_count=0,
            per_league=[],
        )

    league_ids = [row.id for row in membership_rows]

    count_rows = (
        await db.execute(
            select(LeagueMembership.league_id, func.count().label("member_count"))
            .where(
                LeagueMembership.league_id.in_(league_ids),
                LeagueMembership.deleted_at.is_(None),
            )
            .group_by(LeagueMembership.league_id)
        )
    ).all()
    member_counts: dict[uuid.UUID, int] = {row.league_id: row.member_count for row in count_rows}

    # wc_2026_predictor reads rank from a stored LeaderboardSnapshot; this codebase has
    # no such table, so rank is computed the same way the leaderboard computes it.
    tables = await standings_by_league(db, league_ids)
    mine = {
        league_id: next((s for s in table if s.player_id == str(user.id)), None)
        for league_id, table in tables.items()
    }

    rounds = await _latest_rounds(db, league_ids, user.id)

    per_league: list[PerLeagueSummary] = []
    ranks_for_avg: list[int] = []
    for row in membership_rows:
        member_count = member_counts.get(row.id, 0)
        standing = mine.get(row.id)
        per_league.append(
            PerLeagueSummary(
                slug=row.slug,
                name=row.name,
                member_count=member_count,
                rank=standing.rank if standing else None,
                total_points=standing.total_points if standing else 0,
                picks_played=standing.picks_played if standing else 0,
                picks_won=standing.picks_won if standing else 0,
                current_round=rounds.get(row.id),
            )
        )
        if standing is not None and member_count >= _MIN_MEMBERS_FOR_AVG:
            ranks_for_avg.append(standing.rank)

    picks_played = sum(entry.picks_played for entry in per_league)
    picks_won = sum(entry.picks_won for entry in per_league)

    return CrossLeagueSummary(
        avg_rank=round(sum(ranks_for_avg) / len(ranks_for_avg), 2) if ranks_for_avg else None,
        avg_rank_leagues=len(ranks_for_avg),
        total_points=sum(entry.total_points for entry in per_league),
        picks_played=picks_played,
        picks_won=picks_won,
        win_rate_pct=round(100 * picks_won / picks_played) if picks_played else None,
        leagues_count=len(membership_rows),
        per_league=per_league,
    )


async def _latest_rounds(
    db: AsyncSession, league_ids: list[uuid.UUID], player_id: uuid.UUID
) -> dict[uuid.UUID, CurrentRound]:
    """Each league's current round with its coupon and the caller's leg, keyed by league.

    Two queries for the whole set. The first picks one row per league with a window
    function, ordered by :func:`src.services.gameweek.current_round_order` — the same
    rule :func:`~src.services.gameweek.latest_gameweek` applies one league at a time, so
    the home card and the pick screen always agree about which round is current. They
    are one rule spelled twice and must move together; home is where a disagreement
    shows, because it renders every league's card side by side. The second query pulls
    every pick on those rounds, because the coupon's leg count and combined price need
    all of them and the caller's own leg is one of the rows already in hand.
    """
    newest = (
        select(
            Gameweek.id,
            Gameweek.league_id,
            Gameweek.starts_on,
            Gameweek.status,
            Gameweek.locks_at_utc,
            Gameweek.picks_open_at_utc,
            func.row_number()
            .over(
                partition_by=Gameweek.league_id,
                order_by=current_round_order(),
            )
            .label("rn"),
        )
        .where(Gameweek.league_id.in_(league_ids))
        .subquery()
    )
    gameweek_rows = (await db.execute(select(newest).where(newest.c.rn == 1))).all()
    if not gameweek_rows:
        return {}

    # A round belongs to one league since Batch 14, so scoping the picks by round
    # already scopes them by league. Pairing the two anyway keeps a leg here the
    # same set `build_coupon` calls a leg, which filters on both.
    league_of = {row.id: row.league_id for row in gameweek_rows}
    pick_rows = (
        await db.execute(
            select(Pick, Fixture)
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(Pick.gameweek_id.in_(league_of))
        )
    ).all()

    legs: dict[uuid.UUID, list[Decimal]] = {}
    my_picks: dict[uuid.UUID, MyPick] = {}
    for pick, fixture in pick_rows:
        if pick.league_id != league_of[pick.gameweek_id]:
            continue
        legs.setdefault(pick.gameweek_id, []).append(pick.odds_at_pick)
        if pick.player_id == player_id:
            my_picks[pick.gameweek_id] = MyPick(
                fixture_id=str(fixture.id),
                home=fixture.home,
                away=fixture.away,
                market=pick.market.value,
                outcome=pick.outcome.value,
                runner_name=pick.runner_name,
                odds=float(pick.odds_at_pick),
                status=pick.status.value,
            )

    return {
        row.league_id: CurrentRound(
            gameweek_id=str(row.id),
            starts_on=row.starts_on,
            status=row.status.value,
            locks_at_utc=row.locks_at_utc,
            picks_open_at_utc=row.picks_open_at_utc,
            leg_count=len(legs.get(row.id, [])),
            combined_odds=float(combined_odds(legs.get(row.id, []))),
            my_pick=my_picks.get(row.id),
        )
        for row in gameweek_rows
    }
