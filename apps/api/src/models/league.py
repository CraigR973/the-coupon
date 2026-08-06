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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class LeaguePrivacy(StrEnum):
    private = "private"
    public_request = "public_request"
    public_open = "public_open"


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
