"""Six addressed fantasy slots with fresh named prices and isolated transactions."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, DecimalException
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Integer, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.models.fixture import Fixture
from src.models.two_game import FantasyPick, GameOperation, ProviderSnapshot, TwoGameFixture
from src.schemas import UtcDatetime
from src.services.gameweek import selected_competition_slugs
from src.services.odds_provider import (
    OddsProvider,
    OddsProviderError,
    OddsProviderRateLimited,
    is_void_status,
)
from src.services.provider_budget import ProviderBudgetRefused, naive_utc, utc_now
from src.services.two_game_entry import (
    GroupChoice,
    OperationRequest,
    Target,
    admit_action,
    entry_state,
    lock_and_replay,
    operation_hash,
    refuse,
    replay_after_refusal,
    require_open,
    resolve_target,
    selection,
)
from src.services.two_game_group import require_paid
from src.services.two_game_provider import acquire_matching, configured_identity
from src.services.two_game_quotes import QuoteView, SharedQuoteBusy, SharedQuotes
from src.services.weekly_fees import EntryFeeRefused, WeekFee, materialize_entry_fees, project_fees


def canonical_odds(value: Decimal) -> Decimal | None:
    """Reject values storage would round, underflow or overflow; never alter a price."""
    if not value.is_finite() or not Decimal("0.0001") <= value <= Decimal("999999.9999"):
        return None
    try:
        canonical = value.quantize(Decimal("0.0001"))
    except DecimalException:
        return None
    return canonical if canonical == value else None


class FantasyChoice(GroupChoice):
    odds: Decimal = Field(gt=0, allow_inf_nan=False)

    @field_validator("odds")
    @classmethod
    def named_price(cls, value: Decimal) -> Decimal:
        canonical = canonical_odds(value)
        if canonical is None:
            raise ValueError("Price must be exactly representable at four decimal places")
        return canonical


class FantasyContribution(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    week_id: uuid.UUID
    game_id: uuid.UUID
    game_kind: Literal["fantasy"] = "fantasy"
    player_id: uuid.UUID
    slot: int
    fixture_id: uuid.UUID
    market: str
    outcome: str
    runner_name: str
    frozen_odds: Decimal
    quoted_at: UtcDatetime
    provider: str
    bookmaker: str
    revision: int
    operation_id: uuid.UUID
    result: str
    points: int


class FantasyEntry(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    game_id: uuid.UUID
    game_kind: Literal["fantasy"] = "fantasy"
    slot: int
    pick: FantasyContribution | None
    revision: int
    operation_id: uuid.UUID | None


class FantasyGameView(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    week_label: date
    week_number: str
    format: Literal["two_game"] = "two_game"
    game_id: uuid.UUID
    game_kind: Literal["fantasy"] = "fantasy"
    destination: str
    opens_at: UtcDatetime
    locks_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    entry_state: str
    coverage_state: str
    fixtures: list[dict[str, Any]]
    my_entries: list[FantasyContribution]
    slots: list[FantasyEntry]
    progress: dict[str, Any]
    result: dict[str, Any]
    fee: WeekFee


def contribution(pick: FantasyPick) -> FantasyContribution:
    return FantasyContribution(
        id=pick.id,
        league_id=pick.league_id,
        week_id=pick.week_id,
        game_id=pick.game_id,
        player_id=pick.player_id,
        slot=pick.slot,
        fixture_id=pick.fixture_id,
        market=pick.market,
        outcome=pick.outcome,
        runner_name=pick.runner_name,
        frozen_odds=pick.frozen_odds,
        quoted_at=pick.quoted_at,
        provider=pick.provider,
        bookmaker=pick.bookmaker,
        revision=pick.revision,
        operation_id=pick.operation_id,
        result=pick.status,
        points=pick.points_awarded or 0,
    )


def require_slot(slot: int) -> None:
    if not 1 <= slot <= 6:
        refuse(422, "INVALID_SLOT", "Choose a slot from one to six", slot=slot)


async def read_slots(
    db: AsyncSession, target: Target, player_id: uuid.UUID, slot: int | None = None
) -> list[FantasyEntry]:
    picks_query = select(FantasyPick).where(
        FantasyPick.game_id == target.game.id, FantasyPick.player_id == player_id
    )
    operations_query = select(GameOperation).where(
        GameOperation.game_id == target.game.id, GameOperation.player_id == player_id
    )
    if slot is not None:
        picks_query = picks_query.where(FantasyPick.slot == slot)
        operations_query = operations_query.where(GameOperation.slot == slot)
    picks = {
        pick.slot: pick
        for pick in await db.scalars(picks_query.execution_options(populate_existing=True))
    }
    operations = {
        operation.slot: operation
        for operation in await db.scalars(
            operations_query.distinct(GameOperation.slot).order_by(
                GameOperation.slot, cast(GameOperation.response["revision"].astext, Integer).desc()
            )
        )
    }
    result = []
    for number in [slot] if slot is not None else range(1, 7):
        pick, operation = picks.get(number), operations.get(number)
        revision = int(operation.response["revision"]) if operation else 0
        operation_id = operation.operation_id if operation else None
        if pick is not None and pick.revision >= revision:
            revision, operation_id = pick.revision, pick.operation_id
        result.append(
            FantasyEntry(
                **target.identity(),
                slot=number,
                pick=contribution(pick) if pick else None,
                revision=revision,
                operation_id=operation_id,
            )
        )
    return result


async def require_revision(
    db: AsyncSession, target: Target, player_id: uuid.UUID, slot: int, expected: int
) -> FantasyEntry:
    current = (await read_slots(db, target, player_id, slot))[0]
    if current.revision != expected:
        refuse(
            409,
            "ENTRY_CHANGED",
            "This slot changed; review its current choice",
            current=current.model_dump(mode="json"),
            slot=slot,
            **target.identity(),
        )
    return current


async def require_distinct_fixture(
    db: AsyncSession, target: Target, player_id: uuid.UUID, slot: int, fixture_id: uuid.UUID
) -> None:
    taken = await db.scalar(
        select(FantasyPick.slot).where(
            FantasyPick.week_id == target.week.id,
            FantasyPick.player_id == player_id,
            FantasyPick.fixture_id == fixture_id,
            FantasyPick.slot != slot,
        )
    )
    if taken is not None:
        refuse(
            409,
            "FIXTURE_ALREADY_PICKED",
            "You already picked this fixture in another slot",
            slot=slot,
            occupied_slot=taken,
            fixture_id=str(fixture_id),
            **target.identity(),
        )


def fantasy_fee(fee: WeekFee) -> WeekFee:
    return fee.model_copy(
        update={"destination": f"/leagues/{fee.league_id}/weeks/{fee.week_id}/fantasy#payment"}
    )


class FantasyEntries:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
        quotes: SharedQuotes | None = None,
    ) -> None:
        self.sessions = sessions
        self.clock = clock or utc_now
        self._quotes = quotes

    def now(self) -> datetime:
        return naive_utc(self.clock())

    def quotes(self) -> SharedQuotes:
        if self._quotes is None:
            try:
                identity = configured_identity()
            except OddsProviderError:
                refuse(503, "ODDS_UNAVAILABLE", "Quote provenance is unavailable")

            async def acquire() -> OddsProvider:
                return await acquire_matching(identity)

            self._quotes = SharedQuotes(
                self.sessions,
                acquire=acquire,
                source=identity.source,
                bookmaker=identity.bookmaker,
                clock=self.now,
            )
        return self._quotes

    async def get_slot(
        self, league_id: uuid.UUID, week_id: uuid.UUID, player_id: uuid.UUID, slot: int
    ) -> FantasyEntry:
        require_slot(slot)
        async with self.sessions() as db, db.begin():
            target = await resolve_target(
                db, league_id, week_id, "fantasy", player_id, own_history=True
            )
            return (await read_slots(db, target, player_id, slot))[0]

    async def fresh_quote(self, event_id: str) -> QuoteView:
        try:
            return await self.quotes().get_fresh(event_id)
        except ProviderBudgetRefused as exc:
            retry = max(1, math.ceil((naive_utc(exc.retry_at) - self.now()).total_seconds()))
            refuse(
                429,
                "PICKS_BUSY",
                "Quote capacity is busy; please try later",
                retry_after_seconds=retry,
            )
        except SharedQuoteBusy:
            refuse(
                503, "ODDS_UNAVAILABLE", "A shared quote is still refreshing", retry_after_seconds=1
            )
        except OddsProviderRateLimited:
            refuse(
                429,
                "PICKS_BUSY",
                "The quote provider is busy",
                retry_after_seconds=settings.odds_rate_limited_cooldown_seconds,
            )
        except OddsProviderError:
            refuse(503, "ODDS_UNAVAILABLE", "A fresh quote is unavailable")

    def checked_price(
        self, quote: QuoteView, body: FantasyChoice, target: Target, slot: int, event_id: str
    ) -> tuple[Decimal, datetime]:
        identity = self.quotes()
        stamp = quote.observed_at
        if stamp is None:
            refuse(503, "ODDS_UNAVAILABLE", "No observed quote is available")
        age = (self.now() - naive_utc(stamp)).total_seconds()
        price = (
            next(
                (
                    canonical_odds(selection.price)
                    for selection in quote.odds.selections
                    if selection.market.value == body.market
                    and selection.outcome.value == body.outcome
                ),
                None,
            )
            if quote.odds
            else None
        )
        if (
            not 0 <= age <= 60
            or price is None
            or quote.event_id != event_id
            or quote.odds is None
            or quote.odds.provider_event_id != event_id
            or (quote.provider, quote.bookmaker) != (identity.source, identity.bookmaker)
        ):
            refuse(
                503,
                "ODDS_UNAVAILABLE",
                "No fresh valid price is available for this selection",
                slot=slot,
                **target.identity(),
            )
        if price != body.odds:
            refuse(
                409,
                "PRICE_MOVED",
                "Confirm the current price before saving",
                current_odds=str(price),
                quoted_at=naive_utc(stamp).isoformat() + "Z",
                slot=slot,
                **target.identity(),
            )
        return price, naive_utc(stamp)

    async def save(
        self,
        league_id: uuid.UUID,
        week_id: uuid.UUID,
        player_id: uuid.UUID,
        slot: int,
        body: FantasyChoice,
    ) -> FantasyEntry:
        require_slot(slot)
        identity: OperationRequest = dict(
            league_id=league_id,
            week_id=week_id,
            kind="fantasy",
            slot=slot,
            player_id=player_id,
            body=body,
        )
        async with self.sessions() as db, db.begin():
            original = await lock_and_replay(db, **identity)
            if original is not None:
                return FantasyEntry.model_validate(original)
            target = await resolve_target(db, league_id, week_id, "fantasy", player_id)
            await require_open(db, target, self.now())
            fixture, _ = await selection(db, target, body)
            await require_revision(db, target, player_id, slot, body.expected_revision)
            await require_distinct_fixture(db, target, player_id, slot, fixture.id)
            event_id, game_id = fixture.provider_event_id, target.game.id
        try:
            try:
                fee = await materialize_entry_fees(
                    self.sessions,
                    league_id=league_id,
                    week_id=week_id,
                    game_id=game_id,
                    game_kind="fantasy",
                    player_id=player_id,
                    clock=self.now,
                )
            except EntryFeeRefused as exc:
                refuse(
                    404 if exc.code == "NOT_FOUND" else 409,
                    exc.code,
                    "This game is not accepting entries",
                )
            require_paid(fantasy_fee(fee))
            admit_action(player_id, league_id)
        except HTTPException:
            original = await replay_after_refusal(self.sessions, **identity)
            if original is not None:
                return FantasyEntry.model_validate(original)
            raise
        try:
            quote = await self.fresh_quote(event_id)
        except HTTPException:
            # A slow/failed refresh may cross the deadline or another identical
            # operation's commit. Replay and current state remain authoritative;
            # this short reconciliation does not buy another quote or due.
            async with self.sessions() as db, db.begin():
                original = await lock_and_replay(db, **identity)
                if original is not None:
                    return FantasyEntry.model_validate(original)
                target = await resolve_target(db, league_id, week_id, "fantasy", player_id)
                await require_open(db, target, self.now())
                await require_revision(db, target, player_id, slot, body.expected_revision)
            raise
        try:
            async with self.sessions() as db, db.begin():
                original = await lock_and_replay(db, **identity)
                if original is not None:
                    return FantasyEntry.model_validate(original)
                target = await resolve_target(db, league_id, week_id, "fantasy", player_id)
                await require_open(db, target, self.now())
                fixture, runner = await selection(db, target, body, lock_fixture=True)
                current = await require_revision(
                    db, target, player_id, slot, body.expected_revision
                )
                await require_distinct_fixture(db, target, player_id, slot, fixture.id)
                require_paid(
                    fantasy_fee(
                        (
                            await project_fees(
                                db, target.league, player_id, target.week.starts_on, self.now()
                            )
                        ).for_week(target.week)
                    )
                )
                await require_open(db, target, self.now())
                pick = await db.get(FantasyPick, current.pick.id) if current.pick else None
                if self.now() >= target.game.locks_at:
                    refuse(
                        409,
                        "LOCKED",
                        "This game is not accepting entries",
                        slot=slot,
                        **target.identity(),
                    )
                price, stamp = self.checked_price(
                    quote, body, target, slot, fixture.provider_event_id
                )
                if pick is None:
                    pick = FantasyPick(
                        league_id=league_id,
                        week_id=week_id,
                        game_id=target.game.id,
                        player_id=player_id,
                        slot=slot,
                    )
                    db.add(pick)
                pick.fixture_id = fixture.id
                pick.market, pick.outcome, pick.runner_name = body.market, body.outcome, runner
                pick.frozen_odds, pick.quoted_at = price, stamp
                pick.provider, pick.bookmaker = quote.provider, quote.bookmaker
                pick.revision, pick.operation_id = current.revision + 1, body.operation_id
                pick.status, pick.points_awarded = "pending", None
                await db.flush()
                result = FantasyEntry(
                    **target.identity(),
                    slot=slot,
                    pick=contribution(pick),
                    revision=pick.revision,
                    operation_id=pick.operation_id,
                )
                db.add(
                    GameOperation(
                        league_id=league_id,
                        week_id=week_id,
                        game_id=target.game.id,
                        game_kind="fantasy",
                        player_id=player_id,
                        slot=slot,
                        operation_id=body.operation_id,
                        body_hash=operation_hash(body),
                        response=result.model_dump(mode="json"),
                    )
                )
            return result
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if constraint == "uq_fantasy_pick_fixture":
                refuse(
                    409,
                    "FIXTURE_ALREADY_PICKED",
                    "You already picked this fixture in another slot",
                    slot=slot,
                    fixture_id=str(body.fixture_id),
                )
            if constraint == "uq_fantasy_pick_slot":
                current = await self.get_slot(league_id, week_id, player_id, slot)
                refuse(
                    409,
                    "ENTRY_CHANGED",
                    "This slot changed",
                    current=current.model_dump(mode="json"),
                )
            raise

    async def view(
        self, league_id: uuid.UUID, week_id: uuid.UUID, player_id: uuid.UUID
    ) -> FantasyGameView:
        async with self.sessions() as db, db.begin():
            target = await resolve_target(db, league_id, week_id, "fantasy", player_id)
            slots = await read_slots(db, target, player_id)
            mine = [entry.pick for entry in slots if entry.pick is not None]
            fixtures = (
                await db.scalars(
                    select(Fixture)
                    .join(TwoGameFixture, TwoGameFixture.fixture_id == Fixture.id)
                    .where(TwoGameFixture.game_id == target.game.id)
                    .order_by(Fixture.kickoff_utc, Fixture.home, Fixture.id)
                )
            ).all()
            quotes = await self.quotes().peek_many(
                [row.provider_event_id for row in fixtures], db=db
            )
            statuses = {
                row.fixture_id: str(row.payload.get("status", "pending"))
                for row in await db.scalars(
                    select(ProviderSnapshot).where(
                        ProviderSnapshot.fixture_id.in_([fixture.id for fixture in fixtures]),
                        ProviderSnapshot.key.startswith("fixture-state:v1:"),
                        ProviderSnapshot.payload["source"].astext == settings.odds_provider.value,
                    )
                )
            }
            competitions = selected_competition_slugs(target.league)
            accepted = {pick.fixture_id for pick in mine}
            rows = []
            for fixture in fixtures:
                eligible = (
                    target.game.window_start <= fixture.kickoff_utc < target.game.window_end
                    and (competitions is None or fixture.competition_id in competitions)
                    and not is_void_status(statuses.get(fixture.id, "pending"))
                )
                if not eligible and fixture.id not in accepted:
                    continue
                quote = quotes[fixture.provider_event_id]
                prices = (
                    [
                        dict(
                            market=selection.market.value,
                            outcome=selection.outcome.value,
                            odds=str(price),
                        )
                        for selection in quote.odds.selections
                        if (price := canonical_odds(selection.price)) is not None
                        and selection.market.value
                        in {market.value for market in target.league.offered_markets}
                    ]
                    if quote.odds
                    else []
                )
                rows.append(
                    dict(
                        fixture_id=str(fixture.id),
                        home=fixture.home,
                        away=fixture.away,
                        competition_id=fixture.competition_id,
                        kickoff_at=fixture.kickoff_utc.isoformat() + "Z",
                        status=statuses.get(fixture.id, "pending"),
                        eligible=eligible,
                        quote=dict(
                            prices=prices,
                            provider=quote.provider,
                            bookmaker=quote.bookmaker,
                            observed_at=quote.observed_at.isoformat() + "Z"
                            if quote.observed_at
                            else None,
                            age_seconds=quote.age_seconds,
                            availability=quote.availability
                            if prices
                            else "unavailable"
                            if quote.availability == "available"
                            else quote.availability,
                            degraded=quote.degraded,
                        ),
                    )
                )
            points = sum(pick.points for pick in mine)
            return FantasyGameView(
                **target.identity(),
                week_label=target.week.starts_on,
                week_number=str(target.week.number),
                destination=target.destination,
                opens_at=target.game.opens_at,
                locks_at=target.game.locks_at,
                window_start=target.game.window_start,
                window_end=target.game.window_end,
                entry_state=await entry_state(db, target, self.now()),
                coverage_state=target.game.coverage_state,
                fixtures=rows,
                my_entries=mine,
                slots=slots,
                progress=dict(filled_count=len(mine), slot_count=6, partial=0 < len(mine) < 6),
                result=dict(
                    status="pending" if mine else "no_entry",
                    points=points,
                    provisional=target.game.status != "settled",
                ),
                fee=fantasy_fee(
                    (
                        await project_fees(
                            db, target.league, player_id, target.week.starts_on, self.now()
                        )
                    ).for_week(target.week)
                ),
            )
