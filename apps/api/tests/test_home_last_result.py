"""Batch 79 — the settled week reaching the home card, and the rank history under it.

The finding this batch turns on is a scheduling one, not a rendering one:
``current_round_order`` ranks a round accepting picks above a round already started, and
``accepting_picks`` treats a NULL opening as open *now*. On a league that announces no
opening — the ordinary configuration, and 2-1 Hibs' — next week's round therefore
displaces the round that just settled the moment discovery writes it, and a member would
never see how their week went. The same code works perfectly on a league that announces
one. That is why ``last_result`` is a separate read rather than fields on
``current_round``, and why the first test below is the load-bearing one.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def _auth(person: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(person.id, person.role)}"}


async def _profile(db: AsyncSession, name: str) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, owner: Profile, members: list[Profile]) -> League:
    league = League(
        slug=f"b79-{uuid.uuid4().hex[:8]}", name=f"B79 {uuid.uuid4().hex[:4]}", created_by=owner.id
    )
    db.add(league)
    await db.flush()
    for person in members:
        db.add(LeagueMembership(league_id=league.id, player_id=person.id))
    await db.flush()
    return league


async def _round(
    db: AsyncSession,
    league: League,
    *,
    starts_on: date,
    status: GameweekStatus,
    locks_at: datetime,
    opens_at: datetime | None = None,
    number: int | None = None,
) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=status,
        locks_at_utc=locks_at,
        picks_open_at_utc=opens_at,
        number=number,
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


async def _fixture(db: AsyncSession, gameweek: Gameweek, home: str, away: str) -> Fixture:
    fixture = Fixture(
        provider_event_id=f"ev-{uuid.uuid4().hex[:10]}",
        home=home,
        away=away,
        kickoff_utc=_now(),
        competition="Scottish League 2",
        competition_id="scotland-league-two",
    )
    db.add(fixture)
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    await db.flush()
    return fixture


async def _pick(
    db: AsyncSession,
    league: League,
    gameweek: Gameweek,
    person: Profile,
    *,
    status: PickStatus,
    odds: str = "2.00",
    points: int | None = None,
) -> Pick:
    fixture = await _fixture(db, gameweek, "Forfar", "Brechin")
    pick = Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        fixture_id=fixture.id,
        player_id=person.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name="Forfar",
        odds_at_pick=Decimal(odds),
        points_awarded=points,
        status=status,
    )
    db.add(pick)
    await db.flush()
    return pick


async def _summary(client: AsyncClient, person: Profile) -> dict:
    response = await client.get("/api/v1/me/cross-league-summary", headers=_auth(person))
    assert response.status_code == 200
    return response.json()["per_league"][0]


# ── The finding the batch exists for ─────────────────────────────────────────


async def test_settled_week_survives_a_league_that_announces_no_opening(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The case that would have shipped broken, and only on some leagues.

    A NULL ``picks_open_at_utc`` satisfies ``accepting_picks`` immediately, so the round
    discovery wrote for next week is *already* the current round while last week's result
    is a day old. Read off ``current_round`` this member would see nothing about their
    week; the same test on a league announcing an opening would have passed.
    """
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    settled = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=1, hours=2),
        number=4,
    )
    await _pick(session, league, settled, alice, status=PickStatus.won, points=20)
    # Next week's round, born claimable because the league announces no opening.
    await _round(
        session,
        league,
        starts_on=date.today() + timedelta(days=6),
        status=GameweekStatus.open,
        locks_at=_now() + timedelta(days=6),
        opens_at=None,
        number=5,
    )
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["current_round"]["gameweek_id"] != str(
        settled.id
    ), "next week has already displaced the settled round — the premise of this test"
    assert entry["last_result"] is not None
    assert entry["last_result"]["gameweek_id"] == str(settled.id)
    assert entry["last_result"]["number"] == 4


# ── The four things the card had nothing to say about ────────────────────────


async def test_a_winning_pick_reports_its_points_and_the_rounds_won_count(
    session: AsyncSession, client: AsyncClient
) -> None:
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    carol = await _profile(session, "carol")
    league = await _league(session, alice, [alice, bob, carol])
    settled = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await _pick(session, league, settled, alice, status=PickStatus.won, odds="3.50", points=35)
    await _pick(session, league, settled, bob, status=PickStatus.won, odds="2.00", points=20)
    await _pick(session, league, settled, carol, status=PickStatus.lost, odds="4.00")
    await session.commit()

    result = (await _summary(client, alice))["last_result"]

    assert result["my_pick"]["status"] == "won"
    assert result["my_pick"]["points_awarded"] == 35
    assert result["leg_count"] == 3
    assert result["picks_won"] == 2, "two of three landed — `all_won` alone cannot say this"
    assert result["all_won"] is False


async def test_a_void_pick_reports_neither_a_loss_nor_a_zero(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A void fixture never ran. Reporting it as 0 points would read as a bad pick."""
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    settled = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await _pick(session, league, settled, alice, status=PickStatus.void)
    await session.commit()

    result = (await _summary(client, alice))["last_result"]

    assert result["my_pick"]["status"] == "void"
    assert result["my_pick"]["points_awarded"] is None
    assert result["picks_won"] == 0


async def test_rank_movement_measures_the_round_being_reported(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Alice trails Bob until the last round, then passes him — that is +1, not the season.

    Bob's earlier round is what makes this a real test: over the whole season Alice is
    first either way, so a movement computed against an empty table would also read as a
    rise. Only excluding *the reported round* puts her second beforehand.
    """
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    league = await _league(session, alice, [alice, bob])
    earlier = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=8),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=9),
    )
    await _pick(session, league, earlier, bob, status=PickStatus.won, odds="5.00", points=50)
    await _pick(session, league, earlier, alice, status=PickStatus.lost, odds="2.00")
    latest = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await _pick(session, league, latest, alice, status=PickStatus.won, odds="9.00", points=90)
    await _pick(session, league, latest, bob, status=PickStatus.lost, odds="2.00")
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["rank"] == 1, "90 beats 50 over the season"
    assert entry["last_result"]["gameweek_id"] == str(latest.id)
    assert entry["last_result"]["rank_movement"] == 1, "second before this round, first after"


