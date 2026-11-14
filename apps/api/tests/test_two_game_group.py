"""Unpriced group HTTP flows, independent transactions and race boundaries."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.auth import create_access_token
from src.config import settings
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League, PickMarket
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.profile import Profile, UserRole
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
from src.routers import two_game_group as routes
from src.services import two_game_group as group_service
from src.services.two_game_fixture_state import fixture_state_key
from src.services.two_game_group import GroupEntries
from src.services.two_game_storage import ensure_two_game_week, london_utc
from src.services.weekly_fees import close_memberships, financial_lock, release_new_entries

WEEK = date(2026, 11, 21)


@dataclass
class Game:
    sessions: async_sessionmaker
    league: League
    players: list[Profile]
    parent: Gameweek
    group: TwoGame
    fantasy: TwoGame
    fixtures: list[Fixture]
    now: datetime
    attempts_before: int

    @property
    def path(self):
        return f"/api/v1/leagues/{self.league.id}/weeks/{self.parent.id}/games/group"

    def body(self, fixture=0, revision=0, **values):
        return {
            "fixture_id": str(self.fixtures[fixture].id),
            "market": "MATCH_ODDS",
            "outcome": "HOME",
            "expected_revision": revision,
            "operation_id": str(uuid.uuid4()),
            **values,
        }

    async def request(self, method, suffix="/pick", *, player=0, body=None, path=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local.test") as c:
            token = create_access_token(self.players[player].id, self.players[player].role)
            return await c.request(
                method,
                path or self.path + suffix,
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )

    async def save(self, body=None, *, player=0):
        return await self.request("PUT", player=player, body=body or self.body())

    async def count(self, model):
        async with self.sessions() as db:
            if model is ProviderAttempt:
                return await db.scalar(select(func.count()).select_from(model))
            return await db.scalar(
                select(func.count()).select_from(model).where(model.league_id == self.league.id)
            )


@pytest_asyncio.fixture
async def game(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as db, db.begin():
        players = [
            Profile(display_name=f"Group {uuid.uuid4().hex}", pin_hash="x") for _ in range(4)
        ]
        players[-1].role = UserRole.admin
        db.add_all(players)
        await db.flush()
        league = League(
            slug=f"group-{uuid.uuid4().hex}",
            name="Synthetic group",
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
        assert parent is not None
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
        fantasy = TwoGame(
            league_id=league.id,
            week_id=parent.id,
            kind="fantasy",
            opens_at=london_utc(WEEK - timedelta(days=7), 12),
            locks_at=london_utc(WEEK, 12),
            window_start=london_utc(WEEK, 12, 30),
            window_end=london_utc(WEEK + timedelta(days=2)),
        )
        db.add_all([group, fantasy])
        fixtures = [
            Fixture(
                provider_event_id=f"group-{uuid.uuid4().hex}",
                home=f"Home {i}",
                away=f"Away {i}",
                competition="Synthetic",
                competition_id="synthetic",
                kickoff_utc=london_utc(WEEK, 15),
                odds_unpriced_since_utc=london_utc(WEEK - timedelta(days=1)),
            )
            for i in range(5)
        ]
        db.add_all(fixtures)
        await db.flush()
        for fixture in fixtures:
            db.add_all(
                [
                    TwoGameFixture(game_id=group.id, fixture_id=fixture.id),
                    TwoGameFixture(game_id=fantasy.id, fixture_id=fixture.id),
                ]
            )
        attempts_before = int(await db.scalar(select(func.count()).select_from(ProviderAttempt)))
    result = Game(
        sessions,
        league,
        players,
        parent,
        group,
        fantasy,
        fixtures,
        london_utc(WEEK, 13),
        attempts_before,
    )
    monkeypatch.setattr(
        routes, "group_entries", lambda: GroupEntries(sessions, clock=lambda: result.now)
    )
    from src.services.odds_session import odds_session

    async def forbidden_provider():
        raise AssertionError("A group request acquired an odds provider")

    monkeypatch.setattr(odds_session, "acquire", forbidden_provider)
    try:
        yield result
        assert await result.count(ProviderAttempt) == attempts_before
    finally:
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


def assert_unpriced(value):
    if isinstance(value, dict):
        assert not set(value) & {
            "odds",
            "frozen_odds",
            "points",
            "points_awarded",
            "combined_odds",
            "combined_price",
        }
        for child in value.values():
            assert_unpriced(child)
    elif isinstance(value, list):
        for child in value:
            assert_unpriced(child)


@pytest.mark.asyncio
async def test_unpriced_empty_incomplete_and_valid_group_http(game):
    empty = await game.request("GET", "")
    assert empty.status_code == 200, empty.text
    data = empty.json()
    assert data["result"] == {"status": "no_coupon", "final": False}
    assert data["progress"] == {"picked_count": 0, "member_count": 3, "all_picked": False}
    assert len(data["fixtures"]) == 5 and data["entry_state"] == "open"
    assert data["locks_at"].endswith("Z") and data["week_id"] == str(game.parent.id)
    assert data["week_number"] == str(game.parent.number)
    assert data["fee"]["paid_through"]
    assert await game.count(WeeklyFeeObligation) == 0
    saved = await game.save()
    assert saved.status_code == 200, saved.text
    assert saved.json()["pick"]["runner_name"] == "Home 0"
    view = (await game.request("GET", "")).json()
    assert view["progress"] == {"picked_count": 1, "member_count": 3, "all_picked": False}
    assert view["result"]["status"] == "pending"
    assert_unpriced([data, saved.json(), view])
    assert await game.count(GroupPick) == 1 and await game.count(GameOperation) == 1


@pytest.mark.asyncio
async def test_whole_fixture_race_and_failed_replacement_preserve_original(game):
    responses = await asyncio.gather(
        game.save(game.body()), game.save(game.body(outcome="AWAY"), player=1)
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["detail"]["code"] == "FIXTURE_TAKEN"
    winner_index = next(i for i, r in enumerate(responses) if r.status_code == 200)
    other = 1 - winner_index
    original = await game.save(game.body(1), player=other)
    assert original.status_code == 200
    refused = await game.save(game.body(0, 1), player=other)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FIXTURE_TAKEN"
    current = await game.request("GET", player=other)
    assert current.json() == original.json()
    assert await game.count(GroupPick) == 2 and await game.count(GameOperation) == 2


@pytest.mark.asyncio
async def test_same_member_concurrent_revisions_one_wins(game):
    responses = await asyncio.gather(game.save(game.body(0)), game.save(game.body(1)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    failure = next(r.json()["detail"] for r in responses if r.status_code == 409)
    assert failure["code"] == "ENTRY_CHANGED" and failure["current"]["revision"] == 1
    assert await game.count(GroupPick) == 1 and await game.count(GameOperation) == 1


@pytest.mark.asyncio
async def test_identical_operation_race_waits_then_replays_once(game, monkeypatch):
    from src.services import two_game_entry

    real_lock = two_game_entry.financial_lock
    arrived = asyncio.Event()
    calls = 0

    async def watched_lock(db, league_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            arrived.set()
        return await real_lock(db, league_id)

    body = game.body()
    async with game.sessions() as holding, holding.begin():
        await financial_lock(holding, game.league.id)
        monkeypatch.setattr(two_game_entry, "financial_lock", watched_lock)
        tasks = [asyncio.create_task(game.save(body)) for _ in range(2)]
        await asyncio.wait_for(arrived.wait(), 5)
    first, second = await asyncio.gather(*tasks)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await game.count(GroupPick) == await game.count(GameOperation) == 1


@pytest.mark.asyncio
async def test_operation_conflict_atomic_replacement_and_old_replay(game):
    body = game.body()
    first = await game.save(body)
    assert first.status_code == 200
    conflict = await game.save({**body, "outcome": "AWAY"})
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "OPERATION_CONFLICT"
    second = await game.save(game.body(1, 1, market="BOTH_TEAMS_TO_SCORE", outcome="YES"))
    assert second.status_code == 200 and second.json()["revision"] == 2
    assert first.json()["pick"]["id"] == second.json()["pick"]["id"]
    game.now = game.group.locks_at
    async with game.sessions() as db, db.begin():
        await db.execute(
            update(TwoGameRollout)
            .where(TwoGameRollout.league_id == game.league.id)
            .values(suspended=True)
        )
    replayed = await game.save(body)
    assert replayed.status_code == 200 and replayed.json() == first.json()
    assert (await game.request("GET")).json() == second.json()
    assert await game.count(GameOperation) == 2


@pytest.mark.asyncio
async def test_departure_tombstone_replay_and_rejoin_revision(game):
    body = game.body()
    first = await game.save(body)
    assert first.status_code == 200
    async with game.sessions() as db, db.begin():
        await financial_lock(db, game.league.id)
        await close_memberships(db, [game.league.id], game.now, player_id=game.players[0].id)
        await release_new_entries(db, game.players[0].id, [game.league.id], game.now)
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == game.league.id,
                LeagueMembership.player_id == game.players[0].id,
            )
            .values(deleted_at=game.now)
        )
    current = await game.request("GET")
    assert (
        current.status_code == 200
        and current.json()["pick"] is None
        and current.json()["revision"] == 2
    )
    assert (await game.save(body)).json() == first.json()
    assert await game.count(GroupPick) == 0
    async with game.sessions() as db, db.begin():
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == game.league.id,
                LeagueMembership.player_id == game.players[0].id,
            )
            .values(deleted_at=None, joined_at=game.now)
        )
    stale = await game.save(game.body(1, 0))
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "ENTRY_CHANGED"
    refilled = await game.save(game.body(1, 2))
    assert refilled.status_code == 200 and refilled.json()["revision"] == 3


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("suspended", "SUSPENDED"),
        ("cancelled", "CANCELLED"),
        ("not_open", "NOT_OPEN"),
        ("locked", "LOCKED"),
    ],
)
@pytest.mark.asyncio
async def test_mutable_admission_refuses_without_dues(game, mutation, code):
    if mutation == "suspended":
        async with game.sessions() as db, db.begin():
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id == game.league.id)
                .values(suspended=True)
            )
    elif mutation == "cancelled":
        async with game.sessions() as db, db.begin():
            await db.execute(
                update(TwoGame).where(TwoGame.id == game.group.id).values(status="cancelled")
            )
    elif mutation == "not_open":
        game.now = game.group.opens_at - timedelta(microseconds=1)
    else:
        game.now = game.group.locks_at
    response = await game.save()
    assert response.status_code == 409 and response.json()["detail"]["code"] == code
    assert await game.count(GroupPick) == await game.count(WeeklyFeeObligation) == 0


@pytest.mark.parametrize("offset,status", [(-1, 200), (0, 409), (1, 409)])
@pytest.mark.asyncio
async def test_exact_1430_boundary_without_scheduler(game, offset, status):
    game.now = game.group.locks_at + timedelta(microseconds=offset)
    response = await game.save()
    assert response.status_code == status, response.text
    if status == 409:
        assert response.json()["detail"]["code"] == "LOCKED"


@pytest.mark.parametrize(
    "market,outcome", [("bad", "HOME"), ("MATCH_ODDS", "YES"), ("BOTH_TEAMS_TO_SCORE", "AWAY")]
)
@pytest.mark.asyncio
async def test_invalid_market_pair_preserves_old_and_fees(game, market, outcome):
    first = await game.save()
    assert first.status_code == 200
    response = await game.save(game.body(1, 1, market=market, outcome=outcome))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "INVALID_SELECTION"
    assert (await game.request("GET")).json() == first.json()
    assert await game.count(GameOperation) == 1


@pytest.mark.asyncio
async def test_unoffered_market_and_foreign_fixture_cannot_materialise_dues(game):
    async with game.sessions() as db, db.begin():
        await db.execute(
            update(League)
            .where(League.id == game.league.id)
            .values(offered_markets=[PickMarket.MATCH_ODDS])
        )
    response = await game.save(game.body(market="BOTH_TEAMS_TO_SCORE", outcome="YES"))
    assert response.status_code == 422
    response = await game.save(game.body(fixture_id=str(uuid.uuid4())))
    assert response.status_code == 422
    assert await game.count(WeeklyFeeObligation) == 0


@pytest.mark.asyncio
async def test_unpaid_early_fee_commits_once_and_payment_then_succeeds(game):
    async with game.sessions() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=game.league.id,
                player_id=game.players[0].id,
                kind=LedgerKind.cash_out,
                amount_pence=-1000,
            )
        )
    for body in [game.body(), game.body(1)]:
        response = await game.save(body)
        assert response.status_code == 402, response.text
        fee = response.json()["detail"]["fee"]
        assert fee["amount_owed_pence"] == 100 and fee["week_id"] == str(game.parent.id)
        assert not fee["paid_through"]
    assert await game.count(WeeklyFeeObligation) == 1
    assert await game.count(GroupPick) == 0
    async with game.sessions() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=game.league.id,
                player_id=game.players[0].id,
                kind=LedgerKind.payment,
                amount_pence=100,
            )
        )
    assert (await game.save()).status_code == 200
    assert await game.count(WeeklyFeeObligation) == 1


@pytest.mark.parametrize("mode", ["nonmember", "off", "wrong_week", "wrong_league", "deleted"])
@pytest.mark.asyncio
async def test_exact_target_and_access_refusals(game, monkeypatch, mode):
    player, path = 0, game.path + "/pick"
    if mode == "nonmember":
        player = 3
    elif mode == "off":
        monkeypatch.setattr(settings, "two_games_enabled", False)
    elif mode == "wrong_week":
        path = path.replace(str(game.parent.id), str(uuid.uuid4()))
    elif mode == "wrong_league":
        path = path.replace(str(game.league.id), str(uuid.uuid4()))
    else:
        async with game.sessions() as db, db.begin():
            await db.execute(
                update(League).where(League.id == game.league.id).values(deleted_at=game.now)
            )
    for method in ["GET", "PUT"]:
        response = await game.request(
            method, path=path, player=player, body=game.body() if method == "PUT" else None
        )
        assert response.status_code == 404, response.text
    assert await game.count(WeeklyFeeObligation) == 0


@pytest.mark.asyncio
async def test_replay_does_not_bypass_deleted_league(game):
    body = game.body()
    assert (await game.save(body)).status_code == 200
    async with game.sessions() as db, db.begin():
        await db.execute(
            update(League).where(League.id == game.league.id).values(deleted_at=game.now)
        )
    assert (await game.save(body)).status_code == 404


@pytest.mark.asyncio
async def test_legacy_target_redirect_and_legacy_history_remain_unchanged(game):
    async with game.sessions() as db, db.begin():
        legacy = Gameweek(
            league_id=game.league.id,
            starts_on=WEEK - timedelta(days=7),
            status=GameweekStatus.open,
            locks_at_utc=london_utc(WEEK - timedelta(days=7), 14, 30),
        )
        db.add(legacy)
        await db.flush()
        before = (legacy.id, legacy.starts_on, legacy.status, legacy.format, legacy.locks_at_utc)
    path = game.path.replace(str(game.parent.id), str(legacy.id))
    for suffix, method in [("", "GET"), ("/pick", "GET"), ("/pick", "PUT")]:
        response = await game.request(
            method, path=path + suffix, body=game.body() if method == "PUT" else None
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "UNSUPPORTED_FORMAT"
        assert (
            detail["destination"]
            == f"/leagues/{game.league.slug}/predictions?gw={legacy.id}#coupon"
        )
    async with game.sessions() as db:
        after = await db.get(Gameweek, legacy.id)
        assert (after.id, after.starts_on, after.status, after.format, after.locks_at_utc) == before
    assert await game.count(WeeklyFeeObligation) == 0


@pytest.mark.asyncio
async def test_fantasy_claim_does_not_reserve_group_fixture(game):
    async with game.sessions() as db, db.begin():
        db.add(
            FantasyPick(
                league_id=game.league.id,
                week_id=game.parent.id,
                game_id=game.fantasy.id,
                player_id=game.players[1].id,
                fixture_id=game.fixtures[0].id,
                market="MATCH_ODDS",
                outcome="HOME",
                runner_name="Home 0",
                slot=1,
                frozen_odds=Decimal("2.125"),
                quoted_at=game.now,
                provider="fake",
                bookmaker="fake",
                operation_id=uuid.uuid4(),
            )
        )
    assert (await game.save()).status_code == 200
    assert await game.count(GroupPick) == await game.count(FantasyPick) == 1


@pytest.mark.parametrize(
    "change,code,status",
    [
        ("move", "INVALID_SELECTION", 422),
        ("void", "INVALID_SELECTION", 422),
        ("clock", "LOCKED", 409),
    ],
)
@pytest.mark.asyncio
async def test_final_fixture_lock_wait_rechecks_current_census_and_clock(
    game, monkeypatch, change, code, status
):
    reached = asyncio.Event()
    real_selection = group_service.selection

    async def watched_selection(db, target, body, **kwargs):
        if kwargs.get("lock_fixture"):
            reached.set()
        return await real_selection(db, target, body, **kwargs)

    monkeypatch.setattr(group_service, "selection", watched_selection)
    async with game.sessions() as census, census.begin():
        fixture = await census.scalar(
            select(Fixture).where(Fixture.id == game.fixtures[0].id).with_for_update()
        )
        task = asyncio.create_task(game.save())
        await asyncio.wait_for(reached.wait(), 5)
        if change == "move":
            fixture.kickoff_utc += timedelta(hours=1)
        elif change == "void":
            census.add(
                ProviderSnapshot(
                    key=fixture_state_key(settings.odds_provider.value, fixture.provider_event_id),
                    fixture_id=fixture.id,
                    payload={"status": "cancelled", "source": settings.odds_provider.value},
                    observed_at=game.now,
                    expires_at=game.now + timedelta(hours=1),
                )
            )
        else:
            game.now = game.group.locks_at
    response = await task
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert await game.count(GroupPick) == await game.count(GameOperation) == 0


@pytest.mark.asyncio
async def test_early_fee_clock_is_evaluated_after_its_advisory_wait(game, monkeypatch):
    reached = asyncio.Event()
    release = asyncio.Event()
    original = group_service.materialize_entry_fees

    async def waiting_preflight(*args, **kwargs):
        async with game.sessions() as holding, holding.begin():
            await financial_lock(holding, game.league.id)
            task = asyncio.create_task(original(*args, **kwargs))
            reached.set()
            await release.wait()
        return await task

    monkeypatch.setattr(group_service, "materialize_entry_fees", waiting_preflight)
    task = asyncio.create_task(game.save())
    await asyncio.wait_for(reached.wait(), 5)
    game.now = game.group.locks_at
    release.set()
    response = await task
    assert response.status_code == 409 and response.json()["detail"]["code"] == "LOCKED"
    assert await game.count(WeeklyFeeObligation) == await game.count(GroupPick) == 0


@pytest.mark.asyncio
async def test_missing_group_child_and_fantasy_only_fixture_are_not_group_targets(game):
    from sqlalchemy import delete

    async with game.sessions() as db, db.begin():
        await db.execute(
            delete(TwoGameFixture).where(
                TwoGameFixture.game_id == game.group.id,
                TwoGameFixture.fixture_id == game.fixtures[0].id,
            )
        )
        next_parent = await ensure_two_game_week(db, game.league.id, WEEK + timedelta(days=7))
        assert next_parent is not None
        db.add(
            TwoGame(
                league_id=game.league.id,
                week_id=next_parent.id,
                kind="fantasy",
                opens_at=london_utc(WEEK, 12),
                locks_at=london_utc(WEEK + timedelta(days=7), 12),
                window_start=london_utc(WEEK + timedelta(days=7), 12, 30),
                window_end=london_utc(WEEK + timedelta(days=9)),
            )
        )
    response = await game.save()
    assert response.status_code == 422 and response.json()["detail"]["code"] == "INVALID_SELECTION"
    path = game.path.replace(str(game.parent.id), str(next_parent.id))
    assert (await game.request("GET", path=path)).status_code == 404
    assert (await game.request("PUT", path=path + "/pick", body=game.body())).status_code == 404
    assert await game.count(WeeklyFeeObligation) == 0


@pytest.mark.asyncio
async def test_actual_other_league_week_and_shared_fixture_have_separate_claims(game):
    async with game.sessions() as db, db.begin():
        other = League(
            slug=f"other-{uuid.uuid4().hex}", name="Other synthetic", created_by=game.players[0].id
        )
        db.add(other)
        await db.flush()
        db.add(
            TwoGameRollout(
                league_id=other.id,
                first_week=WEEK,
                enabled=True,
                effective_opening=game.group.opens_at,
            )
        )
        db.add(
            LeagueMembership(
                league_id=other.id, player_id=game.players[0].id, joined_at=game.group.opens_at
            )
        )
        db.add(
            LedgerEntry(
                league_id=other.id,
                player_id=game.players[0].id,
                kind=LedgerKind.payment,
                amount_pence=100,
            )
        )
        await db.flush()
        parent = await ensure_two_game_week(db, other.id, WEEK)
        assert parent is not None
        child = TwoGame(
            league_id=other.id,
            week_id=parent.id,
            kind="group",
            opens_at=game.group.opens_at,
            locks_at=game.group.locks_at,
            window_start=game.group.window_start,
            window_end=game.group.window_end,
        )
        db.add(child)
        await db.flush()
        db.add(TwoGameFixture(game_id=child.id, fixture_id=game.fixtures[0].id))
    try:
        body = game.body()
        first = await game.save(body)
        assert first.status_code == 200
        crossed = game.path.replace(str(game.parent.id), str(parent.id)) + "/pick"
        assert (await game.request("PUT", path=crossed, body=body)).status_code == 404
        other_path = (
            game.path.replace(str(game.league.id), str(other.id)).replace(
                str(game.parent.id), str(parent.id)
            )
            + "/pick"
        )
        second = await game.request("PUT", path=other_path, body=body)
        assert second.status_code == 200, second.text
        assert second.json()["league_id"] == str(other.id) and second.json()["week_id"] == str(
            parent.id
        )
        assert second.json()["pick"]["id"] != first.json()["pick"]["id"]
        assert (await game.request("PUT", path=other_path, body=body, player=1)).status_code == 404
    finally:
        async with game.sessions() as db, db.begin():
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id == other.id)
                .values(enabled=False)
            )
            await db.execute(
                update(League).where(League.id == other.id).values(deleted_at=game.now)
            )


@pytest.mark.asyncio
async def test_group_format_admission_allows_twelve_legitimate_edits(game):
    original_id = None
    for revision in range(12):
        response = await game.save(game.body(revision % 5, revision))
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == revision + 1
        original_id = original_id or response.json()["pick"]["id"]
        assert response.json()["pick"]["id"] == original_id
    assert await game.count(GroupPick) == 1 and await game.count(GameOperation) == 12


@pytest.mark.asyncio
async def test_action_abuse_refusal_preserves_pick_and_accepted_replay_is_free(game, monkeypatch):
    monkeypatch.setattr(settings, "two_game_member_actions_hourly", 2)
    body = game.body()
    first = await game.save(body)
    second = await game.save(game.body(1, 1))
    assert first.status_code == second.status_code == 200
    refused = await game.save(game.body(2, 2))
    assert refused.status_code == 429 and refused.json()["detail"]["code"] == "TOO_MANY_TRIES"
    assert (await game.request("GET")).json() == second.json()
    assert (await game.save(body)).json() == first.json()
    assert await game.count(GameOperation) == 2


@pytest.mark.asyncio
async def test_long_opening_group_attempt_materialises_intervening_future_fees_once(game):
    label = WEEK + timedelta(days=14)
    async with game.sessions() as db, db.begin():
        parent = await ensure_two_game_week(db, game.league.id, label)
        assert parent is not None
        child = TwoGame(
            league_id=game.league.id,
            week_id=parent.id,
            kind="group",
            opens_at=game.group.opens_at,
            locks_at=london_utc(label, 14, 30),
            window_start=london_utc(label, 15),
            window_end=london_utc(label, 15),
        )
        fixture = Fixture(
            provider_event_id=f"future-{uuid.uuid4().hex}",
            home="Future home",
            away="Future away",
            competition="Synthetic",
            competition_id="synthetic",
            kickoff_utc=london_utc(label, 15),
        )
        db.add_all([child, fixture])
        db.add(
            LedgerEntry(
                league_id=game.league.id,
                player_id=game.players[0].id,
                kind=LedgerKind.cash_out,
                amount_pence=-1000,
            )
        )
        await db.flush()
        db.add(TwoGameFixture(game_id=child.id, fixture_id=fixture.id))
    path = game.path.replace(str(game.parent.id), str(parent.id)) + "/pick"
    for _ in range(2):
        response = await game.request("PUT", path=path, body=game.body(fixture_id=str(fixture.id)))
        assert response.status_code == 402, response.text
        detail = response.json()["detail"]
        assert detail["amount_owed_pence"] == 300
        assert detail["destination"] == f"/leagues/{game.league.id}/weeks/{parent.id}/group#payment"
        assert detail["payment_url"] == "https://synthetic.invalid/pay"
    assert await game.count(WeeklyFeeObligation) == 3
    assert await game.count(GroupPick) == 0


@pytest.mark.asyncio
async def test_business_rollback_retains_early_fee_and_no_accepted_operation(game, monkeypatch):
    def failed_response(pick):
        raise RuntimeError("synthetic failure after pick flush")

    monkeypatch.setattr(group_service, "contribution", failed_response)
    with pytest.raises(RuntimeError, match="synthetic failure after pick flush"):
        await game.save()
    assert await game.count(WeeklyFeeObligation) == 1
    assert await game.count(GroupPick) == await game.count(GameOperation) == 0


@pytest.mark.asyncio
async def test_opening_instant_is_inclusive_and_accepted_replay_survives_gate_shutdown(
    game, monkeypatch
):
    game.now = game.group.opens_at
    body = game.body()
    first = await game.save(body)
    assert first.status_code == 200, first.text
    monkeypatch.setattr(settings, "two_games_enabled", False)
    replayed = await game.save(body)
    assert replayed.status_code == 200 and replayed.json() == first.json()
    assert (await game.save(game.body(1, 1))).status_code == 404
    assert await game.count(GameOperation) == await game.count(WeeklyFeeObligation) == 1


@pytest.mark.asyncio
async def test_initial_phase_waiting_on_identical_final_save_replays_after_lock(game, monkeypatch):
    from src.services import two_game_entry

    final_locked = asyncio.Event()
    release_first = asyncio.Event()
    second_waiting = asyncio.Event()
    original_selection = group_service.selection
    original_lock = two_game_entry.financial_lock

    async def paused_selection(db, target, body, **kwargs):
        result = await original_selection(db, target, body, **kwargs)
        if kwargs.get("lock_fixture"):
            final_locked.set()
            await release_first.wait()
        return result

    monkeypatch.setattr(group_service, "selection", paused_selection)
    body = game.body()
    first_task = asyncio.create_task(game.save(body))
    await asyncio.wait_for(final_locked.wait(), 5)

    async def second_lock(db, league_id):
        second_waiting.set()
        result = await original_lock(db, league_id)
        # First request has committed. The second must replay despite the lock.
        game.now = game.group.locks_at
        return result

    monkeypatch.setattr(two_game_entry, "financial_lock", second_lock)
    second_task = asyncio.create_task(game.save(body))
    await asyncio.wait_for(second_waiting.wait(), 5)
    release_first.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await game.count(GroupPick) == await game.count(GameOperation) == 1
    assert await game.count(WeeklyFeeObligation) == 1


@pytest.mark.asyncio
async def test_actual_departure_between_fee_commit_and_save_cannot_recreate_claim(
    game, monkeypatch
):
    from src.routers import leagues

    fee_committed = asyncio.Event()
    resume = asyncio.Event()
    original = group_service.materialize_entry_fees

    async def paused_fee(*args, **kwargs):
        fee = await original(*args, **kwargs)
        fee_committed.set()
        await resume.wait()
        return fee

    monkeypatch.setattr(group_service, "materialize_entry_fees", paused_fee)
    monkeypatch.setattr(leagues, "_now", lambda: game.now)
    task = asyncio.create_task(game.save())
    await asyncio.wait_for(fee_committed.wait(), 5)
    left = await game.request("DELETE", path=f"/api/v1/leagues/{game.league.slug}/membership")
    assert left.status_code == 204, left.text
    resume.set()
    response = await task
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NOT_FOUND"
    assert await game.count(WeeklyFeeObligation) == 1
    assert await game.count(GroupPick) == await game.count(GameOperation) == 0


@pytest.mark.asyncio
async def test_census_void_writer_waits_for_accepted_fixture_share_lock(game, monkeypatch):
    from sqlalchemy import text

    fixture_held = asyncio.Event()
    release_pick = asyncio.Event()
    writer_started = asyncio.Event()
    original = group_service.selection
    writer_pid = None

    async def paused_selection(db, target, body, **kwargs):
        result = await original(db, target, body, **kwargs)
        if kwargs.get("lock_fixture"):
            fixture_held.set()
            await release_pick.wait()
        return result

    async def publish_void():
        nonlocal writer_pid
        async with game.sessions() as db, db.begin():
            writer_pid = await db.scalar(text("SELECT pg_backend_pid()"))
            writer_started.set()
            await db.execute(
                update(Fixture).where(Fixture.id == game.fixtures[0].id).values(home="Home 0")
            )
            db.add(
                ProviderSnapshot(
                    key=fixture_state_key(
                        settings.odds_provider.value, game.fixtures[0].provider_event_id
                    ),
                    fixture_id=game.fixtures[0].id,
                    payload={"status": "cancelled", "source": settings.odds_provider.value},
                    observed_at=game.now,
                    expires_at=game.now + timedelta(hours=1),
                )
            )

    monkeypatch.setattr(group_service, "selection", paused_selection)
    save_task = asyncio.create_task(game.save())
    await asyncio.wait_for(fixture_held.wait(), 5)
    writer_task = asyncio.create_task(publish_void())
    await asyncio.wait_for(writer_started.wait(), 5)
    async with game.sessions() as observer:
        blocked = False
        for _ in range(200):
            blocked = await observer.scalar(
                text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": writer_pid}
            )
            if blocked:
                break
            await asyncio.sleep(0.01)
        assert blocked and not writer_task.done()
    release_pick.set()
    saved = await save_task
    assert saved.status_code == 200, saved.text
    await writer_task
    view = await game.request("GET", "")
    assert view.status_code == 200
    retained = next(
        f for f in view.json()["fixtures"] if f["fixture_id"] == str(game.fixtures[0].id)
    )
    assert not retained["eligible"] and retained["claim"]["player_id"] == str(game.players[0].id)
    assert await game.count(GroupPick) == await game.count(GameOperation) == 1


@pytest.mark.parametrize(
    "case", ["malformed_json", "path_uuid", "fixture_uuid", "negative_revision", "extra_field"]
)
@pytest.mark.asyncio
async def test_new_group_validation_uses_contracted_envelope_without_business_work(game, case):
    if case == "malformed_json":
        token = create_access_token(game.players[0].id, game.players[0].role)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://local.test"
        ) as client:
            response = await client.put(
                game.path + "/pick",
                content="{",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
    elif case == "path_uuid":
        response = await game.request(
            "PUT",
            path=game.path.replace(str(game.parent.id), "bad-uuid") + "/pick",
            body=game.body(),
        )
    else:
        values = {
            "fixture_uuid": {"fixture_id": "bad-uuid"},
            "negative_revision": {"expected_revision": -1},
            "extra_field": {"frozen_odds": "2.5"},
        }[case]
        response = await game.save(game.body(**values))
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": {"code": "INVALID_REQUEST", "message": "Check this game's request"}
    }
    assert (
        await game.count(WeeklyFeeObligation)
        == await game.count(GroupPick)
        == await game.count(GameOperation)
        == 0
    )


@pytest.mark.parametrize("invalid_part", ["league", "week"])
@pytest.mark.asyncio
async def test_new_fee_path_validation_shares_envelope_without_business_work(game, invalid_part):
    path = f"/api/v1/leagues/{game.league.id}/weeks/{game.parent.id}/fee"
    path = path.replace(
        str(game.league.id if invalid_part == "league" else game.parent.id), "bad-uuid"
    )
    response = await game.request("GET", path=path)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert isinstance(response.json()["detail"]["message"], str)
    assert await game.count(WeeklyFeeObligation) == await game.count(GroupPick) == 0


@pytest.mark.asyncio
async def test_scoped_new_validation_keeps_existing_legacy_validation_response(game):
    response = await game.request(
        "POST", path="/api/v1/auth/login", body={"display_name": [], "pin": None}
    )
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)
    assert await game.count(WeeklyFeeObligation) == 0


@pytest.mark.asyncio
async def test_new_read_rate_refusal_uses_envelope_and_preserves_business_state(game):
    for _ in range(120):
        response = await game.request("GET")
        assert response.status_code == 200, response.text
    refused = await game.request("GET")
    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"]["code"] == "TOO_MANY_TRIES"
    assert refused.json()["detail"]["retry_after_seconds"] == 60
    assert refused.headers["Retry-After"] == "60"
    assert (
        await game.count(GroupPick)
        == await game.count(GameOperation)
        == await game.count(WeeklyFeeObligation)
        == 0
    )


@pytest.mark.asyncio
async def test_fee_read_waiting_behind_deletion_refreshes_access_instead_of_500(game, monkeypatch):
    from src.routers import weekly_fees

    waiting = asyncio.Event()
    original = weekly_fees.financial_lock

    async def watched_lock(db, league_id):
        waiting.set()
        return await original(db, league_id)

    monkeypatch.setattr(weekly_fees, "financial_lock", watched_lock)
    async with game.sessions() as deletion, deletion.begin():
        await financial_lock(deletion, game.league.id)
        task = asyncio.create_task(
            game.request("GET", path=f"/api/v1/leagues/{game.league.id}/weeks/{game.parent.id}/fee")
        )
        await asyncio.wait_for(waiting.wait(), 5)
        await deletion.execute(
            update(League).where(League.id == game.league.id).values(deleted_at=game.now)
        )
    response = await task
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "NOT_FOUND"
    assert await game.count(WeeklyFeeObligation) == await game.count(GroupPick) == 0


@pytest.mark.asyncio
async def test_non_utf8_json_parser_refusal_uses_new_envelope_without_business_work(game):
    token = create_access_token(game.players[0].id, game.players[0].role)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://local.test"
    ) as client:
        response = await client.put(
            game.path + "/pick",
            content=b"\xff",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert (
        await game.count(WeeklyFeeObligation)
        == await game.count(GroupPick)
        == await game.count(GameOperation)
        == 0
    )


@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("expire_on_commit", [False, True])
@pytest.mark.asyncio
async def test_group_auth_releases_shared_pool_before_independent_service_transactions(
    game, db_engine, monkeypatch, method, expire_on_commit
):
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.database import get_db
    from src.routers import two_game_protocol

    engine = create_async_engine(db_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.5)
    sessions = async_sessionmaker(engine, expire_on_commit=expire_on_commit)

    async def auth_db():
        async with sessions() as db:
            yield db

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = auth_db
    monkeypatch.setattr(two_game_protocol, "AsyncSessionLocal", sessions, raising=False)
    monkeypatch.setattr(
        routes, "group_entries", lambda: GroupEntries(sessions, clock=lambda: game.now)
    )
    try:
        response = await game.request(method, body=game.body() if method == "PUT" else None)
        assert response.status_code == 200, response.text
        assert await game.count(GroupPick) == (1 if method == "PUT" else 0)
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_group_auth_releases_all_connections_before_service_barrier(
    game, db_engine, monkeypatch
):
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.routers import two_game_protocol

    engine = create_async_engine(db_engine.url, pool_size=2, max_overflow=0, pool_timeout=0.5)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    service = GroupEntries(sessions, clock=lambda: game.now)
    original = service.get_pick
    ready = asyncio.Event()
    release = asyncio.Event()
    reached = 0

    async def paused(*args):
        nonlocal reached
        reached += 1
        if reached == 2:
            ready.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(two_game_protocol, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(service, "get_pick", paused)
    monkeypatch.setattr(routes, "group_entries", lambda: service)
    tasks = [asyncio.create_task(game.request("GET", player=i)) for i in range(2)]
    try:
        await asyncio.wait_for(ready.wait(), 5)
        assert engine.pool.checkedout() == 0
        release.set()
        responses = await asyncio.gather(*tasks)
        assert [response.status_code for response in responses] == [200, 200]
        assert await game.count(GroupPick) == await game.count(WeeklyFeeObligation) == 0
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


@pytest.mark.parametrize("state", ["inactive", "deleted"])
@pytest.mark.asyncio
async def test_short_auth_dependency_still_refuses_inactive_and_deleted_profiles(game, state):
    async with game.sessions() as db, db.begin():
        await db.execute(
            update(Profile)
            .where(Profile.id == game.players[0].id)
            .values(**({"is_active": False} if state == "inactive" else {"deleted_at": game.now}))
        )
    response = await game.request("PUT", body=game.body())
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "User not found"
    assert (
        await game.count(GroupPick)
        == await game.count(GameOperation)
        == await game.count(WeeklyFeeObligation)
        == 0
    )
