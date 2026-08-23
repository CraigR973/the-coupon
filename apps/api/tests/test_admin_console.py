"""Batch 66 — the admin console's people half, and the journey it completes.

Batch 56 made ``/auth/pin/reset-request`` truthful: it writes an audit row and pushes
every active site admin. The notification was real and the action behind it did not
exist — the push sent the admin to their own settings page, and exactly one endpoint in
the API used the ``AdminUser`` dependency. A member who forgot four digits was a lost
account, and this is the walk from "I cannot sign in" back to signed in.

What these hold to:

* the journey end to end — member asks, admin is paged at a screen that exists, admin
  clears the PIN, member chooses a new one and signs in;
* an admin reset **revokes every refresh token**, on both admin surfaces, because it is
  one rule and the league-admin endpoint predated it and never obeyed it;
* a cleared PIN is not a blank one — login refuses it outright rather than admitting
  anything, and it stops being claimable once the window closes;
* every endpoint on ``/api/v1/admin`` refuses a non-admin caller — asserted by walking
  the router rather than by listing them, so a route added without the dependency fails
  here rather than shipping;
* the delete is soft, keeps the member's picks, and keeps their display name reserved.

Postgres-backed and **non-hermetic**: these drive the HTTP endpoints, which commit
through their own sessions. Every profile and league is uniquely tagged.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token, hash_pin, hash_token
from src.database import AsyncSessionLocal
from src.main import app
from src.models.invite import Invite
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import ActionType, AuditLog
from src.models.profile import Profile, UserRole
from src.models.refresh_token import RefreshToken
from src.routers.admin import router as admin_router
from src.routers.auth import PIN_NOT_SET
from src.services.credentials import PIN_RESET_CLAIM_WINDOW, STAGE_RESET

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(role: UserRole = UserRole.player, pin: str = "8351") -> Profile:
    """A committed profile the HTTP endpoints can authenticate."""
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=f"{role.value}-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin(pin),
            role=role,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _live_session(user_id: uuid.UUID) -> RefreshToken:
    """One unrevoked refresh token, as a sign-in would have left behind."""
    async with AsyncSessionLocal() as session:
        token = RefreshToken(
            user_id=user_id,
            token_hash=hash_token(f"raw-{uuid.uuid4().hex}"),
            expires_at=_now() + timedelta(days=30),
        )
        session.add(token)
        await session.commit()
        await session.refresh(token)
        return token


async def _reload(player_id: uuid.UUID) -> Profile:
    async with AsyncSessionLocal() as session:
        found = await session.get(Profile, player_id)
        assert found is not None
        return found


async def _live_session_count(user_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        return len(rows.scalars().all())


async def _league_for(owner: Profile) -> League:
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(slug=f"adm-{tag}", name=f"Admin {tag}", created_by=owner.id)
        session.add(league)
        await session.flush()
        session.add(
            LeagueMembership(league_id=league.id, player_id=owner.id, role=LeagueMemberRole.admin)
        )
        await session.commit()
        await session.refresh(league)
        return league


# ── The journey the batch exists for ───────────────────────────────────────────


async def test_a_forgotten_pin_is_now_a_round_trip_rather_than_a_lost_account(
    client: AsyncClient,
) -> None:
    """Member asks, admin is paged at a real screen, admin acts, member signs back in.

    The whole point of the batch in one test. Every step was already there except the
    two in the middle, and without them the first step was a message that went nowhere.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    await _live_session(member.id)

    # 1. The member cannot sign in and asks.
    asked = await client.post(
        "/api/v1/auth/pin/reset-request", json={"display_name": member.display_name}
    )
    assert asked.status_code == 200

    # 2. The admin is paged, and the push now names a screen that exists.
    async with AsyncSessionLocal() as session:
        requested = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.target_id == member.id,
                        AuditLog.action_type == ActionType.player_pin_reset,
                    )
                    .order_by(AuditLog.timestamp.desc())
                )
            )
            .scalars()
            .first()
        )
    assert requested is not None and requested.changes == {
        "stage": "requested",
        "display_name": member.display_name,
    }

    # 3. The admin finds them in the console and clears the PIN.
    listed = await client.get("/api/v1/admin/players", headers=_auth(admin))
    assert listed.status_code == 200
    row = next(p for p in listed.json() if p["id"] == str(member.id))
    assert row["pin_set"] is True

    reset = await client.post(f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin))
    assert reset.status_code == 200, reset.text
    assert reset.json()["pin_cleared"] is True
    assert reset.json()["sessions_revoked"] == 1
    assert "temp_pin" not in reset.json(), "no secret passes through the admin"

    # 4. The member's old PIN is not merely wrong — there is nothing to be wrong about.
    refused = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "8351"}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == PIN_NOT_SET

    # 5. They choose their own, and it is theirs — nobody else ever saw it.
    chosen = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "7412"}
    )
    assert chosen.status_code == 204, chosen.text

    signed_in = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "7412"}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["player"]["display_name"] == member.display_name


