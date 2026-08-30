"""Batch 68 — the two rounds played before the app was watching.

The data itself cannot be tested: whether Walesy really took Salford BTTS at 19/20 is a
question for the screenshot, not for pytest. What *can* be tested is everything around it,
and every one of these is a way this backfill could put a wrong number on a real member's
record without anyone noticing.

* **The prices are internally consistent.** The 8 August slip states its own return, so
  the twelve decimals must multiply back to it. That is the check that catches a
  fraction converted wrongly, which no amount of reading the screenshot again would.
* **Nothing is invented.** No pick carries a status or a score; both come from
  ``settle_gameweek`` against the stored FotMob scorelines, so ``points_awarded`` is
  recomputed rather than transcribed — the row's own verification requirement.
* **It fails closed.** An unknown member, an unresolvable fixture or a missing scoreline
  raises before anything is written.
* **It is idempotent**, because a backfill that half-lands gets run again.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.backfill_august_2026 import (
    KNOWN_SCORES,
    ROUND_08_AUG,
    ROUND_15_AUG,
    ROUND_22_AUG,
    ROUNDS,
    BackfillError,
    apply,
    plan,
)
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.match import Match
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.models.team import Team
from src.services.football_provider import season_for
from src.services.scoring import points_for, standings
from src.services.team_matching import normalise_name

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The slip's own arithmetic: £3.50 staked, £1,660.24 to return.
SLIP_08_STAKE = Decimal("3.50")
SLIP_08_RETURN = Decimal("1660.24")


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


# ── The prices, checked against the slip that quoted them ─────────────────────


#: The fractions bet365 quoted on the 8 August slip, in the order the slip lists them.
#: Kept here rather than in the module because they are the *evidence*; the module stores
#: what the product needs, which is decimals.
SLIP_08_FRACTIONS = [
    (19, 20),  # Salford BTTS
    (10, 11),  # Burton BTTS
    (7, 10),  # Leyton Orient BTTS
    (4, 6),  # Dundee BTTS
    (4, 6),  # St Mirren BTTS
    (8, 13),  # Airdrieonians BTTS
    (8, 11),  # Stranraer BTTS
    (4, 6),  # Stockport win
    (21, 50),  # Stoke win
    (19, 20),  # Stenhousemuir win
    (13, 20),  # Hamilton win
    (27, 100),  # Ross County win
]


def test_the_eight_august_fractions_multiply_back_to_the_slips_own_return() -> None:
    """The slip states its own return, so the twelve legs either reach it or they do not.

    Computed from the **fractions**, exactly, because that is what bet365 priced. The
    stored two-decimal values drift about 1.1% high over twelve legs — 4/6 becomes 1.67
    three times, 8/13 becomes 1.62 — so multiplying those would fail against a tolerance
    tight enough to catch a genuinely mis-read leg. The rounding is checked separately
    below.

    0.1% is bet365's rounding of its own quoted return. A single leg read wrong is a
    several-percent error and cannot hide inside it.
    """
    product = Fraction(1)
    for num, den in SLIP_08_FRACTIONS:
        product *= Fraction(num, den) + 1
    implied = Decimal(product.numerator) / Decimal(product.denominator) * SLIP_08_STAKE

    assert len(SLIP_08_FRACTIONS) == 12
    assert abs(implied - SLIP_08_RETURN) / SLIP_08_RETURN < Decimal(
        "0.001"
    ), f"twelve legs imply £{implied:.2f} against the slip's £{SLIP_08_RETURN}"


def test_each_stored_price_is_its_fraction_rounded_to_two_places() -> None:
    """The per-leg half of the same check.

    The product above would survive two errors that cancel; this will not. Together they
    say the fractions are the slip's *and* each decimal is the right conversion of one —
    which is the whole risk in transcribing a betting slip into a leaderboard.
    """
    stored = [pick.odds for pick in ROUND_08_AUG.picks]
    expected = [
        (Decimal(num) / Decimal(den) + 1).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for num, den in SLIP_08_FRACTIONS
    ]
    assert stored == expected


def test_every_price_is_attributed() -> None:
    """The row requires a written note of which odds are evidenced and which are not.

    That note is only honest if every price carries its source in the data rather than in
    prose somebody has to keep in step.
    """
    for round_ in ROUNDS:
        for pick in round_.picks:
            assert pick.evidence, f"{pick.member} on {round_.starts_on} has no attribution"


def test_the_two_undocumented_prices_are_the_ones_that_score_nothing() -> None:
    """Both 22 August additions lost, so neither price can move the leaderboard.

    This is why the round's undocumented odds were acceptable at all. If either pick had
    won, its price would set its points directly and the batch's own rule — no guessed
    odd — would have stopped it. Pinned so that a later edit cannot quietly turn an
    unevidenced price into a scoring one.
    """
    undocumented = [p for r in ROUNDS for p in r.picks if "owner" in p.evidence]
    assert {p.member for p in undocumented} == {"Lewis", "Josh Caldow"}
    assert all(p in ROUND_22_AUG.picks for p in undocumented)


def test_each_member_picks_once_per_round() -> None:
    """One claim per member per round is the game's rule and the table's constraint."""
    for round_ in ROUNDS:
        members = [p.member for p in round_.picks]
        assert len(members) == len(set(members)), f"{round_.starts_on} names someone twice"


def test_the_full_rounds_are_twelve_and_the_correction_is_two() -> None:
    assert len(ROUND_08_AUG.picks) == 12
    assert len(ROUND_15_AUG.picks) == 12
    assert len(ROUND_22_AUG.picks) == 2


# ── Against a database ────────────────────────────────────────────────────────


async def _fixture_and_score(
    db: AsyncSession,
    home: str,
    away: str,
    day: date,
    score: tuple[int, int],
    *,
    with_match: bool = True,
) -> Fixture:
    """A pooled fixture on ``day``, with a finished match carrying ``score`` unless asked
    otherwise — ``with_match=False`` is the competition no football source covers."""
    tag = uuid.uuid4().hex[:8]
    competition = f"bf-{tag}"
    kickoff = datetime(day.year, day.month, day.day, 14, 0)
    fixture = Fixture(
        provider_event_id=f"ev-{tag}",
        home=home,
        away=away,
        kickoff_utc=kickoff,
        competition="Backfill Division",
        competition_id=competition,
    )
    teams = []
    for name in (home, away):
        team = Team(
            provider_team_id=f"t-{uuid.uuid4().hex[:10]}",
            name=name,
            normalised_name=normalise_name(name),
            competition_id=competition,
        )
        db.add(team)
        teams.append(team)
    db.add(fixture)
    await db.flush()
    if not with_match:
        return fixture
    db.add(
        Match(
            provider_match_id=f"m-{uuid.uuid4().hex[:10]}",
            competition_id=competition,
            competition="Backfill Division",
            season=2026,
            kickoff_utc=kickoff,
            home_team_id=teams[0].id,
            away_team_id=teams[1].id,
            home_goals=score[0],
            away_goals=score[1],
            finished=True,
        )
    )
    await db.flush()
    return fixture


async def _stage(db: AsyncSession, scores: dict[tuple[str, str], tuple[int, int]]) -> League:
    """The 2-1 Hibs league, its members, and every fixture the backfill names.

    Built from the backfill's own tables rather than from a copy of them, so a pick added
    to the data is automatically staged here — a fixture list that drifts from the picks
    would make these tests pass while the real run failed.
    """
    from src.backfill_august_2026 import LEAGUE_SLUG

    owner = Profile(
        display_name=f"bf-owner-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
    )
    db.add(owner)
    await db.flush()
    league = League(slug=LEAGUE_SLUG, name="2-1 Hibs", created_by=owner.id)
    db.add(league)
    await db.flush()

    for member in {p.member for r in ROUNDS for p in r.picks}:
        profile = Profile(display_name=member, pin_hash=hash_pin("8351"), role=UserRole.player)
        db.add(profile)
        await db.flush()
        db.add(LeagueMembership(league_id=league.id, player_id=profile.id))
    await db.flush()

    for round_ in ROUNDS:
        for pick in round_.picks:
            # Faithful to production: a fixture in KNOWN_SCORES is one no football source
            # carries, so it gets a pooled fixture and *no* match row. Staging one would
            # test a world that does not exist and hide the fallback entirely.
            await _fixture_and_score(
                db,
                pick.home,
                pick.away,
                round_.starts_on,
                scores.get((pick.home, pick.away), (1, 1)),
                with_match=(pick.home, pick.away) not in KNOWN_SCORES,
            )
    return league


async def _picks_of(db: AsyncSession, league: League) -> list[tuple[uuid.UUID, str, int | None]]:
    """This league's picks, as a comparable snapshot.

    Scoped, because the suite is not hermetic: other modules commit their own leagues and
    rounds, so an unscoped count here passes alone and fails in a full run.
    """
    rows = (await db.execute(select(Pick).where(Pick.league_id == league.id))).scalars().all()
    return sorted((p.id, p.status.value, p.points_awarded) for p in rows)


async def test_a_dry_run_resolves_everything_and_writes_nothing(session: AsyncSession) -> None:
    """The thing reviewed before the write is the thing the write performs."""
    league = await _stage(session, {})

    plans = await plan(session)

    assert [p.starts_on for p in plans] == [r.starts_on for r in ROUNDS]
    assert sum(len(p.to_insert) for p in plans) == 26  # 12 + 12 + 2
    # Scoped to this league. Other modules in the suite commit picks and rounds of their
    # own, so "nothing exists anywhere" is not a claim this test can make.
    assert await _picks_of(session, league) == []
    rounds = (
        (await session.execute(select(Gameweek).where(Gameweek.league_id == league.id)))
        .scalars()
        .all()
    )
    assert rounds == []


async def test_the_backfill_settles_from_stored_scores_rather_than_asserting_outcomes(
    session: AsyncSession,
) -> None:
    """The row's verification: points recomputed, never transcribed.

    Every pick here is BTTS Yes or a home win into a staged 1-1, so every one of them
    should win — and each should carry exactly ``points_for(odds)``, computed by the same
    ``settle_gameweek`` the evening sweep runs.
    """
    league = await _stage(session, {})

    await apply(session)

    rows = (
        await session.execute(
            select(Pick, Fixture)
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(Pick.league_id == league.id)
        )
    ).all()
    assert len(rows) == 26
    for pick, _ in rows:
        assert pick.status is not PickStatus.pending, "nothing may be left hanging"
        if pick.status is PickStatus.won:
            assert pick.points_awarded == points_for(pick.odds_at_pick)
        else:
            assert pick.points_awarded == 0

    # Every fixture the store answers for is staged 1-1, so its BTTS Yes wins. The one
    # fixture no source carries is settled from its stated 3-0 and therefore loses. Both
    # halves are decided by a *scoreline*, which is the property under test — the backfill
    # asserts no outcome of its own.
    from_store = [
        p
        for p, f in rows
        if p.market is PickMarket.BOTH_TEAMS_TO_SCORE and (f.home, f.away) not in KNOWN_SCORES
    ]
    assert from_store and all(p.status is PickStatus.won for p in from_store)

    stated = [p for p, f in rows if (f.home, f.away) in KNOWN_SCORES]
    assert stated and all(p.status is PickStatus.lost for p in stated)

    # These rounds are August 2026 by definition — that is what the backfill is — so the
    # table is read for that season rather than for today's (Batch 96).
    table = await standings(session, league.id, season=season_for(date(2026, 8, 1)))
    by_name = {s.display_name: s for s in table}
    # Everyone played both backfilled rounds; only the two 22 August additions have a
    # third. That asymmetry is the check that the correction landed on the right people.
    assert by_name["Adam wales"].picks_played == 2, "the two backfilled rounds"
    assert by_name["Lewis"].picks_played == 3, "plus the 22 August pick that was missing"
    assert by_name["Josh Caldow"].picks_played == 3


async def test_a_backfilled_round_lands_settled_with_its_real_instants(
    session: AsyncSession,
) -> None:
    """Created at the league's own lock, not at the moment the script happened to run."""
    league = await _stage(session, {})
    from src.services.gameweek import window_for

    await apply(session)

    rounds = (
        (
            await session.execute(
                select(Gameweek).where(Gameweek.league_id == league.id).order_by(Gameweek.starts_on)
            )
        )
        .scalars()
        .all()
    )
    assert [r.starts_on for r in rounds] == [date(2026, 8, 8), date(2026, 8, 15), date(2026, 8, 22)]
    for round_ in rounds:
        assert round_.status is GameweekStatus.settled
        assert round_.settled_at is not None
        assert round_.locks_at_utc == window_for(league).locks_at(round_.starts_on)
        # Deliberately unnamed: numbering these would put a later number on an earlier
        # date, and renumbering 22 August would rewrite a name members have used.
        assert round_.number is None


