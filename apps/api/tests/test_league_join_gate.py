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

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from src.auth import _JOIN_CODE_ALPHABET, create_access_token, hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.main import app
from src.models.invite import Invite
from src.models.league import League, LeaguePrivacy
from src.models.league_join_request import JoinRequestStatus, LeagueJoinRequest
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, AuditLog
from src.models.profile import Profile, UserRole
from src.models.refresh_token import RefreshToken

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


# -- Batch 143: an invite to a deleted league ---------------------------------
#
# `claim-invite` looked the league up without the `deleted_at` filter every other
# lookup in the app applies, so an invite to a deleted league resolved and the claim
# went on to build a membership of a league that no longer exists — which every
# subsequent lookup would then answer 404 for.


async def _invite(league: League, created_by: Profile) -> Invite:
    async with AsyncSessionLocal() as session:
        invite = Invite(
            league_id=league.id,
            token=f"tok-{uuid.uuid4().hex}",
            created_by=created_by.id,
            is_active=True,
        )
        session.add(invite)
        await session.commit()
        await session.refresh(invite)
        return invite


async def _soft_delete(league_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        league = await session.get(League, league_id)
        assert league is not None
        league.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()


async def test_public_invite_preview_returns_only_allowed_facts(client: AsyncClient) -> None:
    admin = await _profile()
    member = await _profile()
    league = await _league(admin, members=[member])
    invite = await _invite(league, admin)

    answer = await client.get(f"/api/v1/leagues/invite-preview/{invite.token}")

    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    assert answer.json() == {
        "league_name": league.name,
        "inviter_name": admin.display_name,
        "member_count": 2,
    }


@pytest.mark.parametrize("invalid", ["missing", "revoked", "used", "expired", "deleted"])
async def test_public_invite_preview_refuses_invalid_tokens_without_leaking(
    client: AsyncClient, invalid: str
) -> None:
    admin = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)
    token = invite.token
    if invalid == "missing":
        token = f"missing-{uuid.uuid4().hex}"
    else:
        async with AsyncSessionLocal() as session:
            row = await session.get(Invite, invite.id)
            assert row is not None
            if invalid == "revoked":
                row.is_active = False
            elif invalid == "used":
                row.claimed_by = admin.id
            elif invalid == "expired":
                row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
            else:
                target = await session.get(League, league.id)
                assert target is not None
                target.deleted_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

    answer = await client.get(f"/api/v1/leagues/invite-preview/{token}")

    assert answer.status_code == 404
    assert answer.json() == {"detail": "Invite not found"}
    assert league.name not in answer.text
    assert admin.display_name not in answer.text


async def test_public_invite_preview_redacts_a_deleted_inviter(client: AsyncClient) -> None:
    admin = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)
    async with AsyncSessionLocal() as session:
        owner = await session.get(Profile, admin.id)
        assert owner is not None
        owner.display_name = f"Former member {uuid.uuid4().hex[:8]}"
        owner.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()

    answer = await client.get(f"/api/v1/leagues/invite-preview/{invite.token}")

    assert answer.status_code == 200, answer.text
    assert answer.json()["inviter_name"] == "Former member"


async def test_an_invite_to_a_deleted_league_is_refused(client: AsyncClient) -> None:
    admin = await _profile()
    newcomer = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)

    await _soft_delete(league.id)

    refused = await client.post(
        "/api/v1/leagues/claim-invite",
        json={"token": invite.token},
        headers=_auth(newcomer),
    )

    assert refused.status_code == 404, refused.text
    assert await _active_membership(league.id, newcomer.id) is None


async def test_an_invite_to_a_live_league_still_claims(client: AsyncClient) -> None:
    """The half that must not have moved."""
    admin = await _profile()
    newcomer = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)

    claimed = await client.post(
        "/api/v1/leagues/claim-invite",
        json={"token": invite.token},
        headers=_auth(newcomer),
    )

    assert claimed.status_code == 200, claimed.text
    assert await _active_membership(league.id, newcomer.id) is not None


