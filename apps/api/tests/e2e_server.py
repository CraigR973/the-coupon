"""Test-only FastAPI entrypoint for the production-preview browser flow.

Run with ``uvicorn tests.e2e_server:app`` against a disposable migrated
PostgreSQL database. Production never imports this module.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider
from src.main import app
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.services.betfair import (
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.fake_football import SAMPLE_SEASON, FakeFootballData
from src.services.football_data import backfill_season
from src.services.gameweek import latest_gameweek, sync_slate, window_for
from src.services.scoring import settle_gameweek_via_provider

E2E_LEAGUE_SLUG = "the-coupon"
E2E_PIN = "1234"

fake_betfair = FakeBetfair.with_sample_data()
app.dependency_overrides[get_odds_provider] = lambda: fake_betfair

# The canned football data describes 2025-26 while the canned slate is the opening
# Saturday of 2026-27 — the ordinary opening-day situation, where what a member sees
# is last season's final table. The read path takes its season from settings, so it is
# pinned here rather than left to whichever season today happens to fall in; this
# module is test-only, so mutating settings is contained to the browser flow.
settings.football_season = SAMPLE_SEASON


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@app.post("/__e2e/seed")
async def seed_coupon_flow() -> dict[str, object]:
    """Seed three members, the default league, and the canned Saturday slate."""

    global fake_betfair
    fake_betfair = FakeBetfair.with_sample_data()

    async with AsyncSessionLocal() as db:
        # This module is test-only and always targets a disposable database.
        # Reset the complete domain graph so the browser flow is repeatable.
        # `gameweeks` cascades from `leagues` since Batch 14, and `fixtures` are now
        # a pool no gameweek owns, so both roots have to be named explicitly.
        await db.execute(text("TRUNCATE TABLE profiles, leagues, fixtures CASCADE"))

        alice = Profile(
            display_name="Alice",
            pin_hash=hash_pin(E2E_PIN),
            role=UserRole.player,
            timezone="Europe/London",
        )
        bob = Profile(
            display_name="Bob",
            pin_hash=hash_pin(E2E_PIN),
            role=UserRole.player,
            timezone="Europe/London",
        )
        carol = Profile(
            display_name="Carol",
            pin_hash=hash_pin(E2E_PIN),
            role=UserRole.player,
            timezone="Europe/London",
        )
        db.add_all([alice, bob, carol])
        await db.flush()

        league = League(
            slug=E2E_LEAGUE_SLUG,
            name="The Coupon Test League",
            created_by=alice.id,
        )
        db.add(league)
        await db.flush()
        db.add_all(
            [
                LeagueMembership(
                    league_id=league.id,
                    player_id=alice.id,
                    role=LeagueMemberRole.admin,
                ),
                LeagueMembership(league_id=league.id, player_id=bob.id),
                LeagueMembership(league_id=league.id, player_id=carol.id),
            ]
        )

        slate = await fake_betfair.fetch_slate(window_for(league), SAMPLE_SATURDAY)
        gameweek = await sync_slate(db, league, slate)
        gameweek.status = GameweekStatus.open
        gameweek.locks_at_utc = _now() + timedelta(hours=2)

        # Batch 16: the canned season's tables and results for whatever competitions the
        # slate just put in the pool. Runs *after* `sync_slate` because ingestion takes
        # its competition list from the fixtures, and it is the backfill rather than the
        # windowed daily job because the canned results predate the canned slate.
        football = await backfill_season(
            db, FakeFootballData.with_sample_data(), season=SAMPLE_SEASON
        )
        await db.commit()

        return {
            "league_slug": league.slug,
            "gameweek_id": str(gameweek.id),
            "players": ["Alice", "Bob", "Carol"],
            "football_competitions": [r.competition_id for r in football.reports if r.carried],
        }


async def _seeded_gameweek(db: AsyncSession) -> Gameweek | None:
    """The seeded league's latest round.

    Rounds are per-league since Batch 14, so there is no global "latest" to ask for
    — the league has to be resolved first.
    """
    league = (
        await db.execute(select(League).where(League.slug == E2E_LEAGUE_SLUG))
    ).scalar_one_or_none()
    if league is None:
        return None
    return await latest_gameweek(db, league.id)


@app.post("/__e2e/lock")
async def lock_coupon_flow() -> dict[str, str]:
    """Lock the seeded round exactly as the scheduled job would."""

    async with AsyncSessionLocal() as db:
        gameweek = await _seeded_gameweek(db)
        if gameweek is None:
            raise HTTPException(status_code=404, detail="E2E_NOT_SEEDED")
        gameweek.status = GameweekStatus.locked
        gameweek.locks_at_utc = _now() - timedelta(seconds=1)
        await db.commit()
        return {"status": gameweek.status.value}


@app.post("/__e2e/settle")
async def settle_coupon_flow() -> dict[str, object]:
    """Close the canned winning markets and settle all seeded picks."""

    fake_betfair.close_markets(
        {
            SAMPLE_EPL_MATCH_ODDS_MKT: 1001,
            SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
        }
    )
    async with AsyncSessionLocal() as db:
        gameweek = await _seeded_gameweek(db)
        if gameweek is None:
            raise HTTPException(status_code=404, detail="E2E_NOT_SEEDED")
        resolved = await settle_gameweek_via_provider(db, fake_betfair, gameweek)
        await db.commit()
        return {"status": gameweek.status.value, "resolved": resolved}