async def test_running_it_twice_changes_nothing(session: AsyncSession) -> None:
    """A backfill that half-lands gets run again, so the second run must be a no-op."""
    league = await _stage(session, {})
    await apply(session)
    first = await _picks_of(session, league)

    plans = await apply(session)

    assert sum(len(p.to_insert) for p in plans) == 0
    assert sum(len(p.already_present) for p in plans) == 26
    assert await _picks_of(session, league) == first


async def test_it_leaves_picks_that_are_already_recorded_alone(session: AsyncSession) -> None:
    """22 August already holds ten picks in production; the backfill adds two.

    An existing pick must not be touched, re-priced or re-settled — those ten were made
    in the app and are the record.
    """
    league = await _stage(session, {})
    lewis = (
        await session.execute(select(Profile).where(Profile.display_name == "Lewis"))
    ).scalar_one()
    existing_fixture = (
        await session.execute(
            select(Fixture).where(Fixture.home == "Everton FC", Fixture.away == "Crystal Palace")
        )
    ).scalar_one()
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=date(2026, 8, 22),
        status=GameweekStatus.settled,
        locks_at_utc=datetime(2026, 8, 22, 13, 30),
        settled_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(gameweek)
    await session.flush()
    session.add(
        Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=lewis.id,
            fixture_id=existing_fixture.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Everton FC",
            odds_at_pick=Decimal("9.99"),
            status=PickStatus.lost,
            points_awarded=0,
        )
    )
    await session.flush()

    await apply(session)

    kept = (
        await session.execute(
            select(Pick).where(Pick.player_id == lewis.id, Pick.gameweek_id == gameweek.id)
        )
    ).scalar_one()
    assert kept.odds_at_pick == Decimal("9.99"), "an existing pick is the record, not a target"


