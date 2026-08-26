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

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League, PickScope
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.match import Match
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.models.team import Team
from src.services import coupon as coupon_svc
from src.services import scoring
from src.services.betfair import (
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_ID,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import fixtures_for, members_missing_picks, sync_slate, window_for
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import Competition, FixtureOdds, OddsProviderAPIError
from src.services.team_matching import normalise_name

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

# Canned sample winners: Arsenal (home, EPL) and Forfar (home, SL2).
SAMPLE_ARSENAL_SEL = 1001
SAMPLE_FORFAR_SEL = 2001

# The canned non-British competition. `fetch_slate` drops it on the country rule, so no
# round ever pools it and it can only reach a surface from the provider's own catalogue.
SAMPLE_LA_LIGA_ID = "99999"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _auth(profile: Profile) -> dict[str, str]:
    token = create_access_token(profile.id, profile.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client_and_fake() -> AsyncIterator[tuple[AsyncClient, FakeBetfair]]:
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    app.dependency_overrides[get_optional_odds_provider] = lambda: fake
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


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

    The lock moves with the date, because a round a week further out locks a week later.
    That used to be flat, which no test could see while "the current round" meant the
    newest ``starts_on``; since Batch 35 it means the open round locking soonest, and a
    league whose rounds all lock at the same instant is not a league.
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
    gameweek.locks_at_utc = _now() + timedelta(hours=2, weeks=weeks_later)
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


# ── Batch 27: the other end of the claim period ──────────────────────────────


async def test_a_round_that_has_not_opened_rejects_submit(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Refused as *not yet*, not as over — the two ask opposite things of a member."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["earlybird"])
        gameweek, fixture = await _round_with_one_fixture(
            session,
            league,
            date(2026, 8, 29),
            locks_at=_now() + timedelta(hours=2),
            event_id=SAMPLE_EPL_EVENT_ID,
            home="Arsenal",
            away="Chelsea",
            competition="English Premier League",
            competition_id="10932509",
        )
        gameweek.status = GameweekStatus.scheduled
        gameweek.picks_open_at_utc = _now() + timedelta(hours=1)
        await session.commit()
        fixture_id = str(fixture.id)

    r = await _submit(client, league.slug, alice, fixture_id, "MATCH_ODDS", "HOME")
    assert r.status_code == 409 and r.json()["detail"] == "PICKS_NOT_OPEN"


async def test_a_scheduled_round_accepts_a_pick_once_its_time_has_passed(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The stored instant is the gate, not the label the hourly job keeps up with."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["punctual"])
        gameweek, fixture = await _round_with_one_fixture(
            session,
            league,
            date(2026, 9, 5),
            locks_at=_now() + timedelta(hours=2),
            event_id=SAMPLE_EPL_EVENT_ID,
            home="Arsenal",
            away="Chelsea",
            competition="English Premier League",
            competition_id="10932509",
        )
        # Still labelled ``scheduled`` because the open job has not run yet.
        gameweek.status = GameweekStatus.scheduled
        gameweek.picks_open_at_utc = _now() - timedelta(minutes=1)
        await session.commit()
        fixture_id = str(fixture.id)

    r = await _submit(client, league.slug, alice, fixture_id, "MATCH_ODDS", "HOME")
    assert r.status_code == 201, r.text


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
    assert by_name["alice"]["competition"] == "English Premier League"
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
    # A held selection says when it was claimed (Batch 38); a free one does not.
    held = [s for s in fixture_by_id[epl]["selections"] if s["taken_by_player_id"]]
    assert held, "expected at least one claimed selection on the EPL fixture"
    assert all(s["taken_at"] for s in held)
    free = [s for s in fixture_by_id[epl]["selections"] if not s["taken_by_player_id"]]
    assert all(s["taken_at"] is None for s in free)
    # The untouched fixture carries no marker at all.
    assert fixture_by_id[sl2]["competition_id"] == SAMPLE_SL2_ID
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

    # Alice sees the game as hers at the fixture level, but only the selection she
    # actually holds is marked `mine`, and the rest of the game stays open to her.
    # She owns it, so moving between its markets is a re-pick the API allows
    # (`test_fixture_scope_still_lets_a_member_repick_within_their_own_game`) — and a
    # client greys out whatever is already taken or already `mine`, so blanking the
    # whole game would lock the one member entitled to switch out of switching.
    alice_slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice))
    ).json()
    alice_claimed = {f["fixture_id"]: f for f in alice_slate["fixtures"]}[epl]
    assert alice_claimed["mine"] is True
    mine = [s for s in alice_claimed["selections"] if s["mine"]]
    assert [(s["market"], s["outcome"]) for s in mine] == [("MATCH_ODDS", "HOME")]
    assert all(
        s["taken_by_player_id"] is None for s in alice_claimed["selections"] if not s["mine"]
    )


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


async def test_fixture_scope_names_the_other_holder_on_a_game_the_caller_also_holds(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A league switched to the fixture rule keeps picks written under the old one.

    Both members legitimately hold a selection on the same game, so the slate has to
    pick which of them a selection reports — and reporting the *caller* would show the
    game as free to the one member `_claim_conflict` is about to refuse.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    # Written under the selection rule, which permits both, then the league switches.
    assert (await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    assert (await _submit(client, league.slug, bob, epl, "MATCH_ODDS", "DRAW")).status_code == 201
    await _set_pick_scope(league, PickScope.fixture)

    slate = (
        await client.get(f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice))
    ).json()
    claimed = {f["fixture_id"]: f for f in slate["fixtures"]}[epl]
    # Bob holds it too, so every selection Alice does not already own reads as his.
    for selection in claimed["selections"]:
        if (selection["market"], selection["outcome"]) == ("MATCH_ODDS", "HOME"):
            assert selection["mine"] is True
        else:
            assert selection["taken_by_player_id"] == str(bob.id)
            assert selection["mine"] is False


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
    """Both reads default to the round in play and both accept an explicit gameweek.

    "In play" is Batch 65's meaning of it: the round whose picks are locked and whose
    results are not in yet. Members reported the leagues jumping "straight to the next
    week as soon as the picks are locked", and this is that complaint at the two surfaces
    it was seen on. The week turns when the round settles, not when it shuts.
    """
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
        # The older round is over — which is what makes it the one a member browses
        # *back* to. Re-fetch: the league instance above belongs to a closed session.
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == older.id))
        ).scalar_one()
        stored.status = GameweekStatus.locked
        stored.locks_at_utc = _now() - timedelta(hours=1)
        newer = await _open_sample_gameweek(
            session, fake, await session.get(League, league.id), weeks_later=1
        )

    async def default_slate() -> dict[str, Any]:
        return (
            await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(alice))
        ).json()

    async def default_coupon() -> dict[str, Any]:
        return (await client.get(f"/api/v1/leagues/{slug}/coupon", headers=_auth(alice))).json()

    # Default while the older round is being played: that round, with Alice's leg on it —
    # even though next week's card already exists and is already taking picks.
    playing = await default_slate()
    assert playing["gameweek_id"] == str(older.id)
    assert playing["members_missing_picks"] == 0
    assert (await default_coupon())["leg_count"] == 1

    # Named: next week's round, browsed forward to from the one in play.
    ahead = (
        await client.get(
            f"/api/v1/leagues/{slug}/gameweek/current?gameweek_id={newer.id}",
            headers=_auth(alice),
        )
    ).json()
    assert ahead["gameweek_id"] == str(newer.id)
    assert ahead["members_missing_picks"] == 1

    # The results land. Only now does the week turn.
    async with AsyncSessionLocal() as session:
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == older.id))
        ).scalar_one()
        stored.status = GameweekStatus.settled
        stored.settled_at = _now()
        await session.commit()

    assert (await default_slate())["gameweek_id"] == str(newer.id)
    assert (await default_slate())["members_missing_picks"] == 1

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

    settled_default = await default_coupon()
    assert settled_default["gameweek_id"] == str(newer.id)
    assert settled_default["leg_count"] == 0