async def test_the_next_opening_is_carried_while_the_current_round_is_settled(
    session: AsyncSession, client: AsyncClient
) -> None:
    """`current_round` is one round, so a settled card had nothing to count down to."""
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    settled = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await _pick(session, league, settled, alice, status=PickStatus.won, points=20)
    opens_at = _now() + timedelta(days=3)
    await _round(
        session,
        league,
        starts_on=date.today() + timedelta(days=6),
        status=GameweekStatus.scheduled,
        locks_at=_now() + timedelta(days=6),
        opens_at=opens_at,
    )
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["current_round"]["gameweek_id"] == str(
        settled.id
    ), "a future opening does not make that round current — it is not accepting picks yet"
    assert entry["next_opens_at_utc"] is not None
    assert entry["next_opens_at_utc"].startswith(opens_at.isoformat(timespec="seconds")[:16])


async def test_no_opening_is_announced_at_all(session: AsyncSession, client: AsyncClient) -> None:
    """The ordinary configuration. Absent means *no gate*, and must not read as an offset."""
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    await _round(
        session,
        league,
        starts_on=date.today() + timedelta(days=3),
        status=GameweekStatus.open,
        locks_at=_now() + timedelta(days=3),
        opens_at=None,
    )
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["next_opens_at_utc"] is None
    assert entry["last_result"] is None, "no round has settled yet"


async def test_a_league_with_no_settled_round_reports_no_result(
    session: AsyncSession, client: AsyncClient
) -> None:
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    await _round(
        session,
        league,
        starts_on=date.today(),
        status=GameweekStatus.open,
        locks_at=_now() + timedelta(hours=2),
    )
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["last_result"] is None
    assert entry["current_round"] is not None


async def test_a_settled_round_nobody_picked_has_no_coupon_outcome(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Vacuously settled. `all_won` over an empty set is true, and that is not the truth."""
    alice = await _profile(session, "alice")
    league = await _league(session, alice, [alice])
    await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await session.commit()

    result = (await _summary(client, alice))["last_result"]

    assert result["leg_count"] == 0
    assert result["picks_won"] == 0
    assert result["all_won"] is None
    assert result["my_pick"] is None
    assert result["rank_movement"] is None or result["rank_movement"] == 0


# ── Batch 81: the run reaches home ───────────────────────────────────────────


async def test_the_summary_carries_each_leagues_own_form_run(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A member plays several leagues at once and each is its own game.

    Read straight off the league's season table, so home and the leaderboard cannot draw
    different runs for the same member.
    """
    alice = await _profile(session, "alice")
    first = await _league(session, alice, [alice])
    second = await _league(session, alice, [alice])
    for league, status, points in (
        (first, PickStatus.won, 50),
        (second, PickStatus.lost, None),
    ):
        settled = await _round(
            session,
            league,
            starts_on=date.today() - timedelta(days=1),
            status=GameweekStatus.settled,
            locks_at=_now() - timedelta(days=2),
        )
        await _pick(session, league, settled, alice, status=status, points=points)
    await session.commit()

    response = await client.get("/api/v1/me/cross-league-summary", headers=_auth(alice))
    by_slug = {entry["slug"]: entry for entry in response.json()["per_league"]}

    assert [r["points"] for r in by_slug[first.slug]["recent_form"]] == [50]
    assert [r["status"] for r in by_slug[second.slug]["recent_form"]] == ["lost"]


async def test_rank_movement_is_unaffected_by_the_run_now_being_default(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The rewound table still asks for no form, and still measures the right thing.

    Batch 81 flipped the default, which means the *only* remaining `with_form=False` is
    the throwaway table underneath rank movement. If that call ever stops passing it, this
    keeps working and nothing tells you — so the assertion here is the movement, and
    `test_standings_by_league_keeps_leagues_apart` holds the flag itself.
    """
    alice = await _profile(session, "alice")
    bob = await _profile(session, "bob")
    league = await _league(session, alice, [alice, bob])
    earlier = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=8),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=9),
    )
    await _pick(session, league, earlier, bob, status=PickStatus.won, odds="5.00", points=50)
    await _pick(session, league, earlier, alice, status=PickStatus.lost, odds="2.00")
    latest = await _round(
        session,
        league,
        starts_on=date.today() - timedelta(days=1),
        status=GameweekStatus.settled,
        locks_at=_now() - timedelta(days=2),
    )
    await _pick(session, league, latest, alice, status=PickStatus.won, odds="9.00", points=90)
    await _pick(session, league, latest, bob, status=PickStatus.lost, odds="2.00")
    await session.commit()

    entry = await _summary(client, alice)

    assert entry["last_result"]["rank_movement"] == 1
    assert [r["status"] for r in entry["recent_form"]] == ["won", "lost"]
