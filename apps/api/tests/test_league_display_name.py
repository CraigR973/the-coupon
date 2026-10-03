"""Batch 181 — one name per member, in every league.

The per-league display-name override began as Batch 126's problem: it stored whatever it
was sent, and the roster, the standings and the coupon rendered it, so two members could
appear under one name. Batch 126 checked new names against the league's *current* members,
which still let an override copy someone outside the league — the site admin's name, or a
friend's before they joined (review 2026-09-28, SEC-29). No screen ever set one.

The owner's decision on 2026-09-30 removed the route instead of hardening it. What these
hold to: the route is gone; every surface that rendered an override renders the member's
own name, which registration keeps unique, even while an old override is still stored;
and ``src.clear_league_name_overrides`` clears the stored ones and reports how many.

Postgres-backed. The HTTP tests commit through the endpoints' own sessions; the rest share
one session and roll it back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import src.clear_league_name_overrides as clearing
from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import AuditLog
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.betfair import FakeBetfair
from src.services.coupon import build_coupon
from src.services.gameweek import notification_targets
from src.services.scoring import gameweek_results, standings
from tests.season_dates import season_anchor
from tests.test_pick_progress_batch_107 import _epl_fixture_id, _seeded_round

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


async def _store_override(league_id: uuid.UUID, player_id: uuid.UUID, name: str) -> None:
    """An override as a member could still hold one: written before the route was retired."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LeagueMembership)
            .where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.player_id == player_id,
            )
            .values(display_name_override=name)
        )
        await session.commit()


# -- The route ------------------------------------------------------------------


async def test_the_per_league_name_route_is_gone(client: AsyncClient) -> None:
    """SEC-29's door: a member naming themselves after somebody outside the league."""
    admin_name = f"Sam-{uuid.uuid4().hex[:6]}"
    await _profile(admin_name)
    bob = await _profile()
    league = await _league(bob)

    for body in ({"display_name_override": admin_name}, {"display_name_override": None}):
        gone = await client.put(PATH.format(slug=league.slug), json=body, headers=_auth(bob))
        assert gone.status_code == 404, (body, gone.text)
    assert await _override_of(league.id, bob.id) is None


async def test_the_roster_shows_global_names_even_with_an_override_stored(
    client: AsyncClient,
) -> None:
    """The two member lists — the roster and the league page — read the profile's name."""
    owner = await _profile()
    bob = await _profile()
    league = await _league(owner, bob)
    impersonated = f"Erin-{uuid.uuid4().hex[:6]}"
    await _store_override(league.id, bob.id, impersonated)

    roster = await client.get(f"/api/v1/leagues/{league.slug}/members", headers=_auth(owner))
    detail = await client.get(f"/api/v1/leagues/{league.slug}", headers=_auth(owner))

    assert roster.status_code == 200, roster.text
    assert detail.status_code == 200, detail.text
    for listing in (roster.json(), detail.json()["members"]):
        names = {member["display_name"] for member in listing}
        assert names == {owner.display_name, bob.display_name}, names


# -- Every other surface, in one rolled-back session ------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _settled_round_won_by(
    db: AsyncSession, league: League, winner: Profile, impersonated: str
) -> Gameweek:
    """A settled round whose only pick is the winner's, with an override on their row."""
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=season_anchor(days_of_room=14) - timedelta(days=7),
        status=GameweekStatus.settled,
        locks_at_utc=_now() - timedelta(days=8),
    )
    fixture = Fixture(
        provider_event_id=f"ev-{uuid.uuid4().hex[:10]}",
        home="Forfar",
        away="Brechin",
        kickoff_utc=_now() - timedelta(days=8),
        competition="Scottish League 2",
        competition_id="scotland-league-two",
    )
    db.add_all([gameweek, fixture])
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    db.add(
        Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            fixture_id=fixture.id,
            player_id=winner.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar",
            odds_at_pick=Decimal("2.00"),
            points_awarded=20,
            status=PickStatus.won,
        )
    )
    await db.execute(
        update(LeagueMembership)
        .where(LeagueMembership.league_id == league.id, LeagueMembership.player_id == winner.id)
        .values(display_name_override=impersonated)
    )
    await db.flush()
    return gameweek


async def _members(db: AsyncSession, *names: str) -> tuple[League, list[Profile]]:
    people = [
        Profile(
            display_name=f"{name}-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=UserRole.player,
        )
        for name in names
    ]
    db.add_all(people)
    await db.flush()
    league = League(slug=f"dn-{uuid.uuid4().hex[:8]}", name="Global Names", created_by=people[0].id)
    db.add(league)
    await db.flush()
    db.add_all(LeagueMembership(league_id=league.id, player_id=p.id) for p in people)
    await db.flush()
    return league, people


async def test_the_standings_results_coupon_and_alerts_read_the_members_own_name(
    session: AsyncSession,
) -> None:
    """Each of these coalesced the override over the profile's name; none of them now does.

    The coupon never read the override, and is pinned here so it cannot start to.
    """
    league, (owner, bob) = await _members(session, "owner", "bob")
    impersonated = f"Erin-{uuid.uuid4().hex[:6]}"
    gameweek = await _settled_round_won_by(session, league, bob, impersonated)

    table = await standings(session, league.id)
    bobs_row = next(row for row in table if row.player_id == str(bob.id))
    assert bobs_row.display_name == bob.display_name

    results = await gameweek_results(session, league.id)
    assert [result.winner_names for result in results] == [[bob.display_name]]

    coupon = await build_coupon(session, league.id, gameweek)
    assert [leg.player_name for leg in coupon.legs] == [bob.display_name]

    targets = await notification_targets(session, gameweek)
    assert {target.display_name for target in targets} == {owner.display_name, bob.display_name}

    every_name = [bobs_row.display_name, *results[0].winner_names]
    every_name += [leg.player_name for leg in coupon.legs]
    every_name += [target.display_name for target in targets]
    assert impersonated not in every_name


