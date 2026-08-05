"""End-to-end pick → settle → standings flow on real Postgres.

Skipped unless ``DATABASE_URL`` points at a migrated database (the repo runs it via the
pgserver harness, mirroring Batch 1). It proves the pieces the pure tests can't:

* the submit endpoint snapshots the provider's odds and enforces uniqueness **both ways**
  (a taken selection → 409; a member's re-pick updates in place, freeing the old one);
* the two ``picks`` unique constraints reject duplicates at the DB level (the race backstop);
* an unpriced / locked selection is refused;
* ``settle_gameweek`` awards ``round(odds×10)``, and ``standings`` / ``build_coupon`` read back.
"""

from __future__ import annotations

import itertools
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services import coupon as coupon_svc
from src.services import scoring
from src.services.betfair import (
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import sync_slate

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

# Canned sample winners: Arsenal (home, EPL) and Forfar (home, SL2).
SAMPLE_ARSENAL_SEL = 1001
SAMPLE_FORFAR_SEL = 2001


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _auth(profile: Profile) -> dict[str, str]:
    token = create_access_token(profile.id, profile.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client_and_fake() -> AsyncIterator[tuple[AsyncClient, FakeBetfair]]:
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.pop(get_odds_provider, None)


async def _seed_league(session: AsyncSession, names: list[str]) -> tuple[list[Profile], League]:
    """Create N players and a league they all belong to; returns (players, league)."""
    tag = uuid.uuid4().hex[:8]
    players = [
        Profile(display_name=f"{name}-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
        for name in names
    ]
    session.add_all(players)
    await session.flush()
    league = League(slug=f"cpn-{tag}", name=f"Coupon {tag}", created_by=players[0].id)
    session.add(league)
    await session.flush()
    for player in players:
        session.add(LeagueMembership(league_id=league.id, player_id=player.id))
    await session.commit()
    for player in players:
        await session.refresh(player)
    await session.refresh(league)
    return players, league


async def _open_sample_gameweek(session: AsyncSession, fake: FakeBetfair) -> Gameweek:
    """Sync the sample slate and force it open (lock in the future, independent of now)."""
    slate = await fake.fetch_slate(SAMPLE_SATURDAY)
    gameweek = await sync_slate(session, slate)
    gameweek.status = GameweekStatus.open
    gameweek.locks_at_utc = _now() + timedelta(hours=2)
    await session.commit()
    await session.refresh(gameweek)
    return gameweek


async def _fixture_ids(session: AsyncSession, gameweek_id: uuid.UUID) -> dict[str, str]:
    result = await session.execute(select(Fixture).where(Fixture.gameweek_id == gameweek_id))
    return {f.provider_event_id: str(f.id) for f in result.scalars().all()}


async def _submit(
    client: AsyncClient, slug: str, player: Profile, fixture_id: str, market: str, outcome: str
) -> Response:
    return await client.post(
        f"/api/v1/leagues/{slug}/picks",
        json={"fixture_id": fixture_id, "market": market, "outcome": outcome},
        headers=_auth(player),
    )


# ── The full flow ─────────────────────────────────────────────────────────────


async def test_full_pick_flow(client_and_fake: tuple[AsyncClient, FakeBetfair]) -> None:
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob, carol, dave), league = await _seed_league(
            session, ["alice", "bob", "carol", "dave"]
        )
        gameweek = await _open_sample_gameweek(session, fake)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]
    slug = league.slug

    # Alice grabs Arsenal (home); Bob grabs Chelsea (away) — same fixture, distinct picks.
    r = await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")
    assert r.status_code == 201, r.text
    assert r.json()["odds"] == 1.9 and r.json()["status"] == "pending"
    assert (await _submit(client, slug, bob, epl, "MATCH_ODDS", "AWAY")).status_code == 201

    # Carol is blocked from Arsenal (taken), so takes BTTS Yes instead.
    blocked = await _submit(client, slug, carol, epl, "MATCH_ODDS", "HOME")
    assert blocked.status_code == 409 and blocked.json()["detail"] == "SELECTION_TAKEN"
    assert (
        await _submit(client, slug, carol, epl, "BOTH_TEAMS_TO_SCORE", "YES")
    ).status_code == 201

    # Alice re-picks (Forfar, SL2): updates in place and frees Arsenal.
    assert (await _submit(client, slug, alice, sl2, "MATCH_ODDS", "HOME")).status_code == 201
    # Carol now grabs the freed Arsenal (re-pick away from BTTS).
    assert (await _submit(client, slug, carol, epl, "MATCH_ODDS", "HOME")).status_code == 201

    async with AsyncSessionLocal() as session:
        # One pick per member (re-picks updated in place, not appended).
        alice_picks = await session.execute(
            select(func.count())
            .select_from(Pick)
            .where(Pick.league_id == league.id, Pick.player_id == alice.id)
        )
        assert alice_picks.scalar_one() == 1
        total = await session.execute(
            select(func.count()).select_from(Pick).where(Pick.gameweek_id == gameweek.id)
        )
        assert total.scalar_one() == 3  # alice, bob, carol (dave never picked)

        await _assert_db_constraints(session, league.id, gameweek.id, epl, alice, dave)

        # Settle: Arsenal (EPL) and Forfar (SL2) win.
        fake.close_markets(
            {
                SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
                SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
            }
        )
        settlements = await fake.settle([SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID])
        gameweek = (
            await session.execute(select(Gameweek).where(Gameweek.id == gameweek.id))
        ).scalar_one()
        resolved = await scoring.settle_gameweek(session, gameweek, settlements)
        await session.commit()
        assert resolved == 3
        assert gameweek.status is GameweekStatus.settled

        await _assert_scores(session, league.id, alice.id, bob.id, carol.id)

        standings = await scoring.standings(session, league.id)
        by_name = {s.display_name.split("-")[0]: s for s in standings}
        assert by_name["alice"].total_points == 24 and by_name["alice"].rank == 1
        assert by_name["carol"].total_points == 19 and by_name["carol"].rank == 2
        assert by_name["bob"].total_points == 0 and by_name["bob"].rank == 3
        assert by_name["bob"].picks_played == 1 and by_name["bob"].picks_won == 0
        # A member who never picked still appears, tied on 0.
        assert by_name["dave"].total_points == 0 and by_name["dave"].picks_played == 0

        coupon = await coupon_svc.build_coupon(session, league.id, gameweek)
        assert coupon.leg_count == 3
        assert coupon.combined_odds == 19.61  # 2.4 × 4.3 × 1.9 = 19.608
        assert coupon.all_won is False  # Bob's Chelsea lost
        assert coupon.status == "settled"


async def _assert_db_constraints(
    session: AsyncSession,
    league_id: uuid.UUID,
    gameweek_id: uuid.UUID,
    epl_fixture_id: str,
    alice: Profile,
    dave: Profile,
) -> None:
    """Both unique constraints reject duplicates at the DB level (race backstop)."""
    # (1) one pick per member per gameweek — a 2nd row for Alice violates it.
    session.add(
        Pick(
            league_id=league_id,
            gameweek_id=gameweek_id,
            fixture_id=uuid.UUID(epl_fixture_id),
            player_id=alice.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.DRAW,
            runner_name="The Draw",
            odds_at_pick=Decimal("3.75"),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    # (2) no two members hold the same selection — Dave taking Arsenal (Carol holds it).
    session.add(
        Pick(
            league_id=league_id,
            gameweek_id=gameweek_id,
            fixture_id=uuid.UUID(epl_fixture_id),
            player_id=dave.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Arsenal",
            odds_at_pick=Decimal("1.90"),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def _assert_scores(
    session: AsyncSession,
    league_id: uuid.UUID,
    alice_id: uuid.UUID,
    bob_id: uuid.UUID,
    carol_id: uuid.UUID,
) -> None:
    picks = {
        p.player_id: p
        for p in (await session.execute(select(Pick).where(Pick.league_id == league_id))).scalars()
    }
    assert picks[alice_id].status is PickStatus.won and picks[alice_id].points_awarded == 24
    assert picks[carol_id].status is PickStatus.won and picks[carol_id].points_awarded == 19
    assert picks[bob_id].status is PickStatus.lost and picks[bob_id].points_awarded == 0


# ── Edge cases: unpriced selection and a locked gameweek ──────────────────────


async def test_unpriced_selection_is_refused(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["solo"])
        gameweek = Gameweek(
            saturday_date=date(2026, 8, 15),
            status=GameweekStatus.open,
            locks_at_utc=_now() + timedelta(hours=2),
        )
        session.add(gameweek)
        await session.flush()
        fixture = Fixture(
            gameweek_id=gameweek.id,
            provider_event_id=SAMPLE_SL2_EVENT_ID,
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=_now(),
            competition="Scottish League Two",
            competition_id="10932510",
        )
        session.add(fixture)
        await session.commit()
        fixture_id = str(fixture.id)

    # BTTS "No" is unpriced in the sample SL2 market → not offerable.
    r = await _submit(client, league.slug, alice, fixture_id, "BOTH_TEAMS_TO_SCORE", "NO")
    assert r.status_code == 422 and r.json()["detail"] == "SELECTION_NOT_AVAILABLE"


async def test_locked_gameweek_rejects_submit(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["latecomer"])
        gameweek = Gameweek(
            saturday_date=date(2026, 8, 22),
            status=GameweekStatus.open,
            locks_at_utc=_now() - timedelta(minutes=1),  # already past 14:30
        )
        session.add(gameweek)
        await session.flush()
        fixture = Fixture(
            gameweek_id=gameweek.id,
            provider_event_id=SAMPLE_EPL_EVENT_ID,
            home="Arsenal",
            away="Chelsea",
            kickoff_utc=_now(),
            competition="English Premier League",
            competition_id="10932509",
        )
        session.add(fixture)
        await session.commit()
        fixture_id = str(fixture.id)

    r = await _submit(client, league.slug, alice, fixture_id, "MATCH_ODDS", "HOME")
    assert r.status_code == 409 and r.json()["detail"] == "PICKS_LOCKED"


# ── Batch 9: the slate's member roster and fixture-level picked marker ────────

# Distinct far-future Saturdays for the tests below. ``saturday_date`` is unique,
# so each caller needs its own.
_LATEST_SATURDAYS = itertools.count()


async def _open_sample_gameweek_as_latest(session: AsyncSession, fake: FakeBetfair) -> Gameweek:
    """Open the sample slate and make it unambiguously the newest gameweek.

    ``latest_gameweek`` — which is what ``GET .../gameweek/current`` reads — takes
    the maximum ``saturday_date``, and the edge-case tests above commit gameweeks
    dated after ``SAMPLE_SATURDAY``. Any test that reads the slate endpoint has to
    out-date every other gameweek in the shared database or it silently asserts
    against someone else's gameweek.
    """
    gameweek = await _open_sample_gameweek(session, fake)
    gameweek.saturday_date = date(2090, 1, 7) + timedelta(weeks=next(_LATEST_SATURDAYS))
    await session.commit()
    await session.refresh(gameweek)
    return gameweek


async def test_slate_reports_roster_and_fixture_level_marker(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The slate names every member, who is missing, and which games are spoken for."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob, carol), league = await _seed_league(session, ["alice", "bob", "carol"])
        gameweek = await _open_sample_gameweek_as_latest(session, fake)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]
    slug = league.slug

    # Alice and Bob take different selections on the *same* fixture — legal under
    # the selection-level rule, and the case the fixture marker has to collapse.
    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    assert (await _submit(client, slug, bob, epl, "MATCH_ODDS", "AWAY")).status_code == 201

    slate = (
        await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(alice))
    ).json()

    # Roster: three members, ordered by display name, one of them yet to pick.
    assert [m["display_name"] for m in slate["members"]] == sorted(
        m["display_name"] for m in slate["members"]
    )
    assert len(slate["members"]) == 3
    assert slate["members_missing_picks"] == 1
    by_name = {m["display_name"].split("-")[0]: m for m in slate["members"]}
    assert by_name["alice"]["has_picked"] is True
    assert by_name["alice"]["fixture_id"] == epl
    assert by_name["alice"]["home"] == "Arsenal"
    assert by_name["alice"]["odds"] == 1.9
    assert by_name["carol"]["has_picked"] is False
    assert by_name["carol"]["fixture_id"] is None and by_name["carol"]["odds"] is None

    fixture_by_id = {f["fixture_id"]: f for f in slate["fixtures"]}
    # Two holders on the EPL game, named once each; Alice sees it as hers.
    assert sorted(n.split("-")[0] for n in fixture_by_id[epl]["taken_by_names"]) == [
        "alice",
        "bob",
    ]
    assert fixture_by_id[epl]["mine"] is True
    # The untouched fixture carries no marker at all.
    assert fixture_by_id[sl2]["taken_by_names"] == []
    assert fixture_by_id[sl2]["mine"] is False

    # Bob holds the same fixture but a different selection — so it is his too.
    bob_slate = (
        await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(bob))
    ).json()
    assert {f["fixture_id"]: f for f in bob_slate["fixtures"]}[epl]["mine"] is True
    # Carol has picked nothing, so no fixture is hers.
    carol_slate = (
        await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(carol))
    ).json()
    assert all(f["mine"] is False for f in carol_slate["fixtures"])
    assert carol_slate["members_missing_picks"] == 1


async def test_one_member_holding_two_selections_is_named_once(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A re-pick within a fixture must not duplicate the holder in the marker."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["solo"])
        gameweek = await _open_sample_gameweek_as_latest(session, fake)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice))
    ).json()
    marker = {f["fixture_id"]: f for f in slate["fixtures"]}[epl]
    assert len(marker["taken_by_names"]) == 1
    assert slate["members_missing_picks"] == 0