async def test_the_reset_request_push_points_at_a_screen_that_exists(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch 56 sent the admin to ``/settings`` because there was nowhere else to send them.

    The URL is asserted rather than the delivery, because the push itself needs VAPID
    keys and a subscription and neither is guaranteed — what has to be right is where it
    lands when it does.
    """
    await _profile(UserRole.admin)
    member = await _profile()
    sent: list[dict[str, str]] = []

    async def capture(db: object, user_id: object, title: str, body: str, **kwargs: object) -> int:
        data = kwargs.get("data")
        assert isinstance(data, dict)
        sent.append(data)
        return 1

    monkeypatch.setattr("src.routers.auth.send_notification", capture)
    asked = await client.post(
        "/api/v1/auth/pin/reset-request", json={"display_name": member.display_name}
    )
    assert asked.status_code == 200
    assert sent, "an active site admin must be paged"
    for data in sent:
        assert data["url"].startswith("/admin/players"), data["url"]
        assert data["player_id"] == str(member.id)


# ── The rule the batch makes load-bearing ──────────────────────────────────────


async def test_an_admin_reset_revokes_every_session_the_old_pin_opened(
    client: AsyncClient,
) -> None:
    """Batch 56's rule, applied to the reset an admin performs on somebody else.

    A reset that writes a credential and leaves the old sessions renewing themselves for
    thirty days is theatre — the session being shut out outlives the credential it was
    opened with.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    for _ in range(3):
        await _live_session(member.id)
    assert await _live_session_count(member.id) == 3

    response = await client.post(
        f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin)
    )

    assert response.status_code == 200, response.text
    assert response.json()["sessions_revoked"] == 3
    assert await _live_session_count(member.id) == 0
    assert (await _reload(member.id)).pin_hash is None


async def test_the_league_admin_reset_obeys_the_same_rule(client: AsyncClient) -> None:
    """The endpoint that predated the rule and never obeyed it.

    ``POST /leagues/{slug}/members/{id}/reset-pin`` minted a temporary four-digit PIN and
    returned it for the admin to read out, and revoked nothing. Both halves are the
    reason ``services/credentials.clear_pin`` exists rather than a second implementation.
    """
    owner = await _profile()
    member = await _profile()
    league = await _league_for(owner)
    async with AsyncSessionLocal() as session:
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        await session.commit()
    await _live_session(member.id)

    response = await client.post(
        f"/api/v1/leagues/{league.slug}/members/{member.id}/reset-pin", headers=_auth(owner)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["temp_pin"] is None, "no minted secret, and the field kept null for the deploy gap"
    assert body["pin_cleared"] is True
    assert body["sessions_revoked"] == 1
    assert await _live_session_count(member.id) == 0
    assert (await _reload(member.id)).pin_hash is None


# ── A cleared PIN is the absence of one, not a blank one ───────────────────────


async def test_a_cleared_pin_admits_nothing_at_all(client: AsyncClient) -> None:
    """Not the empty string, not four zeroes, not the PIN it used to be."""
    admin = await _profile(UserRole.admin)
    member = await _profile(pin="8351")
    await client.post(f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin))

    for attempt in ("8351", "0000", "1111"):
        response = await client.post(
            "/api/v1/auth/login", json={"display_name": member.display_name, "pin": attempt}
        )
        assert response.status_code == 409, attempt
        assert response.json()["detail"] == PIN_NOT_SET


