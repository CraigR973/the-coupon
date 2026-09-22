"""Batch 112 — a league's rounds are its cadence, and nothing else.

From a live report. A league created at 21:19 on Friday 4 September 2026 with a Friday
19:00 window, then edited to Saturday 12:00 ninety seconds later, ended up holding **four
rounds on two cadences** — Fri 4, Sat 5, Fri 11, Sat 12 September — numbered 1, 3, 2, 4 in
date order, with both Friday rounds holding no picks and the Fri 4 one already past its
deadline when it was written. The stranded Friday round and the real Saturday one carried
the *same* 204 fixtures.

Three defects compounded, and these tests pin the two this batch closes:

* nothing retired a round built against a window the league had stopped playing, and
  ``unlocked_round_dates`` then kept it inside the discovery horizon so it was re-synced
  every morning and never aged out;
* ``upcoming_slate_dates`` includes today by date alone and asks nothing about the time,
  so a league created on its own window day *after* the lock minted a round whose deadline
  had already passed.

The third — that such a round outranks a claimable one in ``current_round_order`` — is
explicitly out of scope and untouched here.

Postgres-backed, because the rule is a delete against real rows with real cascades, and
the no-picks condition is a correlated subquery. Every league gets a window of its own so
one test's rounds can never decide another's.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome, PickScope, PickStatus
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services import scoring
from src.services.admin_ops import settlement_from_score
from src.services.gameweek import (
    populate_cadence_rounds,
    retire_stranded_rounds,
    upcoming_slate_dates,
    window_for,
)
from src.services.odds_provider import SlateWindow
from src.services.season_calendar import labels_for_gameweeks

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The horizon the shipped discovery job walks. Read from the setting in the tests that
#: need the real one; fixed here where the arithmetic is the point.
HORIZON = 2

FRIDAY, SATURDAY = 4, 5


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Never commits — these flush, so the rows are visible here and vanish on rollback."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _league(db: AsyncSession, *, weekday: int, minute: int) -> League:
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"owner-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    db.add(owner)
    await db.flush()
    league = League(
        slug=f"stranded-{tag}",
        name=f"Stranded {tag}",
        created_by=owner.id,
        slate_start_weekday=weekday,
        slate_start_minute=minute,
        slate_end_weekday=weekday,
        slate_end_minute=minute,
        lock_offset_minutes=30,
    )
    db.add(league)
    await db.flush()
    return league


def _window(weekday: int, minute: int) -> SlateWindow:
    return SlateWindow(
        start_weekday=weekday, start_minute=minute, end_weekday=weekday, end_minute=minute
    )


async def _round(
    db: AsyncSession,
    league: League,
    starts_on: date,
    *,
    status: GameweekStatus = GameweekStatus.open,
    window: SlateWindow | None = None,
) -> Gameweek:
    """A round on a date, with the lock its window implies."""
    live = window or window_for(league)
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=status,
        locks_at_utc=live.locks_at(starts_on),
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


async def _pick_on(db: AsyncSession, league: League, gameweek: Gameweek) -> Pick:
    """One member's claim, so the round stops being retirable."""
    tag = uuid.uuid4().hex[:8]
    player = Profile(display_name=f"picker-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    fixture = Fixture(
        provider_event_id=f"ev-{tag}",
        home="Forfar Athletic",
        away="Brechin City",
        kickoff_utc=datetime.combine(gameweek.starts_on, datetime.min.time()),
        competition="Scotland - League Two",
        competition_id="scotland-league-two",
    )
    db.add_all([player, fixture])
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    pick = Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name="Forfar Athletic",
        odds_at_pick=Decimal("2.00"),
        status=PickStatus.pending,
        pick_scope=PickScope.selection,
    )
    db.add(pick)
    await db.flush()
    return pick


async def _dates(db: AsyncSession, league: League) -> list[date]:
    rows = await db.execute(
        select(Gameweek.starts_on)
        .where(Gameweek.league_id == league.id)
        .order_by(Gameweek.starts_on)
    )
    return list(rows.scalars().all())


# ── The rule ──────────────────────────────────────────────────────────────────


async def test_a_window_edit_retires_the_rounds_built_against_the_old_one(
    session: AsyncSession,
) -> None:
    """The reported defect, at its smallest: the league plays Saturday now."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    old_cadence = _window(FRIDAY, 19 * 60)
    for starts_on in upcoming_slate_dates(today, old_cadence, HORIZON):
        await _round(session, league, starts_on, window=old_cadence)
    for starts_on in upcoming_slate_dates(today, window_for(league), HORIZON):
        await _round(session, league, starts_on)

    retired = await retire_stranded_rounds(session, league, today, HORIZON)

    assert retired == upcoming_slate_dates(today, old_cadence, HORIZON)
    assert await _dates(session, league) == upcoming_slate_dates(today, window_for(league), HORIZON)


async def test_the_production_shape_converges_on_two(session: AsyncSession) -> None:
    """Four rounds on two cadences — Fri 4, Sat 5, Fri 11, Sat 12 — become two."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    friday = _window(FRIDAY, 19 * 60)
    for starts_on in (date(2026, 9, 4), date(2026, 9, 11)):
        await _round(session, league, starts_on, window=friday)
    for starts_on in (date(2026, 9, 5), date(2026, 9, 12)):
        await _round(session, league, starts_on)
    assert len(await _dates(session, league)) == 4

    await retire_stranded_rounds(session, league, today, HORIZON)

    assert await _dates(session, league) == [date(2026, 9, 5), date(2026, 9, 12)]


