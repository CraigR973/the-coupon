"""Batch 231: the audited activation, suspension and resume of one league's rollout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src import two_game_rollout as command
from src.auth import create_access_token
from src.config import settings
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League, PickMarket
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.notification import AuditLog, MemberNotification
from src.models.pick import Pick, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.models.two_game import (
    FantasyPick,
    GroupPick,
    MembershipInterval,
    ProviderWork,
    TwoGame,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.routers import admin as admin_routes
from src.services import two_game_events as events
from src.services.two_game_entry import Target, entry_state
from src.services.two_game_reads import GameReads
from src.services.two_game_rollout_admin import (
    RolloutRefused,
    activate_rollout,
    reconciliation,
    resume_rollout,
    suspend_rollout,
)
from src.services.two_game_schedule import prepare_calendar
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import bill_all
from tests import test_two_game_fantasy as entries
from tests import test_two_game_settlement as settlement
from tests import two_game_test_store as stores

baseline_db_engine = stores.baseline_db_engine
result_store = stores.result_store
db_engine = stores.db_engine
fantasy = entries.fantasy
results = settlement.results
WEEK = entries.WEEK

FIRST = date(2026, 11, 28)
#: Wednesday 18 Nov: the first week's rule opening (Sat 21 Nov noon) is still ahead.
BEFORE_OPENING = datetime(2026, 11, 18, 10)
#: Thursday 26 Nov evening: the rule opening has passed, the 28 Nov case.
AFTER_OPENING = datetime(2026, 11, 26, 17, 20)


@dataclass
class Hibs:
    sessions: async_sessionmaker
    league: League
    admin: Profile
    members: list[Profile]
    round_17: uuid.UUID
    round_18: uuid.UUID

    async def activate(self, now: datetime, **options: bool):
        async with self.sessions() as db, db.begin():
            return await activate_rollout(
                db,
                league_id=self.league.id,
                first_week=FIRST,
                actor_id=self.admin.id,
                now=now,
                **options,
            )

    async def refused(self, now: datetime, **options: bool) -> RolloutRefused:
        with pytest.raises(RolloutRefused) as caught:
            await self.activate(now, **options)
        return caught.value

    async def rollout(self) -> TwoGameRollout | None:
        async with self.sessions() as db:
            return await db.get(TwoGameRollout, self.league.id)

    async def request(self, method: str, path: str, *, player: Profile, json=None):
        token = create_access_token(player.id, player.role)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://local.test"
        ) as client:
            return await client.request(
                method,
                f"/api/v1/admin/leagues/{self.league.id}/two-game{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )


@pytest_asyncio.fixture
async def hibs(db_engine, monkeypatch):
    """A 2-1 Hibs-shaped league: 12-hour opening, £1 fee, rounds 17 and 18 on the board."""
    monkeypatch.setattr(settings, "two_games_enabled", True)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    tag = uuid.uuid4().hex
    async with sessions() as db, db.begin():
        admin = Profile(display_name=f"Owner {tag}", pin_hash="x", role=UserRole.admin)
        members = [Profile(display_name=f"Member {i} {tag}", pin_hash="x") for i in range(3)]
        db.add_all([admin, *members])
        await db.flush()
        league = League(
            slug=f"rollout-{tag}",
            name="Synthetic rollout",
            created_by=admin.id,
            offered_markets=[PickMarket.MATCH_ODDS, PickMarket.BOTH_TEAMS_TO_SCORE],
            pick_open_offset_minutes=720,
            entry_fee_pence=100,
            payment_link_url="https://synthetic.invalid/pay",
        )
        db.add(league)
        await db.flush()
        for member in (admin, *members):
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=member.id,
                    joined_at=london_utc(FIRST - timedelta(days=60)),
                )
            )
        fixtures = [
            Fixture(
                provider_event_id=f"rollout-{tag}-{i}",
                home=f"Home {i}",
                away=f"Away {i}",
                competition="Synthetic",
                competition_id="synthetic",
                kickoff_utc=london_utc(FIRST + timedelta(days=7 * i), 15),
            )
            for i in range(2)
        ]
        db.add_all(fixtures)
        played = Gameweek(
            league_id=league.id,
            starts_on=FIRST - timedelta(days=7),
            status=GameweekStatus.settled,
            picks_open_at_utc=london_utc(FIRST - timedelta(days=7), 3),
            locks_at_utc=london_utc(FIRST - timedelta(days=7), 14, 30),
            settled_at=london_utc(FIRST - timedelta(days=7), 18, 5),
            number=16,
        )
        scheduled = [
            Gameweek(
                league_id=league.id,
                starts_on=FIRST + timedelta(days=7 * i),
                status=GameweekStatus.scheduled,
                picks_open_at_utc=london_utc(FIRST + timedelta(days=7 * i), 3),
                locks_at_utc=london_utc(FIRST + timedelta(days=7 * i), 14, 30),
                number=17 + i,
            )
            for i in range(2)
        ]
        db.add_all([played, *scheduled])
        await db.flush()
        db.add_all(
            [
                GameweekFixture(gameweek_id=week.id, fixture_id=fixture.id)
                for week, fixture in zip(scheduled, fixtures, strict=True)
            ]
        )
    result = Hibs(sessions, league, admin, members, scheduled[0].id, scheduled[1].id)
    try:
        yield result
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
                .where(Profile.id.in_([admin.id, *(member.id for member in members)]))
                .values(deleted_at=datetime(2026, 12, 20), is_active=False)
            )


async def site_admin(f) -> Profile:
    async with f.sessions() as db, db.begin():
        admin = Profile(
            display_name=f"Site admin {uuid.uuid4().hex}", pin_hash="x", role=UserRole.admin
        )
        db.add(admin)
    return admin


async def audit_rows(sessions, league_id: uuid.UUID) -> list[AuditLog]:
    async with sessions() as db:
        return list(
            await db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.target_table == "two_game_rollouts", AuditLog.target_id == league_id
                )
                .order_by(AuditLog.timestamp, AuditLog.id)
            )
        )


@pytest.mark.asyncio
async def test_untouched_future_week_writes_one_audited_row_and_refuses_a_second(hibs):
    # A Saturday discovery has not reached yet: no legacy round on it or after it.
    async with hibs.sessions() as db, db.begin():
        await db.execute(delete(Gameweek).where(Gameweek.id.in_([hibs.round_17, hibs.round_18])))
    activation = await hibs.activate(BEFORE_OPENING)
    rollout = await hibs.rollout()
    assert rollout is not None and rollout.enabled and not rollout.suspended
    assert rollout.first_week == FIRST
    # An ordinary activation keeps the rule: previous Saturday noon.
    assert (
        rollout.effective_opening == activation.rule_opening == london_utc(FIRST - timedelta(7), 12)
    )
    assert not activation.opened_at_activation and activation.retired == ()
    [row] = await audit_rows(hibs.sessions, hibs.league.id)
    assert row.actor_id == hibs.admin.id
    assert row.changes["operation"] == "two_game_activated"
    assert row.changes["league_slug"] == hibs.league.slug
    assert row.changes["first_week"] == FIRST.isoformat()
    assert row.changes["retired_rounds"] == []
    assert "owner_decision" not in row.changes
    again = await hibs.refused(BEFORE_OPENING)
    assert again.code == "ALREADY_ACTIVATED"
    assert len(await audit_rows(hibs.sessions, hibs.league.id)) == 1


@pytest.mark.asyncio
async def test_refusals_change_nothing(hibs, monkeypatch):
    member = await hibs.refused(BEFORE_OPENING)
    assert member.code == "LEGACY_WEEK_PRESENT"
    assert [entry["number"] for entry in member.details["rounds"]] == [17, 18]
    late = await hibs.refused(london_utc(FIRST, 12), retire_untouched_legacy=True)
    assert late.code == "TOO_LATE"
    async with hibs.sessions() as db, db.begin():
        with pytest.raises(RolloutRefused) as saturday:
            await activate_rollout(
                db,
                league_id=hibs.league.id,
                first_week=FIRST - timedelta(days=1),
                actor_id=hibs.admin.id,
                now=BEFORE_OPENING,
            )
        assert saturday.value.code == "NOT_A_SATURDAY"
        with pytest.raises(RolloutRefused) as player:
            await activate_rollout(
                db,
                league_id=hibs.league.id,
                first_week=FIRST,
                actor_id=hibs.members[0].id,
                now=BEFORE_OPENING,
            )
        assert (player.value.status, player.value.code) == (403, "NOT_SITE_ADMIN")
    monkeypatch.setattr(settings, "two_games_enabled", False)
    off = await hibs.refused(BEFORE_OPENING, retire_untouched_legacy=True)
    assert off.code == "FORMAT_DISABLED"
    assert await hibs.rollout() is None
    assert await audit_rows(hibs.sessions, hibs.league.id) == []
    async with hibs.sessions() as db:
        assert await db.get(Gameweek, hibs.round_17) is not None
        assert await db.get(Gameweek, hibs.round_18) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("touch", ["opened", "open_status", "pick", "due", "notice"])
async def test_a_touched_legacy_round_refuses_the_whole_activation(hibs, touch):
    async with hibs.sessions() as db, db.begin():
        round_17 = await db.get(Gameweek, hibs.round_17)
        fixture_id = await db.scalar(
            select(GameweekFixture.fixture_id).where(GameweekFixture.gameweek_id == hibs.round_17)
        )
        if touch == "opened":
            round_17.picks_open_at_utc = BEFORE_OPENING - timedelta(hours=1)
        elif touch == "open_status":
            round_17.status = GameweekStatus.open
        elif touch == "pick":
            db.add(
                Pick(
                    league_id=hibs.league.id,
                    gameweek_id=hibs.round_17,
                    fixture_id=fixture_id,
                    player_id=hibs.members[0].id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=PickOutcome.HOME,
                    runner_name="Home 0",
                    odds_at_pick=Decimal("2.00"),
                    status=PickStatus.pending,
                    pick_scope=hibs.league.pick_scope,
                )
            )
        elif touch == "due":
            db.add(
                LedgerEntry(
                    league_id=hibs.league.id,
                    player_id=hibs.members[0].id,
                    kind=LedgerKind.round_due,
                    amount_pence=-100,
                    gameweek_id=hibs.round_17,
                )
            )
        else:
            db.add(
                MemberNotification(
                    user_id=hibs.members[0].id,
                    league_id=hibs.league.id,
                    kind="picks_open",
                    title="Picks are open",
                    body="Synthetic",
                    url=f"/leagues/{hibs.league.slug}/predictions?gw={hibs.round_17}#coupon",
                )
            )
    refusal = await hibs.refused(BEFORE_OPENING, retire_untouched_legacy=True)
    assert refusal.code == "LEGACY_WEEK_TOUCHED"
    assert list(refusal.details["touched"]) == [str(hibs.round_17)]
    assert await hibs.rollout() is None
    async with hibs.sessions() as db:
        assert await db.get(Gameweek, hibs.round_17) is not None
        assert await db.get(Gameweek, hibs.round_18) is not None


@pytest.mark.asyncio
async def test_retiring_untouched_rounds_builds_both_weeks_with_the_announced_deadline(hibs):
    activation = await hibs.activate(BEFORE_OPENING, retire_untouched_legacy=True)
    assert [round_.number for round_ in activation.retired] == [17, 18]
    async with hibs.sessions() as db:
        assert await db.get(Gameweek, hibs.round_17) is None
        assert await db.get(Gameweek, hibs.round_18) is None
        assert (
            await db.scalar(
                select(func.count())
                .select_from(GameweekFixture)
                .where(GameweekFixture.gameweek_id.in_([hibs.round_17, hibs.round_18]))
            )
            == 0
        )
    [row] = await audit_rows(hibs.sessions, hibs.league.id)
    assert [entry["gameweek_id"] for entry in row.changes["retired_rounds"]] == [
        str(hibs.round_17),
        str(hibs.round_18),
    ]
    async with hibs.sessions() as db, db.begin():
        await prepare_calendar(db, BEFORE_OPENING)
    async with hibs.sessions() as db:
        weeks = list(
            await db.scalars(
                select(Gameweek)
                .where(Gameweek.league_id == hibs.league.id, Gameweek.format == "two_game")
                .order_by(Gameweek.starts_on)
            )
        )
        assert [(week.starts_on, week.number) for week in weeks] == [
            (FIRST, 17),
            (FIRST + timedelta(days=7), 18),
        ]
        games = {
            (game.week_id, game.kind): game
            for game in await db.scalars(select(TwoGame).where(TwoGame.league_id == hibs.league.id))
        }
        group = games[(weeks[0].id, "group")]
        # The group keeps exactly the opening and deadline round 17 had announced.
        assert (group.opens_at, group.locks_at) == (london_utc(FIRST, 3), london_utc(FIRST, 14, 30))
        assert games[(weeks[0].id, "fantasy")].opens_at == london_utc(FIRST - timedelta(7), 12)
        assert games[(weeks[1].id, "fantasy")].opens_at == london_utc(FIRST, 12)
        progress = await db.get(ProviderWork, f"calendar:{hibs.league.id}")
        assert progress is not None and progress.payload["state"] != "schedule_conflict"
    # Discovery cannot put a legacy round back once the row exists.
    with pytest.raises(DBAPIError):
        async with hibs.sessions() as db, db.begin():
            db.add(
                Gameweek(
                    league_id=hibs.league.id,
                    starts_on=FIRST + timedelta(days=14),
                    locks_at_utc=london_utc(FIRST + timedelta(days=14), 14, 30),
                )
            )


@pytest.mark.asyncio
async def test_a_passed_first_opening_needs_the_owner_decision_and_then_opens_at_activation(
    hibs,
):
    refusal = await hibs.refused(AFTER_OPENING, retire_untouched_legacy=True)
    assert refusal.code == "OPENING_PASSED"
    assert refusal.details["rule_opening"] == london_utc(FIRST - timedelta(7), 12).isoformat()
    assert await hibs.rollout() is None
    activation = await hibs.activate(
        AFTER_OPENING, retire_untouched_legacy=True, open_at_activation=True
    )
    assert activation.opened_at_activation and activation.effective_opening == AFTER_OPENING
    [row] = await audit_rows(hibs.sessions, hibs.league.id)
    assert row.changes["owner_decision"].startswith("owner 2026-11-22")
    for moment in (AFTER_OPENING, AFTER_OPENING + timedelta(minutes=1)):
        async with hibs.sessions() as db, db.begin():
            await prepare_calendar(db, moment)
    async with hibs.sessions() as db:
        games = {
            (game.kind, game.locks_at): game
            for game in await db.scalars(select(TwoGame).where(TwoGame.league_id == hibs.league.id))
        }
        first = games[("fantasy", london_utc(FIRST, 12))]
        # The stored opening stays the rule's Saturday noon (migration 032's fence); the
        # game did not exist until activation, so entry is open from activation onwards.
        assert (first.opens_at, first.status) == (london_utc(FIRST - timedelta(7), 12), "open")
        group = games[("group", london_utc(FIRST, 14, 30))]
        assert (group.opens_at, group.status) == (london_utc(FIRST, 3), "scheduled")
        second = games[("fantasy", london_utc(FIRST + timedelta(7), 12))]
        assert (second.opens_at, second.status) == (london_utc(FIRST, 12), "scheduled")
        progress = await db.get(ProviderWork, f"calendar:{hibs.league.id}")
        assert progress is not None and progress.payload["state"] != "schedule_conflict"
        week = await db.get(Gameweek, first.week_id)
        rollout = await db.get(TwoGameRollout, hibs.league.id)
        target = Target(hibs.league, week, first, rollout)
        assert await entry_state(db, target, AFTER_OPENING + timedelta(minutes=1)) == "open"
        assert await entry_state(db, Target(hibs.league, week, group, rollout), AFTER_OPENING) == (
            "not_open"
        )


@pytest.mark.asyncio
async def test_admin_routes_preview_by_default_and_refuse_members(hibs, monkeypatch):
    monkeypatch.setattr(admin_routes, "_now", lambda: BEFORE_OPENING)
    body = {"first_week": FIRST.isoformat(), "retire_untouched_legacy": True}
    member = await hibs.request("POST", "/activate", player=hibs.members[0], json=body)
    assert member.status_code == 403
    preview = await hibs.request("POST", "/activate", player=hibs.admin, json=body)
    assert preview.status_code == 200
    assert preview.json()["applied"] is False
    assert len(preview.json()["result"]["retired_rounds"]) == 2
    assert await hibs.rollout() is None
    refused = await hibs.request(
        "POST", "/activate", player=hibs.admin, json={"first_week": FIRST.isoformat()}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "LEGACY_WEEK_PRESENT"
    applied = await hibs.request(
        "POST", "/activate", player=hibs.admin, json={**body, "apply": True}
    )
    assert applied.status_code == 200 and applied.json()["applied"] is True
    assert (await hibs.rollout()) is not None
    status = await hibs.request("GET", "", player=hibs.admin)
    assert status.status_code == 200
    assert status.json()["result"]["rollout"]["first_week"] == FIRST.isoformat()
    suspend = {"reason": "Synthetic emergency", "apply": True}
    suspended = await hibs.request("POST", "/suspend", player=hibs.admin, json=suspend)
    assert suspended.status_code == 200 and (await hibs.rollout()).suspended
    look = await hibs.request("POST", "/resume", player=hibs.admin, json={})
    assert look.status_code == 200 and look.json()["applied"] is False
    assert (await hibs.rollout()).suspended
    resumed = await hibs.request(
        "POST", "/resume", player=hibs.admin, json={"confirm_reconciliation": True, "apply": True}
    )
    assert resumed.status_code == 200 and not (await hibs.rollout()).suspended
    assert [
        row.changes["operation"] for row in await audit_rows(hibs.sessions, hibs.league.id)
    ] == [
        "two_game_activated",
        "two_game_suspended",
        "two_game_resumed",
    ]


@pytest.mark.asyncio
async def test_operator_command_previews_then_applies_the_same_checks(hibs, monkeypatch):
    from src import database

    monkeypatch.setattr(database, "AsyncSessionLocal", hibs.sessions)
    args = [
        "activate",
        "--league",
        hibs.league.slug,
        "--first-week",
        FIRST.isoformat(),
        "--actor",
        str(hibs.admin.id),
    ]
    code, document = await command.run(command.parser().parse_args(args), now=BEFORE_OPENING)
    assert code == 2 and document["refused"]["code"] == "LEGACY_WEEK_PRESENT"
    retire = [*args, "--retire-untouched-legacy"]
    code, document = await command.run(command.parser().parse_args(retire), now=BEFORE_OPENING)
    assert code == 0 and document["applied"] is False
    assert await hibs.rollout() is None
    code, document = await command.run(
        command.parser().parse_args([*retire, "--apply"]), now=BEFORE_OPENING
    )
    assert code == 0 and document["applied"] is True
    assert document["result"]["first_week"] == FIRST.isoformat()
    code, document = await command.run(
        command.parser().parse_args(["status", "--league", hibs.league.slug]), now=BEFORE_OPENING
    )
    assert code == 0 and document["result"]["rollout"]["suspended"] is False


@pytest.mark.asyncio
async def test_suspension_stops_entries_and_openings_but_keeps_billing_settlement_history(
    results,
):
    f = results.fantasy
    admin = await site_admin(f)
    group_path = f.path.replace("fantasy", "group") + "/pick"

    def group_body(index):
        return {key: value for key, value in f.body(index).items() if key != "odds"}

    assert (await f.save()).status_code == 200
    assert (
        await f.request("PUT", player=2, body=group_body(0), path=group_path)
    ).status_code == 200
    await bill_all(f.sessions, f.source.clock.now)
    async with f.sessions() as db, db.begin():
        await suspend_rollout(
            db,
            league_id=f.league.id,
            actor_id=admin.id,
            now=f.source.clock.now,
            reason="Synthetic emergency",
        )
    # Entries stop: a new slot, a replacement and a group pick are all refused.
    for response in (
        await f.save(slot=2, body=f.body(1)),
        await f.save(slot=1, body=f.body(2, revision=1)),
        await f.request("PUT", player=1, body=group_body(3), path=group_path),
    ):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SUSPENDED"
    # Openings stop: the calendar creates no next-week game while suspended.
    async with f.sessions() as db, db.begin():
        await prepare_calendar(db, f.source.clock.now)
    async with f.sessions() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(TwoGame).where(TwoGame.league_id == f.league.id)
            )
            == 2
        )
    # Settlement continues for the accepted picks.
    f.source.clock.now = london_utc(WEEK, 18)
    assert (await results.worker().run())["resolved"] >= 1
    async with f.sessions() as db:
        assert {
            pick.status
            for pick in await db.scalars(
                select(FantasyPick).where(FantasyPick.league_id == f.league.id)
            )
        } == {"won"}
        assert {
            pick.status
            for pick in await db.scalars(
                select(GroupPick).where(GroupPick.league_id == f.league.id)
            )
        } == {"won"}
    # History stays readable, with the accepted picks and their results.
    reads = GameReads(f.sessions, two_games_enabled=True, clock=f.source.clock)
    history = await reads.results(f.players[0].id, f.league.id, f.parent.id)
    assert history.format == "two_game" and history.week_label == WEEK
    assert history.fantasy is not None and history.group is not None
    # Billing continues: the next calendar week is owed while suspended.
    async with f.sessions() as db:
        before = await db.scalar(
            select(func.count())
            .select_from(WeeklyFeeObligation)
            .where(WeeklyFeeObligation.league_id == f.league.id)
        )
    f.source.clock.now = london_utc(WEEK + timedelta(days=2))
    await bill_all(f.sessions, f.source.clock.now)
    async with f.sessions() as db:
        after = await db.scalar(
            select(func.count())
            .select_from(WeeklyFeeObligation)
            .where(WeeklyFeeObligation.league_id == f.league.id)
        )
        labels = set(
            await db.scalars(
                select(WeeklyFeeObligation.week_label).where(
                    WeeklyFeeObligation.league_id == f.league.id
                )
            )
        )
    assert after == before + 3 and WEEK + timedelta(days=7) in labels
    [row] = await audit_rows(f.sessions, f.league.id)
    assert row.changes["operation"] == "two_game_suspended"
    assert row.changes["reason"] == "Synthetic emergency"


@pytest.mark.asyncio
async def test_resume_needs_confirmed_reconciliation_and_never_reopens_a_locked_game(fantasy):
    f = fantasy
    admin = await site_admin(f)
    await bill_all(f.sessions, f.source.clock.now)
    async with f.sessions() as db, db.begin():
        await suspend_rollout(
            db, league_id=f.league.id, actor_id=admin.id, now=f.source.clock.now, reason="Test"
        )
    # The fantasy lock passes while suspended; the group is still open until 14:30.
    f.source.clock.now = london_utc(WEEK, 12, 5)
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    async with f.sessions() as db:
        assert (await db.get(TwoGame, f.game.id)).status == "locked"
    # A member who joined while suspended and has not been billed yet is a gap.
    async with f.sessions() as db, db.begin():
        joined = london_utc(WEEK - timedelta(days=5))
        db.add(LeagueMembership(league_id=f.league.id, player_id=f.players[3].id, joined_at=joined))
        await db.flush()
        db.add(
            MembershipInterval(
                league_id=f.league.id,
                player_id=f.players[3].id,
                joined_at=joined,
                provenance="recorded_membership",
            )
        )

    async def resume(confirm: bool):
        async with f.sessions() as db, db.begin():
            return await resume_rollout(
                db,
                league_id=f.league.id,
                actor_id=admin.id,
                now=f.source.clock.now,
                confirm_reconciliation=confirm,
            )

    with pytest.raises(RolloutRefused) as gap:
        await resume(True)
    assert gap.value.code == "BILLING_GAPS"
    assert gap.value.details["reconciliation"]["billing_gaps"] == {
        str(f.players[3].id): [WEEK.isoformat()]
    }
    await bill_all(f.sessions, f.source.clock.now)
    with pytest.raises(RolloutRefused) as unconfirmed:
        await resume(False)
    assert unconfirmed.value.code == "CONFIRMATION_REQUIRED"
    report = unconfirmed.value.details["reconciliation"]
    assert [game["game_id"] for game in report["locked_while_suspended"]] == [str(f.game.id)]
    assert [game["game_id"] for game in report["opens_on_resume"]] == [str(f.group.id)]
    async with f.sessions() as db:
        assert (await db.get(TwoGameRollout, f.league.id)).suspended
        assert (await reconciliation(db, f.league.id, f.source.clock.now)).suspended
    resumed = await resume(True)
    assert not resumed.billing_gaps
    async with f.sessions() as db:
        assert not (await db.get(TwoGameRollout, f.league.id)).suspended
    await events.lifecycle_events(f.sessions, f.source.clock.now)
    async with f.sessions() as db:
        assert (await db.get(TwoGame, f.game.id)).status == "locked"
        assert (await db.get(TwoGame, f.group.id)).status == "open"
    late = await f.save(slot=1, body=f.body(0))
    assert late.status_code == 409 and late.json()["detail"]["code"] == "LOCKED"
