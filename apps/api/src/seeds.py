"""Small admin-only seed helpers.

These functions are intentionally boring: private users are created directly by
an operator, not through a public signup flow. Rename ``ADMIN_DISPLAY_NAME`` and
set ``ADMIN_PIN`` when you clone this template.
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.profile import Profile, UserRole

ADMIN_DISPLAY_NAME = "Admin"
ADMIN_TIMEZONE = "UTC"


def _validate_pin(pin: str) -> None:
    if len(pin) != 4 or not pin.isdecimal():
        raise ValueError("ADMIN_PIN must be exactly four digits")


def build_admin_profile(pin: str) -> Profile:
    _validate_pin(pin)
    return Profile(
        display_name=ADMIN_DISPLAY_NAME,
        pin_hash=hash_pin(pin),
        role=UserRole.admin,
        timezone=ADMIN_TIMEZONE,
        is_active=True,
    )


async def seed_admin_profile(db: AsyncSession, pin: str) -> Profile:
    """Create or update the private admin profile."""

    _validate_pin(pin)
    result = await db.execute(
        select(Profile).where(
            Profile.display_name == ADMIN_DISPLAY_NAME,
            Profile.deleted_at.is_(None),
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = build_admin_profile(pin)
        db.add(profile)
    else:
        profile.pin_hash = hash_pin(pin)
        profile.role = UserRole.admin
        profile.timezone = ADMIN_TIMEZONE
        profile.is_active = True
    await db.commit()
    await db.refresh(profile)
    return profile


async def _main() -> None:
    pin = os.environ.get("ADMIN_PIN")
    if pin is None:
        raise SystemExit("Set ADMIN_PIN to the admin's four-digit PIN before running this seed.")

    async with AsyncSessionLocal() as db:
        profile = await seed_admin_profile(db, pin)
        print(f"Seeded profile {profile.display_name} ({profile.id})")


if __name__ == "__main__":
    asyncio.run(_main())
