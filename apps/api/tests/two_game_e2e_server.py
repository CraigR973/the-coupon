"""Loopback-only synthetic browser harness. Production never imports this module."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

if os.environ.get("COUPON_TWO_GAME_E2E") != "local-scratch-only":
    raise RuntimeError("Use the dedicated disposable local browser runner")

import httpx
import jwt.api_jwt
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text, update

from src import auth
from src.config import OddsProviderName, settings
from src.database import AsyncSessionLocal, engine
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    ProviderAttempt,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.routers import auth as auth_routes
from src.routers import gameweek as gameweek_routes
from src.routers import me, picks, two_game_fantasy, two_game_group, two_game_reads, weekly_fees
from src.services import dues, scoring, season_calendar
from src.services import gameweek as weeks
from src.services.odds_api import OddsApiProvider
from src.services.odds_provider import EventSettlement, Market, Outcome, OutcomeResult
from src.services.two_game_corrections import correct_shared_fixture
from src.services.two_game_fantasy import FantasyEntries
from src.services.two_game_group import GroupEntries
from src.services.two_game_quotes import SharedQuotes
from src.services.two_game_reads import GameReads
from src.services.two_game_settlement import SettlementWorker
from src.services.two_game_storage import ensure_two_game_week, london_utc
from src.services.weekly_fees import (
    bill_all,
    close_memberships,
    financial_lock,
    release_new_entries,
)
from tests.test_two_game_quotes import Source

WEEK = date(2026, 11, 21)
# Hash the fixed synthetic PIN once; each login still exercises normal verification.
SYNTHETIC_PIN_HASH = auth.hash_pin("1357")
source = Source(engine)
source.clock.now = london_utc(WEEK, 11, 59)
source.source = "oddsapi"
settings.odds_provider = OddsProviderName.oddsapi
settings.odds_api_bookmaker = "Bet365"
settings.two_games_enabled = True
settings.vapid_private_key = settings.vapid_public_key = ""
quotes = SharedQuotes(
    AsyncSessionLocal, source.client, source="oddsapi", bookmaker="Bet365", clock=source.clock
)
result_statuses: dict[str, str] = {}
result_calls: list[str] = []
identities: dict[str, Any] = {}


class SimulatedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        moment = source.clock.now.replace(tzinfo=UTC)
        return (
            cls.fromtimestamp(moment.timestamp(), tz)
            if tz
            else cls.fromtimestamp(moment.timestamp(), UTC).replace(tzinfo=None)
        )


def clock():
    # PyJWT's NumericDate encoder and validator use this same datetime class.
    return SimulatedDateTime.fromtimestamp(
        source.clock.now.replace(tzinfo=UTC).timestamp(), UTC
    ).replace(tzinfo=None)


auth._now = clock
auth_routes._now = clock
jwt.api_jwt.datetime = SimulatedDateTime
for module in (me, gameweek_routes, weeks, scoring, dues, season_calendar):
    module.datetime = SimulatedDateTime
picks._now = clock
weekly_fees.utc_now = clock
two_game_group.group_entries = lambda: GroupEntries(AsyncSessionLocal, clock=clock)
two_game_fantasy.fantasy_entries = lambda: FantasyEntries(
    AsyncSessionLocal, clock=clock, quotes=quotes
)
two_game_reads.game_reads = lambda: GameReads(
    AsyncSessionLocal, two_games_enabled=settings.two_games_enabled, clock=clock
)
app.dependency_overrides[get_odds_provider] = lambda: source.client
app.dependency_overrides[get_optional_odds_provider] = lambda: source.client


async def result_transport(request):
    event = request.url.path.rsplit("/", 1)[-1]
    result_calls.append(event)
    return httpx.Response(
        200,
        json=dict(
            id=event, status=result_statuses.get(event, "finished"), scores=dict(home=2, away=0)
        ),
    )


result_provider = OddsApiProvider(
    "synthetic-results-only",
    budget=source.budget,
    client=httpx.AsyncClient(
        base_url="https://synthetic.invalid", transport=httpx.MockTransport(result_transport)
    ),
)


class SeedRequest(BaseModel):
    mixed: bool = False
    mixed_paid_legacy: bool = False
    enabled: bool = True
    credit_pence: int = 1000
    fantasy: bool = False
    legacy_points: bool = False


@app.post("/__two_game_e2e/seed")
async def seed(body: SeedRequest):
    source.clock.now = london_utc(WEEK - timedelta(days=7) if body.mixed else WEEK, 11, 59)
    if body.fantasy and not body.mixed:
        source.clock.now = london_utc(WEEK, 11, 50)
    source.price, source.priced, source.status = "2.15", True, 200
    source.send_unpriced_rows = source.block_first = False
    source.entered, source.release = asyncio.Event(), asyncio.Event()
    source.calls.clear()
    result_calls.clear()
    result_statuses.clear()
    settings.two_games_enabled = True
    async with AsyncSessionLocal() as db, db.begin():
        await db.execute(
            text(
                "TRUNCATE profiles, leagues, fixtures, rate_limit_counters, "
                "provider_attempts, provider_work, "
                "provider_snapshots, provider_controls, provider_refusals, "
                "notification_sends CASCADE"
            )
        )
        players = [
            Profile(display_name=name, pin_hash=SYNTHETIC_PIN_HASH, timezone="Europe/London")
            for name in ("Alice", "Bob", "Carol")
        ]
        db.add_all(players)
        await db.flush()
        league = League(
            slug="two-game-local",
            name="Two Game Local",
            created_by=players[0].id,
            payment_link_url="https://synthetic.invalid/payment",
        )
        db.add(league)
        await db.flush()
        db.add(
            TwoGameRollout(
                league_id=league.id,
                first_week=WEEK,
                enabled=True,
                effective_opening=london_utc(WEEK - timedelta(days=7), 12),
            )
        )
        for player in players:
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=player.id,
                    joined_at=london_utc(WEEK - timedelta(days=12)),
                )
            )
            db.add(
                LedgerEntry(
                    league_id=league.id,
                    player_id=player.id,
                    kind=LedgerKind.payment,
                    amount_pence=body.credit_pence,
                )
            )
        await db.flush()
        parents = []
        children = []
        fixtures = []
        for offset in (0, 7):
            label = WEEK + timedelta(days=offset)
            parent = await ensure_two_game_week(db, league.id, label)
            parents.append(parent)
            group = TwoGame(
                league_id=league.id,
                week_id=parent.id,
                kind="group",
                opens_at=london_utc(label - timedelta(days=5)),
                locks_at=london_utc(label, 14, 30),
                window_start=london_utc(label, 15),
                window_end=london_utc(label, 15),
                coverage_state="complete",
            )
            fantasy = TwoGame(
                league_id=league.id,
                week_id=parent.id,
                kind="fantasy",
                opens_at=london_utc(label - timedelta(days=7), 12),
                locks_at=london_utc(label, 12),
                window_start=london_utc(label, 12, 30),
                window_end=london_utc(label + timedelta(days=2)),
                coverage_state="complete",
            )
            db.add_all([group, fantasy])
            await db.flush()
            children.append(dict(group=str(group.id), fantasy=str(fantasy.id)))
            card = [
                Fixture(
                    provider_event_id=f"local-{offset}-{i}",
                    home=f"{'Next ' if offset else ''}Home {i+1}",
                    away=f"Away {i+1}",
                    competition="Synthetic",
                    competition_id="synthetic",
                    kickoff_utc=london_utc(
                        label + (timedelta(days=1) if i == 7 else timedelta()),
                        23 if i == 7 else 12 if i == 6 else 15,
                        59 if i == 7 else 30 if i == 6 else 0,
                    ),
                )
                for i in range(8)
            ]
            db.add_all(card)
            await db.flush()
            db.add_all(
                [TwoGameFixture(game_id=fantasy.id, fixture_id=fixture.id) for fixture in card]
            )
            db.add_all(
                [TwoGameFixture(game_id=group.id, fixture_id=fixture.id) for fixture in card[:6]]
            )
            fixtures.append([str(fixture.id) for fixture in card])
        old = Gameweek(
            league_id=league.id,
            starts_on=WEEK - timedelta(days=7),
            status=GameweekStatus.open if body.mixed else GameweekStatus.settled,
            picks_open_at_utc=london_utc(WEEK - timedelta(days=12)),
            locks_at_utc=london_utc(WEEK - timedelta(days=7), 14, 30),
            number=1,
        )
        old_fixture = Fixture(
            provider_event_id="local-legacy",
            home="Legacy Home",
            away="Legacy Away",
            competition="Synthetic",
            competition_id="synthetic",
            kickoff_utc=london_utc(old.starts_on, 15),
        )
        db.add_all([old, old_fixture])
        await db.flush()
        db.add(GameweekFixture(gameweek_id=old.id, fixture_id=old_fixture.id))
        if body.mixed_paid_legacy:
            league.entry_fee_pence = 100
            db.add(
                LedgerEntry(
                    league_id=league.id,
                    player_id=players[0].id,
                    kind=LedgerKind.round_due,
                    amount_pence=-100,
                    gameweek_id=old.id,
                )
            )
            db.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=old.id,
                    fixture_id=old_fixture.id,
                    player_id=players[0].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.AWAY,
                    runner_name="Legacy Away",
                    odds_at_pick=4,
                    status=PickStatus.pending,
                    pick_scope=league.pick_scope,
                )
            )
        if body.legacy_points:
            db.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=old.id,
                    fixture_id=old_fixture.id,
                    player_id=players[0].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.HOME,
                    runner_name="Legacy Home",
                    odds_at_pick=3,
                    points_awarded=30,
                    status=PickStatus.won,
                    pick_scope=league.pick_scope,
                )
            )
        identities.clear()
        identities.update(
            league_id=str(league.id),
            slug=league.slug,
            weeks=[str(parent.id) for parent in parents],
            games=children,
            fixtures=fixtures,
            players={player.display_name: str(player.id) for player in players},
            legacy_week=str(old.id),
            legacy_fixture=str(old_fixture.id),
        )
    async with AsyncSessionLocal() as db, db.begin():
        await db.execute(update(TwoGameRollout).values(enabled=body.enabled))
    from src.rate_limit import limiter

    limiter._storage.reset()
    if body.enabled:
        await bill_all(AsyncSessionLocal, clock())
    return {**identities, "now": source.clock.now.isoformat() + "Z"}


class ClockRequest(BaseModel):
    at: datetime


@app.post("/__two_game_e2e/clock")
async def set_clock(body: ClockRequest):
    source.clock.now = (
        body.at.replace(tzinfo=None)
        if body.at.tzinfo is None
        else body.at.astimezone(UTC).replace(tzinfo=None)
    )
    return {"now": source.clock.now.isoformat() + "Z"}


class SettleRequest(BaseModel):
    statuses: dict[str, str] = {}


@app.post("/__two_game_e2e/settle")
async def settle(body: SettleRequest):
    result_statuses.update(body.statuses)

    async def acquire():
        return result_provider

    worker = SettlementWorker(AsyncSessionLocal, acquire, source="oddsapi", clock=clock)
    return await worker.run()


@app.get("/__two_game_e2e/state")
async def state():
    async with AsyncSessionLocal() as db:
        group = [
            dict(
                week_id=str(pick.week_id),
                player_id=str(pick.player_id),
                fixture_id=str(pick.fixture_id),
                revision=pick.revision,
                operation_id=str(pick.operation_id),
                result=pick.status,
            )
            for pick in await db.scalars(select(GroupPick))
        ]
        legacy = [
            dict(
                fixture_id=str(pick.fixture_id),
                outcome=pick.outcome.value,
                points=pick.points_awarded,
            )
            for pick in await db.scalars(select(Pick))
        ]
        fantasy = [
            dict(
                week_id=str(pick.week_id),
                player_id=str(pick.player_id),
                slot=pick.slot,
                fixture_id=str(pick.fixture_id),
                revision=pick.revision,
                operation_id=str(pick.operation_id),
                result=pick.status,
                points=pick.points_awarded,
            )
            for pick in await db.scalars(select(FantasyPick))
        ]
        obligations = [
            dict(player_id=str(row.player_id), week_label=str(row.week_label))
            for row in await db.scalars(select(WeeklyFeeObligation))
        ]
        counts = {
            model.__tablename__: await db.scalar(select(func.count()).select_from(model))
            for model in (GameOperation, WeeklyFeeObligation, ProviderAttempt)
        }
    return dict(
        obligations=obligations,
        group=group,
        fantasy=fantasy,
        legacy=legacy,
        counts=counts,
        quote_calls=len(source.calls),
        result_calls=len(result_calls),
    )


class SwitchRequest(BaseModel):
    enabled: bool | None = None
    suspended: bool | None = None


@app.post("/__two_game_e2e/switch")
async def switch(body: SwitchRequest):
    values = body.model_dump(exclude_none=True)
    async with AsyncSessionLocal() as db, db.begin():
        await db.execute(update(TwoGameRollout).values(**values))
    return values


class LeaveRequest(BaseModel):
    player_id: uuid.UUID


@app.post("/__two_game_e2e/leave")
async def leave(body: LeaveRequest):
    league_id = uuid.UUID(identities["league_id"])
    async with AsyncSessionLocal() as db, db.begin():
        await financial_lock(db, league_id)
        await close_memberships(db, [league_id], clock(), player_id=body.player_id)
        await release_new_entries(db, body.player_id, [league_id], clock())
        membership = await db.scalar(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.player_id == body.player_id,
            )
        )
        if membership is None:
            raise HTTPException(404)
        membership.deleted_at = clock()
    return {"left": True}


class CreditRequest(BaseModel):
    player_id: uuid.UUID
    amount_pence: int


@app.post("/__two_game_e2e/credit")
async def credit(body: CreditRequest):
    if body.amount_pence <= 0:
        raise HTTPException(422)
    async with AsyncSessionLocal() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=uuid.UUID(identities["league_id"]),
                player_id=body.player_id,
                kind=LedgerKind.payment,
                amount_pence=body.amount_pence,
                monzo_transaction_id=f"synthetic-browser-{uuid.uuid4().hex}",
                created_at=clock(),
            )
        )
    return {"recorded": True}


@app.get("/__two_game_e2e/invalid-auth-tokens")
async def invalid_auth_tokens():
    import jwt

    moment = clock().replace(tzinfo=UTC).timestamp()
    payload = {"sub": identities["players"]["Alice"], "role": "player"}
    return {
        "expired": jwt.encode(
            {**payload, "iat": moment - 25 * 3600, "exp": moment - 3600},
            settings.jwt_access_secret,
            algorithm="HS256",
        ),
        "future": jwt.encode(
            {**payload, "iat": moment + 3600, "exp": moment + 24 * 3600},
            settings.jwt_access_secret,
            algorithm="HS256",
        ),
    }


class QuoteRequest(BaseModel):
    price: str = "2.15"
    priced: bool = True
    warm: bool = False
    week: int = 0


@app.post("/__two_game_e2e/quotes")
async def control_quotes(body: QuoteRequest):
    source.price, source.priced = body.price, body.priced
    if body.warm:
        await quotes.refresh_many(
            [f"local-{body.week * 7}-{i}" for i in range(8)], category="foreground"
        )
    return {"calls": len(source.calls)}


class CorrectionRequest(BaseModel):
    fixture_id: uuid.UUID
    home_won: bool


@app.post("/__two_game_e2e/correct")
async def correct(body: CorrectionRequest):
    async with AsyncSessionLocal() as db, db.begin():
        fixture = await db.get(Fixture, body.fixture_id)
        if fixture is None:
            raise HTTPException(404)
        settlement = EventSettlement(
            provider_event_id=fixture.provider_event_id,
            status="finished",
            settled=True,
            settled_markets=[Market.MATCH_ODDS],
            outcomes=[
                OutcomeResult(
                    market=Market.MATCH_ODDS,
                    outcome=outcome,
                    won=(outcome == Outcome.HOME if body.home_won else outcome == Outcome.AWAY),
                )
                for outcome in (Outcome.HOME, Outcome.DRAW, Outcome.AWAY)
            ],
        )
        result = await correct_shared_fixture(db, fixture.id, settlement, clock())
    return {"changed": len(result.fantasy) + len(result.group) + len(result.legacy)}


@app.post("/__two_game_e2e/bill")
async def run_billing():
    await bill_all(AsyncSessionLocal, clock())
    return {"billed": True}
