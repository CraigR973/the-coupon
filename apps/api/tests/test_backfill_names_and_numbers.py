"""Batch 74 — four rounds renumbered and three members renamed, in production data.

Neither correction is testable in the sense that matters most: whether "Birch" really is
Marc Birch is the owner's word, not pytest's. What *is* testable is every way this could
put a wrong name on a real member's record, or a wrong number on a round people talk about
by number, without anyone noticing.

* **It fails closed.** A missing round or an unresolvable profile raises before anything
  is written, and a target name somebody else already holds aborts the *whole* run —
  including the renumbering, which is unrelated but must not half-land.
* **It is idempotent**, because a backfill that gets interrupted gets run again. The
  renames resolve through the new name as well as the old one, which is the only reason a
  second run is a no-op rather than "neither name matches any profile".
* **The season reads 1-4 afterwards**, checked against the database rather than the plan,
  because ``(league_id, number)`` carries no unique constraint.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.backfill_names_and_numbers import (
    LEAGUE_SLUG,
    RENAMES,
    ROUND_NUMBERS,
    BackfillError,
    apply,
    plan,
)
from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile, UserRole
from src.services.gameweek import next_gameweek_number

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


async def _seed(db: AsyncSession, *, numbers: dict[date, int | None] | None = None) -> League:
    """The league as production holds it before this batch runs.

    ``numbers`` defaults to the state Batch 68 left behind: 8 and 15 August unnumbered
    because it declined to renumber 22 August, and 22 and 29 August reading 1 and 2.
    """
    before: dict[date, int | None] = numbers or {
        date(2026, 8, 8): None,
        date(2026, 8, 15): None,
        date(2026, 8, 22): 1,
        date(2026, 8, 29): 2,
    }
    owner = Profile(
        display_name=f"bf74-owner-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    db.add(owner)
    await db.flush()
    league = League(slug=LEAGUE_SLUG, name="2-1 Hibs", created_by=owner.id)
    db.add(league)
    await db.flush()

    for old in RENAMES:
        profile = Profile(display_name=old, pin_hash=hash_pin("8351"), role=UserRole.player)
        db.add(profile)
        await db.flush()
        db.add(LeagueMembership(league_id=league.id, player_id=profile.id))

    for starts_on, number in before.items():
        db.add(
            Gameweek(
                league_id=league.id,
                starts_on=starts_on,
                status=GameweekStatus.settled,
                locks_at_utc=datetime(starts_on.year, starts_on.month, starts_on.day, 13, 30),
                number=number,
            )
        )
    await db.flush()
    return league


async def _numbers(db: AsyncSession, league: League) -> list[tuple[date, int | None]]:
    rows = (
        await db.execute(
            select(Gameweek.starts_on, Gameweek.number)
            .where(Gameweek.league_id == league.id)
            .order_by(Gameweek.starts_on)
        )
    ).all()
    return [(starts_on, number) for starts_on, number in rows]


async def _names(db: AsyncSession) -> set[str]:
    rows = await db.execute(select(Profile.display_name))
    return set(rows.scalars().all())


# ── The renumbering ────────────────────────────────────────────────────────────


async def test_the_season_reads_one_to_four_in_date_order(session: AsyncSession) -> None:
    """The row's own verification requirement, and the point of the batch.

    Read back from the database rather than from the returned plan: there is no unique
    constraint on ``(league_id, number)``, so "two rounds both called Gameweek 3" is a
    state only an explicit read can rule out.
    """
    league = await _seed(session)
    await apply(session)
    assert await _numbers(session, league) == sorted(ROUND_NUMBERS.items())


async def test_the_next_round_discovered_takes_five(session: AsyncSession) -> None:
    """No code follows the renumbering, which is the claim this checks.

    ``next_gameweek_number`` is one past the season *maximum*, so once these four read 1-4
    the sequence continues on its own. Before the run it would have handed out 3, which is
    a number 22 August was already using under the old scheme.
    """
    league = await _seed(session)
    await apply(session)
    assert await next_gameweek_number(session, league.id, date(2026, 9, 5)) == 5


async def test_a_missing_round_stops_the_run_naming_the_date(session: AsyncSession) -> None:
    """A season that reads 1, 2, 4 is worse than a run that refuses.

    The message carries the date because the fix is manual — somebody has to work out why
    that Saturday is not there before deciding what to do about it.
    """
    league = await _seed(
        session,
        numbers={date(2026, 8, 8): None, date(2026, 8, 22): 1, date(2026, 8, 29): 2},
    )
    with pytest.raises(BackfillError, match="2026-08-15"):
        await plan(session)
    assert await _numbers(session, league) == [
        (date(2026, 8, 8), None),
        (date(2026, 8, 22), 1),
        (date(2026, 8, 29), 2),
    ]


# ── The renames ────────────────────────────────────────────────────────────────


async def test_the_three_members_are_renamed(session: AsyncSession) -> None:
    await _seed(session)
    await apply(session)
    names = await _names(session)
    assert set(RENAMES.values()) <= names
    assert not set(RENAMES) & names, "an old name is still held by somebody"


async def test_a_target_name_already_taken_aborts_the_whole_run(session: AsyncSession) -> None:
    """The renumbering is unrelated to the rename and must still not half-land.

    A stranger holding "Marc Birch" is not something this script may resolve — every
    alternative is the owner's decision, and ``display_name`` being the login identifier
    means guessing wrong locks somebody out of their account.
    """
    league = await _seed(session)
    session.add(
        Profile(
            display_name="Marc Birch",
            pin_hash=hash_pin("8351"),
            role=UserRole.player,
        )
    )
    await session.flush()

    with pytest.raises(BackfillError, match="already held"):
        await apply(session)

    assert await _numbers(session, league) == [
        (date(2026, 8, 8), None),
        (date(2026, 8, 15), None),
        (date(2026, 8, 22), 1),
        (date(2026, 8, 29), 2),
    ]
    assert "Craig" in await _names(session), "a rename landed despite the abort"


async def test_a_target_name_held_case_differently_also_aborts(session: AsyncSession) -> None:
    """``auth.py:436`` reserves names case-insensitively, so this must match that.

    "marc birch" and "Marc Birch" are one person twice on a leaderboard, which is the
    impersonation that check exists to prevent — and renaming onto it would create exactly
    the pair the database's own constraint cannot see.
    """
    await _seed(session)
    session.add(Profile(display_name="marc birch", pin_hash=hash_pin("8351"), role=UserRole.player))
    await session.flush()
    with pytest.raises(BackfillError, match="already held"):
        await apply(session)


async def test_a_name_matching_nothing_stops_the_run(session: AsyncSession) -> None:
    """Neither the old name nor the new one resolves, so there is nothing to rename.

    Silently skipping would leave the owner believing three people were renamed when two
    were, and the one that failed is the one nobody would check.
    """
    league = await _seed(session)
    craig = (
        await session.execute(select(Profile).where(Profile.display_name == "Craig"))
    ).scalar_one()
    craig.display_name = "Someone Else Entirely"
    await session.flush()

    with pytest.raises(BackfillError, match="neither"):
        await plan(session)
    assert await _numbers(session, league) == [
        (date(2026, 8, 8), None),
        (date(2026, 8, 15), None),
        (date(2026, 8, 22), 1),
        (date(2026, 8, 29), 2),
    ]


# ── Running it twice ───────────────────────────────────────────────────────────


async def test_running_it_twice_changes_nothing_the_second_time(session: AsyncSession) -> None:
    """A backfill that gets interrupted gets run again, so this is the realistic case.

    The second run is what proves the renames resolve through the *new* name: matching
    only the old one would raise "neither matches any profile" here, on data that is
    already exactly right.
    """
    league = await _seed(session)
    await apply(session)
    after_first = (await _numbers(session, league), await _names(session))

    rounds, names = await apply(session)
    assert (await _numbers(session, league), await _names(session)) == after_first
    assert not any(change.changing for change in rounds), "a round was rewritten twice"
    assert not any(change.changing for change in names), "a name was rewritten twice"


async def test_a_dry_run_writes_nothing(session: AsyncSession) -> None:
    league = await _seed(session)
    rounds, names = await plan(session)

    assert [change.now for change in rounds] == [1, 2, 3, 4]
    assert {change.now for change in names} == set(RENAMES.values())
    assert await _numbers(session, league) == [
        (date(2026, 8, 8), None),
        (date(2026, 8, 15), None),
        (date(2026, 8, 22), 1),
        (date(2026, 8, 29), 2),
    ]
    assert set(RENAMES) <= await _names(session), "a dry run renamed somebody"
