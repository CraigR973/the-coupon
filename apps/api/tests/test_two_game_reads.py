"""Real HTTP, read-only snapshots and simultaneous explicitly addressed targets."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.config import settings
from src.models.two_game import GameOperation, ProviderAttempt, ProviderWork, WeeklyFeeObligation
from src.routers import two_game_reads as routes
from src.services.two_game_reads import GameReads
from src.services.two_game_storage import london_utc
from tests import test_two_game_fantasy as entries
from tests import two_game_test_store as stores

baseline_db_engine = stores.baseline_db_engine
result_store = stores.result_store
db_engine = stores.db_engine
fantasy = entries.fantasy
WEEK = entries.WEEK


@pytest_asyncio.fixture
async def games(fantasy, monkeypatch):
    monkeypatch.setattr(
        routes,
        "game_reads",
        lambda: GameReads(
            fantasy.sessions,
            two_games_enabled=settings.two_games_enabled,
            clock=fantasy.source.clock,
        ),
    )
    return fantasy


async def home(f):
    response = await f.request("GET", path="/api/v1/me/games")
    assert response.status_code == 200, response.text
    return next(
        league for league in response.json()["leagues"] if league["league_id"] == str(f.league.id)
    )


@pytest.mark.asyncio
async def test_home_reads_all_stored_targets_without_fees_quotes_work_or_operations(games):
    f = games
    next_week = await entries.additional_week(f, WEEK + timedelta(days=7))
    view = await home(f)
    assert view["two_games_enabled"] and len(view["games"]) == 3
    assert view["server_now"].endswith("Z")
    current = {
        card["game_kind"]: card for card in view["games"] if card["week_id"] == str(f.parent.id)
    }
    assert set(current) == {"group", "fantasy"}
    assert current["group"]["entry_state"] == current["fantasy"]["entry_state"] == "open"
    assert current["group"]["result"] == {"status": "no_coupon", "final": False}
    assert len(current["fantasy"]["slots"]) == 6
    upcoming = next(card for card in view["games"] if card["week_id"] == str(next_week[1].id))
    assert upcoming["game_kind"] == "fantasy" and upcoming["entry_state"] == "not_open"
    assert upcoming["destination"] == f"/leagues/{f.league.id}/weeks/{next_week[1].id}/fantasy"
    assert upcoming["fee"]["destination"] == upcoming["destination"] + "#payment"
    assert f.acquisitions == [] and f.source.calls == []
    assert await f.count(WeeklyFeeObligation) == await f.count(GameOperation) == 0
    assert await f.count(ProviderAttempt) == 0
    async with f.sessions() as db:
        assert not list(await db.scalars(select(ProviderWork)))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hour,minute,group,fantasy_state,next_entry",
    [
        (11, 59, "open", "open", "not_open"),
        (12, 0, "open", "locked", "open"),
        (12, 5, "open", "locked", "open"),
        (14, 29, "open", "locked", "open"),
        (14, 30, "locked", "locked", "open"),
    ],
)
async def test_home_has_all_three_saturday_states_at_both_exact_locks(
    games, hour, minute, group, fantasy_state, next_entry
):
    f = games
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    f.source.clock.now = london_utc(WEEK, hour, minute)
    view = await home(f)
    assert len(view["games"]) == 3
    indexed = {(card["week_id"], card["game_kind"]): card for card in view["games"]}
    assert indexed[str(f.parent.id), "group"]["entry_state"] == group
    assert indexed[str(f.parent.id), "fantasy"]["entry_state"] == fantasy_state
    assert indexed[str(later[1].id), "fantasy"]["entry_state"] == next_entry
    assert indexed[str(f.parent.id), "fantasy"]["result"]["weekly_points"] == 0
    assert f.acquisitions == [] and f.source.calls == []


@pytest.mark.asyncio
async def test_addressed_new_results_never_fall_back_to_another_week_or_member(games):
    f = games
    response = await f.request(
        "GET", path=f"/api/v1/leagues/{f.league.id}/weeks/{f.parent.id}/results"
    )
    assert response.status_code == 200, response.text
    assert response.json()["week_id"] == str(f.parent.id)
    assert response.json()["format"] == "two_game"
    assert response.json()["group"]["result"]["status"] == "no_coupon"
    for path in [
        f"/api/v1/leagues/{uuid.uuid4()}/games",
        f"/api/v1/leagues/{f.league.id}/weeks/{uuid.uuid4()}/results",
    ]:
        refused = await f.request("GET", path=path)
        assert refused.status_code == 404 and refused.json()["detail"]["code"] == "NOT_FOUND"
    foreign = await f.request("GET", path=f"/api/v1/leagues/{f.league.id}/games", player=3)
    assert foreign.status_code == 404
    assert f.source.calls == []


@pytest.mark.asyncio
async def test_invalid_history_cursor_has_scoped_validation_without_provider(games):
    f = games
    for cursor in ["bad!", "e30", "a" * 300]:
        response = await f.request(
            "GET", path=f"/api/v1/leagues/{f.league.id}/games?cursor={cursor}"
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] in {"INVALID_CURSOR", "INVALID_REQUEST"}
    assert f.source.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        123,
        {},
        None,
        [1, "2026-11-21", "bad"],
        [{}, "2026-11-21", "bad"],
        ["bad", 1, "bad"],
        ["bad", "2026-11-21", {}],
        ["one", "two"],
        "abc",
    ],
)
async def test_typed_invalid_cursors_always_refuse_without_server_error(games, bad):
    f = games
    cursor = base64.urlsafe_b64encode(json.dumps(bad).encode()).decode().rstrip("=")
    response = await f.request("GET", path=f"/api/v1/leagues/{f.league.id}/games?cursor={cursor}")
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "INVALID_CURSOR"
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
async def test_locked_group_audience_matches_addressed_game_after_departure_and_late_join(games):
    from src.models.league_membership import LeagueMembership
    from src.models.two_game import MembershipInterval

    f = games
    body = f.body()
    body.pop("odds")
    path = f.path.replace("fantasy", "group")
    saved = await f.request("PUT", path=path + "/pick", body=body)
    assert saved.status_code == 200, saved.text
    f.source.clock.now = london_utc(WEEK, 14, 31)
    async with f.sessions() as db, db.begin():
        departed = await db.scalar(
            select(LeagueMembership).where(
                LeagueMembership.league_id == f.league.id,
                LeagueMembership.player_id == f.players[0].id,
            )
        )
        departed.deleted_at = f.source.clock.now
        interval = await db.scalar(
            select(MembershipInterval).where(
                MembershipInterval.league_id == f.league.id,
                MembershipInterval.player_id == f.players[0].id,
            )
        )
        interval.left_at = f.source.clock.now
        db.add(
            LeagueMembership(
                league_id=f.league.id, player_id=f.players[3].id, joined_at=f.source.clock.now
            )
        )
        db.add(
            MembershipInterval(
                league_id=f.league.id,
                player_id=f.players[3].id,
                joined_at=f.source.clock.now,
                provenance="joined",
            )
        )
    view = await f.request("GET", player=1, path=f"/api/v1/leagues/{f.league.id}/games")
    addressed = await f.request("GET", player=1, path=path)
    assert view.status_code == addressed.status_code == 200
    group = next(c for c in view.json()["games"] if c["game_id"] == str(f.group.id))
    assert group["progress"]["picked_count"] == 1
    for key in ["picked_count", "member_count", "all_picked"]:
        assert addressed.json()["progress"][key] == group["progress"][key]
    assert group["progress"]["member_count"] == 1


async def legacy_before_cutover(f, monkeypatch):
    from sqlalchemy import update

    from src import deps
    from src.main import app
    from src.models.fixture import Fixture
    from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
    from src.models.league_membership import LeagueMembership
    from src.models.ledger import LedgerEntry, LedgerKind
    from src.routers import picks

    label = WEEK - timedelta(days=7)
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(LeagueMembership)
            .where(LeagueMembership.league_id == f.league.id)
            .values(joined_at=london_utc(label - timedelta(days=5)))
        )
        parent = Gameweek(
            league_id=f.league.id,
            starts_on=label,
            status=GameweekStatus.open,
            picks_open_at_utc=london_utc(label - timedelta(days=5)),
            locks_at_utc=london_utc(label, 14, 30),
            number=1,
        )
        fixture = Fixture(
            provider_event_id=f"old-{uuid.uuid4().hex}",
            home="Old Home",
            away="Old Away",
            competition="Synthetic",
            competition_id="synthetic",
            kickoff_utc=london_utc(label, 15),
        )
        db.add_all([parent, fixture])
        await db.flush()
        db.add(GameweekFixture(gameweek_id=parent.id, fixture_id=fixture.id))
        f.league.entry_fee_pence = 100
        db.add(f.league)
        db.add(
            LedgerEntry(
                league_id=f.league.id,
                player_id=f.players[0].id,
                gameweek_id=parent.id,
                kind=LedgerKind.round_due,
                amount_pence=-100,
            )
        )
    monkeypatch.setattr(picks, "_now", f.source.clock)
    monkeypatch.setattr(picks, "AsyncSessionLocal", f.sessions)

    async def provider():
        return f.source.client

    monkeypatch.setitem(app.dependency_overrides, deps.get_odds_provider, provider)
    return parent, fixture


@pytest.mark.asyncio
async def test_c1_to_c6_actual_legacy_and_new_writes_remain_separate(games, monkeypatch):
    from decimal import Decimal

    from sqlalchemy import update

    from src.models.gameweek import GameweekStatus
    from src.models.pick import Pick, PickStatus
    from src.models.two_game import FantasyPick, TwoGame

    f = games
    old, fixture = await legacy_before_cutover(f, monkeypatch)
    f.source.clock.now = london_utc(old.starts_on, 11, 59)
    old_path = f"/api/v1/leagues/{f.league.slug}/picks"
    old_body = dict(fixture_id=str(fixture.id), market="MATCH_ODDS", outcome="HOME", odds="2.15")
    before = await home(f)
    assert len(before["legacy_rounds"]) == 1
    assert before["legacy_rounds"][0]["can_pick"]
    assert before["legacy_rounds"][0]["fee"]["round_due_pence"] == 100
    assert all(c["week_id"] != str(old.id) for c in before["games"])
    assert (
        next(c for c in before["games"] if c["game_kind"] == "fantasy")["entry_state"] == "not_open"
    )
    early = await f.save()
    assert early.status_code == 409 and early.json()["detail"]["code"] == "NOT_OPEN"
    assert f.source.calls == [] and await f.count(WeeklyFeeObligation) == 0
    legacy = await f.request("POST", path=old_path, body=old_body)
    assert legacy.status_code == 201, legacy.text
    legacy_read_path = f"/api/v1/leagues/{f.league.slug}/gameweeks/{old.id}/pick"
    legacy_before = await f.request("GET", path=legacy_read_path)
    assert legacy_before.status_code == 200, legacy_before.text
    f.source.clock.now = london_utc(old.starts_on, 12, 5)
    modern = await f.save()
    assert modern.status_code == 200, modern.text
    simultaneous = await home(f)
    assert simultaneous["legacy_rounds"][0]["can_pick"]
    card = next(c for c in simultaneous["games"] if c["game_id"] == str(f.game.id))
    assert card["entry_state"] == "open" and card["progress"]["slots_filled"] == 1
    assert card["slots"][0]["operation_id"] == modern.json()["operation_id"]
    assert card["result"]["weekly_points"] == 0 and card["result"]["provisional"]
    legacy_after = await f.request("GET", path=legacy_read_path)
    assert legacy_after.json() == legacy_before.json()
    calls, fees = len(f.source.calls), await f.count(WeeklyFeeObligation)
    unsupported = await f.request(
        "POST", path=old_path, body={**old_body, "fixture_id": str(f.fixtures[6].id)}
    )
    assert unsupported.status_code == 409, unsupported.text
    assert unsupported.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"
    assert (
        unsupported.json()["detail"]["destination"]
        == f"/leagues/{f.league.id}/weeks/{f.parent.id}/fantasy"
    )
    new_to_old = await f.request(
        "GET", path=f"/api/v1/leagues/{f.league.id}/weeks/{old.id}/games/fantasy"
    )
    assert new_to_old.status_code == 409, new_to_old.text
    assert (
        new_to_old.json()["detail"]["destination"]
        == f"/leagues/{f.league.slug}/predictions?gw={old.id}#coupon"
    )
    assert len(f.source.calls) == calls and await f.count(WeeklyFeeObligation) == fees
    f.source.clock.now = london_utc(old.starts_on, 14, 30)
    locked = await home(f)
    assert not locked["legacy_rounds"][0]["can_pick"]
    assert (
        next(c for c in locked["games"] if c["game_id"] == str(f.game.id))["entry_state"] == "open"
    )
    async with f.sessions() as db, db.begin():
        old.status = GameweekStatus.settled
        db.add(old)
        pick = await db.scalar(select(Pick).where(Pick.gameweek_id == old.id))
        assert pick.odds_at_pick == Decimal("2.15")
        pick.status, pick.points_awarded = PickStatus.won, 22
        await db.execute(
            update(FantasyPick)
            .where(FantasyPick.game_id == f.game.id)
            .values(status="won", points_awarded=22)
        )
        await db.execute(
            update(TwoGame)
            .where(TwoGame.id == f.game.id)
            .values(status="settled", finalized_at=london_utc(WEEK + timedelta(days=2)))
        )
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    f.source.clock.now = london_utc(WEEK + timedelta(days=2), 12, 5)
    final = await home(f)
    assert {c["game_id"] for c in final["games"]} >= {
        str(f.game.id),
        str(f.group.id),
        str(later[2].id),
    }
    assert next(c for c in final["legacy_rounds"] if c["week_id"] == str(old.id))["archived"]
    assert final["season_stats"]["total_points"] == 44
    assert len([w for w in final["weekly_form"] if w["week_id"] == str(f.parent.id)]) == 1
    assert {w["format"] for w in final["weekly_form"]} == {"legacy", "two_game"}
    assert len(f.source.calls) == calls


@pytest.mark.asyncio
async def test_batched_fees_match_single_target_fifo_and_gets_never_materialise(games):
    from sqlalchemy import update

    from src.models.ledger import LedgerEntry, LedgerKind
    from src.services.weekly_fees import project_fees

    f = games
    later = await entries.additional_week(f, WEEK + timedelta(days=7))
    distant = await long_open_week(f, WEEK + timedelta(days=21))
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(LedgerEntry)
            .where(
                LedgerEntry.league_id == f.league.id,
                LedgerEntry.player_id == f.players[0].id,
                LedgerEntry.kind == LedgerKind.payment,
            )
            .values(amount_pence=100)
        )
        # The distant child was announced with its long opening offset at creation.
    f.source.clock.now = london_utc(WEEK, 12, 5)
    view = await home(f)
    by_id = {c["game_id"]: c for c in view["games"]}
    assert by_id[str(f.group.id)]["fee"]["paid_through"]
    assert not by_id[str(later[2].id)]["fee"]["paid_through"]
    assert by_id[str(distant[2].id)]["fee"]["amount_owed_pence"] == 300
    async with f.sessions() as db:
        for card in view["games"]:
            from src.models.gameweek import Gameweek

            parent = await db.get(Gameweek, uuid.UUID(card["week_id"]))
            expected = (
                (
                    await project_fees(
                        db, f.league, f.players[0].id, parent.starts_on, f.source.clock.now
                    )
                )
                .for_week(parent)
                .model_dump(mode="json")
            )
            actual = dict(card["fee"])
            expected.pop("destination")
            actual.pop("destination")
            assert actual == expected
    assert await f.count(WeeklyFeeObligation) == await f.count(GameOperation) == 0
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
async def test_query_count_is_constant_for_five_leagues_and_many_open_games(games, db_engine):
    from sqlalchemy import event

    f = games
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", record)
    try:
        await home(f)
        single = len(statements)
        for i in range(4):
            await entries.additional_week(f, WEEK, another_league=True)
        for i in range(1, 5):
            await long_open_week(f, WEEK + timedelta(days=7 * i))
        statements.clear()
        response = await f.request("GET", path="/api/v1/me/games")
        assert response.status_code == 200, response.text
        assert len(response.json()["leagues"]) == 5
        assert (
            len(
                next(
                    league
                    for league in response.json()["leagues"]
                    if league["league_id"] == str(f.league.id)
                )["games"]
            )
            == 10
        )
        assert len(statements) == single, (single, len(statements))
        assert single <= 25
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", record)
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
async def test_archive_pages_parent_keys_and_keeps_both_children_and_all_actionables(games):
    from sqlalchemy import update

    from src.models.two_game import TwoGame

    f = games
    parents = [f.parent]
    for i in range(1, 5):
        parents.append((await entries.additional_week(f, WEEK + timedelta(days=7 * i)))[1])
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(TwoGame)
            .where(TwoGame.league_id == f.league.id)
            .values(status="settled", finalized_at=london_utc(WEEK + timedelta(days=31)))
        )
    f.source.clock.now = london_utc(WEEK + timedelta(days=35), 11)
    live = await entries.additional_week(f, WEEK + timedelta(days=35))
    path = f"/api/v1/leagues/{f.league.id}/games?page_size=2"
    seen = []
    while True:
        response = await f.request("GET", path=path)
        assert response.status_code == 200, response.text
        view = response.json()
        assert {str(live[2].id)} <= {c["game_id"] for c in view["games"] if not c["archived"]}
        archived = [c for c in view["games"] if c["archived"]]
        by_parent = {}
        for card in archived:
            by_parent.setdefault(card["week_id"], set()).add(card["game_kind"])
        assert all(kinds == {"group", "fantasy"} for kinds in by_parent.values())
        assert not set(seen) & set(by_parent)
        seen.extend(by_parent)
        if not view["next_cursor"]:
            break
        path = f"/api/v1/leagues/{f.league.id}/games?page_size=2&cursor={view['next_cursor']}"
    assert set(seen) == {str(parent.id) for parent in parents}
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["global", "league", "suspended"])
async def test_activation_and_suspension_never_create_data_or_price(games, monkeypatch, switch):
    from src.models.two_game import TwoGameRollout

    f = games
    if switch == "global":
        monkeypatch.setattr(settings, "two_games_enabled", False)
    else:
        async with f.sessions() as db, db.begin():
            rollout = await db.get(TwoGameRollout, f.league.id)
            if switch == "league":
                rollout.enabled = False
            else:
                rollout.suspended = True
    view = await home(f)
    if switch == "suspended":
        assert view["suspended"]
        assert view["games"] and all(c["entry_state"] == "suspended" for c in view["games"])
    else:
        assert not view["two_games_enabled"] and view["games"] == []
        response = await f.request(
            "GET", path=f"/api/v1/leagues/{f.league.id}/weeks/{f.parent.id}/results"
        )
        assert response.status_code == 404
    assert await f.count(WeeklyFeeObligation) == await f.count(GameOperation) == 0
    assert f.source.calls == f.acquisitions == []


async def long_open_week(f, label):
    from src.models.two_game import TwoGame
    from src.services.two_game_storage import ensure_two_game_week

    async with f.sessions() as db, db.begin():
        parent = await ensure_two_game_week(db, f.league.id, label)
        fantasy = TwoGame(
            league_id=f.league.id,
            week_id=parent.id,
            kind="fantasy",
            opens_at=london_utc(WEEK - timedelta(days=7), 12),
            locks_at=london_utc(label, 12),
            window_start=london_utc(label, 12, 30),
            window_end=london_utc(label + timedelta(days=2)),
        )
        group = TwoGame(
            league_id=f.league.id,
            week_id=parent.id,
            kind="group",
            opens_at=london_utc(WEEK - timedelta(days=5)),
            locks_at=london_utc(label, 14, 30),
            window_start=london_utc(label, 15),
            window_end=london_utc(label, 15),
        )
        db.add_all([fantasy, group])
    return f.league, parent, fantasy, []


@pytest.mark.asyncio
async def test_weekly_form_aggregates_six_legs_and_distinguishes_no_entry_void_and_late_join(games):
    from sqlalchemy import update

    from src.models.league_membership import LeagueMembership
    from src.models.two_game import FantasyPick, MembershipInterval, TwoGame
    from src.services.weekly_fees import bill_all

    f = games
    for slot in range(1, 7):
        saved = await f.save(slot, f.body(slot - 1))
        assert saved.status_code == 200, saved.text
    assert (await f.save(player=1)).status_code == 200
    await bill_all(f.sessions, f.source.clock.now)
    async with f.sessions() as db, db.begin():
        picks = list(await db.scalars(select(FantasyPick).where(FantasyPick.game_id == f.game.id)))
        for pick in picks:
            if pick.player_id == f.players[1].id:
                pick.status, pick.points_awarded = "void", 0
            elif pick.slot in (1, 4):
                pick.status, pick.points_awarded = "won", 22
            else:
                pick.status, pick.points_awarded = ("lost" if pick.slot % 2 else "void"), 0
        await db.execute(
            update(TwoGame)
            .where(TwoGame.id == f.game.id)
            .values(status="settled", finalized_at=london_utc(WEEK + timedelta(days=2)))
        )
        db.add(
            LeagueMembership(
                league_id=f.league.id, player_id=f.players[3].id, joined_at=london_utc(WEEK, 12, 1)
            )
        )
        db.add(
            MembershipInterval(
                league_id=f.league.id,
                player_id=f.players[3].id,
                joined_at=london_utc(WEEK, 12, 1),
                provenance="joined",
            )
        )
    f.source.clock.now = london_utc(WEEK + timedelta(days=2), 0, 1)
    for player, status, filled, points in [
        (0, "scored", 6, 44),
        (1, "all_void", 1, 0),
        (2, "no_entry", 0, 0),
    ]:
        response = await f.request(
            "GET", player=player, path=f"/api/v1/leagues/{f.league.id}/games"
        )
        assert response.status_code == 200, response.text
        view = response.json()
        forms = [form for form in view["weekly_form"] if form["week_id"] == str(f.parent.id)]
        assert len(forms) == 1
        assert (forms[0]["status"], forms[0]["slots_filled"], forms[0]["weekly_points"]) == (
            status,
            filled,
            points,
        )
        assert view["season_stats"]["total_points"] == points
        card = next(card for card in view["games"] if card["game_id"] == str(f.game.id))
        assert str(f.players[3].id) not in {member["player_id"] for member in card["members"]}
    late = await f.request("GET", player=3, path=f"/api/v1/leagues/{f.league.id}/games")
    assert late.status_code == 200 and late.json()["weekly_form"] == []


@pytest.mark.asyncio
async def test_http_reads_use_one_read_only_repeatable_snapshot(games, monkeypatch):
    from sqlalchemy import text, update
    from sqlalchemy.exc import DBAPIError

    from src.models.ledger import LedgerEntry, LedgerKind
    from src.models.profile import Profile
    from src.services import two_game_reads as service

    f = games
    original = service.project_read_data
    checked = []

    async def verify(db, data, **kwargs):
        assert await db.scalar(text("SHOW transaction_read_only")) == "on"
        assert await db.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        before = await db.scalar(
            select(LedgerEntry.amount_pence).where(
                LedgerEntry.league_id == f.league.id,
                LedgerEntry.player_id == f.players[0].id,
                LedgerEntry.kind == LedgerKind.payment,
            )
        )
        async with f.sessions() as writer, writer.begin():
            await writer.execute(
                update(LedgerEntry)
                .where(
                    LedgerEntry.league_id == f.league.id,
                    LedgerEntry.player_id == f.players[0].id,
                    LedgerEntry.kind == LedgerKind.payment,
                )
                .values(amount_pence=100)
            )
        assert (
            await db.scalar(
                select(LedgerEntry.amount_pence).where(
                    LedgerEntry.league_id == f.league.id,
                    LedgerEntry.player_id == f.players[0].id,
                    LedgerEntry.kind == LedgerKind.payment,
                )
            )
            == before
        )
        with pytest.raises(DBAPIError) as refused:
            async with db.begin_nested():
                await db.execute(
                    update(Profile)
                    .where(Profile.id == f.players[0].id)
                    .values(display_name="forbidden")
                )
        assert refused.value.orig.sqlstate == "25006"
        checked.append(True)
        return await original(db, data, **kwargs)

    monkeypatch.setattr(service, "project_read_data", verify)
    view = await home(f)
    assert checked == [True] and view["games"]
    async with f.sessions() as db:
        assert (await db.get(Profile, f.players[0].id)).display_name != "forbidden"
    assert f.source.calls == f.acquisitions == []


@pytest.mark.asyncio
async def test_c3_concurrent_legacy_replacement_and_next_fantasy_save_use_exact_targets(
    games, monkeypatch
):
    import asyncio

    from src.models.pick import Pick

    f = games
    old, fixture = await legacy_before_cutover(f, monkeypatch)
    f.source.clock.now = london_utc(old.starts_on, 11, 59)
    path = f"/api/v1/leagues/{f.league.slug}/picks"
    body = dict(fixture_id=str(fixture.id), market="MATCH_ODDS", outcome="HOME", odds="2.15")
    initial = await f.request("POST", path=path, body=body)
    assert initial.status_code == 201, initial.text
    f.source.clock.now = london_utc(old.starts_on, 12, 5)
    legacy, modern = await asyncio.gather(
        f.request("POST", path=path, body={**body, "outcome": "AWAY", "odds": "4.00"}), f.save()
    )
    assert legacy.status_code == 201, legacy.text
    assert modern.status_code == 200, modern.text
    async with f.sessions() as db:
        pick = await db.scalar(select(Pick).where(Pick.gameweek_id == old.id))
        assert str(pick.id) == initial.json()["id"] == legacy.json()["id"]
        assert pick.outcome.value == "AWAY" and str(pick.odds_at_pick) == "4.00"
        assert pick.gameweek_id == old.id and pick.player_id == f.players[0].id
    view = await home(f)
    assert view["legacy_rounds"][0]["my_pick"]["outcome"] == "AWAY"
    card = next(card for card in view["games"] if card["game_id"] == str(f.game.id))
    assert card["slots"][0]["operation_id"] == modern.json()["operation_id"]
    assert card["slots"][0]["pick"]["frozen_odds"] == "2.1500"
    assert card["result"]["weekly_points"] == 0
    assert await f.count(GameOperation) == 1 and await f.count(WeeklyFeeObligation) == 1


def test_pure_fee_projection_and_payments_boot_do_not_load_api_settings():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("JWT_", "MONZO_", "VAPID_"))
    }
    env.update(
        ENVIRONMENT="production",
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        DATABASE_URL="postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/synthetic",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from src.services.weekly_fees import project_loaded_fees; "
            "assert 'src.config' not in sys.modules; "
            "import src.payments_service.app; import src.payments_service.ingest; "
            "assert 'src.config' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["global", "league", "suspended"])
async def test_inactive_hides_new_form_links_but_retains_earned_season_points(
    games, monkeypatch, switch
):
    from sqlalchemy import update

    from src.models.two_game import FantasyPick, TwoGame, TwoGameRollout

    f = games
    assert (await f.save()).status_code == 200
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(FantasyPick)
            .where(FantasyPick.game_id == f.game.id)
            .values(status="won", points_awarded=22)
        )
        await db.execute(
            update(TwoGame)
            .where(TwoGame.id == f.game.id)
            .values(status="settled", finalized_at=london_utc(WEEK + timedelta(days=2)))
        )
        rollout = await db.get(TwoGameRollout, f.league.id)
        if switch == "league":
            rollout.enabled = False
        if switch == "suspended":
            rollout.suspended = True
    if switch == "global":
        monkeypatch.setattr(settings, "two_games_enabled", False)
    f.source.clock.now = london_utc(WEEK + timedelta(days=2), 0, 1)
    view = await home(f)
    assert view["season_stats"]["total_points"] == 22
    if switch == "suspended":
        assert view["games"] and any(form["format"] == "two_game" for form in view["weekly_form"])
    else:
        assert view["games"] == []
        assert all(form["format"] == "legacy" for form in view["weekly_form"])
