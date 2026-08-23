"""Batch 72 — live scores while the round is being played.

The only item on the post-launch list that is an enhancement rather than a defect, and
the one with the most ways to be quietly wrong. Three properties carry it.

**A live score never writes to ``picks``.** Settlement has one authority — the odds
provider, through ``settle_gameweek`` — and a second source that moved ``Pick.status``
would be a member watching points awarded and then withdrawn. Asserted by snapshotting
every pick row around a poll and comparing it back.

**Polling stops when nothing is being played.** A Tuesday morning must cost zero upstream
requests, not "a request that returns nothing".

**A competition the source does not carry renders the round without scores.** The port's
default answer is "I don't know", and that has to reach the screen as an absent scoreline
rather than an error.

Postgres-backed; each test rolls back — but other modules in the suite **commit**, and
the poll is deliberately global (every league's in-play round, not one league's). So every
assertion here is scoped to the competition slug this test made, rather than to "nothing
at all": another module's committed round being in play at the same time is a property of
the suite, not a defect in the job.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
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
from src.models.match import Match
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.coupon import build_coupon
from src.services.football_provider import (
    CompetitionKey,
    FootballDataProvider,
    LeagueTable,
    MatchResult,
    TeamRef,
)
from src.services.live_scores import competitions_in_play, poll_live_scores

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

SEASON = 2026


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


class _Silent(FootballDataProvider):
    """A source that carries nothing — the port's own "I don't know" default.

    FotMob carries neither NI Championship 1 nor the English non-league tiers, so this is
    not a hypothetical: it is what several divisions answer every week.
    """

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def close(self) -> None:  # pragma: no cover — nothing to release
        return None

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        return None

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        return []

    async def fetch_live_scores(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        self.asked.append(competition.slug)
        return await super().fetch_live_scores(competition, season)


class _Live(_Silent):
    """A source with one match in progress in *one* competition, at the score it is at.

    Scoped to a slug because the poll is global: the suite commits rounds from other
    modules, so a fake that answered for every competition it was asked about would
    invent a live match in each of them.
    """

    def __init__(self, slug: str, home: str, away: str, score: tuple[int, int]) -> None:
        super().__init__()
        self.slug = slug
        self.home, self.away, self.score = home, away, score

    async def fetch_live_scores(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        self.asked.append(competition.slug)
        if competition.slug != self.slug:
            return []
        return [
            MatchResult(
                provider_match_id=f"live-{uuid.uuid4().hex[:8]}",
                competition=competition,
                season=season,
                kickoff_utc=_now() - timedelta(minutes=50),
                home=TeamRef(provider_team_id=f"t-{self.home}", name=self.home),
                away=TeamRef(provider_team_id=f"t-{self.away}", name=self.away),
                home_goals=self.score[0],
                away_goals=self.score[1],
                finished=False,
                status="HT",
            )
        ]


class _Exploding(_Silent):
    async def fetch_live_scores(
        self, competition: CompetitionKey, season: int
    ) -> list[MatchResult]:
        self.asked.append(competition.slug)
        raise RuntimeError("fotmob is having a bad afternoon")


async def _round_in_play(
    db: AsyncSession, *, locked_ago: timedelta = timedelta(minutes=50)
) -> tuple[League, Gameweek, Fixture, Pick, Profile]:
    """A league whose round locked recently, with one pending pick on one fixture."""
    tag = uuid.uuid4().hex[:8]
    member = Profile(display_name=f"live-{tag}", pin_hash=hash_pin("8351"), role=UserRole.player)
    db.add(member)
    await db.flush()
    league = League(slug=f"live-{tag}", name=f"Live {tag}", created_by=member.id)
    db.add(league)
    await db.flush()
    db.add(LeagueMembership(league_id=league.id, player_id=member.id))
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=date(2027, 3, 6),
        status=GameweekStatus.locked,
        locks_at_utc=_now() - locked_ago,
    )
    fixture = Fixture(
        provider_event_id=f"ev-{tag}",
        home="Forfar Athletic",
        away="Brechin City",
        kickoff_utc=_now() - timedelta(minutes=45),
        competition="Scottish League Two",
        competition_id=f"sl2-{tag}",
    )
    db.add_all([gameweek, fixture])
    await db.flush()
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    pick = Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        player_id=member.id,
        fixture_id=fixture.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name="Forfar Athletic",
        odds_at_pick=Decimal("2.50"),
        status=PickStatus.pending,
    )
    db.add(pick)
    await db.flush()
    return league, gameweek, fixture, pick, member


async def _pick_rows(db: AsyncSession) -> list[tuple[uuid.UUID, str, int | None]]:
    rows = (await db.execute(select(Pick))).scalars().all()
    return sorted((p.id, p.status.value, p.points_awarded) for p in rows)


# ── The rule the whole feature is bounded by ──────────────────────────────────


async def test_a_live_score_never_writes_to_picks(session: AsyncSession) -> None:
    """Two authorities on one fact is the failure this must not have.

    FotMob may say what the score is; only ``EventSettlement`` says what a pick did. A
    member's pick is on the very match being polled, and it is untouched.
    """
    _, _, fixture, pick, _ = await _round_in_play(session)
    before = await _pick_rows(session)

    sweep = await poll_live_scores(
        session,
        _Live(fixture.competition_id, "Forfar Athletic", "Brechin City", (2, 0)),
        season=SEASON,
        now=_now(),
        limit=50,
    )

    assert sweep.matches_updated >= 1, "the poll did do something"
    assert await _pick_rows(session) == before
    stored = (await session.execute(select(Pick).where(Pick.id == pick.id))).scalar_one()
    assert stored.status is PickStatus.pending
    assert stored.points_awarded is None


async def test_a_live_score_is_stored_unfinished(session: AsyncSession) -> None:
    """``finished`` is the gate every other read uses, and a running score must not pass it.

    The results screen, the form line and Batch 67's settled scorelines all filter on it,
    so a half-time score that stored as finished would be printed as a result in three
    places at once.
    """
    _, _, fixture, _, _ = await _round_in_play(session)

    await poll_live_scores(
        session,
        _Live(fixture.competition_id, "Forfar Athletic", "Brechin City", (1, 1)),
        season=SEASON,
        now=_now(),
        limit=50,
    )

    match = (
        (await session.execute(select(Match).where(Match.competition_id == fixture.competition_id)))
        .scalars()
        .one()
    )
    assert match.finished is False
    assert (match.home_goals, match.away_goals) == (1, 1)


# ── Polling stops when nothing is on ──────────────────────────────────────────


async def test_polling_makes_no_request_when_no_league_has_a_round_in_play(
    session: AsyncSession,
) -> None:
    """Most hours of most weeks. The quiet case has to cost zero, not "return nothing"."""
    _, gameweek, fixture, _, _ = await _round_in_play(session)
    gameweek.status = GameweekStatus.settled
    gameweek.settled_at = _now()
    await session.flush()
    provider = _Live(fixture.competition_id, "Forfar Athletic", "Brechin City", (2, 0))

    await poll_live_scores(session, provider, season=SEASON, now=_now(), limit=50)

    assert fixture.competition_id not in provider.asked, "a settled round is not being played"


async def test_a_round_that_never_settles_stops_being_polled(session: AsyncSession) -> None:
    """Batch 65's bound, doing a second job.

    Batch 64's phantom Premiership round sat locked and unsettled because the provider
    never resolved it. Without the grace this poll inherits from `in_play`, that round
    would have kept a competition being fetched every ten minutes until May.
    """
    _, _, fixture, _, _ = await _round_in_play(session, locked_ago=timedelta(days=5))
    provider = _Live(fixture.competition_id, "Forfar Athletic", "Brechin City", (2, 0))

    await poll_live_scores(session, provider, season=SEASON, now=_now(), limit=50)

    assert fixture.competition_id not in provider.asked


async def test_a_round_being_played_names_its_own_competitions(session: AsyncSession) -> None:
    """Bounded to what is actually on, rather than sweeping the pool."""
    _, gameweek, fixture, _, _ = await _round_in_play(session)

    rounds, competitions = await competitions_in_play(session, _now())

    assert gameweek.id in rounds
    assert fixture.competition_id in {c.slug for c in competitions}


# ── A source that cannot answer ───────────────────────────────────────────────


async def test_a_competition_the_source_does_not_carry_renders_without_scores(
    session: AsyncSession,
) -> None:
    """FotMob carries neither NI Championship 1 nor the English non-league tiers.

    The port's default is "I don't know", and it has to reach the coupon as an absent
    scoreline rather than an error or a nil-nil.
    """
    league, gameweek, fixture, _, _ = await _round_in_play(session)
    provider = _Silent()

    await poll_live_scores(session, provider, season=SEASON, now=_now(), limit=50)
    coupon = await build_coupon(session, league.id, gameweek)

    assert fixture.competition_id in provider.asked, "it was asked"
    assert coupon.legs[0].home_goals is None
    assert coupon.legs[0].away_goals is None


async def test_a_source_that_fails_costs_the_round_its_scores_and_nothing_else(
    session: AsyncSession,
) -> None:
    """One division having a bad afternoon must not take the poll down with it."""
    league, gameweek, _, pick, _ = await _round_in_play(session)

    sweep = await poll_live_scores(session, _Exploding(), season=SEASON, now=_now(), limit=50)
    coupon = await build_coupon(session, league.id, gameweek)

    assert sweep.unavailable and sweep.matches_updated == 0
    assert coupon.legs[0].home_goals is None
    stored = (await session.execute(select(Pick).where(Pick.id == pick.id))).scalar_one()
    assert stored.status is PickStatus.pending


# ── What the coupon does with it ──────────────────────────────────────────────


async def test_an_in_play_round_shows_the_score_marked_as_not_final(
    session: AsyncSession,
) -> None:
    """A running score and a result are different things, and the leg says which it is."""
    league, gameweek, fixture, _, _ = await _round_in_play(session)
    await poll_live_scores(
        session,
        _Live(fixture.competition_id, "Forfar Athletic", "Brechin City", (2, 1)),
        season=SEASON,
        now=_now(),
        limit=50,
    )

    coupon = await build_coupon(session, league.id, gameweek)

    leg = coupon.legs[0]
    assert (leg.home_goals, leg.away_goals) == (2, 1)
    assert leg.score_is_final is False, "2-1 at half time is not 2-1 at full time"
    assert leg.status == "pending", "and the pick has still not done anything"


async def test_a_round_that_has_not_locked_shows_no_score_at_all(
    session: AsyncSession,
) -> None:
    """Before the deadline there is nothing being played, whatever `matches` holds."""
    league, gameweek, _, _, _ = await _round_in_play(session)
    gameweek.status = GameweekStatus.open
    gameweek.locks_at_utc = _now() + timedelta(hours=3)
    await session.flush()

    coupon = await build_coupon(session, league.id, gameweek)

    assert coupon.legs[0].home_goals is None
