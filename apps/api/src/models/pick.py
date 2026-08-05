import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin
from src.models.league import PickScope


class PickMarket(StrEnum):
    """The two markets The Coupon offers. Values mirror
    :class:`src.services.odds_provider.Market` so a snapshotted selection round-trips by
    value, whichever provider priced it.
    """

    MATCH_ODDS = "MATCH_ODDS"
    BOTH_TEAMS_TO_SCORE = "BOTH_TEAMS_TO_SCORE"


class PickOutcome(StrEnum):
    """The selectable outcome within a market. HOME/DRAW/AWAY for Match Odds, YES/NO for
    BTTS. Values mirror :class:`src.services.odds_provider.Outcome`.
    """

    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"


class PickStatus(StrEnum):
    """``pending`` until the gameweek settles, then ``won`` / ``lost``; ``void`` when the
    fixture was postponed or abandoned, or the selection was withdrawn, so the pick scores
    nothing rather than counting as a loss.
    """

    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"


class Pick(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One member's single selection for a gameweek, scoped to a leaderboard.

    Three keys implement the game's core rules:

    * ``uq_picks_league_gameweek_player`` — **one pick per member per gameweek**.
    * ``uq_picks_league_gameweek_selection`` — **no two members hold the same selection**
      (the first-come land-grab). Keyed on ``(fixture, market, outcome)``.
    * ``uq_picks_league_gameweek_fixture`` — **no two members hold the same game**, for
      leagues on the fixture rule only. A *partial* unique index, because the rule is
      per-league and an index predicate cannot join to ``leagues`` — hence
      ``pick_scope`` denormalised onto each row at write time.

    The fixture key implies the selection key, so both hold in fixture mode and the
    selection key alone holds in selection mode.

    ``(fixture, market, outcome)`` is also how a pick settles. Revision ``005`` dropped
    the Betfair market and selection ids this table used to carry: that triple already
    identifies a selection exactly, so no provider's identifiers need to survive into the
    database, and settlement works the same whoever priced the fixture.

    Odds are frozen at pick time in ``odds_at_pick``. ``points_awarded`` stays null until
    the gameweek is settled.
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
        Index(
            "uq_picks_league_gameweek_fixture",
            "league_id",
            "gameweek_id",
            "fixture_id",
            unique=True,
            postgresql_where=text("pick_scope = 'fixture'"),
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
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[PickStatus] = mapped_column(
        Enum(PickStatus, name="pick_status", create_type=False),
        nullable=False,
        server_default="pending",
    )
    # Copied from the owning league when the pick is written. Only the partial
    # index above reads it — never treat it as the league's current setting.
    pick_scope: Mapped[PickScope] = mapped_column(
        Enum(PickScope, name="pick_scope", create_type=False),
        nullable=False,
        server_default="selection",
    )