async def test_saturday_to_friday_edit_retires_the_same_week_stray_and_its_label(
    session: AsyncSession,
) -> None:
    """The new Friday used to be the bound, leaving Saturday just beyond the sweep."""
    friday = date(2026, 9, 4)
    saturday = date(2026, 9, 5)
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    current = await _round(session, league, friday)
    await _round(session, league, saturday, window=_window(SATURDAY, 12 * 60))
    session.add(
        SeasonCalendar(
            season=2026,
            week_one_anchor=date(2026, 8, 8),
            extra_weeks=[],
        )
    )
    await session.flush()

    retired = await retire_stranded_rounds(session, league, friday, horizon=1)
    remaining = list(
        (await session.execute(select(Gameweek).where(Gameweek.league_id == league.id))).scalars()
    )
    labels = await labels_for_gameweeks(session, remaining)

    assert retired == [saturday]
    assert [gameweek.id for gameweek in remaining] == [current.id]
    assert list(labels.values()) == ["5"]


async def test_a_picked_same_week_stray_is_reported_and_not_scored(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A claim makes the stray non-retirable, so settlement is the final backstop."""
    friday = date(2026, 9, 4)
    saturday = date(2026, 9, 5)
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    current = await _round(session, league, friday, status=GameweekStatus.locked)
    stray = await _round(
        session,
        league,
        saturday,
        status=GameweekStatus.locked,
        window=_window(SATURDAY, 12 * 60),
    )
    current_pick = await _pick_on(session, league, current)
    stray_pick = await _pick_on(session, league, stray)
    current_fixture = await session.get(Fixture, current_pick.fixture_id)
    stray_fixture = await session.get(Fixture, stray_pick.fixture_id)
    assert current_fixture is not None and stray_fixture is not None

    reported = Mock()
    monkeypatch.setattr(scoring, "log", reported)

    refused = await scoring.settle_gameweek(
        session,
        stray,
        [settlement_from_score(stray_fixture.provider_event_id, 2, 0)],
    )
    settled = await scoring.settle_gameweek(
        session,
        current,
        [settlement_from_score(current_fixture.provider_event_id, 2, 0)],
    )

    assert refused == 0
    assert stray.status is GameweekStatus.locked
    assert stray_pick.status is PickStatus.pending and stray_pick.points_awarded is None
    assert settled == 1
    assert current.status is GameweekStatus.settled
    assert current_pick.status is PickStatus.won and current_pick.points_awarded == 20
    reported.error.assert_called_once()
    assert reported.error.call_args.args == ("same-football-week settlement refused",)
    assert reported.error.call_args.kwargs["reason"] == "undeclared_same_week_round"


async def test_a_declared_extra_in_the_same_week_still_settles(
    session: AsyncSession,
) -> None:
    """Calendar extras are intentional second rounds, not stranded cadence rows."""
    friday = date(2026, 9, 4)
    extra = date(2026, 9, 5)
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    current = await _round(session, league, friday, status=GameweekStatus.locked)
    extra_round = await _round(session, league, extra, status=GameweekStatus.locked)
    current_pick = await _pick_on(session, league, current)
    extra_pick = await _pick_on(session, league, extra_round)
    current_fixture = await session.get(Fixture, current_pick.fixture_id)
    extra_fixture = await session.get(Fixture, extra_pick.fixture_id)
    assert current_fixture is not None and extra_fixture is not None
    session.add(
        SeasonCalendar(
            season=2026,
            week_one_anchor=date(2026, 8, 8),
            extra_weeks=[extra],
        )
    )
    await session.flush()

    assert (
        await scoring.settle_gameweek(
            session,
            extra_round,
            [settlement_from_score(extra_fixture.provider_event_id, 2, 0)],
        )
        == 1
    )
    assert (
        await scoring.settle_gameweek(
            session,
            current,
            [settlement_from_score(current_fixture.provider_event_id, 2, 0)],
        )
        == 1
    )
    assert current.status is GameweekStatus.settled
    assert extra_round.status is GameweekStatus.settled


async def test_a_stranded_round_holding_a_pick_is_kept(session: AsyncSession) -> None:
    """What `rederive_claim_periods` protects is a deadline members claimed against.

    With a pick on it the round is somebody's week, whatever the window says now.
    """
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    friday = _window(FRIDAY, 19 * 60)
    claimed = await _round(session, league, date(2026, 9, 11), window=friday)
    await _pick_on(session, league, claimed)
    await _round(session, league, date(2026, 9, 4), window=friday)

    retired = await retire_stranded_rounds(session, league, today, HORIZON)

    assert retired == [date(2026, 9, 4)], "the empty one goes, the claimed one stays"
    assert date(2026, 9, 11) in await _dates(session, league)


async def test_a_settled_stranded_round_is_left_alone(session: AsyncSession) -> None:
    """A settled round is history and is left alone whatever its date."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    await _round(
        session,
        league,
        date(2026, 9, 11),
        status=GameweekStatus.settled,
        window=_window(FRIDAY, 19 * 60),
    )

    assert await retire_stranded_rounds(session, league, today, HORIZON) == []
    assert await _dates(session, league) == [date(2026, 9, 11)]


