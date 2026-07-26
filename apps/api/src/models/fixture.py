import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Fixture(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One match on a gameweek's Saturday slate.

    Mapped from a Betfair :class:`~src.services.betfair.SlateFixture`; ``home`` / ``away``
    are the team names Betfair supplies directly (no separate Team table). Unique per
    ``(gameweek, betfair_event_id)`` so re-syncing the slate is idempotent. Odds are not
    stored here — they are snapshotted onto each :class:`~src.models.pick.Pick` at pick
    time, so the offerable selections come live from the adapter.
    """

    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint("gameweek_id", "betfair_event_id", name="uq_fixtures_gameweek_event"),
    )

    gameweek_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gameweeks.id", ondelete="CASCADE"), nullable=False
    )
    betfair_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    home: Mapped[str] = mapped_column(String(120), nullable=False)
    away: Mapped[str] = mapped_column(String(120), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    competition: Mapped[str] = mapped_column(String(120), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(32), nullable=False)
