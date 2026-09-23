"""Batch 145 — the Saturday slate goes down a phone compressed.

A fully-priced 264-fixture slate is about 84 KB of JSON and is the single biggest thing a
member downloads, on the one morning the whole league opens the app at once. Nothing in
the API compressed anything, and production sent no ``vary: accept-encoding``.

The threshold is the interesting decision and these tests pin both sides of it. Above it
are slates, rosters and tables — data the whole league can already see. Below it are the
responses that carry credentials, and **a compressed response leaks its own length**, so
compressing a token beside anything a caller can influence is the shape BREACH attacks.
There is nothing to buy by taking that risk: a kilobyte saved once at sign-in is not the
payload this batch exists for.

Postgres-backed; these tests commit.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile, UserRole
from src.services.betfair import FakeBetfair

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The middleware's floor, asserted here so a change to it has to change this file too.
MINIMUM_COMPRESSED_SIZE = 4096


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """The slate route reaches the odds provider; these tests are about the bytes, not it.

    The canned provider knows none of the event ids seeded below, so every fixture comes
    back unpriced — which is the *larger* slate anyway, since an unpriced fixture still
    carries its two teams, its kick-off and its competition.
    """
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    app.dependency_overrides[get_optional_odds_provider] = lambda: fake
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


def _auth(person: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(person.id, person.role)}"}


def _wire_bytes(response) -> int:  # noqa: ANN001
    """What actually crossed the wire. ``response.content`` is what httpx decoded."""
    return int(response.headers["content-length"])


async def _big_slate(db: AsyncSession, *, members: int, fixtures: int) -> tuple[Profile, str]:
    """A league big enough to clear the threshold: a full roster and a full card."""
    tag = uuid.uuid4().hex[:8]
    people = [
        Profile(
            display_name=f"member-{n:02d}-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player
        )
        for n in range(members)
    ]
    db.add_all(people)
    await db.flush()
    league = League(slug=f"b145-{tag}", name=f"Batch 145 {tag}", created_by=people[0].id)
    db.add(league)
    await db.flush()
    for person in people:
        db.add(LeagueMembership(league_id=league.id, player_id=person.id))
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=_now().date() + timedelta(days=2),
        status=GameweekStatus.open,
        locks_at_utc=_now() + timedelta(hours=6),
    )
    db.add(gameweek)
    await db.flush()
    for n in range(fixtures):
        fixture = Fixture(
            provider_event_id=f"b145-{tag}-{n:03d}",
            home=f"Hometown Wanderers {n:03d}",
            away=f"Awayfield Athletic {n:03d}",
            kickoff_utc=_now() + timedelta(days=2, hours=3),
            competition="Test Division",
            competition_id="test-div-compression",
        )
        db.add(fixture)
        await db.flush()
        db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    await db.commit()
    return people[0], league.slug


async def test_the_saturday_slate_goes_down_the_wire_compressed(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The payload this batch exists for, measured both ways.

    ``content-length`` is what actually crossed the wire; ``response.content`` is what the
    client got after decoding. The gap between them is the batch.
    """
    member, slug = await _big_slate(session, members=12, fixtures=60)
    url = f"/api/v1/leagues/{slug}/gameweek/current"

    plain = await client.get(url, headers={**_auth(member), "Accept-Encoding": "identity"})
    zipped = await client.get(url, headers={**_auth(member), "Accept-Encoding": "gzip"})

    assert plain.status_code == 200 and zipped.status_code == 200
    assert plain.headers.get("content-encoding") is None
    assert zipped.headers.get("content-encoding") == "gzip"

    uncompressed = len(plain.content)
    on_the_wire = _wire_bytes(zipped)
    assert uncompressed > MINIMUM_COMPRESSED_SIZE, "the test slate must clear the threshold"
    # Measured on this shape: 23,205 bytes of JSON down to 3,131 on the wire, 7.4x. The
    # bound is 3x rather than 7x so it pins "it is compressing" without pinning gzip's
    # exact output, which a library upgrade may legitimately move by a few percent.
    assert on_the_wire < uncompressed / 3, f"{on_the_wire} vs {uncompressed} uncompressed"
    # Decoded, the two are the same response.
    assert zipped.json() == plain.json()


async def test_a_response_carrying_a_credential_is_never_compressed(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The reason the threshold is 4 KB and not Starlette's 500 bytes.

    A compressed response leaks its own length. Sign-in hands back tokens, and a token is
    exactly the secret a length oracle is worth mounting against — so the responses that
    carry one stay below the floor and go out in plain bytes.
    """
    tag = uuid.uuid4().hex[:8]
    person = Profile(display_name=f"signer-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    session.add(person)
    await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"display_name": person.display_name, "pin": "1234"},
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200, response.text
    assert "access_token" in response.json(), "the premise: this response carries a credential"
    assert response.headers.get("content-encoding") is None, "a token was compressed"
    assert len(response.content) < MINIMUM_COMPRESSED_SIZE, (
        "a credential-bearing response grew past the floor that keeps it uncompressed — "
        "raise the floor or stop returning it here, but do not let it be compressed"
    )


async def test_a_client_that_asks_for_no_encoding_still_gets_its_json(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Compression is an offer, not a requirement — and the offer must be advertised."""
    member, slug = await _big_slate(session, members=4, fixtures=60)

    response = await client.get(
        f"/api/v1/leagues/{slug}/gameweek/current",
        headers={**_auth(member), "Accept-Encoding": "identity"},
    )

    assert response.status_code == 200
    assert response.headers.get("content-encoding") is None
    assert response.json()["gameweek_id"]


async def test_the_vary_header_carries_both_things_the_response_varies_on(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A cache that keys on one of them and not the other serves the wrong bytes.

    CORS varies the response on ``Origin`` and compression varies it on
    ``Accept-Encoding``. Two middlewares write the same header, and the second must add to
    it rather than replace it — which is the kind of thing that is only ever noticed by a
    shared cache handing a phone a gzip body it did not ask for.
    """
    member, slug = await _big_slate(session, members=4, fixtures=60)

    response = await client.get(
        f"/api/v1/leagues/{slug}/gameweek/current",
        headers={
            **_auth(member),
            "Accept-Encoding": "gzip",
            "Origin": "http://localhost:5173",
        },
    )

    assert response.status_code == 200
    vary = {part.strip().lower() for part in response.headers.get("vary", "").split(",")}
    assert "accept-encoding" in vary, "nothing tells a cache the body depends on the encoding"
    assert "origin" in vary, "compression overwrote the Vary CORS set"
