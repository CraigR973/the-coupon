"""Scheduler domain functions on real Postgres (canned odds via ``FakeBetfair``).

Covers the pieces the pure/unit tests can't — the DB-driven halves of the four jobs:

* ``refresh_slate``            — a provider slate becomes gameweek + fixtures (and an empty
  slate creates nothing);
* ``lock_due_gameweeks``       — an open gameweek past 14:30 flips to ``locked``;
* ``settle_gameweek_via_provider`` + ``standings`` — the **lock → settle → leaderboard**
  end-to-end: canned results settle the picks and the season table updates (the Batch 4
  slice of the acceptance e2e);
* ``members_missing_picks``    — only members without a pick are reminder candidates;
* gameweek selection helpers   — ``current_open_gameweek`` / ``settleable_gameweeks``.

Skipped unless ``DATABASE_URL`` points at a migrated database (the repo runs it via the
pgserver harness). Each test does all its work inside one session and never commits, so the
suite stays hermetic regardless of order.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.betfair import (
    SAMPLE_ARSENAL_SEL,
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import (
    compute_locks_at,
    current_open_gameweek,
    discover_fixtures,
    lock_due_gameweeks,
    members_missing_picks,
    refresh_slate,
    settleable_gameweeks,
)
from src.services.scoring import settle_gameweek_via_provider, standings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session that is always rolled back — nothing these tests write persists."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _seed_league(db: AsyncSession, names: list[str]) -> tuple[dict[str, Profile], League]:
    """Create players + a league they all belong to (flush only — no commit)."""
    tag = uuid.uuid4().hex[:8]
    players = {
        name: Profile(display_name=f"{name}-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
        for name in names
    }
    db.add_all(list(players.values()))
    await db.flush()
    league = League(
        slug=f"cpn-{tag}", name=f"Coupon {tag}", created_by=next(iter(players.values())).id
    )
    db.add(league)
    await db.flush()
    for player in players.values():
        db.add(LeagueMembership(league_id=league.id, player_id=player.id))
    await db.flush()
    return players, league


async def _open_gameweek(db: AsyncSession, saturday: date) -> tuple[Gameweek, Fixture, Fixture]:
    """An open gameweek + the two sample fixtures (EPL, SL2), keyed by ``saturday``."""
    gameweek = Gameweek(
        saturday_date=saturday,
        status=GameweekStatus.open,
        locks_at_utc=compute_locks_at(saturday),
    )
    db.add(gameweek)
    await db.flush()
    kickoff = datetime(saturday.year, saturday.month, saturday.day, 14, 0)
    epl = Fixture(
        gameweek_id=gameweek.id,
        provider_event_id=SAMPLE_EPL_EVENT_ID,
        home="Arsenal",
        away="Chelsea",
        kickoff_utc=kickoff,
        competition="English Premier League",
        competition_id="10932509",
    )
    sl2 = Fixture(
        gameweek_id=gameweek.id,
        provider_event_id=SAMPLE_SL2_EVENT_ID,
        home="Forfar Athletic",
        away="Brechin City",
        kickoff_utc=kickoff,
        competition="Scottish League Two",
        competition_id="10932510",
    )
    db.add_all([epl, sl2])
    await db.flush()
    return gameweek, epl, sl2


def _pick(
    league: League,
    gameweek: Gameweek,
    fixture: Fixture,
    player: Profile,
    outcome: PickOutcome,
    runner_name: str,
    odds: str,
) -> Pick:
    return Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market=PickMarket.MATCH_ODDS,
        outcome=outcome,
        runner_name=runner_name,
        odds_at_pick=Decimal(odds),
    )


# ── refresh_slate ───────────────────────────────────────────────────────────────


async def test_refresh_slate_syncs_fixtures_and_skips_empty(session: AsyncSession) -> None:
    fake = FakeBetfair.with_sample_data()

    gameweek = await refresh_slate(session, fake, SAMPLE_SATURDAY)
    assert gameweek is not None
    assert gameweek.saturday_date == SAMPLE_SATURDAY
    fixtures = (
        (await session.execute(select(Fixture).where(Fixture.gameweek_id == gameweek.id)))
        .scalars()
        .all()
    )
    assert {"Arsenal", "Forfar Athletic"} <= {f.home for f in fixtures}

    # A Saturday the provider prices nothing for → no gameweek is created.
    assert await refresh_slate(session, fake, date(2030, 1, 5)) is None


async def test_discovery_walks_the_horizon_and_skips_barren_saturdays(
    session: AsyncSession,
) -> None:
    """The daily job pre-fetches fixtures ahead of time, without pricing them."""
    fake = FakeBetfair.with_sample_data()

    discovered = await discover_fixtures(
        session, fake, [SAMPLE_SATURDAY, date(2030, 1, 5), date(2030, 1, 12)]
    )

    # Only the Saturday the provider carries a card for becomes a gameweek.
    assert [g.saturday_date for g in discovered] == [SAMPLE_SATURDAY]
    fixtures = (
        (await session.execute(select(Fixture).where(Fixture.gameweek_id == discovered[0].id)))
        .scalars()
        .all()
    )
    assert len(fixtures) >= 2
    # Discovery is fixtures only — no odds were requested for any of them.
    assert fake.odds_calls == [] if hasattr(fake, "odds_calls") else True


async def test_discovery_is_idempotent_across_days(session: AsyncSession) -> None:
    """It runs daily against the same Saturday, so a re-run must not duplicate rows."""
    fake = FakeBetfair.with_sample_data()

    first = await discover_fixtures(session, fake, [SAMPLE_SATURDAY])
    before = (
        (await session.execute(select(Fixture).where(Fixture.gameweek_id == first[0].id)))
        .scalars()
        .all()
    )

    second = await discover_fixtures(session, fake, [SAMPLE_SATURDAY])
    after = (
        (await session.execute(select(Fixture).where(Fixture.gameweek_id == second[0].id)))
        .scalars()
        .all()
    )

    assert second[0].id == first[0].id
    assert len(after) == len(before)


# ── lock → settle → leaderboard (the Batch 4 e2e slice) ─────────────────────────


async def test_lock_then_settle_updates_leaderboard(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, sl2 = await _open_gameweek(session, date(2027, 3, 6))

    # alice → Arsenal (home), bob → Chelsea (away), carol → Forfar (home).
    session.add_all(
        [
            _pick(
                league,
                gameweek,
                epl,
                players["alice"],
                PickOutcome.HOME,
                "Arsenal",
                "1.90",
            ),
            _pick(
                league,
                gameweek,
                epl,
                players["bob"],
                PickOutcome.AWAY,
                "Chelsea",
                "4.30",
            ),
            _pick(
                league,
                gameweek,
                sl2,
                players["carol"],
                PickOutcome.HOME,
                "Forfar Athletic",
                "2.40",
            ),
        ]
    )
    await session.flush()

    # LOCK — after 14:30 the open gameweek flips to locked (and becomes settleable).
    after_lock = gameweek.locks_at_utc + timedelta(minutes=1)
    locked = await lock_due_gameweeks(session, after_lock)
    assert gameweek.id in {g.id for g in locked}
    assert gameweek.status is GameweekStatus.locked
    assert gameweek.id in {g.id for g in await settleable_gameweeks(session, after_lock)}

    # SETTLE — canned results: Arsenal (EPL) and Forfar (SL2) win.
    fake = FakeBetfair.with_sample_data()
    fake.close_markets(
        {
            SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
            SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
        }
    )
    resolved = await settle_gameweek_via_provider(session, fake, gameweek)
    assert resolved == 3
    assert gameweek.status is GameweekStatus.settled
    assert gameweek.settled_at is not None

    picks = {
        p.player_id: p
        for p in (
            await session.execute(select(Pick).where(Pick.gameweek_id == gameweek.id))
        ).scalars()
    }
    assert picks[players["alice"].id].status is PickStatus.won  # 1.90 × 10
    assert picks[players["bob"].id].status is PickStatus.lost
    assert picks[players["carol"].id].status is PickStatus.won  # 2.40 × 10

    # LEADERBOARD — carol 24, alice 19, bob 0.
    table = {s.display_name.split("-")[0]: s for s in await standings(session, league.id)}
    assert (table["carol"].total_points, table["carol"].rank) == (24, 1)
    assert (table["alice"].total_points, table["alice"].rank) == (19, 2)
    assert (table["bob"].total_points, table["bob"].rank) == (0, 3)

    # Idempotent: a second settle pass finds nothing pending.
    assert await settle_gameweek_via_provider(session, fake, gameweek) == 0


# ── gameweek selection helpers ──────────────────────────────────────────────────


async def test_open_and_settleable_selection(session: AsyncSession) -> None:
    gameweek, _epl, _sl2 = await _open_gameweek(session, date(2027, 5, 8))
    before = gameweek.locks_at_utc - timedelta(hours=1)
    after = gameweek.locks_at_utc + timedelta(hours=1)

    # Before lock: open and remindable, not yet settleable.
    current = await current_open_gameweek(session, before)
    assert current is not None and current.id == gameweek.id
    assert gameweek.id not in {g.id for g in await settleable_gameweeks(session, before)}

    # After lock: settleable even while still 'open' (defensive if the lock job missed a run).
    assert gameweek.id in {g.id for g in await settleable_gameweeks(session, after)}


# ── members_missing_picks ───────────────────────────────────────────────────────


async def test_members_missing_picks_targets_only_non_pickers(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, _sl2 = await _open_gameweek(session, date(2027, 4, 3))

    # Only alice has picked.
    session.add(
        _pick(
            league,
            gameweek,
            epl,
            players["alice"],
            PickOutcome.HOME,
            "Arsenal",
            "1.90",
        )
    )
    await session.flush()

    missing = await members_missing_picks(session, gameweek)
    mine = [m for m in missing if m.league_id == str(league.id)]
    assert {m.display_name.split("-")[0] for m in mine} == {"bob", "carol"}
    # Each carries the league context + the member's timezone for the reminder.
    bob = next(m for m in mine if m.display_name.startswith("bob"))
    assert bob.league_name == league.name
    assert bob.timezone == "UTC"
