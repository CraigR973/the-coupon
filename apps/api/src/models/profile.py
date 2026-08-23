from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    player = "player"
    admin = "admin"


class SiteRole(StrEnum):
    """Kept for compatibility with auth module — superadmin maps to admin role."""

    superadmin = "superadmin"
    user = "user"


class OddsFormat(StrEnum):
    """How a member reads prices. Display only — never affects scoring.

    Stored odds stay decimal ``Numeric(6, 2)`` and settlement keeps
    ``round(odds × 10)``, so two members of one league can read the same coupon
    in different notations and still be on the same points.
    """

    decimal = "decimal"
    fractional = "fractional"


class Profile(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    __tablename__ = "profiles"

    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: The bcrypt hash of this member's four-digit PIN, or ``NULL`` for *no credential*
    #: (Batch 66). ``NULL`` is only ever written by an admin PIN reset and only ever
    #: cleared by the member choosing a new one, and it means the account cannot be
    #: signed into at all — not that it can be signed into with anything. Every read
    #: path has to say which of the two it means; see ``src/services/credentials.py``.
    pin_hash: Mapped[str | None] = mapped_column(String(60), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="player_role", create_type=False),
        nullable=False,
        server_default="player",
    )
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default="UTC")
    odds_format: Mapped[OddsFormat] = mapped_column(
        Enum(OddsFormat, name="odds_format", create_type=False),
        nullable=False,
        server_default="decimal",
    )
    #: Where this member's profile picture lives, or ``NULL`` for the initials fallback
    #: every profile had before Batch 42. A URL rather than bytes: the image is held by
    #: an object store, and the database only remembers where. ``NULL`` is the normal
    #: state — most members never set one — so every read must handle it.
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
