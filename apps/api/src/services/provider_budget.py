"""Durable actual-dispatch admission, independent of any member transaction.

Reservations are conservative: once committed they remain spent if dispatch or its
response is uncertain. No session, row lock or advisory lock survives into HTTP I/O.
The legacy fixed-window abuse limits and process cache remain separate safeguards.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.two_game import ProviderAttempt, ProviderControl, ProviderRefusal, ProviderSnapshot
from src.services.odds_provider import OddsProviderRateLimited

Category = Literal["legacy", "foreground", "background", "opening", "settlement"]
_category: ContextVar[Category] = ContextVar("odds_dispatch_category", default="legacy")
LONDON = ZoneInfo("Europe/London")
INSTALLATION_METER = "installation-odds-v1"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


@contextmanager
def provider_category(category: Category) -> Iterator[None]:
    token = _category.set(category)
    try:
        yield
    finally:
        _category.reset(token)


@dataclass(frozen=True)
class BudgetPolicy:
    hourly: int = 90
    daily: int = 450
    background_hourly: int = 10
    background_daily: int = 120
    background_spacing_seconds: int = 360
    opening: int = 5
    settlement_hourly: int = 30
    settlement_daily: int = 200
    rate_cooldown_seconds: int = 300
    refused_cooldown_seconds: int = 900

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("provider ceilings and cooldowns must be positive")


@dataclass(frozen=True)
class Reservation:
    id: uuid.UUID
    reserved_at: datetime
    category: Category


@dataclass(frozen=True)
class BudgetView:
    spent_hour: int
    spent_day: int
    remaining_hour: int
    remaining_day: int
    cooldown_until: datetime | None
    header_remaining: int | None


class ProviderBudgetRefused(OddsProviderRateLimited):
    def __init__(self, reason: str, retry_at: datetime) -> None:
        super().__init__(f"provider admission refused: {reason}")
        self.reason = reason
        self.retry_at = retry_at


def _ceiling(
    stamps: Sequence[datetime], limit: int, now: datetime, span: timedelta
) -> datetime | None:
    active = sorted(stamp for stamp in stamps if stamp > now - span)
    return active[len(active) - limit] + span if len(active) >= limit else None


def _next_opening(now: datetime) -> datetime:
    local = now.replace(tzinfo=UTC).astimezone(LONDON)
    days = (5 - local.weekday()) % 7
    target = (local + timedelta(days=days)).replace(hour=12, minute=0, second=0, microsecond=0)
    if target <= local:
        target += timedelta(days=7)
    return naive_utc(target)


class ProviderBudget:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession] | None = None,
        *,
        policy: BudgetPolicy | None = None,
        meter: str = INSTALLATION_METER,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if sessions is None:
            from src.database import AsyncSessionLocal

            sessions = AsyncSessionLocal
        self.sessions = sessions
        self.policy = policy or BudgetPolicy()
        self.meter = meter
        self.clock = clock

    @classmethod
    def from_settings(cls) -> ProviderBudget:
        from src.config import settings

        return cls(
            policy=BudgetPolicy(
                hourly=settings.two_game_hourly_attempts,
                daily=settings.two_game_daily_attempts,
                background_hourly=settings.two_game_background_hourly,
                background_daily=settings.two_game_background_daily,
                background_spacing_seconds=settings.two_game_background_spacing_seconds,
                opening=settings.two_game_opening_attempts,
                settlement_hourly=settings.two_game_settlement_hourly,
                settlement_daily=settings.two_game_settlement_daily,
                rate_cooldown_seconds=settings.odds_rate_limited_cooldown_seconds,
                refused_cooldown_seconds=settings.odds_refused_cooldown_seconds,
            )
        )

    async def _control(self, db: AsyncSession) -> ProviderControl:
        await db.execute(insert(ProviderControl).values(meter=self.meter).on_conflict_do_nothing())
        control = await db.scalar(
            select(ProviderControl).where(ProviderControl.meter == self.meter).with_for_update()
        )
        if control is None:
            raise RuntimeError("provider control disappeared")
        return control

    def _effective_now(self, control: ProviderControl) -> datetime:
        now = max(naive_utc(self.clock()), control.last_clock_at or datetime.min)
        control.last_clock_at = now
        if control.header_reset_at is not None and control.header_reset_at <= now:
            control.header_remaining = None
        return now

    async def _attempts(self, db: AsyncSession, now: datetime) -> list[tuple[datetime, str]]:
        rows = await db.execute(
            select(ProviderAttempt.reserved_at, ProviderAttempt.category).where(
                ProviderAttempt.meter == self.meter,
                ProviderAttempt.reserved_at > now - timedelta(days=1),
            )
        )
        return [(stamp, category) for stamp, category in rows.all()]

    def _refusal(
        self,
        control: ProviderControl,
        rows: list[tuple[datetime, str]],
        category: Category,
        now: datetime,
    ) -> tuple[str, datetime] | None:
        checks: list[tuple[str, datetime]] = []
        if control.cooldown_until is not None and control.cooldown_until > now:
            checks.append(("provider_cooldown", control.cooldown_until))
        if control.header_remaining is not None and control.header_remaining <= 0:
            checks.append(
                ("provider_remaining", control.header_reset_at or now + timedelta(hours=1))
            )
        stamps = [stamp for stamp, _ in rows]
        for name, limit, span in (
            ("rolling_hour", self.policy.hourly, timedelta(hours=1)),
            ("rolling_day", self.policy.daily, timedelta(days=1)),
        ):
            retry = _ceiling(stamps, limit, now, span)
            if retry is not None:
                checks.append((name, retry))
        local = now.replace(tzinfo=UTC).astimezone(LONDON)
        own = [stamp for stamp, kind in rows if kind == category]
        if category == "background":
            if local.weekday() == 5 and 10 <= local.hour < 13:
                checks.append(
                    (
                        "background_pause",
                        naive_utc(local.replace(hour=13, minute=0, second=0, microsecond=0)),
                    )
                )
            if own:
                retry = max(own) + timedelta(seconds=self.policy.background_spacing_seconds)
                if retry > now:
                    checks.append(("background_spacing", retry))
            caps = (self.policy.background_hourly, self.policy.background_daily)
        elif category == "settlement":
            caps = (self.policy.settlement_hourly, self.policy.settlement_daily)
        elif category == "opening":
            if local.weekday() != 5 or local.hour != 12:
                checks.append(("opening_window", _next_opening(now)))
            caps = (self.policy.opening, self.policy.opening)
        else:
            caps = (self.policy.hourly, self.policy.daily)
        for name, limit, span in (
            ("category_hour", caps[0], timedelta(hours=1)),
            ("category_day", caps[1], timedelta(days=1)),
        ):
            retry = _ceiling(own, limit, now, span)
            if retry is not None:
                checks.append((name, retry))
        return max(checks, key=lambda item: item[1]) if checks else None

    async def admit(self, category: Category | None = None) -> Reservation:
        chosen = category or _category.get()
        refusal: tuple[str, datetime] | None
        reservation: Reservation | None = None
        async with self.sessions() as db, db.begin():
            control = await self._control(db)
            now = self._effective_now(control)
            refusal = self._refusal(control, await self._attempts(db, now), chosen, now)
            if refusal is not None:
                reason, retry = refusal
                db.add(
                    ProviderRefusal(
                        meter=self.meter,
                        category=chosen,
                        refused_at=now,
                        retry_at=retry,
                        reason=reason,
                    )
                )
            else:
                reservation = Reservation(uuid.uuid4(), now, chosen)
                db.add(
                    ProviderAttempt(
                        id=reservation.id, meter=self.meter, category=chosen, reserved_at=now
                    )
                )
                if control.header_remaining is not None:
                    control.header_remaining -= 1
        # Refusal is raised AFTER the independent transaction commits its evidence.
        if refusal is not None:
            raise ProviderBudgetRefused(*refusal)
        if reservation is None:
            raise RuntimeError("provider reservation was not recorded")
        return reservation

    async def observe(
        self, reservation: Reservation, status: int, headers: Mapping[str, str]
    ) -> None:
        values = {key.lower(): value for key, value in headers.items()}
        async with self.sessions() as db, db.begin():
            control = await self._control(db)
            now = self._effective_now(control)
            attempt = await db.get(ProviderAttempt, reservation.id)
            if attempt is None or attempt.meter != self.meter:
                raise ValueError("response does not belong to this meter")
            # Separate receipts preserve the immutable spent-attempt ledger.
            await db.execute(
                insert(ProviderSnapshot)
                .values(
                    key=f"attempt-response:{reservation.id}",
                    payload={"state": "observed", "status": status},
                    observed_at=now,
                    expires_at=now + timedelta(days=2),
                )
                .on_conflict_do_nothing()
            )
            remaining = _integer(
                values.get("x-ratelimit-remaining", values.get("ratelimit-remaining"))
            )
            reset = _reset(
                values.get("x-ratelimit-reset", values.get("ratelimit-reset")),
                reservation.reserved_at,
            )
            if remaining is not None:
                reset = reset or reservation.reserved_at + timedelta(hours=1)
                if reset > now:
                    # Only responses observed before this request was reserved are
                    # certainly included upstream. Earlier requests can finish later;
                    # unresolved requests and equal timestamps stay conservative.
                    later = await db.scalar(
                        select(func.count())
                        .select_from(ProviderAttempt)
                        .outerjoin(
                            ProviderSnapshot,
                            ProviderSnapshot.key
                            == func.concat("attempt-response:", ProviderAttempt.id),
                        )
                        .where(
                            ProviderAttempt.meter == self.meter,
                            ProviderAttempt.reserved_at > now - timedelta(days=1),
                            ProviderAttempt.id != reservation.id,
                            or_(
                                ProviderSnapshot.observed_at.is_(None),
                                ProviderSnapshot.observed_at >= reservation.reserved_at,
                            ),
                        )
                    )
                    available = max(0, remaining - (later or 0))
                    control.header_remaining = (
                        min(control.header_remaining, available)
                        if control.header_remaining is not None
                        else available
                    )
                    control.header_reset_at = max(control.header_reset_at or reset, reset)
            if status in (401, 403, 429):
                retry = _retry_after(values.get("retry-after"), now) if status == 429 else None
                seconds = (
                    self.policy.rate_cooldown_seconds
                    if status == 429
                    else self.policy.refused_cooldown_seconds
                )
                until = retry or now + timedelta(seconds=seconds)
                control.cooldown_until = max(control.cooldown_until or until, until)

    async def view(self) -> BudgetView:
        async with self.sessions() as db:
            control = await db.get(ProviderControl, self.meter)
            now = (
                max(naive_utc(self.clock()), control.last_clock_at or datetime.min)
                if control is not None
                else naive_utc(self.clock())
            )
            rows = await self._attempts(db, now)
            hour = sum(stamp > now - timedelta(hours=1) for stamp, _ in rows)
            remaining = control.header_remaining if control is not None else None
            if (
                control is not None
                and control.header_reset_at is not None
                and control.header_reset_at <= now
            ):
                remaining = None
            cooldown = control.cooldown_until if control is not None else None
            available = remaining if remaining is not None else self.policy.daily
            if cooldown is not None and cooldown > now:
                available = 0
            return BudgetView(
                hour,
                len(rows),
                max(0, min(self.policy.hourly - hour, available)),
                max(0, min(self.policy.daily - len(rows), available)),
                cooldown,
                remaining,
            )


def _integer(value: str | None) -> int | None:
    try:
        result = int(value) if value is not None else -1
        return result if result >= 0 else None
    except ValueError:
        return None


def _reset(value: str | None, sent_at: datetime) -> datetime | None:
    try:
        number = float(value) if value is not None else math.nan
        if not math.isfinite(number) or number < 0:
            return None
        return (
            datetime.fromtimestamp(number, UTC).replace(tzinfo=None)
            if number > 1_000_000_000
            else sent_at + timedelta(seconds=number)
        )
    except (ValueError, OverflowError, OSError):
        return None


def _retry_after(value: str | None, now: datetime) -> datetime | None:
    if value is None:
        return None
    try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds >= 0:
            return now + timedelta(seconds=max(1, seconds))
    except (ValueError, OverflowError):
        pass
    try:
        result = naive_utc(parsedate_to_datetime(value))
        return result if result > now else None
    except (ValueError, TypeError, OverflowError):
        return None