async def test_setting_a_pin_needs_a_reset_that_has_not_expired(client: AsyncClient) -> None:
    """The bound on the credential-less state, and why it has one.

    Nothing proves the caller is the member — that is what "no secret passes through the
    admin" costs — so the window is what keeps a display name from being enough to take
    an account. Past it the reset simply expires and the member asks again.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    await client.post(f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin))

    async with AsyncSessionLocal() as session:
        row = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.target_id == member.id,
                        AuditLog.action_type == ActionType.player_pin_reset,
                    )
                    .order_by(AuditLog.timestamp.desc())
                )
            )
            .scalars()
            .first()
        )
        assert row is not None and row.changes is not None
        assert row.changes["stage"] == STAGE_RESET
        row.timestamp = _now() - PIN_RESET_CLAIM_WINDOW - timedelta(minutes=1)
        await session.commit()

    stale = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "7412"}
    )
    assert stale.status_code == 409
    assert (await _reload(member.id)).pin_hash is None, "an expired reset sets nothing"


async def test_setting_a_pin_is_single_use(client: AsyncClient) -> None:
    """The window closes by making its own condition false — no "used" flag to forget."""
    admin = await _profile(UserRole.admin)
    member = await _profile()
    await client.post(f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin))

    first = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "7412"}
    )
    assert first.status_code == 204
    second = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "9630"}
    )
    assert second.status_code == 409

    still_theirs = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "7412"}
    )
    assert still_theirs.status_code == 200


async def test_a_member_who_never_asked_cannot_have_a_pin_set_on_them(
    client: AsyncClient,
) -> None:
    """An account with a credential is not claimable, whatever the audit log says."""
    member = await _profile(pin="8351")

    response = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "7412"}
    )

    assert response.status_code == 409
    signed_in = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "8351"}
    )
    assert signed_in.status_code == 200, "their own PIN still works"


async def test_the_charset_rules_apply_where_the_member_chooses(client: AsyncClient) -> None:
    """No temporary PIN means no PIN escapes the blocklist by being machine-picked."""
    admin = await _profile(UserRole.admin)
    member = await _profile()
    await client.post(f"/api/v1/admin/players/{member.id}/reset-pin", headers=_auth(admin))

    weak = await client.post(
        "/api/v1/auth/pin/set", json={"display_name": member.display_name, "pin": "1234"}
    )

    assert weak.status_code == 422
    assert (await _reload(member.id)).pin_hash is None


# ── Unlock, delete, and the rest of the console ────────────────────────────────


async def test_an_unlock_returns_the_attempts_without_touching_the_credential(
    client: AsyncClient,
) -> None:
    """The lighter remedy: a member who knows their PIN and mistyped it five times."""
    admin = await _profile(UserRole.admin)
    member = await _profile(pin="8351")
    async with AsyncSessionLocal() as session:
        stored = await session.get(Profile, member.id)
        assert stored is not None
        stored.failed_login_count = 5
        stored.locked_until = _now() + timedelta(minutes=15)
        await session.commit()

    response = await client.post(f"/api/v1/admin/players/{member.id}/unlock", headers=_auth(admin))

    assert response.status_code == 204
    after = await _reload(member.id)
    assert after.failed_login_count == 0
    assert after.locked_until is None
    assert after.pin_hash is not None, "an unlock is not a reset"
    signed_in = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "8351"}
    )
    assert signed_in.status_code == 200


async def test_deleting_a_player_is_soft_and_keeps_their_name_reserved(
    client: AsyncClient,
) -> None:
    """Their settled weeks stay as they were played, and nobody inherits their name.

    The name staying reserved is a consequence rather than an oversight: ``display_name``
    is the login identifier and Batch 63's uniqueness check includes soft-deleted rows.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    await _live_session(member.id)

    response = await client.delete(f"/api/v1/admin/players/{member.id}", headers=_auth(admin))

    assert response.status_code == 204
    after = await _reload(member.id)
    assert after.deleted_at is not None
    assert after.is_active is False
    assert await _live_session_count(member.id) == 0

    taken = await client.post(
        "/api/v1/auth/register",
        json={"display_name": member.display_name.upper(), "pin": "7412"},
    )
    assert taken.status_code == 409, "a departed member's name is not re-registerable"

    listed = await client.get("/api/v1/admin/players", headers=_auth(admin))
    assert any(
        p["id"] == str(member.id) for p in listed.json()
    ), "a soft-deleted member stays visible, or the reserved name has no explanation"