@pytest.mark.parametrize("public_signup_enabled", [True, False])
async def test_invite_registration_creates_account_membership_and_session_together(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, public_signup_enabled: bool
) -> None:
    monkeypatch.setattr(settings, "public_signup_enabled", public_signup_enabled)
    admin = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)
    name = f"invited-{uuid.uuid4().hex[:8]}"

    response = await client.post(
        "/api/v1/auth/register",
        json={"display_name": name, "pin": "3719", "invite_token": invite.token},
    )

    assert response.status_code == 201, response.text
    assert response.json()["joined_league_slug"] == league.slug
    async with AsyncSessionLocal() as session:
        player = (
            await session.execute(select(Profile).where(Profile.display_name == name))
        ).scalar_one()
        claimed = await session.get(Invite, invite.id)
        refresh = (
            await session.execute(select(RefreshToken).where(RefreshToken.user_id == player.id))
        ).scalar_one()
        assert claimed is not None and claimed.claimed_by == player.id
        assert not claimed.is_active
        assert refresh.user_id == player.id
    assert await _active_membership(league.id, player.id) is not None


@pytest.mark.parametrize(
    "invalid", ["missing", "revoked", "used", "expired", "deleted", "full", "code"]
)
async def test_closed_signup_refuses_invalid_invites_without_creating_an_account(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    monkeypatch.setattr(settings, "public_signup_enabled", False)
    admin = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)
    token = invite.token
    if invalid == "missing":
        token = f"missing-{uuid.uuid4().hex}"
    elif invalid == "code":
        assert league.join_code is not None
        token = league.join_code
    else:
        async with AsyncSessionLocal() as session:
            row = await session.get(Invite, invite.id)
            assert row is not None
            if invalid == "revoked":
                row.is_active = False
            elif invalid == "used":
                row.claimed_by = admin.id
            elif invalid == "expired":
                row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
            elif invalid == "deleted":
                target = await session.get(League, league.id)
                assert target is not None
                target.deleted_at = datetime.now(UTC).replace(tzinfo=None)
            elif invalid == "full":
                target = await session.get(League, league.id)
                assert target is not None
                target.max_members = 2
                session.add(LeagueMembership(league_id=league.id, player_id=(await _profile()).id))
            await session.commit()
    name = f"refused-{uuid.uuid4().hex[:8]}"

    response = await client.post(
        "/api/v1/auth/register",
        json={"display_name": name, "pin": "3719", "invite_token": token},
    )

    assert response.status_code in {400, 404, 409}, response.text
    async with AsyncSessionLocal() as session:
        account = (
            await session.execute(select(Profile).where(Profile.display_name == name))
        ).scalar_one_or_none()
        assert account is None


async def test_one_invite_cannot_register_two_accounts_at_once(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "public_signup_enabled", False)
    admin = await _profile()
    league = await _league(admin)
    invite = await _invite(league, admin)
    names = [f"race-{uuid.uuid4().hex[:8]}" for _ in range(2)]

    answers = await asyncio.gather(
        *(
            client.post(
                "/api/v1/auth/register",
                json={"display_name": name, "pin": "3719", "invite_token": invite.token},
            )
            for name in names
        )
    )

    assert sorted(answer.status_code for answer in answers) == [201, 400]
    async with AsyncSessionLocal() as session:
        accounts = (
            (await session.execute(select(Profile).where(Profile.display_name.in_(names))))
            .scalars()
            .all()
        )
        assert len(accounts) == 1


async def test_two_leagues_inserted_without_a_code_never_share_the_databases_draw() -> None:
    """CI run 37247946337: two test leagues took the same six-hex-digit default code.

    A league inserted without a code used to get the database's
    ``upper(substr(md5(random()::text), 1, 6))`` — 16.8 million values, no retry — and the
    suite commits about two hundred leagues that way, so a collision on
    ``uq_leagues_join_code`` was a matter of time. Seeding Postgres' generator before each
    insert makes both of the old draws identical, which is that collision on demand. The
    ORM now supplies the product's own code, which does not come from ``random()`` at all.
    """
    async with AsyncSessionLocal() as session:
        owner = Profile(
            display_name=f"join-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=UserRole.player,
        )
        session.add(owner)
        await session.flush()
        codes: list[str | None] = []
        for name in ("first", "second"):
            await session.execute(text("select setseed(0.42)"))
            league = League(
                slug=f"seeded-{name}-{uuid.uuid4().hex[:6]}",
                name=f"Seeded {name}",
                created_by=owner.id,
            )
            session.add(league)
            await session.flush()
            codes.append(league.join_code)
        await session.rollback()

    first, second = codes
    assert first is not None and second is not None
    assert first != second
    # The same shape every creation route hands out: six letters from the join alphabet.
    for code in (first, second):
        assert re.fullmatch(f"[{_JOIN_CODE_ALPHABET}]{{6}}", code), code
