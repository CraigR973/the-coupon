"""Counted result HTTP and committed recovery across independent scratch DB sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from src.config import settings
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    ProviderAttempt,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameEvent,
    WeeklyFeeObligation,
)
from src.services.odds_api import OddsApiProvider
from src.services.scoring import standings
from src.services.two_game_events import lifecycle_events
from src.services.two_game_results import group_outcome
from src.services.two_game_settlement import (
    SettlementWorker,
    advance_generation,
    result_key,
    result_lock,
)
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import financial_locks
from tests import test_two_game_fantasy as entry_tests
from tests import two_game_test_store as result_store_fixtures

baseline_db_engine = result_store_fixtures.baseline_db_engine
result_store = result_store_fixtures.result_store
db_engine = result_store_fixtures.db_engine

fantasy = entry_tests.fantasy
WEEK = entry_tests.WEEK


@dataclass
class ResultHTTP:
    fantasy: entry_tests.Fantasy
    calls: list[str] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)
    failures: set[str] = field(default_factory=set)
    extra_leagues: list = field(default_factory=list)
    pause: str | None = None
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def dispatch(self, request):
        assert request.url.path.startswith("/events/")
        event = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(event)
        if event == self.pause:
            self.entered.set()
            await self.release.wait()
        if event in self.failures:
            return httpx.Response(400, json={"error": "synthetic result refusal"})
        return httpx.Response(
            200,
            json=dict(
                id=event, status=self.statuses.get(event, "finished"), scores=dict(home=2, away=0)
            ),
        )

    def worker(self, **kwargs):
        return SettlementWorker(
            self.fantasy.sessions,
            self.acquire,
            source="oddsapi",
            clock=self.fantasy.source.clock,
            **kwargs,
        )

    async def acquire(self):
        return self.provider

    async def spent(self):
        async with self.fantasy.sessions() as db:
            return await db.scalar(
                select(func.count())
                .select_from(ProviderAttempt)
                .where(
                    ProviderAttempt.meter == self.fantasy.source.budget.meter,
                    ProviderAttempt.category == "settlement",
                )
            )

    async def ordered(self, indices):
        worker = self.worker()
        await worker.prepare()
        async with self.fantasy.sessions() as db, db.begin():
            for index, fixture in enumerate(indices):
                await db.execute(
                    update(ProviderWork)
                    .where(
                        ProviderWork.fixture_id == self.fantasy.fixtures[fixture].id,
                        ProviderWork.kind == "settlement",
                    )
                    .values(
                        next_at=self.fantasy.source.clock.now
                        - timedelta(minutes=1)
                        + timedelta(seconds=index)
                    )
                )


@pytest_asyncio.fixture
async def results(fantasy):
    result = ResultHTTP(fantasy)
    result.provider = OddsApiProvider(
        "synthetic-result-key",
        budget=fantasy.source.budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(result.dispatch)
        ),
    )
    try:
        yield result
    finally:
        result.release.set()
        await result.provider.close()
        from src.models.league import League

        async with fantasy.sessions() as db, db.begin():
            await db.execute(
                update(League)
                .where(League.id.in_(result.extra_leagues))
                .values(deleted_at=fantasy.source.clock.now)
            )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], "no_coupon"),
        (["won"], "won"),
        (["void"], "void"),
        (["void", "won"], "won"),
        (["lost", "won"], "lost"),
        (["lost", "pending"], "pending"),
        (["void", "pending"], "pending"),
        (["void", "void"], "void"),
    ],
)
def test_unpriced_group_result_precedence(statuses, expected):
    assert group_outcome(statuses) == expected


@pytest.mark.asyncio
async def test_shared_fixture_costs_one_result_and_late_sunday_finalises_independently(results):
    f = results.fantasy
    first = await f.save(body=f.body(0))
    assert first.status_code == 200
    assert (await f.save(player=1, body=f.body(0))).status_code == 200
    assert (await f.save(slot=2, body=f.body(7))).status_code == 200
    group_body = {key: value for key, value in f.body(0).items() if key != "odds"}
    assert (
        await f.request(
            "PUT", player=2, body=group_body, path=f.path.replace("fantasy", "group") + "/pick"
        )
    ).status_code == 200
    receipt = first.json()
    f.source.clock.now = london_utc(WEEK, 18)
    assert (await results.worker().run())["resolved"] == 3
    assert results.calls == [f.fixtures[0].provider_event_id]
    assert await results.spent() == 1
    async with f.sessions() as db:
        group, game = await db.get(TwoGame, f.group.id), await db.get(TwoGame, f.game.id)
        assert group.status == "settled" and group.result_status == "won"
        assert game.status == "locked" and game.finalized_at is None
        parent = await db.get(Gameweek, f.parent.id)
        assert parent.status != GameweekStatus.settled
        table = await standings(db, f.league.id, season=2026)
        assert {row.player_id: row.total_points for row in table}[str(f.players[0].id)] == 22
        operation = await db.scalar(
            select(GameOperation).where(GameOperation.operation_id == receipt["operation_id"])
        )
        assert operation.response == receipt
    f.source.clock.now = london_utc(WEEK + timedelta(days=1), 23, 58)
    await results.worker().run()
    assert len(results.calls) == 1
    f.source.clock.now = london_utc(WEEK + timedelta(days=2), 0, 1)
    await results.worker().run()
    assert results.calls == [f.fixtures[0].provider_event_id, f.fixtures[7].provider_event_id]
    assert await results.spent() == 2
    async with f.sessions() as db:
        game = await db.get(TwoGame, f.game.id)
        assert game.status == "settled" and game.result_status == "scored"
        assert (await db.get(Gameweek, f.parent.id)).status == GameweekStatus.settled
        points = await db.scalar(
            select(func.sum(FantasyPick.points_awarded)).where(
                FantasyPick.player_id == f.players[0].id, FantasyPick.week_id == f.parent.id
            )
        )
        assert points == 44
        versions = [
            (row.kind, row.result_version)
            for row in await db.scalars(select(TwoGame).where(TwoGame.week_id == f.parent.id))
        ]
        events = await db.scalar(
            select(func.count())
            .select_from(TwoGameEvent)
            .where(TwoGameEvent.week_id == f.parent.id, TwoGameEvent.kind == "game_result")
        )
        assert events == 2
    await results.worker().run()
    async with f.sessions() as db:
        assert [
            (row.kind, row.result_version)
            for row in await db.scalars(select(TwoGame).where(TwoGame.week_id == f.parent.id))
        ] == versions
    assert len(results.calls) == 2


@pytest.mark.asyncio
async def test_q9_failed_middle_chunk_keeps_prefix_and_reaches_suffix_after_restart(results):
    f = results.fantasy
    for slot in (1, 2, 3):
        assert (await f.save(slot=slot, body=f.body(slot - 1))).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    await results.ordered([0, 1, 2])
    assert (await results.worker(units_per_pass=1).run())["resolved"] == 1
    results.failures.add(f.fixtures[1].provider_event_id)
    restarted = results.worker()
    outcome = await restarted.run()
    assert outcome["failures"] == 1 and outcome["resolved"] == 1
    assert results.calls == [fixture.provider_event_id for fixture in f.fixtures[:3]]
    assert await results.spent() == 3
    async with f.sessions() as db:
        rows = list(
            await db.scalars(
                select(FantasyPick)
                .where(FantasyPick.week_id == f.parent.id)
                .order_by(FantasyPick.slot)
            )
        )
        assert [row.status for row in rows] == ["won", "pending", "won"]
        assert sum(row.points_awarded or 0 for row in rows) == 44
        dues = await db.scalar(
            select(func.count())
            .select_from(WeeklyFeeObligation)
            .where(WeeklyFeeObligation.league_id == f.league.id)
        )
        assert dues == 1
    await results.worker().run()
    assert len(results.calls) == 3
    results.failures.clear()
    f.source.clock.now += timedelta(minutes=7)
    await results.worker().run()
    assert await results.spent() == 4
    async with f.sessions() as db:
        assert (
            await db.scalar(
                select(func.sum(FantasyPick.points_awarded)).where(
                    FantasyPick.week_id == f.parent.id
                )
            )
            == 66
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(WeeklyFeeObligation)
                .where(WeeklyFeeObligation.league_id == f.league.id)
            )
            == dues
        )


@pytest.mark.asyncio
async def test_pending_prefix_rotates_without_polling_unstarted_sunday(results):
    f = results.fantasy
    for slot, fixture in enumerate((0, 1, 7), 1):
        assert (await f.save(slot=slot, body=f.body(fixture))).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    results.statuses[f.fixtures[0].provider_event_id] = "live"
    await results.ordered([0, 1])
    assert (await results.worker().run())["resolved"] == 1
    assert results.calls == [fixture.provider_event_id for fixture in f.fixtures[:2]]
    assert f.fixtures[7].provider_event_id not in results.calls
    await results.worker().run()
    assert len(results.calls) == 2


@pytest.mark.asyncio
async def test_saturday_only_and_empty_games_finalise_monday_without_provider(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    await results.worker().run()
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))

    async def forbidden():
        raise AssertionError("finaliser acquired provider")

    worker = SettlementWorker(f.sessions, forbidden, source="oddsapi", clock=f.source.clock)
    await worker.run()
    async with f.sessions() as db:
        games = list(await db.scalars(select(TwoGame).where(TwoGame.week_id == f.parent.id)))
        assert all(game.status == "settled" for game in games)
        assert {game.kind: game.result_status for game in games} == {
            "group": "no_coupon",
            "fantasy": "scored",
        }
    assert await results.spent() == 1


@pytest.mark.asyncio
async def test_all_void_fantasy_is_not_a_win_and_preserves_frozen_receipt(results):
    f = results.fantasy
    accepted = (await f.save()).json()
    results.statuses[f.fixtures[0].provider_event_id] = "postponed"
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert pick.status == "void" and pick.points_awarded == 0
        assert pick.frozen_odds == Decimal("2.1500") and pick.revision == 1
        assert (await db.get(TwoGame, f.game.id)).result_status == "all_void"
        operation = await db.scalar(
            select(GameOperation).where(GameOperation.operation_id == accepted["operation_id"])
        )
        assert operation.response == accepted


@pytest.mark.asyncio
async def test_generation_change_during_http_rejects_stale_result_without_refunding(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    results.pause = f.fixtures[0].provider_event_id
    f.source.clock.now = london_utc(WEEK, 18)
    task = asyncio.create_task(results.worker().run())
    await asyncio.wait_for(results.entered.wait(), 3)
    async with f.sessions() as db, db.begin():
        await financial_locks(db, [f.league.id])
        await result_lock(db, f.fixtures[0].id)
        await advance_generation(db, f.fixtures[0].id, f.source.clock.now)
    results.release.set()
    await asyncio.wait_for(task, 5)
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert pick.status == "pending" and pick.points_awarded is None
        assert (await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))).payload[
            "generation"
        ] == 1
    assert await results.spent() == 1


@pytest.mark.asyncio
async def test_inactive_settlement_does_not_acquire_or_create_any_work(results, monkeypatch):
    monkeypatch.setattr(settings, "two_games_enabled", False)
    assert await results.worker().run() == dict(resolved=0, failures=0, chunks=0)
    assert results.calls == [] and await results.spent() == 0


@pytest.mark.asyncio
async def test_accepted_future_moved_postponement_resolves_from_committed_facts(results):
    from src.services.odds_provider import SlateFixture
    from src.services.two_game_fixture_state import record_fixture_observations

    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    fixture = f.fixtures[0]
    async with f.sessions() as db, db.begin():
        await record_fixture_observations(
            db,
            "oddsapi",
            [
                SlateFixture(
                    provider_event_id=fixture.provider_event_id,
                    home=fixture.home,
                    away=fixture.away,
                    competition=fixture.competition,
                    competition_id=fixture.competition_id,
                    kickoff_utc=london_utc(WEEK + timedelta(days=7), 15),
                    status="postponed",
                )
            ],
            observed_at=f.source.clock.now,
            expires_at=f.source.clock.now + timedelta(hours=6),
        )
    assert (await results.worker().run())["resolved"] == 1
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert pick.status == "void" and pick.points_awarded == 0
        assert (await db.get(TwoGame, f.game.id)).status == "settled"
    assert results.calls == [] and await results.spent() == 0


@pytest.mark.asyncio
async def test_generation_refreshes_preloaded_state_after_another_manual_commit(results):
    f = results.fantasy
    fixture_id = f.fixtures[0].id
    async with f.sessions() as db, db.begin():
        await result_lock(db, fixture_id)
        await advance_generation(db, fixture_id, f.source.clock.now)
    async with f.sessions() as stale, stale.begin():
        loaded = await stale.get(ProviderSnapshot, result_key(fixture_id))
        assert loaded.payload["generation"] == 1
        async with f.sessions() as fresh, fresh.begin():
            await result_lock(fresh, fixture_id)
            await advance_generation(fresh, fixture_id, f.source.clock.now)
        await result_lock(stale, fixture_id)
        await advance_generation(stale, fixture_id, f.source.clock.now)
    async with f.sessions() as db:
        assert (await db.get(ProviderSnapshot, result_key(fixture_id))).payload["generation"] == 3


@pytest.mark.asyncio
async def test_queued_zero_entry_reminder_rechecks_first_slot_before_inbox(results):
    from src.models.notification import MemberNotification
    from src.services.two_game_events import prepare_events

    f = results.fantasy
    f.source.clock.now = london_utc(WEEK, 9)
    await lifecycle_events(f.sessions, f.source.clock.now)
    assert (await f.save()).status_code == 200
    async with f.sessions() as db, db.begin():
        await prepare_events(db, f.source.clock.now)
    async with f.sessions() as db:
        reminded = set(
            await db.scalars(
                select(MemberNotification.user_id).where(
                    MemberNotification.league_id == f.league.id,
                    MemberNotification.kind == "game_reminder",
                )
            )
        )
        assert reminded == {f.players[1].id, f.players[2].id}
    assert results.calls == []


async def admin_correction(f, monkeypatch, *, fixture=0, home=0, away=2):
    from src.models.profile import Profile, UserRole
    from src.routers import admin

    monkeypatch.setattr(admin, "_now", f.source.clock)
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(Profile).where(Profile.id == f.players[0].id).values(role=UserRole.admin)
        )
    f.players[0].role = UserRole.admin
    return await f.request(
        "POST",
        path=f"/api/v1/admin/fixtures/{f.fixtures[fixture].id}/correct",
        body=dict(home_goals=home, away_goals=away, reason="Synthetic correction acceptance"),
    )


@pytest.mark.asyncio
async def test_shared_http_correction_updates_both_games_and_is_idempotent(results, monkeypatch):
    from src.models.notification import AuditLog

    f = results.fantasy
    assert (await f.save()).status_code == 200
    group_body = {key: value for key, value in f.body().items() if key != "odds"}
    assert (
        await f.request(
            "PUT", player=1, body=group_body, path=f.path.replace("fantasy", "group") + "/pick"
        )
    ).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    response = await admin_correction(f, monkeypatch)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["picks_checked"] == 2 and body["changed"] == []
    assert len(body["group_changed"]) == len(body["fantasy_changed"]) == 1
    assert (
        not {"odds", "points", "points_before", "combined_odds"} & body["group_changed"][0].keys()
    )
    assert (
        body["fantasy_changed"][0]["points_before"] == 22
        and body["fantasy_changed"][0]["points"] == 0
    )
    async with f.sessions() as db:
        group, game = await db.get(TwoGame, f.group.id), await db.get(TwoGame, f.game.id)
        assert group.result_status == "lost" and group.status == game.status == "settled"
        versions = group.result_version, game.result_version
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert (
            pick.status == "lost"
            and pick.points_awarded == 0
            and pick.frozen_odds == Decimal("2.1500")
        )
        audits = await db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.target_id == f.fixtures[0].id)
        )
        assert audits == 1
    again = await admin_correction(f, monkeypatch)
    assert (
        again.status_code == 200
        and again.json()["group_changed"] == again.json()["fantasy_changed"] == []
    )
    async with f.sessions() as db:
        assert (
            (await db.get(TwoGame, f.group.id)).result_version,
            (await db.get(TwoGame, f.game.id)).result_version,
        ) == versions
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == f.fixtures[0].id)
            )
            == audits
        )
    assert len(results.calls) == 1


@pytest.mark.asyncio
async def test_queued_result_versions_are_prepared_in_semantic_order(results, monkeypatch):
    import uuid

    from src.services import two_game_events as events

    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    assert (await admin_correction(f, monkeypatch)).status_code == 200
    async with f.sessions() as db, db.begin():
        rows = list(
            await db.scalars(
                select(TwoGameEvent)
                .where(TwoGameEvent.game_id == f.game.id)
                .order_by(TwoGameEvent.version)
            )
        )
        assert len(rows) == 2
        reversed_ids = sorted([uuid.uuid4(), uuid.uuid4()], reverse=True)
        for row, identity in zip(rows, reversed_ids, strict=True):
            row.id = identity
        expected = [row.version for row in rows]
    observed = []
    original = events.prepare_collected_notifications

    async def capture(db, intents):
        observed.extend(
            intent.data["result_version"]
            for intent in intents
            if intent.user_id == f.players[0].id and intent.data.get("game_id") == str(f.game.id)
        )
        return await original(db, intents)

    monkeypatch.setattr(events, "prepare_collected_notifications", capture)
    async with f.sessions() as db, db.begin():
        await events.prepare_events(db, f.source.clock.now)
    assert observed == expected


async def legacy_round(results, statuses, *, shared=False):
    import uuid
    from datetime import date

    from src.models.fixture import Fixture
    from src.models.gameweek import GameweekFixture
    from src.models.league import League
    from src.models.league_membership import LeagueMembership
    from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus

    f = results.fantasy
    label = date(2330, 1, 1)
    label += timedelta(days=(5 - label.weekday()) % 7)
    f.source.clock.now = london_utc(label + timedelta(days=2))
    async with f.sessions() as db, db.begin():
        league = League(
            slug=f"settlement-legacy-{uuid.uuid4().hex}",
            name="Synthetic legacy results",
            created_by=f.players[0].id,
        )
        db.add(league)
        await db.flush()
        results.extra_leagues.append(league.id)
        parent = Gameweek(
            league_id=league.id,
            starts_on=label,
            locks_at_utc=london_utc(label, 14, 30),
            status=GameweekStatus.locked,
        )
        db.add(parent)
        await db.flush()
        fixtures = []
        for index, value in enumerate(statuses):
            db.add(LeagueMembership(league_id=league.id, player_id=f.players[index].id))
            fixture = (
                await db.get(Fixture, f.fixtures[index].id)
                if shared
                else Fixture(
                    provider_event_id=f"legacy-result-{uuid.uuid4().hex}",
                    home=f"Legacy home {index}",
                    away=f"Legacy away {index}",
                    kickoff_utc=london_utc(label, 15),
                    competition="Synthetic",
                    competition_id="synthetic",
                )
            )
            if not shared:
                db.add(fixture)
            await db.flush()
            db.add(GameweekFixture(gameweek_id=parent.id, fixture_id=fixture.id))
            await db.flush()
            db.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=parent.id,
                    fixture_id=fixture.id,
                    player_id=f.players[index].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.HOME,
                    runner_name=fixture.home,
                    odds_at_pick=Decimal("2.00"),
                    status=PickStatus(value),
                    points_awarded=20 if value == "won" else None if value == "pending" else 0,
                )
            )
            fixtures.append(fixture.id)
        return league.id, parent.id, fixtures


@pytest.mark.asyncio
async def test_provider_free_recovery_finalises_nonempty_resolved_legacy_round(results):
    _, parent_id, _ = await legacy_round(results, ["won", "lost"])
    await results.worker().finalise()
    async with results.fantasy.sessions() as db:
        assert (await db.get(Gameweek, parent_id)).status == GameweekStatus.settled
        outbox = list(
            await db.scalars(
                select(ProviderSnapshot).where(
                    ProviderSnapshot.key.startswith(f"legacy-settlement:v1:{parent_id}:")
                )
            )
        )
        assert len(outbox) == 1 and len(outbox[0].payload["notifications"]) == 2
    await results.worker().finalise()
    assert results.calls == [] and await results.spent() == 0
    async with results.fantasy.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProviderSnapshot)
                .where(ProviderSnapshot.key.startswith(f"legacy-settlement:v1:{parent_id}:"))
            )
            == 1
        )


@pytest.mark.asyncio
async def test_mixed_settlement_serialises_two_last_legacy_chunks(results, monkeypatch):
    _, parent_id, _ = await legacy_round(results, ["pending", "pending"])
    original = results.dispatch
    both = asyncio.Event()
    release = asyncio.Event()

    async def barrier(request):
        if request.url.path.startswith("/events/legacy-result-"):
            results.entered_count += 1
            if results.entered_count == 2:
                both.set()
            await release.wait()
        return await original(request)

    results.entered_count = 0
    client = httpx.AsyncClient(
        base_url="https://synthetic.invalid", transport=httpx.MockTransport(barrier)
    )
    await results.provider.close()
    results.provider = OddsApiProvider(
        "synthetic-results", budget=results.fantasy.source.budget, client=client
    )
    first = asyncio.create_task(results.worker(units_per_pass=1).run())
    second = asyncio.create_task(results.worker(units_per_pass=1).run())
    try:
        await asyncio.wait_for(both.wait(), 3)
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert sum(outcome["resolved"] for outcome in outcomes) == 2
    finally:
        release.set()
        for task in (first, second):
            if not task.done():
                task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
    async with results.fantasy.sessions() as db:
        assert (await db.get(Gameweek, parent_id)).status == GameweekStatus.settled
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProviderSnapshot)
                .where(ProviderSnapshot.key.startswith(f"legacy-settlement:v1:{parent_id}:"))
            )
            == 1
        )
    assert await results.spent() == 2


@pytest.mark.asyncio
async def test_one_http_correction_recomputes_legacy_group_fantasy_across_leagues(
    results, monkeypatch
):
    from src.models.notification import AuditLog
    from src.models.pick import Pick

    f = results.fantasy
    assert (await f.save()).status_code == 200
    body = {key: value for key, value in f.body().items() if key != "odds"}
    assert (
        await f.request(
            "PUT", player=1, body=body, path=f.path.replace("fantasy", "group") + "/pick"
        )
    ).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    legacy_league, _, _ = await legacy_round(results, ["won"], shared=True)
    response = await admin_correction(f, monkeypatch)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["picks_checked"] == 3
    assert (
        len(result["changed"])
        == len(result["group_changed"])
        == len(result["fantasy_changed"])
        == 1
    )
    async with f.sessions() as db:
        old = await db.scalar(select(Pick).where(Pick.league_id == legacy_league))
        new = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert old.status.value == new.status == "lost"
        assert old.points_awarded == new.points_awarded == 0
        assert old.odds_at_pick == Decimal("2.00") and new.frozen_odds == Decimal("2.1500")
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == f.fixtures[0].id)
            )
            == 2
        )
    assert len(result["leagues_audited"]) == 2 and len(results.calls) == 1


@pytest.mark.asyncio
async def test_actual_http_manual_correction_fences_paused_provider_and_supplies_pending_games(
    results, monkeypatch
):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    body = {key: value for key, value in f.body().items() if key != "odds"}
    assert (
        await f.request(
            "PUT", player=1, body=body, path=f.path.replace("fantasy", "group") + "/pick"
        )
    ).status_code == 200
    legacy_league, _, _ = await legacy_round(results, ["won"], shared=True)
    results.pause = f.fixtures[0].provider_event_id
    task = asyncio.create_task(results.worker().run())
    try:
        await asyncio.wait_for(results.entered.wait(), 3)
        corrected = await admin_correction(f, monkeypatch)
        assert corrected.status_code == 200, corrected.text
        assert len(corrected.json()["changed"]) == 1
        assert corrected.json()["group_changed"] == corrected.json()["fantasy_changed"] == []
        results.release.set()
        await asyncio.wait_for(task, 5)
    finally:
        results.release.set()
        await asyncio.gather(task, return_exceptions=True)
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        group = await db.scalar(select(GroupPick).where(GroupPick.week_id == f.parent.id))
        assert pick.status == group.status == "lost" and pick.points_awarded == 0
        canonical = await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))
        assert canonical.payload["authority"] == "manual" and canonical.payload["generation"] == 1
    assert await results.spent() == len(results.calls) == 1


@pytest.mark.asyncio
async def test_reclaimed_work_token_discards_older_opposite_result_without_refund(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    entered, release = asyncio.Event(), asyncio.Event()

    async def competing(request):
        event = request.url.path.rsplit("/", 1)[-1]
        results.calls.append(event)
        first = len(results.calls) == 1
        if first:
            entered.set()
            await release.wait()
        return httpx.Response(
            200,
            json=dict(
                id=event,
                status="finished",
                scores=dict(home=0 if first else 2, away=2 if first else 0),
            ),
        )

    await results.provider.close()
    results.provider = OddsApiProvider(
        "synthetic-token-recovery",
        budget=f.source.budget,
        client=httpx.AsyncClient(
            base_url="https://synthetic.invalid", transport=httpx.MockTransport(competing)
        ),
    )
    task = asyncio.create_task(results.worker(units_per_pass=1).run())
    try:
        await asyncio.wait_for(entered.wait(), 3)
        f.source.clock.now += timedelta(seconds=46)
        newer = await results.worker(units_per_pass=1).run()
        assert newer["resolved"] == 1
        async with f.sessions() as db:
            version = (await db.get(TwoGame, f.game.id)).result_version
        release.set()
        older = await asyncio.wait_for(task, 5)
        assert older["resolved"] == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.week_id == f.parent.id))
        assert pick.status == "won" and pick.points_awarded == 22
        assert (await db.get(TwoGame, f.game.id)).result_version == version
    assert await results.spent() == len(results.calls) == 2


@pytest.mark.asyncio
async def test_mixed_statistics_count_legacy_once_and_fantasy_legs_without_group_or_voids(
    results, monkeypatch
):
    import uuid

    from sqlalchemy import event

    from src.models.gameweek import GameweekFixture
    from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
    from src.services.scoring import standings_by_league
    from src.services.two_game_results import recompute_game

    f = results.fantasy
    for slot in range(1, 7):
        assert (await f.save(slot, f.body(fixture=slot - 1))).status_code == 200
    group_body = {key: value for key, value in f.body().items() if key != "odds"}
    assert (
        await f.request("PUT", body=group_body, path=f.path.replace("fantasy", "group") + "/pick")
    ).status_code == 200
    old_ids = []
    async with f.sessions() as db, db.begin():
        for offset, odds, points in [(14, "2.00", 20), (7, "3.00", 30)]:
            label = WEEK - timedelta(days=offset)
            old = Gameweek(
                league_id=f.league.id,
                starts_on=label,
                locks_at_utc=london_utc(label, 14, 30),
                status=GameweekStatus.settled,
            )
            db.add(old)
            await db.flush()
            old_ids.append(old.id)
            db.add(GameweekFixture(gameweek_id=old.id, fixture_id=f.fixtures[0].id))
            await db.flush()
            db.add(
                Pick(
                    league_id=f.league.id,
                    gameweek_id=old.id,
                    fixture_id=f.fixtures[0].id,
                    player_id=f.players[0].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.HOME,
                    runner_name="Legacy home",
                    odds_at_pick=Decimal(odds),
                    status=PickStatus.won,
                    points_awarded=points,
                )
            )
            if offset == 14:
                db.add(
                    Pick(
                        league_id=f.league.id,
                        gameweek_id=old.id,
                        fixture_id=f.fixtures[0].id,
                        player_id=f.players[1].id,
                        market=PickMarket.MATCH_ODDS,
                        outcome=PickOutcome.AWAY,
                        runner_name="Legacy away",
                        odds_at_pick=Decimal("4.00"),
                        status=PickStatus.void,
                        points_awarded=0,
                    )
                )
        for slot, status, price, points in [
            (1, "won", "2.05", 21),
            (2, "lost", "1.80", 0),
            (3, "void", "7.00", 0),
            (4, "won", "2.15", 22),
            (5, "pending", "9.00", None),
            (6, "won", "3.05", 31),
        ]:
            await db.execute(
                update(FantasyPick)
                .where(FantasyPick.game_id == f.game.id, FantasyPick.slot == slot)
                .values(status=status, frozen_odds=Decimal(price), points_awarded=points)
            )
        await db.execute(
            update(GroupPick).where(GroupPick.game_id == f.group.id).values(status="won")
        )
        await recompute_game(db, f.game.id, london_utc(WEEK, 18))
        snapshot = await db.get(ProviderSnapshot, f"game-result:v1:{f.game.id}")
        assert snapshot.payload["members"][0]["weekly_points"] == 74
        assert snapshot.payload["winner_ids"] == [] and not snapshot.payload["final"]
    statements = []

    def count_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = f.sessions.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", count_select)
    try:
        async with f.sessions() as db:
            rows = await standings(db, f.league.id, season=2026)
        assert len(statements) == 2
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_select)
    own = next(row for row in rows if row.player_id == str(f.players[0].id))
    assert (own.total_points, own.picks_played, own.picks_priced, own.picks_won) == (124, 6, 6, 5)
    assert (own.cumulative_odds, own.average_odds, own.points_per_pick) == (14.05, 2.34, 20.67)
    assert (own.best_return, own.win_rate_pct, own.longshot_picks, own.favourite_picks) == (
        31,
        83,
        2,
        4,
    )
    void = next(row for row in rows if row.player_id == str(f.players[1].id))
    assert (void.total_points, void.picks_played, void.picks_priced, void.win_rate_pct) == (
        0,
        1,
        0,
        None,
    )
    async with f.sessions() as db:
        rewound = await standings_by_league(
            db, [f.league.id], exclude_gameweek_ids=[f.parent.id], with_form=False, season=2026
        )
        assert (
            next(r for r in rewound[f.league.id] if r.player_id == own.player_id).total_points == 50
        )
        assert set(old_ids).isdisjoint({f.parent.id, uuid.UUID(int=0)})
    monkeypatch.setattr(settings, "two_games_enabled", False)
    async with f.sessions() as db:
        retained = await standings(db, f.league.id, season=2026)
    assert [(r.player_id, r.total_points) for r in retained] == [
        (r.player_id, r.total_points) for r in rows
    ]


@pytest.mark.asyncio
async def test_late_sunday_june_result_stays_in_saturdays_season(results):
    import uuid
    from datetime import date

    from src.models.fixture import Fixture
    from src.services.football_provider import season_for
    from src.services.two_game_results import recompute_game

    f = results.fantasy
    year = next(year for year in range(2340, 2400) if date(year, 6, 29).weekday() == 5)
    label = date(year, 6, 29)
    target = await entry_tests.additional_week(f, label)
    _, parent, game, fixtures = target
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(Fixture)
            .where(Fixture.id == fixtures[0].id)
            .values(kickoff_utc=london_utc(label + timedelta(days=1), 23, 59))
        )
        db.add(
            FantasyPick(
                league_id=f.league.id,
                week_id=parent.id,
                game_id=game.id,
                fixture_id=fixtures[0].id,
                player_id=f.players[0].id,
                slot=1,
                market="MATCH_ODDS",
                outcome="HOME",
                runner_name="Late Sunday home",
                frozen_odds=Decimal("2.0500"),
                quoted_at=london_utc(label - timedelta(days=1)),
                provider="oddsapi",
                bookmaker="Bet365",
                operation_id=uuid.uuid4(),
            )
        )
    results.statuses[fixtures[0].provider_event_id] = "live"
    f.source.clock.now = london_utc(label + timedelta(days=2), 0, 1)
    await results.worker().run()
    async with f.sessions() as db:
        assert (await db.get(TwoGame, game.id)).finalized_at is None
    results.statuses[fixtures[0].provider_event_id] = "finished"
    f.source.clock.now = london_utc(label + timedelta(days=2), 2, 6)
    await results.worker().run()
    assert results.calls == [fixtures[0].provider_event_id] * 2
    async with f.sessions() as db, db.begin():
        settled = await db.get(TwoGame, game.id)
        assert settled.finalized_at == f.source.clock.now and settled.result_status == "scored"
        assert season_for(label) == year - 1
        old = await standings(db, f.league.id, season=year - 1)
        new = await standings(db, f.league.id, season=year)
        assert next(row for row in old if row.player_id == str(f.players[0].id)).total_points == 21
        assert all(row.total_points == 0 for row in new)
        assert not await recompute_game(db, game.id, f.source.clock.now)


async def site_admin(f, monkeypatch):
    from src.models.profile import Profile, UserRole
    from src.routers import admin

    monkeypatch.setattr(admin, "_now", f.source.clock)
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(Profile).where(Profile.id == f.players[0].id).values(role=UserRole.admin)
        )
    f.players[0].role = UserRole.admin


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["settle", "void-non-scoring"])
async def test_manual_round_rechecks_committed_settlement_after_waiting_for_league_lock(
    results, monkeypatch, route
):
    from src.models.notification import AuditLog
    from src.models.pick import Pick, PickStatus
    from src.services import two_game_settlement as service

    f = results.fantasy
    league_id, parent_id, fixtures = await legacy_round(results, ["pending"])
    await site_admin(f, monkeypatch)
    reached = asyncio.Event()
    original = service.settlement_locks

    async def arriving(db, league_ids):
        reached.set()
        await original(db, league_ids)

    async with f.sessions() as holder:
        await original(holder, [league_id])
        monkeypatch.setattr(service, "settlement_locks", arriving)
        body = (
            dict(results=[dict(fixture_id=str(fixtures[0]), home_goals=0, away_goals=2)])
            if route == "settle"
            else dict(reason="Synthetic non-scoring round")
        )
        request = asyncio.create_task(
            f.request("POST", path=f"/api/v1/admin/results/{parent_id}/{route}", body=body)
        )
        try:
            await asyncio.wait_for(reached.wait(), 3)
            await holder.execute(
                update(Pick)
                .where(Pick.gameweek_id == parent_id)
                .values(status=PickStatus.won, points_awarded=20)
            )
            await holder.execute(
                update(Gameweek)
                .where(Gameweek.id == parent_id)
                .values(status=GameweekStatus.settled, settled_at=f.source.clock.now)
            )
            await holder.commit()
            response = await asyncio.wait_for(request, 3)
            assert response.status_code == 409, response.text
        finally:
            await holder.rollback()
            await asyncio.gather(request, return_exceptions=True)
    async with f.sessions() as db:
        assert (
            await db.scalar(select(Pick).where(Pick.gameweek_id == parent_id))
        ).points_awarded == 20
        assert (
            await db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.target_id == parent_id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_concurrent_identical_shared_corrections_publish_one_version_and_audit(
    results, monkeypatch
):
    from src.models.notification import AuditLog

    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    async with f.sessions() as db:
        version = (await db.get(TwoGame, f.game.id)).result_version
    await site_admin(f, monkeypatch)
    body = dict(home_goals=0, away_goals=2, reason="Synthetic concurrent shared correction")
    path = f"/api/v1/admin/fixtures/{f.fixtures[0].id}/correct"
    first, second = await asyncio.gather(
        f.request("POST", path=path, body=body), f.request("POST", path=path, body=body)
    )
    assert first.status_code == second.status_code == 200
    assert sorted(len(response.json()["fantasy_changed"]) for response in (first, second)) == [0, 1]
    async with f.sessions() as db:
        assert (await db.get(TwoGame, f.game.id)).result_version == version + 1
        assert (await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))).payload[
            "generation"
        ] == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == f.fixtures[0].id)
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["pick", "round", "void"])
async def test_scoped_manual_writer_fences_inflight_result_without_promoting_its_scope(
    results, monkeypatch, writer
):
    from src.models.league import League
    from src.models.pick import Pick, PickStatus

    f = results.fantasy
    assert (await f.save()).status_code == 200
    league_id, parent_id, fixtures = await legacy_round(
        results, ["won" if writer == "pick" else "pending"], shared=True
    )
    await site_admin(f, monkeypatch)
    if writer == "void":
        async with f.sessions() as db, db.begin():
            parent = await db.get(Gameweek, parent_id)
            league = await db.get(League, league_id)
            league.slate_start_weekday = league.slate_end_weekday = 4
            db.add(
                Gameweek(
                    league_id=league_id,
                    starts_on=parent.starts_on - timedelta(days=1),
                    locks_at_utc=parent.locks_at_utc - timedelta(days=1),
                    status=GameweekStatus.settled,
                )
            )
    results.pause = f.fixtures[0].provider_event_id
    task = asyncio.create_task(results.worker().run())
    try:
        await asyncio.wait_for(results.entered.wait(), 3)
        if writer == "pick":
            async with f.sessions() as db:
                pick_id = await db.scalar(select(Pick.id).where(Pick.gameweek_id == parent_id))
            path = f"/api/v1/admin/picks/{pick_id}/correct"
            body = dict(home_goals=0, away_goals=2, reason="Synthetic scoped pick correction")
        elif writer == "round":
            path = f"/api/v1/admin/results/{parent_id}/settle"
            body = dict(results=[dict(fixture_id=str(fixtures[0]), home_goals=0, away_goals=2)])
        else:
            path = f"/api/v1/admin/results/{parent_id}/void-non-scoring"
            body = dict(reason="Synthetic undeclared legacy sibling")
        response = await f.request("POST", path=path, body=body)
        assert response.status_code == 200, response.text
        results.release.set()
        await asyncio.wait_for(task, 5)
    finally:
        results.release.set()
        await asyncio.gather(task, return_exceptions=True)
    async with f.sessions() as db:
        scoped = await db.scalar(select(Pick).where(Pick.gameweek_id == parent_id))
        assert scoped.status == (PickStatus.void if writer == "void" else PickStatus.lost)
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == f.game.id))
        assert pick.status == "pending" and pick.points_awarded is None
        snapshot = await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))
        assert snapshot.payload["generation"] == 1
        assert (
            snapshot.payload.get("authority") != "manual" and "settlement" not in snapshot.payload
        )
    assert await results.spent() == len(results.calls) == 1


@pytest.mark.asyncio
async def test_legacy_outbox_orders_original_then_multiple_same_clock_corrections(
    results, monkeypatch
):
    from src.models.pick import Pick, PickStatus
    from src.services import two_game_events as events
    from src.services.two_game_settlement import settlement_locks

    f = results.fantasy
    league_id, parent_id, _ = await legacy_round(results, ["won"])
    await results.worker().finalise()
    async with f.sessions() as db, db.begin():
        await settlement_locks(db, [league_id])
        pick = await db.scalar(select(Pick).where(Pick.gameweek_id == parent_id))
        pick.status, pick.points_awarded = PickStatus.lost, 0
        await db.flush()
        await events.stage_legacy_corrections(db, [pick.id], f.source.clock.now, 1)
        pick.status, pick.points_awarded = PickStatus.won, 20
        await db.flush()
        await events.stage_legacy_corrections(db, [pick.id], f.source.clock.now, 2)
    observed = []

    async def capture(db, intents):
        observed.extend(
            (intent.data["type"], intent.body)
            for intent in intents
            if intent.data.get("league_id") == str(league_id)
        )
        return []

    monkeypatch.setattr(events, "prepare_collected_notifications", capture)
    async with f.sessions() as db, db.begin():
        await events.prepare_events(db, f.source.clock.now)
    assert [kind for kind, _ in observed] == [
        "round_settled",
        "result_corrected",
        "result_corrected",
    ]
    assert (
        "20 points" in observed[0][1] and "lost" in observed[1][1] and "20 points" in observed[2][1]
    )


async def observe_result_fixture(f, *, status, kickoff=None):
    from src.services.odds_provider import SlateFixture
    from src.services.two_game_fixture_state import record_fixture_observations

    fixture = f.fixtures[0]
    async with f.sessions() as db, db.begin():
        await record_fixture_observations(
            db,
            "oddsapi",
            [
                SlateFixture(
                    provider_event_id=fixture.provider_event_id,
                    home=fixture.home,
                    away=fixture.away,
                    competition=fixture.competition,
                    competition_id=fixture.competition_id,
                    kickoff_utc=kickoff or fixture.kickoff_utc,
                    status=status,
                )
            ],
            observed_at=f.source.clock.now,
            expires_at=f.source.clock.now + timedelta(hours=6),
        )


@pytest.mark.asyncio
async def test_inferred_void_rechecks_reinstatement_between_preflight_and_commit(
    results, monkeypatch
):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await observe_result_fixture(f, status="postponed")
    worker = results.worker()
    original = worker._preflight

    async def reinstate(lease):
        captured = await original(lease)
        assert captured[1].void
        f.source.clock.now += timedelta(seconds=1)
        await observe_result_fixture(f, status="pending")
        return captured

    monkeypatch.setattr(worker, "_preflight", reinstate)
    assert (await worker.run())["resolved"] == 0
    assert results.calls == [] and await results.spent() == 0
    async with f.sessions() as db:
        pick = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == f.game.id))
        assert pick.status == "pending" and pick.points_awarded is None
    f.source.clock.now += timedelta(minutes=7)
    assert (await results.worker().run())["resolved"] == 1
    assert len(results.calls) == await results.spent() == 1


@pytest.mark.asyncio
async def test_old_provider_void_does_not_void_reinstated_later_week_or_poll_before_kickoff(
    results,
):
    from src.models.two_game import TwoGameFixture

    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    results.statuses[f.fixtures[0].provider_event_id] = "postponed"
    await results.worker().run()
    async with f.sessions() as db:
        assert (
            await db.scalar(select(FantasyPick).where(FantasyPick.game_id == f.game.id))
        ).status == "void"
        assert (await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))).payload[
            "authority"
        ] == "provider"
    next_label = WEEK + timedelta(days=7)
    target = await entry_tests.additional_week(f, next_label)
    league, parent, game, fixtures = target
    f.source.clock.now = london_utc(WEEK, 18, 1)
    await observe_result_fixture(f, status="pending", kickoff=london_utc(next_label, 15))
    async with f.sessions() as db, db.begin():
        db.add(TwoGameFixture(game_id=game.id, fixture_id=f.fixtures[0].id))
    body = {**f.body(), "fixture_id": str(f.fixtures[0].id)}
    path = f"/api/v1/leagues/{league.id}/weeks/{parent.id}/games/fantasy/slots/1"
    assert (await f.request("PUT", path=path, body=body)).status_code == 200
    f.source.clock.now = london_utc(next_label, 14)
    await results.worker().run()
    assert len(results.calls) == await results.spent() == 1
    results.statuses[f.fixtures[0].provider_event_id] = "finished"
    f.source.clock.now = london_utc(next_label, 18)
    await results.worker().run()
    async with f.sessions() as db:
        old = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == f.game.id))
        new = await db.scalar(select(FantasyPick).where(FantasyPick.game_id == game.id))
        assert old.status == "void" and old.points_awarded == 0
        assert new.status == "won" and new.points_awarded == 22
    assert len(results.calls) == await results.spent() == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_only_enabled_scheduler_has_independent_minute_result_finalisation(monkeypatch, enabled):
    from src.scheduler import create_scheduler

    monkeypatch.setattr(settings, "two_games_enabled", enabled)
    scheduler = create_scheduler()
    job = scheduler.get_job("two_game_settlement")
    if enabled:
        assert job is not None and job.trigger.interval == timedelta(minutes=1)
        assert job.coalesce and job.max_instances == 1
    else:
        assert job is None


@pytest.mark.asyncio
async def test_shared_scoped_shared_correction_restores_result_with_new_notice_identity(
    results, monkeypatch
):
    from src.models.pick import Pick

    f = results.fantasy
    _, parent_id, _ = await legacy_round(results, ["won"], shared=True)
    await results.worker().finalise()
    assert (await admin_correction(f, monkeypatch)).status_code == 200
    async with f.sessions() as db:
        pick_id = await db.scalar(select(Pick.id).where(Pick.gameweek_id == parent_id))
    restored = await f.request(
        "POST",
        path=f"/api/v1/admin/picks/{pick_id}/correct",
        body=dict(home_goals=2, away_goals=0, reason="Synthetic scoped restore"),
    )
    assert restored.status_code == 200 and restored.json()["changed"]
    again = await admin_correction(f, monkeypatch)
    assert again.status_code == 200 and len(again.json()["changed"]) == 1
    repeated = await admin_correction(f, monkeypatch)
    assert repeated.status_code == 200 and repeated.json()["changed"] == []
    async with f.sessions() as db:
        state = await db.get(ProviderSnapshot, result_key(f.fixtures[0].id))
        assert state.payload["generation"] == 3
        notices = list(
            await db.scalars(
                select(ProviderSnapshot).where(
                    ProviderSnapshot.key.startswith(
                        f"legacy-settlement:v1:{parent_id}:result_corrected:"
                    )
                )
            )
        )
        assert len(notices) == 3
        assert sorted(row.payload["sequence"] for row in notices) == [2, 3, 4]


@pytest.mark.asyncio
async def test_budget_refusal_survives_restart_while_provider_free_finalisers_continue(
    results, monkeypatch
):
    from src.services.provider_budget import BudgetPolicy

    f = results.fantasy
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    monkeypatch.setattr(f.source.budget, "policy", BudgetPolicy(hourly=1))
    await f.source.budget.admit("legacy")
    before_dues = await f.count(WeeklyFeeObligation)
    first = await results.worker().run()
    assert first["failures"] == 1 and first["resolved"] == 0
    async with f.sessions() as db:
        assert (await db.get(TwoGame, f.group.id)).result_status == "no_coupon"
        assert (await db.get(TwoGame, f.group.id)).finalized_at == f.source.clock.now
        assert (await db.get(TwoGame, f.game.id)).finalized_at is None
    assert (await results.worker().run())["chunks"] == 0
    assert results.calls == [] and await results.spent() == 0
    f.source.clock.now += timedelta(hours=1, seconds=1)
    assert (await results.worker().run())["resolved"] == 1
    assert len(results.calls) == await results.spent() == 1
    assert await f.count(WeeklyFeeObligation) == before_dues


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", [9, 18, 49])
async def test_cancelled_game_keeps_lifecycle_state_and_suppresses_entry_notices(results, hour):
    f = results.fantasy
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(TwoGame).where(TwoGame.week_id == f.parent.id).values(status="cancelled")
        )
    f.source.clock.now = london_utc(WEEK) + timedelta(hours=hour)
    await lifecycle_events(f.sessions, f.source.clock.now)
    await results.worker().finalise()
    await lifecycle_events(f.sessions, f.source.clock.now)
    async with f.sessions() as db:
        games = list(await db.scalars(select(TwoGame).where(TwoGame.week_id == f.parent.id)))
        assert all(game.status == "cancelled" for game in games)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(TwoGameEvent)
                .where(
                    TwoGameEvent.week_id == f.parent.id,
                    TwoGameEvent.kind.in_(["game_opened", "game_locked", "game_reminder"]),
                )
            )
            == 0
        )
    assert results.calls == []
    group = await f.request("GET", path=f.path.replace("fantasy", "group"))
    fantasy = await f.request("GET", path=f.path)
    assert group.status_code == fantasy.status_code == 200
    assert group.json()["result"]["final"] is (hour >= 15)
    assert fantasy.json()["result"]["provisional"] is (hour < 48)


@pytest.mark.asyncio
async def test_shared_correction_locks_pending_claim_league_before_it_can_settle(
    results, monkeypatch
):
    from src.models.pick import Pick, PickStatus
    from src.services import two_game_corrections as corrections
    from src.services.two_game_settlement import settlement_locks

    f = results.fantasy
    first_league, _, _ = await legacy_round(results, ["won"], shared=True)
    pending_league, pending_parent, _ = await legacy_round(results, ["pending"], shared=True)
    await site_admin(f, monkeypatch)
    reached = asyncio.Event()
    scopes = []

    async def arriving(db, league_ids):
        scopes.append(set(league_ids))
        reached.set()
        await settlement_locks(db, league_ids)

    async with f.sessions() as holder:
        await settlement_locks(holder, [first_league, pending_league])
        monkeypatch.setattr(corrections, "settlement_locks", arriving)
        request = asyncio.create_task(admin_correction(f, monkeypatch))
        try:
            await asyncio.wait_for(reached.wait(), 3)
            assert {first_league, pending_league} <= scopes[0]
            await holder.execute(
                update(Pick)
                .where(Pick.gameweek_id == pending_parent)
                .values(status=PickStatus.won, points_awarded=20)
            )
            await holder.execute(
                update(Gameweek)
                .where(Gameweek.id == pending_parent)
                .values(status=GameweekStatus.settled, settled_at=f.source.clock.now)
            )
            await holder.commit()
            response = await asyncio.wait_for(request, 3)
            assert response.status_code == 200, response.text
            assert len(response.json()["changed"]) == 2
        finally:
            await holder.rollback()
            await asyncio.gather(request, return_exceptions=True)


@pytest.mark.asyncio
async def test_shared_correction_refuses_new_league_scope_without_partial_mutation(
    results, monkeypatch
):
    from src.models.pick import Pick, PickStatus
    from src.services import two_game_corrections as corrections
    from src.services.two_game_settlement import settlement_locks

    f = results.fantasy
    league_id, parent_id, _ = await legacy_round(results, ["won"], shared=True)
    await site_admin(f, monkeypatch)
    reached = asyncio.Event()

    async def arriving(db, league_ids):
        reached.set()
        await settlement_locks(db, league_ids)

    async with f.sessions() as holder:
        await settlement_locks(holder, [league_id])
        monkeypatch.setattr(corrections, "settlement_locks", arriving)
        request = asyncio.create_task(admin_correction(f, monkeypatch))
        try:
            await asyncio.wait_for(reached.wait(), 3)
            await legacy_round(results, ["won"], shared=True)
            await holder.commit()
            response = await asyncio.wait_for(request, 3)
            assert (
                response.status_code == 409
                and response.json()["detail"]["code"] == "RESULT_SCOPE_CHANGED"
            )
        finally:
            await holder.rollback()
            await asyncio.gather(request, return_exceptions=True)
    async with f.sessions() as db:
        original = await db.scalar(select(Pick).where(Pick.gameweek_id == parent_id))
        assert original.status == PickStatus.won and original.points_awarded == 20
        assert await db.get(ProviderSnapshot, result_key(f.fixtures[0].id)) is None
    accepted = await admin_correction(f, monkeypatch)
    assert accepted.status_code == 200 and len(accepted.json()["changed"]) == 2
