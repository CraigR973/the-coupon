"""Batch 70 — what kind of picks people are actually making.

The owner asked for cumulative and average odds on the league table and the profile.
These are one change rather than two: ``Standing`` is the single ranking rule in the
codebase and the leaderboard, the profile and the cross-league summary all read it, so
the figures go into the aggregate once and every surface gets them.

Two things make these tests worth their length.

**Every figure is recomputed here from the picks, in Python, and compared against what
the aggregate returned.** Asserting a SQL sum against a hand-written copy of the same SQL
sum proves only that it was copied correctly; recomputing from the rows proves the query
means what it claims.

**Void picks are the decision the row asked to be recorded.** ``picks_played`` counts won,
lost *and* void, because a member whose fixture was postponed did take part in that round.
The odds figures count only what ran, because a bet that was never struck is not a price
the member should be credited with. Two denominators, deliberately, and the UI says so.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, time
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.scoring import LONGSHOT_ODDS, Standing, points_for, standings
from tests.season_dates import season_week

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _league_with_member(db: AsyncSession) -> tuple[League, Profile]:
    tag = uuid.uuid4().hex[:8]
    member = Profile(display_name=f"shape-{tag}", pin_hash=hash_pin("8351"), role=UserRole.player)
    db.add(member)
    await db.flush()
    league = League(slug=f"shape-{tag}", name=f"Shape {tag}", created_by=member.id)
    db.add(league)
    await db.flush()
    db.add(LeagueMembership(league_id=league.id, player_id=member.id))
    await db.flush()
    return league, member


async def _settled_pick(
    db: AsyncSession,
    league: League,
    member: Profile,
    *,
    week: int,
    odds: str,
    status: PickStatus,
) -> Pick:
    """One resolved pick in its own round, scored the way settlement scores it."""
    tag = uuid.uuid4().hex[:8]
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=season_week(week + 26),
        status=GameweekStatus.settled,
        locks_at_utc=_lock(week),
    )
    fixture = Fixture(
        provider_event_id=f"ev-{tag}",
        home=f"Home {tag}",
        away=f"Away {tag}",
        kickoff_utc=_lock(week),
        competition="Test Division",
        competition_id=f"div-{tag}",
    )
    db.add_all([gameweek, fixture])
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    price = Decimal(odds)
    pick = Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        player_id=member.id,
        fixture_id=fixture.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name=f"Home {tag}",
        odds_at_pick=price,
        status=status,
        points_awarded=points_for(price) if status is PickStatus.won else 0,
    )
    db.add(pick)
    await db.flush()
    return pick


def _lock(week: int) -> datetime:
    """This round's lock, a week apart from its neighbours. Naive-UTC, as stored.

    Follows the round's own date rather than a written-down year. These rounds used to sit
    in January 2027 because any settled week would do; since Batch 96 the table is bounded
    by season, so "any week" has to be a week of the season being played or every figure
    here reads zero.
    """
    return datetime.combine(season_week(week + 26), time(14, 30))


def _expected(picks: Sequence[Pick]) -> dict[str, object]:
    """Every figure, recomputed from the picks themselves rather than from the query.

    This is the point of the module: a hand-copied SQL expression would agree with the
    query for the same wrong reason. Working from the rows means the two only agree if
    the aggregate means what its docstring says.
    """
    played = [p for p in picks if p.status in (PickStatus.won, PickStatus.lost, PickStatus.void)]
    priced = [p for p in played if p.status in (PickStatus.won, PickStatus.lost)]
    won = [p for p in played if p.status is PickStatus.won]
    total = sum(p.points_awarded or 0 for p in played)
    cumulative = sum(float(p.odds_at_pick) for p in priced)
    return {
        "total_points": total,
        "picks_played": len(played),
        "picks_won": len(won),
        "picks_priced": len(priced),
        "cumulative_odds": round(cumulative, 2),
        "average_odds": round(cumulative / len(priced), 2) if priced else None,
        "points_per_pick": round(total / len(played), 2) if played else None,
        "best_return": max((p.points_awarded or 0 for p in played), default=None),
        "win_rate_pct": round(100 * len(won) / len(played)) if played else None,
        "longshot_picks": sum(1 for p in priced if p.odds_at_pick >= LONGSHOT_ODDS),
        "favourite_picks": sum(1 for p in priced if p.odds_at_pick < LONGSHOT_ODDS),
    }


def _actual(row: Standing) -> dict[str, object]:
    return {key: getattr(row, key) for key in _expected([])}


async def test_every_figure_matches_the_picks_it_is_made_of(session: AsyncSession) -> None:
    """A season with wins, losses and a spread of prices, recomputed from the rows."""
    league, member = await _league_with_member(session)
    picks = [
        await _settled_pick(session, league, member, week=0, odds="1.50", status=PickStatus.won),
        await _settled_pick(session, league, member, week=1, odds="2.20", status=PickStatus.lost),
        await _settled_pick(session, league, member, week=2, odds="4.00", status=PickStatus.won),
        await _settled_pick(session, league, member, week=3, odds="3.00", status=PickStatus.lost),
    ]

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert _actual(row) == _expected(picks)
    # Spelled out as well as compared, so a reader can see the arithmetic rather than
    # trusting two helpers to disagree usefully.
    assert row.picks_played == 4
    assert row.picks_priced == 4
    assert row.cumulative_odds == 10.70
    # 10.70 / 4 is 2.675, and `round` takes that to 2.67 — the value is not exactly
    # representable as a float, so it rounds down. Left as it lands rather than nudged:
    # the same rounding runs on every surface, so they agree with each other.
    assert row.average_odds == 2.67
    assert row.best_return == 40  # round(4.00 × 10)
    assert row.longshot_picks == 2  # 4.00 and 3.00, at the 3.00 line
    assert row.favourite_picks == 2


async def test_a_void_pick_counts_as_played_and_not_as_priced(session: AsyncSession) -> None:
    """The decision the row asked to be recorded, asserted on both denominators.

    A postponed fixture is a round the member took part in, so it stays in
    ``picks_played`` — and a bet that never ran, so its price is not folded into a
    cumulative total the member did not stake.
    """
    league, member = await _league_with_member(session)
    picks = [
        await _settled_pick(session, league, member, week=0, odds="2.00", status=PickStatus.won),
        await _settled_pick(session, league, member, week=1, odds="9.00", status=PickStatus.void),
    ]

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert _actual(row) == _expected(picks)
    assert row.picks_played == 2, "the void round was still played"
    assert row.picks_priced == 1, "and the bet was never struck"
    assert row.cumulative_odds == 2.00, "the 9.00 that never ran is not theirs"
    assert row.average_odds == 2.00
    assert row.longshot_picks == 0, "a void longshot is not a longshot taken"
    # And the two denominators genuinely differ here, which is the thing the UI must say.
    assert row.picks_played != row.picks_priced


async def test_a_member_whose_only_pick_was_voided_has_no_odds_figures(
    session: AsyncSession,
) -> None:
    """Zero priced picks is a missing answer, not a zero one."""
    league, member = await _league_with_member(session)
    await _settled_pick(session, league, member, week=0, odds="5.00", status=PickStatus.void)

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert row.picks_played == 1
    assert row.picks_priced == 0
    assert row.average_odds is None, "no average over nothing"
    assert row.cumulative_odds == 0.0
    assert row.points_per_pick == 0.0, "they played a round and scored nothing"


async def test_a_member_who_has_never_picked_reports_nothing_rather_than_zero(
    session: AsyncSession,
) -> None:
    """An untested record is not a bad one — the rule Batch 25 set for win rate."""
    league, member = await _league_with_member(session)

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert row.picks_played == 0
    assert row.average_odds is None
    assert row.points_per_pick is None
    assert row.best_return is None
    assert row.win_rate_pct is None


async def test_the_longshot_line_is_inclusive_and_carried_on_the_row(
    session: AsyncSession,
) -> None:
    """A pick exactly on the line is a longshot, and the screen labels it from the row.

    The line travels with the figure so the UI cannot drift from the value the split was
    computed with — the same reason `odds_degraded` travels with the odds.
    """
    league, member = await _league_with_member(session)
    await _settled_pick(session, league, member, week=0, odds="3.00", status=PickStatus.lost)
    await _settled_pick(session, league, member, week=1, odds="2.99", status=PickStatus.lost)

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert row.longshot_picks == 1
    assert row.favourite_picks == 1
    assert row.longshot_odds == float(LONGSHOT_ODDS)


async def test_pending_picks_are_in_none_of_the_figures(session: AsyncSession) -> None:
    """A round still being played is not a record. It is not played, priced or counted."""
    league, member = await _league_with_member(session)
    await _settled_pick(session, league, member, week=0, odds="2.00", status=PickStatus.won)
    await _settled_pick(session, league, member, week=1, odds="8.00", status=PickStatus.pending)

    row = next(s for s in await standings(session, league.id) if s.player_id == str(member.id))

    assert row.picks_played == 1
    assert row.picks_priced == 1
    assert row.cumulative_odds == 2.00


async def test_the_ranking_is_unchanged_by_any_of_this(session: AsyncSession) -> None:
    """Points then wins then name, exactly as before. The new figures rank nothing.

    Worth pinning: adding columns to the one aggregate every surface reads is precisely
    the change that could reorder a leaderboard without anyone intending it.
    """
    league, first = await _league_with_member(session)
    second = Profile(
        display_name=f"rival-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    session.add(second)
    await session.flush()
    session.add(LeagueMembership(league_id=league.id, player_id=second.id))
    await session.flush()

    # `first` wins once at long odds; `second` wins twice at short ones for more points.
    await _settled_pick(session, league, first, week=0, odds="6.00", status=PickStatus.won)
    await _settled_pick(session, league, second, week=1, odds="4.00", status=PickStatus.won)
    await _settled_pick(session, league, second, week=2, odds="4.00", status=PickStatus.won)

    table = await standings(session, league.id)

    assert [s.player_id for s in table] == [str(second.id), str(first.id)]
    assert table[0].rank == 1 and table[1].rank == 2
    # …even though the member below has the longer average price.
    assert table[1].average_odds > table[0].average_odds
