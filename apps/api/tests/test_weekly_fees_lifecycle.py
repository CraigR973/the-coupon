"""Real lifecycle barriers, delayed assignments, release and retained provenance."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token
from src.main import app
from src.models.fixture import Fixture
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry
from src.models.profile import Profile, UserRole
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    MembershipInterval,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
)
from src.payments_service.ingest import LinkPayment, Recorded, record_link_payment
from src.routers.leagues import _upsert_membership, notify_join_committed
from src.services.account_erasure import erase_account
from src.services.gameweek import release_unlocked_picks
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import (
    bill_all,
    financial_lock,
    materialize_dues,
    materialize_entry_fees,
    member_barrier,
    project_fees,
    track_join,
)
from tests import test_weekly_fees as fee_tests
from tests.test_weekly_fees import W0, W1, W2, W3, dues, fantasy, seed

db = fee_tests.db
committed = fee_tests.committed


@pytest.mark.asyncio
async def test_delayed_queued_fake_payment_counts_only_after_unchanged_assignment(committed):
    sessions, league, player, _, parent, _ = committed
    now = london_utc(W2, 12)
    async with sessions() as db, db.begin():
        await materialize_dues(db, league.id, player.id, now, through=W3, early=True)
        payment = LinkPayment(
            f"tx_{uuid.uuid4().hex}", league.monzo_link_id, 100, now, None, "Synthetic Card"
        )
        assert (
            await record_link_payment(db, payment, counting_since=london_utc(W0)) == Recorded.queued
        )
    async with sessions() as db:
        fee = (await project_fees(db, league, player.id, W3, now)).for_week(parent)
        assert fee.amount_owed_pence == 300
        entry = await db.scalar(
            select(LedgerEntry).where(LedgerEntry.monzo_transaction_id == payment.transaction_id)
        )
        entry_id = entry.id
    async with sessions() as db, db.begin():
        admin = Profile(
            display_name=f"Billing admin {uuid.uuid4().hex}", pin_hash="x", role=UserRole.admin
        )
        db.add(admin)
        await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(admin.id, admin.role)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        response = await client.post(
            f"/api/v1/leagues/{league.slug}/payments/{entry_id}/assign",
            headers=headers,
            json={"player_id": str(player.id)},
        )
        assert response.status_code == 200
    async with sessions() as db, db.begin():
        fee = (await project_fees(db, league, player.id, W3, now)).for_week(parent)
        assert fee.amount_owed_pence == 200
        assert [row.week_label for row in fee.obligations] == [W2, W3]
        assert (
            await record_link_payment(db, payment, counting_since=london_utc(W0))
            == Recorded.duplicate
        )
        admin = await db.get(Profile, admin.id)
        admin.deleted_at = now
        admin.is_active = False


@pytest.mark.asyncio
async def test_delete_barrier_refuses_join_promptly_even_with_league_lock(committed):
    sessions, league, player, _, _, _ = committed
    async with sessions() as deleting, deleting.begin():
        await member_barrier(deleting, player.id, deleting=True)

        async def try_join():
            async with sessions() as joining, joining.begin():
                await financial_lock(joining, league.id)
                await _upsert_membership(league.id, player.id, joining)

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(try_join(), timeout=2)
        assert exc.value.status_code == 409 and exc.value.detail == "MEMBERSHIP_CHANGING"


@pytest.mark.asyncio
async def test_existing_shared_join_finishes_before_exclusive_deletion_collects(committed):
    sessions, league, player, _, _, _ = committed
    entered, acquired = asyncio.Event(), asyncio.Event()

    async def deleting():
        async with sessions() as db, db.begin():
            entered.set()
            await member_barrier(db, player.id, deleting=True)
            acquired.set()
            intervals = list(
                await db.scalars(
                    select(MembershipInterval).where(MembershipInterval.player_id == player.id)
                )
            )
            return len(intervals)

    async with sessions() as joining, joining.begin():
        assert await member_barrier(joining, player.id)
        member = await joining.scalar(
            select(LeagueMembership).where(LeagueMembership.league_id == league.id)
        )
        await track_join(joining, member)
        task = asyncio.create_task(deleting())
        await entered.wait()
        assert not acquired.is_set()
    assert await asyncio.wait_for(task, timeout=2) == 1
    assert acquired.is_set()


@pytest.mark.asyncio
async def test_avatar_pause_join_to_new_league_is_collected_and_closed(committed, monkeypatch):
    sessions, league, player, _, _, _ = committed
    avatar_entered, avatar_release = asyncio.Event(), asyncio.Event()
    storage = AsyncMock()

    async def delete_avatar(**kwargs):
        avatar_entered.set()
        await avatar_release.wait()

    storage.delete.side_effect = delete_avatar

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, 11, tzinfo=UTC)

    monkeypatch.setattr("src.services.account_erasure.datetime", Clock)
    monkeypatch.setattr("src.routers.leagues._now", lambda: datetime(2026, 11, 20, 10))
    async with sessions() as db, db.begin():
        stored = await db.get(Profile, player.id)
        stored.avatar_url = "/synthetic-avatar"
        other = League(
            slug=f"billing-{uuid.uuid4().hex}",
            name="Synthetic joined during avatar",
            created_by=player.id,
        )
        db.add(other)
        await db.flush()
        db.add(
            TwoGameRollout(
                league_id=other.id,
                first_week=W1,
                enabled=True,
                effective_opening=london_utc(W0, 12),
            )
        )

    async def erase():
        async with sessions() as db, db.begin():
            stored = await db.get(Profile, player.id)
            await erase_account(db, stored, storage)

    task = asyncio.create_task(erase())
    try:
        await avatar_entered.wait()
        async with sessions() as db, db.begin():
            await _upsert_membership(other.id, player.id, db)
        avatar_release.set()
        await asyncio.wait_for(task, timeout=5)
        async with sessions() as db, db.begin():
            stored = await db.get(Profile, player.id)
            intervals = list(
                await db.scalars(
                    select(MembershipInterval).where(MembershipInterval.player_id == player.id)
                )
            )
            assert {row.league_id for row in intervals} == {league.id, other.id}
            assert all(
                row.left_at == stored.deleted_at == datetime(2026, 11, 20, 11) for row in intervals
            )
            assert [row.week_label for row in await dues(db, other, player)] == [W1]
            rollout = await db.get(TwoGameRollout, other.id)
            rollout.enabled = False
            other = await db.get(League, other.id)
            other.deleted_at = stored.deleted_at
    finally:
        avatar_release.set()
        if not task.done():
            await task


@pytest.mark.asyncio
async def test_join_notification_holds_no_member_or_financial_lock(committed, monkeypatch):
    sessions, league, player, _, _, _ = committed

    async def delivery(db, *args):
        async with sessions() as observer, observer.begin():
            assert await member_barrier(observer, player.id, deleting=True)
            assert await financial_lock(observer, league.id)

    monkeypatch.setattr("src.routers.leagues.notify_member_joined", delivery)
    async with sessions() as db:
        await member_barrier(db, player.id)
        await financial_lock(db, league.id)
        await asyncio.wait_for(notify_join_committed(db, player, league), timeout=2)


@pytest.mark.asyncio
async def test_departure_between_locks_keeps_fantasy_frees_group_and_retains_revision(
    db, monkeypatch
):
    league, player, _ = await seed(db, monkeypatch)
    parent, fantasy_game = await fantasy(db, league, W1)
    group_game = TwoGame(
        league_id=league.id,
        week_id=parent.id,
        kind="group",
        opens_at=london_utc(W1 - timedelta(days=1)),
        locks_at=london_utc(W1, 14, 30),
        window_start=london_utc(W1, 15),
        window_end=london_utc(W1, 15),
    )
    fixture = Fixture(
        provider_event_id=f"billing-{uuid.uuid4().hex}",
        home="Home",
        away="Away",
        kickoff_utc=london_utc(W1, 15),
        competition="Premier League",
        competition_id="england-premier-league",
    )
    db.add_all([group_game, fixture])
    await db.flush()
    db.add_all(
        TwoGameFixture(game_id=game.id, fixture_id=fixture.id)
        for game in (group_game, fantasy_game)
    )
    await db.flush()
    common = dict(
        league_id=league.id,
        week_id=parent.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market="MATCH_ODDS",
        outcome="HOME",
        runner_name="Home",
    )
    group_pick = GroupPick(**common, game_id=group_game.id, revision=3, operation_id=uuid.uuid4())
    fantasy_pick = FantasyPick(
        **common,
        game_id=fantasy_game.id,
        slot=1,
        revision=2,
        operation_id=uuid.uuid4(),
        frozen_odds=Decimal("2.15"),
        quoted_at=london_utc(W0, 12),
        provider="fake",
        bookmaker="synthetic",
    )
    db.add_all([group_pick, fantasy_pick])
    await db.flush()
    await materialize_dues(db, league.id, player.id, london_utc(W1, 13))
    owed = [(row.id, row.ledger_entry_id) for row in await dues(db, league, player)]
    assert await release_unlocked_picks(db, player.id, [league.id], now=london_utc(W1, 13)) == 1
    await db.flush()
    assert await db.get(GroupPick, group_pick.id) is None
    assert await db.get(FantasyPick, fantasy_pick.id) is fantasy_pick
    operation = await db.scalar(select(GameOperation).where(GameOperation.game_id == group_game.id))
    assert operation.response["pick"] is None and operation.response["revision"] == 4
    assert operation.slot == 0
    assert [(row.id, row.ledger_entry_id) for row in await dues(db, league, player)] == owed
    assert await release_unlocked_picks(db, player.id, [league.id], now=london_utc(W1, 13)) == 0


@pytest.mark.parametrize("name", ["Weekly", "Fee"])
@pytest.mark.asyncio
async def test_erasure_of_name_matching_generated_dues_preserves_immutable_money(
    db, monkeypatch, name
):
    league, player, _ = await seed(db, monkeypatch)
    player.display_name = name
    await db.flush()
    await materialize_dues(db, league.id, player.id, london_utc(W1))
    original = [(row.id, row.ledger_entry_id) for row in await dues(db, league, player)]

    # Erasure departs at its own clock and bills the departure week. Pin that clock
    # inside W1's already-billed week, as the avatar-race test above does, so the
    # check stays about immutable money rather than about today's date: on the real
    # clock it went red at Monday 23 Nov 00:00 London, when W2's week began.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, 11, tzinfo=UTC)

    monkeypatch.setattr("src.services.account_erasure.datetime", Clock)
    await erase_account(db, player, AsyncMock())
    await db.flush()
    assert player.deleted_at is not None and not player.is_active
    assert [(row.id, row.ledger_entry_id) for row in await dues(db, league, player)] == original


@pytest.mark.asyncio
async def test_failed_league_rolls_back_without_starving_other_billing(committed, monkeypatch):
    sessions, league, player, _, _, _ = committed
    async with sessions() as db, db.begin():
        other, other_player, _ = await seed(db, monkeypatch)
    original = materialize_dues

    async def broken(db, league_id, player_id, moment, **kwargs):
        count = await original(db, league_id, player_id, moment, **kwargs)
        if league_id == league.id:
            raise RuntimeError("synthetic failure after uncommitted due")
        return count

    monkeypatch.setattr("src.services.weekly_fees.materialize_dues", broken)
    try:
        with pytest.raises(ExceptionGroup) as failure:
            await bill_all(sessions, london_utc(W1))
        assert len(failure.value.exceptions) == 1
        async with sessions() as db:
            assert await dues(db, league, player) == []
            assert [row.week_label for row in await dues(db, other, other_player)] == [W1]
        monkeypatch.setattr("src.services.weekly_fees.materialize_dues", original)
        assert await bill_all(sessions, london_utc(W1)) == 1
        async with sessions() as db:
            assert (
                len(await dues(db, league, player)) == len(await dues(db, other, other_player)) == 1
            )
    finally:
        async with sessions() as db, db.begin():
            rollout = await db.get(TwoGameRollout, other.id)
            rollout.enabled = False
            stored = await db.get(League, other.id)
            stored.deleted_at = london_utc(W2)
            profile = await db.get(Profile, other_player.id)
            profile.deleted_at = london_utc(W2)
            profile.is_active = False


@pytest.mark.asyncio
async def test_new_current_group_paid_and_next_fantasy_unpaid_have_independent_entitlement(
    committed,
):
    sessions, league, player, _, _, _ = committed
    from src.models.ledger import LedgerKind
    from src.services.two_game_storage import ensure_two_game_week

    now = london_utc(W1, 12)
    async with sessions() as db, db.begin():
        current = await ensure_two_game_week(db, league.id, W1)
        group = TwoGame(
            league_id=league.id,
            week_id=current.id,
            kind="group",
            opens_at=london_utc(W1 - timedelta(days=1)),
            locks_at=london_utc(W1, 14, 30),
            window_start=london_utc(W1, 15),
            window_end=london_utc(W1, 15),
        )
        db.add(group)
        next_parent, next_game = await fantasy(db, league, W2)
        db.add(
            LedgerEntry(
                league_id=league.id, player_id=player.id, kind=LedgerKind.payment, amount_pence=100
            )
        )
        await db.flush()

    async def admission(parent, game):
        return await materialize_entry_fees(
            sessions,
            league_id=league.id,
            week_id=parent.id,
            game_id=game.id,
            game_kind=game.kind,
            player_id=player.id,
            now=now,
        )

    assert (await admission(current, group)).paid_through
    for _ in range(6):
        fee = await admission(next_parent, next_game)
        assert fee.amount_owed_pence == 100 and not fee.paid_through
    assert (await admission(current, group)).paid_through
    async with sessions() as db, db.begin():
        assert [row.week_label for row in await dues(db, league, player)] == [W1, W2]
        db.add(
            LedgerEntry(
                league_id=league.id, player_id=player.id, kind=LedgerKind.payment, amount_pence=100
            )
        )
    assert (await admission(next_parent, next_game)).paid_through
    async with sessions() as db, db.begin():
        assert await materialize_dues(db, league.id, player.id, london_utc(W2)) == 0
        assert len(await dues(db, league, player)) == 2
