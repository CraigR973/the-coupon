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

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League, PickScope
from src.models.league_membership import LeagueMemberRole, LeagueMembership
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
from src.services.gameweek import fixtures_for, members_missing_picks, sync_slate, window_for

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


async def _open_sample_gameweek(
    session: AsyncSession, fake: FakeBetfair, league: League, *, weeks_later: int = 0
) -> Gameweek:
    """Give ``league`` the canned card as an open round (lock in the future).

    Rounds are per-league since Batch 14, so every test's freshly seeded league gets
    its own and no test can collide with another's. ``weeks_later`` shifts the round
    forward for tests that need a league to have more than one — the canned slate
    only exists on ``SAMPLE_SATURDAY``, so the card is synced from there and the date
    moved afterwards.
    """
    slate = await fake.fetch_slate(window_for(league), SAMPLE_SATURDAY)
    if weeks_later:
        # Shift the *slate* rather than the synced round: moving the round afterwards
        # would find and rename the one already there instead of making a second.
        slate = slate.model_copy(
            update={"starts_on": SAMPLE_SATURDAY + timedelta(weeks=weeks_later)}
        )
    gameweek = await sync_slate(session, league, slate)
    gameweek.status = GameweekStatus.open
    gameweek.locks_at_utc = _now() + timedelta(hours=2)
    await session.commit()
    await session.refresh(gameweek)
    return gameweek


async def _round_with_one_fixture(
    session: AsyncSession,
    league: League,
    starts_on: date,
    *,
    locks_at: datetime,
    event_id: str,
    home: str,
    away: str,
    competition: str,
    competition_id: str,
) -> tuple[Gameweek, Fixture]:
    """A hand-built round playing exactly one pooled fixture.

    For the edge cases that need a card the canned provider does not offer. Reuses
    a pooled fixture if another league already discovered the same event, since
    ``provider_event_id`` is unique across the pool.
    """
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=GameweekStatus.open,
        locks_at_utc=locks_at,
    )
    session.add(gameweek)
    await session.flush()

    existing = await session.execute(select(Fixture).where(Fixture.provider_event_id == event_id))
    fixture = existing.scalar_one_or_none()
    if fixture is None:
        fixture = Fixture(
            provider_event_id=event_id,
            home=home,
            away=away,
            kickoff_utc=_now(),
            competition=competition,
            competition_id=competition_id,
        )
        session.add(fixture)
        await session.flush()
    session.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    await session.commit()
    await session.refresh(gameweek)
    await session.refresh(fixture)
    return gameweek, fixture


async def _fixture_ids(session: AsyncSession, gameweek_id: uuid.UUID) -> dict[str, str]:
    return {f.provider_event_id: str(f.id) for f in await fixtures_for(session, gameweek_id)}


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
        gameweek = await _open_sample_gameweek(session, fake, league)
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
        gameweek, fixture = await _round_with_one_fixture(
            session,
            league,
            date(2026, 8, 15),
            locks_at=_now() + timedelta(hours=2),
            event_id=SAMPLE_SL2_EVENT_ID,
            home="Forfar Athletic",
            away="Brechin City",
            competition="Scottish League Two",
            competition_id="10932510",
        )
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
        gameweek, fixture = await _round_with_one_fixture(
            session,
            league,
            date(2026, 8, 22),
            locks_at=_now() - timedelta(minutes=1),  # already past the deadline
            event_id=SAMPLE_EPL_EVENT_ID,
            home="Arsenal",
            away="Chelsea",
            competition="English Premier League",
            competition_id="10932509",
        )
        fixture_id = str(fixture.id)

    r = await _submit(client, league.slug, alice, fixture_id, "MATCH_ODDS", "HOME")
    assert r.status_code == 409 and r.json()["detail"] == "PICKS_LOCKED"


# ── Batch 9: the slate's member roster and fixture-level picked marker ────────


async def test_slate_reports_roster_and_fixture_level_marker(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The slate names every member, who is missing, and which games are spoken for."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob, carol), league = await _seed_league(session, ["alice", "bob", "carol"])
        gameweek = await _open_sample_gameweek(session, fake, league)
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
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice))
    ).json()
    marker = {f["fixture_id"]: f for f in slate["fixtures"]}[epl]
    assert len(marker["taken_by_names"]) == 1
    assert slate["members_missing_picks"] == 0


