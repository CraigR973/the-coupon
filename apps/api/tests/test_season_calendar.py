"""Batch 113 — one deployment calendar names every league's football week."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Collection, Sequence
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
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services.football_week import (
    UNDECLARED_SAME_WEEK_ROUND,
    UNDECLARED_SIBLING_ALREADY_SETTLED,
    WOULD_STRAND_KEPT_ROUND,
    new_round_refusal,
    settle_refusal,
)
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
    calendar_for,
    canonical_saturday,
    declare_extra_week,
    ensure_calendar_for_new_season,
    labels_for_dates,
    labels_for_gameweeks,
    move_anchor,
    reanchor_from_earliest_round,
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


# ── Batch 132: the two calendar guards ────────────────────────────────────────
#
# Both defects only exist once migration 025 ships, which is why this batch follows that
# shipment rather than preceding it.


async def test_declaring_an_extra_week_in_the_past_is_refused(session: AsyncSession) -> None:
    """A date nobody can still play is not a date to declare.

    `declare_extra_week` validated only the season and that the date was not already
    canonical, so a past Wednesday was accepted — and relabelled the week around it.
    """
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    await session.flush()

    with pytest.raises(ValueError, match="EXTRA_WEEK_IN_THE_PAST"):
        await declare_extra_week(session, 2026, date(2026, 8, 5), today=date(2026, 9, 23))


async def test_declaring_an_extra_week_in_a_settled_week_is_refused(
    session: AsyncSession,
) -> None:
    """The finding: it renamed an already settled, already picked round from 5 to 5b.

    Mirrors `move_anchor`'s `SEASON_ANCHOR_LOCKED`, narrowed to the one football week a
    declaration can relabel — a settled week elsewhere in the season is untouched by it.
    """
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    settled_saturday = date(2026, 9, 12)
    await _round(session, league, settled_saturday, status=GameweekStatus.settled)
    await session.flush()

    # The Wednesday of that same football week — the date that would relabel it.
    with pytest.raises(PermissionError, match="EXTRA_WEEK_LOCKED"):
        await declare_extra_week(session, 2026, date(2026, 9, 9), today=date(2026, 9, 1))


async def test_a_settled_week_elsewhere_does_not_block_a_future_declaration(
    session: AsyncSession,
) -> None:
    """The half that must not move: the lock is the week, not the season.

    Locking the whole season would refuse every declaration from the first settlement
    onward, which is most of the season and none of the harm.
    """
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    await _round(session, league, date(2026, 9, 12), status=GameweekStatus.settled)
    await session.flush()

    ahead = date(2026, 12, 23)
    calendar = await declare_extra_week(session, 2026, ahead, today=date(2026, 9, 23))

    assert ahead in calendar.extra_weeks


async def test_an_unsettled_future_week_is_still_declarable(session: AsyncSession) -> None:
    """The midweek fixture the feature exists for, with a live round beside it.

    Deliberately not Boxing Day: 26 December 2026 is a Saturday and therefore already
    canonical, which `EXTRA_WEEK_IS_ALREADY_CANONICAL` refuses for its own older reason.
    """
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    midweek = date(2026, 12, 29)
    assert midweek.weekday() != 5, "the date under test must not be a Saturday"
    await _round(session, league, date(2026, 12, 26), status=GameweekStatus.open)
    await session.flush()

    calendar = await declare_extra_week(session, 2026, midweek, today=date(2026, 12, 1))
    assert midweek in calendar.extra_weeks


async def test_the_anchor_is_the_earliest_saturday_whatever_the_discovery_order(
    session: AsyncSession,
) -> None:
    """The second finding: the anchor was whichever round discovery happened to write.

    A Friday league walked before a Saturday league left the anchor a week late and split
    week 1 into "1" and "1b". Which league a scheduler reaches first is not a fact about
    the season.

    Note this is about *discovery*, not about reading: `labels_for_gameweeks` still never
    moves an anchor, which `test_stored_anchor_survives_a_later_added_earlier_round`
    above holds.
    """
    # Season 2031, not 2026. `ensure_calendar_for_new_season` establishes an anchor only
    # for a season with no rounds at all, and `reanchor_from_earliest_round` refuses once
    # anything in the season has settled — both of which are deployment-wide reads, and
    # the full suite commits 2026 rounds (settled ones included) from other modules. A
    # season nothing else touches is the only way to drive this end to end.
    _, friday = await _league(session, weekday=4)
    _, saturday = await _league(session, weekday=5)
    provider = _Provider()

    # The Friday league is walked first. Its first round is 2031-08-08, whose canonical
    # Saturday is the 9th — a week later than the Saturday league's 2031-08-02.
    await discover_fixtures(session, provider, [friday], date(2031, 8, 4), 1)
    calendar = await calendar_for(session, 2031)
    assert calendar is not None
    late = calendar.week_one_anchor
    assert late == canonical_saturday(date(2031, 8, 8)), "the premise: it anchored late"

    await discover_fixtures(session, provider, [saturday], date(2031, 7, 28), 1)

    calendar = await calendar_for(session, 2031)
    assert calendar is not None
    assert calendar.week_one_anchor == date(2031, 8, 2), "the anchor did not come back"
    assert calendar.week_one_anchor < late


async def test_a_deleted_leagues_earlier_round_does_not_move_the_anchor(
    session: AsyncSession,
) -> None:
    _, live = await _league(session)
    _, deleted = await _league(session)
    deleted.deleted_at = datetime(2051, 8, 1)
    early = date(2051, 8, 3)
    later = early + timedelta(weeks=1)
    live_anchor = canonical_saturday(later)
    assert canonical_saturday(early) < live_anchor
    calendar = SeasonCalendar(season=2051, week_one_anchor=live_anchor, extra_weeks=[])
    session.add(calendar)
    await _round(session, deleted, early)
    await _round(session, live, later)
    await session.flush()

    assert await reanchor_from_earliest_round(session, 2051) is None
    assert calendar.week_one_anchor == live_anchor


async def test_a_deleted_leagues_date_does_not_add_a_suffix_to_a_live_week(
    session: AsyncSession,
) -> None:
    _, live = await _league(session)
    _, deleted = await _league(session)
    deleted.deleted_at = datetime(2052, 8, 1)
    early = date(2052, 8, 3)
    later = early + timedelta(weeks=1)
    session.add(
        SeasonCalendar(
            season=2052,
            week_one_anchor=canonical_saturday(later),
            extra_weeks=[],
        )
    )
    await _round(session, deleted, early)
    live_round = await _round(session, live, later)
    await session.flush()

    assert await labels_for_gameweeks(session, [live_round]) == {live_round.id: "1"}


async def test_a_deleted_leagues_settlement_does_not_block_a_live_reanchor(
    session: AsyncSession,
) -> None:
    _, live = await _league(session)
    _, deleted = await _league(session)
    deleted.deleted_at = datetime(2053, 8, 1)
    early = date(2053, 8, 2)
    later = early + timedelta(weeks=1)
    early_anchor = canonical_saturday(early)
    late_anchor = canonical_saturday(later)
    calendar = SeasonCalendar(season=2053, week_one_anchor=late_anchor, extra_weeks=[])
    session.add(calendar)
    await _round(session, live, early)
    await _round(session, deleted, later, status=GameweekStatus.settled)
    await session.flush()

    assert await reanchor_from_earliest_round(session, 2053) is calendar
    assert calendar.week_one_anchor == early_anchor


async def test_only_deleted_rounds_leave_a_new_season_empty_for_anchoring(
    session: AsyncSession,
) -> None:
    _, deleted = await _league(session)
    deleted.deleted_at = datetime(2054, 8, 1)
    await _round(session, deleted, date(2054, 8, 1))
    await session.flush()

    live_start = date(2054, 8, 8)
    calendar = await ensure_calendar_for_new_season(session, live_start)

    assert calendar is not None
    assert calendar.week_one_anchor == canonical_saturday(live_start)


async def test_the_anchor_never_moves_after_a_settlement(session: AsyncSession) -> None:
    """The same rule `move_anchor` enforces, applied to the automatic move.

    A settled week that changes number is worse than a week 1 that is late — the numbers
    are what members remember a season by.
    """
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 8), extra_weeks=[]))
    await _round(session, league, date(2026, 8, 8), status=GameweekStatus.settled)
    await _round(session, league, date(2026, 8, 1), number=2, status=GameweekStatus.open)
    await session.flush()

    assert await reanchor_from_earliest_round(session, 2026) is None
    calendar = await calendar_for(session, 2026)
    assert calendar is not None
    assert calendar.week_one_anchor == date(2026, 8, 8)


async def test_the_anchor_only_ever_moves_earlier(session: AsyncSession) -> None:
    """Moving it later renumbers every round downward, which is the opposite of a fix."""
    _, league = await _league(session)
    session.add(SeasonCalendar(season=2026, week_one_anchor=date(2026, 8, 1), extra_weeks=[]))
    await _round(session, league, date(2026, 8, 15))
    await session.flush()

    assert await reanchor_from_earliest_round(session, 2026) is None
    calendar = await calendar_for(session, 2026)
    assert calendar is not None
    assert calendar.week_one_anchor == date(2026, 8, 1)


# ── One round per league per football week (Batch 184) ───────────────────────


async def _league_rounds(db: AsyncSession, league: League) -> list[Gameweek]:
    rows = await db.execute(
        select(Gameweek).where(Gameweek.league_id == league.id).order_by(Gameweek.starts_on)
    )
    return list(rows.scalars().all())


async def _claim(db: AsyncSession, league: League, gameweek: Gameweek) -> Pick:
    """One member's pick on ``gameweek`` — what keeps a stray from being retired."""
    tag = uuid.uuid4().hex[:8]
    member = Profile(display_name=f"claim-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    day = gameweek.starts_on
    fixture = Fixture(
        provider_event_id=f"claim-{tag}",
        home="Forfar",
        away="Brechin",
        kickoff_utc=datetime(day.year, day.month, day.day, 14),
        competition="Played League",
        competition_id="played-league",
    )
    db.add_all([member, fixture])
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    pick = Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        fixture_id=fixture.id,
        player_id=member.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name="Forfar",
        odds_at_pick=Decimal("2.00"),
    )
    db.add(pick)
    await db.flush()
    return pick


