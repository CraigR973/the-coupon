"""Versioned per-game facts, durable recipient claims and session-free push plans."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import NotificationSend
from src.models.pick import Pick
from src.models.profile import Profile
from src.models.two_game import (
    FantasyPick,
    GroupPick,
    MembershipInterval,
    ProviderSnapshot,
    TwoGame,
    TwoGameEvent,
    TwoGameRollout,
)
from src.services.notification_triggers import notify_round_settled
from src.services.provider_budget import utc_now
from src.services.push_notification_service import (
    PreparedNotification,
    collect_notification_intents,
    deliver_prepared_notification,
    prepare_collected_notifications,
    record_notification_outcomes,
    send_notification,
)
from src.services.two_game_settlement import active
from src.services.weekly_fees import financial_locks


def destination(game: TwoGame) -> str:
    return f"/leagues/{game.league_id}/weeks/{game.week_id}/{game.kind}"


def recipient_key(event: TwoGameEvent, player_id: uuid.UUID) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                str(event.league_id),
                str(event.week_id),
                event.game_kind,
                event.kind,
                event.version,
                str(player_id),
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def claim_recipient(db: AsyncSession, kind: str, subject: str, now: datetime) -> bool:
    return (
        await db.scalar(
            insert(NotificationSend)
            .values(kind=kind, subject=subject, sent_at=now)
            .on_conflict_do_nothing(constraint="uq_notification_sends_kind_subject")
            .returning(NotificationSend.id)
        )
    ) is not None


LIFECYCLE_KINDS = ("game_opened", "game_reminder", "game_locked")


def lifecycle_step(game: TwoGame, suspended: bool, now: datetime) -> tuple[str, list[str]]:
    """The status a game holds at ``now`` and the lifecycle facts it should have recorded."""
    if now >= game.locks_at:
        return (game.status if game.status in ("settled", "cancelled") else "locked"), [
            "game_locked"
        ]
    if game.opens_at <= now and not suspended:
        kinds = ["game_opened"]
        if (
            now + timedelta(hours=2, minutes=30)
            <= game.locks_at
            <= now + timedelta(hours=3, minutes=30)
        ):
            kinds.append("game_reminder")
        return ("open" if game.status == "scheduled" else game.status), kinds
    return game.status, []


async def lifecycle_due(
    db: AsyncSession, league_ids: list[uuid.UUID], now: datetime
) -> set[uuid.UUID]:
    """Leagues with a status to move or a lifecycle fact to record, read without a lock.

    Batch 237. Most minutes nothing changes, and taking each league's lock to find that
    out queued this pass behind whatever else held it. A league found here still takes
    its lock and decides again from what it reads under it.
    """
    if not league_ids:
        return set()
    rollouts = {
        row.league_id: row
        for row in await db.scalars(
            select(TwoGameRollout).where(TwoGameRollout.league_id.in_(league_ids))
        )
    }
    recorded = {
        (game_id, kind)
        for game_id, kind in await db.execute(
            select(TwoGameEvent.game_id, TwoGameEvent.kind).where(
                TwoGameEvent.league_id.in_(league_ids),
                TwoGameEvent.version == 0,
                TwoGameEvent.kind.in_(LIFECYCLE_KINDS),
            )
        )
    }
    due: set[uuid.UUID] = set()
    for game in await db.scalars(select(TwoGame).where(TwoGame.league_id.in_(league_ids))):
        rollout = rollouts.get(game.league_id)
        if rollout is None or not rollout.enabled or game.status == "cancelled":
            continue
        status, kinds = lifecycle_step(game, rollout.suspended, now)
        if status != game.status or any((game.id, kind) not in recorded for kind in kinds):
            due.add(game.league_id)
    return due


async def lifecycle_events(sessions: async_sessionmaker[AsyncSession], now: datetime) -> None:
    async with sessions() as db:
        if not await active(db):
            return
        league_ids = list(
            await db.scalars(
                select(TwoGameRollout.league_id)
                .join(League, League.id == TwoGameRollout.league_id)
                .where(TwoGameRollout.enabled.is_(True), League.deleted_at.is_(None))
                .order_by(TwoGameRollout.league_id)
            )
        )
        due = await lifecycle_due(db, league_ids, now)
    for league_id in league_ids:
        if league_id not in due:
            continue
        async with sessions() as db, db.begin():
            await financial_locks(db, [league_id])
            rollout = await db.get(TwoGameRollout, league_id, populate_existing=True)
            if rollout is None or not rollout.enabled:
                continue
            games = list(
                await db.scalars(
                    select(TwoGame)
                    .where(TwoGame.league_id == league_id)
                    .order_by(TwoGame.id)
                    .with_for_update()
                )
            )
            for game in games:
                if game.status == "cancelled":
                    continue
                game.status, kinds = lifecycle_step(game, rollout.suspended, now)
                for kind in kinds:
                    payload: dict[str, Any] = dict(destination=destination(game))
                    if kind == "game_reminder":
                        model: type[GroupPick] | type[FantasyPick] = (
                            GroupPick if game.kind == "group" else FantasyPick
                        )
                        entered = set(
                            await db.scalars(
                                select(model.player_id).where(model.game_id == game.id)
                            )
                        )
                        members = await db.scalars(
                            select(LeagueMembership.player_id)
                            .join(Profile, Profile.id == LeagueMembership.player_id)
                            .where(
                                LeagueMembership.league_id == league_id,
                                LeagueMembership.deleted_at.is_(None),
                                Profile.deleted_at.is_(None),
                                Profile.is_active.is_(True),
                            )
                        )
                        payload["recipients"] = [
                            str(player_id) for player_id in members if player_id not in entered
                        ]
                    await db.execute(
                        insert(TwoGameEvent)
                        .values(
                            game_id=game.id,
                            league_id=game.league_id,
                            week_id=game.week_id,
                            game_kind=game.kind,
                            kind=kind,
                            version=0,
                            payload=payload,
                        )
                        .on_conflict_do_nothing(constraint="uq_two_game_events_version")
                    )


async def event_audience(db: AsyncSession, event: TwoGameEvent, game: TwoGame) -> list[Profile]:
    if event.kind in ("game_result", "game_corrected"):
        at_lock = set(
            await db.scalars(
                select(MembershipInterval.player_id).where(
                    MembershipInterval.league_id == game.league_id,
                    MembershipInterval.joined_at <= game.locks_at,
                    or_(
                        MembershipInterval.left_at.is_(None),
                        MembershipInterval.left_at > game.locks_at,
                    ),
                )
            )
        )
        model: type[GroupPick] | type[FantasyPick] = (
            GroupPick if game.kind == "group" else FantasyPick
        )
        at_lock |= set(await db.scalars(select(model.player_id).where(model.game_id == game.id)))
        # Legacy-compatible memberships without an interval can still own an accepted
        # leg, but are not guessed into historical zero-entry participation.
        ids = at_lock
    else:
        ids = set(
            await db.scalars(
                select(LeagueMembership.player_id).where(
                    LeagueMembership.league_id == game.league_id,
                    LeagueMembership.deleted_at.is_(None),
                )
            )
        )
        if event.kind == "game_reminder":
            ids &= {uuid.UUID(value) for value in event.payload.get("recipients", [])}
            current_model: type[GroupPick] | type[FantasyPick] = (
                GroupPick if game.kind == "group" else FantasyPick
            )
            ids -= set(
                await db.scalars(
                    select(current_model.player_id).where(current_model.game_id == game.id)
                )
            )
    return list(
        await db.scalars(
            select(Profile)
            .where(Profile.id.in_(ids), Profile.deleted_at.is_(None), Profile.is_active.is_(True))
            .order_by(Profile.id)
        )
    )


async def prepare_events(
    db: AsyncSession, now: datetime
) -> tuple[tuple[PreparedNotification, ...], list[uuid.UUID], list[str]]:
    if not await active(db):
        return (), [], []
    events = list(
        await db.scalars(
            select(TwoGameEvent)
            .join(League, League.id == TwoGameEvent.league_id)
            .join(TwoGameRollout, TwoGameRollout.league_id == League.id)
            .where(
                TwoGameEvent.delivered_at.is_(None),
                League.deleted_at.is_(None),
                TwoGameRollout.enabled.is_(True),
            )
            .order_by(
                TwoGameEvent.game_id,
                TwoGameEvent.version,
                case(
                    (TwoGameEvent.kind == "game_opened", 0),
                    (TwoGameEvent.kind == "game_reminder", 1),
                    (TwoGameEvent.kind == "game_locked", 2),
                    else_=3,
                ),
                TwoGameEvent.id,
            )
            .limit(100)
            .with_for_update(of=TwoGameEvent, skip_locked=True)
        )
    )
    with collect_notification_intents() as intents:
        for event in events:
            game = await db.get(TwoGame, event.game_id)
            if game is not None and event.kind in ("game_opened", "game_reminder", "game_locked"):
                rollout = await db.get(TwoGameRollout, event.league_id)
                if game.status == "cancelled" or (
                    event.kind != "game_locked"
                    and (rollout is None or rollout.suspended or now >= game.locks_at)
                ):
                    continue
            parent = await db.get(Gameweek, event.week_id)
            if game is None or parent is None:
                continue
            audience = await event_audience(db, event, game)
            for member in audience:
                if not await claim_recipient(db, event.kind, recipient_key(event, member.id), now):
                    continue
                label = parent.starts_on.strftime("%-d %b")
                name = "Saturday group" if game.kind == "group" else "Weekend fantasy"
                if event.kind in ("game_result", "game_corrected"):
                    if game.kind == "group":
                        body = f"{name}, {label}: {event.payload['status'].replace('_', ' ')}."
                    else:
                        result = next(
                            (
                                row
                                for row in event.payload.get("members", [])
                                if row["player_id"] == str(member.id)
                            ),
                            None,
                        )
                        body = (
                            f"{name}, {label}: {result['weekly_points']} points "
                            f"from {result['slots_filled']} picks."
                            if result
                            else f"{name}, {label}: no entry."
                        )
                    if event.kind == "game_corrected":
                        body = "Result corrected. " + body
                elif event.kind == "game_reminder":
                    body = (
                        f"No entry yet for {name.lower()}, {label}. "
                        f"Your deadline is {game.locks_at.isoformat()} UTC. "
                        "£1 is owed for this calendar week regardless of participation."
                    )
                else:
                    action = "entries locked" if event.kind == "game_locked" else "entries open"
                    body = (
                        f"{name}, {label}: {action}. "
                        "£1 is owed for this calendar week regardless of participation."
                    )
                await send_notification(
                    db,
                    member.id,
                    name,
                    body,
                    data=dict(
                        type=event.kind,
                        league_id=str(event.league_id),
                        week_id=str(event.week_id),
                        game_id=str(event.game_id),
                        game_kind=event.game_kind,
                        week_label=parent.starts_on.isoformat(),
                        result_version=event.version,
                        url=destination(game),
                    ),
                    tag=f"game-{game.id}-{member.id}",
                    timezone_name=member.timezone,
                    now_utc=now,
                    league_id=event.league_id,
                )
        legacy = list(
            await db.scalars(
                select(ProviderSnapshot)
                .where(
                    ProviderSnapshot.key.startswith("legacy-settlement:v1:"),
                    ProviderSnapshot.payload["claimed"].astext.is_(None),
                )
                .order_by(
                    ProviderSnapshot.payload["week_id"].astext,
                    cast(ProviderSnapshot.payload["sequence"].astext, Integer),
                    ProviderSnapshot.key,
                )
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in legacy:
            for notice in row.payload.get("notifications", []):
                legacy_member = await db.get(Profile, uuid.UUID(notice["user_id"]))
                if (
                    legacy_member is None
                    or not legacy_member.is_active
                    or legacy_member.deleted_at is not None
                ):
                    continue
                subject = hashlib.sha256(f"{row.key}:{legacy_member.id}".encode()).hexdigest()
                if not await claim_recipient(db, notice["data"]["type"], subject, now):
                    continue
                await send_notification(
                    db,
                    legacy_member.id,
                    notice["title"],
                    notice["body"],
                    data=notice["data"],
                    tag=notice.get("tag"),
                    timezone_name=notice["timezone_name"],
                    now_utc=now,
                    league_id=uuid.UUID(notice["league_id"]),
                )
            row.payload = dict(row.payload, claimed=True)
        plans = await prepare_collected_notifications(db, intents)
    return plans, [event.id for event in events], [row.key for row in legacy]


async def deliver_events(
    sessions: async_sessionmaker[AsyncSession], *, clock: Callable[[], datetime] = utc_now
) -> int:
    async with sessions() as db, db.begin():
        plans, event_ids, legacy_keys = await prepare_events(db, clock())
    if not plans and not event_ids and not legacy_keys:
        return 0
    reports = [await deliver_prepared_notification(plan) for plan in plans]
    async with sessions() as db, db.begin():
        await record_notification_outcomes(db, reports)
        for event in await db.scalars(select(TwoGameEvent).where(TwoGameEvent.id.in_(event_ids))):
            if event.delivered_at is None:
                event.delivered_at = clock()
    return len(event_ids) + len(legacy_keys)


async def stage_legacy_fact(
    db: AsyncSession,
    parent: Gameweek,
    now: datetime,
    *,
    corrected_players: set[uuid.UUID] | None = None,
    identity: str = "0",
) -> None:
    """Freeze the existing legacy copy in the same transaction as its result."""
    kind = "result_corrected" if corrected_players is not None else "round_settled"
    # All callers hold the parent league's settlement lock, so this sequence also
    # orders corrections from different fixtures committed at the same clock tick.
    last_sequence = await db.scalar(
        select(func.max(cast(ProviderSnapshot.payload["sequence"].astext, Integer))).where(
            ProviderSnapshot.key.startswith(f"legacy-settlement:v1:{parent.id}:")
        )
    )
    sequence = (last_sequence or 0) + 1
    with collect_notification_intents() as intents:
        await notify_round_settled(db, parent)
    notices = []
    for intent in intents:
        if corrected_players is not None and intent.user_id not in corrected_players:
            continue
        original = json.loads(intent.payload)
        body = "Result corrected. " + intent.body if corrected_players is not None else intent.body
        data = dict(intent.data or {}, type=kind)
        notices.append(
            dict(
                user_id=str(intent.user_id),
                title=intent.title,
                body=body,
                data=data,
                tag=original.get("tag"),
                timezone_name=intent.timezone_name,
                league_id=str(parent.league_id),
            )
        )
    await db.execute(
        insert(ProviderSnapshot)
        .values(
            key=f"legacy-settlement:v1:{parent.id}:{kind}:{identity}",
            payload=dict(
                week_id=str(parent.id),
                league_id=str(parent.league_id),
                sequence=sequence,
                notifications=notices,
            ),
            observed_at=now,
            expires_at=datetime.max,
        )
        .on_conflict_do_nothing()
    )


async def stage_legacy_corrections(
    db: AsyncSession, pick_ids: list[uuid.UUID], now: datetime, generation: int
) -> None:
    rows = (
        await db.execute(
            select(Pick, Gameweek)
            .join(Gameweek, Gameweek.id == Pick.gameweek_id)
            .where(Pick.id.in_(pick_ids), Gameweek.status == GameweekStatus.settled)
        )
    ).all()
    parents: dict[uuid.UUID, tuple[Gameweek, set[uuid.UUID], list[str]]] = {}
    for pick, parent in rows:
        if parent.id not in parents:
            parents[parent.id] = (parent, set(), [])
        parents[parent.id][1].add(pick.player_id)
        parents[parent.id][2].append(str(pick.id))
    for parent, players, ids in parents.values():
        identity = hashlib.sha256(json.dumps([sorted(ids), generation]).encode()).hexdigest()
        await stage_legacy_fact(db, parent, now, corrected_players=players, identity=identity)
