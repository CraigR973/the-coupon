import uuid

from sqlalchemy import ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Standing(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One club's line in one competition's table, for one season (Batch 16).

    Stored as published rather than computed from :class:`~src.models.match.Match`.
    A table is not a sum of results: points deductions, expunged records, and
    ordering rules (head-to-head in Scotland, goal difference in England) are the
    competition's, and reproducing them from scores would produce a table that
    quietly disagrees with the official one.

    ``updated_at`` (from the mixin) is what the screens show as "as of", and what the
    ingestion job orders by when it has more competitions than its per-run budget.

    Goal difference is not stored — it is ``goals_for - goals_against`` and a stored
    copy is one more thing that can disagree with its inputs.
    """

    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "season", "team_id", name="uq_standings_competition_season_team"
        ),
        Index("ix_standings_competition_season_position", "competition_id", "season", "position"),
    )

    #: The **odds** provider's slug, matching ``fixtures.competition_id``.
    competition_id: Mapped[str] = mapped_column(String(120), nullable=False)
    competition: Mapped[str] = mapped_column(String(120), nullable=False)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    played: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    won: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    drawn: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    lost: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    goals_for: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    goals_against: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    points: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    #: The table's own form string, most recent last. Display falls back to form derived
    #: from ``matches``, so this is kept for fidelity rather than relied on.
    form: Mapped[str] = mapped_column(String(10), nullable=False, server_default="")