async def test_an_admin_cannot_delete_themselves(client: AsyncClient) -> None:
    """There is no undelete screen, and locking the console is not one click away."""
    admin = await _profile(UserRole.admin)

    response = await client.delete(f"/api/v1/admin/players/{admin.id}", headers=_auth(admin))

    assert response.status_code == 422
    assert (await _reload(admin.id)).deleted_at is None


async def test_the_console_lists_invites_and_leagues_across_every_league(
    client: AsyncClient,
) -> None:
    """A site admin is in no league by default, which is exactly why these exist."""
    admin = await _profile(UserRole.admin)
    owner = await _profile()
    league = await _league_for(owner)
    async with AsyncSessionLocal() as session:
        session.add(
            Invite(
                token=f"tok-{uuid.uuid4().hex[:12]}",
                league_id=league.id,
                created_by=owner.id,
            )
        )
        await session.commit()

    leagues = await client.get("/api/v1/admin/leagues", headers=_auth(admin))
    assert leagues.status_code == 200
    mine = next(entry for entry in leagues.json() if entry["id"] == str(league.id))
    assert mine["member_count"] == 1
    assert mine["join_code"]

    invites = await client.get("/api/v1/admin/invites", headers=_auth(admin))
    assert invites.status_code == 200
    entry = next(i for i in invites.json() if i["league_id"] == str(league.id))
    assert entry["created_by_name"] == owner.display_name
    assert entry["claimed_by_name"] is None
    assert entry["is_active"] is True

    revoked = await client.delete(f"/api/v1/admin/invites/{entry['id']}", headers=_auth(admin))
    assert revoked.status_code == 204
    after = await client.get("/api/v1/admin/invites", headers=_auth(admin))
    assert next(i for i in after.json() if i["id"] == entry["id"])["is_active"] is False


async def test_rotating_a_join_code_works_on_a_league_the_admin_is_not_in(
    client: AsyncClient,
) -> None:
    admin = await _profile(UserRole.admin)
    owner = await _profile()
    league = await _league_for(owner)
    before = league.join_code

    response = await client.post(
        f"/api/v1/admin/leagues/{league.id}/rotate-join-code", headers=_auth(admin)
    )

    assert response.status_code == 200, response.text
    assert response.json()["join_code"] != before
    async with AsyncSessionLocal() as session:
        stored = await session.get(League, league.id)
        assert stored is not None and stored.join_code == response.json()["join_code"]


# ── The gate, asserted by walking the router ───────────────────────────────────


def _admin_routes() -> list[tuple[str, str]]:
    """Every (method, path) the admin router serves, read from the router itself.

    Walked rather than listed so a route added without the ``AdminUser`` dependency fails
    here instead of shipping — a hand-written list only ever covers the routes somebody
    remembered to add to it, which is the same class of omission this batch found in the
    league-admin reset.
    """
    routes: list[tuple[str, str]] = []
    for route in admin_router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        routes.extend((method, path) for method in sorted(methods) if method != "HEAD")
    return routes


def _fill(path: str, ident: uuid.UUID) -> str:
    """Substitute any path parameter with one real-looking id."""
    parts = [
        str(ident) if segment.startswith("{") and segment.endswith("}") else segment
        for segment in path.split("/")
    ]
    return "/".join(parts)


async def test_every_admin_endpoint_refuses_a_player(client: AsyncClient) -> None:
    """403 for a signed-in non-admin, on every route the router carries."""
    player = await _profile()
    target = await _profile()
    routes = _admin_routes()
    assert len(routes) >= 8, "the router lost its routes, not its gate"

    for method, path in routes:
        response = await client.request(
            method, _fill(path, target.id), headers=_auth(player), json={}
        )
        assert response.status_code == 403, f"{method} {path} answered {response.status_code}"


async def test_every_admin_endpoint_refuses_an_anonymous_caller(client: AsyncClient) -> None:
    """401/403 without a token — never a 200, and never a 500."""
    target = await _profile()

    for method, path in _admin_routes():
        response = await client.request(method, _fill(path, target.id), json={})
        assert response.status_code in (
            401,
            403,
        ), f"{method} {path} answered {response.status_code}"
