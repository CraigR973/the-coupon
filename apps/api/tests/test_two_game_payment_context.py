"""Receipt claims use actual queued assignment, stored targets and pooled credit."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from src.models.ledger import LedgerEntry, LedgerKind
from src.models.notification import MemberNotification, NotificationSend
from src.models.profile import Profile, UserRole
from src.models.two_game import GameOperation, TwoGameRollout, WeeklyFeeObligation
from src.routers import payments
from src.services.payment_notices import PAYMENT_RECORDED, prepare_payment_notices
from src.services.two_game_payment_context import payment_game_context
from src.services.two_game_storage import london_utc
from tests import test_two_game_fantasy as entries
from tests import test_two_game_reads as reads
from tests import two_game_test_store as stores

baseline_db_engine = stores.baseline_db_engine
result_store = stores.result_store
db_engine = stores.db_engine
fantasy = entries.fantasy
games = reads.games
WEEK = entries.WEEK


async def queued_assignment(f, monkeypatch, *, amount=100):
    f.source.clock.now = london_utc(WEEK, 12, 5)
    monkeypatch.setattr(payments, "_now", f.source.clock)
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(LedgerEntry)
            .where(
                LedgerEntry.league_id == f.league.id,
                LedgerEntry.player_id == f.players[0].id,
                LedgerEntry.kind == LedgerKind.payment,
            )
            .values(amount_pence=1)
        )
        # One penny already present +99p newly assigned clears the current £1 only.
        admin = await db.get(Profile, f.players[0].id)
        admin.role = UserRole.admin
        f.players[0].role = UserRole.admin
        payment = LedgerEntry(
            league_id=f.league.id,
            player_id=None,
            kind=LedgerKind.payment,
            amount_pence=amount,
            monzo_transaction_id=f"synthetic-{uuid.uuid4().hex}",
            payer_name="Private synthetic payer",
            created_at=f.source.clock.now - timedelta(days=10),
        )
        db.add(payment)
    response = await f.request(
        "POST",
        path=f"/api/v1/leagues/{f.league.slug}/payments/{payment.id}/assign",
        body={"player_id": str(f.players[0].id)},
    )
    assert response.status_code == 200, response.text
    return payment


async def notices(f):
    async with f.sessions() as db, db.begin():
        return await prepare_payment_notices(db, f.source.clock.now)


@pytest.mark.asyncio
async def test_delayed_actual_http_assignment_one_receipt_names_independent_entitlements(
    games, monkeypatch
):
    f = games
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    payment = await queued_assignment(f, monkeypatch, amount=99)
    first, second = await asyncio.gather(notices(f), notices(f))
    assert first.targeted + second.targeted == 1
    assert (await notices(f)).targeted == 0
    async with f.sessions() as db:
        inbox = list(
            await db.scalars(
                select(MemberNotification).where(MemberNotification.league_id == f.league.id)
            )
        )
        assert len(inbox) == 1
        assert "Group for 21 Nov: paid." in inbox[0].body
        assert "Fantasy for 28 Nov: £1 owed before entry." in inbox[0].body
        assert inbox[0].url == f"/leagues/{f.league.id}/weeks/{later[1].id}/fantasy#payment"
        assert "Private synthetic payer" not in inbox[0].body
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationSend)
                .where(
                    NotificationSend.kind == PAYMENT_RECORDED,
                    NotificationSend.subject == str(payment.id),
                )
            )
            == 1
        )
        stored = await db.get(LedgerEntry, payment.id)
        assert stored.gameweek_id is None and stored.player_id == f.players[0].id
        context = await payment_game_context(
            db, f.league, f.players[0].id, f.source.clock.now, two_games_enabled=True
        )
        assert {target["game_kind"] for target in context.targets} == {"group", "fantasy"}
        assert next(target for target in context.targets if target["game_id"] == str(f.group.id))[
            "paid_through"
        ]
        assert not next(
            target for target in context.targets if target["game_id"] == str(later[2].id)
        )["paid_through"]
    assert await f.count(WeeklyFeeObligation) == await f.count(GameOperation) == 0
    assert f.source.calls == f.acquisitions == []
    async with f.sessions() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=f.league.id,
                player_id=f.players[0].id,
                kind=LedgerKind.payment,
                amount_pence=100,
            )
        )
    view = await reads.home(f)
    assert all(card["fee"]["paid_through"] for card in view["games"])


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["suspended", "not_open", "left"])
async def test_receipt_known_target_stays_addressed_when_entry_unavailable(games, state):
    from src.models.league_membership import LeagueMembership

    f = games
    if state == "not_open":
        f.source.clock.now = london_utc(WEEK - timedelta(days=7), 11)
    else:
        assert (await f.save()).status_code == 200
        async with f.sessions() as db, db.begin():
            if state == "suspended":
                rollout = await db.get(TwoGameRollout, f.league.id)
                rollout.suspended = True
            else:
                f.source.clock.now = london_utc(WEEK, 12, 5)
                member = await db.scalar(
                    select(LeagueMembership).where(
                        LeagueMembership.league_id == f.league.id,
                        LeagueMembership.player_id == f.players[0].id,
                    )
                )
                member.deleted_at = f.source.clock.now
    async with f.sessions() as db:
        context = await payment_game_context(
            db, f.league, f.players[0].id, f.source.clock.now, two_games_enabled=True
        )
        assert "No entry is open." in context.standing
        assert context.targets and context.destination.startswith(f"/leagues/{f.league.id}/weeks/")
        assert context.destination.endswith("#payment")
    if state == "left":
        response = await f.request("GET", path=f"/api/v1/leagues/{f.league.id}/games")
        assert response.status_code == 200, response.text
        assert any(
            card["game_id"] == str(f.game.id) and card["archived"]
            for card in response.json()["games"]
        )
    assert f.source.calls == [] if state == "not_open" else len(f.source.calls) == 1


@pytest.mark.asyncio
async def test_deleted_enabled_league_cannot_starve_healthy_receipt(games):
    from src.models.league import League

    f = games
    other = await entries.additional_week(f, WEEK, another_league=True)
    f.source.clock.now = london_utc(WEEK, 12, 5)
    async with f.sessions() as db, db.begin():
        for league in [f.league, other[0]]:
            db.add(
                LedgerEntry(
                    league_id=league.id,
                    player_id=f.players[0].id,
                    kind=LedgerKind.payment,
                    amount_pence=100,
                    monzo_transaction_id=f"synthetic-{uuid.uuid4().hex}",
                    created_at=f.source.clock.now,
                )
            )
        await db.execute(
            update(League).where(League.id == f.league.id).values(deleted_at=f.source.clock.now)
        )
    assert (await notices(f)).targeted == 2
    async with f.sessions() as db:
        inbox = list(
            await db.scalars(
                select(MemberNotification).where(MemberNotification.user_id == f.players[0].id)
            )
        )
        assert {notification.league_id for notification in inbox} == {f.league.id, other[0].id}
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
async def test_mixed_legacy_and_new_receipt_context_keeps_both_exact_targets(games, monkeypatch):
    f = games
    old, _ = await reads.legacy_before_cutover(f, monkeypatch)
    f.source.clock.now = london_utc(old.starts_on, 12, 5)
    async with f.sessions() as db:
        context = await payment_game_context(
            db, f.league, f.players[0].id, f.source.clock.now, two_games_enabled=True
        )
        assert "Legacy round for 14 Nov: paid." in context.standing
        assert "Fantasy for 21 Nov: paid." in context.standing
        assert {target["week_id"] for target in context.targets} == {str(old.id), str(f.parent.id)}
        legacy = next(target for target in context.targets if target["game_kind"] == "legacy")
        assert legacy["destination"] == f"/leagues/{f.league.slug}/predictions?gw={old.id}#coupon"
        assert "game_id" not in legacy
    assert await f.count(WeeklyFeeObligation) == 0 and f.source.calls == []


@pytest.mark.asyncio
async def test_billing_only_parent_without_children_is_not_an_invented_game_or_pick_promise(games):
    from src.models.league import League
    from src.models.league_membership import LeagueMembership
    from src.models.two_game import ProviderAttempt, ProviderWork, TwoGame
    from src.services.two_game_storage import ensure_two_game_week

    f = games
    async with f.sessions() as db, db.begin():
        league = League(
            slug=f"billing-{uuid.uuid4().hex}", name="Billing only", created_by=f.players[0].id
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
        db.add(
            LeagueMembership(
                league_id=league.id,
                player_id=f.players[0].id,
                joined_at=london_utc(WEEK - timedelta(days=5)),
            )
        )
        await db.flush()
        parent = await ensure_two_game_week(db, league.id, WEEK)
    response = await f.request("GET", path=f"/api/v1/leagues/{league.id}/games")
    assert response.status_code == 200, response.text
    assert response.json()["games"] == response.json()["legacy_rounds"] == []
    assert response.json()["next_game_state"] == "pending"
    async with f.sessions() as db:
        context = await payment_game_context(
            db, league, f.players[0].id, f.source.clock.now, two_games_enabled=True
        )
        assert context.targets == []
        assert context.standing == "No entry is open. Weekly fees still apply."
        assert context.destination == f"/leagues/{league.slug}/predictions"
        assert not list(await db.scalars(select(TwoGame).where(TwoGame.week_id == parent.id)))
        assert not list(
            await db.scalars(
                select(WeeklyFeeObligation).where(WeeklyFeeObligation.league_id == league.id)
            )
        )
        assert not list(await db.scalars(select(ProviderWork)))
    assert await f.count(ProviderAttempt) == 0 and f.acquisitions == f.source.calls == []
