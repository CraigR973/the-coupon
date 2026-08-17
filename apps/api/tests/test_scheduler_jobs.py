"""Scheduler domain functions on real Postgres (canned odds via ``FakeBetfair``).

Covers the pieces the pure/unit tests can't — the DB-driven halves of the four jobs:

* ``refresh_slate``            — a provider slate becomes gameweek + fixtures (and an empty
  slate creates nothing);
* ``lock_due_gameweeks``       — an open gameweek past 14:30 flips to ``locked``;
* ``open_due_gameweeks``       — a scheduled gameweek past its announced pick-open time
  flips to ``open`` (Batch 27), and one that never opened still locks;
* ``settle_gameweek_via_provider`` + ``standings`` — the **lock → settle → leaderboard**
  end-to-end: canned results settle the picks and the season table updates (the Batch 4
  slice of the acceptance e2e);
* ``members_missing_picks``    — only members without a pick are reminder candidates;
* gameweek selection helpers   — ``current_open_gameweeks`` / ``settleable_gameweeks``.

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
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.betfair import (
    SAMPLE_ARSENAL_SEL,
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_ID,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import (
    current_open_gameweeks,
    discover_fixtures,
    fixtures_for,
    lock_due_gameweeks,
    members_missing_picks,
    open_due_gameweeks,
    refresh_slate,
    settleable_gameweeks,
    window_for,
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


async def _open_gameweek(
    db: AsyncSession, league: League, starts_on: date
) -> tuple[Gameweek, Fixture, Fixture]:
    """An open round for ``league`` playing the two sample fixtures (EPL, SL2).

    Fixtures go into the shared pool and are linked to the round, which is how a
    second league can be given the same card without a second row.
    """
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=GameweekStatus.open,
        locks_at_utc=window_for(league).locks_at(starts_on),
    )
    db.add(gameweek)
    await db.flush()
    kickoff = datetime(starts_on.year, starts_on.month, starts_on.day, 14, 0)

    fixtures = []
    for event_id, home, away, competition, competition_id in (
        (SAMPLE_EPL_EVENT_ID, "Arsenal", "Chelsea", "English Premier League", "10932509"),
        (
            SAMPLE_SL2_EVENT_ID,
            "Forfar Athletic",
            "Brechin City",
            "Scottish League Two",
            "10932510",
        ),
    ):
        existing = await db.execute(select(Fixture).where(Fixture.provider_event_id == event_id))
        fixture = existing.scalar_one_or_none()
        if fixture is None:
            fixture = Fixture(
                provider_event_id=event_id,
                home=home,
                away=away,
                kickoff_utc=kickoff,
                competition=competition,
                competition_id=competition_id,
            )
            db.add(fixture)
            await db.flush()
        db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
        fixtures.append(fixture)
    await db.flush()
    return gameweek, fixtures[0], fixtures[1]


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
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    gameweek = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert gameweek is not None
    assert gameweek.starts_on == SAMPLE_SATURDAY
    assert gameweek.league_id == league.id
    fixtures = await fixtures_for(session, gameweek.id)
    assert {"Arsenal", "Forfar Athletic"} <= {f.home for f in fixtures}

    # A date the provider prices nothing for → no round is created.
    assert await refresh_slate(session, fake, league, date(2030, 1, 5)) is None


async def test_discovery_walks_the_horizon_and_skips_barren_dates(
    session: AsyncSession,
) -> None:
    """The daily job pre-fetches fixtures ahead of time, without pricing them."""
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    # A horizon starting the week before the sample Saturday: the first date carries
    # the canned card, the rest carry nothing.
    discovered = await discover_fixtures(
        session, fake, [league], SAMPLE_SATURDAY - timedelta(days=2), 3
    )

    assert [g.starts_on for g in discovered] == [SAMPLE_SATURDAY]
    assert len(await fixtures_for(session, discovered[0].id)) >= 2


async def test_discovery_is_idempotent_across_days(session: AsyncSession) -> None:
    """It runs daily against the same round, so a re-run must not duplicate rows."""
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    first = await discover_fixtures(session, fake, [league], SAMPLE_SATURDAY, 1)
    before = await fixtures_for(session, first[0].id)

    second = await discover_fixtures(session, fake, [league], SAMPLE_SATURDAY, 1)
    after = await fixtures_for(session, second[0].id)

    assert second[0].id == first[0].id
    assert len(after) == len(before)


async def test_two_leagues_on_one_window_cost_a_single_provider_fetch(
    session: AsyncSession,
) -> None:
    """The whole point of the shared pool: a second league on the same window is free.

    This is the property the request budget depends on. If discovery ever fetches
    per league instead of per window, the provider bill scales with membership and
    the free plan stops being enough.
    """
    _, first = await _seed_league(session, ["alice"])
    _, second = await _seed_league(session, ["bob"])
    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []

    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date) -> object:
        calls.append(starts_on)
        return await original(window, starts_on)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    discovered = await discover_fixtures(session, fake, [first, second], SAMPLE_SATURDAY, 1)

    assert len(calls) == 1, "one window, one date — one fetch, however many leagues"
    assert len(discovered) == 2, "but both leagues get their own round"
    assert {g.league_id for g in discovered} == {first.id, second.id}

    # …drawing on the same pooled fixture rows, not copies.
    first_fixtures = {f.id for f in await fixtures_for(session, discovered[0].id)}
    second_fixtures = {f.id for f in await fixtures_for(session, discovered[1].id)}
    assert first_fixtures == second_fixtures
    assert first_fixtures, "the round is not empty"


async def test_a_different_window_costs_its_own_fetch(session: AsyncSession) -> None:
    """Only a genuinely different window adds provider cost."""
    _, saturday_league = await _seed_league(session, ["alice"])
    _, friday_league = await _seed_league(session, ["bob"])
    friday_league.slate_start_weekday = 4  # Friday
    friday_league.slate_end_weekday = 0  # through Monday
    await session.flush()

    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []
    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date) -> object:
        calls.append(starts_on)
        return await original(window, starts_on)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    await discover_fixtures(session, fake, [saturday_league, friday_league], SAMPLE_SATURDAY, 1)
    assert len(calls) == 2, "two distinct windows, two fetches"


# ── Batch 15: the per-league competition selection (link-time filter) ────────────


async def test_sync_slate_plays_only_the_leagues_selected_competitions(
    session: AsyncSession,
) -> None:
    """A league that plays only the EPL gets the EPL fixture and not the Scottish one.

    The selection is applied at link time, so the same shared fetch feeds a narrowed
    league a subset of its fixtures without a second provider request.
    """
    _, league = await _seed_league(session, ["epl-only"])
    league.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    await session.flush()
    fake = FakeBetfair.with_sample_data()

    gameweek = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert gameweek is not None
    fixtures = await fixtures_for(session, gameweek.id)
    assert {f.competition_id for f in fixtures} == {SAMPLE_EPL_ID}
    assert [f.home for f in fixtures] == ["Arsenal"], "the Scottish fixture must be excluded"


async def test_sync_slate_records_no_round_when_the_selection_excludes_every_fixture(
    session: AsyncSession,
) -> None:
    """A league playing none of a window's competitions gets no round, not an empty one."""
    _, league = await _seed_league(session, ["none-of-these"])
    league.competitions = [{"slug": "a-competition-not-on-this-slate", "name": "Elsewhere"}]
    await session.flush()
    fake = FakeBetfair.with_sample_data()

    # The provider *does* carry fixtures for this date — they are just not this league's.
    assert await refresh_slate(session, fake, league, SAMPLE_SATURDAY) is None
    # And an all-UK league on the same date still gets its round from the same data.
    _, all_uk = await _seed_league(session, ["all-uk"])
    assert await refresh_slate(session, fake, all_uk, SAMPLE_SATURDAY) is not None


