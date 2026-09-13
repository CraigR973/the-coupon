"""The site-admin calendar surface mutates declarations, never fixture discovery."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services.season_calendar import canonical_saturday

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_calendar_crud_is_global_deferred_and_pick_safe(client: AsyncClient) -> None:
    tag = uuid.uuid4().hex
    season = 3000 + int(tag[:2], 16)
    anchor = canonical_saturday(date(season, 8, 1))
    extra = anchor + timedelta(days=1)
    async with AsyncSessionLocal() as db:
        admin = Profile(
            display_name=f"calendar-admin-{tag[:8]}",
            pin_hash=hash_pin("1234"),
            role=UserRole.admin,
        )
        db.add(admin)
        await db.flush()
        db.add(SeasonCalendar(season=season, week_one_anchor=anchor, extra_weeks=[]))
        await db.commit()
        await db.refresh(admin)
    headers = {"Authorization": f"Bearer {create_access_token(admin.id, admin.role)}"}

    declared = await client.post(
        "/api/v1/admin/calendar/extra-weeks",
        json={"season": season, "starts_on": extra.isoformat()},
        headers=headers,
    )
    assert declared.status_code == 200, declared.text
    assert any(
        week["starts_on"] == extra.isoformat() and week["is_extra"]
        for week in declared.json()["weeks"]
    )
    async with AsyncSessionLocal() as db:
        # The request records intent only. Discovery is the sole materialisation path.
        rounds = await db.scalar(
            select(Gameweek).where(Gameweek.starts_on == extra).exists().select()
        )
        assert rounds is False

        league = League(slug=f"calendar-{tag[:8]}", name="Calendar", created_by=admin.id)
        db.add(league)
        await db.flush()
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=extra,
            number=1,
            status=GameweekStatus.settled,
            locks_at_utc=datetime(extra.year, extra.month, extra.day, 13, 30),
        )
        fixture = Fixture(
            provider_event_id=f"calendar-{tag}",
            home="Forfar",
            away="Brechin",
            kickoff_utc=datetime(extra.year, extra.month, extra.day, 14),
            competition="League Two",
            competition_id="scotland-league-two",
        )
        db.add_all([gameweek, fixture])
        await db.flush()
        db.add(
            Pick(
                league_id=league.id,
                gameweek_id=gameweek.id,
                fixture_id=fixture.id,
                player_id=admin.id,
                market=PickMarket.MATCH_ODDS,
                outcome=PickOutcome.HOME,
                runner_name="Forfar",
                odds_at_pick=Decimal("2.00"),
            )
        )
        await db.commit()

    refused = await client.request(
        "DELETE",
        "/api/v1/admin/calendar/extra-weeks",
        json={"season": season, "starts_on": extra.isoformat()},
        headers=headers,
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "EXTRA_WEEK_HAS_PICKS"

    # This HTTP test must commit so the next request can see the declaration and pick.
    # Remove its deliberately far-future fixture afterwards: the football-data tests
    # discover competitions from the shared fixture pool and run later in the suite.
    async with AsyncSessionLocal() as db:
        await db.execute(delete(League).where(League.slug == f"calendar-{tag[:8]}"))
        await db.execute(delete(Fixture).where(Fixture.provider_event_id == f"calendar-{tag}"))
        await db.execute(delete(Profile).where(Profile.id == admin.id))
        await db.execute(delete(SeasonCalendar).where(SeasonCalendar.season == season))
        await db.commit()
