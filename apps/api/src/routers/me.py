"""Endpoints scoped to the authenticated user (``/api/v1/me``).

Everything else in the API is read through one league: a slate, a coupon, a table and
a member's record all take a slug. That is right for the things a league owns, and
wrong for the two screens that are about the *member* — home, and their own profile —
because a member in three leagues has three of everything and no single slug is the
answer.

``GET /me/cross-league-summary`` is the read those screens share. It costs the same
nine queries whether the caller is in one league or six — none of them per league.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.rate_limit import limiter, per_user_key
from src.schemas import UtcDatetime
from src.services.coupon import combined_odds
from src.services.football_provider import season_for
from src.services.gameweek import PICKABLE_STATES, current_round_order
from src.services.scoring import LONGSHOT_ODDS, FormRound, resolve_season, standings_by_league

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
    #: What this pick scored, once the round settled. ``None`` while it is still running,
    #: and on a lost or void pick, which is the difference between nothing and zero.
    #: Batch 79; optional with a default because the web app deploys ahead of the API.
    points_awarded: int | None = None


class CurrentRound(BaseModel):
    """A league's latest round as it concerns the caller — the home card's body.

    ``my_pick`` is ``None`` when they have not claimed a selection yet, which is the
    state the card exists to shout about while the round is still open.
    """

    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: UtcDatetime
    # When picks open, or ``null`` when the league announces no opening (Batch 27). The
    # card counts down to whichever of the two instants is next.
    picks_open_at_utc: UtcDatetime | None
    # The whole league's acca for the round, so the card can say what is riding on it.
    leg_count: int
    combined_odds: float
    my_pick: MyPick | None


class LastResult(BaseModel):
    """The most recently settled round of a league, as it concerns the caller.

    **This is deliberately not read off ``current_round``.** A settled round only stays
    current while nothing else outranks it, and :func:`~src.services.gameweek.current_round_order`
    ranks a round accepting picks above one already started — which, for a league that
    announces no opening, is next week's round from the moment discovery writes it. On
    those leagues home would move on the same day and the member would never see how their
    week went; on a league that *does* announce an opening the identical code works, so the
    feature would appear or not appear according to a settings toggle nobody would connect
    to it. It gets its own query.
    """

    gameweek_id: str
    starts_on: date
    #: What members call the round. ``None`` on a round discovered before Batch 41.
    number: int | None
    leg_count: int
    #: How many of those legs landed. ``all_won`` alone cannot tell five of six from none.
    picks_won: int
    combined_odds: float
    all_won: bool | None
    my_pick: MyPick | None
    #: Places gained over this round — positive up, negative down, ``None`` when the
    #: caller had no row in the table before it. Differenced against the same ranking
    #: rule that produced ``rank``, with this one round excluded; see
    #: :func:`~src.services.scoring.standings_by_league`.
    #:
    #: Also ``None`` when the round being reported is not in the season the table covers
    #: (Batch 96). The last result a league played can be June's while the table is
    #: already August's, and "you moved up two" over a round the table does not count is
    #: not a smaller number — it is a statement about nothing.
    rank_movement: int | None = None


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
    # Batch 70. Optional with defaults for the window where this app is deployed and the
    # API is not; see `Standing` for why the two denominators differ.
    picks_priced: int = 0
    cumulative_odds: float = 0.0
    average_odds: float | None = None
    points_per_pick: float | None = None
    best_return: int | None = None
    longshot_picks: int = 0
    favourite_picks: int = 0
    #: The last five settled rounds, most recent first (Batch 81). Read straight off the
    #: league's own season table, so home and the leaderboard can never draw different
    #: runs for the same member.
    recent_form: list[FormRound] = []
    # `None` when the league has no rounds yet.
    current_round: CurrentRound | None
    # Batch 79, both optional with defaults for the deploy gap.
    #: The week just gone, whether or not it is still the current round.
    last_result: LastResult | None = None
    #: When this league next starts accepting picks, if that instant is still ahead.
    #: `None` when no future round announces an opening — including the ordinary case of
    #: a league that announces none at all, whose next round is claimable on discovery.
    next_opens_at_utc: UtcDatetime | None = None


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
    # Batch 70, summed across leagues rather than averaged: every league prices in the
    # same decimal odds, so a cumulative total across three of them is a real number,
    # and the average is that total over the picks that actually ran — not the mean of
    # three per-league means, which would weight a one-pick league like a full season.
    picks_priced: int = 0
    cumulative_odds: float = 0.0
    average_odds: float | None = None
    points_per_pick: float | None = None
    best_return: int | None = None
    longshot_picks: int = 0
    favourite_picks: int = 0
    longshot_odds: float = 3.0
    leagues_count: int
    per_league: list[PerLeagueSummary]


@router.get("/cross-league-summary", response_model=CrossLeagueSummary)
@limiter.limit("120/minute", key_func=per_user_key)
async def cross_league_summary(
    request: Request,
    user: CurrentUser,
    db: Db,
) -> CrossLeagueSummary:
    """The caller's record across all their leagues, plus this week and last in each.

    Nine fixed queries, none of them per league: the caller's memberships, member counts,
    every league's season table at once, each league's latest round and the picks on it,
    each league's most recently *settled* round and the picks on that, the next announced
    opening, and the season table again with those settled rounds left out — which is
    where rank movement comes from. Adding a sixth league adds rows, not round trips.
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
    results = await _last_results(db, league_ids, user.id)
    openings = await _next_openings(db, league_ids)

    # Movement is the table as it stood *before* the round being reported, differenced
    # against the table now. Both come from `standings_by_league`, so the number attached
    # to a rank can never have been produced by different arithmetic to the rank itself.
    # Only rounds inside the season the table covers can move a rank in it. Excluding one
    # from a season it was never joined into would rewind nothing and report a confident
    # zero, which is worse than the `None` the boundary check below leaves in its place.
    this_season = resolve_season(None)
    settled_ids = [
        uuid.UUID(result.gameweek_id)
        for result in results.values()
        if season_for(result.starts_on) == this_season
    ]
    # `with_form=False` is the one place it belongs (Batch 81): this table exists to be
    # subtracted from the one above, never to be drawn, so a run of recent results on it
    # would be a query paid for and thrown away.
    before = (
        await standings_by_league(db, league_ids, settled_ids, with_form=False)
        if settled_ids
        else {}
    )

    per_league: list[PerLeagueSummary] = []
    ranks_for_avg: list[int] = []
    for row in membership_rows:
        member_count = member_counts.get(row.id, 0)
        standing = mine.get(row.id)
        result = results.get(row.id)
        if (
            result is not None
            and standing is not None
            and season_for(result.starts_on) == this_season
        ):
            was = next((s for s in before.get(row.id, []) if s.player_id == str(user.id)), None)
            # Positive is upward, so a rank that fell from 5 to 3 reads as +2.
            result.rank_movement = was.rank - standing.rank if was is not None else None
        per_league.append(
            PerLeagueSummary(
                slug=row.slug,
                name=row.name,
                member_count=member_count,
                rank=standing.rank if standing else None,
                total_points=standing.total_points if standing else 0,
                picks_played=standing.picks_played if standing else 0,
                picks_won=standing.picks_won if standing else 0,
                picks_priced=standing.picks_priced if standing else 0,
                cumulative_odds=standing.cumulative_odds if standing else 0.0,
                average_odds=standing.average_odds if standing else None,
                points_per_pick=standing.points_per_pick if standing else None,
                best_return=standing.best_return if standing else None,
                longshot_picks=standing.longshot_picks if standing else 0,
                favourite_picks=standing.favourite_picks if standing else 0,
                recent_form=standing.recent_form if standing else [],
                current_round=rounds.get(row.id),
                last_result=result,
                next_opens_at_utc=openings.get(row.id),
            )
        )
        if standing is not None and member_count >= _MIN_MEMBERS_FOR_AVG:
            ranks_for_avg.append(standing.rank)

    picks_played = sum(entry.picks_played for entry in per_league)
    picks_won = sum(entry.picks_won for entry in per_league)
    total_points = sum(entry.total_points for entry in per_league)
    picks_priced = sum(entry.picks_priced for entry in per_league)
    cumulative_odds = sum(entry.cumulative_odds for entry in per_league)
    returns = [entry.best_return for entry in per_league if entry.best_return is not None]

    return CrossLeagueSummary(
        avg_rank=round(sum(ranks_for_avg) / len(ranks_for_avg), 2) if ranks_for_avg else None,
        avg_rank_leagues=len(ranks_for_avg),
        total_points=total_points,
        picks_played=picks_played,
        picks_won=picks_won,
        win_rate_pct=round(100 * picks_won / picks_played) if picks_played else None,
        picks_priced=picks_priced,
        cumulative_odds=round(cumulative_odds, 2),
        average_odds=round(cumulative_odds / picks_priced, 2) if picks_priced else None,
        points_per_pick=round(total_points / picks_played, 2) if picks_played else None,
        best_return=max(returns) if returns else None,
        longshot_picks=sum(entry.longshot_picks for entry in per_league),
        favourite_picks=sum(entry.favourite_picks for entry in per_league),
        longshot_odds=float(LONGSHOT_ODDS),
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


async def _last_results(
    db: AsyncSession, league_ids: list[uuid.UUID], player_id: uuid.UUID
) -> dict[uuid.UUID, LastResult]:
    """Each league's most recently settled round, keyed by league.

    Two queries for the whole set, the same shape as :func:`_latest_rounds`: one row per
    league by window function, then every pick on those rounds. It is a *separate* read
    from the current round on purpose — see :class:`LastResult` for why reading it off
    ``current_round`` shows the member their week on some leagues and not others.

    Ordered by ``starts_on`` alone rather than by
    :func:`~src.services.gameweek.current_round_order`: among rounds that have settled,
    the most recent one is simply the latest, and none of that function's four tiers
    discriminates within a set where every row is terminal.
    """
    newest = (
        select(
            Gameweek.id,
            Gameweek.league_id,
            Gameweek.starts_on,
            Gameweek.number,
            func.row_number()
            .over(partition_by=Gameweek.league_id, order_by=Gameweek.starts_on.desc())
            .label("rn"),
        )
        .where(
            Gameweek.league_id.in_(league_ids),
            Gameweek.status == GameweekStatus.settled,
        )
        .subquery()
    )
    gameweek_rows = (await db.execute(select(newest).where(newest.c.rn == 1))).all()
    if not gameweek_rows:
        return {}

    # A round belongs to one league since Batch 14, so scoping by round already scopes by
    # league. Pairing them anyway keeps a leg here the same set `build_coupon` calls a leg.
    league_of = {row.id: row.league_id for row in gameweek_rows}
    pick_rows = (
        await db.execute(
            select(Pick, Fixture)
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(Pick.gameweek_id.in_(league_of))
        )
    ).all()

    legs: dict[uuid.UUID, list[Decimal]] = {}
    statuses: dict[uuid.UUID, list[PickStatus]] = {}
    my_picks: dict[uuid.UUID, MyPick] = {}
    for pick, fixture in pick_rows:
        if pick.league_id != league_of[pick.gameweek_id]:
            continue
        legs.setdefault(pick.gameweek_id, []).append(pick.odds_at_pick)
        statuses.setdefault(pick.gameweek_id, []).append(pick.status)
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
                points_awarded=pick.points_awarded,
            )

    return {
        row.league_id: LastResult(
            gameweek_id=str(row.id),
            starts_on=row.starts_on,
            number=row.number,
            leg_count=len(legs.get(row.id, [])),
            picks_won=sum(1 for s in statuses.get(row.id, []) if s is PickStatus.won),
            combined_odds=float(combined_odds(legs.get(row.id, []))),
            # Mirrors `gameweek_results`: a round nobody picked on is vacuously settled
            # and has no coupon outcome, rather than a true one over an empty set.
            all_won=(
                all(s is PickStatus.won for s in statuses[row.id]) if statuses.get(row.id) else None
            ),
            my_pick=my_picks.get(row.id),
        )
        for row in gameweek_rows
    }


async def _next_openings(
    db: AsyncSession, league_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When each league next starts accepting picks, for the leagues where that is ahead.

    A league with no key here has nothing to count down to, and there are two very
    different reasons for that which the card must not conflate: either no future round
    announces an opening at all — the ordinary configuration, where a round is claimable
    from the moment discovery writes it — or the next opening has already passed, in which
    case the current round's own countdown is the one to show.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = (
        await db.execute(
            select(
                Gameweek.league_id,
                func.min(Gameweek.picks_open_at_utc).label("opens_at"),
            )
            .where(
                Gameweek.league_id.in_(league_ids),
                Gameweek.status.in_(PICKABLE_STATES),
                Gameweek.picks_open_at_utc.is_not(None),
                Gameweek.picks_open_at_utc > now,
            )
            .group_by(Gameweek.league_id)
        )
    ).all()
    return {row.league_id: row.opens_at for row in rows}