async def test_narrowing_after_a_round_exists_keeps_the_round_but_stops_adding(
    session: AsyncSession,
) -> None:
    """Links are added, never removed — narrowing does not strip a fixture a member may hold.

    The Scottish fixture linked while the league was all-UK stays put; a later refresh
    under an EPL-only selection simply adds nothing new.
    """
    _, league = await _seed_league(session, ["was-broad"])
    fake = FakeBetfair.with_sample_data()

    first = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert first is not None
    assert {SAMPLE_EPL_ID, SAMPLE_SL2_ID} == {
        f.competition_id for f in await fixtures_for(session, first.id)
    }

    league.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    await session.flush()
    again = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert again is not None and again.id == first.id
    # Both fixtures remain: the existing SL2 link is preserved even though it is no
    # longer selected, because a pick may already stand on it.
    assert {SAMPLE_EPL_ID, SAMPLE_SL2_ID} == {
        f.competition_id for f in await fixtures_for(session, again.id)
    }


# ── lock → settle → leaderboard (the Batch 4 e2e slice) ─────────────────────────


async def test_lock_then_settle_updates_leaderboard(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, sl2 = await _open_gameweek(session, league, date(2027, 3, 6))

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
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 8))
    before = gameweek.locks_at_utc - timedelta(hours=1)
    after = gameweek.locks_at_utc + timedelta(hours=1)

    # Before lock: open and remindable, not yet settleable.
    assert gameweek.id in {g.id for g in await current_open_gameweeks(session, before)}
    assert gameweek.id not in {g.id for g in await settleable_gameweeks(session, before)}

    # After lock: settleable even while still 'open' (defensive if the lock job missed a run).
    assert gameweek.id in {g.id for g in await settleable_gameweeks(session, after)}