async def test_a_stranded_round_past_its_lock_but_unclaimed_is_retired(
    session: AsyncSession,
) -> None:
    """The no-picks condition is what makes a passed deadline safe to withdraw."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    # Friday 4 September, already locked by the time it was written.
    await _round(
        session,
        league,
        today,
        status=GameweekStatus.locked,
        window=_window(FRIDAY, 19 * 60),
    )

    assert await retire_stranded_rounds(session, league, today, HORIZON) == [today]
    assert await _dates(session, league) == []


async def test_history_is_never_retired(session: AsyncSession) -> None:
    """The horizon bound, which is the difference between a fix and eating the season.

    A legitimate round nobody happened to pick on is not junk — it is a week the league
    played badly — and without this bound every one of them would match the rule.
    """
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    old = date(2026, 8, 12)  # a Wednesday: not a cadence date, unclaimed, unsettled
    await _round(session, league, old, status=GameweekStatus.locked)

    assert await retire_stranded_rounds(session, league, today, HORIZON) == []
    assert old in await _dates(session, league)


async def test_a_round_beyond_the_horizon_is_not_retired(session: AsyncSession) -> None:
    """Bounded at the far end too: nothing out there has firmed up yet."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    far = max(upcoming_slate_dates(today, window_for(league), HORIZON)) + timedelta(weeks=6)
    await _round(session, league, far)

    assert await retire_stranded_rounds(session, league, today, HORIZON) == []
    assert far in await _dates(session, league)


# ── Never mint a round whose lock has already passed ──────────────────────────


async def test_a_league_created_on_its_window_day_after_the_lock_gets_no_round(
    session: AsyncSession,
) -> None:
    """The 21:19 creation, which minted a round that was unpickable the moment it existed."""
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    today = date(2026, 9, 4)  # a Friday; the window opens 19:00 and locks 18:30
    after_the_lock = datetime(2026, 9, 4, 20, 19)

    result = await populate_cadence_rounds(session, None, league, today, 1, now=after_the_lock)

    assert result.created_dates == []
    assert today in result.skipped_dates
    assert await _dates(session, league) == []


async def test_the_same_league_created_before_the_lock_still_gets_its_round(
    session: AsyncSession,
) -> None:
    """The rule refuses a dead deadline, not the day itself."""
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    today = date(2026, 9, 4)
    before_the_lock = datetime(2026, 9, 4, 9, 0)
    fixture = Fixture(
        provider_event_id=f"ev-{uuid.uuid4().hex[:8]}",
        home="Forfar Athletic",
        away="Brechin City",
        kickoff_utc=window_for(league).utc_before_open(today, 0),
        competition="Scotland - League Two",
        competition_id="scotland-league-two",
    )
    session.add(fixture)
    await session.flush()

    result = await populate_cadence_rounds(session, None, league, today, 1, now=before_the_lock)

    assert result.created_dates == [today]
    assert today not in result.skipped_dates


async def test_an_existing_round_is_never_dropped_by_the_already_locked_rule(
    session: AsyncSession,
) -> None:
    """Conditioned on `status is None`, so it only ever refuses to *create*.

    A league mid-season has a round on today whose lock passed this morning; that is a real
    week it is playing, and a rebuild must not treat it as one to refuse.
    """
    league = await _league(session, weekday=FRIDAY, minute=19 * 60)
    today = date(2026, 9, 4)
    await _round(session, league, today)

    result = await populate_cadence_rounds(
        session, None, league, today, 1, now=datetime(2026, 9, 4, 20, 19)
    )

    assert result.created_dates == []
    assert await _dates(session, league) == [today], "still there, not retired and not dropped"


# ── The populate retires before it adds ───────────────────────────────────────


async def test_the_rebuild_converges_rather_than_accumulating(session: AsyncSession) -> None:
    """ "Refresh rounds" after a window edit is the admin's route to the same rule."""
    today = date(2026, 9, 4)
    league = await _league(session, weekday=SATURDAY, minute=12 * 60)
    friday = _window(FRIDAY, 19 * 60)
    for starts_on in upcoming_slate_dates(today, friday, HORIZON):
        await _round(session, league, starts_on, window=friday)

    await populate_cadence_rounds(
        session, None, league, today, HORIZON, now=datetime(2026, 9, 4, 9, 0)
    )

    assert (
        await _dates(session, league) == []
    ), "the old cadence is retired; the new one has an empty pool and defers"
