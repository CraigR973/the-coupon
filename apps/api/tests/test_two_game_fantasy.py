"""Addressed fantasy HTTP, exact prices, independent slots and real transport spend."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.auth import create_access_token
from src.config import OddsProviderName, settings
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.league import League, PickMarket
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.profile import Profile
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    ProviderAttempt,
    ProviderSnapshot,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.routers import two_game_fantasy as routes
from src.routers import two_game_group as group_routes
from src.services import two_game_fantasy as service
from src.services.betfair import FakeBetfair
from src.services.odds_api import OddsApiProvider
from src.services.provider_budget import BudgetPolicy, ProviderBudget
from src.services.two_game_fantasy import FantasyEntries
from src.services.two_game_group import GroupEntries
from src.services.two_game_provider import ProviderIdentity, native_identity
from src.services.two_game_quotes import SharedQuotes
from src.services.two_game_storage import ensure_two_game_week, london_utc
from src.services.weekly_fees import close_memberships, financial_lock, release_new_entries
from tests.test_two_game_quotes import Source

WEEK = date(2026, 11, 21)


@dataclass
class Fantasy:
    sessions: async_sessionmaker
    league: League
    players: list[Profile]
    parent: Gameweek
    game: TwoGame
    group: TwoGame
    fixtures: list[Fixture]
    source: Source
    quotes: SharedQuotes
    acquisitions: list

    @property
    def path(self):
        return f"/api/v1/leagues/{self.league.id}/weeks/{self.parent.id}/games/fantasy"

    def body(self, fixture=0, revision=0, **values):
        return {
            "fixture_id": str(self.fixtures[fixture].id),
            "market": "MATCH_ODDS",
            "outcome": "HOME",
            "odds": "2.1500",
            "expected_revision": revision,
            "operation_id": str(uuid.uuid4()),
            **values,
        }

    async def request(self, method, *, slot=1, player=0, body=None, path=None):
        token = create_access_token(self.players[player].id, self.players[player].role)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://local.test"
        ) as client:
            return await client.request(
                method,
                path or self.path + f"/slots/{slot}",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )

    async def save(self, slot=1, body=None, *, player=0):
        return await self.request("PUT", slot=slot, player=player, body=body or self.body())

    async def count(self, model):
        async with self.sessions() as db:
            clause = (
                model.meter == self.source.budget.meter
                if model is ProviderAttempt
                else model.league_id == self.league.id
            )
            return await db.scalar(select(func.count()).select_from(model).where(clause))


@pytest_asyncio.fixture
async def fantasy(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    monkeypatch.setattr(settings, "odds_provider", OddsProviderName.oddsapi)
    monkeypatch.setattr(settings, "odds_api_bookmaker", "Bet365")
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    source = Source(db_engine)
    source.source = "oddsapi"
    async with sessions() as db, db.begin():
        players = [
            Profile(display_name=f"Fantasy {uuid.uuid4().hex}", pin_hash="x") for _ in range(4)
        ]
        db.add_all(players)
        await db.flush()
        league = League(
            slug=f"fantasy-{uuid.uuid4().hex}",
            name="Synthetic fantasy",
            created_by=players[0].id,
            offered_markets=[PickMarket.MATCH_ODDS, PickMarket.BOTH_TEAMS_TO_SCORE],
            payment_link_url="https://synthetic.invalid/pay",
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
        for player in players[:3]:
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=player.id,
                    joined_at=london_utc(WEEK - timedelta(days=5)),
                )
            )
            db.add(
                LedgerEntry(
                    league_id=league.id,
                    player_id=player.id,
                    kind=LedgerKind.payment,
                    amount_pence=1000,
                )
            )
        await db.flush()
        parent = await ensure_two_game_week(db, league.id, WEEK)
        group = TwoGame(
            league_id=league.id,
            week_id=parent.id,
            kind="group",
            opens_at=london_utc(WEEK - timedelta(days=5)),
            locks_at=london_utc(WEEK, 14, 30),
            window_start=london_utc(WEEK, 15),
            window_end=london_utc(WEEK, 15),
            coverage_state="complete",
        )
        game = TwoGame(
            league_id=league.id,
            week_id=parent.id,
            kind="fantasy",
            opens_at=london_utc(WEEK - timedelta(days=7), 12),
            locks_at=london_utc(WEEK, 12),
            window_start=london_utc(WEEK, 12, 30),
            window_end=london_utc(WEEK + timedelta(days=2)),
            coverage_state="complete",
        )
        db.add_all([group, game])
        fixtures = [
            Fixture(
                provider_event_id=f"fantasy-{uuid.uuid4().hex}",
                home=f"Home {i}",
                away=f"Away {i}",
                competition="Synthetic",
                competition_id="synthetic",
                kickoff_utc=london_utc(WEEK, 15),
            )
            for i in range(9)
        ]
        fixtures[6].kickoff_utc = london_utc(WEEK, 12, 30)
        fixtures[7].kickoff_utc = london_utc(WEEK + timedelta(days=1), 23, 59)
        db.add_all(fixtures)
        await db.flush()
        db.add_all([TwoGameFixture(game_id=game.id, fixture_id=row.id) for row in fixtures])
        db.add_all([TwoGameFixture(game_id=group.id, fixture_id=row.id) for row in fixtures[:6]])
        await db.flush()
        # Census can move an already linked fixture beyond the stored window.
        # The API must recheck it; initial linking correctly rejects that date.
        fixtures[8].kickoff_utc = london_utc(WEEK + timedelta(days=2))
    acquisitions = []

    async def acquire():
        acquisitions.append(True)
        assert native_identity(source.client) == ProviderIdentity("oddsapi", "Bet365")
        return source.client

    quotes = SharedQuotes(
        sessions, acquire=acquire, source="oddsapi", bookmaker="Bet365", clock=source.clock
    )
    result = Fantasy(
        sessions, league, players, parent, game, group, fixtures, source, quotes, acquisitions
    )
    monkeypatch.setattr(
        routes,
        "fantasy_entries",
        lambda: FantasyEntries(sessions, clock=source.clock, quotes=result.quotes),
    )
    monkeypatch.setattr(
        group_routes, "group_entries", lambda: GroupEntries(sessions, clock=source.clock)
    )
    try:
        yield result
    finally:
        await source.close()
        async with sessions() as db, db.begin():
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id == league.id)
                .values(enabled=False)
            )
            await db.execute(
                update(League)
                .where(League.id == league.id)
                .values(deleted_at=datetime(2026, 12, 20))
            )
            await db.execute(
                update(Profile)
                .where(Profile.id.in_([p.id for p in players]))
                .values(deleted_at=datetime(2026, 12, 20), is_active=False)
            )


@pytest.mark.asyncio
async def test_empty_reads_are_six_addressed_slots_without_fees_or_provider(fantasy):
    response = await fantasy.request("GET", path=fantasy.path)
    assert response.status_code == 200, response.text
    view = response.json()
    assert len(view["slots"]) == 6
    assert all(row["pick"] is None and row["revision"] == 0 for row in view["slots"])
    assert view["my_entries"] == []
    assert view["progress"] == dict(filled_count=0, slot_count=6, partial=False)
    assert view["result"]["status"] == "no_entry"
    assert (
        view["fee"]["destination"]
        == f"/leagues/{fantasy.league.id}/weeks/{fantasy.parent.id}/fantasy#payment"
    )
    assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 0
    assert fantasy.acquisitions == fantasy.source.calls == []


@pytest.mark.asyncio
async def test_six_independent_saves_share_one_fee_and_freeze_exact_provenance(fantasy):
    for slot in range(1, 7):
        response = await fantasy.save(slot, fantasy.body(slot - 1))
        assert response.status_code == 200, response.text
        pick = response.json()["pick"]
        assert (pick["slot"], pick["frozen_odds"], pick["provider"], pick["bookmaker"]) == (
            slot,
            "2.1500",
            "oddsapi",
            "Bet365",
        )
        assert pick["points"] == 0 and pick["result"] == "pending"
    assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 6
    assert await fantasy.count(WeeklyFeeObligation) == 1
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 6


@pytest.mark.parametrize("slot", [-1, 0, 7])
@pytest.mark.asyncio
async def test_invalid_slot_refuses_before_fee_or_acquisition(fantasy, slot):
    response = await fantasy.save(slot)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "INVALID_SLOT"
    assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 0
    assert fantasy.acquisitions == []


@pytest.mark.asyncio
async def test_own_fixture_cannot_fill_two_slots_but_members_and_group_share(fantasy):
    first = await fantasy.save()
    assert first.status_code == 200, first.text
    duplicate = await fantasy.save(2)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "FIXTURE_ALREADY_PICKED"
    other = await fantasy.save(1, player=1)
    assert other.status_code == 200, other.text
    group_path = fantasy.path.replace("fantasy", "group") + "/pick"
    group_body = fantasy.body()
    group_body.pop("odds")
    group = await fantasy.request("PUT", path=group_path, body=group_body)
    assert group.status_code == 200, group.text
    assert "frozen_odds" not in group.json()["pick"]
    assert await fantasy.count(GroupPick) == 1
    assert await fantasy.count(FantasyPick) == 2
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.asyncio
async def test_failed_duplicate_replacement_keeps_original_price_and_other_slot(fantasy):
    a = await fantasy.save(1, fantasy.body(0))
    b = await fantasy.save(2, fantasy.body(1))
    response = await fantasy.save(1, fantasy.body(1, 1))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "FIXTURE_ALREADY_PICKED"
    assert (await fantasy.request("GET", slot=1)).json() == a.json()
    assert (await fantasy.request("GET", slot=2)).json() == b.json()
    assert len(fantasy.source.calls) == 2


@pytest.mark.asyncio
async def test_replacement_updates_only_its_slot_and_old_operation_cannot_revert_it(fantasy):
    old_body = fantasy.body(0)
    old = await fantasy.save(1, old_body)
    other = await fantasy.save(2, fantasy.body(1))
    newer = await fantasy.save(1, fantasy.body(2, 1))
    assert newer.status_code == 200, newer.text
    assert newer.json()["revision"] == 2
    assert newer.json()["pick"]["id"] == old.json()["pick"]["id"]
    replay = await fantasy.save(1, old_body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == old.json()
    assert (await fantasy.request("GET", slot=1)).json() == newer.json()
    assert (await fantasy.request("GET", slot=2)).json() == other.json()
    assert len(fantasy.source.calls) == 3


@pytest.mark.asyncio
async def test_same_slot_concurrent_fills_have_one_winner_without_overwrite(fantasy):
    results = await asyncio.gather(
        fantasy.save(1, fantasy.body(0)), fantasy.save(1, fantasy.body(1))
    )
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 1
    assert await fantasy.count(WeeklyFeeObligation) == 1


@pytest.mark.asyncio
async def test_two_slots_racing_for_own_fixture_coalesce_price_and_keep_one(fantasy):
    results = await asyncio.gather(fantasy.save(1), fantasy.save(2))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 1
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.asyncio
async def test_distinct_slots_fill_concurrently_and_identical_operation_replays_once(fantasy):
    body = fantasy.body(0)
    results = await asyncio.gather(
        fantasy.save(1, body), fantasy.save(1, body), fantasy.save(2, fantasy.body(1))
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert results[0].json() == results[1].json()
    assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 2
    assert len(fantasy.source.calls) == 2


@pytest.mark.asyncio
async def test_canonical_named_price_replays_but_changed_body_conflicts_after_lock(
    fantasy, monkeypatch
):
    body = fantasy.body(0, odds="2.15")
    first = await fantasy.save(1, body)
    assert first.status_code == 200, first.text
    fantasy.source.clock.now = london_utc(WEEK, 12)
    monkeypatch.setattr(settings, "two_games_enabled", False)
    replay = await fantasy.save(1, {**body, "odds": "2.15000"})
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    conflict = await fantasy.save(1, {**body, "odds": "2.1501"})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "OPERATION_CONFLICT"
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.asyncio
async def test_four_place_price_move_needs_explicit_current_confirmation(fantasy):
    fantasy.source.price = "2.1234"
    response = await fantasy.save(1, fantasy.body(0, odds="2.1235"))
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "PRICE_MOVED" and detail["current_odds"] == "2.1234"
    assert detail["slot"] == 1 and detail["week_id"] == str(fantasy.parent.id)
    assert await fantasy.count(FantasyPick) == 0
    assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 1
    confirm = await fantasy.save(1, fantasy.body(0, odds=detail["current_odds"]))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["pick"]["frozen_odds"] == "2.1234"
    assert len(fantasy.source.calls) == 1


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", "0.00001", "2.12345", "1000000"])
@pytest.mark.asyncio
async def test_invalid_client_price_refuses_without_fees_or_transport(fantasy, price):
    response = await fantasy.save(1, fantasy.body(0, odds=price))
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 0


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", "2.12345", "1000000"])
@pytest.mark.asyncio
async def test_invalid_source_price_preserves_slot_and_spent_attempt(fantasy, price):
    original = await fantasy.save()
    assert original.status_code == 200, original.text
    fantasy.source.price = price
    response = await fantasy.save(1, fantasy.body(1, 1))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "ODDS_UNAVAILABLE"
    assert (await fantasy.request("GET")).json() == original.json()
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2
    assert await fantasy.count(WeeklyFeeObligation) == 1


@pytest.mark.parametrize("price", ["2.1234", "2.15000", "999999.9999"])
@pytest.mark.asyncio
async def test_valid_exact_source_prices_persist_without_rounding(fantasy, price):
    fantasy.source.price = price
    response = await fantasy.save(1, fantasy.body(0, odds=price))
    assert response.status_code == 200, response.text
    async with fantasy.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == fantasy.game.id))
        assert pick.frozen_odds == Decimal(price)
    assert Decimal(response.json()["pick"]["frozen_odds"]) == Decimal(price)


@pytest.mark.asyncio
async def test_missing_selected_market_and_bounded_empty_quote_never_make_entry(fantasy):
    response = await fantasy.save(1, fantasy.body(0, market="BOTH_TEAMS_TO_SCORE", outcome="YES"))
    assert response.status_code == 503, response.text
    fantasy.source.priced = False
    for _ in range(2):
        response = await fantasy.save(2, fantasy.body(1))
        assert response.status_code == 503, response.text
    assert await fantasy.count(FantasyPick) == 0
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2


@pytest.mark.asyncio
async def test_exhausted_budget_refuses_before_dispatch_but_readback_and_replay_work(fantasy):
    fantasy.source.budget.policy = BudgetPolicy(hourly=1)
    body = fantasy.body()
    first = await fantasy.save(1, body)
    assert first.status_code == 200, first.text
    refused = await fantasy.save(2, fantasy.body(1))
    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"]["code"] == "PICKS_BUSY"
    assert refused.json()["detail"]["retry_after_seconds"] == 3600
    assert (await fantasy.request("GET")).json() == first.json()
    assert (await fantasy.save(1, body)).json() == first.json()
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    assert await fantasy.count(FantasyPick) == 1


@pytest.mark.asyncio
async def test_slow_quote_crossing_noon_is_spent_without_accepting_pick(fantasy):
    fantasy.source.block_first = True
    task = asyncio.create_task(fantasy.save())
    try:
        await asyncio.wait_for(fantasy.source.entered.wait(), 5)
        fantasy.source.clock.now = london_utc(WEEK, 12)
        fantasy.source.release.set()
        response = await task
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "LOCKED"
        assert await fantasy.count(FantasyPick) == 0
        assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 1
    finally:
        fantasy.source.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_business_rollback_keeps_quote_fee_and_spend_for_same_operation_retry(
    fantasy, monkeypatch
):
    old = await fantasy.save()
    assert old.status_code == 200, old.text
    body = fantasy.body(1, 1)
    original_hash = service.operation_hash

    def fail_hash(body):
        raise RuntimeError("synthetic business rollback")

    monkeypatch.setattr(service, "operation_hash", fail_hash)
    with pytest.raises(RuntimeError, match="business rollback"):
        await fantasy.save(1, body)
    assert (await fantasy.request("GET")).json() == old.json()
    assert await fantasy.count(GameOperation) == 1
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2
    assert await fantasy.count(WeeklyFeeObligation) == 1
    monkeypatch.setattr(service, "operation_hash", original_hash)
    retry = await fantasy.save(1, body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["revision"] == 2
    assert len(fantasy.source.calls) == 2


@pytest.mark.parametrize(("fixture", "allowed"), [(6, True), (7, True), (8, False)])
@pytest.mark.asyncio
async def test_saturday_inclusive_sunday_included_monday_exclusive(fantasy, fixture, allowed):
    response = await fantasy.save(1, fantasy.body(fixture))
    assert response.status_code == (200 if allowed else 422), response.text
    assert len(fantasy.source.calls) == (1 if allowed else 0)


async def additional_week(fantasy, label, *, another_league=False):
    async with fantasy.sessions() as db, db.begin():
        league = fantasy.league
        if another_league:
            league = League(
                slug=f"another-{uuid.uuid4().hex}",
                name="Synthetic other league",
                created_by=fantasy.players[0].id,
            )
            db.add(league)
            await db.flush()
            db.add(
                TwoGameRollout(
                    league_id=league.id,
                    first_week=label,
                    enabled=True,
                    effective_opening=london_utc(label - timedelta(days=7), 12),
                )
            )
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=fantasy.players[0].id,
                    joined_at=london_utc(WEEK - timedelta(days=5)),
                )
            )
            db.add(
                LedgerEntry(
                    league_id=league.id,
                    player_id=fantasy.players[0].id,
                    kind=LedgerKind.payment,
                    amount_pence=1000,
                )
            )
            await db.flush()
        parent = await ensure_two_game_week(db, league.id, label)
        game = TwoGame(
            league_id=league.id,
            week_id=parent.id,
            kind="fantasy",
            opens_at=london_utc(label - timedelta(days=7), 12),
            locks_at=london_utc(label, 12),
            window_start=london_utc(label, 12, 30),
            window_end=london_utc(label + timedelta(days=2)),
            coverage_state="complete",
        )
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
        fixtures = [
            Fixture(
                provider_event_id=f"later-{uuid.uuid4().hex}",
                home=f"Later Home {i}",
                away=f"Later Away {i}",
                competition="Synthetic",
                competition_id="synthetic",
                kickoff_utc=london_utc(label, 15),
            )
            for i in range(6)
        ]
        db.add_all([game, group, *fixtures])
        await db.flush()
        db.add_all([TwoGameFixture(game_id=game.id, fixture_id=row.id) for row in fixtures])
        db.add_all([TwoGameFixture(game_id=group.id, fixture_id=row.id) for row in fixtures])
    return league, parent, game, fixtures


async def target_save(fantasy, target, slot=1, fixture=0):
    league, parent, game, fixtures = target
    body = {**fantasy.body(), "fixture_id": str(fixtures[fixture].id)}
    path = f"/api/v1/leagues/{league.id}/weeks/{parent.id}/games/fantasy/slots/{slot}"
    return await fantasy.request("PUT", path=path, body=body)


async def transport_statuses(fantasy, statuses):
    original = fantasy.source.dispatch
    offset = len(fantasy.source.calls)

    async def dispatch(request):
        fantasy.source.status = statuses[min(len(fantasy.source.calls) - offset, len(statuses) - 1)]
        return await original(request)

    prior = fantasy.source.client
    fantasy.source.client = OddsApiProvider(
        "synthetic-not-an-account-key",
        budget=fantasy.source.budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    await prior.close()


@pytest.mark.asyncio
async def test_actual_transport_two_failures_then_success_charge_three_attempts(fantasy):
    await transport_statuses(fantasy, [500, 500, 200])
    response = await fantasy.save()
    assert response.status_code == 200, response.text
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 3
    assert await fantasy.count(FantasyPick) == await fantasy.count(WeeklyFeeObligation) == 1


@pytest.mark.asyncio
async def test_actual_transport_budget_stops_retry_before_third_dispatch(fantasy):
    fantasy.source.budget.policy = BudgetPolicy(hourly=2)
    await transport_statuses(fantasy, [500, 500, 200])
    response = await fantasy.save()
    assert response.status_code == 429, response.text
    assert response.json()["detail"]["code"] == "PICKS_BUSY"
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2
    assert await fantasy.count(FantasyPick) == 0
    assert await fantasy.count(WeeklyFeeObligation) == 1


@pytest.mark.asyncio
async def test_upstream_429_then_durable_cooldown_refuse_without_second_dispatch(fantasy):
    fantasy.source.status = 429
    first = await fantasy.save()
    second = await fantasy.save(2, fantasy.body(1))
    assert first.status_code == second.status_code == 429, (first.text, second.text)
    assert first.json()["detail"]["code"] == second.json()["detail"]["code"] == "PICKS_BUSY"
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    assert await fantasy.count(FantasyPick) == 0


@pytest.mark.asyncio
async def test_cancelled_dispatched_write_retains_spend_and_lease_across_restart(fantasy):
    fantasy.source.block_first = True
    body = fantasy.body()
    task = asyncio.create_task(fantasy.save(1, body))
    try:
        await asyncio.wait_for(fantasy.source.entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await fantasy.count(ProviderAttempt) == 1
        assert await fantasy.count(FantasyPick) == 0
        assert (await fantasy.request("GET")).json()["pick"] is None

        async def acquire():
            return fantasy.source.client

        fantasy.quotes = SharedQuotes(
            fantasy.sessions,
            acquire=acquire,
            source="oddsapi",
            bookmaker="Bet365",
            clock=fantasy.source.clock,
        )
        busy = await fantasy.save(1, body)
        assert busy.status_code == 503, busy.text
        assert len(fantasy.source.calls) == 1
        fantasy.source.clock.now += timedelta(seconds=46)
        fantasy.source.release.set()
        retry = await fantasy.save(1, body)
        assert retry.status_code == 200, retry.text
        assert (await fantasy.request("GET")).json()["operation_id"] == body["operation_id"]
        assert (await fantasy.save(1, body)).json() == retry.json()
        assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2
        assert await fantasy.count(WeeklyFeeObligation) == 1
    finally:
        fantasy.source.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_six_current_then_six_next_at_noon_preserve_legacy_limits(fantasy):
    later = await additional_week(fantasy, WEEK + timedelta(days=7))
    fantasy.source.clock.now = london_utc(WEEK, 12) - timedelta(microseconds=1)
    for slot in range(1, 7):
        response = await fantasy.save(slot, fantasy.body(slot - 1))
        assert response.status_code == 200, response.text
    fantasy.source.clock.now = london_utc(WEEK, 12)
    locked = await fantasy.save(1, fantasy.body(6, 1))
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"]["code"] == "LOCKED"
    for slot in range(1, 7):
        response = await target_save(fantasy, later, slot, slot - 1)
        assert response.status_code == 200, response.text
    assert await fantasy.count(FantasyPick) == 12
    assert await fantasy.count(WeeklyFeeObligation) == 2
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 12


@pytest.mark.asyncio
async def test_current_next_other_league_and_background_share_last_capacity(fantasy):
    later = await additional_week(fantasy, WEEK + timedelta(days=7))
    another = await additional_week(fantasy, WEEK + timedelta(days=7), another_league=True)
    fantasy.source.budget.policy = BudgetPolicy(hourly=1)
    fantasy.source.clock.now = london_utc(WEEK, 12) - timedelta(microseconds=1)
    first = await fantasy.save()
    assert first.status_code == 200, first.text
    fantasy.source.clock.now = london_utc(WEEK, 12)
    next_result, other_result = await asyncio.gather(
        target_save(fantasy, later), target_save(fantasy, another)
    )
    assert next_result.status_code == other_result.status_code == 429, (
        next_result.text,
        other_result.text,
    )
    from src.services.provider_budget import ProviderBudgetRefused

    with pytest.raises(ProviderBudgetRefused):
        await fantasy.quotes.refresh_many([later[3][1].provider_event_id], category="opening")
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.parametrize("age", [timedelta(seconds=60), timedelta(seconds=60, microseconds=1)])
@pytest.mark.asyncio
async def test_route_uses_exact_sixty_seconds_then_refreshes(fantasy, age):
    await fantasy.quotes.get_fresh(fantasy.fixtures[0].provider_event_id)
    fantasy.source.clock.now += age
    response = await fantasy.save()
    assert response.status_code == 200, response.text
    expected = 1 if age == timedelta(seconds=60) else 2
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == expected


@pytest.mark.asyncio
async def test_quote_aging_while_waiting_final_lock_is_not_frozen(fantasy, monkeypatch):
    await fantasy.quotes.get_fresh(fantasy.fixtures[0].provider_event_id)
    fantasy.source.clock.now += timedelta(seconds=59)
    reached, release = asyncio.Event(), asyncio.Event()
    original = service.lock_and_replay
    calls = 0

    async def delayed(db, **identity):
        nonlocal calls
        calls += 1
        if calls == 2:
            reached.set()
            await release.wait()
        return await original(db, **identity)

    monkeypatch.setattr(service, "lock_and_replay", delayed)
    task = asyncio.create_task(fantasy.save())
    try:
        await asyncio.wait_for(reached.wait(), 5)
        async with fantasy.sessions() as db, db.begin():
            await financial_lock(db, fantasy.league.id)
            fantasy.source.clock.now += timedelta(seconds=2)
        release.set()
        response = await task
        assert response.status_code == 503, response.text
        assert response.json()["detail"]["code"] == "ODDS_UNAVAILABLE"
        assert await fantasy.count(FantasyPick) == 0
        assert len(fantasy.source.calls) == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_future_dated_observation_is_never_frozen(fantasy, monkeypatch):
    view = await fantasy.quotes.get_fresh(fantasy.fixtures[0].provider_event_id)

    async def future(event_id):
        return replace(view, observed_at=fantasy.source.clock.now + timedelta(seconds=1))

    monkeypatch.setattr(fantasy.quotes, "get_fresh", future)
    response = await fantasy.save()
    assert response.status_code == 503, response.text
    assert await fantasy.count(FantasyPick) == 0
    assert len(fantasy.source.calls) == 1


@pytest.mark.asyncio
async def test_early_three_week_fees_survive_quote_failure_and_current_group_stays_paid(fantasy):
    current = await additional_week(fantasy, WEEK + timedelta(days=7))
    future = await additional_week(fantasy, WEEK + timedelta(days=14))
    fantasy.source.clock.now = london_utc(WEEK + timedelta(days=7), 12)
    fantasy.source.priced = False
    refused = await target_save(fantasy, future)
    assert refused.status_code == 503, refused.text
    assert await fantasy.count(WeeklyFeeObligation) == 3
    before = len(fantasy.source.calls)
    league, parent, _, fixtures = current
    body = fantasy.body()
    body.pop("odds")
    body["fixture_id"] = str(fixtures[0].id)
    path = f"/api/v1/leagues/{league.id}/weeks/{parent.id}/games/group/pick"
    group = await fantasy.request("PUT", path=path, body=body)
    assert group.status_code == 200, group.text
    assert len(fantasy.source.calls) == before
    assert await fantasy.count(WeeklyFeeObligation) == 3


@pytest.mark.asyncio
async def test_shared_one_connection_pool_supports_browse_auth_quote_and_save(
    fantasy, db_engine, monkeypatch
):
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.routers import two_game_protocol

    engine = create_async_engine(db_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.5)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fantasy.source.budget = ProviderBudget(
        sessions, meter=fantasy.source.budget.meter, clock=fantasy.source.clock
    )
    original = fantasy.source.dispatch

    async def dispatch(request):
        async with sessions() as db, db.begin():
            await financial_lock(db, fantasy.league.id)
        return await original(request)

    old = fantasy.source.client
    fantasy.source.client = OddsApiProvider(
        "synthetic-key",
        budget=fantasy.source.budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    await old.close()

    async def acquire():
        return fantasy.source.client

    quotes = SharedQuotes(
        sessions, acquire=acquire, source="oddsapi", bookmaker="Bet365", clock=fantasy.source.clock
    )
    monkeypatch.setattr(two_game_protocol, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(
        routes,
        "fantasy_entries",
        lambda: FantasyEntries(sessions, clock=fantasy.source.clock, quotes=quotes),
    )
    try:
        view = await fantasy.request("GET", path=fantasy.path)
        assert view.status_code == 200, view.text
        assert fantasy.source.calls == []
        response = await fantasy.save()
        assert response.status_code == 200, response.text
        assert engine.pool.checkedout() == 0
        assert len(fantasy.source.calls) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unpaid_save_commits_due_before_refusal_and_never_acquires_provider(fantasy):
    async with fantasy.sessions() as db, db.begin():
        await db.execute(
            delete(LedgerEntry).where(
                LedgerEntry.league_id == fantasy.league.id,
                LedgerEntry.player_id == fantasy.players[0].id,
                LedgerEntry.kind == LedgerKind.payment,
            )
        )
    refused = await fantasy.save()
    assert refused.status_code == 402, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "PAYMENT_REQUIRED"
    assert detail["amount_owed_pence"] == 100
    assert (
        detail["destination"]
        == f"/leagues/{fantasy.league.id}/weeks/{fantasy.parent.id}/fantasy#payment"
    )
    assert await fantasy.count(WeeklyFeeObligation) == 1
    assert await fantasy.count(FantasyPick) == await fantasy.count(ProviderAttempt) == 0
    assert fantasy.acquisitions == []
    async with fantasy.sessions() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=fantasy.league.id,
                player_id=fantasy.players[0].id,
                kind=LedgerKind.payment,
                amount_pence=100,
            )
        )
    accepted = await fantasy.save()
    assert accepted.status_code == 200, accepted.text
    assert await fantasy.count(WeeklyFeeObligation) == 1


@pytest.mark.parametrize("gate", ["off", "suspended", "nonmember", "not_open"])
@pytest.mark.asyncio
async def test_free_fantasy_refusals_have_no_due_quote_or_mutation(fantasy, monkeypatch, gate):
    player = 0
    if gate == "off":
        monkeypatch.setattr(settings, "two_games_enabled", False)
    elif gate == "suspended":
        async with fantasy.sessions() as db, db.begin():
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id == fantasy.league.id)
                .values(suspended=True)
            )
    elif gate == "nonmember":
        player = 3
    else:
        fantasy.source.clock.now = fantasy.game.opens_at - timedelta(microseconds=1)
    response = await fantasy.save(player=player)
    assert response.status_code == (404 if gate in {"off", "nonmember"} else 409), response.text
    assert (
        await fantasy.count(FantasyPick)
        == await fantasy.count(WeeklyFeeObligation)
        == await fantasy.count(ProviderAttempt)
        == 0
    )
    assert fantasy.acquisitions == []


@pytest.mark.asyncio
async def test_current_readback_never_exposes_another_members_slot(fantasy):
    accepted = await fantasy.save()
    assert accepted.status_code == 200, accepted.text
    other = await fantasy.request("GET", player=1)
    assert other.status_code == 200, other.text
    assert other.json()["pick"] is None and other.json()["revision"] == 0
    view = await fantasy.request("GET", path=fantasy.path, player=1)
    assert view.status_code == 200, view.text
    assert view.json()["my_entries"] == []
    assert all(slot["pick"] is None for slot in view.json()["slots"])
    assert len(fantasy.source.calls) == 1


@pytest.mark.asyncio
async def test_existing_foreign_league_week_and_fantasy_only_fixtures_are_isolated(fantasy):
    other = await additional_week(fantasy, WEEK, another_league=True)
    wrong_path = fantasy.path.replace(str(fantasy.parent.id), str(other[1].id)) + "/slots/1"
    foreign = await fantasy.request("PUT", path=wrong_path, body=fantasy.body())
    assert foreign.status_code == 404, foreign.text
    body = {**fantasy.body(), "fixture_id": str(other[3][0].id)}
    foreign_fixture = await fantasy.save(body=body)
    assert foreign_fixture.status_code == 422, foreign_fixture.text
    group_body = fantasy.body(6)
    group_body.pop("odds")
    group = await fantasy.request(
        "PUT", path=fantasy.path.replace("fantasy", "group") + "/pick", body=group_body
    )
    assert group.status_code == 422, group.text
    assert (
        await fantasy.count(FantasyPick)
        == await fantasy.count(GroupPick)
        == await fantasy.count(WeeklyFeeObligation)
        == await fantasy.count(ProviderAttempt)
        == 0
    )


@pytest.mark.asyncio
async def test_slot_and_member_are_part_of_operation_scope(fantasy):
    operation = str(uuid.uuid4())
    a = await fantasy.save(1, fantasy.body(0, operation_id=operation))
    b = await fantasy.save(2, fantasy.body(1, operation_id=operation))
    c = await fantasy.save(1, fantasy.body(0, operation_id=operation), player=1)
    assert a.status_code == b.status_code == c.status_code == 200, (a.text, b.text, c.text)
    assert a.json()["slot"] == c.json()["slot"] == 1 and b.json()["slot"] == 2
    assert a.json()["pick"]["player_id"] != c.json()["pick"]["player_id"]
    assert await fantasy.count(GameOperation) == await fantasy.count(FantasyPick) == 3
    assert len(fantasy.source.calls) == 2


@pytest.mark.parametrize("match", [True, False])
@pytest.mark.asyncio
async def test_actual_production_quote_factory_validates_native_provenance(
    fantasy, monkeypatch, match
):
    from src.services.odds_session import odds_session

    acquired = []

    async def acquire():
        acquired.append(True)
        return fantasy.source.client if match else FakeBetfair()

    monkeypatch.setattr(odds_session, "acquire", acquire)
    monkeypatch.setattr(
        routes,
        "fantasy_entries",
        lambda: FantasyEntries(fantasy.sessions, clock=fantasy.source.clock),
    )
    response = await fantasy.save()
    assert response.status_code == (200 if match else 503), response.text
    assert len(acquired) == 1
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == int(match)
    if match:
        assert (response.json()["pick"]["provider"], response.json()["pick"]["bookmaker"]) == (
            "oddsapi",
            "Bet365",
        )
    else:
        assert await fantasy.count(FantasyPick) == 0
        async with fantasy.sessions() as db:
            row = await db.get(
                ProviderSnapshot, fantasy.quotes.key(fantasy.fixtures[0].provider_event_id)
            )
            assert row.payload["state"] == "pending"
            assert row.lease_token is row.negative_recheck_at is None


@pytest.mark.parametrize("kind", ["json", "schema"])
@pytest.mark.asyncio
async def test_invalid_actual_http_payload_is_sanitised_without_fixture_negative(fantasy, kind):
    async def dispatch(request):
        fantasy.source.calls.append([request.url.params.get("eventId")])
        return (
            httpx.Response(200, content=b"not-json")
            if kind == "json"
            else httpx.Response(
                200, json={"id": fantasy.fixtures[0].provider_event_id, "bookmakers": []}
            )
        )

    old = fantasy.source.client
    fantasy.source.client = OddsApiProvider(
        "synthetic-key",
        budget=fantasy.source.budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(dispatch)
        ),
    )
    await old.close()
    response = await fantasy.save()
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "ODDS_UNAVAILABLE"
    assert "not-json" not in response.text
    assert await fantasy.count(FantasyPick) == 0
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    async with fantasy.sessions() as db:
        row = await db.get(
            ProviderSnapshot, fantasy.quotes.key(fantasy.fixtures[0].provider_event_id)
        )
        assert row.lease_token is row.negative_recheck_at is None


@pytest.mark.asyncio
async def test_stale_revision_and_slot_type_refuse_without_new_fee_or_transport(fantasy):
    accepted = await fantasy.save()
    assert accepted.status_code == 200, accepted.text
    stale = await fantasy.save(1, fantasy.body(1))
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "ENTRY_CHANGED"
    malformed = await fantasy.request(
        "PUT", path=fantasy.path + "/slots/not-an-integer", body=fantasy.body(1, 1)
    )
    assert malformed.status_code == 422, malformed.text
    assert malformed.json()["detail"]["code"] == "INVALID_REQUEST"
    assert (await fantasy.request("GET")).json() == accepted.json()
    assert len(fantasy.source.calls) == 1


@pytest.mark.asyncio
async def test_next_entry_opens_exactly_when_current_locks(fantasy):
    later = await additional_week(fantasy, WEEK + timedelta(days=7))
    fantasy.source.clock.now = london_utc(WEEK, 12) - timedelta(microseconds=1)
    early = await target_save(fantasy, later)
    assert early.status_code == 409, early.text
    assert early.json()["detail"]["code"] == "NOT_OPEN"
    assert await fantasy.count(WeeklyFeeObligation) == await fantasy.count(ProviderAttempt) == 0
    fantasy.source.clock.now = london_utc(WEEK, 12)
    accepted = await target_save(fantasy, later)
    assert accepted.status_code == 200, accepted.text
    current = await fantasy.save()
    assert current.status_code == 409, current.text
    assert current.json()["detail"]["code"] == "LOCKED"
    assert await fantasy.count(WeeklyFeeObligation) == 2
    assert len(fantasy.source.calls) == 1


@pytest.mark.asyncio
async def test_membership_release_tombstone_is_slot_local_and_old_retry_never_recreates(fantasy):
    body = fantasy.body()
    original = await fantasy.save(1, body)
    assert original.status_code == 200, original.text
    moment = fantasy.source.clock.now
    async with fantasy.sessions() as db, db.begin():
        await close_memberships(db, [fantasy.league.id], moment, player_id=fantasy.players[0].id)
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == fantasy.league.id,
                LeagueMembership.player_id == fantasy.players[0].id,
            )
            .values(deleted_at=moment)
        )
        await release_new_entries(db, fantasy.players[0].id, [fantasy.league.id], moment)
    released = await fantasy.request("GET")
    assert released.status_code == 200, released.text
    assert released.json()["pick"] is None and released.json()["revision"] == 2
    assert (await fantasy.request("GET", slot=2)).json()["revision"] == 0
    replay = await fantasy.save(1, body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == original.json()
    assert await fantasy.count(FantasyPick) == 0
    fantasy.source.clock.now += timedelta(seconds=1)
    async with fantasy.sessions() as db, db.begin():
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == fantasy.league.id,
                LeagueMembership.player_id == fantasy.players[0].id,
            )
            .values(deleted_at=None, joined_at=fantasy.source.clock.now)
        )
    stale = await fantasy.save(1, fantasy.body(1))
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "ENTRY_CHANGED"
    fresh = await fantasy.save(1, fantasy.body(1, 2))
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["revision"] == 3
    assert await fantasy.count(WeeklyFeeObligation) == 1
    assert len(fantasy.source.calls) == 2


@pytest.mark.parametrize("change", ["leave", "suspend", "move", "void"])
@pytest.mark.asyncio
async def test_final_fresh_checks_refuse_roster_schedule_or_fixture_change_during_http(
    fantasy, change
):
    from src.services.two_game_fixture_state import fixture_state_key

    fantasy.source.block_first = True
    task = asyncio.create_task(fantasy.save())
    try:
        await asyncio.wait_for(fantasy.source.entered.wait(), 5)
        async with fantasy.sessions() as db, db.begin():
            await financial_lock(db, fantasy.league.id)
            if change == "leave":
                await close_memberships(
                    db,
                    [fantasy.league.id],
                    fantasy.source.clock.now,
                    player_id=fantasy.players[0].id,
                )
                await db.execute(
                    update(LeagueMembership)
                    .where(
                        LeagueMembership.league_id == fantasy.league.id,
                        LeagueMembership.player_id == fantasy.players[0].id,
                    )
                    .values(deleted_at=fantasy.source.clock.now)
                )
                await release_new_entries(
                    db, fantasy.players[0].id, [fantasy.league.id], fantasy.source.clock.now
                )
            elif change == "suspend":
                await db.execute(
                    update(TwoGameRollout)
                    .where(TwoGameRollout.league_id == fantasy.league.id)
                    .values(suspended=True)
                )
            elif change == "move":
                await db.execute(
                    update(Fixture)
                    .where(Fixture.id == fantasy.fixtures[0].id)
                    .values(kickoff_utc=london_utc(WEEK + timedelta(days=2)))
                )
            else:
                await db.execute(
                    update(Fixture)
                    .where(Fixture.id == fantasy.fixtures[0].id)
                    .values(home=fantasy.fixtures[0].home)
                )
                db.add(
                    ProviderSnapshot(
                        key=fixture_state_key("oddsapi", fantasy.fixtures[0].provider_event_id),
                        fixture_id=fantasy.fixtures[0].id,
                        payload={"source": "oddsapi", "status": "cancelled"},
                        observed_at=fantasy.source.clock.now,
                        expires_at=fantasy.source.clock.now + timedelta(hours=6),
                    )
                )
        fantasy.source.release.set()
        response = await task
        expected = {
            "leave": (404, "NOT_FOUND"),
            "suspend": (409, "SUSPENDED"),
            "move": (422, "INVALID_SELECTION"),
            "void": (422, "INVALID_SELECTION"),
        }[change]
        assert (response.status_code, response.json()["detail"]["code"]) == expected, response.text
        assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 0
        assert await fantasy.count(WeeklyFeeObligation) == 1
        assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    finally:
        fantasy.source.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_lost_success_response_reconciles_exact_slot_without_another_price(fantasy):
    body = fantasy.body()

    class LostResponse(ASGITransport):
        async def handle_async_request(self, request):
            response = await super().handle_async_request(request)
            assert response.status_code == 200
            await response.aread()
            raise httpx.ReadError("synthetic lost success response", request=request)

    token = create_access_token(fantasy.players[0].id, fantasy.players[0].role)
    async with AsyncClient(transport=LostResponse(app=app), base_url="http://local.test") as client:
        with pytest.raises(httpx.ReadError, match="lost success"):
            await client.put(
                fantasy.path + "/slots/1", json=body, headers={"Authorization": f"Bearer {token}"}
            )
    read = await fantasy.request("GET")
    assert read.status_code == 200, read.text
    assert read.json()["operation_id"] == body["operation_id"] and read.json()["slot"] == 1
    assert (await fantasy.request("GET", slot=2)).json()["pick"] is None
    fantasy.source.budget.policy = BudgetPolicy(hourly=1)
    fantasy.source.clock.now = london_utc(WEEK, 12)
    replay = await fantasy.save(1, body)
    assert replay.status_code == 200, replay.text
    assert replay.json() == read.json()
    assert await fantasy.count(GameOperation) == await fantasy.count(FantasyPick) == 1
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.asyncio
async def test_smallest_exact_positive_port_quote_survives_database_roundtrip(fantasy, monkeypatch):
    from src.services.odds_provider import FixtureOdds, Market, Outcome, Selection

    async def positive(event_ids):
        return [
            FixtureOdds(
                provider_event_id=event,
                home="Synthetic Home",
                away="Synthetic Away",
                selections=[
                    Selection(
                        market=Market.MATCH_ODDS,
                        outcome=Outcome.HOME,
                        runner_name="Synthetic Home",
                        price=Decimal("0.0001"),
                    )
                ],
            )
            for event in event_ids
        ]

    monkeypatch.setattr(fantasy.source.client, "fetch_odds", positive)
    response = await fantasy.save(1, fantasy.body(0, odds="0.0001"))
    assert response.status_code == 200, response.text
    assert response.json()["pick"]["frozen_odds"] == "0.0001"
    async with fantasy.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == fantasy.game.id))
        assert pick.frozen_odds == Decimal("0.0001")
    # This is a port/storage boundary oracle, not HTTP capacity evidence.
    assert fantasy.source.calls == []
    assert await fantasy.count(ProviderAttempt) == 0


@pytest.mark.asyncio
async def test_positive_port_underflow_cannot_round_into_replacement(fantasy, monkeypatch):
    from src.services.odds_provider import FixtureOdds, Market, Outcome, Selection

    original = await fantasy.save()
    assert original.status_code == 200, original.text
    port_calls = []

    async def underflow(event_ids):
        port_calls.append(list(event_ids))
        return [
            FixtureOdds(
                provider_event_id=event,
                home="Synthetic Home",
                away="Synthetic Away",
                selections=[
                    Selection(
                        market=Market.MATCH_ODDS,
                        outcome=Outcome.HOME,
                        runner_name="Synthetic Home",
                        price=Decimal("0.00001"),
                    )
                ],
            )
            for event in event_ids
        ]

    monkeypatch.setattr(fantasy.source.client, "fetch_odds", underflow)
    body = fantasy.body(1, 1)
    for _ in range(2):
        response = await fantasy.save(1, body)
        assert response.status_code == 503, response.text
        assert response.json()["detail"]["code"] == "ODDS_UNAVAILABLE"
        assert (await fantasy.request("GET", slot=1)).json() == original.json()
    assert port_calls == [[fantasy.fixtures[1].provider_event_id]]
    async with fantasy.sessions() as db:
        snapshot = await db.get(
            ProviderSnapshot, fantasy.quotes.key(fantasy.fixtures[1].provider_event_id)
        )
        assert snapshot.payload["odds"]["selections"][0]["price"] == "0.00001"
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == fantasy.game.id))
        assert pick.fixture_id == fantasy.fixtures[0].id
        assert pick.frozen_odds == Decimal("2.1500") and pick.revision == 1
    assert await fantasy.count(FantasyPick) == await fantasy.count(GameOperation) == 1
    assert await fantasy.count(WeeklyFeeObligation) == 1
    # Only the original accepted slot used actual HTTP. This is port/storage evidence.
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1


@pytest.mark.asyncio
async def test_second_price_movement_does_not_accept_an_unspecified_confirmation(fantasy):
    original = await fantasy.save()
    assert original.status_code == 200, original.text
    fantasy.source.price = "2.3500"
    first = await fantasy.save(1, fantasy.body(1, 1))
    assert first.status_code == 409, first.text
    assert first.json()["detail"]["current_odds"] == "2.3500"
    fantasy.source.clock.now += timedelta(seconds=61)
    fantasy.source.price = "2.4000"
    second = await fantasy.save(1, fantasy.body(1, 1, odds=first.json()["detail"]["current_odds"]))
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "PRICE_MOVED"
    assert second.json()["detail"]["current_odds"] == "2.4000"
    assert (await fantasy.request("GET")).json() == original.json()
    assert await fantasy.count(GameOperation) == 1
    confirmed = await fantasy.save(
        1, fantasy.body(1, 1, odds=second.json()["detail"]["current_odds"])
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["pick"]["frozen_odds"] == "2.4000"
    assert confirmed.json()["revision"] == 2
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 3


@pytest.mark.asyncio
async def test_actual_entry_and_opening_race_share_one_remaining_dispatch_across_noon(fantasy):
    from src.services.provider_budget import ProviderBudgetRefused

    later = await additional_week(fantasy, WEEK + timedelta(days=7))
    another = await additional_week(fantasy, WEEK + timedelta(days=7), another_league=True)
    fantasy.source.budget.policy = BudgetPolicy(hourly=2)
    fantasy.source.clock.now = london_utc(WEEK, 12) - timedelta(seconds=1)
    await fantasy.source.client.fetch_odds([f"prior-legacy-{uuid.uuid4().hex}"])
    assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    first_ready, all_ready, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    reached = 0

    async def acquire():
        nonlocal reached
        reached += 1
        first_ready.set()
        if reached == 4:
            all_ready.set()
        await release.wait()
        return fantasy.source.client

    fantasy.quotes = SharedQuotes(
        fantasy.sessions,
        acquire=acquire,
        source="oddsapi",
        bookmaker="Bet365",
        clock=fantasy.source.clock,
    )
    tasks = [asyncio.create_task(fantasy.save())]
    try:
        await asyncio.wait_for(first_ready.wait(), 5)
        fantasy.source.clock.now = london_utc(WEEK, 12)
        tasks.extend(
            [
                asyncio.create_task(target_save(fantasy, later)),
                asyncio.create_task(target_save(fantasy, another)),
                asyncio.create_task(
                    fantasy.quotes.refresh_many([later[3][1].provider_event_id], category="opening")
                ),
            ]
        )
        await asyncio.wait_for(all_ready.wait(), 5)
        release.set()
        current, next_entry, other_entry, opening = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 2
        winner = fantasy.source.calls[1][0]
        assert current.status_code == 409, current.text
        assert current.json()["detail"]["code"] == "LOCKED"
        assert (await fantasy.request("GET")).json()["pick"] is None
        for target, response in [(later, next_entry), (another, other_entry)]:
            admitted = winner == target[3][0].provider_event_id
            assert response.status_code == (200 if admitted else 429), response.text
            path = f"/api/v1/leagues/{target[0].id}/weeks/{target[1].id}/games/fantasy/slots/1"
            read = await fantasy.request("GET", path=path)
            assert read.status_code == 200, read.text
            assert (read.json()["pick"] is not None) == admitted
        if winner == later[3][1].provider_event_id:
            assert isinstance(opening, dict)
            assert opening[winner].odds is not None
        else:
            assert isinstance(opening, ProviderBudgetRefused)
        assert winner in {
            fantasy.fixtures[0].provider_event_id,
            later[3][0].provider_event_id,
            another[3][0].provider_event_id,
            later[3][1].provider_event_id,
        }
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
