"""Persisted provider eligibility, separate from a game's immutable accepted history."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.two_game import ProviderSnapshot
from src.services.odds_provider import is_void_status


def fixture_state_key(source: str, event_id: str) -> str:
    identity = json.dumps([source, event_id], separators=(",", ":"))
    return "fixture-state:v1:" + hashlib.sha256(identity.encode()).hexdigest()


async def explicitly_void(db: AsyncSession, source: str, event_id: str) -> bool:
    row = await db.get(ProviderSnapshot, fixture_state_key(source, event_id))
    return row is not None and is_void_status(str(row.payload.get("status", "")))
