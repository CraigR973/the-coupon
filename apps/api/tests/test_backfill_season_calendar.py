"""Batch 113's season-calendar backfill is explicit, inspectable and idempotent."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.backfill_season_calendar import apply, plan
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

SEASON = 2040
ANCHOR = date(2040, 8, 4)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _seed_production_shape(db: AsyncSession) -> tuple[League, League, list[Gameweek]]:
    tag = uuid.uuid4().hex[:8]
    owner = Profile(
        display_name=f"backfill-calendar-{tag}",
        pin_hash=hash_pin("1234"),
        role=UserRole.player,
    )
    db.add(owner)
    await db.flush()
    hibs = League(slug=f"hibs-{tag}", name=f"2-1 Hibs {tag}", created_by=owner.id)
    mccann = League(slug=f"mccann-{tag}", name=f"McCann's Defenders {tag}", created_by=owner.id)
    db.add_all([hibs, mccann])
    await db.flush()

    rounds: list[Gameweek] = []
    for offset, number in enumerate(range(1, 6)):
        starts_on = ANCHOR + timedelta(weeks=offset)
        rounds.append(
            Gameweek(
                league_id=hibs.id,
                starts_on=starts_on,
                number=number,
                status=GameweekStatus.settled,
                locks_at_utc=datetime(starts_on.year, starts_on.month, starts_on.day, 13, 30),
            )
        )
    for starts_on, number in [
        (ANCHOR + timedelta(weeks=3), 2),
        (ANCHOR + timedelta(weeks=4), 3),
    ]:
        rounds.append(
            Gameweek(
                league_id=mccann.id,
                starts_on=starts_on,
                number=number,
                status=GameweekStatus.settled,
                locks_at_utc=datetime(starts_on.year, starts_on.month, starts_on.day, 13, 30),
            )
        )
    db.add_all(rounds)
    await db.flush()

    fixture = Fixture(
        provider_event_id=f"backfill-{tag}",
        home="Forfar",
        away="Brechin",
        kickoff_utc=datetime.combine(ANCHOR + timedelta(weeks=4), datetime.min.time()).replace(
            hour=14
        ),
        competition="League Two",
        competition_id="scotland-league-two",
    )
    db.add(fixture)
    await db.flush()
    db.add(
        Pick(
            league_id=mccann.id,
            gameweek_id=rounds[-1].id,
            fixture_id=fixture.id,
            player_id=owner.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar",
            odds_at_pick=Decimal("2.00"),
            status=PickStatus.won,
            points_awarded=20,
        )
    )
    await db.flush()
    return hibs, mccann, rounds


async def test_dry_run_names_only_the_two_visible_moves_and_writes_nothing(
    session: AsyncSession,
) -> None:
    hibs, mccann, rounds = await _seed_production_shape(session)
    before = {round_.id: round_.number for round_ in rounds}

    calendars, changes = await plan(session)

    calendar = next(change for change in calendars if change.season == SEASON)
    assert calendar.anchor == ANCHOR
    assert calendar.already_stored is False
    assert await session.get(SeasonCalendar, SEASON) is None
    moving = [
        change
        for change in changes
        if change.changing and change.league in {hibs.name, mccann.name}
    ]
    assert [(change.league, change.starts_on, change.was, change.now) for change in moving] == [
        (mccann.name, ANCHOR + timedelta(weeks=3), "2", "4"),
        (mccann.name, ANCHOR + timedelta(weeks=4), "3", "5"),
    ]
    assert {round_.id: round_.number for round_ in rounds} == before


async def test_apply_stores_only_the_calendar_even_for_a_settled_pick(
    session: AsyncSession,
) -> None:
    _hibs, _mccann, rounds = await _seed_production_shape(session)
    before = {round_.id: round_.number for round_ in rounds}

    await apply(session)

    calendar = await session.get(SeasonCalendar, SEASON)
    assert calendar is not None and calendar.week_one_anchor == ANCHOR
    assert {round_.id: round_.number for round_ in rounds} == before
    _calendars, second_plan = await plan(session)
    assert not any(
        change.changing for change in second_plan if change.starts_on.year in {2040, 2041}
    )
