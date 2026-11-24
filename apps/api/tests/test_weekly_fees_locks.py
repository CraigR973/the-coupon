"""Batch 240: the every-minute dues pass takes the league lock only when it has work.

`run_weekly_dues` held each two-game league's financial lock (advisory key 220) for its
whole walk of every member, every minute, so a save that coincided waited for it. These
tests hold that lock in another session: an empty pass must finish regardless, and a pass
that owes someone money must still wait for the lock and then write it.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import event, func, select, text

from src.models.two_game import MembershipInterval
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import _bill_league, billing_bounds
from tests import test_weekly_fees as fees

committed = fees.committed
W1, W2, W3 = fees.W1, fees.W2, fees.W3

LEAGUE_LOCK = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))")


async def labels(sessions, league, player):
    async with sessions() as db:
        return [row.week_label for row in await fees.dues(db, league, player)]


@pytest.mark.asyncio
async def test_an_empty_dues_pass_completes_while_another_session_holds_the_league_lock(
    committed, db_engine
):
    sessions, league, player, *_ = committed
    now = london_utc(W2, 12)
    # The first pass records the member's interval and the W1 and W2 dues it owes.
    assert await _bill_league(sessions, league.id, now) == 2
    seen: list[str] = []

    def count(_conn, _cursor, statement, *_args):
        seen.append(statement)

    async with sessions() as held, held.begin():
        await held.execute(LEAGUE_LOCK, {"key": str(league.id)})
        event.listen(db_engine.sync_engine, "before_cursor_execute", count)
        try:
            assert await asyncio.wait_for(_bill_league(sessions, league.id, now), timeout=5) == 0
        finally:
            event.remove(db_engine.sync_engine, "before_cursor_execute", count)
    assert not any("pg_advisory" in statement for statement in seen)
    assert await labels(sessions, league, player) == [W1, W2]


@pytest.mark.asyncio
async def test_a_member_owed_a_new_week_still_gets_it_after_waiting_for_the_lock(committed):
    sessions, league, player, *_ = committed
    assert await _bill_league(sessions, league.id, london_utc(W2, 12)) == 2
    # Monday 00:00 London starts the W3 billing week: the member now owes it.
    monday = billing_bounds(W3)[0]
    async with sessions() as held, held.begin():
        await held.execute(LEAGUE_LOCK, {"key": str(league.id)})
        pending = asyncio.create_task(_bill_league(sessions, league.id, monday))
        await asyncio.sleep(0.5)
        assert not pending.done()
    assert await asyncio.wait_for(pending, timeout=10) == 1
    assert await labels(sessions, league, player) == [W1, W2, W3]


@pytest.mark.asyncio
async def test_a_member_with_no_interval_yet_waits_for_the_lock_and_is_recorded(committed):
    sessions, league, player, *_ = committed
    async with sessions() as held, held.begin():
        await held.execute(LEAGUE_LOCK, {"key": str(league.id)})
        pending = asyncio.create_task(_bill_league(sessions, league.id, london_utc(W2, 12)))
        await asyncio.sleep(0.5)
        assert not pending.done()
    assert await asyncio.wait_for(pending, timeout=10) == 2
    async with sessions() as db:
        recorded = await db.scalar(
            select(func.count())
            .select_from(MembershipInterval)
            .where(
                MembershipInterval.league_id == league.id,
                MembershipInterval.player_id == player.id,
                MembershipInterval.left_at.is_(None),
            )
        )
    assert recorded == 1
    assert await labels(sessions, league, player) == [W1, W2]
