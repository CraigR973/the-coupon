"""Batch 126 — one name, one member, within a league.

The per-league display-name override stored whatever it was sent, bounded only by the
column's 100 characters: no charset, no normalisation, and **no uniqueness at all**.
The roster, the standings and the coupon all render the override, so two members could
appear under one name — and the owner's text-only decision makes the name the whole of
a member's identity here, so that is impersonation rather than a cosmetic clash.

Registration has enforced the charset and case-insensitive uniqueness since Batch 63.
This path was the gap. The rules now live in `src.display_name` and both paths read
them from there.

Postgres-backed and non-hermetic: these drive the HTTP endpoints, which commit through
their own sessions.
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
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.routers.league_memberships import NAME_TAKEN_IN_LEAGUE

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

PATH = "/api/v1/leagues/{slug}/members/me/display-name"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(display_name: str | None = None) -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=display_name or f"dn-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=UserRole.player,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _league(*members: Profile) -> League:
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(slug=f"dn-{tag}", name=f"Display Name {tag}", created_by=members[0].id)
        session.add(league)
        await session.flush()
        for index, member in enumerate(members):
            session.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=member.id,
                    role=LeagueMemberRole.admin if index == 0 else LeagueMemberRole.player,
                )
            )
        await session.commit()
        await session.refresh(league)
        return league


async def _override_of(league_id: uuid.UUID, player_id: uuid.UUID) -> str | None:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(LeagueMembership.display_name_override).where(
                    LeagueMembership.league_id == league_id,
                    LeagueMembership.player_id == player_id,
                )
            )
        ).scalar_one()


# -- The finding ---------------------------------------------------------------


async def test_an_override_colliding_with_another_members_name_is_refused(
    client: AsyncClient,
) -> None:
    """Taking someone's exact name, which is the whole of their identity here."""
    taken = f"Alice {uuid.uuid4().hex[:6]}"
    victim = await _profile(taken)
    impersonator = await _profile()
    league = await _league(victim, impersonator)

    refused = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": taken},
        headers=_auth(impersonator),
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == NAME_TAKEN_IN_LEAGUE
    assert await _override_of(league.id, impersonator.id) is None


async def test_the_collision_check_ignores_case_and_padding(client: AsyncClient) -> None:
    """A padded, lower-cased copy reads as the same name on a league table."""
    tag = uuid.uuid4().hex[:6]
    victim = await _profile(f"Alice {tag}")
    impersonator = await _profile()
    league = await _league(victim, impersonator)

    refused = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": f"  alice   {tag.upper()}  "},
        headers=_auth(impersonator),
    )

    assert refused.status_code == 409, refused.text


async def test_an_override_colliding_with_another_members_override_is_refused(
    client: AsyncClient,
) -> None:
    """The effective name is what is rendered, so the effective name is what must be
    unique — not the profile name underneath it."""
    first = await _profile()
    second = await _profile()
    league = await _league(first, second)

    claimed = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "The Gaffer"},
        headers=_auth(first),
    )
    assert claimed.status_code == 204, claimed.text

    refused = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "the gaffer"},
        headers=_auth(second),
    )
    assert refused.status_code == 409, refused.text


async def test_the_charset_rules_are_the_registration_ones(client: AsyncClient) -> None:
    """Reused rather than restated — the point of moving them to `src.display_name`."""
    member = await _profile()
    league = await _league(member)

    rejected = [
        "  ",
        "a",
        "x" * 33,
        # Leading *whitespace* is trimmed by normalisation, so it is legal; leading
        # punctuation is not, because a name must not be able to sort itself first.
        "-leading-punct",
        ".dotfile",
        # Built rather than written literally, so nothing in the toolchain between here
        # and the test runner can quietly normalise it away.
        "party " + chr(0x1F389),
        chr(0) + "null",
        "semi;colon",
        "<script>",
    ]
    for bad in rejected:
        refused = await client.put(
            PATH.format(slug=league.slug),
            json={"display_name_override": bad},
            headers=_auth(member),
        )
        assert refused.status_code == 422, (repr(bad), refused.status_code, refused.text)


# -- The halves that must keep working -----------------------------------------


async def test_clearing_the_override_still_works(client: AsyncClient) -> None:
    """Explicitly, because a uniqueness check applied to `None` would break it."""
    member = await _profile()
    league = await _league(member)

    await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "Gaffer"},
        headers=_auth(member),
    )
    assert await _override_of(league.id, member.id) == "Gaffer"

    cleared = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": None},
        headers=_auth(member),
    )

    assert cleared.status_code == 204, cleared.text
    assert await _override_of(league.id, member.id) is None


async def test_a_free_name_is_accepted_and_stored_normalised(client: AsyncClient) -> None:
    member = await _profile()
    league = await _league(member)

    accepted = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "  The   Gaffer  "},
        headers=_auth(member),
    )

    assert accepted.status_code == 204, accepted.text
    assert await _override_of(league.id, member.id) == "The Gaffer"


async def test_keeping_your_own_override_is_not_a_collision_with_yourself(
    client: AsyncClient,
) -> None:
    """The exclusion that makes the check usable rather than a one-way door."""
    member = await _profile()
    league = await _league(member)

    first = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "Gaffer"},
        headers=_auth(member),
    )
    assert first.status_code == 204

    again = await client.put(
        PATH.format(slug=league.slug),
        json={"display_name_override": "Gaffer"},
        headers=_auth(member),
    )
    assert again.status_code == 204, again.text


async def test_the_same_name_is_free_in_a_different_league(client: AsyncClient) -> None:
    """Uniqueness is *within a league*. Two leagues are two games (AGENTS.md)."""
    taken = f"Alice {uuid.uuid4().hex[:6]}"
    taken_by = await _profile(taken)
    member = await _profile()
    here = await _league(taken_by, member)
    elsewhere = await _league(member)

    refused = await client.put(
        PATH.format(slug=here.slug),
        json={"display_name_override": taken},
        headers=_auth(member),
    )
    assert refused.status_code == 409

    allowed = await client.put(
        PATH.format(slug=elsewhere.slug),
        json={"display_name_override": taken},
        headers=_auth(member),
    )
    assert allowed.status_code == 204, allowed.text
