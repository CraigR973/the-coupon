"""Owner corrections: ordinary standings and profiles consume real mixed history."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select, update

from src.config import settings
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.two_game import FantasyPick, MembershipInterval, TwoGame, TwoGameRollout
from src.services.scoring import standings
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import bill_all
from tests import test_two_game_fantasy as entries
from tests import two_game_test_store as stores

baseline_db_engine = stores.baseline_db_engine
result_store = stores.result_store
db_engine = stores.db_engine
fantasy = entries.fantasy
WEEK = entries.WEEK


async def legacy_round(f, weeks_ago):
    label = WEEK - timedelta(weeks=weeks_ago)
    async with f.sessions() as db, db.begin():
        old = Gameweek(
            league_id=f.league.id,
            starts_on=label,
            status=GameweekStatus.settled,
            locks_at_utc=london_utc(label, 14, 30),
        )
        db.add(old)
        await db.flush()
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
                runner_name="Legacy Home",
                odds_at_pick=Decimal("2.00"),
                status=PickStatus.won,
                points_awarded=20,
            )
        )
    return old.id


async def table(f):
    response = await f.request("GET", path=f"/api/v1/leagues/{f.league.slug}/standings")
    assert response.status_code == 200, response.text
    return {row["player_id"]: row for row in response.json()}


async def finalise(f):
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(TwoGame)
            .where(TwoGame.id == f.game.id)
            .values(status="settled", finalized_at=london_utc(WEEK + timedelta(days=2)))
        )


@pytest.mark.asyncio
async def test_ordinary_standings_aggregate_six_fantasy_legs_before_five_week_limit(fantasy):
    f = fantasy
    old_ids = [await legacy_round(f, n) for n in range(1, 6)]
    for slot in range(1, 7):
        response = await f.save(slot, f.body(slot - 1))
        assert response.status_code == 200, response.text
    group = await f.request(
        "PUT",
        body={k: v for k, v in f.body().items() if k != "odds"},
        path=f.path.replace("fantasy", "group") + "/pick",
    )
    assert group.status_code == 200, group.text
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(FantasyPick)
            .where(FantasyPick.game_id == f.game.id)
            .values(status="won", points_awarded=22)
        )
        await db.execute(
            update(TwoGame)
            .where(TwoGame.id == f.group.id)
            .values(status="settled", finalized_at=london_utc(WEEK))
        )
    await finalise(f)
    own = (await table(f))[str(f.players[0].id)]
    form = own["recent_form"]
    assert len(form) == 5
    assert [row["gameweek_id"] for row in form] == [str(f.parent.id), *map(str, old_ids[:4])]
    assert str(old_ids[4]) not in {row["gameweek_id"] for row in form}
    assert form[0] == {
        "gameweek_id": str(f.parent.id),
        "starts_on": WEEK.isoformat(),
        "status": "scored",
        "points": 132,
        "format": "two_game",
        "game_kind": "fantasy",
        "slots_filled": 6,
        "destination": f"/leagues/{f.league.id}/weeks/{f.parent.id}/fantasy",
    }
    assert all(row["status"] == "won" and row["points"] == 20 for row in form[1:])
    assert form[1]["destination"] == f"/leagues/{f.league.slug}/predictions?gw={old_ids[0]}#coupon"
    assert (own["total_points"], own["picks_played"], own["picks_won"]) == (232, 11, 11)
    statements = []

    def count_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = f.sessions.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", count_select)
    try:
        async with f.sessions() as db:
            await standings(db, f.league.id, season=2026)
        assert len(statements) == 2
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_select)


@pytest.mark.asyncio
async def test_ordinary_fantasy_form_distinguishes_no_entry_void_and_late_join_when_disabled(
    fantasy, monkeypatch
):
    f = fantasy
    assert (await f.save()).status_code == 200
    assert (await f.save(player=1)).status_code == 200
    await bill_all(f.sessions, f.source.clock.now)
    async with f.sessions() as db, db.begin():
        for pick in await db.scalars(select(FantasyPick).where(FantasyPick.game_id == f.game.id)):
            pick.status = "won" if pick.player_id == f.players[0].id else "void"
            pick.points_awarded = 22 if pick.status == "won" else 0
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
        await db.execute(
            update(TwoGameRollout)
            .where(TwoGameRollout.league_id == f.league.id)
            .values(enabled=False)
        )
    await finalise(f)
    monkeypatch.setattr(settings, "two_games_enabled", False)
    rows = await table(f)
    for player, status, filled, points in [
        (0, "scored", 1, 22),
        (1, "all_void", 1, 0),
        (2, "no_entry", 0, 0),
    ]:
        own = rows[str(f.players[player].id)]
        assert len(own["recent_form"]) == 1
        item = own["recent_form"][0]
        assert (item["status"], item["slots_filled"], item["points"]) == (status, filled, points)
        assert item["destination"] == f"/leagues/{f.league.id}/weeks/{f.parent.id}/fantasy"
        assert own["total_points"] == points
    assert rows[str(f.players[3].id)]["recent_form"] == []


@pytest.mark.asyncio
async def test_unfinalised_fantasy_does_not_displace_settled_legacy_form(fantasy):
    f = fantasy
    old = await legacy_round(f, 1)
    assert (await f.save()).status_code == 200
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(FantasyPick)
            .where(FantasyPick.game_id == f.game.id)
            .values(status="won", points_awarded=22)
        )
    own = (await table(f))[str(f.players[0].id)]
    assert own["total_points"] == 42
    assert [item["gameweek_id"] for item in own["recent_form"]] == [str(old)]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_legacy", [False, True])
async def test_profile_history_matches_resolved_fantasy_statistics_before_week_finality(
    fantasy, with_legacy
):
    f = fantasy
    old = await legacy_round(f, 1) if with_legacy else None
    assert (await f.save()).status_code == 200
    assert (await f.save(2, f.body(1))).status_code == 200
    group = await f.request(
        "PUT",
        body={k: v for k, v in f.body().items() if k != "odds"},
        path=f.path.replace("fantasy", "group") + "/pick",
    )
    assert group.status_code == 200, group.text
    async with f.sessions() as db, db.begin():
        await db.execute(
            update(FantasyPick)
            .where(FantasyPick.game_id == f.game.id, FantasyPick.slot == 1)
            .values(status="won", points_awarded=22)
        )
        game = await db.get(TwoGame, f.game.id)
        assert game.finalized_at is None
    response = await f.request(
        "GET", path=f"/api/v1/leagues/{f.league.slug}/players/{f.players[0].id}/profile"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_points"], body["picks_won"], body["picks_played"]) == (
        42 if with_legacy else 22,
        2 if with_legacy else 1,
        2 if with_legacy else 1,
    )
    assert sum(item["points_awarded"] or 0 for item in body["history"]) == body["total_points"]
    assert len(body["history"]) == (2 if with_legacy else 1)
    leg = body["history"][0]
    assert (leg["format"], leg["game_kind"], leg["game_id"], leg["slot"]) == (
        "two_game",
        "fantasy",
        str(f.game.id),
        1,
    )
    assert (leg["gameweek_id"], leg["fixture_id"]) == (str(f.parent.id), str(f.fixtures[0].id))
    assert (leg["odds"], leg["frozen_odds"], leg["status"], leg["points_awarded"]) == (
        2.15,
        "2.1500",
        "won",
        22,
    )
    assert leg["destination"] == f"/leagues/{f.league.id}/weeks/{f.parent.id}/fantasy"
    if with_legacy:
        legacy = body["history"][1]
        assert (
            legacy["gameweek_id"],
            legacy["odds"],
            legacy["status"],
            legacy["points_awarded"],
        ) == (str(old), 2.0, "won", 20)
        assert legacy["game_kind"] == "legacy" and legacy["game_id"] is None
        assert legacy["destination"] == f"/leagues/{f.league.slug}/predictions?gw={old}#coupon"
