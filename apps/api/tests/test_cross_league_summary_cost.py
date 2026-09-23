"""Batch 144 — what the cross-league summary spends to label its rounds.

A public round label is derived from one stored anchor per season plus **every date that
season's rounds fall on, deployment-wide** — because the football week an anchor names is
shared across leagues. That read is the whole cost of labelling, and it does not vary
with which rounds are being labelled. Two consequences the code got wrong, and this file
pins:

* the summary labels **two** sets of rounds (this week's and last week's) and was paying
  the deployment-wide read twice for one request;
* the read selected whole ``Gameweek`` rows to look at one column of them, so it
  hydrated every round every league has ever played in order to collect a set of dates.

Each test owns a season no other test touches. That is not fussiness: these reads are
deployment-wide and the suite shares one database, so a count taken over "the season
being played" would be a count of whatever else the run has already committed.

Postgres-backed; these tests commit.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal, engine
from src.main import app
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services.season_calendar import SeasonLabels, season_bounds

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: One season per test, chosen well clear of any season the rest of the suite seeds.
PRODUCTION_SHAPE_SEASON = 2041
STRESS_SHAPE_SEASON = 2042
PROJECTION_SEASON = 2043


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def _auth(person: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(person.id, person.role)}"}


class Recorder:
    """Every SQL statement a block of work issues, so its cost can be counted."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def _flat(self, statement: str) -> str:
        return " ".join(statement.split()).upper()

    def matching(self, *needles: str) -> list[str]:
        return [s for s in self.statements if all(n.upper() in self._flat(s) for n in needles)]

    def season_calendar_reads(self) -> list[str]:
        return [s for s in self.matching("SELECT", "SEASON_CALENDARS")]

    def deployment_wide_date_reads(self) -> list[str]:
        """The label read: every date a season's rounds fall on, across all leagues."""
        return [
            s for s in self.matching("SELECT", "GAMEWEEKS.STARTS_ON") if "DISTINCT" in self._flat(s)
        ]


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    rec = Recorder()

    def record(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        rec.statements.append(statement)

    # The app's own sessions run on this engine; `.sync_engine` is the one the event
    # system listens on, and it is shared with the seeding session above.
    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        yield rec
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)


async def _member(db: AsyncSession, name: str) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, owner: Profile) -> League:
    league = League(
        slug=f"b144-{uuid.uuid4().hex[:8]}",
        name=f"B144 {uuid.uuid4().hex[:4]}",
        created_by=owner.id,
    )
    db.add(league)
    await db.flush()
    db.add(LeagueMembership(league_id=league.id, player_id=owner.id))
    await db.flush()
    return league


async def _calendar(db: AsyncSession, season: int) -> date:
    """Anchor week one on the season's first Saturday, and hand that Saturday back."""
    first_day, _ = season_bounds(season)
    anchor = first_day + timedelta(days=(5 - first_day.weekday()) % 7)
    db.add(SeasonCalendar(season=season, week_one_anchor=anchor, extra_weeks=[]))
    await db.flush()
    return anchor


async def _round(
    db: AsyncSession, league: League, starts_on: date, status: GameweekStatus
) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=status,
        locks_at_utc=_now() - timedelta(days=1),
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


async def _seed(db: AsyncSession, season: int, *, leagues: int, weeks: int) -> Profile:
    """`leagues` leagues each playing the same `weeks` Saturdays — production's shape.

    Rounds share dates across leagues, which is the whole reason a label is a deployment
    -wide idea. It is also what makes the distinct projection cheaper than the rows.
    """
    anchor = await _calendar(db, season)
    member = await _member(db, "member")
    for _ in range(leagues):
        league = await _league(db, member)
        for week in range(weeks):
            day = anchor + timedelta(weeks=week)
            await _round(db, league, day, GameweekStatus.settled)
        # One open round ahead of the settled run, so `current_round` has something to
        # label as well as `last_result` — the two call sites this batch shares.
        await _round(db, league, anchor + timedelta(weeks=weeks), GameweekStatus.open)
    await db.commit()
    return member


