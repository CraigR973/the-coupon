"""F1-F6 monetary oracles: London weeks, independent commits and pooled money."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth import create_access_token
from src.config import settings
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.models.profile import Profile
from src.models.two_game import (
    ConfirmedBreak,
    FantasyPick,
    MembershipInterval,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.payments_service.ingest import LinkPayment, Recorded, record_link_payment
from src.routers.leagues import _upsert_membership
from src.services.dues import payment_required
from src.services.two_game_schedule import prepare_calendar
from src.services.two_game_storage import ensure_two_game_week, london_utc
from src.services.weekly_fees import (
    EntryFeeRefused,
    bill_all,
    billing_bounds,
    billing_label,
    close_memberships,
    financial_lock,
    materialize_dues,
    materialize_entry_fees,
    project_fees,
    track_join,
)

W0 = date(2026, 11, 14)
W1 = date(2026, 11, 21)
W2 = date(2026, 11, 28)
W3 = date(2026, 12, 5)


@pytest_asyncio.fixture
async def db(db_conn) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(
        bind=db_conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as session:
        yield session


async def seed(db, monkeypatch, *, joined=None, first=W1):
    monkeypatch.setattr(settings, "two_games_enabled", True)
    player = Profile(display_name=f"Billing {uuid.uuid4().hex}", pin_hash="x")
    db.add(player)
    await db.flush()
    league = League(
        slug=f"billing-{uuid.uuid4().hex}",
        name="Synthetic billing",
        created_by=player.id,
        entry_fee_pence=None,
        monzo_link_id=f"unipaylink_{uuid.uuid4().hex}",
        payment_link_url="https://synthetic.invalid/pay",
    )
    db.add(league)
    await db.flush()
    member = LeagueMembership(
        league_id=league.id,
        player_id=player.id,
        joined_at=joined or london_utc(W0 - timedelta(days=5)),
    )
    db.add(member)
    db.add(
        TwoGameRollout(
            league_id=league.id,
            first_week=first,
            enabled=True,
            effective_opening=london_utc(first - timedelta(days=7), 12),
        )
    )
    await db.flush()
    return league, player, member


async def dues(db, league, player):
    return list(
        await db.scalars(
            select(WeeklyFeeObligation)
            .where(
                WeeklyFeeObligation.league_id == league.id,
                WeeklyFeeObligation.player_id == player.id,
            )
            .order_by(WeeklyFeeObligation.week_label)
        )
    )


async def fantasy(db, league, label):
    parent = await ensure_two_game_week(db, league.id, label)
    assert parent is not None
    game = TwoGame(
        league_id=league.id,
        week_id=parent.id,
        kind="fantasy",
        opens_at=london_utc(label - timedelta(days=7), 12),
        locks_at=london_utc(label, 12),
        window_start=london_utc(label, 12, 30),
        window_end=london_utc(label + timedelta(days=2)),
    )
    db.add(game)
    await db.flush()
    return parent, game


@pytest.mark.parametrize(
    ("joined", "labels"),
    [
        (datetime(2026, 11, 20, 10), [W1, W2]),
        (datetime(2026, 11, 22, 23, 59, 59, 999000), [W1, W2]),
        (datetime(2026, 11, 23), [W2]),
        (datetime(2026, 11, 23, 0, 0, 0, 1000), [W2]),
    ],
)
@pytest.mark.asyncio
async def test_f1_join_and_delayed_monday_catchup(db, monkeypatch, joined, labels):
    league, player, _ = await seed(db, monkeypatch, joined=joined, first=W0)
    assert await materialize_dues(db, league.id, player.id, datetime(2026, 11, 24)) == len(labels)
    assert await materialize_dues(db, league.id, player.id, datetime(2026, 11, 24)) == 0
    rows = await dues(db, league, player)
    assert [row.week_label for row in rows] == labels
    assert all(row.owed_at == max(billing_bounds(row.week_label)[0], joined) for row in rows)
    assert await db.scalar(
        select(func.sum(LedgerEntry.amount_pence)).where(LedgerEntry.player_id == player.id)
    ) == -100 * len(labels)


@pytest.mark.parametrize(
    ("label", "hours"),
    [
        (date(2027, 3, 27), 167),
        (date(2027, 10, 30), 169),
        (W1, 168),
    ],
)
def test_billing_calendar_uses_london_not_fixed_duration(label, hours):
    start, end = billing_bounds(label)
    assert (end - start).total_seconds() == hours * 3600
    assert billing_label(start) == label
    assert billing_label(end - timedelta(microseconds=1)) == label
    assert billing_label(end) == label + timedelta(days=7)


@pytest.mark.asyncio
async def test_f2_departure_exclusive_at_monday_and_no_future_clock_charge(db, monkeypatch):
    league, player, member = await seed(db, monkeypatch)
    boundary = billing_bounds(W2)[0]
    assert await close_memberships(db, [league.id], boundary, player_id=player.id) == 1
    member.deleted_at = boundary
    await db.flush()
    assert await materialize_dues(db, league.id, player.id, boundary + timedelta(days=9)) == 0
    assert [row.week_label for row in await dues(db, league, player)] == [W1]


@pytest.mark.asyncio
async def test_f2_zero_length_interval_never_creates_due(db, monkeypatch):
    boundary = billing_bounds(W2)[0]
    league, player, _ = await seed(db, monkeypatch, joined=boundary)
    assert await close_memberships(db, [league.id], boundary, player_id=player.id) == 1
    assert await dues(db, league, player) == []


@pytest.mark.asyncio
async def test_f2_same_week_rejoin_retains_original_due_and_interval(db, monkeypatch):
    league, player, member = await seed(db, monkeypatch)
    left = datetime(2026, 11, 18, 10)
    await close_memberships(db, [league.id], left, player_id=player.id)
    member.deleted_at = left
    await db.flush()
    original = (await dues(db, league, player))[0]
    monkeypatch.setattr("src.routers.leagues._now", lambda: datetime(2026, 11, 20, 10))
    rejoined = await _upsert_membership(league.id, player.id, db)
    assert rejoined.id == member.id and rejoined.joined_at == datetime(2026, 11, 20, 10)
    assert [row.id for row in await dues(db, league, player)] == [original.id]
    assert (
        len(
            list(
                await db.scalars(
                    select(MembershipInterval).where(MembershipInterval.player_id == player.id)
                )
            )
        )
        == 2
    )
    # Repeated active admission cannot reset history or role.
    await _upsert_membership(league.id, player.id, db)
    assert member.joined_at == datetime(2026, 11, 20, 10)
    assert len(await dues(db, league, player)) == 1


@pytest.mark.asyncio
async def test_f2_early_future_obligation_survives_departure_before_billing_start(db, monkeypatch):
    league, player, member = await seed(db, monkeypatch)
    early = london_utc(W0, 12)
    assert await materialize_dues(db, league.id, player.id, early, through=W3, early=True) == 3
    original = [(row.id, row.interval_id, row.owed_at) for row in await dues(db, league, player)]
    await close_memberships(db, [league.id], early + timedelta(hours=1), player_id=player.id)
    member.deleted_at = early + timedelta(hours=1)
    await db.flush()
    assert await materialize_dues(db, league.id, player.id, datetime(2026, 12, 10)) == 0
    assert [
        (row.id, row.interval_id, row.owed_at) for row in await dues(db, league, player)
    ] == original
    assert all(owed == early for _, _, owed in original)


@pytest.mark.asyncio
async def test_f3_f4_legacy_paid_current_and_unpaid_next_preserve_ledger(db, monkeypatch):
    league, player, _ = await seed(db, monkeypatch)
    league.entry_fee_pence = 100
    old = Gameweek(
        league_id=league.id,
        starts_on=W0,
        status=GameweekStatus.open,
        locks_at_utc=london_utc(W0, 14, 30),
        picks_open_at_utc=london_utc(W0 - timedelta(days=1)),
    )
    db.add(old)
    await db.flush()
    entries = [
        LedgerEntry(
            league_id=league.id,
            player_id=player.id,
            gameweek_id=old.id,
            kind=LedgerKind.round_due,
            amount_pence=-100,
        ),
        LedgerEntry(
            league_id=league.id, player_id=player.id, kind=LedgerKind.payment, amount_pence=100
        ),
    ]
    db.add_all(entries)
    await db.flush()
    fingerprint = [(row.id, row.kind, row.amount_pence, row.gameweek_id) for row in entries]
    next_week, _ = await fantasy(db, league, W1)
    assert await payment_required(db, league, old, player.id) is False
    projected = (await project_fees(db, league, player.id, W1, london_utc(W0, 12))).for_week(
        next_week
    )
    assert projected.amount_owed_pence == projected.obligation_pence == 100
    assert not projected.paid_through and await dues(db, league, player) == []
    for _ in range(8):
        await materialize_dues(db, league.id, player.id, london_utc(W0, 12), through=W1, early=True)
    await materialize_dues(db, league.id, player.id, london_utc(W1))
    assert len(await dues(db, league, player)) == 1
    assert await payment_required(db, league, old, player.id) is False
    assert [(row.id, row.kind, row.amount_pence, row.gameweek_id) for row in entries] == fingerprint
    assert old.format == "legacy"


@pytest.mark.asyncio
async def test_f5_read_projects_three_empty_weeks_without_writing_and_fifo_clears_oldest(
    db, monkeypatch
):
    league, player, _ = await seed(db, monkeypatch)
    parent, _ = await fantasy(db, league, W3)
    now = london_utc(W3 - timedelta(days=7), 12)
    fee = (await project_fees(db, league, player.id, W3, now)).for_week(parent)
    assert fee.amount_owed_pence == 300 and fee.pooled_credit_pence == 0
    assert [row.week_label for row in fee.obligations] == [W1, W2, W3]
    assert await dues(db, league, player) == []
    assert await materialize_dues(db, league.id, player.id, now, through=W3, early=True) == 3
    db.add(
        LedgerEntry(
            league_id=league.id, player_id=player.id, kind=LedgerKind.payment, amount_pence=100
        )
    )
    await db.flush()
    fee = (await project_fees(db, league, player.id, W3, now)).for_week(parent)
    assert fee.amount_owed_pence == 200
    assert [row.week_label for row in fee.obligations] == [W2, W3]
    db.add(
        LedgerEntry(
            league_id=league.id, player_id=player.id, kind=LedgerKind.payment, amount_pence=250
        )
    )
    await db.flush()
    fee = (await project_fees(db, league, player.id, W3, now)).for_week(parent)
    assert fee.paid_through and fee.amount_owed_pence == 0 and fee.pooled_credit_pence == 50


@pytest.mark.parametrize(
    "state", ["no_entry", "partial", "all_void", "cancelled", "break", "suspended"]
)
@pytest.mark.asyncio
async def test_every_week_owes_without_discovery_entries_or_result(db, monkeypatch, state):
    league, player, _ = await seed(db, monkeypatch)
    if state in {"all_void", "cancelled", "partial"}:
        parent, game = await fantasy(db, league, W1)
        game.result_status = "void" if state == "all_void" else "pending"
        if state == "cancelled":
            game.status = "cancelled"
        else:
            fixture = Fixture(
                provider_event_id=f"billing-{uuid.uuid4().hex}",
                home="Home",
                away="Away",
                kickoff_utc=london_utc(W1, 15),
                competition="Premier League",
                competition_id="england-premier-league",
            )
            db.add(fixture)
            await db.flush()
            db.add(TwoGameFixture(game_id=game.id, fixture_id=fixture.id))
            await db.flush()
            db.add(
                FantasyPick(
                    league_id=league.id,
                    week_id=parent.id,
                    game_id=game.id,
                    fixture_id=fixture.id,
                    player_id=player.id,
                    slot=1,
                    market="MATCH_ODDS",
                    outcome="HOME",
                    runner_name="Home",
                    operation_id=uuid.uuid4(),
                    frozen_odds=Decimal("2.15"),
                    quoted_at=london_utc(W0, 12),
                    provider="fake",
                    bookmaker="synthetic",
                    status="void" if state == "all_void" else "pending",
                    points_awarded=0 if state == "all_void" else None,
                )
            )
    if state == "break":
        db.add(
            ConfirmedBreak(
                league_id=league.id,
                week_label=W1,
                confirmed_by=player.id,
                evidence="Synthetic explicit break evidence, never inferred from empty data",
            )
        )
    if state == "suspended":
        rollout = await db.get(TwoGameRollout, league.id)
        rollout.suspended = True
    await db.flush()
    assert await materialize_dues(db, league.id, player.id, london_utc(W2)) == 2
    assert await materialize_dues(db, league.id, player.id, london_utc(W2)) == 0
    assert [row.week_label for row in await dues(db, league, player)] == [W1, W2]
    assert (
        await db.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.player_id == player.id, LedgerEntry.kind == LedgerKind.due_reversal)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_inactive_creates_no_intervals_or_money_but_retained_closure_is_recorded(
    db, monkeypatch
):
    league, player, _ = await seed(db, monkeypatch)
    monkeypatch.setattr(settings, "two_games_enabled", False)
    assert await materialize_dues(db, league.id, player.id, london_utc(W1)) == 0
    assert not await financial_lock(db, league.id)
    monkeypatch.setattr(settings, "two_games_enabled", True)
    await track_join(
        db, await db.scalar(select(LeagueMembership).where(LeagueMembership.league_id == league.id))
    )
    monkeypatch.setattr(settings, "two_games_enabled", False)
    assert await close_memberships(db, [league.id], london_utc(W1), player_id=player.id) == 1
    assert await dues(db, league, player) == []


@pytest.mark.asyncio
async def test_negative_adjustment_cannot_disappear_from_paid_through(db, monkeypatch):
    league, player, _ = await seed(db, monkeypatch)
    week, _ = await fantasy(db, league, W1)
    db.add(
        LedgerEntry(
            league_id=league.id, player_id=player.id, kind=LedgerKind.adjustment, amount_pence=-50
        )
    )
    await db.flush()
    fee = (await project_fees(db, league, player.id, W1, london_utc(W0, 12))).for_week(week)
    assert fee.amount_owed_pence == 150 and not fee.paid_through


@pytest_asyncio.fixture
async def committed(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as db, db.begin():
        league, player, member = await seed(db, monkeypatch)
        parent, game = await fantasy(db, league, W3)
    try:
        yield sessions, league, player, member, parent, game
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
                .where(Profile.id == player.id)
                .values(deleted_at=datetime(2026, 12, 20), is_active=False)
            )


@pytest.mark.asyncio
async def test_early_attempt_commits_all_intervening_dues_even_when_unpaid(committed):
    sessions, league, player, _, parent, game = committed
    fee = await materialize_entry_fees(
        sessions,
        league_id=league.id,
        week_id=parent.id,
        game_id=game.id,
        game_kind="fantasy",
        player_id=player.id,
        now=london_utc(W2, 12),
    )
    assert fee.amount_owed_pence == 300
    async with sessions() as db:
        assert [row.week_label for row in await dues(db, league, player)] == [W1, W2, W3]
    # Later business failure is outside the financial commit.
    async with sessions() as db, db.begin():
        db.add(
            LedgerEntry(
                league_id=league.id, player_id=player.id, kind=LedgerKind.adjustment, amount_pence=1
            )
        )
        await db.rollback()
    async with sessions() as db:
        assert len(await dues(db, league, player)) == 3


@pytest.mark.asyncio
async def test_f6_real_concurrent_cron_join_early_and_duplicate_delayed_fake_payment(
    committed, monkeypatch
):
    sessions, league, player, _, parent, game = committed
    now = london_utc(W2, 12)
    monkeypatch.setattr("src.routers.leagues._now", lambda: now)
    async with sessions() as db, db.begin():
        db.add(
            PayerMapping(league_id=league.id, player_id=player.id, monzo_user_id="user_synthetic")
        )

    payment = LinkPayment(
        f"tx_{uuid.uuid4().hex}", league.monzo_link_id, 300, now, "user_synthetic", "Synthetic"
    )

    async def join():
        async with sessions() as db, db.begin():
            await _upsert_membership(league.id, player.id, db)

    async def pay():
        async with sessions() as db, db.begin():
            return await record_link_payment(db, payment, counting_since=london_utc(W0))

    async def early():
        return await materialize_entry_fees(
            sessions,
            league_id=league.id,
            week_id=parent.id,
            game_id=game.id,
            game_kind="fantasy",
            player_id=player.id,
            now=now,
        )

    async def discovery_calendar():
        async with sessions() as db, db.begin():
            await prepare_calendar(db, now)

    results = await asyncio.gather(
        bill_all(sessions, now), join(), early(), discovery_calendar(), pay(), pay()
    )
    assert set(results[-2:]) == {Recorded.matched, Recorded.duplicate}
    async with sessions() as db:
        rows = await dues(db, league, player)
        assert [row.week_label for row in rows] == [W1, W2, W3]
        assert len({row.ledger_entry_id for row in rows}) == 3
        assert (await project_fees(db, league, player.id, W3, now)).for_week(parent).paid_through
        assert (
            await db.scalar(
                select(func.sum(LedgerEntry.amount_pence)).where(LedgerEntry.player_id == player.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_waiting_entry_cannot_use_pre_rejoin_instant_as_free_entitlement(committed):
    sessions, league, player, _, parent, game = committed
    old = london_utc(W2, 12)
    async with sessions() as blocker, blocker.begin():
        await financial_lock(blocker, league.id)
        task = asyncio.create_task(
            materialize_entry_fees(
                sessions,
                league_id=league.id,
                week_id=parent.id,
                game_id=game.id,
                game_kind="fantasy",
                player_id=player.id,
                now=old,
            )
        )
        await asyncio.sleep(0)
        await close_memberships(
            blocker, [league.id], old + timedelta(seconds=1), player_id=player.id
        )
        member = await blocker.scalar(
            select(LeagueMembership).where(LeagueMembership.league_id == league.id)
        )
        member.joined_at = old + timedelta(seconds=2)
        await blocker.flush()
        await track_join(blocker, member)
    with pytest.raises(EntryFeeRefused, match="NOT_FOUND"):
        await task
    async with sessions() as db:
        assert W3 not in [row.week_label for row in await dues(db, league, player)]


@pytest.mark.asyncio
async def test_fee_http_exact_target_auth_and_projection_without_writes(committed, monkeypatch):
    sessions, league, player, _, parent, _ = committed
    monkeypatch.setattr("src.routers.weekly_fees.utc_now", lambda: london_utc(W2, 12))
    headers = {"Authorization": f"Bearer {create_access_token(player.id, player.role)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        path = f"/api/v1/leagues/{league.id}/weeks/{parent.id}/fee"
        response = await client.get(path, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["amount_owed_pence"] == 300 and body["paid_through"] is False
        assert body["week_label"] == W3.isoformat() and body["billing_starts_at"].endswith("Z")
        assert (await client.get(path)).status_code == 401
        assert (
            await client.get(path.replace(str(league.id), str(uuid.uuid4())), headers=headers)
        ).status_code == 404
        monkeypatch.setattr(settings, "two_games_enabled", False)
        assert (await client.get(path, headers=headers)).status_code == 404
    async with sessions() as db:
        assert await dues(db, league, player) == []


@pytest.mark.asyncio
async def test_cached_league_is_revalidated_after_concurrent_deletion(committed):
    sessions, league, player, _, _, _ = committed
    async with sessions() as waiting:
        stale = await waiting.get(League, league.id)
        assert stale.deleted_at is None
        async with sessions() as deleting, deleting.begin():
            await financial_lock(deleting, league.id)
            await deleting.execute(
                update(League).where(League.id == league.id).values(deleted_at=london_utc(W1))
            )
        assert await materialize_dues(waiting, league.id, player.id, london_utc(W2)) == 0
        assert await dues(waiting, league, player) == []


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("before_open", "NOT_OPEN"),
        ("at_lock", "LOCKED"),
        ("suspended", "SUSPENDED"),
        ("cancelled", "CANCELLED"),
        ("wrong_game", "NOT_FOUND"),
        ("wrong_league", "NOT_FOUND"),
        ("inactive", "NOT_FOUND"),
        ("not_member", "NOT_FOUND"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_early_attempt_does_not_materialize_future_dues(
    committed, monkeypatch, case, code
):
    sessions, league, player, _, parent, game = committed
    moment = london_utc(W2, 12)
    if case == "before_open":
        moment -= timedelta(microseconds=1)
    if case == "at_lock":
        moment = game.locks_at
    if case == "inactive":
        monkeypatch.setattr(settings, "two_games_enabled", False)
    if case in {"suspended", "cancelled", "not_member"}:
        async with sessions() as db, db.begin():
            if case == "suspended":
                rollout = await db.get(TwoGameRollout, league.id)
                rollout.suspended = True
            if case == "cancelled":
                stored_game = await db.get(TwoGame, game.id)
                stored_game.status = "cancelled"
            if case == "not_member":
                member = await db.scalar(
                    select(LeagueMembership).where(LeagueMembership.league_id == league.id)
                )
                member.deleted_at = moment
    with pytest.raises(EntryFeeRefused, match=code):
        await materialize_entry_fees(
            sessions,
            league_id=uuid.uuid4() if case == "wrong_league" else league.id,
            week_id=parent.id,
            game_id=game.id,
            game_kind="group" if case == "wrong_game" else "fantasy",
            player_id=player.id,
            now=moment,
        )
    async with sessions() as db:
        assert await dues(db, league, player) == []


@pytest.mark.asyncio
async def test_fee_http_errors_use_contracted_envelope_and_exact_legacy_destination(committed):
    sessions, league, player, _, _, _ = committed
    async with sessions() as db, db.begin():
        legacy = Gameweek(league_id=league.id, starts_on=W0, locks_at_utc=london_utc(W0, 14, 30))
        db.add(legacy)
        await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(player.id, player.role)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
        missing = await client.get(
            f"/api/v1/leagues/{league.id}/weeks/{uuid.uuid4()}/fee", headers=headers
        )
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "NOT_FOUND"
        assert missing.json()["detail"]["message"]
        wrong_format = await client.get(
            f"/api/v1/leagues/{league.id}/weeks/{legacy.id}/fee", headers=headers
        )
        assert wrong_format.status_code == 409
        detail = wrong_format.json()["detail"]
        assert detail["code"] == "UNSUPPORTED_FORMAT" and detail["message"]
        assert detail["week_id"] == str(legacy.id)
        assert detail["destination"] == f"/leagues/{league.slug}/predictions?gw={legacy.id}#coupon"
    async with sessions() as db:
        assert await dues(db, league, player) == []
