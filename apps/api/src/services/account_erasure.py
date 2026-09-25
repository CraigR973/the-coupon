"""A member deletes their own account, or takes their data with them. Batch 136.

Since Batch 74 the login identifier is a real name, and the product is UK-facing: a
member who wants to leave was owed both erasure and a copy of their data, and had
neither — only a site-admin soft delete that deliberately keeps the name reserved.

**The owner's decisions.** 2026-09-22: anonymise and keep history — the member disappears
from view and their name is freed for reuse, while their settled points still sum into
historic standings so past leagues stay coherent. 2026-09-25: erase *everything* that
names them; show them as "Former member"; take effect immediately once they re-enter
their PIN; and refuse while they are the only admin of a league somebody else still
plays in.

**How the history stays coherent.** Standings count active memberships, so the
memberships are kept — ending them would take the member's points out of every past
table. What makes them absent everywhere else is the profile: ``deleted_at`` and
``is_active`` are exactly what the site-admin delete sets, and every roster, reminder and
round-progress read already skips such a profile.

**Why a stored placeholder, not just a label.** ``profiles.display_name`` is unique, so
the real name cannot stay and cannot be shared: it is overwritten with ``Former member``
plus eight random hex digits, and the read paths members see map that to plain "Former
member". A read that somebody forgets to map therefore shows the placeholder — never the
name. The privacy guarantee is the overwrite; the label is presentation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.display_name import FORMER_MEMBER, former_member_placeholder
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek
from src.models.invite import Invite
from src.models.league import League
from src.models.league_join_request import LeagueJoinRequest
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.notification import (
    ActionType,
    ActorType,
    AuditLog,
    NotificationPreferences,
    PushSubscription,
)
from src.models.pick import Pick
from src.models.profile import OddsFormat, Profile
from src.models.rate_limit import RateLimitCounter
from src.models.refresh_token import RefreshToken
from src.services.avatar_storage import AvatarStorage


class SoleAdminError(Exception):
    """Deletion refused: leaving would strand leagues other members still play in."""

    def __init__(self, leagues: Sequence[str]) -> None:
        super().__init__(", ".join(leagues))
        self.leagues = list(leagues)


async def leagues_they_alone_run(db: AsyncSession, member_id: uuid.UUID) -> list[str]:
    """Leagues where this member is the only admin and at least one other member plays."""
    live_other = (
        select(LeagueMembership.league_id, LeagueMembership.role)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .where(
            LeagueMembership.player_id != member_id,
            LeagueMembership.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
        .subquery()
    )
    rows = await db.execute(
        select(League.name)
        .join(LeagueMembership, LeagueMembership.league_id == League.id)
        .join(live_other, live_other.c.league_id == League.id)
        .where(
            LeagueMembership.player_id == member_id,
            LeagueMembership.role == LeagueMemberRole.admin,
            LeagueMembership.deleted_at.is_(None),
            League.deleted_at.is_(None),
        )
        .group_by(League.id, League.name)
        .having(func.sum(case((live_other.c.role == LeagueMemberRole.admin, 1), else_=0)) == 0)
        .order_by(League.name)
    )
    return [name for (name,) in rows.all()]


def _scrub(value: Any, names: set[str]) -> Any:
    """Replace every string that is one of the member's names, however deeply nested."""
    if isinstance(value, str):
        return FORMER_MEMBER if value.casefold() in names else value
    if isinstance(value, list):
        return [_scrub(item, names) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item, names) for key, item in value.items()}
    return value