async def test_the_summary_resolves_its_round_labels_once_for_the_whole_request(
    session: AsyncSession, client: AsyncClient, recorder: Recorder
) -> None:
    """The finding: two call sites, two identical deployment-wide reads, one request.

    `_latest_rounds` and `_last_results` each labelled their own rounds, and a label
    costs one read of the season's calendar plus one of every date its rounds fall on.
    Nothing about those two reads depends on which rounds are being labelled, so the
    second pair was bought and thrown away.
    """
    member = await _seed(session, PRODUCTION_SHAPE_SEASON, leagues=1, weeks=6)
    recorder.statements.clear()

    response = await client.get("/api/v1/me/cross-league-summary", headers=_auth(member))

    assert response.status_code == 200
    entry = response.json()["per_league"][0]
    # Both call sites still label, so this is not "once" bought by labelling less.
    assert entry["current_round"]["season_week"] == "7"
    assert entry["last_result"]["season_week"] == "6"

    calendars = recorder.season_calendar_reads()
    dates = recorder.deployment_wide_date_reads()
    assert len(calendars) == 1, f"the season calendar was read {len(calendars)} times"
    assert len(dates) == 1, f"the deployment-wide date read ran {len(dates)} times"


async def test_the_label_read_does_not_grow_with_the_rounds_it_is_not_labelling(
    session: AsyncSession, client: AsyncClient, recorder: Recorder
) -> None:
    """The stress shape: five leagues, twelve weeks, same two reads as one league.

    The cost this batch removes is the one that scales with the deployment rather than
    with the response, so the measurement that matters is that a season with sixty-five
    rounds in it costs the same number of round trips as a season with seven.
    """
    member = await _seed(session, STRESS_SHAPE_SEASON, leagues=5, weeks=12)
    recorder.statements.clear()

    response = await client.get("/api/v1/me/cross-league-summary", headers=_auth(member))

    assert response.status_code == 200
    body = response.json()
    assert body["leagues_count"] == 5
    assert {entry["current_round"]["season_week"] for entry in body["per_league"]} == {"13"}

    assert len(recorder.season_calendar_reads()) == 1
    assert len(recorder.deployment_wide_date_reads()) == 1


async def test_the_label_read_asks_for_dates_rather_than_rounds(
    session: AsyncSession, recorder: Recorder
) -> None:
    """Row volume: a set of dates, not a hydrated round per league per week.

    Asserted on the statement rather than on a row count because that is where the saving
    lives — `SELECT DISTINCT gameweeks.starts_on` cannot return more rows than the season
    has distinct dates, however many leagues played them, and it never builds a
    ``Gameweek``. The old form selected the whole table.
    """
    member = await _seed(session, PROJECTION_SEASON, leagues=4, weeks=5)
    rounds = (
        await session.execute(
            Gameweek.__table__.select().where(
                Gameweek.starts_on >= season_bounds(PROJECTION_SEASON)[0],
                Gameweek.starts_on <= season_bounds(PROJECTION_SEASON)[1],
            )
        )
    ).all()
    assert len(rounds) == 24, "4 leagues x (5 settled + 1 open) — the rows the old read built"
    recorder.statements.clear()

    labels = await SeasonLabels().of(session, [row for row in rounds])

    assert len(labels) == 24, "every round is still labelled"
    assert set(labels.values()) == {"1", "2", "3", "4", "5", "6"}, "six distinct weeks"

    reads = recorder.deployment_wide_date_reads()
    assert len(reads) == 1
    flat = " ".join(reads[0].split()).upper()
    assert "GAMEWEEKS.ID" not in flat, f"the label read still hydrates whole rounds: {flat}"
    assert flat.count("GAMEWEEKS.") == 3, f"one projected column and two bounds: {flat}"
    assert member is not None
