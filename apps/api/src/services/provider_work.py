"""Short, token-fenced work leases; never keep a database transaction over HTTP."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.two_game import ProviderWork
from src.services.provider_budget import naive_utc, utc_now


@dataclass(frozen=True)
class WorkLease:
    key: str
    token: uuid.UUID
    kind: str
    payload: dict[str, Any]
    cursor: str | None
    fixture_id: uuid.UUID | None
    attempts: int


async def enqueue(
    db: AsyncSession,
    *,
    key: str,
    kind: str,
    payload: dict[str, Any],
    next_at: datetime,
    fixture_id: uuid.UUID | None = None,
) -> None:
    # A preparation pass cannot reset progress, retry time or a running owner's lease.
    await db.execute(
        insert(ProviderWork)
        .values(key=key, kind=kind, payload=payload, next_at=next_at, fixture_id=fixture_id)
        .on_conflict_do_nothing()
    )


class WorkQueue:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = utc_now,
        lease_seconds: int = 45,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("work lease must be positive")
        self.sessions, self.clock, self.lease_seconds = sessions, clock, lease_seconds

    async def claim(
        self,
        kinds: Sequence[str],
        *,
        source: str | None = None,
        keys: Sequence[str] | None = None,
    ) -> WorkLease | None:
        now = naive_utc(self.clock())
        async with self.sessions() as db, db.begin():
            scope = [] if source is None else [ProviderWork.payload["source"].astext == source]
            if keys is not None:
                scope.append(ProviderWork.key.in_(keys))
            row = await db.scalar(
                select(ProviderWork)
                .where(
                    ProviderWork.kind.in_(kinds),
                    ProviderWork.next_at <= now,
                    or_(ProviderWork.lease_until.is_(None), ProviderWork.lease_until <= now),
                    *scope,
                )
                .order_by(ProviderWork.next_at, ProviderWork.key)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            token = uuid.uuid4()
            row.lease_token, row.lease_until = token, now + timedelta(seconds=self.lease_seconds)
            # A crash/expired failure must rotate behind other waiting work even
            # when no owner survives to record a backoff.
            row.next_at = row.lease_until
            row.attempts += 1
            return WorkLease(
                row.key,
                token,
                row.kind,
                dict(row.payload),
                row.cursor,
                row.fixture_id,
                row.attempts,
            )

    async def owned(
        self, db: AsyncSession, lease: WorkLease, *, require_live: bool = True
    ) -> ProviderWork | None:
        live = [ProviderWork.lease_until > naive_utc(self.clock())] if require_live else []
        row: ProviderWork | None = await db.scalar(
            select(ProviderWork)
            .where(
                ProviderWork.key == lease.key,
                ProviderWork.lease_token == lease.token,
                *live,
            )
            .with_for_update()
        )
        return row

    async def defer(
        self,
        lease: WorkLease,
        reason: str,
        *,
        retry_at: datetime | None = None,
        kind: str | None = None,
    ) -> None:
        now = naive_utc(self.clock())
        async with self.sessions() as db, db.begin():
            row = await self.owned(db, lease, require_live=False)
            if row is not None:
                if kind is not None:
                    row.kind = kind
                row.last_error = reason[:200]
                row.next_at = max(
                    retry_at or now + timedelta(minutes=min(60, 6 * lease.attempts)),
                    now + timedelta(seconds=1),
                )
                row.lease_token = row.lease_until = None
