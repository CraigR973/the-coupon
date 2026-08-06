import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Match(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One real match with its score — the record The Coupon never kept (Batch 16).

    Scores were consumed and thrown away: ``settle_gameweek_via_provider`` reads a result
    from the odds provider, writes pick status and points, and keeps nothing. So there was
    no way to show a previous result or a run of form even for matches the game itself had
    settled — and no way at all for the rest of the card, because the slate has only ever
    fetched fixtures inside a league's window. Sunday, Monday and midweek games were never
    seen.

    This is therefore a *separate* record from :class:`~src.models.fixture.Fixture`, not an
    extension of it. A fixture is something a league can pick on; a match is something that
    happened. Most matches here are neither pickable nor picked, and a fixture is only a
    match once it kicks off.

    The two are related by team and kick-off, through
    :class:`~src.models.team.TeamAlias` — deliberately not by a foreign key, because the
    providers' event ids share no namespace and a fixture that is postponed out of the
    window still has a match row when it is eventually played.

    ``competition_id`` / ``competition`` are the **odds** provider's slug and display
    name, so a match, a fixture, and a standings row all describe a competition the same
    way. Scores stay ``NULL`` until ``finished``.
    """

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("provider_match_id", name="uq_matches_provider_match"),
        Index("ix_matches_competition_season_kickoff", "competition_id", "season", "kickoff_utc"),
        # Form is "this club's last five, either home or away", so both sides are
        # indexed with the kick-off that orders them.
        Index("ix_matches_home_team_kickoff", "home_team_id", "kickoff_utc"),
        Index("ix_matches_away_team_kickoff", "away_team_id", "kickoff_utc"),
    )

    provider_match_id: Mapped[str] = mapped_column(String(64), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(120), nullable=False)
    competition: Mapped[str] = mapped_column(String(120), nullable=False)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    home_team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    away_team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    home_goals: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: Terminal — the score is final. An in-play match carries a partial score, so this
    #: is the gate rather than the presence of goals.
    finished: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="")
