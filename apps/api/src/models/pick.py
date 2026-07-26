import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class PickMarket(StrEnum):
    """The two markets The Coupon offers. Values mirror the Betfair market codes
    (:class:`src.services.betfair.Market`) so a snapshotted selection round-trips by value.
    """

    MATCH_ODDS = "MATCH_ODDS"
    BOTH_TEAMS_TO_SCORE = "BOTH_TEAMS_TO_SCORE"


class PickOutcome(StrEnum):
    """The selectable outcome within a market. HOME/DRAW/AWAY for Match Odds, YES/NO for
    BTTS. Values mirror :class:`src.services.betfair.Outcome`.
    """

    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"


class PickStatus(StrEnum):
    """``pending`` until the gameweek settles, then ``won`` / ``lost``; ``void`` when the
    Betfair runner was removed (e.g. a cancelled fixture) so the pick scores nothing.
    """

    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"


class Pick(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One member's single selection for a gameweek, scoped to a leaderboard.

    Two unique constraints implement the game's core rules:

    * ``uq_picks_league_gameweek_player`` — **one pick per member per gameweek**.
    * ``uq_picks_league_gameweek_selection`` — **no two members hold the same selection**
      (the first-come land-grab). Keyed on ``(fixture, market, outcome)`` rather than the
      Betfair selection id, which is only unique *within* a market (BTTS reuses the same
      Yes/No ids across every fixture).

    Odds are frozen at pick time in ``odds_at_pick`` (with the Betfair market/selection ids
    for settlement). ``points_awarded`` stays null until the gameweek is settled.
    """

    __tablename__ = "picks"
    __table_args__ = (
        UniqueConstraint(
            "league_id", "gameweek_id", "player_id", name="uq_picks_league_gameweek_player"
        ),
        UniqueConstraint(
            "league_id",
            "gameweek_id",
            "fixture_id",
            "market",
            "outcome",
            name="uq_picks_league_gameweek_selection",
        ),
        Index("ix_picks_league_gameweek", "league_id", "gameweek_id"),
        Index("ix_picks_player_id", "player_id"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    gameweek_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gameweeks.id", ondelete="CASCADE"), nullable=False
    )
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    market: Mapped[PickMarket] = mapped_column(
        Enum(PickMarket, name="pick_market", create_type=False), nullable=False
    )
    outcome: Mapped[PickOutcome] = mapped_column(
        Enum(PickOutcome, name="pick_outcome", create_type=False), nullable=False
    )
    runner_name: Mapped[str] = mapped_column(String(120), nullable=False)
    odds_at_pick: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    betfair_market_id: Mapped[str] = mapped_column(String(32), nullable=False)
    betfair_selection_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[PickStatus] = mapped_column(
        Enum(PickStatus, name="pick_status", create_type=False),
        nullable=False,
        server_default="pending",
    )
