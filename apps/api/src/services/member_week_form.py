"""SQL-only settled member/week projection shared by Home and ordinary standings."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import String, and_, case, cast, exists, func, literal, or_, select, union_all
from sqlalchemy.sql.selectable import Subquery

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.models.two_game import FantasyPick, MembershipInterval, TwoGame, TwoGameRollout
from src.services.season_calendar import season_bounds


def member_weeks(
    league_ids: Collection[uuid.UUID],
    season: int,
    *,
    two_game_leagues: Collection[uuid.UUID],
    player_id: uuid.UUID | None = None,
) -> Subquery:
    """One row per eligible member/week; no Group rows or per-leg form window."""
    first, last = season_bounds(season)
    legacy = (
        select(
            Pick.league_id,
            Pick.player_id,
            Gameweek.id.label("week_id"),
            Gameweek.starts_on.label("week_label"),
            literal("legacy").label("format"),
            cast(Pick.status, String).label("status"),
            func.coalesce(Pick.points_awarded, 0).label("weekly_points"),
            literal(1).label("slots_filled"),
        )
        .join(Gameweek, Gameweek.id == Pick.gameweek_id)
        .where(
            Pick.league_id.in_(league_ids),
            Gameweek.format == "legacy",
            Gameweek.status == GameweekStatus.settled,
            Gameweek.starts_on.between(first, last),
            Pick.status.in_((PickStatus.won, PickStatus.lost, PickStatus.void)),
        )
    )
    historical_member = (
        exists()
        .where(
            MembershipInterval.league_id == TwoGame.league_id,
            MembershipInterval.player_id == LeagueMembership.player_id,
            MembershipInterval.joined_at <= TwoGame.locks_at,
            or_(
                MembershipInterval.left_at.is_(None), MembershipInterval.left_at > TwoGame.locks_at
            ),
        )
        .correlate(TwoGame, LeagueMembership)
    )
    accepted_owner = (
        exists()
        .where(
            FantasyPick.game_id == TwoGame.id,
            FantasyPick.player_id == LeagueMembership.player_id,
        )
        .correlate(TwoGame, LeagueMembership)
    )
    filled = func.count(FantasyPick.id)
    pending = func.sum(case((FantasyPick.status == "pending", 1), else_=0))
    nonvoid = func.sum(case((FantasyPick.status != "void", 1), else_=0))
    fantasy = (
        select(
            TwoGame.league_id,
            LeagueMembership.player_id,
            TwoGame.week_id,
            Gameweek.starts_on.label("week_label"),
            literal("two_game").label("format"),
            case(
                (filled == 0, "no_entry"),
                (pending > 0, "pending"),
                (nonvoid == 0, "all_void"),
                else_="scored",
            ).label("status"),
            func.coalesce(func.sum(FantasyPick.points_awarded), 0).label("weekly_points"),
            filled.label("slots_filled"),
        )
        .select_from(TwoGame)
        .join(Gameweek, Gameweek.id == TwoGame.week_id)
        .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
        .join(LeagueMembership, LeagueMembership.league_id == TwoGame.league_id)
        .outerjoin(
            FantasyPick,
            and_(
                FantasyPick.game_id == TwoGame.id,
                FantasyPick.player_id == LeagueMembership.player_id,
            ),
        )
        .where(
            TwoGame.league_id.in_(two_game_leagues),
            Gameweek.format == "two_game",
            Gameweek.starts_on >= TwoGameRollout.first_week,
            TwoGame.kind == "fantasy",
            TwoGame.finalized_at.is_not(None),
            Gameweek.starts_on.between(first, last),
            or_(historical_member, accepted_owner),
        )
        .group_by(
            TwoGame.league_id, LeagueMembership.player_id, TwoGame.week_id, Gameweek.starts_on
        )
    )
    if player_id is not None:
        legacy = legacy.where(Pick.player_id == player_id)
        fantasy = fantasy.where(LeagueMembership.player_id == player_id)
    return union_all(legacy, fantasy).subquery("member_weeks")


def recent_member_weeks(weeks: Subquery, limit: int) -> Subquery:
    ranked = select(
        weeks,
        func.row_number()
        .over(
            partition_by=(weeks.c.league_id, weeks.c.player_id),
            order_by=(weeks.c.week_label.desc(), weeks.c.week_id.desc()),
        )
        .label("position"),
    ).subquery("ranked_member_weeks")
    return select(ranked).where(ranked.c.position <= limit).subquery("recent_member_weeks")
