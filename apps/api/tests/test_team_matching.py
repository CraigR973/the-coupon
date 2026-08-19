"""The name-reconciliation layer between the two providers' team spellings.

``fixtures.home`` / ``away`` come from odds-api.io and ``teams.name`` from API-Football,
and nothing joins them. These tests pin the three things that decide whether a form line
appears beside the right club: what normalisation folds away, what it deliberately does
*not*, and when a fuzzy match must refuse to guess.

The pure tests need no database. The last section does, because alias learning is the
part that makes the read path a primary-key lookup.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.team import Team, TeamAlias
from src.services.team_matching import (
    MATCH_THRESHOLD,
    best_match,
    normalise_name,
    record_alias,
    resolve_names,
    similarity,
)

SL2 = "scotland-league-two"


# ── Normalisation ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Arsenal", "Arsenal FC"),  # the club designator
        ("Airdrieonians FC", "AIRDRIEONIANS"),  # case
        ("Nott'm Forest", "Nottingham Forest"),  # apostrophe + abbreviation
        ("Sheff Wed", "Sheffield Wednesday"),
        ("Man Utd", "Man United"),
        ("Wolves", "Wolverhampton Wanderers"),
        ("QPR", "Queens Park Rangers"),
        ("St Johnstone", "Saint Johnstone"),
        ("Bayer Leverkusen", "Bayer  Leverkusen"),  # collapsed whitespace
        ("Beşiktaş", "Besiktas"),  # diacritics
        ("Brighton & Hove Albion", "Brighton and Hove Albion"),
    ],
)
def test_spellings_of_the_same_club_normalise_alike(left: str, right: str) -> None:
    assert normalise_name(left) == normalise_name(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # The distinguishing words are *kept*: dropping "Town"/"United"/"City" would merge
        # clubs that genuinely share a place name, which is the failure this layer exists
        # to avoid. Boston United and Boston Town are both real, and both English.
        ("Boston United", "Boston Town"),
        ("Bristol City", "Bristol Rovers"),
        ("Sheffield United", "Sheffield Wednesday"),
        ("Manchester United", "Manchester City"),
        ("Forfar Athletic", "Forfar"),
    ],
)
def test_different_clubs_do_not_normalise_alike(left: str, right: str) -> None:
    assert normalise_name(left) != normalise_name(right)


def test_a_name_of_only_club_designators_keeps_them() -> None:
    """Otherwise every such name normalises to "" and matches every other one."""
    assert normalise_name("FC") == "fc"
    assert normalise_name("FC") == normalise_name("F.C.")


# ── Similarity and the refusal to guess ───────────────────────────────────────


def _team(name: str, competition_id: str = SL2) -> Team:
    return Team(
        id=uuid.uuid4(),
        provider_team_id=f"t-{name}",
        name=name,
        normalised_name=normalise_name(name),
        competition_id=competition_id,
    )


def test_similarity_is_one_for_identical_names() -> None:
    assert similarity("forfar athletic", "forfar athletic") == 1.0


def test_similarity_survives_a_missing_word() -> None:
    """Shared-token proportion is what character similarity scores badly here."""
    assert similarity("inverness caledonian thistle", "inverness caledonian") >= MATCH_THRESHOLD


def test_the_subset_bonus_is_what_clubs_need_and_competitions_must_not_have() -> None:
    """One flag, two opposite truths (Batch 37).

    For clubs the shorter name is usually an abbreviation of the longer, so the bonus is
    right. For competitions the shorter name is usually a *different* competition:
    "premier league" is a whole division, and treating it as shorthand for the fifth-tier
    "southern league premier division south" is how that division came to resolve to
    England's top flight.
    """
    club = similarity("inverness caledonian", "inverness caledonian thistle")
    assert club >= MATCH_THRESHOLD

    competition = "southern league premier division south"
    assert similarity(competition, "premier league") >= MATCH_THRESHOLD
    assert similarity(competition, "premier league", allow_subset=False) < MATCH_THRESHOLD


def test_withholding_the_subset_bonus_leaves_exact_matches_alone() -> None:
    assert similarity("premier league", "premier league", allow_subset=False) == 1.0
    assert similarity("national league north", "national league north", allow_subset=False) == 1.0


def test_best_match_finds_the_club_behind_a_spelling_drift() -> None:
    candidates = [_team("Forfar Athletic FC"), _team("Brechin City FC"), _team("Elgin City FC")]
    team, score = best_match(normalise_name("Forfar Athletic"), candidates)
    assert team is not None
    assert team.name == "Forfar Athletic FC"
    assert score >= MATCH_THRESHOLD


def test_best_match_refuses_an_unrelated_name() -> None:
    candidates = [_team("Forfar Athletic FC"), _team("Brechin City FC")]
    team, _ = best_match(normalise_name("Peterhead"), candidates)
    assert team is None


def test_a_subset_of_the_words_matches_but_never_beats_the_exact_club() -> None:
    """ "Rangers" must be Rangers, even with Queens Park Rangers in the same division."""
    candidates = [_team("Rangers"), _team("Queens Park Rangers")]
    team, _ = best_match(normalise_name("Rangers FC"), candidates)
    assert team is not None
    assert team.name == "Rangers"


def test_best_match_refuses_when_two_candidates_are_equally_close() -> None:
    """An ambiguous name resolves to nothing on purpose.

    No form line is much better than another club's form line, and the two Bangors are a
    real pair — one Welsh, one Northern Irish — that a wider candidate pool would offer.
    """
    candidates = [_team("Bangor City FC"), _team("Bangor City")]
    team, _ = best_match(normalise_name("Bangor City"), candidates)
    assert team is None


def test_best_match_on_an_empty_pool_is_a_miss_not_a_crash() -> None:
    assert best_match("anything", []) == (None, 0.0)


# ── Alias learning (Postgres-backed) ──────────────────────────────────────────

pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Rolls back on exit — these tests flush, never commit."""
    async with AsyncSessionLocal() as s:
        try:
            yield s
        finally:
            await s.rollback()


