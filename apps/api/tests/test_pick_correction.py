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
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal

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