# ── Batch 10: the per-league fixture rule ────────────────────────────────────


async def _set_pick_scope(league: League, scope: PickScope) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(update(League).where(League.id == league.id).values(pick_scope=scope))
        await session.commit()


async def test_fixture_scope_takes_the_whole_game(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Under the fixture rule, claiming any market on a game takes every market."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    await _set_pick_scope(league, PickScope.fixture)
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]
    slug = league.slug

    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201

    # Bob is refused every other market on the same game — the away side, the
    # draw, and BTTS — all of which the selection rule would have allowed.
    for market, outcome in (
        ("MATCH_ODDS", "AWAY"),
        ("MATCH_ODDS", "DRAW"),
        ("BOTH_TEAMS_TO_SCORE", "YES"),
    ):
        refused = await _submit(client, slug, bob, epl, market, outcome)
        assert refused.status_code == 409, f"{market}:{outcome} → {refused.text}"
        assert refused.json()["detail"] == "FIXTURE_TAKEN"

    # A different game is still his for the taking.
    assert (await _submit(client, slug, bob, sl2, "MATCH_ODDS", "HOME")).status_code == 201


async def test_fixture_scope_hides_every_selection_on_a_claimed_game(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The slate must not offer selections the submit endpoint is bound to refuse."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    await _set_pick_scope(league, PickScope.fixture)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201

    slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(bob))
    ).json()
    assert slate["pick_scope"] == "fixture"
    claimed = {f["fixture_id"]: f for f in slate["fixtures"]}[epl]
    assert claimed["selections"], "the fixture should still be priced"
    for selection in claimed["selections"]:
        assert selection["taken_by_player_id"] == str(alice.id)
        assert selection["mine"] is False

    # Alice sees the same game as entirely hers.
    alice_slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice))
    ).json()
    alice_claimed = {f["fixture_id"]: f for f in alice_slate["fixtures"]}[epl]
    assert all(s["mine"] is True for s in alice_claimed["selections"])