async def _stored_team(session: AsyncSession, name: str, competition_id: str) -> Team:
    team = Team(
        provider_team_id=f"af-{uuid.uuid4().hex[:8]}",
        name=name,
        normalised_name=normalise_name(name),
        competition_id=competition_id,
    )
    session.add(team)
    await session.flush()
    return team


@pytest_db
@pytest.mark.asyncio
async def test_resolving_a_name_learns_it_as_an_alias(session: AsyncSession) -> None:
    """The first sighting is fuzzy; every later one is a primary-key hit."""
    competition = f"comp-{uuid.uuid4().hex[:8]}"
    team = await _stored_team(session, "Forfar Athletic FC", competition)

    resolved = await resolve_names(session, competition, ["Forfar Athletic"])
    assert resolved["Forfar Athletic"].id == team.id

    stored = await session.execute(
        select(TeamAlias).where(
            TeamAlias.competition_id == competition,
            TeamAlias.normalised == normalise_name("Forfar Athletic"),
        )
    )
    alias = stored.scalar_one()
    assert alias.team_id == team.id
    assert alias.source == "odds"


@pytest_db
@pytest.mark.asyncio
async def test_an_unresolvable_name_is_absent_rather_than_wrong(session: AsyncSession) -> None:
    competition = f"comp-{uuid.uuid4().hex[:8]}"
    await _stored_team(session, "Forfar Athletic FC", competition)

    resolved = await resolve_names(session, competition, ["Peterhead", "Forfar Athletic"])
    assert "Peterhead" not in resolved
    assert "Forfar Athletic" in resolved


@pytest_db
@pytest.mark.asyncio
async def test_the_same_spelling_means_different_clubs_in_different_competitions(
    session: AsyncSession,
) -> None:
    """Club names are only unique within a division — hence the per-competition key."""
    wales = f"wales-{uuid.uuid4().hex[:8]}"
    ulster = f"nireland-{uuid.uuid4().hex[:8]}"
    welsh = await _stored_team(session, "Bangor City FC", wales)
    irish = await _stored_team(session, "Bangor FC", ulster)

    assert (await resolve_names(session, wales, ["Bangor City"]))["Bangor City"].id == welsh.id
    assert (await resolve_names(session, ulster, ["Bangor"]))["Bangor"].id == irish.id


@pytest_db
@pytest.mark.asyncio
async def test_an_existing_alias_is_never_re_pointed(session: AsyncSession) -> None:
    """A later fuzzy match must not overwrite a link made by hand or from the source."""
    competition = f"comp-{uuid.uuid4().hex[:8]}"
    first = await _stored_team(session, "Brechin City FC", competition)
    second = await _stored_team(session, "Brechin City Reserves", competition)

    await record_alias(session, competition, "Brechin", first, source="manual")
    await record_alias(session, competition, "Brechin", second, source="odds")

    stored = await session.execute(
        select(TeamAlias).where(
            TeamAlias.competition_id == competition,
            TeamAlias.normalised == normalise_name("Brechin"),
        )
    )
    alias = stored.scalar_one()
    assert alias.team_id == first.id
    assert alias.source == "manual"


@pytest_db
@pytest.mark.asyncio
async def test_resolving_nothing_touches_no_rows(session: AsyncSession) -> None:
    assert await resolve_names(session, "anything", []) == {}
    assert await resolve_names(session, "anything", ["", "   "]) == {}
