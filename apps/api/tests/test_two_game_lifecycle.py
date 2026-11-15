"""Durable local notices, independent entry latency and requester-only lifecycle."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from src.config import settings
from src.models.notification import (
    MemberNotification,
    NotificationPreferences,
    PushSubscription,
)
from src.models.two_game import (
    FantasyPick,
    GroupPick,
    TwoGame,
    TwoGameEvent,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.services import two_game_events as events
from src.services.push_notification_service import PushDeliveryOutcome, PushDeliveryReport
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import bill_all
from tests import test_two_game_fantasy as entries
from tests import test_two_game_settlement as settlement
from tests import two_game_test_store as result_store_fixtures

baseline_db_engine = result_store_fixtures.baseline_db_engine
result_store = result_store_fixtures.result_store
db_engine = result_store_fixtures.db_engine

fantasy = entries.fantasy
results = settlement.results
WEEK = entries.WEEK


async def full_audience(f):
    await bill_all(f.sessions, f.source.clock.now)


async def subscriptions(f, monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", "synthetic-local-private-key")
    monkeypatch.setattr(settings, "vapid_public_key", "synthetic-local-public-key")
    async with f.sessions() as db, db.begin():
        for member in f.players[:3]:
            db.add(
                PushSubscription(
                    user_id=member.id,
                    subscription=dict(
                        endpoint=f"https://synthetic.invalid/push/{member.id}",
                        keys=dict(p256dh="synthetic", auth="synthetic"),
                    ),
                )
            )


@pytest.mark.asyncio
async def test_independent_group_fantasy_claims_and_fake_push_failures_never_duplicate(
    results, monkeypatch
):
    f = results.fantasy
    await full_audience(f)
    assert (await f.save()).status_code == 200
    await subscriptions(f, monkeypatch)
    attempted = []

    async def failed(plan):
        assert f.sessions.kw["bind"].pool.checkedout() == 0
        attempted.extend(push.subscription_id for push in plan.pushes)
        return PushDeliveryReport(
            tuple(PushDeliveryOutcome(push.subscription_id, "failed") for push in plan.pushes),
            plan.attempted_at,
        )

    monkeypatch.setattr(events, "deliver_prepared_notification", failed)
    f.source.clock.now = london_utc(WEEK, 18)
    await results.worker().run()
    await events.deliver_events(f.sessions, clock=f.source.clock)
    assert len(attempted) == 3
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    await events.deliver_events(f.sessions, clock=f.source.clock)
    assert len(attempted) == 6
    await events.deliver_events(f.sessions, clock=f.source.clock)
    assert len(attempted) == 6
    async with f.sessions() as db:
        inbox = list(
            await db.scalars(
                select(MemberNotification).where(MemberNotification.league_id == f.league.id)
            )
        )
        assert len(inbox) == 6
        assert {row.url for row in inbox} == {
            f"/leagues/{f.league.id}/weeks/{f.parent.id}/group",
            f"/leagues/{f.league.id}/weeks/{f.parent.id}/fantasy",
        }
        assert all(
            row.failed_send_count == 2
            for row in await db.scalars(
                select(PushSubscription).where(
                    PushSubscription.user_id.in_([member.id for member in f.players[:3]])
                )
            )
        )
    assert len(results.calls) == 1


@pytest.mark.asyncio
async def test_claim_and_inbox_commit_survive_delivery_exception_and_restart(results, monkeypatch):
    f = results.fantasy
    await full_audience(f)
    await subscriptions(f, monkeypatch)
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    attempted = []

    async def crash(plan):
        attempted.append(plan)
        raise RuntimeError("synthetic push failure after committed claims")

    monkeypatch.setattr(events, "deliver_prepared_notification", crash)
    with pytest.raises(RuntimeError, match="committed claims"):
        await events.deliver_events(f.sessions, clock=f.source.clock)
    assert len(attempted) == 1
    async with f.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MemberNotification)
                .where(MemberNotification.league_id == f.league.id)
            )
            == 6
        )
    await events.deliver_events(f.sessions, clock=f.source.clock)
    assert len(attempted) == 1
    async with f.sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MemberNotification)
                .where(MemberNotification.league_id == f.league.id)
            )
            == 6
        )


@pytest.mark.parametrize("policy", ["global", "league", "results", "quiet"])
@pytest.mark.asyncio
async def test_result_notices_obey_existing_mute_and_quiet_policy(results, monkeypatch, policy):
    from src.models.league_membership import LeagueMembership

    f = results.fantasy
    await full_audience(f)
    await subscriptions(f, monkeypatch)
    async with f.sessions() as db, db.begin():
        values = dict(user_id=f.players[0].id)
        if policy == "global":
            values["global_mute"] = True
        elif policy == "results":
            values["mute_results"] = True
        elif policy == "quiet":
            values.update(
                quiet_hours_start=datetime(2000, 1, 1, 0), quiet_hours_end=datetime(2000, 1, 1, 6)
            )
        if policy == "league":
            await db.execute(
                update(LeagueMembership)
                .where(
                    LeagueMembership.league_id == f.league.id,
                    LeagueMembership.player_id == f.players[0].id,
                )
                .values(notification_muted=True)
            )
        else:
            db.add(NotificationPreferences(**values))
    sent_to = []

    async def fake(plan):
        sent_to.extend(push.subscription_id for push in plan.pushes)
        return PushDeliveryReport(
            tuple(PushDeliveryOutcome(push.subscription_id, "sent") for push in plan.pushes),
            plan.attempted_at,
        )

    monkeypatch.setattr(events, "deliver_prepared_notification", fake)
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    await events.deliver_events(f.sessions, clock=f.source.clock)
    async with f.sessions() as db:
        own = list(
            await db.scalars(
                select(MemberNotification).where(
                    MemberNotification.league_id == f.league.id,
                    MemberNotification.user_id == f.players[0].id,
                )
            )
        )
        own_sub = await db.scalar(
            select(PushSubscription.id).where(PushSubscription.user_id == f.players[0].id)
        )
        assert len(own) == (2 if policy == "quiet" else 0)
        assert own_sub not in sent_to
        assert len(sent_to) == 4


@pytest.mark.asyncio
async def test_suspension_stops_opening_reminder_but_retains_settlement_and_billing(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(TwoGameRollout)
            .where(TwoGameRollout.league_id == f.league.id)
            .values(suspended=True)
        )
    f.source.clock.now = london_utc(WEEK, 9)
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await bill_all(f.sessions, f.source.clock.now)
    await results.worker().run()
    async with f.sessions() as db:
        kinds = set(
            await db.scalars(select(TwoGameEvent.kind).where(TwoGameEvent.league_id == f.league.id))
        )
        assert not {"game_opened", "game_reminder"} & kinds
        assert "game_result" in kinds
        assert (await db.get(TwoGame, f.game.id)).status == "settled"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(WeeklyFeeObligation)
                .where(WeeklyFeeObligation.league_id == f.league.id)
            )
            == 6
        )


@pytest.mark.asyncio
async def test_lifecycle_facts_do_not_repeat_after_result_version_changes(results):
    f = results.fantasy
    await full_audience(f)
    assert (await f.save()).status_code == 200
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    f.source.clock.now = london_utc(WEEK, 18)
    await results.worker().run()
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await results.worker().run()
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    async with f.sessions() as db:
        facts = list(
            await db.scalars(
                select(TwoGameEvent).where(
                    TwoGameEvent.league_id == f.league.id,
                    TwoGameEvent.kind.in_(["game_opened", "game_locked"]),
                )
            )
        )
        assert len(facts) == 4 and all(row.version == 0 for row in facts)


@pytest.mark.asyncio
async def test_paused_settlement_allows_next_entry_and_fee_commits_and_records_latency(results):
    f = results.fantasy
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    results.pause = f.fixtures[0].provider_event_id
    task = asyncio.create_task(results.worker().run())
    try:
        await asyncio.wait_for(results.entered.wait(), 3)
        assert f.sessions.kw["bind"].pool.checkedout() == 0
        started = time.monotonic()
        saved = await asyncio.wait_for(entries.target_save(f, later), 3)
        elapsed = time.monotonic() - started
        assert saved.status_code == 200, saved.text
        async with f.sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(WeeklyFeeObligation)
                    .where(
                        WeeklyFeeObligation.league_id == f.league.id,
                        WeeklyFeeObligation.player_id == f.players[0].id,
                    )
                )
                == 2
            )
        print(f"paused_settlement_next_entry_and_fee_commit_seconds={elapsed:.6f}")
        assert not task.done()
        concurrent_entry = asyncio.create_task(entries.target_save(f, later, slot=2, fixture=1))
        result_started = time.monotonic()
        results.release.set()
        _, concurrent_saved = await asyncio.wait_for(asyncio.gather(task, concurrent_entry), 5)
        assert concurrent_saved.status_code == 200, concurrent_saved.text
        visible = await f.request("GET")
        assert visible.status_code == 200
        assert visible.json()["pick"]["result"] == "won"
        assert visible.json()["pick"]["points"] == 22
        print(
            "settlement_result_visible_with_concurrent_entry_seconds="
            f"{time.monotonic() - result_started:.6f}"
        )
    finally:
        results.release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert await results.spent() == 1


@pytest.mark.asyncio
async def test_cancelled_http_lease_and_spend_survive_and_suffix_finishes_first(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    assert (await f.save(slot=2, body=f.body(1))).status_code == 200
    f.source.clock.now = london_utc(WEEK, 18)
    await results.ordered([0, 1])
    results.pause = f.fixtures[0].provider_event_id
    task = asyncio.create_task(results.worker(units_per_pass=1).run())
    await asyncio.wait_for(results.entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await results.spent() == 1
    assert (await results.worker(units_per_pass=1).run())["resolved"] == 1
    async with f.sessions() as db:
        rows = list(
            await db.scalars(
                select(FantasyPick)
                .where(FantasyPick.week_id == f.parent.id)
                .order_by(FantasyPick.slot)
            )
        )
        assert [row.status for row in rows] == ["pending", "won"]
    f.source.clock.now += timedelta(seconds=46)
    results.release.set()
    await results.worker().run()
    assert await results.spent() == 3
    async with f.sessions() as db:
        assert (
            await db.scalar(
                select(func.sum(FantasyPick.points_awarded)).where(
                    FantasyPick.week_id == f.parent.id
                )
            )
            == 44
        )


@pytest.mark.asyncio
async def test_export_contains_only_requesters_new_records_and_group_is_unpriced(results):
    f = results.fantasy
    assert (await f.save()).status_code == 200
    assert (await f.save(player=1, body=f.body(1))).status_code == 200
    own_body = {key: value for key, value in f.body().items() if key != "odds"}
    other_body = {key: value for key, value in f.body(2).items() if key != "odds"}
    assert (
        await f.request("PUT", body=own_body, path=f.path.replace("fantasy", "group") + "/pick")
    ).status_code == 200
    assert (
        await f.request(
            "PUT", player=1, body=other_body, path=f.path.replace("fantasy", "group") + "/pick"
        )
    ).status_code == 200
    exported = await f.request("GET", path="/api/v1/me/export")
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert (
        len(body["fantasy_picks"])
        == len(body["group_picks"])
        == len(body["membership_intervals"])
        == len(body["weekly_fees"])
        == 1
    )
    assert len(body["game_operations"]) == 2
    assert not {"points", "odds", "frozen_odds", "bookmaker"} & body["group_picks"][0].keys()
    assert body["fantasy_picks"][0]["frozen_odds"] == "2.1500"
    text = json.dumps(body)
    assert (
        f.players[1].display_name not in text
        and str(f.fixtures[1].id) not in text
        and str(f.fixtures[2].id) not in text
    )
    assert "pin_hash" not in text and "body_hash" not in text


@pytest.mark.asyncio
async def test_http_erasure_releases_only_unlocked_games_and_retains_owed_history(
    results, monkeypatch
):
    from datetime import UTC

    from src.auth import hash_pin
    from src.models.league_membership import LeagueMemberRole, LeagueMembership
    from src.models.ledger import LedgerEntry, LedgerKind
    from src.models.profile import Profile
    from src.services import account_erasure

    f = results.fantasy
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    assert (await f.save()).status_code == 200
    f.source.clock.now = london_utc(WEEK, 12)
    assert (await entries.target_save(f, later)).status_code == 200
    body = {key: value for key, value in f.body().items() if key != "odds"}
    assert (
        await f.request("PUT", body=body, path=f.path.replace("fantasy", "group") + "/pick")
    ).status_code == 200
    f.source.clock.now = london_utc(WEEK, 13)

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = f.source.clock.now.replace(tzinfo=UTC)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(account_erasure, "datetime", ClockDateTime)
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(Profile).where(Profile.id == f.players[0].id).values(pin_hash=hash_pin("8351"))
        )
        await db.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == f.league.id,
                LeagueMembership.player_id == f.players[1].id,
            )
            .values(role=LeagueMemberRole.admin)
        )
        db.add(
            LedgerEntry(
                league_id=f.league.id,
                player_id=f.players[0].id,
                kind=LedgerKind.adjustment,
                amount_pence=-1000,
            )
        )
    response = await f.request("POST", path="/api/v1/me/delete", body=dict(pin="8351"))
    assert response.status_code == 204, response.text
    async with f.sessions() as db:
        member = await db.get(Profile, f.players[0].id)
        assert member.deleted_at is not None and not member.is_active
        assert f.players[0].display_name not in member.display_name and member.pin_hash is None
        kept = list(await db.scalars(select(FantasyPick).where(FantasyPick.player_id == member.id)))
        assert (
            len(kept) == 1
            and kept[0].week_id == f.parent.id
            and kept[0].frozen_odds == Decimal("2.1500")
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(GroupPick).where(GroupPick.player_id == member.id)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(WeeklyFeeObligation)
                .where(
                    WeeklyFeeObligation.league_id == f.league.id,
                    WeeklyFeeObligation.player_id == member.id,
                )
            )
            == 2
        )
        assert (
            await db.scalar(
                select(func.sum(LedgerEntry.amount_pence)).where(
                    LedgerEntry.league_id == f.league.id, LedgerEntry.player_id == member.id
                )
            )
            == -200
        )


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([], []),
        ([dict(player_id="a", entry_result="all_void", weekly_points=0)], []),
        (
            [
                dict(player_id="a", entry_result="no_entry", weekly_points=0),
                dict(player_id="b", entry_result="scored", weekly_points=0),
            ],
            ["b"],
        ),
        (
            [
                dict(player_id="a", entry_result="scored", weekly_points=0),
                dict(player_id="b", entry_result="scored", weekly_points=0),
            ],
            ["a", "b"],
        ),
        (
            [
                dict(player_id="a", entry_result="scored", weekly_points=44),
                dict(player_id="b", entry_result="scored", weekly_points=22),
            ],
            ["a"],
        ),
    ],
)
def test_weekly_winners_compare_entered_weekly_sums(members, expected):
    from src.services.two_game_results import weekly_winner_ids

    assert weekly_winner_ids(members) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["cancelled", "suspended", "deadline"])
async def test_queued_entry_notice_rechecks_cancel_suspension_and_deadline(
    results, monkeypatch, changed
):
    f = results.fantasy
    async with f.sessions() as db, db.begin():
        db.add(
            TwoGameEvent(
                league_id=f.league.id,
                week_id=f.parent.id,
                game_id=f.game.id,
                game_kind="fantasy",
                kind="game_opened",
                version=0,
                payload={},
            )
        )
        if changed == "cancelled":
            await db.execute(
                update(TwoGame).where(TwoGame.id == f.game.id).values(status="cancelled")
            )
        elif changed == "suspended":
            await db.execute(
                update(TwoGameRollout)
                .where(TwoGameRollout.league_id == f.league.id)
                .values(suspended=True)
            )
    if changed == "deadline":
        f.source.clock.now = london_utc(WEEK, 12)
    captured = []

    async def capture(db, intents):
        captured.extend(
            intent for intent in intents if intent.data.get("game_id") == str(f.game.id)
        )
        return []

    monkeypatch.setattr(events, "prepare_collected_notifications", capture)
    assert await events.deliver_events(f.sessions, clock=f.source.clock) == 1
    assert captured == []
    assert await events.deliver_events(f.sessions, clock=f.source.clock) == 0
