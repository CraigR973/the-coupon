"""Batch 134 — a mis-settled pick is corrected through the API, not a script.

The row's verification: correcting a settled pick updates its points *and the standings*
and writes an audit row; a non-site-admin is refused; the correction is idempotent. The
standings half is read back through :func:`~src.services.scoring.standings`, the same
function the leaderboard serves, so "recomputes the affected standings" is shown rather
than argued.

Postgres-backed. Each test builds its own league, as ``test_admin_operations`` does.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, AuditLog
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.football_provider import season_for
from src.services.scoring import standings
from tests.season_dates import season_anchor

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The round's Saturday. Its season is passed explicitly, so the test does not start
#: failing when the calendar moves past it.
ROUND_DAY = date(2027, 3, 6)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(role: UserRole = UserRole.player) -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=f"{role.value}-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=role,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _settled_pick(
    member: Profile, *, status: PickStatus = PickStatus.lost, points: int = 0
) -> Pick:
    """A league whose round settled with one home-win pick at 2.50, recorded as ``status``.

    The shape the batch exists for: a week members have already seen, scored wrongly.
    """
    tag = uuid.uuid4().hex[:8]
    kickoff = datetime(ROUND_DAY.year, ROUND_DAY.month, ROUND_DAY.day, 15, 0)
    async with AsyncSessionLocal() as session:
        league = League(slug=f"fix-{tag}", name=f"Fix {tag}", created_by=member.id)
        session.add(league)
        await session.flush()
        session.add(
            LeagueMembership(league_id=league.id, player_id=member.id, role=LeagueMemberRole.admin)
        )
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=ROUND_DAY,
            status=GameweekStatus.settled,
            locks_at_utc=kickoff - timedelta(minutes=30),
        )
        fixture = Fixture(
            provider_event_id=f"ev-{tag}",
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=kickoff,
            competition="Scottish League Two",
            competition_id=f"sl2-{tag}",
        )
        session.add_all([gameweek, fixture])
        await session.flush()
        session.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
        pick = Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=member.id,
            fixture_id=fixture.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar Athletic",
            odds_at_pick=Decimal("2.50"),
            status=status,
            points_awarded=points,
        )
        session.add(pick)
        await session.commit()
        await session.refresh(pick)
        return pick


async def _reload(pick_id: uuid.UUID) -> Pick:
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(Pick).where(Pick.id == pick_id))).scalar_one()


async def _season_points(league_id: uuid.UUID, player_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        table = await standings(session, league_id, season=season_for(ROUND_DAY))
    return next(row.total_points for row in table if row.player_id == str(player_id))


async def _corrections(pick_id: uuid.UUID) -> list[AuditLog]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(AuditLog).where(AuditLog.target_table == "picks", AuditLog.target_id == pick_id)
        )
        return list(rows.scalars().all())


async def test_a_correction_moves_the_pick_and_the_table_and_is_audited(
    client: AsyncClient,
) -> None:
    """Recorded lost, actually won 2-1: 25 points, on the pick and on the leaderboard."""
    admin = await _profile(UserRole.admin)
    member = await _profile()
    pick = await _settled_pick(member)
    assert await _season_points(pick.league_id, member.id) == 0

    response = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct",
        json={"home_goals": 2, "away_goals": 1, "reason": "Provider settled it as a draw"},
        headers=_auth(admin),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "pick_id": str(pick.id),
        "changed": True,
        "status_before": "lost",
        "points_before": 0,
        "status": "won",
        "points": 25,
    }
    corrected = await _reload(pick.id)
    assert (corrected.status, corrected.points_awarded) == (PickStatus.won, 25)
    assert await _season_points(pick.league_id, member.id) == 25

    (audit,) = await _corrections(pick.id)
    assert audit.action_type == ActionType.league_updated
    assert audit.actor_id == admin.id
    assert audit.changes == {
        "action": "pick_corrected",
        "league_id": str(pick.league_id),
        "gameweek_id": str(pick.gameweek_id),
        "result": {"home_goals": 2, "away_goals": 1},
        "before": {"status": "lost", "points": 0},
        "after": {"status": "won", "points": 25},
        "reason": "Provider settled it as a draw",
    }


async def test_the_same_correction_twice_changes_nothing_the_second_time(
    client: AsyncClient,
) -> None:
    admin = await _profile(UserRole.admin)
    member = await _profile()
    pick = await _settled_pick(member)
    body = {"home_goals": 2, "away_goals": 1, "reason": "Provider settled it as a draw"}

    first = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct", json=body, headers=_auth(admin)
    )
    second = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct", json=body, headers=_auth(admin)
    )

    assert first.json()["changed"] is True
    assert second.status_code == 200
    assert second.json()["changed"] is False
    assert second.json()["status"] == second.json()["status_before"] == "won"
    assert len(await _corrections(pick.id)) == 1, "a repeat must not write a second audit row"
    assert await _season_points(pick.league_id, member.id) == 25


async def test_a_member_who_runs_the_league_is_still_refused(client: AsyncClient) -> None:
    """Site admins only. The member here is their own league's admin, and that is not
    enough: correcting scores is not a league-level power."""
    member = await _profile()
    pick = await _settled_pick(member)

    response = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct",
        json={"home_goals": 2, "away_goals": 1, "reason": "I think I won"},
        headers=_auth(member),
    )

    assert response.status_code == 403
    unchanged = await _reload(pick.id)
    assert (unchanged.status, unchanged.points_awarded) == (PickStatus.lost, 0)
    assert await _corrections(pick.id) == []


async def test_a_void_correction_scores_nothing_and_loses_nothing(client: AsyncClient) -> None:
    admin = await _profile(UserRole.admin)
    member = await _profile()
    pick = await _settled_pick(member, status=PickStatus.won, points=25)

    response = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct",
        json={"void": True, "reason": "Match abandoned after it was settled"},
        headers=_auth(admin),
    )

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["points"]) == ("void", 0)
    assert await _season_points(pick.league_id, member.id) == 0


async def test_a_pending_pick_is_settled_not_corrected(client: AsyncClient) -> None:
    admin = await _profile(UserRole.admin)
    member = await _profile()
    pick = await _settled_pick(member, status=PickStatus.pending, points=0)

    response = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct",
        json={"home_goals": 1, "away_goals": 0, "reason": "Early"},
        headers=_auth(admin),
    )

    assert response.status_code == 409
    assert (await _reload(pick.id)).status == PickStatus.pending


async def test_a_correction_needs_both_scores_or_void(client: AsyncClient) -> None:
    admin = await _profile(UserRole.admin)
    member = await _profile()
    pick = await _settled_pick(member)

    response = await client.post(
        f"/api/v1/admin/picks/{pick.id}/correct",
        json={"home_goals": 2, "reason": "Half a result"},
        headers=_auth(admin),
    )

    assert response.status_code == 422
    assert await _corrections(pick.id) == []


# ── Batch 187: a wrong result, corrected once for every league ─────────────────

SEND = "src.services.notification_triggers.send_notification"
REASON = "Provider recorded it 2-1; it finished 1-1"
MATCH_COMPETITION = "scotland-league-two"


def _recorder(sent: list[dict[str, Any]]) -> Callable[..., Coroutine[Any, Any, int]]:
    """Stands in for ``send_notification`` and writes down what it was asked to deliver."""

    async def send(
        db: Any,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        tag: str | None = None,
        timezone_name: str = "UTC",
        now_utc: datetime | None = None,
        league_id: uuid.UUID | None = None,
    ) -> int:
        sent.append({"user_id": user_id, "body": body, "tag": tag, "league_id": league_id})
        return 1

    return send


@dataclass
class _Match:
    admin: Profile
    alice: Profile
    bob: Profile
    carol: Profile
    first: League
    second: League
    first_round: Gameweek
    second_round: Gameweek
    fixture: Fixture
    picks: dict[str, Pick]


async def _one_match_in_two_leagues() -> _Match:
    """One settled match on two leagues' cards — committed, in the season being played.

    Alice plays in both. In the first league she took the home win at 2.50 (won 25) and Bob
    the draw at 3.40 (lost); in the second she took the away win at 4.00 (lost) and Carol
    the home win at 1.80 (won 18). The provider had it 2-1; it finished 1-1.
    """
    tag = uuid.uuid4().hex[:8]
    day = season_anchor(days_of_room=9) - timedelta(days=2)
    kickoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    admin = await _profile(UserRole.admin)
    alice, bob, carol = await _profile(), await _profile(), await _profile()
    async with AsyncSessionLocal() as session:
        first = League(slug=f"fixa-{tag}", name=f"First {tag}", created_by=alice.id)
        second = League(slug=f"fixb-{tag}", name=f"Second {tag}", created_by=alice.id)
        fixture = Fixture(
            provider_event_id=f"ev-b187-{tag}",
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=kickoff,
            competition="Scottish League Two",
            # One fixed competition for every match these tests commit: the pool's distinct
            # competitions are what `test_request_budget` holds to the measured catalogue.
            competition_id=MATCH_COMPETITION,
        )
        session.add_all([first, second, fixture])
        await session.flush()
        for league, members in ((first, (alice, bob)), (second, (alice, carol))):
            for member in members:
                session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        rounds = {}
        for league in (first, second):
            gameweek = Gameweek(
                league_id=league.id,
                starts_on=day,
                number=12,
                status=GameweekStatus.settled,
                locks_at_utc=kickoff - timedelta(minutes=30),
            )
            session.add(gameweek)
            await session.flush()
            session.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
            rounds[league.id] = gameweek
        picks = {}
        for key, league, member, outcome, odds, status, points in (
            ("alice_first", first, alice, PickOutcome.HOME, "2.50", PickStatus.won, 25),
            ("bob", first, bob, PickOutcome.DRAW, "3.40", PickStatus.lost, 0),
            ("alice_second", second, alice, PickOutcome.AWAY, "4.00", PickStatus.lost, 0),
            ("carol", second, carol, PickOutcome.HOME, "1.80", PickStatus.won, 18),
        ):
            pick = Pick(
                league_id=league.id,
                gameweek_id=rounds[league.id].id,
                player_id=member.id,
                fixture_id=fixture.id,
                market=PickMarket.MATCH_ODDS,
                outcome=outcome,
                runner_name=outcome.value,
                odds_at_pick=Decimal(odds),
                status=status,
                points_awarded=points,
            )
            session.add(pick)
            picks[key] = pick
        await session.commit()
        return _Match(
            admin,
            alice,
            bob,
            carol,
            first,
            second,
            rounds[first.id],
            rounds[second.id],
            fixture,
            picks,
        )


async def _pending_only_match() -> Pick:
    """A match whose only pick has not settled — nothing a correction may touch."""
    tag = uuid.uuid4().hex[:8]
    member = await _profile()
    async with AsyncSessionLocal() as session:
        league = League(slug=f"fixp-{tag}", name=f"Pending {tag}", created_by=member.id)
        fixture = Fixture(
            provider_event_id=f"ev-b187p-{tag}",
            home="Arbroath",
            away="Montrose",
            kickoff_utc=datetime.now(UTC).replace(tzinfo=None),
            competition="Scottish League Two",
            competition_id=MATCH_COMPETITION,
        )
        session.add_all([league, fixture])
        await session.flush()
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=season_anchor(days_of_room=9),
            status=GameweekStatus.locked,
            locks_at_utc=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
        )
        session.add(gameweek)
        await session.flush()
        pick = Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=member.id,
            fixture_id=fixture.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Arbroath",
            odds_at_pick=Decimal("1.95"),
        )
        session.add(pick)
        await session.commit()
        return pick


async def _correct(client: AsyncClient, match: _Match, body: dict[str, Any]) -> Any:
    return await client.post(
        f"/api/v1/admin/fixtures/{match.fixture.id}/correct", json=body, headers=_auth(match.admin)
    )


async def _points(league: League, member: Profile, day: date) -> int:
    async with AsyncSessionLocal() as session:
        table = await standings(session, league.id, season=season_for(day))
    return next(row.total_points for row in table if row.player_id == str(member.id))


async def test_a_fixture_correction_moves_every_league_and_tells_each_changed_member(
    client: AsyncClient,
) -> None:
    """The owner's decision: one score entered, every settled pick on the match re-scored.

    Standings, coupons, results and career figures agree in both leagues afterwards, each
    league's log carries its own row, and exactly the three members whose result moved are
    re-sent their settle line — Alice's second-league pick lost either way, so it is not.
    """
    match = await _one_match_in_two_leagues()
    day = match.first_round.starts_on

    sent: list[dict[str, Any]] = []
    with patch(SEND, new=_recorder(sent)):
        response = await _correct(
            client, match, {"home_goals": 1, "away_goals": 1, "reason": REASON}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["picks_checked"] == 4
    assert body["leagues_audited"] == sorted([match.first.slug, match.second.slug])
    assert body["members_told"] == 3
    assert {(entry["pick_id"], entry["status"], entry["points"]) for entry in body["changed"]} == {
        (str(match.picks["alice_first"].id), "lost", 0),
        (str(match.picks["bob"].id), "won", 34),
        (str(match.picks["carol"].id), "lost", 0),
    }

    # Standings in both leagues.
    assert await _points(match.first, match.alice, day) == 0
    assert await _points(match.first, match.bob, day) == 34
    assert await _points(match.second, match.alice, day) == 0
    assert await _points(match.second, match.carol, day) == 0

    # The coupons: the moved picks say so, with the reason; the confirmed one does not.
    first_coupon = await client.get(
        f"/api/v1/leagues/{match.first.slug}/coupon",
        params={"gameweek_id": str(match.first_round.id)},
        headers=_auth(match.bob),
    )
    second_coupon = await client.get(
        f"/api/v1/leagues/{match.second.slug}/coupon",
        params={"gameweek_id": str(match.second_round.id)},
        headers=_auth(match.carol),
    )
    legs = {leg["player_id"]: leg for leg in first_coupon.json()["legs"]} | {
        f"2:{leg['player_id']}": leg for leg in second_coupon.json()["legs"]
    }
    assert (legs[str(match.bob.id)]["status"], legs[str(match.bob.id)]["corrected"]) == (
        "won",
        True,
    )
    assert legs[str(match.bob.id)]["correction_reason"] == REASON
    assert legs[str(match.alice.id)]["corrected"] is True
    assert legs[f"2:{match.carol.id}"]["corrected"] is True
    assert legs[f"2:{match.alice.id}"]["corrected"] is False

    # Results: the first league's round now has Bob as its winner.
    results = await client.get(
        f"/api/v1/leagues/{match.first.slug}/results", headers=_auth(match.bob)
    )
    (row,) = results.json()
    assert (row["winner_names"], row["winner_points"]) == ([match.bob.display_name], 34)

    # Career figures, across leagues.
    alice_summary = await client.get("/api/v1/me/cross-league-summary", headers=_auth(match.alice))
    bob_summary = await client.get("/api/v1/me/cross-league-summary", headers=_auth(match.bob))
    assert alice_summary.json()["total_points"] == 0
    assert bob_summary.json()["total_points"] == 34

    # One audit row per league, each in that league's own log.
    for league in (match.first, match.second):
        trail = await client.get(
            f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(match.admin)
        )
        rows = [entry for entry in trail.json()["entries"] if entry["target_table"] == "fixtures"]
        assert len(rows) == 1, league.slug
        assert rows[0]["changes"]["action"] == "fixture_corrected"
        assert rows[0]["changes"]["reason"] == REASON
        assert rows[0]["changes"]["result"] == {"home_goals": 1, "away_goals": 1}

    # One message per changed member, replacing the settle line they already had.
    assert sorted(message["user_id"] for message in sent) == sorted(
        [match.alice.id, match.bob.id, match.carol.id]
    )
    by_member = {message["user_id"]: message for message in sent}
    assert by_member[match.bob.id]["body"].startswith("Result corrected. Gameweek ")
    assert by_member[match.bob.id]["body"].endswith("won 34 points.")
    assert (
        by_member[match.bob.id]["tag"] == f"round-settled-{match.first.id}-{match.first_round.id}"
    )
    assert by_member[match.carol.id]["league_id"] == match.second.id


async def test_the_same_correction_twice_changes_and_tells_nothing_the_second_time(
    client: AsyncClient,
) -> None:
    match = await _one_match_in_two_leagues()
    body = {"home_goals": 1, "away_goals": 1, "reason": REASON}
    first = await _correct(client, match, body)

    sent: list[dict[str, Any]] = []
    with patch(SEND, new=_recorder(sent)):
        again = await _correct(client, match, body)

    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["changed"] == []
    assert again.json()["leagues_audited"] == []
    assert again.json()["members_told"] == 0
    assert sent == []
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.target_table == "fixtures", AuditLog.target_id == match.fixture.id
            )
        )
    assert len(list(rows.scalars().all())) == 2, "one row per league, written once"


async def test_a_void_correction_voids_every_settled_pick_on_the_match(client: AsyncClient) -> None:
    match = await _one_match_in_two_leagues()

    with patch(SEND, new=_recorder([])):
        response = await _correct(client, match, {"void": True, "reason": "Abandoned at half time"})

    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as session:
        stored = (
            await session.execute(select(Pick).where(Pick.fixture_id == match.fixture.id))
        ).scalars()
        assert {(pick.status, pick.points_awarded) for pick in stored} == {(PickStatus.void, 0)}


async def test_the_correction_is_refused_without_a_result_or_a_settled_pick(
    client: AsyncClient,
) -> None:
    match = await _one_match_in_two_leagues()
    pending = await _pending_only_match()

    half = await _correct(client, match, {"home_goals": 1, "reason": "Half a result"})
    nothing_settled = await client.post(
        f"/api/v1/admin/fixtures/{pending.fixture_id}/correct",
        json={"home_goals": 1, "away_goals": 0, "reason": "Too early"},
        headers=_auth(match.admin),
    )
    unknown = await client.post(
        f"/api/v1/admin/fixtures/{uuid.uuid4()}/correct",
        json={"home_goals": 1, "away_goals": 0, "reason": "No such match"},
        headers=_auth(match.admin),
    )
    not_admin = await client.post(
        f"/api/v1/admin/fixtures/{match.fixture.id}/correct",
        json={"home_goals": 1, "away_goals": 1, "reason": REASON},
        headers=_auth(match.bob),
    )

    assert half.status_code == 422
    assert nothing_settled.status_code == 409
    assert unknown.status_code == 404
    assert not_admin.status_code == 403
    assert (await _reload(match.picks["bob"].id)).status == PickStatus.lost


async def test_the_correction_screen_lists_the_match_with_its_leagues(client: AsyncClient) -> None:
    match = await _one_match_in_two_leagues()

    listed = await client.get("/api/v1/admin/results/settled-fixtures", headers=_auth(match.admin))
    refused = await client.get("/api/v1/admin/results/settled-fixtures", headers=_auth(match.bob))

    assert listed.status_code == 200
    matching = [row for row in listed.json() if row["fixture_id"] == str(match.fixture.id)]
    assert len(matching) == 1
    entry = matching[0]
    assert entry["settled_picks"] == 4
    assert entry["leagues"] == sorted([match.first.name, match.second.name])
    assert refused.status_code == 403
