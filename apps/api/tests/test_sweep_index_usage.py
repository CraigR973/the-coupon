"""Batch 146 — the round sweeps read an index instead of the whole table.

Two reads had nothing they could use. Stranded-round retirement and discovery range over
``gameweeks.starts_on``, which carried no index: the unique constraint on
``(league_id, starts_on)`` is left-anchored on the league and cannot serve a date range
across every league. And the settle sweep, together with retirement's "has anyone picked
on this round?" existence check, filters ``picks`` by ``gameweek_id`` alone, where
``ix_picks_league_gameweek`` is left-anchored on ``league_id`` — and a round belongs to
exactly one league since Batch 14, so those reads have no league to hand it.

**These tests only mean anything at a shape production has not reached.** At 87 picks and
24 gameweeks (measured 2026-09-23) PostgreSQL will sequentially scan whichever way the
indexes are defined, correctly, because reading the whole table is cheaper than an index
lookup on a page or two. So each test seeds thousands of rows and asks the planner. That
is the point of the batch: the indexes are invisible today and are the first thing to
matter as rounds accumulate.

Everything here **rolls back**. Twenty thousand committed picks would slow every other
test in the suite and corrupt every deployment-wide count it takes.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: Enough rows that an index lookup beats reading the table. Production is three orders of
#: magnitude below this; the review's stress shape is what this approximates.
ROUNDS = 6_000
PICKS = 20_000


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _stress_shape(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Thousands of rounds and picks, inserted in bulk and never committed.

    Returns one league id and one gameweek id to filter on. Written as SQL rather than ORM
    objects because twenty thousand hydrated `Pick`s would take longer than the rest of
    the suite put together, and nothing here reads them back as objects.
    """
    tag = uuid.uuid4().hex[:8]
    player = (
        await db.execute(
            text(
                "insert into profiles (id, display_name, pin_hash, role) "
                "values (gen_random_uuid(), :name, 'x', 'player') returning id"
            ),
            {"name": f"b146-{tag}"},
        )
    ).scalar_one()
    league = (
        await db.execute(
            text(
                "insert into leagues (id, slug, name, created_by) "
                "values (gen_random_uuid(), :slug, :name, :by) returning id"
            ),
            {"slug": f"b146-{tag}", "name": f"B146 {tag}", "by": player},
        )
    ).scalar_one()
    fixture = (
        await db.execute(
            text(
                "insert into fixtures (id, provider_event_id, home, away, kickoff_utc, "
                "competition, competition_id) values (gen_random_uuid(), :ev, 'H', 'A', "
                ":ko, 'Test', 'test-div') returning id"
            ),
            {"ev": f"b146-{tag}", "ko": _now()},
        )
    ).scalar_one()

    # Rounds spread across many dates, which is what makes a date range selective.
    first = date(2040, 7, 1)
    await db.execute(
        text(
            "insert into gameweeks (id, league_id, starts_on, status, locks_at_utc) "
            "select gen_random_uuid(), :league, (cast(:first as date) + n), "
            "'settled', :locks from generate_series(0, :n) as n"
        ),
        {"league": league, "first": first, "locks": _now(), "n": ROUNDS},
    )
    gameweek = (
        await db.execute(
            text("select id from gameweeks where league_id = :league limit 1"), {"league": league}
        )
    ).scalar_one()
    await db.execute(
        text(
            "insert into picks (id, league_id, gameweek_id, fixture_id, player_id, market, "
            "outcome, runner_name, odds_at_pick, status) "
            "select gen_random_uuid(), :league, g.id, :fixture, :player, 'MATCH_ODDS', "
            "'HOME', 'H', 2.0, 'pending' from ("
            "  select id from gameweeks where league_id = :league limit :n"
            ") as g"
        ),
        {"league": league, "fixture": fixture, "player": player, "n": PICKS},
    )
    # Without fresh statistics the planner still believes these tables hold a handful of
    # rows and will sequentially scan whatever exists. ANALYZE inside the transaction sees
    # the uncommitted rows.
    await db.execute(text("analyze gameweeks"))
    await db.execute(text("analyze picks"))
    return league, gameweek


async def _plan(db: AsyncSession, sql: str, params: dict) -> str:
    rows = (await db.execute(text(f"explain (analyze, buffers) {sql}"), params)).scalars().all()
    return "\n".join(rows)


async def test_a_date_range_over_rounds_uses_an_index_rather_than_the_whole_table(
    session: AsyncSession,
) -> None:
    """What retirement and discovery do: range over `starts_on`, across every league.

    The left-anchored unique constraint cannot serve this. Before Batch 146 nothing could.
    """
    _league, _gameweek = await _stress_shape(session)
    first = date(2040, 8, 1)

    plan = await _plan(
        session,
        "select id from gameweeks where starts_on >= :a and starts_on <= :b",
        {"a": first, "b": first + timedelta(days=14)},
    )

    assert "ix_gameweeks_starts_on" in plan, f"the date range is not using the index:\n{plan}"
    assert "Seq Scan on gameweeks" not in plan, f"still reading the whole table:\n{plan}"


async def test_the_pick_existence_check_uses_an_index_rather_than_the_whole_table(
    session: AsyncSession,
) -> None:
    """Retirement's "has anyone picked on this round?" and the settle sweep.

    Filtered by `gameweek_id` alone, which `ix_picks_league_gameweek` cannot serve.
    """
    _league, gameweek = await _stress_shape(session)

    plan = await _plan(
        session,
        "select exists (select 1 from picks where gameweek_id = :g)",
        {"g": gameweek},
    )

    assert "ix_picks_gameweek_id" in plan, f"the existence check is not using the index:\n{plan}"
    assert "Seq Scan on picks" not in plan, f"still reading the whole table:\n{plan}"


async def test_the_league_scoped_pick_read_still_uses_the_composite_it_always_did(
    session: AsyncSession,
) -> None:
    """The new index must not steal work the composite serves better.

    A read that *does* know the league — the coupon build, `services/coupon.py` — should
    still take `ix_picks_league_gameweek`, which is narrower for that shape. An index that
    quietly becomes the planner's default for everything is a regression wearing a
    speed-up's clothes.
    """
    league, gameweek = await _stress_shape(session)

    plan = await _plan(
        session,
        "select id from picks where league_id = :l and gameweek_id = :g",
        {"l": league, "g": gameweek},
    )

    assert "Seq Scan on picks" not in plan, f"still reading the whole table:\n{plan}"
    assert "ix_picks_league_gameweek" in plan or "ix_picks_gameweek_id" in plan, plan
