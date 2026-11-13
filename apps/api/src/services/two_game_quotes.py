"""Shared positive quotes and bounded negative rechecks with committed short leases."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.two_game import ProviderSnapshot
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    FixtureOdds,
    OddsProvider,
    OddsProviderAPIError,
    OddsProviderBadRequest,
)
from src.services.provider_budget import Category, naive_utc, provider_category, utc_now


@dataclass(frozen=True)
class QuoteView:
    event_id: str
    odds: FixtureOdds | None
    observed_at: datetime | None
    age_seconds: float | None
    availability: str
    degraded: bool
    provider: str
    bookmaker: str


class SharedQuoteBusy(OddsProviderAPIError):
    """Another short lease owns the refresh; no extra HTTP was dispatched."""


class SharedQuotes:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        provider: OddsProvider,
        *,
        source: str,
        bookmaker: str,
        clock: Callable[[], datetime] = utc_now,
        fresh_seconds: int = 60,
        negative_seconds: int = 300,
        lease_seconds: int = 45,
        browse_seconds: int = 6 * 3600,
    ) -> None:
        if not 0 < fresh_seconds <= 60 or min(negative_seconds, lease_seconds, browse_seconds) <= 0:
            raise ValueError("invalid quote freshness or lease policy")
        while isinstance(provider, CachingOddsProvider):
            # Preserve the protected legacy six-hour negative cache. The new format
            # uses its own durable recheck policy; HTTP still passes the same meter.
            provider = provider.inner
        self.sessions, self.provider = sessions, provider
        self.source, self.bookmaker, self.clock = source, bookmaker, clock
        self.fresh_seconds, self.negative_seconds = fresh_seconds, negative_seconds
        self.lease_seconds, self.browse_seconds = lease_seconds, browse_seconds

    def key(self, event_id: str) -> str:
        identity = json.dumps([self.source, self.bookmaker, event_id], separators=(",", ":"))
        return "quote:v1:" + hashlib.sha256(identity.encode()).hexdigest()

    def _view(self, event_id: str, row: ProviderSnapshot | None, now: datetime) -> QuoteView:
        if row is None or row.payload.get("state") == "pending":
            return QuoteView(
                event_id, None, None, None, "pending", False, self.source, self.bookmaker
            )
        age = (now - row.observed_at).total_seconds()
        odds = None
        if row.payload.get("state") == "available" and age >= 0:
            try:
                odds = FixtureOdds.model_validate(row.payload.get("odds"))
            except ValidationError:
                pass
        return QuoteView(
            event_id,
            odds,
            row.observed_at,
            age if age >= 0 else None,
            "available" if odds is not None else "unavailable",
            row.expires_at < now or age < 0 or bool(row.payload.get("refresh_failed")),
            self.source,
            self.bookmaker,
        )

    def _fresh(self, view: QuoteView, max_age: int) -> bool:
        return (
            view.odds is not None
            and bool(view.odds.selections)
            and view.age_seconds is not None
            and 0 <= view.age_seconds <= max_age
        )

    async def peek_many(self, event_ids: Sequence[str]) -> dict[str, QuoteView]:
        """Stored browse state only. This method can never request prices."""
        if not event_ids:
            return {}
        now = naive_utc(self.clock())
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(ProviderSnapshot).where(
                        ProviderSnapshot.key.in_([self.key(event_id) for event_id in event_ids])
                    )
                )
            ).all()
            by_key = {row.key: row for row in rows}
            return {
                event_id: self._view(event_id, by_key.get(self.key(event_id)), now)
                for event_id in event_ids
            }

    async def _claim(
        self, event_ids: Sequence[str], *, force: bool, opening_at: datetime | None
    ) -> tuple[dict[str, uuid.UUID], dict[str, QuoteView], set[str]]:
        now = naive_utc(self.clock())
        claimed: dict[str, uuid.UUID] = {}
        views: dict[str, QuoteView] = {}
        negatives: set[str] = set()
        async with self.sessions() as db, db.begin():
            for event_id in sorted(set(event_ids)):
                key = self.key(event_id)
                await db.execute(
                    insert(ProviderSnapshot)
                    .values(key=key, payload={"state": "pending"}, observed_at=now, expires_at=now)
                    .on_conflict_do_nothing()
                )
                row = await db.scalar(
                    select(ProviderSnapshot).where(ProviderSnapshot.key == key).with_for_update()
                )
                if row is None:
                    raise RuntimeError("quote snapshot disappeared")
                view = self._view(event_id, row, now)
                views[event_id] = view
                if not force and self._fresh(view, self.fresh_seconds):
                    continue
                opening_recheck = opening_at is not None and row.observed_at < opening_at <= now
                if (
                    row.payload.get("state") == "unavailable"
                    and row.negative_recheck_at is not None
                    and row.negative_recheck_at > now
                    and not opening_recheck
                ):
                    negatives.add(event_id)
                    continue
                if row.lease_until is not None and row.lease_until > now:
                    continue
                token = uuid.uuid4()
                row.lease_token, row.lease_until = (
                    token,
                    now + timedelta(seconds=self.lease_seconds),
                )
                claimed[event_id] = token
        return claimed, views, negatives

    async def _release_failed(self, claimed: dict[str, uuid.UUID]) -> None:
        async with self.sessions() as db, db.begin():
            for event_id, token in claimed.items():
                row = await db.scalar(
                    select(ProviderSnapshot)
                    .where(
                        ProviderSnapshot.key == self.key(event_id),
                        ProviderSnapshot.lease_token == token,
                    )
                    .with_for_update()
                )
                if row is not None:
                    row.lease_token = row.lease_until = None
                    row.payload = {**row.payload, "refresh_failed": True}

    async def _fetch_and_store(self, claimed: dict[str, uuid.UUID], *, category: Category) -> None:
        if not claimed:
            return
        try:
            with provider_category(category):
                fetched = await self.provider.fetch_odds(list(claimed))
        except OddsProviderBadRequest:
            if len(claimed) > 1:
                await self._release_failed(claimed)
                raise
            # An explicit rejection of this one fixture is a bounded negative, not
            # permission to re-buy the same failure on every tap.
            fetched = []
        except Exception:
            # Cancellation/crash leaves its conservative lease until expiry. Known
            # failures release only leases still owned by this caller; old data stays.
            await self._release_failed(claimed)
            raise
        now = naive_utc(self.clock())
        by_id = {odds.provider_event_id: odds for odds in fetched}
        async with self.sessions() as db, db.begin():
            for event_id, token in claimed.items():
                quote = by_id.get(event_id)
                if quote is not None:
                    quote = quote.model_copy(
                        update={
                            "selections": [
                                selection
                                for selection in quote.selections
                                if selection.price.is_finite() and selection.price > 0
                            ]
                        }
                    )
                positive = quote is not None and bool(quote.selections)
                payload = {
                    "state": "available" if positive else "unavailable",
                    "odds": quote.model_dump(mode="json")
                    if positive and quote is not None
                    else None,
                    "provider": self.source,
                    "bookmaker": self.bookmaker,
                }
                expiry = now + timedelta(
                    seconds=self.browse_seconds if positive else self.negative_seconds
                )
                await db.execute(
                    update(ProviderSnapshot)
                    .where(
                        ProviderSnapshot.key == self.key(event_id),
                        ProviderSnapshot.lease_token == token,
                        ProviderSnapshot.lease_until > now,
                    )
                    .values(
                        payload=payload,
                        observed_at=now,
                        expires_at=expiry,
                        negative_recheck_at=None if positive else expiry,
                        lease_token=None,
                        lease_until=None,
                    )
                )
        # An expired/overwritten token never writes a result or returns its old price.

    async def get_fresh(self, event_id: str) -> QuoteView:
        """Coalesce one fixture, reuse only positive <=60s, never freeze stale data."""
        for _ in range(41):
            claimed, views, negatives = await self._claim([event_id], force=False, opening_at=None)
            view = views[event_id]
            if self._fresh(view, self.fresh_seconds):
                return view
            if event_id in negatives:
                raise OddsProviderAPIError("No positive quote; bounded market recheck is pending")
            if claimed:
                await self._fetch_and_store(claimed, category="foreground")
                current = (await self.peek_many([event_id]))[event_id]
                if self._fresh(current, self.fresh_seconds):
                    return current
                if current.availability == "unavailable":
                    raise OddsProviderAPIError("No fresh positive quote is available")
                raise SharedQuoteBusy("The quote lease expired; read back before retrying")
            # The session/transaction has already closed. Waiting owns no DB lock.
            await asyncio.sleep(0.05)
        raise SharedQuoteBusy("A shared quote refresh is still in progress")

    async def refresh_many(
        self,
        event_ids: Sequence[str],
        *,
        category: Category = "background",
        opening_at: datetime | None = None,
    ) -> dict[str, QuoteView]:
        ids = list(dict.fromkeys(event_ids))
        if len(ids) > 10:
            raise ValueError("one price work chunk may contain at most ten fixtures")
        claimed, _, _ = await self._claim(ids, force=True, opening_at=opening_at)
        await self._fetch_and_store(claimed, category=category)
        return await self.peek_many(ids)