# ── Failing closed ────────────────────────────────────────────────────────────


async def test_an_unknown_member_stops_the_run(session: AsyncSession) -> None:
    """A nickname mapped to nobody must raise, not silently drop a member's round."""
    league = await _stage(session, {})
    membership = (
        await session.execute(
            select(LeagueMembership)
            .join(Profile, Profile.id == LeagueMembership.player_id)
            .where(LeagueMembership.league_id == league.id, Profile.display_name == "Grant Moore")
        )
    ).scalar_one()
    membership.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    await session.flush()

    with pytest.raises(BackfillError, match="Grant Moore"):
        await plan(session)


async def test_a_fixture_that_does_not_resolve_stops_the_run(session: AsyncSession) -> None:
    """Exactly one fixture, or nothing is written.

    Deliberately not fuzzy: `match_link` may fail open because a missing scoreline costs a
    member nothing, but attaching a pick to the wrong fixture costs them their record.
    """
    await _stage(session, {})
    stray = (
        await session.execute(
            select(Fixture).where(Fixture.home == "Salford City", Fixture.away == "Shrewsbury Town")
        )
    ).scalar_one()
    await session.delete(stray)
    await session.flush()

    with pytest.raises(BackfillError, match="Salford City v Shrewsbury Town"):
        await plan(session)


