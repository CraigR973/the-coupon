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
    pin_hash: Mapped[str] = mapped_column(String(60), nullable=False)
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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
