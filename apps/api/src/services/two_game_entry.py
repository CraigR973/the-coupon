"""Exact-target admission and replay for the isolated game APIs.

No provider dependency belongs here. The short admission transaction must end
before independently committing early dues or doing later quote I/O.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn, TypedDict, Unpack

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, cast, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import PickMarket, PickOutcome
from src.models.two_game import GameOperation, ProviderWork, TwoGame, TwoGameFixture, TwoGameRollout
from src.rate_limit import consume_shared_limit
from src.services.competitions import plays_competition
from src.services.gameweek import selected_competition_slugs
from src.services.two_game_fixture_state import explicitly_void
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import _active_membership, _rollout, financial_lock


def refuse(status: int, code: str, message: str, **details: Any) -> NoReturn:
    raise HTTPException(status_code=status, detail={"code": code, "message": message, **details})


async def read_snapshot(db: AsyncSession) -> None:
    """Make this transaction one read-only snapshot. Call it before any other statement.

    Batch 237. A game read takes no league lock, so it never queues behind a save, a
    membership change or background work holding one; the snapshot keeps every fact it
    returns from the same instant instead. ``/me/games`` has always read this way.
    """
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))


class GroupChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixture_id: uuid.UUID
    market: str
    outcome: str
    expected_revision: int = Field(ge=0)
    operation_id: uuid.UUID


class RemovePick(BaseModel):
    """Withdraw the member's own pick: the revision it replaces and a replayable id.

    Batch 234. The body hashes differently from any save, so an operation id reused
    across a save and a removal is refused as a conflict rather than replayed.
    """

    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    operation_id: uuid.UUID


class OperationRequest(TypedDict):
    league_id: uuid.UUID
    week_id: uuid.UUID
    kind: str
    slot: int
    player_id: uuid.UUID
    body: GroupChoice | RemovePick


def operation_hash(body: BaseModel) -> str:
    value = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


async def replay(
    db: AsyncSession,
    *,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    kind: str,
    slot: int,
    player_id: uuid.UUID,
    body: GroupChoice | RemovePick,
) -> dict[str, Any] | None:
    operation: GameOperation | None = await db.scalar(
        select(GameOperation).where(
            GameOperation.league_id == league_id,
            GameOperation.week_id == week_id,
            GameOperation.game_kind == kind,
            GameOperation.slot == slot,
            GameOperation.player_id == player_id,
            GameOperation.operation_id == body.operation_id,
        )
    )
    if operation is None:
        return None
    if operation.body_hash != operation_hash(body):
        refuse(
            409,
            "OPERATION_CONFLICT",
            "This operation already saved another request",
            league_id=str(league_id),
            week_id=str(week_id),
            game_kind=kind,
            slot=slot,
        )
    return operation.response


async def lock_and_replay(
    db: AsyncSession, **request: Unpack[OperationRequest]
) -> dict[str, Any] | None:
    await authorise_history(db, request["league_id"], request["week_id"], request["player_id"])
    original = await replay(db, **request)
    if original is not None:
        return original
    if await _active_membership(db, request["league_id"], request["player_id"]) is None:
        # A successful in-flight operation can have committed immediately before
        # departure. Its owner's historical replay remains available.
        original = await replay(db, **request)
        if original is not None:
            return original
        refuse(404, "NOT_FOUND", "No accessible game target")
    await financial_lock(db, request["league_id"])
    await authorise_history(db, request["league_id"], request["week_id"], request["player_id"])
    # This must precede every mutable check after waiting, including membership,
    # opening/lock and revision. Two identical concurrent requests replay once.
    return await replay(db, **request)


async def authorise_history(
    db: AsyncSession, league_id: uuid.UUID, week_id: uuid.UUID, player_id: uuid.UUID
) -> None:
    """Historical replay retains ownership checks before mutable entry gates."""
    league = await db.get(League, league_id, populate_existing=True)
    week = await db.get(Gameweek, week_id, populate_existing=True)
    member = await db.scalar(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.player_id == player_id,
        )
    )
    if (
        league is None
        or league.deleted_at is not None
        or week is None
        or week.league_id != league_id
        or member is None
    ):
        refuse(404, "NOT_FOUND", "No accessible game target")


async def replay_after_refusal(
    sessions: async_sessionmaker[AsyncSession], **request: Unpack[OperationRequest]
) -> dict[str, Any] | None:
    """Reconcile a handoff failure with an independently committed receipt.

    The first admission and the fee preflight use separate transactions. An
    identical caller can commit between them. Take the same short league lock
    before the final read, but never apply current entry/payment gates to an
    already accepted receipt. Baseline historical ownership still applies.
    """
    async with sessions() as db, db.begin():
        await authorise_history(db, request["league_id"], request["week_id"], request["player_id"])
        await financial_lock(db, request["league_id"])
        await authorise_history(db, request["league_id"], request["week_id"], request["player_id"])
        return await replay(db, **request)


@dataclass
class Target:
    league: League
    week: Gameweek
    game: TwoGame
    rollout: TwoGameRollout

    def identity(self) -> dict[str, Any]:
        return {
            "league_id": str(self.league.id),
            "week_id": str(self.week.id),
            "game_id": str(self.game.id),
            "game_kind": self.game.kind,
        }

    @property
    def destination(self) -> str:
        return f"/leagues/{self.league.id}/weeks/{self.week.id}/{self.game.kind}"


async def resolve_target(
    db: AsyncSession,
    league_id: uuid.UUID,
    week_id: uuid.UUID,
    kind: str,
    player_id: uuid.UUID,
    *,
    own_history: bool = False,
    lock: bool = True,
) -> Target:
    """Resolve and authorise one exact game address.

    A write keeps ``lock`` and holds the league's financial lock until it commits. A read
    passes ``lock=False`` inside :func:`read_snapshot`: it checks the same access facts
    once, from its snapshot, and never waits for the lock (Batch 237).
    """
    league = await db.get(League, league_id, populate_existing=True)
    week = await db.get(Gameweek, week_id, populate_existing=True)
    member = await _active_membership(db, league_id, player_id)
    if member is None and own_history:
        member = await db.scalar(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.player_id == player_id,
            )
        )
    if (
        league is None
        or league.deleted_at is not None
        or week is None
        or week.league_id != league_id
        or member is None
    ):
        refuse(404, "NOT_FOUND", "No accessible game target")
    if week.format != "two_game":
        refuse(
            409,
            "UNSUPPORTED_FORMAT",
            "This week uses the legacy coupon",
            week_id=str(week_id),
            destination=f"/leagues/{league.slug}/predictions?gw={week_id}#coupon",
        )
    rollout = await _rollout(db, league_id)
    if rollout is None or week.starts_on < rollout.first_week:
        refuse(404, "NOT_FOUND", "No accessible game target")
    if lock:
        await financial_lock(db, league_id)
        # The advisory may have waited for leave/delete/suspension. Refresh every
        # access fact after it, not just objects cached before waiting.
        league = await db.get(League, league_id, populate_existing=True)
        rollout = await _rollout(db, league_id)
        member = await _active_membership(db, league_id, player_id)
        if member is None and own_history:
            member = await db.scalar(
                select(LeagueMembership).where(
                    LeagueMembership.league_id == league_id,
                    LeagueMembership.player_id == player_id,
                )
            )
        if (
            league is None
            or league.deleted_at is not None
            or rollout is None
            or week.starts_on < rollout.first_week
            or member is None
        ):
            refuse(404, "NOT_FOUND", "No accessible game target")
    game: TwoGame | None = await db.scalar(
        select(TwoGame)
        .where(
            TwoGame.league_id == league_id,
            TwoGame.week_id == week_id,
            TwoGame.kind == kind,
        )
        .execution_options(populate_existing=True)
    )
    if game is None:
        refuse(404, "NOT_FOUND", "No accessible game target")
    return Target(league, week, game, rollout)


async def entry_state(db: AsyncSession, target: Target, now: datetime) -> str:
    if target.rollout.suspended:
        return "suspended"
    if target.game.status == "cancelled":
        return "cancelled"
    if now >= target.game.locks_at or target.game.status == "settled":
        return "locked"
    calendar = await db.get(ProviderWork, f"calendar:{target.league.id}", populate_existing=True)
    if (
        now < target.game.opens_at
        or calendar
        and calendar.payload.get("state") == "schedule_conflict"
    ):
        return "not_open"
    return "open"


async def require_open(db: AsyncSession, target: Target, now: datetime) -> None:
    state = await entry_state(db, target, now)
    if state != "open":
        refuse(409, state.upper(), "This game is not accepting entries", **target.identity())


async def selection(
    db: AsyncSession,
    target: Target,
    body: GroupChoice,
    *,
    lock_fixture: bool = False,
) -> tuple[Fixture, str]:
    statement = (
        select(Fixture)
        .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
        .where(TwoGameFixture.game_id == target.game.id, Fixture.id == body.fixture_id)
        .execution_options(populate_existing=True)
    )
    if lock_fixture:
        # Census updates the Fixture before its status snapshot in one transaction.
        # A share lock stabilises both eligibility facts until this save commits.
        statement = statement.with_for_update(read=True, of=Fixture)
    fixture: Fixture | None = await db.scalar(statement)
    if fixture is None:
        refuse(422, "INVALID_SELECTION", "Choose a fixture in this game", **target.identity())
    stamp = fixture.kickoff_utc
    expected_group = london_utc(target.week.starts_on, 15)
    eligible = (
        stamp == expected_group == target.game.window_start == target.game.window_end
        if target.game.kind == "group"
        else target.game.window_start <= stamp < target.game.window_end
    )
    competitions = selected_competition_slugs(target.league)
    if (
        not eligible
        or not plays_competition(target.game.kind, fixture.competition_id, competitions)
        or await explicitly_void(db, settings.odds_provider.value, fixture.provider_event_id)
    ):
        refuse(422, "INVALID_SELECTION", "This fixture is no longer eligible", **target.identity())
    try:
        market, outcome = PickMarket(body.market), PickOutcome(body.outcome)
    except ValueError:
        refuse(
            422, "INVALID_SELECTION", "Choose an offered market and outcome", **target.identity()
        )
    valid = (
        outcome in (PickOutcome.HOME, PickOutcome.DRAW, PickOutcome.AWAY)
        if market == PickMarket.MATCH_ODDS
        else outcome in (PickOutcome.YES, PickOutcome.NO)
    )
    if market not in target.league.offered_markets or not valid:
        refuse(
            422, "INVALID_SELECTION", "Choose an offered market and outcome", **target.identity()
        )
    runner = {
        PickOutcome.HOME: fixture.home,
        PickOutcome.AWAY: fixture.away,
        PickOutcome.DRAW: "Draw",
        PickOutcome.YES: "Both teams score",
        PickOutcome.NO: "No — not both score",
    }[outcome]
    return fixture, runner


async def operation_revision(
    db: AsyncSession,
    target: Target,
    player_id: uuid.UUID,
    slot: int,
) -> tuple[int, uuid.UUID | None]:
    row = (
        await db.execute(
            select(
                cast(GameOperation.response["revision"].astext, Integer),
                GameOperation.operation_id,
            )
            .where(
                GameOperation.game_id == target.game.id,
                GameOperation.player_id == player_id,
                GameOperation.slot == slot,
            )
            .order_by(cast(GameOperation.response["revision"].astext, Integer).desc())
            .limit(1)
        )
    ).first()
    return (int(row[0]), row[1]) if row else (0, None)


def admit_action(player_id: uuid.UUID, league_id: uuid.UUID) -> None:
    if not consume_shared_limit(
        str(player_id), f"{settings.two_game_member_actions_hourly}/hour", "two-game-member-actions"
    ):
        refuse(429, "TOO_MANY_TRIES", "Please wait before another edit", retry_after_seconds=3600)
    if not consume_shared_limit(
        str(league_id), f"{settings.two_game_league_actions_hourly}/hour", "two-game-league-actions"
    ):
        refuse(429, "PICKS_BUSY", "The league is busy; please try later", retry_after_seconds=3600)
