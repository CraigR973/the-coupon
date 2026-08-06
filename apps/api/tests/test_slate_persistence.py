"""Slate persistence against a real database.

Column widths only fail against PostgreSQL, so these are Postgres-backed. They
exist because migration 005 widened `fixtures.provider_event_id` for the new
provider but left `fixtures.competition_id` at its Betfair-era `String(32)`.
That column had held short numeric competition ids and now holds an
odds-api.io league slug; ten of the thirty UK slugs are longer than 32
characters. Because a slate is written in one transaction, the first oversized
slug aborted the entire refresh with `StringDataRightTruncationError`, and
production could build no slate at all.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.league import League
from src.models.profile import Profile, UserRole
from src.services.gameweek import fixtures_for, sync_slate
from src.services.odds_provider import Slate, SlateFixture

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

# The longest UK league slug odds-api.io returns, measured live on 2026-08-04.
# The longest across all 728 competitions was 66 characters.
LONGEST_UK_SLUG = "england-amateur-southern-league-premier-division-central"
LONGEST_UK_NAME = "England Amateur - Southern League, Premier Division Central"


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Never commits: `sync_slate` flushes, so the rows are visible to this
    session and vanish on rollback. Keeps the shared scratch database clean for
    the rest of the suite."""
    async with AsyncSessionLocal() as s:
        try:
            yield s
        finally:
            await s.rollback()


async def _league(session: AsyncSession) -> League:
    """A league to own the round — rounds are per-league since Batch 14."""
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"owner-{tag}", pin_hash="x", role=UserRole.player)
    session.add(owner)
    await session.flush()
    league = League(slug=f"slate-{tag}", name=f"Slate {tag}", created_by=owner.id)
    session.add(league)
    await session.flush()
    return league


def _slate(saturday: datetime, *, competition: str, competition_id: str) -> Slate:
    return Slate(
        starts_on=saturday.date(),
        fixtures=[
            SlateFixture(
                provider_event_id="90000001",
                home="Truro City",
                away="Chesham United",
                kickoff_utc=saturday.replace(tzinfo=None),
                competition=competition,
                competition_id=competition_id,
            )
        ],
    )


async def test_persists_the_longest_real_league_slug(session: AsyncSession) -> None:
    """A 56-character slug must round-trip, not truncate or raise."""
    saturday = datetime(2027, 3, 6, 15, 0, tzinfo=UTC)
    gameweek = await sync_slate(
        session,
        await _league(session),
        _slate(saturday, competition=LONGEST_UK_NAME, competition_id=LONGEST_UK_SLUG),
    )

    stored = (await fixtures_for(session, gameweek.id))[0]
    assert stored.competition_id == LONGEST_UK_SLUG
    assert stored.competition == LONGEST_UK_NAME


async def test_column_admits_the_longest_slug_the_provider_can_return(
    session: AsyncSession,
) -> None:
    """66 characters is the observed maximum across every competition.

    Guards the width itself rather than one league, so a provider adding a
    longer competition than any UK one still fits.
    """
    saturday = datetime(2027, 3, 13, 15, 0, tzinfo=UTC)
    slug = "x" * 66
    gameweek = await sync_slate(
        session,
        await _league(session),
        _slate(saturday, competition="Some Long Competition", competition_id=slug),
    )

    stored = (await fixtures_for(session, gameweek.id))[0]
    assert stored.competition_id == slug
