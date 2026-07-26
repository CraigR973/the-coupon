from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class GameweekStatus(StrEnum):
    """Lifecycle of a weekly round.

    ``open`` — picks accepted; ``locked`` — 14:30 Saturday passed, picks frozen;
    ``settled`` — Betfair results in, points awarded.
    """

    open = "open"
    locked = "locked"
    settled = "settled"


class Gameweek(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One Saturday's slate — the weekly round every leaderboard plays.

    Global (not per-league): the fixtures are the same for everyone. Uniqueness is
    the Saturday's date, so a slate is synced once and shared. ``locks_at_utc`` is
    14:30 UK local for that Saturday, stored as naive UTC like every ``*_utc`` column.
    """

    __tablename__ = "gameweeks"
    __table_args__ = (UniqueConstraint("saturday_date", name="uq_gameweeks_saturday_date"),)

    saturday_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[GameweekStatus] = mapped_column(
        Enum(GameweekStatus, name="gameweek_status", create_type=False),
        nullable=False,
        server_default="open",
    )
    locks_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
