"""Batch 125 — oversight is a read. Acting inside a league is not.

`require_league_member` let site admins past the membership check, and the bypass
covered **writes** as well as reads. A site admin who had never joined a league could
submit a pick, which *consumes a selection from that league's pool* — one pick per
member per round, unique within the league — so it took the selection away from a
genuine member. The admin appeared in no member list and no standing, and could not undo
it by leaving, because there was no membership to leave.

The bypass is kept for reads, which is what oversight means: look at any league without
joining it and appearing on its table. Writes go through
`require_league_member_write`, which has no bypass at all.

Postgres-backed and non-hermetic: these drive the HTTP endpoints, which commit through
their own sessions.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import require_league_member as deps_read_member
from src.main import app
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile, UserRole
from src.routers.leagues import require_league_member as leagues_read_member

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

#: The two read-variant dependencies, which no mutating route may depend on.
READ_ONLY_MEMBER_DEPS = {deps_read_member, leagues_read_member}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(role: UserRole = UserRole.player) -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=f"wa-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=role,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _league(owner: Profile) -> League:
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(slug=f"wa-{tag}", name=f"Write Access {tag}", created_by=owner.id)
        session.add(league)
        await session.flush()
        session.add(
            LeagueMembership(league_id=league.id, player_id=owner.id, role=LeagueMemberRole.admin)
        )
        await session.commit()
        await session.refresh(league)
        return league


# ── The finding ───────────────────────────────────────────────────────────────


async def test_a_non_member_site_admin_is_refused_on_the_pick_path(client: AsyncClient) -> None:
    """The write that took a selection from a real member."""
    member = await _profile()
    league = await _league(member)
    site_admin = await _profile(UserRole.admin)

    refused = await client.post(
        f"/api/v1/leagues/{league.slug}/picks",
        json={"fixture_id": str(uuid.uuid4()), "market": "MATCH_ODDS", "outcome": "HOME"},
        headers=_auth(site_admin),
    )

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == "League membership required"
    # Refused by the dependency, so nothing downstream ran and no pick exists.
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(Pick).where(Pick.player_id == site_admin.id))
        assert rows.scalars().all() == []


async def test_a_non_member_site_admin_is_refused_on_the_per_league_display_name(
    client: AsyncClient,
) -> None:
    """The other write that reached through the bypass."""
    member = await _profile()
    league = await _league(member)
    site_admin = await _profile(UserRole.admin)

    refused = await client.put(
        f"/api/v1/leagues/{league.slug}/members/me/display-name",
        json={"display_name_override": "Gatecrasher"},
        headers=_auth(site_admin),
    )

    assert refused.status_code == 403, refused.text


# ── The half that must not have moved ─────────────────────────────────────────


async def test_site_admin_read_access_to_any_league_is_unchanged(client: AsyncClient) -> None:
    """Oversight is the reason the bypass exists, and it is untouched."""
    member = await _profile()
    league = await _league(member)
    site_admin = await _profile(UserRole.admin)

    for path in (
        f"/api/v1/leagues/{league.slug}/members",
        f"/api/v1/leagues/{league.slug}/standings",
        f"/api/v1/leagues/{league.slug}/seasons",
        f"/api/v1/leagues/{league.slug}/results",
        f"/api/v1/leagues/{league.slug}/gameweeks",
    ):
        response = await client.get(path, headers=_auth(site_admin))
        assert response.status_code == 200, (path, response.text)


async def test_an_ordinary_non_member_is_still_refused_on_reads(client: AsyncClient) -> None:
    """The bypass is for site admins, not for everyone — asserted so the split cannot
    be 'fixed' by removing the check instead of the bypass."""
    member = await _profile()
    league = await _league(member)
    stranger = await _profile()

    response = await client.get(f"/api/v1/leagues/{league.slug}/members", headers=_auth(stranger))
    assert response.status_code == 403, response.text


async def test_a_real_member_still_reaches_the_write_paths(client: AsyncClient) -> None:
    """The write variant must refuse non-members, not members.

    The display-name write is the one of the two that needs no slate, so it is the one
    that can prove the dependency admits a genuine member.
    """
    member = await _profile()
    league = await _league(member)

    accepted = await client.put(
        f"/api/v1/leagues/{league.slug}/members/me/display-name",
        json={"display_name_override": f"Ace {uuid.uuid4().hex[:4]}"},
        headers=_auth(member),
    )
    assert accepted.status_code == 204, accepted.text


# ── The guard, so the next write cannot pick the wrong door ───────────────────


def _api_routes() -> list[APIRoute]:
    """Every `APIRoute` in the app, reached through the routers it was included from.

    `app.routes` is **not** a flat list of routes on fastapi 0.141: `include_router`
    leaves `_IncludedRouter` wrappers, which expose no `.routes` and only reach their
    own through `.original_router`. Walking the top level alone finds the four OpenAPI
    routes and nothing else — which is exactly how a guard like the one below passes
    while asserting nothing, so `test_the_route_walk_actually_finds_the_routes` exists
    to catch that happening again on a future upgrade.
    """
    found: list[APIRoute] = []
    stack: list[object] = list(app.routes)
    seen: set[int] = set()
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, APIRoute):
            found.append(item)
        for attr in ("routes", "original_router"):
            nested = getattr(item, attr, None)
            if nested is None:
                continue
            stack.extend(nested if isinstance(nested, list) else [nested])
    return found


def _dependency_calls(route: APIRoute) -> set[object]:
    found: set[object] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            found.add(dep.call)
        stack.extend(dep.dependencies)
    return found


def test_the_route_walk_actually_finds_the_routes() -> None:
    """Guards the guard below, which is worthless if it walks an empty list."""
    routes = _api_routes()
    assert len(routes) > 50, f"only found {len(routes)} routes — the walk is wrong"
    paths = {route.path for route in routes}
    assert any(path.endswith("/picks") for path in paths), sorted(paths)[:5]


def test_no_mutating_route_depends_on_the_read_variant() -> None:
    """The structural half.

    Splitting the dependency fixes today's two call sites; this is what stops the third
    from quietly choosing the bypassing one. A route that legitimately must not require
    membership — joining, claiming an invite — depends on neither variant and is
    untouched by this.
    """
    offenders = [
        f"{sorted(route.methods & MUTATING)} {route.path}"
        for route in _api_routes()
        if route.methods & MUTATING and _dependency_calls(route) & READ_ONLY_MEMBER_DEPS
    ]
    assert offenders == [], (
        "these change league state through the read-variant membership dependency, "
        "which lets a non-member site admin act inside the league: " + ", ".join(offenders)
    )