async def test_a_mid_week_move_to_friday_keeps_the_picked_saturday_as_the_weeks_round(
    session: AsyncSession,
) -> None:
    """CORR-20's first reproduction: a Saturday league moves to Friday on the Wednesday.

    The Saturday round already holds a pick, so retirement keeps it — and discovery used
    to create the new Friday beside it. The guard then refused the Saturday at every
    sweep while it went on taking picks. Now the week is played on the round it already
    has: no Friday this week, the Friday cadence from the next, and the Saturday — the
    week's only round — is one the guard lets score.
    """
    _, league = await _league(session, weekday=5)
    session.add(SeasonCalendar(season=2055, week_one_anchor=date(2055, 8, 7), extra_weeks=[]))
    await session.flush()
    saturday = date(2055, 10, 2)
    friday = saturday - timedelta(days=1)
    wednesday = saturday - timedelta(days=3)
    provider = _Provider()

    await discover_fixtures(session, provider, [league], saturday - timedelta(days=5), 1)
    (kept,) = await _league_rounds(session, league)
    assert kept.starts_on == saturday
    await _claim(session, league, kept)

    league.slate_start_weekday = 4
    league.slate_end_weekday = 4
    await session.flush()
    await discover_fixtures(session, provider, [league], wednesday, 2)
    # The settings edit's own rebuild takes the same path, and refuses the same round.
    await populate_cadence_rounds(session, provider, league, wednesday, 2)

    rounds = await _league_rounds(session, league)
    assert [round_.starts_on for round_ in rounds] == [saturday, friday + timedelta(weeks=1)]
    assert await settle_refusal(session, kept) is None, "the week's only round scores"
    assert await labels_for_gameweeks(session, rounds) == {rounds[0].id: "9", rounds[1].id: "10"}


