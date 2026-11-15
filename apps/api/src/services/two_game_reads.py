"""Snapshot reads with a fixed number of query groups and no quote/provider port.

The API boundary supplies its installation gate explicitly. The same loader can
compose a payment notice inside its existing transaction without opening another
connection, writing dues, or changing how pooled payments are allocated.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Integer, and_, cast, exists, func, literal, or_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import DUE_KINDS, LedgerEntry, LedgerKind
from src.models.pick import Pick
from src.models.profile import Profile
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    MembershipInterval,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameRollout,
)
from src.services.dues import MemberLedger
from src.services.provider_budget import naive_utc, utc_now
from src.services.two_game_read_models import HomeGames, LeagueGames, WeekResults
from src.services.two_game_storage import LONDON
from src.services.weekly_fees import billing_label


class GameReadRefused(Exception):
    def __init__(self, code: str = "NOT_FOUND", status: int = 404):
        self.code, self.status = code, status


def encode_cursor(league_id: uuid.UUID, parent: Gameweek) -> str:
    raw = json.dumps([str(league_id), parent.starts_on.isoformat(), str(parent.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str, league_id: uuid.UUID) -> tuple[date, uuid.UUID]:
    try:
        if len(value) > 256:
            raise ValueError
        decoded = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(decoded, list)
            or len(decoded) != 3
            or not all(isinstance(part, str) for part in decoded)
        ):
            raise ValueError
        owner, label, parent = decoded
        if uuid.UUID(owner) != league_id:
            raise ValueError
        return date.fromisoformat(label), uuid.UUID(parent)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise GameReadRefused("INVALID_CURSOR", 422) from exc


@dataclass
class ReadData:
    player_id: uuid.UUID
    now: datetime
    season: int
    leagues: dict[uuid.UUID, League] = field(default_factory=dict)
    members: dict[uuid.UUID, LeagueMembership] = field(default_factory=dict)
    rollouts: dict[uuid.UUID, TwoGameRollout] = field(default_factory=dict)
    active: set[uuid.UUID] = field(default_factory=set)
    parents: dict[uuid.UUID, Gameweek] = field(default_factory=dict)
    selected_parents: set[uuid.UUID] = field(default_factory=set)
    archive: set[uuid.UUID] = field(default_factory=set)
    cursors: dict[uuid.UUID, str] = field(default_factory=dict)
    games: list[TwoGame] = field(default_factory=list)
    roster: list[tuple[LeagueMembership, Profile]] = field(default_factory=list)
    intervals: list[MembershipInterval] = field(default_factory=list)
    group: list[GroupPick] = field(default_factory=list)
    fantasy: list[FantasyPick] = field(default_factory=list)
    operations: dict[tuple[uuid.UUID, int], GameOperation] = field(default_factory=dict)
    legacy: dict[uuid.UUID, Pick] = field(default_factory=dict)
    counts: dict[uuid.UUID, int] = field(default_factory=dict)
    ledgers: dict[uuid.UUID, MemberLedger] = field(default_factory=dict)
    recorded_fees: dict[uuid.UUID, int] = field(default_factory=dict)
    calendar: dict[uuid.UUID, ProviderWork] = field(default_factory=dict)
    snapshots: dict[str, ProviderSnapshot] = field(default_factory=dict)


async def load_read_data(
    db: AsyncSession,
    player_id: uuid.UUID,
    now: datetime,
    *,
    two_games_enabled: bool,
    league_id: uuid.UUID | None = None,
    cursor: str | None = None,
    page_size: int = 20,
    season: int | None = None,
    week_id: uuid.UUID | None = None,
) -> ReadData:
    from src.services.football_provider import season_for
    from src.services.season_calendar import season_bounds

    if cursor is not None and league_id is None:
        raise GameReadRefused("INVALID_CURSOR", 422)
    if not 1 <= page_size <= 50:
        raise GameReadRefused("INVALID_REQUEST", 422)
    now = naive_utc(now)
    data = ReadData(
        player_id,
        now,
        season
        if season is not None
        else season_for(now.replace(tzinfo=UTC).astimezone(LONDON).date()),
    )
    query = (
        select(LeagueMembership, League, TwoGameRollout)
        .join(League, League.id == LeagueMembership.league_id)
        .outerjoin(TwoGameRollout, TwoGameRollout.league_id == League.id)
        .where(LeagueMembership.player_id == player_id, League.deleted_at.is_(None))
    )
    if league_id is None:
        query = query.where(LeagueMembership.deleted_at.is_(None))
    else:
        query = query.where(League.id == league_id)
    for member, league, rollout in (await db.execute(query)).all():
        data.members[league.id], data.leagues[league.id] = member, league
        if rollout is not None:
            data.rollouts[league.id] = rollout
            if two_games_enabled and rollout.enabled:
                data.active.add(league.id)
    if league_id is not None and league_id not in data.leagues:
        raise GameReadRefused()
    if not data.leagues:
        return data
    league_ids = list(data.leagues)
    if week_id is not None:
        requested_parent = await db.scalar(
            select(Gameweek).where(Gameweek.id == week_id, Gameweek.league_id.in_(league_ids))
        )
        if (
            requested_parent is None
            or requested_parent.format == "two_game"
            and requested_parent.league_id not in data.active
        ):
            raise GameReadRefused()
        data.parents[requested_parent.id] = requested_parent
        data.selected_parents.add(requested_parent.id)
    else:
        retained = [key for key, member in data.members.items() if member.deleted_at is not None]
        retained_pending = and_(
            TwoGame.league_id.in_(retained),
            TwoGame.locks_at <= now,
            TwoGame.finalized_at.is_(None),
            or_(
                exists().where(GroupPick.game_id == TwoGame.id, GroupPick.player_id == player_id),
                exists().where(
                    FantasyPick.game_id == TwoGame.id, FantasyPick.player_id == player_id
                ),
                exists().where(
                    MembershipInterval.league_id == TwoGame.league_id,
                    MembershipInterval.player_id == player_id,
                    MembershipInterval.joined_at <= TwoGame.locks_at,
                    or_(
                        MembershipInterval.left_at.is_(None),
                        MembershipInterval.left_at > TwoGame.locks_at,
                    ),
                ),
            ),
        )
        history = select(
            Gameweek.id.label("id"),
            Gameweek.league_id.label("league_id"),
            func.row_number()
            .over(
                partition_by=Gameweek.league_id,
                order_by=(Gameweek.starts_on.desc(), Gameweek.id.desc()),
            )
            .label("position"),
        ).where(
            Gameweek.league_id.in_(league_ids),
            or_(
                and_(Gameweek.format == "legacy", Gameweek.status == GameweekStatus.settled),
                and_(
                    Gameweek.league_id.in_(data.active),
                    exists().where(
                        TwoGame.week_id == Gameweek.id,
                        or_(
                            TwoGame.finalized_at.is_not(None),
                            TwoGame.status == "cancelled",
                            retained_pending,
                        ),
                    ),
                ),
            ),
        )
        if season is not None:
            history = history.where(Gameweek.starts_on.between(*season_bounds(season)))
        if cursor is not None:
            assert league_id is not None
            label, identifier = decode_cursor(cursor, league_id)
            history = history.where(
                tuple_(Gameweek.starts_on, Gameweek.id)
                < tuple_(literal(label), literal(identifier))
            )
        ranked = history.subquery("history_parents")
        histories = list(
            await db.scalars(
                select(Gameweek)
                .join(ranked, ranked.c.id == Gameweek.id)
                .where(ranked.c.position <= page_size + 1)
                .order_by(Gameweek.league_id, Gameweek.starts_on.desc(), Gameweek.id.desc())
            )
        )
        groups: dict[uuid.UUID, list[Gameweek]] = defaultdict(list)
        for parent in histories:
            groups[parent.league_id].append(parent)
        for owner, parents in groups.items():
            for parent in parents[:page_size]:
                data.parents[parent.id] = parent
                data.archive.add(parent.id)
                data.selected_parents.add(parent.id)
            if len(parents) > page_size:
                data.cursors[owner] = encode_cursor(owner, parents[page_size - 1])
        live_members = [key for key, member in data.members.items() if member.deleted_at is None]
        legacy = await db.scalars(
            select(Gameweek).where(
                Gameweek.league_id.in_(live_members),
                Gameweek.format == "legacy",
                or_(
                    Gameweek.starts_on == billing_label(now),
                    and_(
                        Gameweek.status != GameweekStatus.settled,
                        or_(
                            Gameweek.picks_open_at_utc.is_(None), Gameweek.picks_open_at_utc <= now
                        ),
                    ),
                ),
            )
        )
        for parent in legacy:
            data.parents[parent.id] = parent
            data.selected_parents.add(parent.id)
            data.archive.discard(parent.id)
    future = (
        select(
            TwoGame.id,
            func.row_number()
            .over(partition_by=TwoGame.league_id, order_by=(TwoGame.opens_at, TwoGame.id))
            .label("position"),
        )
        .where(
            TwoGame.league_id.in_(data.active),
            TwoGame.kind == "fantasy",
            TwoGame.opens_at > now,
            TwoGame.status != "cancelled",
        )
        .subquery("announced_fantasy")
    )
    games = (
        select(TwoGame, Gameweek)
        .join(Gameweek, Gameweek.id == TwoGame.week_id)
        .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
        .where(TwoGame.league_id.in_(data.active), Gameweek.starts_on >= TwoGameRollout.first_week)
    )
    games = games.where(
        or_(
            TwoGame.league_id.in_(
                [key for key, member in data.members.items() if member.deleted_at is None]
            ),
            TwoGame.locks_at <= now,
            TwoGame.status.in_(["settled", "cancelled"]),
        )
    )
    if week_id is not None:
        games = games.where(TwoGame.week_id == week_id)
    else:
        live_members = [key for key, member in data.members.items() if member.deleted_at is None]
        live = and_(
            TwoGame.league_id.in_(live_members),
            or_(
                Gameweek.starts_on == billing_label(now),
                and_(
                    TwoGame.status != "cancelled",
                    or_(
                        and_(TwoGame.opens_at <= now, TwoGame.locks_at > now),
                        and_(TwoGame.locks_at <= now, TwoGame.finalized_at.is_(None)),
                        TwoGame.id.in_(select(future.c.id).where(future.c.position == 1)),
                    ),
                ),
            ),
        )
        games = games.where(or_(TwoGame.week_id.in_(data.archive), live))
    for game, parent in (await db.execute(games.order_by(Gameweek.starts_on, TwoGame.kind))).all():
        data.games.append(game)
        data.parents[parent.id] = parent
        data.selected_parents.add(parent.id)
    if week_id is not None and data.parents[week_id].format == "two_game" and not data.games:
        raise GameReadRefused()
    ledger_rows = (
        await db.execute(
            select(
                LedgerEntry.league_id,
                LedgerEntry.kind,
                LedgerEntry.amount_pence,
                LedgerEntry.gameweek_id,
            ).where(LedgerEntry.league_id.in_(league_ids), LedgerEntry.player_id == player_id)
        )
    ).all()
    for owner, kind, amount, parent_id in ledger_rows:
        ledger = data.ledgers.setdefault(owner, MemberLedger())
        if kind in DUE_KINDS:
            ledger.owed_by_round[parent_id] = ledger.owed_by_round.get(parent_id, 0) - amount
        else:
            ledger.credit_pence += amount
    through = max([billing_label(now), *(parent.starts_on for parent in data.parents.values())])
    owed_ids = {
        identifier
        for ledger in data.ledgers.values()
        for identifier in ledger.owed_by_round
        if identifier is not None
    }
    for parent in await db.scalars(
        select(Gameweek).where(
            or_(
                Gameweek.id.in_(owed_ids),
                and_(
                    Gameweek.league_id.in_(data.active),
                    Gameweek.format == "two_game",
                    Gameweek.starts_on <= through,
                ),
            )
        )
    ):
        data.parents[parent.id] = parent
    data.roster = [
        (member, profile)
        for member, profile in (
            await db.execute(
                select(LeagueMembership, Profile)
                .join(Profile, Profile.id == LeagueMembership.player_id)
                .where(LeagueMembership.league_id.in_(league_ids))
            )
        ).all()
    ]
    data.intervals = list(
        await db.scalars(
            select(MembershipInterval).where(MembershipInterval.league_id.in_(league_ids))
        )
    )
    game_ids = [game.id for game in data.games]
    data.group = list(await db.scalars(select(GroupPick).where(GroupPick.game_id.in_(game_ids))))
    data.fantasy = list(
        await db.scalars(select(FantasyPick).where(FantasyPick.game_id.in_(game_ids)))
    )
    operations = await db.scalars(
        select(GameOperation)
        .where(GameOperation.game_id.in_(game_ids), GameOperation.player_id == player_id)
        .distinct(GameOperation.game_id, GameOperation.slot)
        .order_by(
            GameOperation.game_id,
            GameOperation.slot,
            cast(GameOperation.response["revision"].astext, Integer).desc(),
        )
    )
    data.operations = {(operation.game_id, operation.slot): operation for operation in operations}
    legacy_ids = [
        identifier
        for identifier in data.selected_parents
        if data.parents[identifier].format == "legacy"
    ]
    data.legacy = {
        pick.gameweek_id: pick
        for pick in await db.scalars(
            select(Pick).where(Pick.gameweek_id.in_(legacy_ids), Pick.player_id == player_id)
        )
    }
    data.counts = {
        key: count
        for key, count in (
            await db.execute(
                select(Pick.gameweek_id, func.count())
                .where(Pick.gameweek_id.in_(legacy_ids))
                .group_by(Pick.gameweek_id)
            )
        ).all()
    }
    data.recorded_fees = {
        key: amount
        for key, amount in (
            await db.execute(
                select(LedgerEntry.gameweek_id, func.max(-LedgerEntry.amount_pence))
                .where(
                    LedgerEntry.gameweek_id.in_(legacy_ids),
                    LedgerEntry.kind == LedgerKind.round_due,
                )
                .group_by(LedgerEntry.gameweek_id)
            )
        ).all()
        if key is not None
    }
    calendars = await db.scalars(
        select(ProviderWork).where(
            ProviderWork.key.in_([f"calendar:{owner}" for owner in league_ids])
        )
    )
    data.calendar = {uuid.UUID(row.key.split(":", 1)[1]): row for row in calendars}
    data.snapshots = {
        row.key: row
        for row in await db.scalars(
            select(ProviderSnapshot).where(
                ProviderSnapshot.key.in_([f"game-result:v1:{game.id}" for game in data.games])
            )
        )
    }
    return data


def pick_payload(pick: GroupPick | FantasyPick | Pick) -> dict[str, Any]:
    payload: dict[str, Any] = dict(
        id=str(pick.id),
        player_id=str(pick.player_id),
        fixture_id=str(pick.fixture_id),
        market=str(pick.market),
        outcome=str(pick.outcome),
        runner_name=pick.runner_name,
        result=str(pick.status),
    )
    if isinstance(pick, Pick):
        payload.update(odds=str(pick.odds_at_pick), points=pick.points_awarded)
    else:
        payload.update(
            league_id=str(pick.league_id),
            week_id=str(pick.week_id),
            game_id=str(pick.game_id),
            game_kind=pick.game_kind,
            revision=pick.revision,
            operation_id=str(pick.operation_id),
        )
        if isinstance(pick, FantasyPick):
            payload.update(
                slot=pick.slot,
                frozen_odds=str(pick.frozen_odds),
                quoted_at=pick.quoted_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z"),
                provider=pick.provider,
                bookmaker=pick.bookmaker,
                points=pick.points_awarded or 0,
            )
    return payload


def addressed_entry(data: ReadData, game: TwoGame, slot: int) -> dict[str, Any]:
    picks: Sequence[GroupPick | FantasyPick]
    if game.kind == "group":
        picks = data.group
    else:
        picks = data.fantasy
    pick = next(
        (
            row
            for row in picks
            if row.game_id == game.id
            and row.player_id == data.player_id
            and (not isinstance(row, FantasyPick) or row.slot == slot)
        ),
        None,
    )
    operation = data.operations.get((game.id, slot))
    revision = int(operation.response["revision"]) if operation else 0
    payload = dict(
        league_id=str(game.league_id),
        week_id=str(game.week_id),
        game_id=str(game.id),
        game_kind=game.kind,
        pick=pick_payload(pick) if pick else None,
        revision=max(revision, pick.revision if pick else 0),
        operation_id=str(pick.operation_id)
        if pick
        else str(operation.operation_id)
        if operation
        else None,
    )
    if game.kind == "fantasy":
        payload["slot"] = slot
    return payload


def audience(data: ReadData, game: TwoGame) -> set[uuid.UUID]:
    picks: Sequence[GroupPick | FantasyPick]
    if game.kind == "group":
        picks = data.group
    else:
        picks = data.fantasy
    owners = {row.player_id for row in picks if row.game_id == game.id}
    if data.now < game.locks_at:
        return owners | {
            member.player_id
            for member, profile in data.roster
            if member.league_id == game.league_id
            and member.deleted_at is None
            and profile.deleted_at is None
            and profile.is_active
        }
    return owners | {
        interval.player_id
        for interval in data.intervals
        if interval.league_id == game.league_id
        and interval.joined_at <= game.locks_at
        and (interval.left_at is None or interval.left_at > game.locks_at)
    }


def game_state(data: ReadData, game: TwoGame) -> str:
    if data.rollouts[game.league_id].suspended:
        return "suspended"
    if game.status == "cancelled":
        return "cancelled"
    if data.now >= game.locks_at or game.status == "settled":
        return "locked"
    calendar = data.calendar.get(game.league_id)
    if (
        data.now < game.opens_at
        or calendar
        and calendar.payload.get("state") == "schedule_conflict"
    ):
        return "not_open"
    return "open"


async def project_read_data(
    db: AsyncSession, data: ReadData, *, include_stats: bool = True
) -> HomeGames:
    from src.display_name import public_name
    from src.services.gameweek import pick_refusal
    from src.services.scoring import standings_by_league
    from src.services.season_calendar import labels_for_gameweeks
    from src.services.two_game_read_history import legacy_fee, weekly_forms
    from src.services.two_game_read_models import FantasyCard, GroupCard, LegacyRoundCard
    from src.services.two_game_results import fantasy_outcome, group_outcome
    from src.services.weekly_fees import Interval, project_loaded_fees

    if not data.leagues:
        return HomeGames(leagues=[])
    stats = (
        await standings_by_league(db, list(data.leagues), with_form=False, season=data.season)
        if include_stats
        else {}
    )
    forms = (
        await weekly_forms(
            db, data.player_id, data.leagues, data.season, two_game_leagues=data.active
        )
        if include_stats
        else {}
    )
    labels = await labels_for_gameweeks(
        db, [parent for parent in data.parents.values() if parent.format == "legacy"]
    )
    names = {profile.id: public_name(profile.display_name) for _, profile in data.roster}
    output = []
    for owner, league in data.leagues.items():
        own_games = [game for game in data.games if game.league_id == owner]
        member = data.members[owner]
        projection = None
        if owner in data.active:
            through = max(
                [
                    billing_label(data.now),
                    *(data.parents[game.week_id].starts_on for game in own_games),
                ]
            )
            projection = project_loaded_fees(
                league,
                data.rollouts[owner].first_week,
                [
                    Interval(row.id, row.joined_at, row.left_at)
                    for row in data.intervals
                    if row.league_id == owner and row.player_id == data.player_id
                ],
                member if member.deleted_at is None else None,
                data.ledgers.get(owner),
                data.parents,
                {
                    parent.starts_on: parent.id
                    for parent in data.parents.values()
                    if parent.league_id == owner and parent.format == "two_game"
                },
                through,
                data.now,
            )
        cards: list[GroupCard | FantasyCard] = []
        next_opening = min(
            [
                game.opens_at
                for game in own_games
                if game.kind == "fantasy" and game.opens_at > data.now
            ],
            default=None,
        )
        for game in own_games:
            assert projection is not None
            parent = data.parents[game.week_id]
            destination = f"/leagues/{owner}/weeks/{parent.id}/{game.kind}"
            live = member.deleted_at is None and (
                parent.starts_on == billing_label(data.now)
                or game.status != "cancelled"
                and (
                    game.opens_at <= data.now < game.locks_at
                    or data.now >= game.locks_at
                    and game.finalized_at is None
                    or game.kind == "fantasy"
                    and game.opens_at == next_opening
                )
            )
            final = game.finalized_at is not None or game.status == "settled"
            base: dict[str, Any] = dict(
                league_id=owner,
                week_id=parent.id,
                game_id=game.id,
                week_label=parent.starts_on,
                week_number=str(parent.number),
                destination=destination,
                opens_at=game.opens_at,
                locks_at=game.locks_at,
                window_start=game.window_start,
                window_end=game.window_end,
                entry_state=game_state(data, game),
                purpose="results"
                if data.now >= game.locks_at
                else "upcoming"
                if data.now < game.opens_at
                else "entry",
                coverage_state=game.coverage_state,
                result_version=game.result_version,
                archived=not live,
                fee=projection.for_week(parent).model_copy(
                    update={"destination": destination + "#payment"}
                ),
            )
            members = audience(data, game)
            if game.kind == "group":
                group_picks = [pick for pick in data.group if pick.game_id == game.id]
                picked = len({pick.player_id for pick in group_picks} & members)
                cards.append(
                    GroupCard(
                        **base,
                        progress=dict(
                            picked_count=picked,
                            member_count=len(members),
                            missing_contributors=len(members) - picked,
                            all_picked=bool(members) and picked == len(members),
                        ),
                        my_entry=addressed_entry(data, game, 0),
                        result=dict(
                            status=group_outcome([pick.status for pick in group_picks]), final=final
                        ),
                    )
                )
            else:
                fantasy_picks = [pick for pick in data.fantasy if pick.game_id == game.id]
                mine = [pick for pick in fantasy_picks if pick.player_id == data.player_id]
                own_result = fantasy_outcome(mine)
                summaries = [
                    dict(
                        player_id=str(player),
                        display_name=names.get(player, "Former member"),
                        **fantasy_outcome(
                            [pick for pick in fantasy_picks if pick.player_id == player]
                        ),
                    )
                    for player in sorted(members, key=str)
                    if data.now >= game.locks_at or player == data.player_id
                ]
                snapshot = data.snapshots.get(f"game-result:v1:{game.id}")
                cards.append(
                    FantasyCard(
                        **base,
                        progress=dict(
                            slots_filled=len(mine),
                            slot_count=6,
                            entered=bool(mine),
                            partial=0 < len(mine) < 6,
                        ),
                        slots=[addressed_entry(data, game, slot) for slot in range(1, 7)],
                        result=dict(**own_result, final=final, provisional=not final),
                        members=summaries,
                        winner_ids=list(snapshot.payload.get("winner_ids", []))
                        if snapshot and final
                        else [],
                    )
                )
        legacy_cards = []
        ledger = data.ledgers.get(owner, MemberLedger())
        for parent_id in sorted(
            data.selected_parents,
            key=lambda identifier: (data.parents[identifier].starts_on, str(identifier)),
            reverse=True,
        ):
            parent = data.parents[parent_id]
            if parent.league_id != owner or parent.format != "legacy":
                continue
            pick = data.legacy.get(parent.id)
            legacy_cards.append(
                LegacyRoundCard(
                    league_id=owner,
                    week_id=parent.id,
                    starts_on=parent.starts_on,
                    week_number=labels.get(parent.id, str(parent.number)),
                    destination=f"/leagues/{league.slug}/predictions?gw={parent.id}#coupon",
                    status=parent.status.value,
                    picks_open_at=parent.picks_open_at_utc,
                    locks_at=parent.locks_at_utc,
                    can_pick=member.deleted_at is None and pick_refusal(parent, data.now) is None,
                    picked_count=data.counts.get(parent.id, 0),
                    my_pick=pick_payload(pick) if pick else None,
                    archived=parent.id in data.archive,
                    fee=legacy_fee(
                        league, parent, member, ledger, data.parents, data.recorded_fees, labels
                    ),
                )
            )
        own_stats = next(
            (
                row.model_dump(mode="json")
                for row in stats.get(owner, [])
                if row.player_id == str(data.player_id)
            ),
            None,
        )
        next_game = min(
            (
                game
                for game in own_games
                if game.kind == "fantasy"
                and (
                    data.parents[game.week_id].starts_on > billing_label(data.now)
                    or game.opens_at > data.now
                )
            ),
            key=lambda game: (data.parents[game.week_id].starts_on, str(game.id)),
            default=None,
        )
        calendar = data.calendar.get(owner)
        output.append(
            LeagueGames(
                league_id=owner,
                slug=league.slug,
                name=league.name,
                two_games_enabled=owner in data.active,
                suspended=bool(owner in data.active and data.rollouts[owner].suspended),
                next_game_state="known" if next_game else "pending",
                next_game_opens_at=next_game.opens_at if next_game else None,
                calendar_state=str(calendar.payload.get("state")) if calendar else None,
                server_now=data.now,
                season=data.season,
                season_stats=own_stats,
                weekly_form=forms.get(owner, []),
                games=cards,
                legacy_rounds=legacy_cards,
                next_cursor=data.cursors.get(owner),
            )
        )
    return HomeGames(leagues=output)


class GameReads:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        two_games_enabled: bool,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.sessions, self.two_games_enabled, self.clock = sessions, two_games_enabled, clock

    async def read(
        self,
        player_id: uuid.UUID,
        *,
        league_id: uuid.UUID | None = None,
        cursor: str | None = None,
        page_size: int = 20,
        season: int | None = None,
        week_id: uuid.UUID | None = None,
    ) -> HomeGames:
        async with self.sessions() as db, db.begin():
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            data = await load_read_data(
                db,
                player_id,
                self.clock(),
                two_games_enabled=self.two_games_enabled,
                league_id=league_id,
                cursor=cursor,
                page_size=page_size,
                season=season,
                week_id=week_id,
            )
            return await project_read_data(db, data)

    async def results(
        self, player_id: uuid.UUID, league_id: uuid.UUID, week_id: uuid.UUID
    ) -> WeekResults:
        from src.services.coupon import build_coupon
        from src.services.two_game_read_models import FantasyCard, GroupCard

        async with self.sessions() as db, db.begin():
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            data = await load_read_data(
                db,
                player_id,
                self.clock(),
                two_games_enabled=self.two_games_enabled,
                league_id=league_id,
                week_id=week_id,
            )
            parent = data.parents[week_id]
            if parent.format == "legacy":
                coupon = await build_coupon(db, league_id, parent)
                return WeekResults(
                    league_id=league_id,
                    week_id=week_id,
                    week_label=parent.starts_on,
                    format="legacy",
                    legacy=coupon.model_dump(mode="json"),
                )
            projected = await project_read_data(db, data, include_stats=False)
            cards = projected.leagues[0].games
            return WeekResults(
                league_id=league_id,
                week_id=week_id,
                week_label=parent.starts_on,
                format="two_game",
                group=next((card for card in cards if isinstance(card, GroupCard)), None),
                fantasy=next((card for card in cards if isinstance(card, FantasyCard)), None),
            )
