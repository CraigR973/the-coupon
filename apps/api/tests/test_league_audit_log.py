"""Batch 94 — the league-scoped audit log, and the leak it must not have.

Until this endpoint the only reader of ``audit_log`` in the API was the site-admin
dashboard: 25 rows, global across every league. Making a *league* admin a reader means
answering a question the table cannot answer directly — there is no ``league_id`` column —
so the association is reconstructed from what the writers happen to record. Two things
follow, and both are tested here: the reconstruction must not miss rows (a trail with
silent gaps is worse than none), and it must not reach into another league.

Postgres-backed; these tests commit, so every fixture is uniquely tagged.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile, UserRole

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        yield db


async def _league_with_admin_and_member(
    db: AsyncSession, label: str
) -> tuple[League, Profile, Profile]:
    tag = uuid.uuid4().hex[:8]
    admin = Profile(display_name=f"{label}-admin-{tag}", pin_hash=hash_pin("1234"))
    member = Profile(display_name=f"{label}-member-{tag}", pin_hash=hash_pin("1234"))
    db.add_all([admin, member])
    await db.flush()
    league = League(slug=f"{label}-{tag}", name=f"League {tag}", created_by=admin.id)
    db.add(league)
    await db.flush()
    db.add(LeagueMembership(league_id=league.id, player_id=admin.id, role=LeagueMemberRole.admin))
    db.add(LeagueMembership(league_id=league.id, player_id=member.id))
    await db.commit()
    await db.refresh(league)
    await db.refresh(admin)
    await db.refresh(member)
    return league, admin, member


async def _row(
    db: AsyncSession,
    actor: Profile,
    action: ActionType,
    target_table: str,
    target_id: uuid.UUID | None,
    changes: dict[str, object] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_id=actor.id,
        actor_type=ActorType.player,
        action_type=action,
        target_table=target_table,
        target_id=target_id,
        changes=changes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


class TestScoping:
    async def test_admin_sees_their_own_leagues_rows(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        league, admin, member = await _league_with_admin_and_member(session, "own")
        mine = await _row(
            session,
            admin,
            ActionType.member_removed,
            "league_memberships",
            league.id,
            {"player_id": str(member.id)},
        )

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(admin))

        assert res.status_code == 200
        assert [e["id"] for e in res.json()["entries"]] == [str(mine.id)]

    async def test_no_cross_league_leakage(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        mine_league, mine_admin, _ = await _league_with_admin_and_member(session, "mine")
        theirs_league, theirs_admin, theirs_member = await _league_with_admin_and_member(
            session, "theirs"
        )
        await _row(session, mine_admin, ActionType.league_updated, "leagues", mine_league.id)
        theirs = await _row(
            session,
            theirs_admin,
            ActionType.member_removed,
            "league_memberships",
            theirs_league.id,
            {"player_id": str(theirs_member.id)},
        )
        # The shape that leaks if the filter trusts `changes` without checking the slug.
        theirs_invite = await _row(
            session,
            theirs_admin,
            ActionType.league_invite_revoked,
            "invites",
            uuid.uuid4(),
            {"league_slug": theirs_league.slug},
        )

        res = await client.get(
            f"/api/v1/leagues/{mine_league.slug}/audit-log", headers=_auth(mine_admin)
        )

        ids = {e["id"] for e in res.json()["entries"]}
        assert str(theirs.id) not in ids
        assert str(theirs_invite.id) not in ids
        assert res.json()["total"] == 1

    async def test_finds_rows_that_name_the_league_only_in_changes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """``league_invite_revoked`` records the *invite* id, not the league's.

        Batch 94 may not change what the writers record, so the reader has to cope. A
        revoked invite missing from the one screen that claims to show what happened to
        the league is exactly the silent gap this arm of the filter exists to prevent.
        """
        league, admin, _ = await _league_with_admin_and_member(session, "changes")
        revoked = await _row(
            session,
            admin,
            ActionType.league_invite_revoked,
            "invites",
            uuid.uuid4(),
            {"league_slug": league.slug},
        )

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(admin))

        assert [e["id"] for e in res.json()["entries"]] == [str(revoked.id)]

    async def test_a_real_admin_action_shows_up(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """End-to-end: the reader must match what the writers actually produce."""
        league, admin, _ = await _league_with_admin_and_member(session, "real")

        patched = await client.patch(
            f"/api/v1/leagues/{league.slug}",
            json={"description": "changed by the test"},
            headers=_auth(admin),
        )
        assert patched.status_code == 200

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(admin))

        entries = res.json()["entries"]
        assert [e["action_type"] for e in entries] == ["league_updated"]
        assert entries[0]["actor_name"] == admin.display_name


class TestWhoMayRead:
    async def test_a_non_admin_member_is_refused(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        league, _, member = await _league_with_admin_and_member(session, "nonadmin")

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(member))

        assert res.status_code == 403
        assert "admin" in res.json()["detail"].lower()

    async def test_a_stranger_is_refused(self, client: AsyncClient, session: AsyncSession) -> None:
        league, _, _ = await _league_with_admin_and_member(session, "stranger")
        outsider = Profile(
            display_name=f"outsider-{uuid.uuid4().hex[:8]}", pin_hash=hash_pin("1234")
        )
        session.add(outsider)
        await session.commit()
        await session.refresh(outsider)

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(outsider))

        assert res.status_code == 403

    async def test_an_anonymous_caller_is_refused(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        league, _, _ = await _league_with_admin_and_member(session, "anon")

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log")

        assert res.status_code in (401, 403)

    async def test_a_site_admin_may_read_any_league(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        # `require_league_admin` lets a superadmin through without membership; the audit
        # trail is not an exception to that, and the site console already reads these rows.
        league, _, _ = await _league_with_admin_and_member(session, "site")
        superadmin = Profile(
            display_name=f"site-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("1234"),
            role=UserRole.admin,
        )
        session.add(superadmin)
        await session.commit()
        await session.refresh(superadmin)

        res = await client.get(
            f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(superadmin)
        )

        assert res.status_code == 200


class TestPagination:
    async def test_pages_rather_than_capping_at_25(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """The dashboard's flat 25 is a glance at an installation. This is one history."""
        league, admin, _ = await _league_with_admin_and_member(session, "paging")
        for _ in range(30):
            await _row(session, admin, ActionType.league_updated, "leagues", league.id)

        first = (
            await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(admin))
        ).json()
        second = (
            await client.get(
                f"/api/v1/leagues/{league.slug}/audit-log?page=2", headers=_auth(admin)
            )
        ).json()

        assert first["total"] == 30
        assert len(first["entries"]) == 25
        assert len(second["entries"]) == 5
        assert not {e["id"] for e in first["entries"]} & {e["id"] for e in second["entries"]}

    async def test_a_hostile_page_size_falls_back_to_the_default(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        league, admin, _ = await _league_with_admin_and_member(session, "hostile")

        res = await client.get(
            f"/api/v1/leagues/{league.slug}/audit-log?page=-3&page_size=100000",
            headers=_auth(admin),
        )

        assert res.status_code == 200
        assert res.json()["page"] == 1
        assert res.json()["page_size"] == 25


class TestPayload:
    async def test_carries_the_changes_the_dashboard_drops(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        """ "A member was removed" is not the answer; "who removed whom" is."""
        league, admin, member = await _league_with_admin_and_member(session, "payload")
        await _row(
            session,
            admin,
            ActionType.member_removed,
            "league_memberships",
            league.id,
            {"player_id": str(member.id)},
        )

        res = await client.get(f"/api/v1/leagues/{league.slug}/audit-log", headers=_auth(admin))

        entry = res.json()["entries"][0]
        assert entry["changes"] == {"player_id": str(member.id)}
        assert entry["actor_name"] == admin.display_name
        assert entry["target_table"] == "league_memberships"