@pytest_asyncio.fixture
async def odds_client() -> AsyncIterator[tuple[AsyncClient, FakeBetfair]]:
    """The submit endpoint over the canned card, as Batch 107's pick-progress tests drive it."""
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    app.dependency_overrides[get_optional_odds_provider] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, fake
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


async def test_the_pick_alert_names_the_picker_by_their_own_name(
    odds_client: tuple[AsyncClient, FakeBetfair],
) -> None:
    """The alert looked the override up for itself, so it is driven through the endpoint."""
    client, fake = odds_client
    league, gameweek, (picker, *_others) = await _seeded_round(fake, 3)
    impersonated = f"Erin-{uuid.uuid4().hex[:6]}"
    await _store_override(league.id, picker.id, impersonated)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        claimed = await client.post(
            f"/api/v1/leagues/{league.slug}/picks",
            json={"fixture_id": fixture_id, "market": "MATCH_ODDS", "outcome": "HOME"},
            headers=_auth(picker),
        )

    assert claimed.status_code == 201, claimed.text
    bodies = [call.args[3] for call in send.await_args_list]
    assert len(bodies) == 2, bodies
    assert all(body.startswith(f"{picker.display_name} picked ") for body in bodies), bodies
    assert not any(impersonated in body for body in bodies), bodies


# -- The data step ------------------------------------------------------------------


async def test_the_data_step_counts_the_overrides_and_clears_them(session: AsyncSession) -> None:
    """Counted before, cleared with the count reported, and nothing left afterwards."""
    league, (owner, bob, carol) = await _members(session, "owner", "bob", "carol")
    before = await clearing.count_overrides(session)
    for person, name in ((bob, "Gaffer"), (carol, "Skipper")):
        await session.execute(
            update(LeagueMembership)
            .where(LeagueMembership.league_id == league.id, LeagueMembership.player_id == person.id)
            .values(display_name_override=name)
        )

    assert await clearing.count_overrides(session) == before + 2
    assert await clearing.clear_overrides(session) == before + 2
    assert await clearing.count_overrides(session) == 0
    assert await clearing.clear_overrides(session) == 0

    rows = (
        await session.execute(
            select(LeagueMembership.player_id, LeagueMembership.display_name_override).where(
                LeagueMembership.league_id == league.id
            )
        )
    ).all()
    assert {player_id: override for player_id, override in rows} == {
        owner.id: None,
        bob.id: None,
        carol.id: None,
    }


async def test_the_dry_run_reports_the_count_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The first run in production is a dry run; it must leave every override where it is."""
    member = await _profile()
    league = await _league(member)
    await _store_override(league.id, member.id, "Gaffer")

    await clearing._run(apply_changes=False)

    printed = capsys.readouterr().out
    assert "per-league names stored: " in printed
    assert "DRY RUN" in printed
    assert await _override_of(league.id, member.id) == "Gaffer"

    await clearing._run(apply_changes=True)

    printed = capsys.readouterr().out
    assert "per-league names cleared: " in printed
    assert await _override_of(league.id, member.id) is None


async def test_the_data_step_clears_the_rows_of_members_who_left(session: AsyncSession) -> None:
    """A member who leaves and rejoins gets their old row back, override and all."""
    league, (_owner, leaver) = await _members(session, "owner", "leaver")
    await session.execute(
        update(LeagueMembership)
        .where(LeagueMembership.league_id == league.id, LeagueMembership.player_id == leaver.id)
        .values(display_name_override="Gaffer", deleted_at=_now())
    )

    await clearing.clear_overrides(session)

    override = (
        await session.execute(
            select(LeagueMembership.display_name_override).where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == leaver.id,
            )
        )
    ).scalar_one()
    assert override is None


async def test_the_data_step_changes_nothing_but_the_name(session: AsyncSession) -> None:
    """Roles, join dates, mutes and departures stay; no profile changes; no audit row."""
    league, (owner, bob) = await _members(session, "owner", "bob")
    left_at = _now() - timedelta(days=3)
    await session.execute(
        update(LeagueMembership)
        .where(LeagueMembership.league_id == league.id, LeagueMembership.player_id == bob.id)
        .values(
            display_name_override="Gaffer",
            role=LeagueMemberRole.admin,
            notification_muted=True,
            deleted_at=left_at,
        )
    )
    columns = (
        LeagueMembership.player_id,
        LeagueMembership.role,
        LeagueMembership.joined_at,
        LeagueMembership.notification_muted,
        LeagueMembership.deleted_at,
    )

    async def _rows() -> set[tuple[object, ...]]:
        rows = await session.execute(
            select(*columns).where(LeagueMembership.league_id == league.id)
        )
        return {tuple(row) for row in rows.all()}

    async def _audit_rows() -> int:
        return (await session.execute(select(func.count()).select_from(AuditLog))).scalar_one()

    memberships_before = await _rows()
    names_before = {owner.display_name, bob.display_name}
    audits_before = await _audit_rows()

    await clearing.clear_overrides(session)

    assert await _rows() == memberships_before
    assert await _audit_rows() == audits_before
    names_after = {
        name
        for (name,) in (
            await session.execute(
                select(Profile.display_name).where(Profile.id.in_([owner.id, bob.id]))
            )
        ).all()
    }
    assert names_after == names_before