async def test_a_move_to_saturday_after_fridays_round_settled_adds_no_second_round(
    session: AsyncSession,
) -> None:
    """CORR-20's second reproduction: the Friday round settles, then the league moves.

    Discovery used to create that week's Saturday, labelled like the settled Friday and
    open for picks, which the guard then refused for ever because an undeclared sibling
    had already scored. Now the settled Friday stays the week's one round.
    """
    _, league = await _league(session, weekday=4)
    session.add(SeasonCalendar(season=2056, week_one_anchor=date(2056, 8, 5), extra_weeks=[]))
    await session.flush()
    saturday = date(2056, 10, 7)
    friday = saturday - timedelta(days=1)
    provider = _Provider()

    await discover_fixtures(session, provider, [league], friday - timedelta(days=4), 1)
    (played,) = await _league_rounds(session, league)
    assert played.starts_on == friday
    played.status = GameweekStatus.settled
    league.slate_start_weekday = 5
    league.slate_end_weekday = 5
    await session.flush()

    await discover_fixtures(session, provider, [league], friday, 2)

    rounds = await _league_rounds(session, league)
    assert [round_.starts_on for round_ in rounds] == [friday, saturday + timedelta(weeks=1)]
    assert await labels_for_gameweeks(session, rounds) == {rounds[0].id: "10", rounds[1].id: "11"}