async def test_results_lists_only_settled_gameweeks_with_winner_and_outcome(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Batch 25 — a settled week's headline: who won, their points, the coupon outcome."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        older = await _open_sample_gameweek(session, fake, league)
        older_fixtures = await _fixture_ids(session, older.id)
    slug = league.slug

    # Alice takes Arsenal (home, wins); Bob takes Brechin (away, loses to Forfar at home).
    assert (
        await _submit(
            client, slug, alice, older_fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME"
        )
    ).status_code == 201
    assert (
        await _submit(client, slug, bob, older_fixtures[SAMPLE_SL2_EVENT_ID], "MATCH_ODDS", "AWAY")
    ).status_code == 201

    async with AsyncSessionLocal() as session:
        # A second, still-open round — must not appear in the results list.
        newer = await _open_sample_gameweek(
            session, fake, await session.get(League, league.id), weeks_later=1
        )

        fake.close_markets(
            {
                SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
                SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
            }
        )
        settlements = await fake.settle([SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID])
        gameweek = (
            await session.execute(select(Gameweek).where(Gameweek.id == older.id))
        ).scalar_one()
        await scoring.settle_gameweek(session, gameweek, settlements)
        await session.commit()

    results = (await client.get(f"/api/v1/leagues/{slug}/results", headers=_auth(alice))).json()

    assert [row["gameweek_id"] for row in results] == [str(older.id)]
    assert str(newer.id) not in {row["gameweek_id"] for row in results}
    row = results[0]
    assert row["winner_names"] == [alice.display_name]
    assert row["winner_points"] == 19  # round(1.9 × 10)
    assert row["leg_count"] == 2
    assert row["combined_odds"] == 5.89  # 1.9 × 3.1
    assert row["all_won"] is False  # Bob's Brechin lost
    # Batch 79: `all_won` alone reads the same for five of six and none of six.
    assert row["picks_won"] == 1, "Alice's Arsenal landed and Bob's Brechin did not"


# ── Batch 67: what a round looks like once it has been played ──────────────────
#
# `CombinedAccaView` showed a won/lost badge per leg and an "All legs won" line, which is
# the outcome and not the *result*. The scoreline is not on `fixtures` — the odds provider
# settles in market and outcome terms and keeps no goals — so it is reached through a
# name-based join to `matches`, and a wrong join would print a false scoreline against a
# real member's pick. These walk that through the endpoint the screen actually calls.


async def _record_played_match(
    home: str, away: str, competition_id: str, kickoff: datetime, score: tuple[int, int]
) -> None:
    """A finished match on the football-data side, as the sweep would have written it.

    Existing matches in the same competition and window are cleared first, and that is
    load-bearing rather than tidiness: this module commits, the fixture pool is shared by
    ``provider_event_id``, so every test here works against the *same* Arsenal v Chelsea
    row. Without the clear, the third test to seed a result finds three candidates on one
    day and `scorelines_for` correctly refuses to guess between them — the ambiguity guard
    firing on an artefact of test order rather than on anything real.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Match).where(
                Match.competition_id == competition_id,
                Match.kickoff_utc >= kickoff - timedelta(days=7),
                Match.kickoff_utc <= kickoff + timedelta(days=7),
            )
        )
        teams = []
        for name in (home, away):
            team = Team(
                provider_team_id=f"t-{uuid.uuid4().hex[:10]}",
                name=name,
                normalised_name=normalise_name(name),
                competition_id=competition_id,
            )
            session.add(team)
            teams.append(team)
        await session.flush()
        session.add(
            Match(
                provider_match_id=f"m-{uuid.uuid4().hex[:10]}",
                competition_id=competition_id,
                competition="Sampled",
                season=2026,
                kickoff_utc=kickoff,
                home_team_id=teams[0].id,
                away_team_id=teams[1].id,
                home_goals=score[0],
                away_goals=score[1],
                finished=True,
            )
        )
        await session.commit()


async def _settle_sample_round(fake: FakeBetfair, gameweek_id: uuid.UUID) -> None:
    """Arsenal and Forfar win, and the round settles — the canned result the suite uses."""
    async with AsyncSessionLocal() as session:
        fake.close_markets(
            {
                SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
                SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
            }
        )
        settlements = await fake.settle([SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID])
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == gameweek_id))
        ).scalar_one()
        await scoring.settle_gameweek(session, stored, settlements)
        await session.commit()


async def test_a_settled_coupon_carries_each_legs_scoreline_and_points(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The result, next to the outcome, for the legs whose match could be resolved.

    Both legs of the sample card are settled; only one of them has a played match on the
    football side. The other is the failing-open case in the same response: its outcome
    renders, its scoreline does not, and nothing errors.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
        epl_fixture = (
            (
                await session.execute(
                    select(Fixture).where(Fixture.provider_event_id == SAMPLE_EPL_EVENT_ID)
                )
            )
            .scalars()
            .first()
        )
        assert epl_fixture is not None
        kickoff, competition_id = epl_fixture.kickoff_utc, epl_fixture.competition_id
    slug = league.slug

    assert (
        await _submit(client, slug, alice, fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME")
    ).status_code == 201
    assert (
        await _submit(client, slug, bob, fixtures[SAMPLE_SL2_EVENT_ID], "MATCH_ODDS", "AWAY")
    ).status_code == 201

    # Only the Arsenal game is on the football side. The Scottish one is the competition
    # the source does not carry — the every-week case for the non-league tiers.
    await _record_played_match("Arsenal", "Chelsea", competition_id, kickoff, (2, 1))
    await _settle_sample_round(fake, gameweek.id)

    coupon = (await client.get(f"/api/v1/leagues/{slug}/coupon", headers=_auth(alice))).json()

    assert coupon["status"] == "settled"
    by_fixture = {leg["fixture_id"]: leg for leg in coupon["legs"]}
    won = by_fixture[fixtures[SAMPLE_EPL_EVENT_ID]]
    assert (won["home_goals"], won["away_goals"]) == (2, 1)
    assert won["status"] == "won"
    assert won["points_awarded"] == 19  # round(1.9 × 10)

    unresolved = by_fixture[fixtures[SAMPLE_SL2_EVENT_ID]]
    assert unresolved["home_goals"] is None, "no match to resolve means no score, not nil-nil"
    assert unresolved["away_goals"] is None
    assert unresolved["status"] == "lost", "the outcome still renders"
    assert unresolved["points_awarded"] == 0


async def test_an_unsettled_round_carries_no_scoreline(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A partial score beside a pending pick would read as final. Live scores are Batch 72."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
        epl_fixture = (
            (
                await session.execute(
                    select(Fixture).where(Fixture.provider_event_id == SAMPLE_EPL_EVENT_ID)
                )
            )
            .scalars()
            .first()
        )
        assert epl_fixture is not None
        kickoff, competition_id = epl_fixture.kickoff_utc, epl_fixture.competition_id
    slug = league.slug

    assert (
        await _submit(client, slug, alice, fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME")
    ).status_code == 201
    await _record_played_match("Arsenal", "Chelsea", competition_id, kickoff, (2, 1))

    coupon = (await client.get(f"/api/v1/leagues/{slug}/coupon", headers=_auth(alice))).json()

    assert coupon["status"] != "settled"
    assert all(leg["home_goals"] is None for leg in coupon["legs"])


async def test_scrolling_back_to_an_older_settled_round_shows_its_result(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Not only the most recent one — the owner's seventh point is browsing history.

    The round is named explicitly while a *newer* one is current, which is the state a
    member is in when they scroll back through the season.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        older = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, older.id)
        epl_fixture = (
            (
                await session.execute(
                    select(Fixture).where(Fixture.provider_event_id == SAMPLE_EPL_EVENT_ID)
                )
            )
            .scalars()
            .first()
        )
        assert epl_fixture is not None
        kickoff, competition_id = epl_fixture.kickoff_utc, epl_fixture.competition_id
    slug = league.slug

    assert (
        await _submit(client, slug, alice, fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME")
    ).status_code == 201
    await _record_played_match("Arsenal", "Chelsea", competition_id, kickoff, (3, 0))
    await _settle_sample_round(fake, older.id)

    async with AsyncSessionLocal() as session:
        newer = await _open_sample_gameweek(
            session, fake, await session.get(League, league.id), weeks_later=1
        )
    current = (await client.get(f"/api/v1/leagues/{slug}/coupon", headers=_auth(alice))).json()
    assert current["gameweek_id"] == str(newer.id), "the league has moved on"

    browsed = (
        await client.get(
            f"/api/v1/leagues/{slug}/coupon?gameweek_id={older.id}", headers=_auth(alice)
        )
    ).json()

    assert browsed["gameweek_id"] == str(older.id)
    leg = browsed["legs"][0]
    assert (leg["home_goals"], leg["away_goals"]) == (3, 0)


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


# ── Batch 15: league admin configuration ─────────────────────────────────────


async def _make_admin(league: League, player: Profile) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == player.id,
            )
            .values(role=LeagueMemberRole.admin)
        )
        await session.commit()


async def test_create_league_carries_window_markets_and_competitions(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Everything an admin configures is settable at creation, and echoed back."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (creator,), _throwaway = await _seed_league(session, ["founder"])

    body = {
        "name": f"Config Crew {uuid.uuid4().hex[:6]}",
        "offered_markets": ["MATCH_ODDS"],
        "competitions": [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}],
        "slate_start_weekday": 4,
        "slate_start_minute": 19 * 60,
        "slate_end_weekday": 0,
        "slate_end_minute": 22 * 60,
        "lock_offset_minutes": 60,
    }
    r = await client.post("/api/v1/leagues", json=body, headers=_auth(creator))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["offered_markets"] == ["MATCH_ODDS"]
    assert data["competitions"] == [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    assert data["slate_window"] == {
        "start_weekday": 4,
        "start_minute": 1140,
        "end_weekday": 0,
        "end_minute": 1320,
        "lock_offset_minutes": 60,
        # Batch 27: unset unless asked for — "claimable as soon as it is published".
        "pick_open_offset_minutes": None,
    }

    # A league created with no config takes the old defaults: all UK, both markets, Sat 15:00.
    plain = await client.post(
        "/api/v1/leagues",
        json={"name": f"Plain {uuid.uuid4().hex[:6]}"},
        headers=_auth(creator),
    )
    pd = plain.json()
    assert pd["competitions"] is None
    assert pd["offered_markets"] == ["MATCH_ODDS", "BOTH_TEAMS_TO_SCORE"]
    assert pd["slate_window"]["start_weekday"] == 5 and pd["slate_window"]["start_minute"] == 900


async def test_admin_edits_window_markets_and_competitions(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The same fields are editable after creation via PATCH, gated by LeagueAdminDep."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["boss"])
    await _make_admin(league, alice)
    slug = league.slug

    r = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={
            "slate_start_weekday": 4,
            "lock_offset_minutes": 120,
            "offered_markets": ["BOTH_TEAMS_TO_SCORE"],
            "competitions": [{"slug": SAMPLE_SL2_ID, "name": "Scottish League Two"}],
        },
        headers=_auth(alice),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slate_window"]["start_weekday"] == 4
    assert data["slate_window"]["lock_offset_minutes"] == 120
    assert data["offered_markets"] == ["BOTH_TEAMS_TO_SCORE"]
    assert data["competitions"] == [{"slug": SAMPLE_SL2_ID, "name": "Scottish League Two"}]

    # Passing competitions: null returns to the all-UK group (distinct from "unchanged").
    back = await client.patch(
        f"/api/v1/leagues/{slug}", json={"competitions": None}, headers=_auth(alice)
    )
    assert back.status_code == 200 and back.json()["competitions"] is None
    # Omitting competitions leaves the all-UK setting untouched.
    untouched = await client.patch(
        f"/api/v1/leagues/{slug}", json={"lock_offset_minutes": 45}, headers=_auth(alice)
    )
    assert untouched.json()["competitions"] is None


async def test_admin_sets_and_clears_the_pick_open_time(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Batch 27's control, alongside the rest of the window settings."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["timekeeper"])
    await _make_admin(league, alice)
    slug = league.slug

    # A new league announces no opening — the pre-batch rule.
    before = await client.get(f"/api/v1/leagues/{slug}", headers=_auth(alice))
    assert before.json()["slate_window"]["pick_open_offset_minutes"] is None

    a_week = 7 * 24 * 60
    r = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={"pick_open_offset_minutes": a_week},
        headers=_auth(alice),
    )
    assert r.status_code == 200, r.text
    assert r.json()["slate_window"]["pick_open_offset_minutes"] == a_week

    # Omitting it leaves the announcement alone…
    kept = await client.patch(
        f"/api/v1/leagues/{slug}", json={"lock_offset_minutes": 45}, headers=_auth(alice)
    )
    assert kept.json()["slate_window"]["pick_open_offset_minutes"] == a_week
    # …and null switches it back off, which is why null cannot mean "unchanged" here.
    cleared = await client.patch(
        f"/api/v1/leagues/{slug}", json={"pick_open_offset_minutes": None}, headers=_auth(alice)
    )
    assert cleared.json()["slate_window"]["pick_open_offset_minutes"] is None


async def test_a_claim_period_cannot_close_before_it_opens(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Refused as a 422 in both directions, rather than reaching the database's check."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["backwards"])
    await _make_admin(league, alice)
    slug = league.slug

    # Picks opening *after* they lock — both offsets count back from the same anchor.
    r = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={"lock_offset_minutes": 60, "pick_open_offset_minutes": 30},
        headers=_auth(alice),
    )
    assert r.status_code == 422, r.text

    # And a lock moved on its own must still clear an offset it never mentions.
    ok = await client.patch(
        f"/api/v1/leagues/{slug}", json={"pick_open_offset_minutes": 120}, headers=_auth(alice)
    )
    assert ok.status_code == 200, ok.text
    late_lock = await client.patch(
        f"/api/v1/leagues/{slug}", json={"lock_offset_minutes": 180}, headers=_auth(alice)
    )
    assert late_lock.status_code == 422, late_lock.text

    # Creation is guarded the same way.
    bad = await client.post(
        "/api/v1/leagues",
        json={
            "name": f"Backwards {uuid.uuid4().hex[:6]}",
            "lock_offset_minutes": 60,
            "pick_open_offset_minutes": 30,
        },
        headers=_auth(alice),
    )
    assert bad.status_code == 422, bad.text


async def test_offered_markets_hide_from_the_slate_and_block_submit(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A market the league does not offer is neither shown nor accepted."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["mo-only"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
        # Restrict this league to Match Odds only.
        stored = await session.get(League, league.id)
        assert stored is not None
        stored.offered_markets = [PickMarket.MATCH_ODDS]
        await session.commit()
    epl = fixtures[SAMPLE_EPL_EVENT_ID]
    slug = league.slug

    slate = (
        await client.get(f"/api/v1/leagues/{slug}/gameweek/current", headers=_auth(alice))
    ).json()
    epl_fixture = {f["fixture_id"]: f for f in slate["fixtures"]}[epl]
    assert {s["market"] for s in epl_fixture["selections"]} == {"MATCH_ODDS"}, "BTTS must be hidden"

    # Submitting the hidden market is refused even posted directly.
    refused = await _submit(client, slug, alice, epl, "BOTH_TEAMS_TO_SCORE", "YES")
    assert refused.status_code == 422 and refused.json()["detail"] == "MARKET_NOT_OFFERED"
    # The offered market is still pickable.
    assert (await _submit(client, slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201


async def test_competition_catalogue_comes_from_the_provider_not_from_fixtures(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Batch 21: the picker is populated without this league having run a slate.

    `fixtures` is a pool shared by every league, so "empty" is not assertable in this
    committed database. The discriminator is `SAMPLE_LA_LIGA_ID` instead: `fetch_slate`
    drops it on the country rule, so no round can ever pool it and its presence in the
    catalogue can only mean the provider was asked.
    """
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["cataloguer"])
        rows = await session.execute(select(Fixture.competition_id).distinct())
        pooled = set(rows.scalars().all())
    await _make_admin(league, alice)

    cat = (
        await client.get(f"/api/v1/leagues/{league.slug}/competitions", headers=_auth(alice))
    ).json()
    assert cat["all_uk"] is True
    assert cat["selected"] == []
    by_slug = {c["slug"]: c["name"] for c in cat["available"]}
    assert by_slug.get(SAMPLE_EPL_ID) == "English Premier League"
    assert by_slug.get(SAMPLE_SL2_ID) == "Scottish League Two"
    assert SAMPLE_LA_LIGA_ID not in pooled
    assert by_slug.get(SAMPLE_LA_LIGA_ID) == "Spanish La Liga"


