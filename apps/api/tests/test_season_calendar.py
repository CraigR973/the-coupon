"""Batch 113 — one deployment calendar names every league's football week."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services.gameweek import (
    discover_fixtures,
    populate_cadence_rounds,
    retire_stranded_rounds,
    window_for,
)
from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    OddsProvider,
    Slate,
    SlateFixture,
    SlateWindow,
)
from src.services.season_calendar import (
    canonical_saturday,
    labels_for_dates,
    labels_for_gameweeks,
    move_anchor,
    withdraw_extra_week,
)

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


async def _league(
    db: AsyncSession,
    *,
    weekday: int = 5,
    competitions: list[dict[str, str]] | None = None,
) -> tuple[Profile, League]:
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"calendar-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    db.add(owner)
    await db.flush()
    league = League(
        slug=f"calendar-{tag}",
        name=f"Calendar {tag}",
        created_by=owner.id,
        slate_start_weekday=weekday,
        slate_end_weekday=weekday,
        competitions=competitions,
    )
    db.add(league)
    await db.flush()
    return owner, league


async def _round(
    db: AsyncSession,
    league: League,
    starts_on: date,
    *,
    number: int = 1,
    status: GameweekStatus = GameweekStatus.open,
) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        number=number,
        status=status,
        locks_at_utc=window_for(league).locks_at(starts_on),
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


class _Provider(OddsProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[SlateWindow, date]] = []

    async def login(self) -> str:
        return ""

    async def keep_alive(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        self.calls.append((window, starts_on))
        return Slate(
            starts_on=starts_on,
            fixtures=[
                SlateFixture(
                    provider_event_id=f"event-{window.start_weekday}-{starts_on}",
                    home="Forfar",
                    away="Brechin",
                    kickoff_utc=datetime(starts_on.year, starts_on.month, starts_on.day, 14),
                    competition="Played League",
                    competition_id="played-league",
                )
            ],
        )

    async def fetch_competitions(self) -> list[Competition]:
        return []

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        return []

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return []


def test_one_football_week_covers_wednesday_through_tuesday() -> None:
    calendar = SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[])
    days = {
        date(2026, 9, 2),  # Wednesday
        date(2026, 9, 4),  # Friday
        date(2026, 9, 5),  # Saturday
        date(2026, 9, 6),  # Sunday
        date(2026, 9, 8),  # Tuesday
    }
    assert set(labels_for_dates(calendar, days).values()) == {"5"}
    assert canonical_saturday(date(2027, 6, 30)) == date(2027, 7, 3)
    assert canonical_saturday(date(2027, 7, 1)) == date(2027, 7, 3)


def test_an_extra_date_gets_the_same_suffix_everywhere() -> None:
    calendar = SeasonCalendar(
        season=2026,
        week_one_anchor=date(2026, 8, 8),
        extra_weeks=[date(2026, 9, 6)],
    )
    labels = labels_for_dates(calendar, {date(2026, 9, 4), date(2026, 9, 5), date(2026, 9, 6)})
    assert labels == {
        date(2026, 9, 4): "5",
        date(2026, 9, 5): "5",
        date(2026, 9, 6): "5b",
    }


async def test_stored_anchor_survives_a_later_added_earlier_round(
    session: AsyncSession,
) -> None:
    _, league = await _league(session)
    calendar = SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[])
    session.add(calendar)
    later = await _round(session, league, date(2026, 8, 8))
    earlier = await _round(session, league, date(2026, 8, 1), number=2)

    labels = await labels_for_gameweeks(session, [earlier, later])
    assert calendar.week_one_anchor == date(2026, 8, 8)
    assert labels == {earlier.id: "1", later.id: "1b"}


async def test_anchor_move_is_refused_after_any_settlement(session: AsyncSession) -> None:
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    await _round(session, league, date(2026, 8, 8), status=GameweekStatus.settled)

    with pytest.raises(PermissionError, match="SEASON_ANCHOR_LOCKED"):
        await move_anchor(session, 2026, date(2026, 8, 15))


async def test_two_leagues_on_different_weekdays_share_the_public_number(
    session: AsyncSession,
) -> None:
    _, friday = await _league(session, weekday=4)
    _, saturday = await _league(session, weekday=5)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    friday_round = await _round(session, friday, date(2026, 9, 4), number=3)
    saturday_round = await _round(session, saturday, date(2026, 9, 5), number=5)

    assert await labels_for_gameweeks(session, [friday_round, saturday_round]) == {
        friday_round.id: "5",
        saturday_round.id: "5",
    }


async def test_discovery_materialises_an_extra_once_per_distinct_window(
    session: AsyncSession,
) -> None:
    _, saturday = await _league(session, weekday=5)
    _, saturday_excluded = await _league(
        session,
        weekday=5,
        competitions=[{"slug": "not-on-this-card", "name": "Not here"}],
    )
    _, friday = await _league(session, weekday=4)
    extra = date(2026, 8, 5)
    session.add(
        SeasonCalendar(
            season=2026,
            week_one_anchor=date(2026, 8, 8),
            extra_weeks=[extra],
        )
    )
    await session.flush()
    provider = _Provider()

    discovered = await discover_fixtures(
        session,
        provider,
        [saturday, saturday_excluded, friday],
        date(2026, 8, 2),
        1,
    )

    assert len([call for call in provider.calls if call[1] == extra]) == 2
    extra_rounds = {
        (round_.league_id, round_.starts_on) for round_ in discovered if round_.starts_on == extra
    }
    assert extra_rounds == {
        (saturday.id, extra),
        (friday.id, extra),
    }
    assert not any(
        round_.league_id == saturday_excluded.id and round_.starts_on == extra
        for round_ in discovered
    )


async def test_request_population_never_materialises_an_extra_week(
    session: AsyncSession,
) -> None:
    _, league = await _league(session)
    extra = date(2026, 8, 5)
    session.add(
        SeasonCalendar(
            season=2026,
            week_one_anchor=date(2026, 8, 8),
            extra_weeks=[extra],
        )
    )
    await session.flush()
    provider = _Provider()

    populated = await populate_cadence_rounds(session, provider, league, date(2026, 8, 2), 1)

    assert extra not in {round_.starts_on for round_ in populated.gameweeks}
    assert extra not in {call[1] for call in provider.calls}


async def test_declared_extra_is_kept_then_withdrawn_extra_is_retired(
    session: AsyncSession,
) -> None:
    _, league = await _league(session)
    extra = date(2026, 8, 5)
    calendar = SeasonCalendar(
        season=2026,
        week_one_anchor=date(2026, 8, 8),
        extra_weeks=[extra],
    )
    session.add(calendar)
    round_ = await _round(session, league, extra)

    assert await retire_stranded_rounds(session, league, date(2026, 8, 2), 1) == []
    calendar.extra_weeks = []
    await session.flush()
    assert await retire_stranded_rounds(session, league, date(2026, 8, 2), 1) == [extra]
    assert await session.get(Gameweek, round_.id) is None


async def test_withdrawal_is_refused_when_any_league_has_a_pick(
    session: AsyncSession,
) -> None:
    player, league = await _league(session)
    extra = date(2026, 8, 5)
    calendar = SeasonCalendar(
        season=2026,
        week_one_anchor=date(2026, 8, 8),
        extra_weeks=[extra],
    )
    session.add(calendar)
    gameweek = await _round(session, league, extra)
    fixture = Fixture(
        provider_event_id=f"picked-{uuid.uuid4().hex}",
        home="Forfar",
        away="Brechin",
        kickoff_utc=datetime(2026, 8, 5, 19, 45),
        competition="Played League",
        competition_id="played-league",
    )
    session.add(fixture)
    await session.flush()
    session.add(
        Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            fixture_id=fixture.id,
            player_id=player.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar",
            odds_at_pick=Decimal("2.00"),
        )
    )
    await session.flush()

    with pytest.raises(PermissionError, match="EXTRA_WEEK_HAS_PICKS"):
        await withdraw_extra_week(session, 2026, extra)
    assert calendar.extra_weeks == [extra]
