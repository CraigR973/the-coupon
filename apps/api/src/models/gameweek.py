import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class GameweekStatus(StrEnum):
    """Lifecycle of a round.

    ``open`` — picks accepted; ``locked`` — the deadline passed, picks frozen;
    ``settled`` — provider results in, points awarded.
    """

    open = "open"
    locked = "locked"
    settled = "settled"


class Gameweek(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One round of one league.

    **Per-league since Batch 14.** It was global — one row per Saturday, shared by
    every leaderboard — which meant two leagues could not play different fixtures.
    Now each league owns its own rounds and selects fixtures from the shared pool
    through :class:`GameweekFixture`, so two leagues can run different cards, on
    different days, at the same time.

    ``starts_on`` is the date the league's slate window opens (it was
    ``saturday_date`` until Batch 14, which is no longer true for a league playing
    Friday to Monday). Uniqueness is ``(league, starts_on)``: one round per league
    per window, rather than one round per Saturday for everyone.

    ``locks_at_utc`` is derived from the league's ``lock_offset_minutes`` before the
    window opens, stored naive-UTC like every ``*_utc`` column.
    """

    __tablename__ = "gameweeks"
    __table_args__ = (
        UniqueConstraint("league_id", "starts_on", name="uq_gameweeks_league_starts_on"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[GameweekStatus] = mapped_column(
        Enum(GameweekStatus, name="gameweek_status", create_type=False),
        nullable=False,
        server_default="open",
    )
    locks_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class GameweekFixture(Base):
    """Which pool fixtures a league's round is playing.

    The join that makes the fixture pool shared. Before Batch 14 a fixture belonged
    to exactly one gameweek (``fixtures.gameweek_id``), so the same real match could
    not appear on two leagues' cards without being stored twice — and storing it
    twice would have meant fetching it twice against the provider's rate limit.

    Composite primary key, no surrogate id: the pair *is* the fact.
    """

    __tablename__ = "gameweek_fixtures"

    gameweek_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gameweeks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        primary_key=True,
    )