async def test_fixture_scope_still_lets_a_member_repick_within_their_own_game(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A member owns the whole game, so switching market inside it is not a conflict."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["solo"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    await _set_pick_scope(league, PickScope.fixture)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    switched = await _submit(client, league.slug, alice, epl, "BOTH_TEAMS_TO_SCORE", "YES")
    assert switched.status_code == 201, switched.text
    assert switched.json()["outcome"] == "YES"


async def test_the_fixture_index_is_the_race_backstop(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The partial unique index rejects a second holder even past the pre-check."""
    _, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    await _set_pick_scope(league, PickScope.fixture)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    async with AsyncSessionLocal() as session:
        for player, outcome in ((alice, PickOutcome.HOME), (bob, PickOutcome.AWAY)):
            session.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=gameweek.id,
                    fixture_id=uuid.UUID(epl),
                    player_id=player.id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=outcome,
                    runner_name="whoever",
                    odds_at_pick=Decimal("2.00"),
                    pick_scope=PickScope.fixture,
                )
            )
        with pytest.raises(IntegrityError):
            await session.commit()

    # The same two rows are fine under the selection rule — the index is partial.
    async with AsyncSessionLocal() as session:
        for player, outcome in ((alice, PickOutcome.HOME), (bob, PickOutcome.AWAY)):
            session.add(
                Pick(
                    league_id=league.id,
                    gameweek_id=gameweek.id,
                    fixture_id=uuid.UUID(epl),
                    player_id=player.id,
                    market=PickMarket.MATCH_ODDS,
                    outcome=outcome,
                    runner_name="whoever",
                    odds_at_pick=Decimal("2.00"),
                    pick_scope=PickScope.selection,
                )
            )
        await session.commit()


async def test_tightening_to_fixture_scope_is_refused_when_it_would_break(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Two members already sharing a game must not be silently made illegal."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]
    slug = league.slug

    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    assert (await _submit(client, slug, bob, epl, "MATCH_ODDS", "AWAY")).status_code == 201

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == alice.id,
            )
            .values(role=LeagueMemberRole.admin)
        )
        await session.commit()

    refused = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={"pick_scope": "fixture"},
        headers=_auth(alice),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "PICK_SCOPE_CONFLICT"

    # Nothing changed: the league is still on the selection rule.
    detail = await client.get(f"/api/v1/leagues/{slug}", headers=_auth(alice))
    assert detail.json()["pick_scope"] == "selection"


async def test_switching_scope_restamps_pending_picks(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Old rows must not be exempted from the rule their league just adopted."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]
    slug = league.slug

    # Different games, so tightening the rule is legal.
    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    assert (await _submit(client, slug, bob, sl2, "MATCH_ODDS", "HOME")).status_code == 201

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == alice.id,
            )
            .values(role=LeagueMemberRole.admin)
        )
        await session.commit()

    ok = await client.patch(
        f"/api/v1/leagues/{slug}", json={"pick_scope": "fixture"}, headers=_auth(alice)
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["pick_scope"] == "fixture"

    async with AsyncSessionLocal() as session:
        scopes = await session.execute(
            select(Pick.pick_scope).where(
                Pick.league_id == league.id, Pick.gameweek_id == gameweek.id
            )
        )
        assert set(scopes.scalars().all()) == {PickScope.fixture}


# ── Batch 12: browsing back through the season ───────────────────────────────


async def test_gameweek_list_counts_fixtures_and_this_leagues_picks(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The season list is the browsable history, counted per league."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        older = await _open_sample_gameweek(session, fake, league)
        newer = await _open_sample_gameweek(session, fake, league, weeks_later=1)
        newer_fixtures = await _fixture_ids(session, newer.id)
    slug = league.slug

    assert (
        await _submit(
            client, slug, alice, newer_fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME"
        )
    ).status_code == 201

    listed = (await client.get(f"/api/v1/leagues/{slug}/gameweeks", headers=_auth(alice))).json()
    by_id = {row["gameweek_id"]: row for row in listed}

    # Newest first, and both gameweeks are retained — nothing is pruned.
    assert [row["gameweek_id"] for row in listed][:2] == [str(newer.id), str(older.id)]
    assert by_id[str(newer.id)]["pick_count"] == 1
    assert by_id[str(older.id)]["pick_count"] == 0
    assert by_id[str(newer.id)]["fixture_count"] >= 2

    # Rounds are per-league since Batch 14, so another league does not merely see
    # these rounds empty — it does not see them at all.
    async with AsyncSessionLocal() as session:
        (carol,), other_league = await _seed_league(session, ["carol"])
    other = (
        await client.get(f"/api/v1/leagues/{other_league.slug}/gameweeks", headers=_auth(carol))
    ).json()
    assert {row["gameweek_id"] for row in other}.isdisjoint({str(newer.id), str(older.id)})


async def test_slate_and_coupon_read_a_named_gameweek(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Both reads default to the latest and both accept an explicit gameweek."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        older = await _open_sample_gameweek(session, fake, league)
        older_fixtures = await _fixture_ids(session, older.id)
    slug = league.slug

    # Pick while only the older round exists — next week's card appears afterwards,
    # which is both the realistic order and the only unambiguous one: the two rounds
    # draw on the same pooled fixtures, so a fixture id alone cannot say which round
    # a submission means.
    assert (
        await _submit(
            client, slug, alice, older_fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME"
        )
    ).status_code == 201

    async with AsyncSessionLocal() as session:
        # Re-fetch: the league instance above belongs to a session that has closed.
        newer = await _open_sample_gameweek(
            session, fake, await session.get(League, league.id), weeks_later=1
        )

    # Default: the latest gameweek, which has no picks.
    default_slate = (
        await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(alice))
    ).json()
    assert default_slate["gameweek_id"] == str(newer.id)
    assert default_slate["members_missing_picks"] == 1

    # Named: the older one, where Alice's pick is still visible.
    past_slate = (
        await client.get(
            f"/api/v1/leagues/{slug}/gameweek/current?gameweek_id={older.id}",
            headers=_auth(alice),
        )
    ).json()
    assert past_slate["gameweek_id"] == str(older.id)
    assert past_slate["members_missing_picks"] == 0

    past_coupon = (
        await client.get(
            f"/api/v1/leagues/{slug}/coupon?gameweek_id={older.id}", headers=_auth(alice)
        )
    ).json()
    assert past_coupon["gameweek_id"] == str(older.id)
    assert past_coupon["leg_count"] == 1

    default_coupon = (
        await client.get(f"/api/v1/leagues/{slug}/coupon", headers=_auth(alice))
    ).json()
    assert default_coupon["gameweek_id"] == str(newer.id)
    assert default_coupon["leg_count"] == 0


async def test_an_unknown_or_malformed_gameweek_id_is_a_404(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A query-string id the caller invented must 404, not 500."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        await _open_sample_gameweek(session, fake, league)
    slug = league.slug

    for bad in (str(uuid.uuid4()), "not-a-uuid", ""):
        slate = await client.get(
            f"/api/v1/leagues/{slug}/gameweek/current?gameweek_id={bad}", headers=_auth(alice)
        )
        coupon = await client.get(
            f"/api/v1/leagues/{slug}/coupon?gameweek_id={bad}", headers=_auth(alice)
        )
        assert slate.status_code == 404, f"{bad!r} → {slate.text}"
        assert coupon.status_code == 404, f"{bad!r} → {coupon.text}"


# ── Batch 13: the per-league member profile ──────────────────────────────────


async def test_profile_reports_this_leagues_record_and_settled_history(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Win rate and history come from the same settled picks the table counts."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]
    slug = league.slug

    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    assert (await _submit(client, slug, bob, sl2, "MATCH_ODDS", "HOME")).status_code == 201

    # Settle: Arsenal (Alice) wins, Forfar (Bob) also wins — then check the split.
    async with AsyncSessionLocal() as session:
        fake.close_markets({SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL})
        settlements = await fake.settle([SAMPLE_EPL_EVENT_ID])
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == gameweek.id))
        ).scalar_one()
        await scoring.settle_gameweek(session, stored, settlements)
        await session.commit()

    profile = (
        await client.get(f"/api/v1/leagues/{slug}/players/{alice.id}/profile", headers=_auth(alice))
    ).json()

    assert profile["display_name"] == alice.display_name
    assert profile["picks_played"] == 1
    assert profile["picks_won"] == 1
    assert profile["win_rate_pct"] == 100
    assert profile["total_points"] == 19  # round(1.90 × 10)

    # History carries the settled pick, and only that one.
    assert len(profile["history"]) == 1
    entry = profile["history"][0]
    assert entry["home"] == "Arsenal" and entry["status"] == "won"
    assert entry["points_awarded"] == 19
    assert entry["odds"] == 1.9

    # Bob's pick never settled, so his record is untested rather than bad.
    bob_profile = (
        await client.get(f"/api/v1/leagues/{slug}/players/{bob.id}/profile", headers=_auth(alice))
    ).json()
    assert bob_profile["picks_played"] == 0
    assert bob_profile["win_rate_pct"] is None
    assert bob_profile["history"] == []


async def test_profile_is_scoped_to_the_league_it_is_read_through(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A member of two leagues has two records, and one league cannot see the other."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), first = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, first)
        fixtures = await _fixture_ids(session, gameweek.id)
        # A second league Alice also belongs to, but has not picked in.
        second = League(slug=f"cpn2-{uuid.uuid4().hex[:8]}", name="Second", created_by=alice.id)
        session.add(second)
        await session.flush()
        session.add(LeagueMembership(league_id=second.id, player_id=alice.id))
        await session.commit()
        second_slug = second.slug
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, first.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201

    in_second = (
        await client.get(
            f"/api/v1/leagues/{second_slug}/players/{alice.id}/profile", headers=_auth(alice)
        )
    ).json()
    assert in_second["picks_played"] == 0, "the other league's picks must not leak in"

    # Bob is not in the second league, so he has no record there.
    missing = await client.get(
        f"/api/v1/leagues/{second_slug}/players/{bob.id}/profile", headers=_auth(alice)
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Player is not in this league"


async def test_profile_rejects_a_non_member_caller_and_a_malformed_id(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        (outsider,), _ = await _seed_league(session, ["outsider"])

    # A member of another league cannot read this league's profiles at all.
    forbidden = await client.get(
        f"/api/v1/leagues/{league.slug}/players/{alice.id}/profile", headers=_auth(outsider)
    )
    assert forbidden.status_code == 403

    # A player id that cannot be a UUID is a miss, not a 500.
    malformed = await client.get(
        f"/api/v1/leagues/{league.slug}/players/not-a-uuid/profile", headers=_auth(alice)
    )
    assert malformed.status_code == 404


# ── Batch 14: per-league rounds and per-league windows ───────────────────────


async def test_two_leagues_play_different_cards_at_the_same_time(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The change Batch 14 exists for: one global round no longer binds everyone."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), saturday_league = await _seed_league(session, ["alice"])
        (bob,), friday_league = await _seed_league(session, ["bob"])
        # A Friday-to-Monday league. The canned card sits on a Saturday, which is
        # inside that range, so both leagues can be given a real slate.
        friday_league.slate_start_weekday = 4
        friday_league.slate_start_minute = 19 * 60
        friday_league.slate_end_weekday = 0
        friday_league.slate_end_minute = 22 * 60
        friday_league.lock_offset_minutes = 60
        await session.commit()
        await session.refresh(friday_league)

        saturday_round = await _open_sample_gameweek(session, fake, saturday_league)
        friday_slate = await fake.fetch_slate(
            window_for(friday_league), SAMPLE_SATURDAY - timedelta(days=1)
        )
        friday_round = await sync_slate(session, friday_league, friday_slate)
        friday_round.status = GameweekStatus.open
        friday_round.locks_at_utc = _now() + timedelta(hours=2)
        await session.commit()
        await session.refresh(friday_round)

    # Each league's slate is its own round, on its own date.
    for player, league, expected in (
        (alice, saturday_league, saturday_round),
        (bob, friday_league, friday_round),
    ):
        slate = (
            await client.get(
                f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(player)
            )
        ).json()
        assert slate["gameweek_id"] == str(expected.id)
        assert slate["starts_on"] == expected.starts_on.isoformat()

    assert saturday_round.starts_on != friday_round.starts_on, "different windows, different dates"

    # The Friday league's lock is an hour before Friday 19:00, not 14:30 Saturday.
    assert friday_round.id != saturday_round.id


async def test_a_league_cannot_read_another_leagues_round(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Knowing a round's id must not be enough to read it.

    Before Batch 14 ``gameweek_by_id`` was a bare primary-key lookup, so any member
    of any league could read any round by id. Rounds are league-owned now and the
    lookup is scoped, so someone else's round is indistinguishable from one that
    does not exist.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), theirs = await _seed_league(session, ["alice"])
        (mallory,), mine = await _seed_league(session, ["mallory"])
        their_round = await _open_sample_gameweek(session, fake, theirs)
        await _open_sample_gameweek(session, fake, await session.get(League, mine.id))

    for path in ("gameweek/current", "coupon"):
        peek = await client.get(
            f"/api/v1/leagues/{mine.slug}/{path}?gameweek_id={their_round.id}",
            headers=_auth(mallory),
        )
        assert peek.status_code == 404, f"{path} leaked another league's round: {peek.text}"

    # And the owner can still read it perfectly well.
    ok = await client.get(
        f"/api/v1/leagues/{theirs.slug}/gameweek/current?gameweek_id={their_round.id}",
        headers=_auth(alice),
    )
    assert ok.status_code == 200


async def test_a_fixture_off_this_leagues_card_cannot_be_picked(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Pooled fixtures are shared, so membership of a card has to be checked."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), playing = await _seed_league(session, ["alice"])
        (bob,), not_playing = await _seed_league(session, ["bob"])
        gameweek = await _open_sample_gameweek(session, fake, playing)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    # Bob's league has no rounds at all, so the pooled fixture is not on his card.
    refused = await _submit(client, not_playing.slug, bob, epl, "MATCH_ODDS", "HOME")
    assert refused.status_code == 404
    assert refused.json()["detail"] == "Fixture is not on this league's slate"

    # Alice's league is playing it.
    assert (
        await _submit(client, playing.slug, alice, epl, "MATCH_ODDS", "HOME")
    ).status_code == 201


async def test_reminders_reach_every_league_not_just_one(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """``members_missing_picks`` had no league filter before Batch 14.

    A reminder for one round went to every member of every league in the database.
    """
    _, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), first = await _seed_league(session, ["alice"])
        (bob,), second = await _seed_league(session, ["bob"])
        first_round = await _open_sample_gameweek(session, fake, first)
        await _open_sample_gameweek(session, fake, await session.get(League, second.id))

        recipients = await members_missing_picks(session, first_round)

    names = {r.player_id for r in recipients}
    assert str(alice.id) in names
    assert str(bob.id) not in names, "another league's members must not be reminded"
