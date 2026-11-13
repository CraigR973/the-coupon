"""Batch 220: actual PostgreSQL ownership, atomicity and inactive-mode fences."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src.config import settings
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile, UserRole
from src.models.two_game import (
    TABLE_NAMES,
    FantasyPick,
    GroupPick,
    MembershipInterval,
    ProviderAttempt,
    ProviderControl,
    ProviderSnapshot,
    ProviderWork,
    TwoGame,
    TwoGameFixture,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.services.dues import record_round_dues, reverse_round_dues
from src.services.gameweek import resolve_gameweek, settleable_gameweeks
from src.services.scoring import settle_gameweek
from src.services.two_game_storage import (
    ensure_two_game_week,
    legacy_date_blocked,
    london_utc,
)

# The label test reads deployment-wide dates. Keep its synthetic season separate
# from the committed 2059/60 legacy pick-flow fixtures; all assertions stay exact.
WEEK = date(2160, 1, 1)
WEEK += timedelta(days=(5 - WEEK.weekday()) % 7)


@pytest_asyncio.fixture
async def db(db_conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(
        bind=db_conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as session:
        yield session


async def seed(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> tuple[League, tuple[Profile, Profile], Gameweek, tuple[TwoGame, TwoGame], list[Fixture]]:
    monkeypatch.setattr(settings, "two_games_enabled", True)
    members = tuple(
        Profile(display_name=f"storage-{uuid.uuid4().hex}", pin_hash="x", role=UserRole.player)
        for _ in range(2)
    )
    db.add_all(members)
    await db.flush()
    league = League(
        slug=f"storage-{uuid.uuid4().hex}",
        name="Synthetic storage league",
        created_by=members[0].id,
        entry_fee_pence=100,
    )
    db.add(league)
    await db.flush()
    db.add_all(
        LeagueMembership(
            league_id=league.id, player_id=p.id, joined_at=london_utc(WEEK - timedelta(days=20))
        )
        for p in members
    )
    db.add(
        TwoGameRollout(
            league_id=league.id,
            first_week=WEEK,
            enabled=True,
            effective_opening=london_utc(WEEK - timedelta(days=7), 12),
        )
    )
    await db.flush()
    week = await ensure_two_game_week(db, league.id, WEEK)
    assert week is not None
    group = TwoGame(
        league_id=league.id,
        week_id=week.id,
        kind="group",
        opens_at=london_utc(WEEK - timedelta(days=1), 12),
        locks_at=london_utc(WEEK, 14, 30),
        window_start=london_utc(WEEK, 15),
        window_end=london_utc(WEEK, 15),
    )
    fantasy = TwoGame(
        league_id=league.id,
        week_id=week.id,
        kind="fantasy",
        opens_at=london_utc(WEEK - timedelta(days=7), 12),
        locks_at=london_utc(WEEK, 12),
        window_start=london_utc(WEEK, 12, 30),
        window_end=london_utc(WEEK + timedelta(days=2)),
    )
    db.add_all([group, fantasy])
    fixtures = [
        Fixture(
            provider_event_id=f"storage-{uuid.uuid4().hex}",
            home=f"Home {i}",
            away=f"Away {i}",
            kickoff_utc=london_utc(WEEK, 15),
            competition="Scottish League Two",
            competition_id="scotland-league-two",
        )
        for i in range(3)
    ]
    db.add_all(fixtures)
    await db.flush()
    db.add_all(
        TwoGameFixture(game_id=g.id, fixture_id=f.id) for g in (group, fantasy) for f in fixtures
    )
    await db.flush()
    return league, (members[0], members[1]), week, (group, fantasy), fixtures


def group_pick(
    league: League, week: Gameweek, game: TwoGame, fixture: Fixture, player: Profile
) -> GroupPick:
    return GroupPick(
        league_id=league.id,
        week_id=week.id,
        game_id=game.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market="MATCH_ODDS",
        outcome="HOME",
        runner_name=fixture.home,
        operation_id=uuid.uuid4(),
    )


def fantasy_pick(
    league: League, week: Gameweek, game: TwoGame, fixture: Fixture, player: Profile, slot: int = 1
) -> FantasyPick:
    return FantasyPick(
        league_id=league.id,
        week_id=week.id,
        game_id=game.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market="MATCH_ODDS",
        outcome="HOME",
        runner_name=fixture.home,
        operation_id=uuid.uuid4(),
        slot=slot,
        frozen_odds=Decimal("2.15"),
        quoted_at=game.opens_at,
        provider="fake",
        bookmaker="synthetic",
    )


async def add_due(
    db: AsyncSession,
    league: League,
    week: Gameweek,
    player: Profile,
    *,
    joined_delta: int = -20,
    owed_delta: int = 0,
) -> WeeklyFeeObligation:
    interval = MembershipInterval(
        league_id=league.id,
        player_id=player.id,
        joined_at=london_utc(WEEK + timedelta(days=joined_delta)),
        provenance="synthetic-activation",
    )
    db.add(interval)
    due = LedgerEntry(
        league_id=league.id,
        player_id=player.id,
        kind=LedgerKind.round_due,
        amount_pence=-100,
        gameweek_id=week.id,
    )
    db.add(due)
    await db.flush()
    obligation = WeeklyFeeObligation(
        league_id=league.id,
        player_id=player.id,
        week_id=week.id,
        week_label=WEEK,
        interval_id=interval.id,
        ledger_entry_id=due.id,
        billing_start=london_utc(WEEK - timedelta(days=5)),
        billing_end=london_utc(WEEK + timedelta(days=2)),
        owed_at=london_utc(WEEK + timedelta(days=owed_delta)),
    )
    db.add(obligation)
    await db.flush()
    return obligation


@pytest.mark.asyncio
async def test_installation_gate_returns_before_any_database_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "two_games_enabled", False)
    fake_db = AsyncMock(spec=AsyncSession)
    assert await ensure_two_game_week(fake_db, uuid.uuid4(), WEEK) is None
    assert fake_db.mock_calls == []


@pytest.mark.asyncio
async def test_default_parent_and_suspended_billing_only_creation(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, _, week, _, _ = await seed(db, monkeypatch)
    rollout = await db.get(TwoGameRollout, league.id)
    assert rollout is not None
    rollout.suspended = True
    await db.flush()
    target = WEEK + timedelta(days=7)
    assert await ensure_two_game_week(db, league.id, target) is None
    parent = await ensure_two_game_week(db, league.id, target, billing=True)
    assert parent is not None and parent.format == "two_game"
    assert parent.status == GameweekStatus.locked and parent.picks_open_at_utc is None
    assert parent.id != week.id
    assert await db.scalar(select(TwoGame.id).where(TwoGame.week_id == parent.id)) is None


@pytest.mark.asyncio
async def test_legacy_and_new_week_fences_preserve_published_legacy(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, _, week, _, _ = await seed(db, monkeypatch)
    old = Gameweek(
        league_id=league.id,
        starts_on=WEEK - timedelta(days=7),
        locks_at_utc=london_utc(WEEK - timedelta(days=7), 14, 30),
    )
    db.add(old)
    await db.flush()
    assert old.format == "legacy"
    assert not await legacy_date_blocked(db, league.id, old.starts_on)
    assert await legacy_date_blocked(db, league.id, WEEK + timedelta(days=2))
    with pytest.raises(HTTPException) as refusal:
        await resolve_gameweek(db, league.id, str(week.id))
    assert refusal.value.status_code == 409
    assert refusal.value.detail["code"] == "UNSUPPORTED_FORMAT"
    assert week.id not in {g.id for g in await settleable_gameweeks(db, london_utc(WEEK, 16))}
    assert await settle_gameweek(db, week, []) == 0
    assert week.status == GameweekStatus.locked


@pytest.mark.parametrize("column,value", [("format", "legacy"), ("id", uuid.uuid4())])
@pytest.mark.asyncio
async def test_new_parent_identity_cannot_change(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, column: str, value: object
) -> None:
    league, _, _, _, _ = await seed(db, monkeypatch)
    week = await ensure_two_game_week(db, league.id, WEEK + timedelta(days=7), billing=True)
    assert week is not None
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(Gameweek).where(Gameweek.id == week.id).values(**{column: value})
            )


@pytest.mark.asyncio
async def test_raw_legacy_fixture_writer_is_refused(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, week, _, fixtures = await seed(db, monkeypatch)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(GameweekFixture(gameweek_id=week.id, fixture_id=fixtures[0].id))
            await db.flush()


@pytest.mark.asyncio
async def test_raw_legacy_pick_writer_is_refused(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, _, fixtures = await seed(db, monkeypatch)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=week.id,
                    fixture_id=fixtures[0].id,
                    player_id=members[0].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.HOME,
                    runner_name=fixtures[0].home,
                    odds_at_pick=Decimal("2.15"),
                )
            )
            await db.flush()


@pytest.mark.asyncio
async def test_equal_group_open_and_lock_policy_is_preserved(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, _, _, _, _ = await seed(db, monkeypatch)
    label = WEEK + timedelta(days=7)
    week = await ensure_two_game_week(db, league.id, label)
    assert week is not None
    game = TwoGame(
        league_id=league.id,
        week_id=week.id,
        kind="group",
        opens_at=london_utc(label, 14, 30),
        locks_at=london_utc(label, 14, 30),
        window_start=london_utc(label, 15),
        window_end=london_utc(label, 15),
    )
    db.add(game)
    await db.flush()
    assert game.opens_at == game.locks_at


@pytest.mark.asyncio
async def test_child_and_pick_ownership_cannot_cross_leagues(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    other = League(
        slug=f"other-{uuid.uuid4().hex}", name="Other synthetic league", created_by=members[0].id
    )
    db.add(other)
    await db.flush()
    db.add(LeagueMembership(league_id=other.id, player_id=members[0].id))
    await db.flush()
    wrong = group_pick(league, week, games[0], fixtures[0], members[0])
    wrong.league_id = other.id
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(wrong)
            await db.flush()


@pytest.mark.asyncio
async def test_group_claim_replacement_conflict_preserves_original(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    first = group_pick(league, week, games[0], fixtures[0], members[0])
    second = group_pick(league, week, games[0], fixtures[1], members[1])
    db.add_all([first, second])
    await db.flush()
    first_id, original = first.id, first.fixture_id
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(GroupPick)
                .where(GroupPick.id == first_id)
                .values(fixture_id=second.fixture_id)
            )
    await db.refresh(first)
    assert first.fixture_id == original
    assert not {"frozen_odds", "odds", "points_awarded"} & set(GroupPick.__table__.columns.keys())


@pytest.mark.parametrize("slot", [0, 7])
@pytest.mark.asyncio
async def test_fantasy_slot_bounds(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, slot: int
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(fantasy_pick(league, week, games[1], fixtures[0], members[0], slot))
            await db.flush()


@pytest.mark.asyncio
async def test_shared_selection_is_independent_but_own_fixture_is_unique(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    db.add(group_pick(league, week, games[0], fixtures[0], members[0]))
    db.add_all(fantasy_pick(league, week, games[1], fixtures[0], p) for p in members)
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(fantasy_pick(league, week, games[1], fixtures[0], members[0], 2))
            await db.flush()
    picks = (await db.scalars(select(FantasyPick).where(FantasyPick.week_id == week.id))).all()
    assert len(picks) == 2 and all(p.frozen_odds == Decimal("2.15") for p in picks)


@pytest.mark.parametrize(
    "kind,day,hour,minute",
    [
        ("group", 0, 14, 59),
        ("group", 1, 15, 0),
        ("fantasy", 0, 12, 29),
        ("fantasy", 2, 0, 0),
    ],
)
@pytest.mark.asyncio
async def test_fixture_membership_enforces_exact_windows(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, kind: str, day: int, hour: int, minute: int
) -> None:
    _, _, _, games, _ = await seed(db, monkeypatch)
    fixture = Fixture(
        provider_event_id=f"boundary-{uuid.uuid4().hex}",
        home="Boundary A",
        away="Boundary B",
        competition="League Two",
        competition_id="scotland-league-two",
        kickoff_utc=london_utc(WEEK + timedelta(days=day), hour, minute),
    )
    db.add(fixture)
    await db.flush()
    game = games[0] if kind == "group" else games[1]
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(TwoGameFixture(game_id=game.id, fixture_id=fixture.id))
            await db.flush()


@pytest.mark.asyncio
async def test_owed_fee_and_ledger_survive_legacy_void_or_departure(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, _, _ = await seed(db, monkeypatch)
    obligation = await add_due(db, league, week, members[0])
    assert await record_round_dues(db, league, week) == 0
    assert await reverse_round_dues(db, [week.id], note="synthetic legacy reversal") == 0
    assert (await db.get(LedgerEntry, obligation.ledger_entry_id)).amount_pence == -100
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(LedgerEntry)
                .where(LedgerEntry.id == obligation.ledger_entry_id)
                .values(amount_pence=-200)
            )


@pytest.mark.asyncio
async def test_fee_cannot_charge_wholly_pre_membership_week(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, _, _ = await seed(db, monkeypatch)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await add_due(db, league, week, members[0], joined_delta=7, owed_delta=7)


@pytest.mark.asyncio
async def test_interval_uuid_and_closed_history_are_immutable(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, _, _ = await seed(db, monkeypatch)
    obligation = await add_due(db, league, week, members[0])
    unreferenced = MembershipInterval(
        league_id=league.id,
        player_id=members[1].id,
        joined_at=london_utc(WEEK),
        provenance="synthetic-join",
    )
    db.add(unreferenced)
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(MembershipInterval)
                .where(MembershipInterval.id == unreferenced.id)
                .values(id=uuid.uuid4())
            )
    await db.execute(
        update(MembershipInterval)
        .where(MembershipInterval.id == obligation.interval_id)
        .values(left_at=london_utc(WEEK, 13))
    )
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(MembershipInterval)
                .where(MembershipInterval.id == obligation.interval_id)
                .values(left_at=None)
            )
    assert (await db.get(WeeklyFeeObligation, obligation.id)).amount_pence == 100


@pytest.mark.asyncio
async def test_new_tables_force_rls_and_revoke_public_grants(db: AsyncSession) -> None:
    rows = (
        await db.execute(
            text("""
        SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
        WHERE relnamespace='public'::regnamespace AND relname = ANY(:names)
    """),
            {"names": list(TABLE_NAMES)},
        )
    ).all()
    assert len(rows) == len(TABLE_NAMES)
    assert all(enabled and forced for _, enabled, forced in rows)
    grants = await db.scalar(
        text("""
        SELECT count(*) FROM pg_class c,
          LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE c.relnamespace='public'::regnamespace AND c.relname=ANY(:names)
          AND (a.grantee=0 OR a.grantee IN
               (SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated')))
    """),
        {"names": list(TABLE_NAMES)},
    )
    assert grants == 0


@pytest.mark.asyncio
async def test_every_new_foreign_key_has_a_valid_leading_index(db: AsyncSession) -> None:
    missing = (
        (
            await db.execute(
                text("""
        SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        WHERE c.contype='f' AND t.relname=ANY(:names) AND NOT EXISTS (
          SELECT 1 FROM pg_index i WHERE i.indrelid=c.conrelid
            AND i.indisvalid AND i.indpred IS NULL AND NOT EXISTS (
              SELECT 1 FROM unnest(c.conkey) WITH ORDINALITY AS f(attnum,pos)
              WHERE i.indkey[(f.pos-1)::integer] IS DISTINCT FROM f.attnum))
    """),
                {"names": list(TABLE_NAMES)},
            )
        )
        .scalars()
        .all()
    )
    assert missing == []


@pytest.mark.asyncio
async def test_budget_and_cursor_commits_survive_business_rollback(db_engine) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    meter = f"storage-{uuid.uuid4().hex}"
    now = london_utc(WEEK)
    async with maker() as db:
        db.add(ProviderAttempt(meter=meter, category="quote", reserved_at=now))
        db.add(ProviderControl(meter=meter, cooldown_until=now + timedelta(minutes=15)))
        db.add(
            ProviderSnapshot(
                key=meter,
                payload={"price": "2.15"},
                observed_at=now,
                expires_at=now + timedelta(seconds=60),
            )
        )
        db.add(
            ProviderWork(
                key=meter, kind="pricing", payload={"completed": [1]}, cursor="page-2", next_at=now
            )
        )
        await db.commit()
    async with maker() as business:
        await business.execute(
            update(ProviderWork)
            .where(ProviderWork.key == meter)
            .values(cursor="uncommitted-business-change")
        )
        await business.rollback()
    async with maker() as restarted:
        assert await restarted.scalar(
            select(ProviderAttempt.id).where(ProviderAttempt.meter == meter)
        )
        assert (await restarted.get(ProviderControl, meter)).cooldown_until == now + timedelta(
            minutes=15
        )
        assert (await restarted.get(ProviderSnapshot, meter)).payload == {"price": "2.15"}
        assert (await restarted.get(ProviderWork, meter)).cursor == "page-2"
        with pytest.raises(IntegrityError):
            async with restarted.begin_nested():
                await restarted.execute(
                    update(ProviderAttempt)
                    .where(ProviderAttempt.meter == meter)
                    .values(reserved_at=now + timedelta(days=1))
                )


@pytest.mark.asyncio
async def test_failed_fantasy_replacement_keeps_fixture_price_and_revision(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    first = fantasy_pick(league, week, games[1], fixtures[0], members[0], 1)
    second = fantasy_pick(league, week, games[1], fixtures[1], members[0], 2)
    second.frozen_odds = Decimal("3.20")
    db.add_all([first, second])
    await db.flush()
    first_id, original_fixture = first.id, first.fixture_id
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                update(FantasyPick)
                .where(FantasyPick.id == first_id)
                .values(fixture_id=second.fixture_id, frozen_odds=Decimal("4.50"), revision=2)
            )
    await db.refresh(first)
    assert (first.fixture_id, first.frozen_odds, first.revision) == (
        original_fixture,
        Decimal("2.15"),
        1,
    )


@pytest.mark.parametrize(
    "case", ["group_member", "group_fixture", "fantasy_slot", "fantasy_fixture"]
)
@pytest.mark.asyncio
async def test_concurrent_claims_admit_only_one_committed_writer(
    db_engine, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as setup:
        league, members, week, games, fixtures = await seed(setup, monkeypatch)
        await setup.commit()
    barrier = asyncio.Barrier(2)
    model = GroupPick if case.startswith("group") else FantasyPick

    async def save(n: int) -> bool:
        player = members[n] if case == "group_fixture" else members[0]
        fixture = fixtures[0] if case in ("group_fixture", "fantasy_fixture") else fixtures[n]
        if model is GroupPick:
            pick = group_pick(league, week, games[0], fixture, player)
        else:
            slot = n + 1 if case == "fantasy_fixture" else 1
            pick = fantasy_pick(league, week, games[1], fixture, player, slot)
        async with maker() as request:
            request.add(pick)
            await barrier.wait()
            try:
                await request.commit()
                return True
            except IntegrityError:
                await request.rollback()
                return False

    try:
        results = await asyncio.gather(save(0), save(1))
        assert sorted(results) == [False, True]
        async with maker() as check:
            assert (
                await check.scalar(
                    select(func.count()).select_from(model).where(model.week_id == week.id)
                )
                == 1
            )
    finally:
        # Only this test's synthetic committed rows, in the disposable gate database.
        async with maker() as cleanup:
            for table in (GroupPick, FantasyPick):
                await cleanup.execute(delete(table).where(table.week_id == week.id))
            await cleanup.execute(
                delete(TwoGameFixture).where(TwoGameFixture.game_id.in_([g.id for g in games]))
            )
            await cleanup.execute(delete(TwoGame).where(TwoGame.week_id == week.id))
            await cleanup.execute(delete(Gameweek).where(Gameweek.id == week.id))
            await cleanup.execute(
                delete(TwoGameRollout).where(TwoGameRollout.league_id == league.id)
            )
            await cleanup.execute(
                delete(LeagueMembership).where(LeagueMembership.league_id == league.id)
            )
            await cleanup.execute(delete(League).where(League.id == league.id))
            await cleanup.execute(delete(Profile).where(Profile.id.in_([p.id for p in members])))
            await cleanup.execute(delete(Fixture).where(Fixture.id.in_([f.id for f in fixtures])))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_legacy_readers_ignore_new_parents_without_renaming_history(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.models.season_calendar import SeasonCalendar
    from src.routers.picks import my_pick
    from src.services.discovery_health import discovery_health
    from src.services.football_provider import season_for
    from src.services.gameweek import seasons_played
    from src.services.scoring import gameweek_results
    from src.services.season_calendar import SeasonLabels

    league, members, week, _, _ = await seed(db, monkeypatch)
    rollout = await db.get(TwoGameRollout, league.id)
    rollout.enabled = False
    await db.flush()
    old = Gameweek(
        league_id=league.id,
        starts_on=WEEK - timedelta(days=1),
        locks_at_utc=london_utc(WEEK - timedelta(days=1), 14, 30),
        status=GameweekStatus.settled,
        created_at=london_utc(WEEK - timedelta(days=10)),
    )
    db.add(old)
    db.add(SeasonCalendar(season=season_for(WEEK), week_one_anchor=WEEK, extra_weeks=[]))
    await db.flush()
    before = await SeasonLabels().of(db, [old])
    rollout.enabled = True
    week.status = GameweekStatus.settled
    week.created_at = london_utc(WEEK)
    await db.flush()
    assert await SeasonLabels().of(db, [old]) == before == {old.id: "1"}
    results = await gameweek_results(db, league.id, season=season_for(WEEK))
    assert [r.gameweek_id for r in results] == [str(old.id)]
    seasons = await seasons_played(db, league.id)
    assert next(s for s in seasons if s.season == season_for(WEEK)).rounds_settled == 1
    health = await discovery_health(db, london_utc(WEEK), stale_after_hours=24)
    assert health.newest_round_created_at == old.created_at
    assert health.stale
    with pytest.raises(HTTPException) as refusal:
        await my_pick(league.slug, week.id, members[0], league, db)
    assert refusal.value.status_code == 409
    assert refusal.value.detail["code"] == "UNSUPPORTED_FORMAT"
    assert await my_pick(league.slug, old.id, members[0], league, db) is None
    assert await my_pick(league.slug, uuid.uuid4(), members[0], league, db) is None


@pytest.mark.asyncio
async def test_raw_legacy_parent_cannot_be_created_past_cutover(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, _, _, _, _ = await seed(db, monkeypatch)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(
                Gameweek(
                    league_id=league.id,
                    starts_on=WEEK + timedelta(days=6),
                    locks_at_utc=london_utc(WEEK + timedelta(days=6), 14, 30),
                )
            )
            await db.flush()


@pytest.mark.asyncio
async def test_pick_cannot_cross_weeks_even_with_valid_member_and_fixture(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    league, members, week, games, fixtures = await seed(db, monkeypatch)
    other = await ensure_two_game_week(db, league.id, WEEK + timedelta(days=7))
    assert other is not None
    wrong = fantasy_pick(league, week, games[1], fixtures[0], members[0])
    wrong.week_id = other.id
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(wrong)
            await db.flush()