async def test_a_new_round_is_refused_only_beside_an_undeclared_one(
    session: AsyncSession,
) -> None:
    """The guard's question, asked before the row exists — and Batch 113's extras untouched."""
    _, league = await _league(session, weekday=5)
    saturday = date(2057, 10, 6)
    extra_tuesday = saturday + timedelta(days=3)
    session.add(
        SeasonCalendar(season=2057, week_one_anchor=date(2057, 8, 4), extra_weeks=[extra_tuesday])
    )
    await _round(session, league, saturday, status=GameweekStatus.settled)
    kept_stray = saturday + timedelta(weeks=2, days=-1)
    settled_stray = saturday + timedelta(weeks=3, days=-1)
    await _round(session, league, kept_stray)
    await _round(session, league, settled_stray, status=GameweekStatus.settled)
    await session.flush()

    # A declared extra beside a settled cadence round is intentional on both sides.
    assert await new_round_refusal(session, league, extra_tuesday) is None
    assert await new_round_refusal(session, league, saturday + timedelta(weeks=1)) is None
    assert (
        await new_round_refusal(session, league, saturday + timedelta(weeks=2))
        == WOULD_STRAND_KEPT_ROUND
    )
    assert (
        await new_round_refusal(session, league, saturday + timedelta(weeks=3))
        == UNDECLARED_SIBLING_ALREADY_SETTLED
    )
    assert (
        await new_round_refusal(session, league, saturday - timedelta(days=1))
        == UNDECLARED_SAME_WEEK_ROUND
    )


async def test_a_leagues_second_round_in_one_week_takes_its_own_label(
    session: AsyncSession,
) -> None:
    """CORR-13: two rounds of one league in one week no longer both read "Gameweek 10".

    The earlier round keeps the week's label, so a settled round keeps the name members
    were told; the later one takes the next suffix. Another league's round on the same
    Saturday still shares the public number, which is what the calendar is for.
    """
    _, friday_league = await _league(session, weekday=4)
    _, saturday_league = await _league(session, weekday=5)
    session.add(SeasonCalendar(season=2058, week_one_anchor=date(2058, 8, 3), extra_weeks=[]))
    saturday = date(2058, 10, 5)
    friday = saturday - timedelta(days=1)
    current = await _round(session, friday_league, friday)
    stray = await _round(session, friday_league, saturday)
    elsewhere = await _round(session, saturday_league, saturday)
    played = await _round(
        session, saturday_league, friday + timedelta(weeks=1), status=GameweekStatus.settled
    )
    after_it = await _round(session, saturday_league, saturday + timedelta(weeks=1))
    await session.flush()

    assert await labels_for_gameweeks(session, [current, stray, elsewhere, played, after_it]) == {
        current.id: "10",
        stray.id: "10b",
        elsewhere.id: "10",
        played.id: "11",
        after_it.id: "11b",
    }
    # Labelling one round alone reads its league's week, not just the rows it was handed.
    assert await labels_for_gameweeks(session, [stray]) == {stray.id: "10b"}
