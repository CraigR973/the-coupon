"""Small admin-only seed helpers.

These functions are intentionally boring: private users are created directly by
an operator, not through a public signup flow. Rename ``ADMIN_DISPLAY_NAME`` and
set ``ADMIN_PIN`` when you clone this template.
"""

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.league import League, LeaguePrivacy
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole

ADMIN_DISPLAY_NAME = "Admin"
ADMIN_TIMEZONE = "UTC"
DEFAULT_LEAGUE_SLUG = "the-coupon"
DEFAULT_LEAGUE_NAME = "The Coupon"


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


@dataclass(frozen=True)
class BootstrapPlayer:
    display_name: str
    pin: str
    role: UserRole = UserRole.player
    timezone: str = "Europe/London"
    league_role: LeagueMemberRole = LeagueMemberRole.player


@dataclass(frozen=True)
class BootstrapSummary:
    profiles_created: int
    profiles_updated: int
    memberships_created: int
    memberships_restored: int
    league_slug: str


def _player_from_mapping(raw: object) -> BootstrapPlayer:
    if not isinstance(raw, dict):
        raise ValueError("Each roster item must be an object")
    display_name = str(raw.get("display_name", "")).strip()
    pin = str(raw.get("pin", "")).strip()
    if not display_name:
        raise ValueError("Roster display_name is required")
    _validate_pin(pin)
    role = UserRole(str(raw.get("role", UserRole.player.value)))
    league_role = LeagueMemberRole(str(raw.get("league_role", LeagueMemberRole.player.value)))
    timezone = str(raw.get("timezone", "Europe/London")).strip() or "Europe/London"
    return BootstrapPlayer(
        display_name=display_name,
        pin=pin,
        role=role,
        timezone=timezone,
        league_role=league_role,
    )


def load_roster(path: Path) -> list[BootstrapPlayer]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_players = data.get("players") if isinstance(data, dict) else data
    if not isinstance(raw_players, list) or not raw_players:
        raise ValueError("Roster JSON must contain a non-empty players array")
    return [_player_from_mapping(item) for item in raw_players]


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


async def bootstrap_league(
    db: AsyncSession,
    *,
    admin_pin: str,
    roster: list[BootstrapPlayer],
    league_slug: str = DEFAULT_LEAGUE_SLUG,
    league_name: str = DEFAULT_LEAGUE_NAME,
) -> BootstrapSummary:
    admin = await seed_admin_profile(db, admin_pin)
    by_name = {player.display_name: player for player in roster}
    by_name[admin.display_name] = BootstrapPlayer(
        display_name=admin.display_name,
        pin=admin_pin,
        role=UserRole.admin,
        timezone=admin.timezone,
        league_role=LeagueMemberRole.admin,
    )

    created = 0
    updated = 0
    profiles: dict[str, Profile] = {admin.display_name: admin}
    for player in by_name.values():
        if player.display_name == admin.display_name:
            continue
        result = await db.execute(
            select(Profile).where(
                Profile.display_name == player.display_name,
                Profile.deleted_at.is_(None),
            )
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = Profile(
                display_name=player.display_name,
                pin_hash=hash_pin(player.pin),
                role=player.role,
                timezone=player.timezone,
                is_active=True,
            )
            db.add(profile)
            created += 1
        else:
            profile.pin_hash = hash_pin(player.pin)
            profile.role = player.role
            profile.timezone = player.timezone
            profile.is_active = True
            profile.failed_login_count = 0
            profile.locked_until = None
            updated += 1
        profiles[player.display_name] = profile

    await db.flush()

    league = (
        await db.execute(
            select(League).where(League.slug == league_slug, League.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if league is None:
        league = League(
            slug=league_slug,
            name=league_name,
            description="Private weekly football accumulator.",
            privacy=LeaguePrivacy.private,
            max_members=max(15, len(by_name)),
            created_by=admin.id,
        )
        db.add(league)
    else:
        league.name = league_name
        league.privacy = LeaguePrivacy.private
        league.max_members = max(league.max_members, len(by_name))
    await db.flush()

    memberships_created = 0
    memberships_restored = 0
    for player in by_name.values():
        profile = profiles[player.display_name]
        membership = (
            await db.execute(
                select(LeagueMembership).where(
                    LeagueMembership.league_id == league.id,
                    LeagueMembership.player_id == profile.id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=profile.id,
                    role=player.league_role,
                )
            )
            memberships_created += 1
        else:
            membership.role = player.league_role
            if membership.deleted_at is not None:
                membership.deleted_at = None
                memberships_restored += 1

    await db.commit()
    return BootstrapSummary(
        profiles_created=created,
        profiles_updated=updated,
        memberships_created=memberships_created,
        memberships_restored=memberships_restored,
        league_slug=league_slug,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap The Coupon profiles and league.")
    parser.add_argument("--roster", type=Path, required=True, help="JSON roster with players[]")
    parser.add_argument("--league-slug", default=DEFAULT_LEAGUE_SLUG)
    parser.add_argument("--league-name", default=DEFAULT_LEAGUE_NAME)
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    pin = os.environ.get("ADMIN_PIN")
    if pin is None:
        raise SystemExit("Set ADMIN_PIN to the admin's four-digit PIN before running this seed.")

    async with AsyncSessionLocal() as db:
        summary = await bootstrap_league(
            db,
            admin_pin=pin,
            roster=load_roster(args.roster),
            league_slug=args.league_slug,
            league_name=args.league_name,
        )
        print(
            "Bootstrap complete: "
            f"league={summary.league_slug} "
            f"profiles_created={summary.profiles_created} "
            f"profiles_updated={summary.profiles_updated} "
            f"memberships_created={summary.memberships_created} "
            f"memberships_restored={summary.memberships_restored}"
        )


if __name__ == "__main__":
    asyncio.run(_main())
