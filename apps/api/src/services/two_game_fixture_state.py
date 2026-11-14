"""Persisted provider eligibility, separate from a game's immutable accepted history."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.two_game import ProviderSnapshot
from src.services.odds_provider import SlateFixture, is_void_status
from src.services.provider_budget import naive_utc


def fixture_state_key(source: str, event_id: str) -> str:
    identity = json.dumps([source, event_id], separators=(",", ":"))
    return "fixture-state:v1:" + hashlib.sha256(identity.encode()).hexdigest()


async def explicitly_void(db: AsyncSession, source: str, event_id: str) -> bool:
    row = await db.get(ProviderSnapshot, fixture_state_key(source, event_id))
    return row is not None and is_void_status(str(row.payload.get("status", "")))


async def record_fixture_observations(
    db: AsyncSession,
    source: str,
    fixtures: Sequence[SlateFixture],
    *,
    observed_at: datetime,
    expires_at: datetime,
) -> None:
    """Persist actual source facts atomically, Fixture before its shared status.

    Call only for fresh provider responses, never a pooled or cached slate.
    Every writer takes the same fixture order; no league lock or external I/O
    belongs here. Even unchanged metadata is upserted, so a final entry's
    Fixture SHARE also fences status-only changes.
    """
    fixture_ids = await upsert_fixture_metadata(db, fixtures)
    by_event = {fixture.provider_event_id: fixture for fixture in fixtures}
    for event_id in sorted(by_event):
        fixture = by_event[event_id]
        fixture_id = fixture_ids[event_id]
        state = dict(
            source=source,
            event_id=event_id,
            status=fixture.status,
            kickoff_utc=naive_utc(fixture.kickoff_utc).isoformat(),
        )
        values = dict(
            payload=state,
            fixture_id=fixture_id,
            observed_at=naive_utc(observed_at),
            expires_at=naive_utc(expires_at),
        )
        await db.execute(
            insert(ProviderSnapshot)
            .values(key=fixture_state_key(source, event_id), **values)
            .on_conflict_do_update(index_elements=[ProviderSnapshot.key], set_=values)
        )


async def upsert_fixture_metadata(
    db: AsyncSession, fixtures: Sequence[SlateFixture], *, skip_unchanged: bool = False
) -> dict[str, uuid.UUID]:
    """Lock shared metadata in provider-event order for fresh and legacy writers."""
    fixture_ids: dict[str, uuid.UUID] = {}
    by_event = {fixture.provider_event_id: fixture for fixture in fixtures}
    existing = {}
    if skip_unchanged and by_event:
        rows = await db.scalars(
            select(Fixture)
            .where(Fixture.provider_event_id.in_(by_event))
            .execution_options(populate_existing=True)
        )
        existing = {row.provider_event_id: row for row in rows}
    for event_id in sorted(by_event):
        fixture = by_event[event_id]
        metadata = dict(
            home=fixture.home,
            away=fixture.away,
            kickoff_utc=naive_utc(fixture.kickoff_utc),
            competition=fixture.competition,
            competition_id=fixture.competition_id,
        )
        current = existing.get(event_id)
        if current is not None and all(
            getattr(current, key) == value for key, value in metadata.items()
        ):
            fixture_ids[event_id] = current.id
            continue
        fixture_id = await db.scalar(
            insert(Fixture)
            .values(provider_event_id=event_id, **metadata)
            .on_conflict_do_update(constraint="uq_fixtures_provider_event", set_=metadata)
            .returning(Fixture.id)
        )
        assert fixture_id is not None
        fixture_ids[event_id] = fixture_id
    return fixture_ids
