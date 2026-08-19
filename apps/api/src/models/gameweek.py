import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class GameweekStatus(StrEnum):
    """Lifecycle of a round.

    ``scheduled`` — the round exists but picks are not claimable yet;
    ``open`` — picks accepted; ``locked`` — the deadline passed, picks frozen;
    ``settled`` — provider results in, points awarded.

    ``scheduled`` arrived with Batch 27. Until then ``open`` meant both "this round
    has been discovered" and "you may claim on it", because a round became claimable
    the moment discovery wrote it — an instant no member could predict. A league that
    announces when picks open needs the two to be separate states.
    """

    scheduled = "scheduled"
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

    ``picks_open_at_utc`` is the other end of the same claim period (Batch 27), derived
    from ``pick_open_offset_minutes``. ``NULL`` is the rule every round had before it
    existed — claimable as soon as discovery writes the row — so an unconfigured league
    is unchanged. Neither instant is re-derived once a round exists: a window change
    applies to rounds discovered from then on, exactly as it always has.
    """

    __tablename__ = "gameweeks"
    __table_args__ = (
        UniqueConstraint("league_id", "starts_on", name="uq_gameweeks_league_starts_on"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: What members call this round — "Gameweek 12" (Batch 41). Assigned at discovery as
    #: one past the highest number the league already holds *in the same season*, so a
    #: round inserted mid-sequence takes the next number rather than renumbering history.
    #: Nullable because a round discovered before Batch 41 may predate the backfill, and
    #: because nothing may depend on it: locking, settlement and scoring all key on
    #: instants and status, never on this. Purely what the round is called.
    #:
    #: No database constraint enforces uniqueness, because the season it is unique
    #: *within* is derived from ``starts_on`` rather than stored. The invariant lives in
    #: ``next_gameweek_number``.
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[GameweekStatus] = mapped_column(
        Enum(GameweekStatus, name="gameweek_status", create_type=False),
        nullable=False,
        server_default="open",
    )
    locks_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    picks_open_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
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