async def test_competition_catalogue_falls_back_to_pooled_when_the_provider_is_down(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """An upstream failure degrades to the old catalogue rather than locking the admin out.

    The picker is also how a league *un*-narrows itself, so a 503 here would leave an
    admin unable to change a selection they can no longer see.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["degrader"])
        # Pool the sample fixtures into the shared table via this league's round.
        await _open_sample_gameweek(session, fake, league)
    await _make_admin(league, alice)

    app.dependency_overrides[get_odds_provider] = lambda: _BrokenCatalogue()
    try:
        r = await client.get(f"/api/v1/leagues/{league.slug}/competitions", headers=_auth(alice))
    finally:
        app.dependency_overrides[get_odds_provider] = lambda: fake

    assert r.status_code == 200
    by_slug = {c["slug"]: c["name"] for c in r.json()["available"]}
    assert by_slug.get(SAMPLE_EPL_ID) == "English Premier League"
    assert by_slug.get(SAMPLE_SL2_ID) == "Scottish League Two"


class _BrokenCatalogue(FakeBetfair):
    """The canned provider with an unreachable competition catalogue."""

    async def fetch_competitions(self, **_: object) -> list[Competition]:
        raise OddsProviderAPIError("upstream unreachable")


async def test_ad_hoc_gameweek_creates_a_filtered_round_and_is_idempotent(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """An admin can create a round on an arbitrary date; the competition filter applies."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["adhoc"])
    await _make_admin(league, alice)
    slug = league.slug

    # Narrow to the EPL before creating the round, so the filter is exercised on a fresh card.
    await client.patch(
        f"/api/v1/leagues/{slug}",
        json={"competitions": [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]},
        headers=_auth(alice),
    )

    r = await client.post(
        f"/api/v1/leagues/{slug}/gameweeks",
        json={"starts_on": SAMPLE_SATURDAY.isoformat()},
        headers=_auth(alice),
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["created"] is True
    assert created["fixture_count"] == 1, "only the EPL fixture, not the Scottish one"
    gwid = created["gameweek_id"]

    # The single fixture on the round is the EPL one.
    slate = (
        await client.get(
            f"/api/v1/leagues/{slug}/gameweek/current?gameweek_id={gwid}", headers=_auth(alice)
        )
    ).json()
    assert [f["home"] for f in slate["fixtures"]] == ["Arsenal"]

    # Re-posting the same date refreshes in place — same round, created=false.
    again = await client.post(
        f"/api/v1/leagues/{slug}/gameweeks",
        json={"starts_on": SAMPLE_SATURDAY.isoformat()},
        headers=_auth(alice),
    )
    assert again.status_code == 201
    assert again.json()["gameweek_id"] == gwid and again.json()["created"] is False


async def test_ad_hoc_gameweek_is_rate_limited_to_what_the_request_budget_allows(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The only provider call left in the request path, so the limit is the guard.

    An unconfigured league's call is one ``/events`` per UK competition — the cost of a
    whole discovery run — and exhausting odds-api.io's quota is silent: picks simply stay
    ``pending`` and the week never finishes. The arithmetic behind the number is asserted
    in ``tests/test_request_budget.py``; this pins that it is actually enforced.
    """
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["limited"])
    await _make_admin(league, alice)

    async def create() -> Response:
        return await client.post(
            f"/api/v1/leagues/{league.slug}/gameweeks",
            json={"starts_on": SAMPLE_SATURDAY.isoformat()},
            headers=_auth(alice),
        )

    assert (await create()).status_code == 201
    assert (await create()).status_code == 201, "re-posting the same date is still allowed"
    assert (await create()).status_code == 429


async def test_ad_hoc_gameweek_with_no_fixtures_is_a_422(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A date the provider prices nothing for is a clear error, not an empty round."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["barren"])
    await _make_admin(league, alice)

    r = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks",
        json={"starts_on": date(2030, 1, 5).isoformat()},
        headers=_auth(alice),
    )
    assert r.status_code == 422 and r.json()["detail"] == "NO_FIXTURES"


async def test_config_surfaces_are_gated_to_admins(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A plain member cannot edit config, read the catalogue, or create a round."""
    client, _ = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["admin", "member"])
    await _make_admin(league, alice)  # bob stays a plain member
    slug = league.slug

    assert (
        await client.patch(
            f"/api/v1/leagues/{slug}", json={"lock_offset_minutes": 45}, headers=_auth(bob)
        )
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/leagues/{slug}/competitions", headers=_auth(bob))
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/leagues/{slug}/gameweeks",
            json={"starts_on": "2027-12-26"},
            headers=_auth(bob),
        )
    ).status_code == 403
    # The admin is allowed the catalogue.
    assert (
        await client.get(f"/api/v1/leagues/{slug}/competitions", headers=_auth(alice))
    ).status_code == 200


# ── Batch 26: the cross-league summary behind home and the career profile ────


async def _also_in(session: AsyncSession, name: str, members: list[Profile]) -> League:
    """A further league the given players belong to, created by the first of them."""
    league = League(slug=f"cpn-{uuid.uuid4().hex[:8]}", name=name, created_by=members[0].id)
    session.add(league)
    await session.flush()
    for player in members:
        session.add(LeagueMembership(league_id=league.id, player_id=player.id))
    await session.commit()
    await session.refresh(league)
    return league


async def _settle_all(gameweek: Gameweek, fake: FakeBetfair) -> None:
    """Settle a round against the canned EPL result (Arsenal win)."""
    async with AsyncSessionLocal() as session:
        fake.close_markets({SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL})
        settlements = await fake.settle([SAMPLE_EPL_EVENT_ID])
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == gameweek.id))
        ).scalar_one()
        await scoring.settle_gameweek(session, stored, settlements)
        await session.commit()


