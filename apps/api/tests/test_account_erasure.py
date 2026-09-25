"""Batch 136 — a member deletes their own account, or takes their data with them.

The row's verification: a deleted member's name is anonymised everywhere it renders while
their points still sum into historic standings; the export contains the member's own data
and nobody else's. Around those, the owner's four decisions of 2026-09-25 — everything
naming them goes, "Former member", immediately after the PIN, and not while they alone run
a league somebody else plays in.

Postgres-backed. Each test builds its own league and members.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.invite import Invite
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import (
    ActionType,
    ActorType,
    AuditLog,
    NotificationPreferences,
    PushSubscription,
)
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.models.rate_limit import RateLimitCounter
from src.models.refresh_token import RefreshToken
from src.services.coupon import build_coupon
from src.services.football_provider import season_for
from src.services.scoring import standings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

ROUND_DAY = date(2027, 3, 6)
PIN = "8351"
PLACEHOLDER = re.compile(r"^Former member [0-9a-f]{8}$")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(name: str | None = None, role: UserRole = UserRole.player) -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=name or f"Member {uuid.uuid4().hex[:6]}",
            pin_hash=hash_pin(PIN),
            role=role,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


@dataclass
class _League:
    league: League
    gameweek: Gameweek
    leaver_pick: Pick
    stayer_pick: Pick


async def _league_with(
    leaver: Profile, stayer: Profile, *, leaver_admin: bool = False, stayer_admin: bool = True
) -> _League:
    """One settled round: the leaver won at 2.50 (25 points), the stayer lost."""
    tag = uuid.uuid4().hex[:8]
    kickoff = datetime(ROUND_DAY.year, ROUND_DAY.month, ROUND_DAY.day, 15, 0)
    async with AsyncSessionLocal() as session:
        league = League(slug=f"bye-{tag}", name=f"League {tag}", created_by=stayer.id)
        session.add(league)
        await session.flush()
        session.add_all(
            [
                LeagueMembership(
                    league_id=league.id,
                    player_id=leaver.id,
                    role=LeagueMemberRole.admin if leaver_admin else LeagueMemberRole.player,
                    display_name_override="The Leaver's League Name",
                ),
                LeagueMembership(
                    league_id=league.id,
                    player_id=stayer.id,
                    role=LeagueMemberRole.admin if stayer_admin else LeagueMemberRole.player,
                ),
            ]
        )
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=ROUND_DAY,
            status=GameweekStatus.settled,
            locks_at_utc=kickoff - timedelta(minutes=30),
        )
        home_win = Fixture(
            provider_event_id=f"ev-a-{tag}",
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=kickoff,
            competition="Scottish League Two",
            competition_id=f"sl2-{tag}",
        )
        other = Fixture(
            provider_event_id=f"ev-b-{tag}",
            home="Stenhousemuir",
            away="Elgin City",
            kickoff_utc=kickoff,
            competition="Scottish League Two",
            competition_id=f"sl2-{tag}",
        )
        session.add_all([gameweek, home_win, other])
        await session.flush()
        session.add_all(
            [
                GameweekFixture(gameweek_id=gameweek.id, fixture_id=home_win.id),
                GameweekFixture(gameweek_id=gameweek.id, fixture_id=other.id),
            ]
        )
        leaver_pick = Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=leaver.id,
            fixture_id=home_win.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar Athletic",
            odds_at_pick=Decimal("2.50"),
            status=PickStatus.won,
            points_awarded=25,
        )
        stayer_pick = Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=stayer.id,
            fixture_id=other.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.AWAY,
            runner_name="Elgin City",
            odds_at_pick=Decimal("3.10"),
            status=PickStatus.lost,
            points_awarded=0,
        )
        session.add_all([leaver_pick, stayer_pick])
        await session.commit()
        for row in (league, gameweek, leaver_pick, stayer_pick):
            await session.refresh(row)
        return _League(league, gameweek, leaver_pick, stayer_pick)


async def _traces_of(member: Profile, league: League) -> None:
    """Everything else that names or follows a member around, as production would hold it."""
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                RefreshToken(
                    user_id=member.id,
                    token_hash=uuid.uuid4().hex,
                    device_hint="Leaver's iPhone",
                    expires_at=datetime(2030, 1, 1),
                ),
                PushSubscription(
                    user_id=member.id,
                    subscription={"endpoint": "https://fcm.googleapis.com/x", "keys": {}},
                    device_hint="Leaver's iPhone",
                    is_active=True,
                ),
                NotificationPreferences(user_id=member.id, global_mute=False),
                Invite(
                    token=uuid.uuid4().hex,
                    display_name_hint=member.display_name,
                    league_id=league.id,
                    created_by=league.created_by,
                    claimed_by=member.id,
                ),
                AuditLog(
                    actor_id=None,
                    actor_type=ActorType.admin,
                    action_type=ActionType.player_pin_reset,
                    target_table="profiles",
                    target_id=member.id,
                    changes={"stage": "reset", "display_name": member.display_name},
                ),
                RateLimitCounter(
                    bucket_key=f"login:{member.display_name.lower()}:203.0.113.9",
                    limit_item="LIMITER/5/15/minute",
                    window_start=datetime(2026, 9, 25),
                    hits=1,
                    expires_at=datetime(2030, 1, 1),
                ),
            ]
        )
        await session.commit()


async def _delete(client: AsyncClient, member: Profile, pin: str = PIN) -> int:
    response = await client.post("/api/v1/me/delete", json={"pin": pin}, headers=_auth(member))
    return response.status_code


async def _reload(profile_id: uuid.UUID) -> Profile:
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(Profile).where(Profile.id == profile_id))).scalar_one()


async def _count(model: type, **where: object) -> int:
    async with AsyncSessionLocal() as session:
        query = select(func.count()).select_from(model)
        for column, value in where.items():
            query = query.where(getattr(model, column) == value)
        return int((await session.execute(query)).scalar_one())


# ── The row's first verification ────────────────────────────────────────────────


async def test_a_deleted_member_is_former_member_everywhere_and_their_points_still_count(
    client: AsyncClient,
) -> None:
    leaver = await _profile(f"Leaver {uuid.uuid4().hex[:6]}")
    stayer = await _profile()
    setup = await _league_with(leaver, stayer)
    await _traces_of(leaver, setup.league)
    old_name = leaver.display_name

    assert await _delete(client, leaver) == 204

    # The leaderboard: their row survives, labelled, with their 25 points in it.
    async with AsyncSessionLocal() as session:
        table = await standings(session, setup.league.id, season=season_for(ROUND_DAY))
        coupon = await build_coupon(session, setup.league.id, setup.gameweek)
    rows = {row.player_id: row for row in table}
    assert (rows[str(leaver.id)].display_name, rows[str(leaver.id)].total_points) == (
        "Former member",
        25,
    )
    assert rows[str(stayer.id)].display_name == stayer.display_name
    # The coupon: the leg they picked is still on it, under the same label.
    assert "Former member" in {leg.player_name for leg in coupon.legs}
    assert old_name not in {leg.player_name for leg in coupon.legs}

    # What is stored names nobody.
    gone = await _reload(leaver.id)
    assert PLACEHOLDER.match(gone.display_name)
    assert (gone.pin_hash, gone.avatar_url, gone.is_active) == (None, None, False)
    assert gone.deleted_at is not None
    async with AsyncSessionLocal() as session:
        membership = (
            await session.execute(
                select(LeagueMembership).where(LeagueMembership.player_id == leaver.id)
            )
        ).scalar_one()
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.target_id == leaver.id,
                    AuditLog.action_type == ActionType.player_pin_reset,
                )
            )
        ).scalar_one()
        hint = (
            await session.execute(
                select(Invite.display_name_hint).where(Invite.claimed_by == leaver.id)
            )
        ).scalar_one()
    assert membership.display_name_override is None
    assert membership.deleted_at is None, "ending it would take their points out of the table"
    assert audit.changes == {"stage": "reset", "display_name": "Former member"}
    assert hint is None

    # Devices, sessions, settings and the login throttle keyed on their name: gone.
    assert await _count(RefreshToken, user_id=leaver.id) == 0
    assert await _count(PushSubscription, user_id=leaver.id) == 0
    assert await _count(NotificationPreferences, user_id=leaver.id) == 0
    assert await _count(RateLimitCounter, bucket_key=f"login:{old_name.lower()}:203.0.113.9") == 0

    # Signed out at once, and the name is free for somebody else.
    assert (await client.get("/api/v1/auth/me", headers=_auth(leaver))).status_code == 401
    reuse = await client.post(
        "/api/v1/auth/register", json={"display_name": old_name, "pin": "7294"}
    )
    assert reuse.status_code == 201, reuse.text


# ── The owner's rules around it ─────────────────────────────────────────────────


async def test_a_wrong_pin_deletes_nothing_and_does_not_sign_them_out(
    client: AsyncClient,
) -> None:
    """403, not 401: the web client treats 401 as an expired session."""
    member = await _profile()
    assert await _delete(client, member, pin="0000") == 403
    kept = await _reload(member.id)
    assert (kept.display_name, kept.deleted_at) == (member.display_name, None)


async def test_the_only_admin_of_a_league_others_play_in_is_refused_until_they_hand_over(
    client: AsyncClient,
) -> None:
    runner = await _profile()
    player = await _profile()
    setup = await _league_with(runner, player, leaver_admin=True, stayer_admin=False)

    refused = await client.post("/api/v1/me/delete", json={"pin": PIN}, headers=_auth(runner))
    assert refused.status_code == 409
    assert setup.league.name in refused.json()["detail"]
    assert (await _reload(runner.id)).deleted_at is None

    async with AsyncSessionLocal() as session:
        membership = (
            await session.execute(
                select(LeagueMembership).where(
                    LeagueMembership.league_id == setup.league.id,
                    LeagueMembership.player_id == player.id,
                )
            )
        ).scalar_one()
        membership.role = LeagueMemberRole.admin
        await session.commit()
    assert await _delete(client, runner) == 204


async def test_a_site_admin_cannot_delete_themselves_here(client: AsyncClient) -> None:
    admin = await _profile(role=UserRole.admin)
    assert await _delete(client, admin) == 409
    assert (await _reload(admin.id)).deleted_at is None


@pytest.mark.parametrize("name", ["Former member", "former member 1a2b3c4d", "FORMER MEMBERS"])
async def test_nobody_can_register_as_a_former_member(client: AsyncClient, name: str) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"display_name": name, "pin": "7294"}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "That name is reserved."


# ── The row's second verification ───────────────────────────────────────────────


async def test_the_export_is_their_data_and_nobody_elses(client: AsyncClient) -> None:
    member = await _profile(f"Exporter {uuid.uuid4().hex[:6]}")
    other = await _profile(f"Neighbour {uuid.uuid4().hex[:6]}")
    setup = await _league_with(member, other)

    response = await client.get("/api/v1/me/export", headers=_auth(member))

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    export = response.json()
    assert export["profile"]["display_name"] == member.display_name
    assert [league["league"] for league in export["leagues"]] == [setup.league.name]
    assert export["leagues"][0]["your_name_in_this_league"] == "The Leaver's League Name"
    (pick,) = export["picks"]
    assert (pick["fixture"], pick["odds"], pick["status"], pick["points"]) == (
        "Forfar Athletic v Brechin City",
        "2.50",
        "won",
        25,
    )
    text = json.dumps(export)
    assert other.display_name not in text, "another member's name is in the export"
    assert "Elgin City" not in text, "another member's pick is in the export"
    assert "pin_hash" not in text and "$2b$" not in text, "a credential is in the export"
