import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class LeaguePrivacy(StrEnum):
    private = "private"
    public_request = "public_request"
    public_open = "public_open"


class PickMarket(StrEnum):
    """The two markets The Coupon can offer. Values mirror
    :class:`src.services.odds_provider.Market` so a snapshotted selection round-trips by
    value, whichever provider priced it.

    Defined here rather than on :class:`~src.models.pick.Pick` (which re-exports it)
    because a league now *chooses* which of these it offers — ``League.offered_markets``
    — so the enum is a league-configuration concept, not only a pick one.
    """

    MATCH_ODDS = "MATCH_ODDS"
    BOTH_TEAMS_TO_SCORE = "BOTH_TEAMS_TO_SCORE"


class PickScope(StrEnum):
    """How much of a fixture one member's claim takes.

    ``selection`` is the original rule: a member claims exactly one
    ``(fixture, market, outcome)`` and other members may claim the rest of that
    game. ``fixture`` makes a claim take the whole game.

    The choice is per-league and shrinks the pick pool roughly fivefold, which
    matters when the roster is large relative to the slate.
    """

    selection = "selection"
    fixture = "fixture"


#: `date.weekday()` — Monday is 0, Saturday is 5.
SATURDAY = 5
#: 15:00, as minutes from midnight — the kick-off the product was built around.
THREE_PM = 15 * 60
#: Picks lock this long before the window opens. 30 minutes before 15:00 is 14:30.
DEFAULT_LOCK_OFFSET_MINUTES = 30
#: The market set every league offered before Batch 15, and the default a new one gets.
DEFAULT_OFFERED_MARKETS: tuple[PickMarket, ...] = (
    PickMarket.MATCH_ODDS,
    PickMarket.BOTH_TEAMS_TO_SCORE,
)


class League(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    __tablename__ = "leagues"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_leagues_slug"),
        CheckConstraint(
            "max_members BETWEEN 2 AND 50",
            name="ck_leagues_max_members_range",
        ),
        CheckConstraint(
            "slate_start_weekday BETWEEN 0 AND 6 AND slate_end_weekday BETWEEN 0 AND 6",
            name="ck_leagues_slate_weekdays",
        ),
        CheckConstraint(
            "slate_start_minute BETWEEN 0 AND 1439 AND slate_end_minute BETWEEN 0 AND 1439",
            name="ck_leagues_slate_minutes",
        ),
        CheckConstraint(
            "lock_offset_minutes >= 0",
            name="ck_leagues_lock_offset_non_negative",
        ),
        # Picks cannot open after they lock, or the round could never be played.
        # NULL is "no announced opening", not an offset of zero, so it is exempt.
        CheckConstraint(
            "pick_open_offset_minutes IS NULL "
            "OR pick_open_offset_minutes >= lock_offset_minutes",
            name="ck_leagues_pick_open_before_lock",
        ),
        CheckConstraint(
            "cardinality(offered_markets) >= 1",
            name="ck_leagues_offered_markets_nonempty",
        ),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy: Mapped[LeaguePrivacy] = mapped_column(
        Enum(LeaguePrivacy, name="league_privacy", create_type=False),
        nullable=False,
        server_default="private",
    )
    max_members: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15")
    pick_scope: Mapped[PickScope] = mapped_column(
        Enum(PickScope, name="pick_scope", create_type=False),
        nullable=False,
        server_default="selection",
    )

    # ── What this league offers (Batch 15) ────────────────────────────────────
    #
    # ``competitions`` is the competition selection. ``None`` is the group *all UK
    # leagues* — the rule the slate always used — so an unset league is unchanged.
    # A non-null value is an explicit ``[{"slug", "name"}]`` list and the round plays
    # only those, filtered at link time in ``sync_slate``. A value blob rather than a
    # join table because it is read and written whole, never queried by competition,
    # and kept small by the provider's rate limit.
    #
    # ``offered_markets`` is which of the two markets the league offers — a subset of
    # the existing ``pick_market`` enum, never new values (widening the markets
    # themselves would be a migration). The check keeps it non-empty.
    competitions: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    offered_markets: Mapped[list[PickMarket]] = mapped_column(
        ARRAY(Enum(PickMarket, name="pick_market", create_type=False)),
        nullable=False,
        server_default=sa.text("ARRAY['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE']::pick_market[]"),
    )

    # ── The weekly window this league plays (Batch 14) ────────────────────────
    #
    # A range from (start weekday, start minute) to (end weekday, end minute) in
    # Europe/London, plus how long before it opens picks lock. The defaults are
    # exactly the rule the product shipped with: a single Saturday 15:00 kick-off
    # locking at 14:30, expressed as a degenerate range whose start equals its end.
    # Storing a *range* rather than one kick-off time is what lets Batch 15 offer
    # "Friday 19:00 to Monday 22:00" as configuration rather than a migration.
    slate_start_weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=str(SATURDAY)
    )
    slate_start_minute: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=str(THREE_PM)
    )
    slate_end_weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=str(SATURDAY)
    )
    slate_end_minute: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=str(THREE_PM)
    )
    lock_offset_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_LOCK_OFFSET_MINUTES)
    )
    # How long before the window opens picks *open* (Batch 27) — the far end of the
    # claim period whose near end is ``lock_offset_minutes``. Measured the same way, so
    # a bigger number is earlier and the two are directly comparable. ``NULL`` means the
    # league announces no opening and a round is claimable the moment discovery writes
    # it, which is what every round did before this column existed.
    pick_open_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False
    )
    join_code: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
        unique=True,
        server_default=sa.text("upper(substr(md5(random()::text), 1, 6))"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