async def test_standings_by_league_keeps_leagues_apart(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The batched table must agree with the per-league one and never pool picks."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), first = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, first)
        fixtures = await _fixture_ids(session, gameweek.id)
        second = await _also_in(session, "Second", [alice, bob])
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    assert (await _submit(client, first.slug, alice, epl, "MATCH_ODDS", "HOME")).status_code == 201
    await _settle_all(gameweek, fake)

    async with AsyncSessionLocal() as session:
        # Batch 80: `standings` asks for the form run, so the batched call has to be asked
        # for the same thing before the two can be compared. Everything else about them
        # must still be identical — there is one ranking rule in the codebase.
        tables = await scoring.standings_by_league(session, [first.id, second.id], with_form=True)
        assert tables[first.id] == await scoring.standings(session, first.id)
        assert tables[second.id] == await scoring.standings(session, second.id)

        # And the default really is off, which is what keeps `routers/me.py` from paying
        # for a run it never renders — twice per request, since it differences two tables.
        lean = await scoring.standings_by_league(session, [first.id, second.id])
        assert all(row.recent_form == [] for row in lean[first.id])

    in_first = next(s for s in tables[first.id] if s.player_id == str(alice.id))
    in_second = next(s for s in tables[second.id] if s.player_id == str(alice.id))
    assert in_first.total_points == 19  # round(1.90 × 10)
    assert in_second.total_points == 0, "the first league's picks must not leak into the second"


async def test_cross_league_summary_totals_points_and_breaks_them_down(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Points and win rate sum across leagues; each league keeps its own rank."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob, carol), first = await _seed_league(session, ["alice", "bob", "carol"])
        first_gw = await _open_sample_gameweek(session, fake, first)
        first_fixtures = await _fixture_ids(session, first_gw.id)
        second = await _also_in(session, "Second", [alice, bob, carol])
        second_gw = await _open_sample_gameweek(session, fake, second)
        second_fixtures = await _fixture_ids(session, second_gw.id)

    # Alice wins in both leagues; the same fixture is claimable in each because
    # uniqueness is per league.
    for slug, fixtures in ((first.slug, first_fixtures), (second.slug, second_fixtures)):
        submitted = await _submit(
            client, slug, alice, fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME"
        )
        assert submitted.status_code == 201
    await _settle_all(first_gw, fake)
    await _settle_all(second_gw, fake)

    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()

    assert summary["leagues_count"] == 2
    assert summary["total_points"] == 38, "19 in each league — the same scale, so it sums"
    assert summary["picks_played"] == 2
    assert summary["picks_won"] == 2
    assert summary["win_rate_pct"] == 100

    by_slug = {entry["slug"]: entry for entry in summary["per_league"]}
    assert set(by_slug) == {first.slug, second.slug}
    for slug in (first.slug, second.slug):
        assert by_slug[slug]["total_points"] == 19
        assert by_slug[slug]["rank"] == 1
        assert by_slug[slug]["member_count"] == 3
    assert by_slug[second.slug]["name"] == "Second"

    # Ordered by league name, as the breakdown is rendered.
    assert [entry["name"] for entry in summary["per_league"]] == sorted(
        entry["name"] for entry in summary["per_league"]
    )


async def test_avg_rank_skips_leagues_too_small_to_rank_against(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A two-person league is rank 1 by default and must not flatter the average."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob, carol), big = await _seed_league(session, ["alice", "bob", "carol"])
        gameweek = await _open_sample_gameweek(session, fake, big)
        fixtures = await _fixture_ids(session, gameweek.id)
        tiny = await _also_in(session, "Tiny", [alice, bob])
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    # Bob scores in the big league, so Alice sits second there.
    assert (await _submit(client, big.slug, bob, epl, "MATCH_ODDS", "HOME")).status_code == 201
    await _settle_all(gameweek, fake)

    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()

    by_slug = {entry["slug"]: entry for entry in summary["per_league"]}
    assert by_slug[big.slug]["rank"] == 2
    assert by_slug[tiny.slug]["rank"] == 1, "the small league still reports its own rank"
    assert by_slug[tiny.slug]["member_count"] == 2

    assert summary["avg_rank"] == 2.0, "1.5 would mean the two-person league counted"
    assert summary["avg_rank_leagues"] == 1


async def test_cross_league_summary_carries_each_leagues_current_round(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Home's card needs this week's pick and coupon per league, or says there is none."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), playing = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, playing)
        fixtures = await _fixture_ids(session, gameweek.id)
        idle = await _also_in(session, "Idle", [alice, bob])
    epl, sl2 = fixtures[SAMPLE_EPL_EVENT_ID], fixtures[SAMPLE_SL2_EVENT_ID]

    assert (
        await _submit(client, playing.slug, alice, epl, "MATCH_ODDS", "HOME")
    ).status_code == 201
    assert (await _submit(client, playing.slug, bob, sl2, "MATCH_ODDS", "HOME")).status_code == 201

    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()
    by_slug = {entry["slug"]: entry for entry in summary["per_league"]}

    current = by_slug[playing.slug]["current_round"]
    assert current["gameweek_id"] == str(gameweek.id)
    assert current["status"] == "open"
    assert current["leg_count"] == 2, "the whole league's acca, not just the caller's leg"
    assert current["combined_odds"] == 4.56  # 1.9 × 2.4
    assert current["my_pick"]["home"] == "Arsenal"
    assert current["my_pick"]["odds"] == 1.9
    assert current["my_pick"]["status"] == "pending"

    # A league with no rounds yet has nothing to show for the week.
    assert by_slug[idle.slug]["current_round"] is None

    # Bob has not picked in the round, so his card must show the gap rather than a leg.
    bob_summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(bob))).json()
    bob_round = {e["slug"]: e for e in bob_summary["per_league"]}[playing.slug]["current_round"]
    assert bob_round["my_pick"]["home"] == "Forfar Athletic"
    assert bob_round["leg_count"] == 2


async def test_a_one_off_round_does_not_hijack_this_week_on_home_or_the_coupon(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Batch 35: a Boxing Day round added in August must not become "this week".

    Both surfaces are asserted in one test on purpose. Home's card and the Coupon tab
    read the current round through two different queries — a window function over every
    league in ``routers/me.py``, and ``latest_gameweek`` one league at a time — and they
    are one rule spelled twice. Home is where a disagreement shows, because a member in
    three leagues sees one card jump forward to a round that opens in December while the
    others still show Saturday.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["one-off"])
        this_week = await _open_sample_gameweek(session, fake, league)
        # The one-off: far ahead of the cadence, and locking long after this week's round.
        await _round_with_one_fixture(
            session,
            league,
            SAMPLE_SATURDAY + timedelta(weeks=20),
            locks_at=_now() + timedelta(weeks=20),
            event_id="e-boxing-day",
            home="Manchester United",
            away="Newcastle",
            competition="English Premier League",
            competition_id=SAMPLE_EPL_ID,
        )

    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()
    card = {entry["slug"]: entry for entry in summary["per_league"]}[league.slug]["current_round"]
    assert card["gameweek_id"] == str(this_week.id), "home's card follows the round to act on"

    coupon = await client.get(f"/api/v1/leagues/{league.slug}/coupon", headers=_auth(alice))
    assert coupon.json()["gameweek_id"] == str(this_week.id), "and the Coupon tab agrees"

    slate = await client.get(
        f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
    )
    assert slate.json()["gameweek_id"] == str(this_week.id), "and so does the pick screen"


async def test_cross_league_summary_shows_an_unpicked_round_and_no_leagues(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """No pick yet is `my_pick: null`; no memberships at all is an empty summary."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        await _open_sample_gameweek(session, fake, league)
        loner = Profile(
            display_name=f"loner-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("1234"),
            role=UserRole.player,
        )
        session.add(loner)
        await session.commit()
        await session.refresh(loner)

    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()
    current = summary["per_league"][0]["current_round"]
    assert current["my_pick"] is None
    assert current["leg_count"] == 0
    assert current["combined_odds"] == 1.0, "an empty acca prices at evens, not zero"
    assert summary["win_rate_pct"] is None, "an untested record is not a bad one"

    empty = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(loner))).json()
    assert empty == {
        "avg_rank": None,
        "avg_rank_leagues": 0,
        "total_points": 0,
        "picks_played": 0,
        "picks_won": 0,
        "win_rate_pct": None,
        # Batch 70's figures, at their zero. Asserted as an exact shape on purpose: a
        # field silently appearing or vanishing from this response is what the deployed
        # web app would meet in the window before `/ship-prod`.
        "picks_priced": 0,
        "cumulative_odds": 0.0,
        "average_odds": None,
        "points_per_pick": None,
        "best_return": None,
        "longshot_picks": 0,
        "favourite_picks": 0,
        "longshot_odds": 3.0,
        "leagues_count": 0,
        "per_league": [],
    }


# ── Batch 70: one aggregate, three surfaces, one answer ───────────────────────


async def test_the_leaderboard_the_profile_and_the_home_summary_agree(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """`Standing` is the single ranking rule, and this is the property that makes it worth it.

    The leaderboard, the per-league profile and the cross-league summary read the same
    aggregate on purpose, so the figures cannot disagree. Batch 70 added seven fields to
    it, which is exactly the change that could make them start disagreeing — the profile
    used to recompute win rate for itself.

    One fixture set, three endpoints, field by field.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice, bob), league = await _seed_league(session, ["alice", "bob"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    slug = league.slug

    assert (
        await _submit(client, slug, alice, fixtures[SAMPLE_EPL_EVENT_ID], "MATCH_ODDS", "HOME")
    ).status_code == 201
    assert (
        await _submit(client, slug, bob, fixtures[SAMPLE_SL2_EVENT_ID], "MATCH_ODDS", "AWAY")
    ).status_code == 201
    await _settle_sample_round(fake, gameweek.id)

    table = (await client.get(f"/api/v1/leagues/{slug}/standings", headers=_auth(alice))).json()
    row = next(entry for entry in table if entry["player_id"] == str(alice.id))
    profile = (
        await client.get(f"/api/v1/leagues/{slug}/players/{alice.id}/profile", headers=_auth(alice))
    ).json()
    summary = (await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))).json()
    card = {entry["slug"]: entry for entry in summary["per_league"]}[slug]

    shared = (
        "total_points",
        "picks_played",
        "picks_won",
        "picks_priced",
        "cumulative_odds",
        "average_odds",
        "points_per_pick",
        "best_return",
        "longshot_picks",
        "favourite_picks",
    )
    for field in shared:
        assert row[field] == profile[field] == card[field], field
    assert row["win_rate_pct"] == profile["win_rate_pct"]

    # And Alice's own numbers are the ones her single won pick implies.
    assert row["picks_played"] == 1
    assert row["picks_priced"] == 1
    assert row["cumulative_odds"] == 1.9
    assert row["average_odds"] == 1.9
    assert row["favourite_picks"] == 1, "1.90 is short of the longshot line"
    assert row["best_return"] == 19  # round(1.9 × 10)

    # A member in one league sees that league's figures as their whole record.
    assert summary["cumulative_odds"] == card["cumulative_odds"]
    assert summary["longshot_odds"] == row["longshot_odds"]


# ── Batch 48: the pick screen survives the odds provider ──────────────────────
#
# `_live_odds` used to call `fetch_odds` with no fallback, so a provider failure
# propagated and `GET /leagues/{slug}/gameweek/current` — the screen every member opens
# to make their pick — answered 500. Observed in production on 2026-08-21, the day
# before launch: `/odds/multi` returned 429, the slate 500ed, and the Football tab
# beside it kept working because it reads only the database.
#
# These drive the real request path, with the real cache wrapper in front of a provider
# that refuses, because the fallback *is* the cache.


class _BrokenOdds(FakeBetfair):
    """The canned provider with prices that raise the way a rate-limited one does.

    Only ``fetch_odds`` breaks. That is the shape of the real failure: the card is in
    the database and upstream is asked for nothing but the prices on it.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.breaking = True

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        if self.breaking:
            raise OddsProviderAPIError("odds-api.io /odds unexpected status 429")
        return await super().fetch_odds(event_ids, max_age_seconds=max_age_seconds)


def _cached(stub: _BrokenOdds) -> CachingOddsProvider:
    """The stub behind the wrapper the request path actually gets.

    Held in a closure, never a default argument: FastAPI reads an override's signature
    as request parameters, and pydantic deep-copies a default per request, which would
    hand every load its own empty cache and quietly test nothing.

    ``ttl_seconds=0`` makes every entry instantly stale, so each call attempts a refresh
    — which is the only way a failing provider is ever reached, and what the fallback has
    to survive. The entries stay behind it regardless; that is the point.
    """
    return CachingOddsProvider(stub, ttl_seconds=0.0)


async def test_the_slate_serves_the_last_known_prices_when_the_provider_refuses(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A warm cache turns a provider outage into stale prices, not a 500."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["stale"])
        await _open_sample_gameweek(session, fake, league)

    stub = _BrokenOdds.with_sample_data()
    stub.breaking = False
    cached = _cached(stub)
    app.dependency_overrides[get_odds_provider] = lambda: cached
    try:
        # One healthy load to warm the cache — this is how it happens in production too.
        healthy = await client.get(
            f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
        )
        assert healthy.status_code == 200
        assert healthy.json()["odds_degraded"] is False
        priced = {f["fixture_id"]: f["selections"] for f in healthy.json()["fixtures"]}
        assert any(priced.values()), "the warm load has prices to be remembered by"

        stub.breaking = True
        degraded = await client.get(
            f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
        )
    finally:
        app.dependency_overrides[get_odds_provider] = lambda: fake

    assert degraded.status_code == 200, "the core screen of the product stays up"
    body = degraded.json()
    assert body["odds_degraded"] is True, "and says the prices may be out of date"
    assert {f["fixture_id"]: f["selections"] for f in body["fixtures"]} == priced


async def test_the_slate_shows_the_fixtures_when_there_is_nothing_cached_either(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A cold cache degrades to a card with no prices — which beats an error page."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["cold"])
        await _open_sample_gameweek(session, fake, league)

    cached = _cached(_BrokenOdds.with_sample_data())
    app.dependency_overrides[get_odds_provider] = lambda: cached
    try:
        r = await client.get(
            f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
        )
    finally:
        app.dependency_overrides[get_odds_provider] = lambda: fake

    assert r.status_code == 200
    body = r.json()
    assert body["odds_degraded"] is True
    assert len(body["fixtures"]) == 2, "the card is in the database and still renders"
    assert all(f["selections"] == [] for f in body["fixtures"]), "with nothing to claim"


async def test_a_pick_is_refused_rather_than_frozen_at_a_price_we_could_not_confirm(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Browsing degrades; picking must not.

    The cache is warm here — a stale price is sitting right there — and the submission
    still refuses, because a winner scores ``round(odds × 10)`` from the number frozen at
    this instant. A stale price is not a degraded pick, it is a wrong score.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["loud"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    stub = _BrokenOdds.with_sample_data()
    stub.breaking = False
    cached = _cached(stub)
    app.dependency_overrides[get_odds_provider] = lambda: cached
    try:
        warm = await client.get(
            f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
        )
        assert warm.status_code == 200

        stub.breaking = True
        refused = await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")

        # And the same screen, at the same moment, still serves the card.
        slate = await client.get(
            f"/api/v1/leagues/{league.slug}/gameweek/current", headers=_auth(alice)
        )
    finally:
        app.dependency_overrides[get_odds_provider] = lambda: fake

    assert refused.status_code == 503
    assert refused.json()["detail"] == "ODDS_UNAVAILABLE"
    assert slate.status_code == 200 and slate.json()["odds_degraded"] is True

    async with AsyncSessionLocal() as session:
        picks = await session.execute(
            select(func.count()).select_from(Pick).where(Pick.gameweek_id == gameweek.id)
        )
        assert picks.scalar_one() == 0, "nothing was written at an unconfirmed price"


# ── Batch 57: a malformed id is a client error, not a 500 ────────────────────


async def test_a_malformed_fixture_id_is_a_404_not_a_500(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """It used to reach the driver and raise. Verified over HTTP: 500 before, 404 after."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        await _open_sample_gameweek(session, fake, league)

    resp = await _submit(client, league.slug, alice, "not-a-uuid", "MATCH_ODDS", "HOME")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Fixture not found"


async def test_a_well_formed_but_absent_fixture_id_still_answers_404(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The behaviour that was already right, held in place while the other was fixed."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        await _open_sample_gameweek(session, fake, league)

    resp = await _submit(client, league.slug, alice, str(uuid.uuid4()), "MATCH_ODDS", "HOME")

    assert resp.status_code == 404, resp.text


async def test_a_malformed_gameweek_id_is_a_422_not_a_500(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """Typed `uuid.UUID` now, so FastAPI refuses it before a query is built."""
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        await _open_sample_gameweek(session, fake, league)

    resp = await client.get(
        f"/api/v1/leagues/{league.slug}/gameweeks/not-a-uuid/pick",
        headers=_auth(alice),
    )

    assert resp.status_code == 422, resp.text


# ── Batch 57: the deadline is re-checked after the provider call ─────────────


async def test_a_lock_that_passes_during_the_odds_fetch_refuses_the_pick(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The window between clearing the deadline and committing was a real one.

    `_snapshot_selection` leaves the process to price the fixture. The deadline is a
    fixed instant and `_now()` keeps moving, so a slow answer used to be written *after*
    lock — at whatever time the third party happened to reply. The whole product turns on
    that instant: a pick landing at 14:30:03 scores like any other.

    Simulated the way it actually happens — a fixed deadline a moment away and a provider
    that takes longer than that to answer — rather than by moving the deadline, which the
    request would not see: `pick_refusal` is handed the ORM object already loaded in this
    request's session, so what it re-reads is the clock, not the row.
    """
    client, fake = client_and_fake
    async with AsyncSessionLocal() as session:
        (alice,), league = await _seed_league(session, ["alice"])
        gameweek = await _open_sample_gameweek(session, fake, league)
        fixtures = await _fixture_ids(session, gameweek.id)
        # Lock a fraction of a second out: open when the request starts, shut when the
        # price comes back.
        gameweek.locks_at_utc = _now() + timedelta(milliseconds=250)
        await session.commit()
    epl = fixtures[SAMPLE_EPL_EVENT_ID]

    original_fetch = fake.fetch_odds

    async def _slow_fetch(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(1.0)
        return await original_fetch(*args, **kwargs)  # type: ignore[arg-type]

    fake.fetch_odds = _slow_fetch  # type: ignore[method-assign]
    try:
        resp = await _submit(client, league.slug, alice, epl, "MATCH_ODDS", "HOME")
    finally:
        fake.fetch_odds = original_fetch  # type: ignore[method-assign]

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "PICKS_LOCKED"

    # And nothing was written.
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(Pick).where(Pick.gameweek_id == gameweek.id)
        )
    assert count == 0