async def test_a_missing_scoreline_stops_the_run(session: AsyncSession) -> None:
    """An unsettled backfilled pick would sit pending forever and hold the round open.

    `scorelines_for` returns nothing for a fixture it cannot resolve, which is right for a
    screen and wrong here, so the backfill turns that silence into a failure.
    """
    await _stage(session, {})
    match = (
        await session.execute(
            select(Match)
            .join(Team, Team.id == Match.home_team_id)
            .where(Team.name == "Salford City")
        )
    ).scalar_one()
    await session.delete(match)
    await session.flush()

    with pytest.raises(BackfillError, match="no stored scoreline"):
        await apply(session)

    await session.rollback()


async def test_an_ambiguous_fixture_stops_the_run(session: AsyncSession) -> None:
    """Two fixtures for one pairing on one day is not a thing to pick between."""
    await _stage(session, {})
    await _fixture_and_score(session, "Salford City", "Shrewsbury Town", date(2026, 8, 8), (1, 1))

    with pytest.raises(BackfillError, match="matched 2 fixtures"):
        await plan(session)


async def test_a_same_pairing_on_a_different_day_is_not_this_round(
    session: AsyncSession,
) -> None:
    """A reverse or replayed fixture elsewhere in the season must not be picked up."""
    await _stage(session, {})
    await _fixture_and_score(
        session, "Salford City", "Shrewsbury Town", date(2026, 8, 8) + timedelta(days=90), (2, 2)
    )

    plans = await plan(session)

    assert sum(len(p.to_insert) for p in plans) == 26


