"""Batch 124 — the join code is not a way around removal, or around approval.

Two holes with one shape: the join code was treated as proof of belonging, and it is
not. Every member can read it.

* **Removal never rotated it.** `_upsert_membership` restores a soft-deleted row, and
  `join-by-code` checked nothing about why the row was deleted, so a member who was
  removed and pasted the code back was in again immediately — no invite, no approval,
  no audit trail beyond a second "joined".
* **`public_request` was gated at one door only.** `POST /{slug}/join` opened a request
  and waited for an admin; `join-by-code` created the membership outright. The same
  person refused at the front door walked in through the side.

Postgres-backed and non-hermetic, like `test_admin_console.py`: these drive the HTTP
endpoints, which commit through their own sessions. Every profile and league is tagged.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.league import League, LeaguePrivacy
from src.models.league_join_request import JoinRequestStatus, LeagueJoinRequest
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, AuditLog
from src.models.profile import Profile, UserRole

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile() -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=f"join-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=UserRole.player,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _league(
    owner: Profile,
    privacy: LeaguePrivacy = LeaguePrivacy.public_open,
    *,
    members: list[Profile] | None = None,
) -> League:
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(
            slug=f"jg-{tag}",
            name=f"Join Gate {tag}",
            created_by=owner.id,
            privacy=privacy,
        )
        session.add(league)
        await session.flush()
        session.add(
            LeagueMembership(league_id=league.id, player_id=owner.id, role=LeagueMemberRole.admin)
        )
        for member in members or []:
            session.add(
                LeagueMembership(
                    league_id=league.id, player_id=member.id, role=LeagueMemberRole.player
                )
            )
        await session.commit()
        await session.refresh(league)
        return league


async def _reload(league_id: uuid.UUID) -> League:
    async with AsyncSessionLocal() as session:
        found = await session.get(League, league_id)
        assert found is not None
        return found


async def _active_membership(league_id: uuid.UUID, player_id: uuid.UUID) -> LeagueMembership | None:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(LeagueMembership).where(
                    LeagueMembership.league_id == league_id,
                    LeagueMembership.player_id == player_id,
                    LeagueMembership.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()


async def _pending_requests(league_id: uuid.UUID, player_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(LeagueJoinRequest).where(
                LeagueJoinRequest.league_id == league_id,
                LeagueJoinRequest.player_id == player_id,
                LeagueJoinRequest.status == JoinRequestStatus.pending,
            )
        )
        return len(rows.scalars().all())


# ── Removal ───────────────────────────────────────────────────────────────────


async def test_a_removed_members_old_code_is_refused(client: AsyncClient) -> None:
    """The finding, end to end. Removed, pastes the code back, and stays out."""
    admin = await _profile()
    removed = await _profile()
    league = await _league(admin, members=[removed])
    old_code = league.join_code
    assert old_code is not None

    gone = await client.delete(
        f"/api/v1/leagues/{league.slug}/members/{removed.id}", headers=_auth(admin)
    )
    assert gone.status_code == 204, gone.text
    assert await _active_membership(league.id, removed.id) is None

    walked_back_in = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": old_code}, headers=_auth(removed)
    )
    assert walked_back_in.status_code == 404, walked_back_in.text
    assert await _active_membership(league.id, removed.id) is None


async def test_removal_rotates_the_code_and_says_so(client: AsyncClient) -> None:
    """Rotation is the mechanism, so it has to be visible to the admin who caused it."""
    admin = await _profile()
    removed = await _profile()
    league = await _league(admin, members=[removed])
    old_code = league.join_code

    await client.delete(f"/api/v1/leagues/{league.slug}/members/{removed.id}", headers=_auth(admin))

    after = await _reload(league.id)
    assert after.join_code is not None
    assert after.join_code != old_code

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(AuditLog).where(
                AuditLog.target_table == "leagues",
                AuditLog.target_id == league.id,
                AuditLog.action_type == ActionType.league_join_code_rotated,
            )
        )
        assert len(rows.scalars().all()) == 1


async def test_the_new_code_still_admits_somebody_who_was_never_removed(
    client: AsyncClient,
) -> None:
    """Rotation must close one door, not the league."""
    admin = await _profile()
    removed = await _profile()
    newcomer = await _profile()
    league = await _league(admin, members=[removed])

    await client.delete(f"/api/v1/leagues/{league.slug}/members/{removed.id}", headers=_auth(admin))
    rotated = (await _reload(league.id)).join_code
    assert rotated is not None

    joined = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": rotated}, headers=_auth(newcomer)
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["status"] == "joined"
    assert await _active_membership(league.id, newcomer.id) is not None


# ── Approval ──────────────────────────────────────────────────────────────────


async def test_join_by_code_on_an_approval_gated_league_creates_a_request(
    client: AsyncClient,
) -> None:
    """The second finding. Holding the code is not approval — every member can read it."""
    admin = await _profile()
    outsider = await _profile()
    league = await _league(admin, LeaguePrivacy.public_request)
    code = league.join_code
    assert code is not None

    answer = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": code}, headers=_auth(outsider)
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "pending"
    assert answer.json()["league_slug"] == league.slug
    assert await _active_membership(league.id, outsider.id) is None
    assert await _pending_requests(league.id, outsider.id) == 1


async def test_the_two_doors_answer_a_gated_league_the_same_way(client: AsyncClient) -> None:
    """`/join` and `/join-by-code` share one helper so they cannot drift apart again."""
    admin = await _profile()
    outsider = await _profile()
    league = await _league(admin, LeaguePrivacy.public_request)
    code = league.join_code
    assert code is not None

    front = await client.post(f"/api/v1/leagues/{league.slug}/join", headers=_auth(outsider))
    assert front.status_code == 200, front.text
    assert front.json()["status"] == "pending"

    # A second attempt through the *other* door is refused for the same reason, rather
    # than quietly opening a second request or a membership.
    side = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": code}, headers=_auth(outsider)
    )
    assert side.status_code == 409, side.text
    assert side.json()["detail"] == "JOIN_REQUEST_PENDING"
    assert await _pending_requests(league.id, outsider.id) == 1
    assert await _active_membership(league.id, outsider.id) is None


async def test_an_open_league_still_joins_straight_through(client: AsyncClient) -> None:
    """The half that must not have moved."""
    admin = await _profile()
    newcomer = await _profile()
    league = await _league(admin, LeaguePrivacy.public_open)
    code = league.join_code
    assert code is not None

    answer = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": code}, headers=_auth(newcomer)
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "joined"
    assert await _active_membership(league.id, newcomer.id) is not None
    assert await _pending_requests(league.id, newcomer.id) == 0