# ── the pick-open flip (Batch 27) ───────────────────────────────────────────────


async def test_a_scheduled_round_opens_when_its_announced_time_arrives(
    session: AsyncSession,
) -> None:
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 15))
    opens_at = gameweek.locks_at_utc - timedelta(days=7)
    gameweek.status = GameweekStatus.scheduled
    gameweek.picks_open_at_utc = opens_at
    await session.flush()

    # A minute early it stays shut, and is not a reminder candidate — nagging a member
    # for a pick they cannot make yet is worse than not reminding them at all.
    # Scoped to this round rather than asserting an empty sweep: the HTTP pick-flow
    # tests commit rounds of their own into the shared scratch database.
    early = opens_at - timedelta(minutes=1)
    assert gameweek.id not in {g.id for g in await open_due_gameweeks(session, early)}
    assert gameweek.status is GameweekStatus.scheduled
    assert gameweek.id not in {g.id for g in await current_open_gameweeks(session, early)}

    # On the instant it opens, and only then does it start reminding.
    assert gameweek.id in {g.id for g in await open_due_gameweeks(session, opens_at)}
    assert gameweek.status is GameweekStatus.open
    assert gameweek.id in {g.id for g in await current_open_gameweeks(session, opens_at)}


async def test_a_round_that_never_opened_still_locks(session: AsyncSession) -> None:
    """A missed open job must not leave a round advertising a claim period that closed."""
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 22))
    gameweek.status = GameweekStatus.scheduled
    gameweek.picks_open_at_utc = gameweek.locks_at_utc - timedelta(days=7)
    await session.flush()

    after_lock = gameweek.locks_at_utc + timedelta(minutes=1)
    assert gameweek.id in {g.id for g in await lock_due_gameweeks(session, after_lock)}
    assert gameweek.status is GameweekStatus.locked


async def test_a_round_with_no_announced_opening_is_never_flipped(
    session: AsyncSession,
) -> None:
    """The pre-batch rule: no instant, no waiting — the round is already ``open``."""
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 29))
    assert gameweek.picks_open_at_utc is None

    opened = await open_due_gameweeks(session, gameweek.locks_at_utc)
    assert gameweek.id not in {g.id for g in opened}
    assert gameweek.status is GameweekStatus.open


# ── members_missing_picks ───────────────────────────────────────────────────────


async def test_members_missing_picks_targets_only_non_pickers(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, _sl2 = await _open_gameweek(session, league, date(2027, 4, 3))

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
    # And the slug, which is what the reminder's url is built from (Batch 30).
    assert bob.league_slug == league.slug