# ── The one scoreline the football data does not carry ────────────────────────


def test_the_only_stated_score_is_the_competition_no_source_carries() -> None:
    """Aberdeen v Dundee, 15 August, is Scotland - League Cup Group C.

    The L4 record already lists that cup among the three api-football never resolved, and
    FotMob has nothing for it either: production holds zero finished matches in it. Pinned
    to one entry so the fallback cannot quietly become a habit — every other scoreline in
    this backfill comes from the football source, independent of the screenshots.
    """
    assert set(KNOWN_SCORES) == {("Aberdeen FC", "Dundee FC")}
    assert KNOWN_SCORES[("Aberdeen FC", "Dundee FC")] == (3, 0)


async def test_a_stated_score_settles_a_fixture_the_store_cannot_answer(
    session: AsyncSession,
) -> None:
    """The hole it exists to fill: no match row, so no scoreline, so no settlement.

    Without it Walesy's 15 August pick would sit pending forever and hold the round open —
    and the round would never reach the members who played it.
    """
    league = await _stage(session, {})

    await apply(session)

    walesy = (
        await session.execute(select(Profile).where(Profile.display_name == "Adam wales"))
    ).scalar_one()
    round_15 = (
        await session.execute(
            select(Gameweek).where(
                Gameweek.league_id == league.id, Gameweek.starts_on == date(2026, 8, 15)
            )
        )
    ).scalar_one()
    pick = (
        await session.execute(
            select(Pick).where(Pick.player_id == walesy.id, Pick.gameweek_id == round_15.id)
        )
    ).scalar_one()
    # 3-0 is one team scoring, so BTTS Yes loses — decided by the stated score rather than
    # asserted by the backfill.
    assert pick.status is PickStatus.lost
    assert pick.points_awarded == 0
    assert round_15.status is GameweekStatus.settled


async def test_a_stated_score_may_not_override_one_the_store_holds(
    session: AsyncSession,
) -> None:
    """A fallback that can outrank real data is not a fallback, it is a second truth.

    Here the store *can* answer for Aberdeen v Dundee — the staging gives it a 1-1 — and a
    stated 3-0 sitting beside it is a disagreement to be looked at, not resolved silently
    in favour of the screenshot.
    """
    await _stage(session, {})
    # Give the *store* an answer for the one fixture we also hold a stated score for —
    # a match row against the existing fixture, not a second fixture, which would trip
    # the ambiguity guard first and prove nothing about this one.
    fixture = (
        await session.execute(
            select(Fixture).where(Fixture.home == "Aberdeen FC", Fixture.away == "Dundee FC")
        )
    ).scalar_one()
    teams = []
    for name in ("Aberdeen FC", "Dundee FC"):
        team = Team(
            provider_team_id=f"t-{uuid.uuid4().hex[:10]}",
            name=name,
            normalised_name=normalise_name(name),
            competition_id=fixture.competition_id,
        )
        session.add(team)
        teams.append(team)
    await session.flush()
    session.add(
        Match(
            provider_match_id=f"m-{uuid.uuid4().hex[:10]}",
            competition_id=fixture.competition_id,
            competition="Backfill Division",
            season=2026,
            kickoff_utc=fixture.kickoff_utc,
            home_team_id=teams[0].id,
            away_team_id=teams[1].id,
            home_goals=1,
            away_goals=1,
            finished=True,
        )
    )
    await session.flush()

    with pytest.raises(BackfillError, match="would override stored data"):
        await apply(session)
