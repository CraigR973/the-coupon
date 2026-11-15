"""Unpriced whole-fixture contributions and exact operation reconciliation."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.fixture import Fixture
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile
from src.models.two_game import GameOperation, GroupPick, ProviderSnapshot, TwoGameFixture
from src.schemas import UtcDatetime
from src.services.gameweek import selected_competition_slugs
from src.services.odds_provider import is_void_status
from src.services.provider_budget import naive_utc, utc_now
from src.services.two_game_entry import (
    GroupChoice,
    OperationRequest,
    Target,
    admit_action,
    entry_state,
    lock_and_replay,
    operation_hash,
    operation_revision,
    refuse,
    replay,
    replay_after_refusal,
    require_open,
    resolve_target,
    selection,
)
from src.services.two_game_results import group_outcome
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import (
    EntryFeeRefused,
    WeekFee,
    materialize_entry_fees,
    project_fees,
)


class GroupContribution(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    week_id: uuid.UUID
    game_id: uuid.UUID
    game_kind: Literal["group"] = "group"
    player_id: uuid.UUID
    fixture_id: uuid.UUID
    market: str
    outcome: str
    runner_name: str
    revision: int
    operation_id: uuid.UUID
    result: str


class GroupEntry(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    game_id: uuid.UUID
    game_kind: Literal["group"] = "group"
    pick: GroupContribution | None
    revision: int
    operation_id: uuid.UUID | None


class GroupGameView(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    week_label: date
    week_number: str
    format: Literal["two_game"] = "two_game"
    game_id: uuid.UUID
    game_kind: Literal["group"] = "group"
    destination: str
    opens_at: UtcDatetime
    locks_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    entry_state: str
    coverage_state: str
    fixtures: list[dict[str, Any]]
    my_entries: list[GroupContribution]
    progress: dict[str, Any]
    result: dict[str, Any]
    fee: WeekFee


def contribution(pick: GroupPick) -> GroupContribution:
    return GroupContribution(
        id=pick.id,
        league_id=pick.league_id,
        week_id=pick.week_id,
        game_id=pick.game_id,
        player_id=pick.player_id,
        fixture_id=pick.fixture_id,
        market=pick.market,
        outcome=pick.outcome,
        runner_name=pick.runner_name,
        revision=pick.revision,
        operation_id=pick.operation_id,
        result=pick.status,
    )


async def read_entry(db: AsyncSession, target: Target, player_id: uuid.UUID) -> GroupEntry:
    pick: GroupPick | None = await db.scalar(
        select(GroupPick)
        .where(
            GroupPick.game_id == target.game.id,
            GroupPick.player_id == player_id,
        )
        .execution_options(populate_existing=True)
    )
    revision, operation_id = await operation_revision(db, target, player_id, 0)
    if pick is not None and pick.revision >= revision:
        revision, operation_id = pick.revision, pick.operation_id
    return GroupEntry(
        **target.identity(),
        pick=contribution(pick) if pick else None,
        revision=revision,
        operation_id=operation_id,
    )


async def require_revision(
    db: AsyncSession,
    target: Target,
    player_id: uuid.UUID,
    expected: int,
) -> GroupEntry:
    current = await read_entry(db, target, player_id)
    if current.revision != expected:
        refuse(
            409,
            "ENTRY_CHANGED",
            "This contribution changed; review the current choice",
            current=current.model_dump(mode="json"),
            **target.identity(),
        )
    return current


def require_paid(fee: WeekFee) -> None:
    if not fee.paid_through:
        refuse(
            402,
            "PAYMENT_REQUIRED",
            "Pay through this week before contributing",
            week_id=str(fee.week_id),
            league_id=str(fee.league_id),
            amount_owed_pence=fee.amount_owed_pence,
            destination=fee.destination,
            payment_url=fee.payment_url,
            fee=fee.model_dump(mode="json"),
        )


class GroupEntries:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions = sessions
        self.clock = clock or utc_now

    def now(self) -> datetime:
        return naive_utc(self.clock())

    async def get_pick(
        self,
        league_id: uuid.UUID,
        week_id: uuid.UUID,
        player_id: uuid.UUID,
    ) -> GroupEntry:
        async with self.sessions() as db, db.begin():
            target = await resolve_target(
                db, league_id, week_id, "group", player_id, own_history=True
            )
            return await read_entry(db, target, player_id)

    async def save(
        self,
        league_id: uuid.UUID,
        week_id: uuid.UUID,
        player_id: uuid.UUID,
        body: GroupChoice,
    ) -> GroupEntry:
        identity: OperationRequest = dict(
            league_id=league_id,
            week_id=week_id,
            kind="group",
            slot=0,
            player_id=player_id,
            body=body,
        )
        # Phase 1: replay precedes mutable admission, and invalid local choices
        # cannot fabricate future dues. End this transaction before fee preflight.
        async with self.sessions() as db, db.begin():
            original = await lock_and_replay(db, **identity)
            if original is not None:
                return GroupEntry.model_validate(original)
            target = await resolve_target(db, league_id, week_id, "group", player_id)
            await require_open(db, target, self.now())
            await selection(db, target, body)
            await require_revision(db, target, player_id, body.expected_revision)
            game_id = target.game.id
        try:
            try:
                fee = await materialize_entry_fees(
                    self.sessions,
                    league_id=league_id,
                    week_id=week_id,
                    game_id=game_id,
                    game_kind="group",
                    player_id=player_id,
                    clock=self.now,
                )
            except EntryFeeRefused as exc:
                refuse(
                    404 if exc.code == "NOT_FOUND" else 409,
                    exc.code,
                    "This game is not accepting entries",
                )
            require_paid(fee)
        except HTTPException:
            original = await replay_after_refusal(self.sessions, **identity)
            if original is not None:
                return GroupEntry.model_validate(original)
            raise
        # Phase 3: serialise on the same league lock as roster/discovery/billing,
        # then refresh every mutable fact. No provider is ever acquired.
        try:
            async with self.sessions() as db, db.begin():
                original = await lock_and_replay(db, **identity)
                if original is not None:
                    return GroupEntry.model_validate(original)
                target = await resolve_target(db, league_id, week_id, "group", player_id)
                # resolve_target may wait: replay once more under the acquired lock.
                original = await replay(db, **identity)
                if original is not None:
                    return GroupEntry.model_validate(original)
                await require_open(db, target, self.now())
                fixture, runner = await selection(db, target, body, lock_fixture=True)
                current = await require_revision(db, target, player_id, body.expected_revision)
                require_paid(
                    (
                        await project_fees(
                            db, target.league, player_id, target.week.starts_on, self.now()
                        )
                    ).for_week(target.week)
                )
                taken = await db.scalar(
                    select(GroupPick.id).where(
                        GroupPick.week_id == week_id,
                        GroupPick.fixture_id == fixture.id,
                        GroupPick.player_id != player_id,
                    )
                )
                if taken is not None:
                    refuse(
                        409,
                        "FIXTURE_TAKEN",
                        "Another member claimed this fixture",
                        fixture_id=str(fixture.id),
                        **target.identity(),
                    )
                # Fixture acquisition may have waited behind a census update.
                await require_open(db, target, self.now())
                admit_action(player_id, league_id)
                pick = await db.get(GroupPick, current.pick.id) if current.pick else None
                if pick is None:
                    pick = GroupPick(
                        league_id=league_id,
                        week_id=week_id,
                        game_id=target.game.id,
                        player_id=player_id,
                    )
                    db.add(pick)
                pick.fixture_id = fixture.id
                pick.market, pick.outcome, pick.runner_name = body.market, body.outcome, runner
                pick.revision, pick.operation_id = current.revision + 1, body.operation_id
                pick.status = "pending"
                await db.flush()
                result = GroupEntry(
                    **target.identity(),
                    pick=contribution(pick),
                    revision=pick.revision,
                    operation_id=pick.operation_id,
                )
                db.add(
                    GameOperation(
                        league_id=league_id,
                        week_id=week_id,
                        game_id=target.game.id,
                        game_kind="group",
                        player_id=player_id,
                        slot=0,
                        operation_id=body.operation_id,
                        body_hash=operation_hash(body),
                        response=result.model_dump(mode="json"),
                    )
                )
            return result
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if constraint == "uq_group_pick_fixture":
                refuse(
                    409,
                    "FIXTURE_TAKEN",
                    "Another member claimed this fixture",
                    fixture_id=str(body.fixture_id),
                    league_id=str(league_id),
                    week_id=str(week_id),
                )
            if constraint == "uq_group_pick_member":
                current = await self.get_pick(league_id, week_id, player_id)
                refuse(
                    409,
                    "ENTRY_CHANGED",
                    "This contribution changed",
                    current=current.model_dump(mode="json"),
                )
            raise

    async def view(
        self,
        league_id: uuid.UUID,
        week_id: uuid.UUID,
        player_id: uuid.UUID,
    ) -> GroupGameView:
        from src.config import settings
        from src.display_name import public_name

        async with self.sessions() as db, db.begin():
            target = await resolve_target(db, league_id, week_id, "group", player_id)
            now = self.now()
            mine = await read_entry(db, target, player_id)
            rows = (
                await db.execute(
                    select(Fixture, GroupPick, Profile)
                    .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
                    .outerjoin(
                        GroupPick,
                        (GroupPick.game_id == target.game.id)
                        & (GroupPick.fixture_id == Fixture.id),
                    )
                    .outerjoin(Profile, Profile.id == GroupPick.player_id)
                    .where(TwoGameFixture.game_id == target.game.id)
                    .order_by(Fixture.kickoff_utc, Fixture.home, Fixture.id)
                )
            ).all()
            statuses = {
                row.fixture_id: str(row.payload.get("status", "pending"))
                for row in await db.scalars(
                    select(ProviderSnapshot).where(
                        ProviderSnapshot.fixture_id.in_([fixture.id for fixture, _, _ in rows]),
                        ProviderSnapshot.key.startswith("fixture-state:v1:"),
                        ProviderSnapshot.payload["source"].astext == settings.odds_provider.value,
                    )
                )
            }
            fixtures = []
            competitions = selected_competition_slugs(target.league)
            for fixture, pick, profile in rows:
                status = statuses.get(fixture.id, "pending")
                eligible = (
                    fixture.kickoff_utc
                    == london_utc(target.week.starts_on, 15)
                    == target.game.window_start
                    == target.game.window_end
                    and (competitions is None or fixture.competition_id in competitions)
                    and not is_void_status(status)
                )
                if not eligible and pick is None:
                    continue
                fixtures.append(
                    {
                        "fixture_id": str(fixture.id),
                        "home": fixture.home,
                        "away": fixture.away,
                        "competition_id": fixture.competition_id,
                        "kickoff_at": fixture.kickoff_utc.isoformat() + "Z",
                        "status": status,
                        "allowed_markets": [
                            {
                                "market": market.value,
                                "outcomes": ["HOME", "DRAW", "AWAY"]
                                if market.value == "MATCH_ODDS"
                                else ["YES", "NO"],
                            }
                            for market in target.league.offered_markets
                        ],
                        "eligible": eligible,
                        "claim": {
                            "player_id": str(pick.player_id),
                            "display_name": public_name(profile.display_name)
                            if profile
                            else "Former member",
                            "market": pick.market,
                            "outcome": pick.outcome,
                            "runner_name": pick.runner_name,
                            "result": pick.status,
                        }
                        if pick
                        else None,
                    }
                )
            member_count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(LeagueMembership)
                    .join(Profile, Profile.id == LeagueMembership.player_id)
                    .where(
                        LeagueMembership.league_id == league_id,
                        LeagueMembership.deleted_at.is_(None),
                        Profile.deleted_at.is_(None),
                        Profile.is_active.is_(True),
                    )
                )
                or 0
            )
            picked = int(
                await db.scalar(
                    select(func.count())
                    .select_from(GroupPick)
                    .join(
                        LeagueMembership,
                        (LeagueMembership.league_id == league_id)
                        & (LeagueMembership.player_id == GroupPick.player_id),
                    )
                    .join(Profile, Profile.id == GroupPick.player_id)
                    .where(
                        GroupPick.game_id == target.game.id,
                        LeagueMembership.deleted_at.is_(None),
                        Profile.deleted_at.is_(None),
                        Profile.is_active.is_(True),
                    )
                )
                or 0
            )
            return GroupGameView(
                **target.identity(),
                week_label=target.week.starts_on,
                week_number=str(target.week.number),
                destination=target.destination,
                opens_at=target.game.opens_at,
                locks_at=target.game.locks_at,
                window_start=target.game.window_start,
                window_end=target.game.window_end,
                entry_state=await entry_state(db, target, now),
                coverage_state=target.game.coverage_state,
                fixtures=fixtures,
                my_entries=[mine.pick] if mine.pick else [],
                progress={
                    "picked_count": picked,
                    "member_count": member_count,
                    "all_picked": member_count > 0 and picked == member_count,
                },
                result={
                    "status": group_outcome(
                        [pick.status for _, pick, _ in rows if pick is not None]
                    ),
                    "final": target.game.finalized_at is not None
                    or target.game.status == "settled",
                },
                fee=(
                    await project_fees(db, target.league, player_id, target.week.starts_on, now)
                ).for_week(target.week),
            )