async def erase_account(db: AsyncSession, member: Profile, storage: AvatarStorage) -> None:
    """Remove everything that names ``member``, keeping only anonymous scoring rows.

    Raises :class:`SoleAdminError` before changing anything if leaving would strand a
    league. Does not commit — the caller owns the transaction, so the erasure lands whole
    or not at all.
    """
    stranded = await leagues_they_alone_run(db, member.id)
    if stranded:
        raise SoleAdminError(stranded)

    memberships = list(
        (
            await db.execute(
                select(LeagueMembership).where(LeagueMembership.player_id == member.id)
            )
        ).scalars()
    )
    invites = list(
        (await db.execute(select(Invite).where(Invite.claimed_by == member.id))).scalars()
    )
    names = {member.display_name}
    names |= {m.display_name_override for m in memberships if m.display_name_override}
    names |= {i.display_name_hint for i in invites if i.display_name_hint}
    folded = {name.casefold() for name in names}

    # Audit entries about or by them. The ids stay — they name nobody now — and any
    # string that was one of their names becomes "Former member".
    linked = [member.id, *(m.id for m in memberships)]
    audits = (
        await db.execute(
            select(AuditLog).where(
                or_(AuditLog.actor_id == member.id, AuditLog.target_id.in_(linked))
            )
        )
    ).scalars()
    for audit in audits:
        if audit.changes:
            scrubbed = _scrub(audit.changes, folded)
            if scrubbed != audit.changes:
                audit.changes = scrubbed

    # The name somebody typed when inviting them, whether or not the invite was used.
    for invite in (
        await db.execute(
            select(Invite).where(
                or_(
                    Invite.claimed_by == member.id,
                    func.lower(Invite.display_name_hint).in_(folded),
                )
            )
        )
    ).scalars():
        invite.display_name_hint = None

    # Kept, so their points stay in every table they were earned in — but without the
    # name they chose for each league.
    for membership in memberships:
        membership.display_name_override = None

    await db.execute(delete(LeagueJoinRequest).where(LeagueJoinRequest.player_id == member.id))
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == member.id))
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == member.id))
    await db.execute(
        delete(NotificationPreferences).where(NotificationPreferences.user_id == member.id)
    )
    # Login throttles are keyed ``login:<name>:<address>`` — a name and an IP address.
    await db.execute(
        delete(RateLimitCounter).where(
            or_(
                *(
                    RateLimitCounter.bucket_key.startswith(f"login:{name}:", autoescape=True)
                    for name in folded
                )
            )
        )
    )

    if member.avatar_url:
        await storage.delete(player_id=str(member.id))
    now = datetime.now(UTC).replace(tzinfo=None)
    member.display_name = former_member_placeholder()
    member.avatar_url = None
    member.pin_hash = None
    member.is_active = False
    member.deleted_at = now
    member.failed_login_count = 0
    member.locked_until = None
    member.timezone = "UTC"
    member.odds_format = OddsFormat.decimal
    member.updated_at = now

    db.add(
        AuditLog(
            actor_id=member.id,
            actor_type=ActorType.player,
            # No "account erased" value exists and adding one is an irreversible
            # ``ALTER TYPE``; ``member_removed`` against ``profiles`` is the nearest true
            # thing, as the site-admin delete records itself, and the scope says which.
            action_type=ActionType.member_removed,
            target_table="profiles",
            target_id=member.id,
            changes={"scope": "self_erasure"},
        )
    )
    await db.flush()


async def export_account(db: AsyncSession, member: Profile) -> dict[str, Any]:
    """Everything the product holds about ``member``, and nothing about anybody else.

    Other members appear nowhere: a pick lists its own fixture, market, price and result,
    never who else picked. Credentials are left out — the PIN hash and the push
    endpoint's keys are secrets, not information about the member.
    """
    memberships = (
        await db.execute(
            select(LeagueMembership, League.name, League.slug)
            .join(League, League.id == LeagueMembership.league_id)
            .where(LeagueMembership.player_id == member.id)
            .order_by(LeagueMembership.joined_at)
        )
    ).all()
    picks = (
        await db.execute(
            select(Pick, League.name, Gameweek.starts_on, Fixture)
            .join(League, League.id == Pick.league_id)
            .join(Gameweek, Gameweek.id == Pick.gameweek_id)
            .join(Fixture, Fixture.id == Pick.fixture_id)
            .where(Pick.player_id == member.id)
            .order_by(Gameweek.starts_on, League.name)
        )
    ).all()
    prefs = (
        await db.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == member.id)
        )
    ).scalar_one_or_none()
    sessions = (
        await db.execute(
            select(RefreshToken.device_hint, RefreshToken.expires_at).where(
                RefreshToken.user_id == member.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    ).all()
    devices = (
        await db.execute(
            select(PushSubscription.device_hint, PushSubscription.is_active).where(
                PushSubscription.user_id == member.id
            )
        )
    ).all()

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "display_name": member.display_name,
            "role": member.role.value,
            "timezone": member.timezone,
            "odds_format": member.odds_format.value,
            "has_profile_picture": member.avatar_url is not None,
            "created_at": member.created_at.isoformat() if member.created_at else None,
        },
        "leagues": [
            {
                "league": name,
                "slug": slug,
                "role": membership.role.value,
                "your_name_in_this_league": membership.display_name_override,
                "notifications_muted": membership.notification_muted,
                "joined_at": membership.joined_at.isoformat(),
                "left_at": membership.deleted_at.isoformat() if membership.deleted_at else None,
            }
            for membership, name, slug in memberships
        ],
        "picks": [
            {
                "league": league_name,
                "round_starts_on": starts_on.isoformat(),
                "fixture": f"{fixture.home} v {fixture.away}",
                "kickoff_utc": fixture.kickoff_utc.isoformat(),
                "competition": fixture.competition,
                "market": pick.market.value,
                "selection": pick.runner_name,
                "odds": str(pick.odds_at_pick),
                "status": pick.status.value,
                "points": pick.points_awarded,
            }
            for pick, league_name, starts_on, fixture in picks
        ],
        "notification_preferences": None
        if prefs is None
        else {
            "global_mute": prefs.global_mute,
            "quiet_hours_start": prefs.quiet_hours_start.time().isoformat()
            if prefs.quiet_hours_start
            else None,
            "quiet_hours_end": prefs.quiet_hours_end.time().isoformat()
            if prefs.quiet_hours_end
            else None,
        },
        "signed_in_devices": [
            {"device": hint, "session_expires_at": expires.isoformat()}
            for hint, expires in sessions
        ],
        "push_devices": [{"device": hint, "active": active} for hint, active in devices],
    }
