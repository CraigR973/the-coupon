"""Domain notification triggers — thin wrappers over ``send_notification``.

Batch 1 kept only the league-membership trigger the leagues routers call; Batch 4 adds the
pick-reminder trigger the scheduler drives. Each decides *who* to notify and with what copy;
``send_notification`` enforces per-member mute / quiet hours and does the delivery.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.gameweek_completion import GameweekCompletion
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import Profile, UserRole
from src.services.fotmob_health import FotMobAlert
from src.services.gameweek import RoundProgress, members_missing_picks, notification_targets
from src.services.push_notification_service import send_notification
from src.services.round_completion import claim_pending_completion, mark_delivered

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def _admin_players(session: AsyncSession) -> Sequence[Profile]:
    """Active, non-deleted admin profiles — recipients for admin alerts."""
    result = await session.execute(
        select(Profile).where(
            Profile.role == UserRole.admin,
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
    )
    return result.scalars().all()


async def notify_member_joined(
    session: AsyncSession,
    player_name: str,
    league_name: str,
    league_id: uuid.UUID,
) -> None:
    """Notify admins when an existing player joins a league via code or invite.

    ``league_id`` is required rather than optional, which is the point of Batch 85. This
    was the one trigger Batch 76 did not update, so a site admin who had muted a league
    still got its "New member" push — the message names the league in both its title and
    its body, so it is exactly the kind ``send_notification``'s league gate exists for.
    Leaving the parameter defaulted would have let a fourth call site reintroduce the
    same omission silently.
    """
    for admin in await _admin_players(session):
        await send_notification(
            session,
            admin.id,
            f"New member: {league_name}",
            f"{player_name} has joined {league_name}.",
            timezone_name=admin.timezone,
            league_id=league_id,
        )


#: How long one football-provider alert silences the next. A blocked source answers every
#: request the same way and the live-scores job runs every ten minutes, so without this the
#: first bad Saturday is a hundred identical pushes. The loud cases get the shorter window
#: because they are the ones where being told again an hour later is still useful.
FOOTBALL_PROVIDER_ALERT_COOLDOWN = timedelta(hours=1)
FOOTBALL_PROVIDER_QUIET_COOLDOWN = timedelta(hours=6)


async def notify_football_provider_trouble(session: AsyncSession, alert: FotMobAlert) -> bool:
    """Record that the football data source has bitten, and tell the admins. Batch 101.

    Returns whether anything was written — ``False`` means an identical-enough alert is
    still inside its cooldown, which is the normal answer during an outage rather than a
    failure. The caller logs either way; this decides only whether to make a noise.

    The row goes down *with* the push and not instead of it. The push is what reaches a
    person on the day; the row is what is still there on Monday when somebody asks how
    long this has been happening, and it is what the cooldown above reads — so the
    silence survives a redeploy, which an in-process timer would not.
    """
    cooldown = FOOTBALL_PROVIDER_ALERT_COOLDOWN if alert.loud else FOOTBALL_PROVIDER_QUIET_COOLDOWN
    since = datetime.now(UTC).replace(tzinfo=None) - cooldown
    recent = await session.execute(
        select(AuditLog.id)
        .where(
            AuditLog.action_type == ActionType.football_provider_degraded,
            AuditLog.timestamp >= since,
        )
        .limit(1)
    )
    if recent.scalar_one_or_none() is not None:
        return False

    session.add(
        AuditLog(
            actor_id=None,
            actor_type=ActorType.system,
            action_type=ActionType.football_provider_degraded,
            target_table="",
            target_id=None,
            changes={"trouble": str(alert.trouble), "detail": alert.detail},
        )
    )
    if alert.loud:
        for admin in await _admin_players(session):
            await send_notification(
                session,
                admin.id,
                alert.title,
                alert.detail,
                timezone_name=admin.timezone,
            )
    return True


def _lock_label(locks_at_utc: datetime, timezone_name: str) -> str:
    """The deadline on the member's own clock, as ``Sat 14:30``.

    The copy said "14:30" flat until Batch 30. Lock time has been per-league since
    Batch 14 and admin-configurable since Batch 15, so a constant is simply wrong for
    a league playing Friday to Monday — and the reminder can precede the deadline by
    more than a day, which is why the weekday is named too. Unknown timezones fall back
    to UTC, matching ``push_notification_service``.
    """
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return locks_at_utc.replace(tzinfo=UTC).astimezone(zone).strftime("%a %H:%M")


async def send_pick_reminders(session: AsyncSession, gameweek: Gameweek) -> int:
    """Push a reminder to every active member who hasn't picked for ``gameweek``.

    Returns the number of members nudged (a member in N leagues without a pick is nudged
    once per league). ``send_notification`` honours each member's mute / quiet hours, so a
    suppressed recipient is still counted here — this reports who was *targeted*, and the
    delivery layer decides what actually goes out.

    The ``url`` is the point of naming the league in the body: before Batch 30 no address
    in the app named a league's coupon, so ``sw.ts`` fell back to ``/`` and a reminder about
    league B dropped the member on a list of every league they play.
    """
    reminded = 0
    for member in await members_missing_picks(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            "Pick due",
            f"You haven't made your pick in {member.league_name} yet — "
            f"picks lock {_lock_label(gameweek.locks_at_utc, member.timezone)}.",
            data={
                "type": "pick_reminder",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"pick-reminder-{member.league_id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        reminded += 1
    return reminded


async def notify_picks_open(session: AsyncSession, gameweek: Gameweek) -> int:
    """Tell a league its round is now claimable. Batch 76.

    ``run_open_gameweeks`` has flipped ``scheduled -> open`` hourly since Batch 27 and
    returned the rounds it moved; it simply told nobody. This is that missing half.

    **Dead code in 2-1 Hibs until the owner sets an offset**, and shipped anyway. That
    league has ``pick_open_offset_minutes`` unset, so its rounds are born ``open`` at
    discovery and ``open_due_gameweeks`` will never move one — there is no opening instant
    to announce. It is correct for ``the-coupon``, which carries the offset already.

    Everyone active and unmuted is told, not only those without a pick: nobody can hold a
    pick in a round that has this instant only just passed.
    """
    told = 0
    for member in await notification_targets(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            "Picks are open",
            f"The coupon is open in {member.league_name} — "
            f"picks lock {_lock_label(gameweek.locks_at_utc, member.timezone)}.",
            data={
                "type": "picks_open",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"picks-open-{member.league_id}-{gameweek.id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        told += 1
    return told


#: The fragment the web app answers its copy section at.
#:
#: Batch 105 merged the combined coupon into the current round and made this the section's
#: one address — ``COUPON_SECTION_ID`` in ``apps/web/src/lib/leagues.ts``, exported there
#: precisely so the anchor, the redirect and this link cannot drift apart. A notification
#: is the only place outside that module where the address gets minted by hand, which is
#: why it is a named constant here and asserted in a test rather than typed into an
#: f-string.
COUPON_SECTION_HASH = "#coupon"


def coupon_section_url(league_slug: str, gameweek_id: uuid.UUID) -> str:
    """A deep link to one round's copy section — the completion alert's destination.

    Both halves of the address are load-bearing. The gameweek id is league-scoped, so it
    only resolves against the league it came from; and the round has to be named because
    "all picks are in" is worth reading after the coupon has moved on, at which point the
    league's *current* round is a different one.
    """
    return f"/leagues/{league_slug}/predictions?gw={gameweek_id}{COUPON_SECTION_HASH}"


async def notify_pick_made(
    session: AsyncSession,
    gameweek: Gameweek,
    picker_id: uuid.UUID,
    picker_name: str,
    selection: str,
    odds: Decimal,
    *,
    moved: bool,
    progress: RoundProgress,
) -> int:
    """Tell the rest of the league somebody claimed — or moved. Batch 76, reworded in 107.

    The event the game is actually built around: the coupon is a land-grab, and until
    Batch 76 nothing announced a grab. ``moved`` carries the more useful half — a member
    switching frees their old selection back into the pool, and nothing in the product
    said so.

    **The copy is one line now.** It read
    ``New pick in 2-1 Hibs`` / ``Dave took Arsenal at 1.80 in 2-1 Hibs.`` — which named
    the league twice, in a tray entry that is already league-scoped, and spent both of
    them saying nothing a member wanted. It now reads
    ``2-1 Hibs`` / ``Dave picked Arsenal @ 1.80 · 3/12 picked``: the league once, in the
    title where the tray puts it, and the recovered room given to the thing nobody could
    previously find out from a phone — how close the coupon is to being worth copying.

    **None of this is a disclosure.** ``routers/gameweek.py``'s ``_gameweek_members``
    already serves every member's pick, the holder's name and the frozen price to any
    member of that league *before* lock, because the land-grab is unreadable otherwise.
    This says on a phone what the screen already says.

    ``odds`` is ``Pick.odds_at_pick`` — the price frozen onto the row at claim time, never
    a live quote. A winning pick scores ``round(odds × 10)`` against that stored number, so
    an alert quoting anything else would be quoting a score nobody gets. ``progress`` is
    passed in for the same reason: the submitting member's response carries those two
    numbers, and a push that re-counted them would be free to disagree with the screen
    that member is looking at.

    The ``tag`` collapses per ``(league, round)``, which is load-bearing rather than tidy:
    twelve members each notifying eleven others is 132 sends a round in 2-1 Hibs, and the
    owner has chosen that over a digest. One live pick alert in the tray is what makes it
    survivable — that and the per-league mute, which this passes.
    """
    verb = "moved to" if moved else "picked"
    told = 0
    for member in await notification_targets(session, gameweek, excluding=picker_id):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            member.league_name,
            f"{picker_name} {verb} {selection} @ {odds:.2f} · "
            f"{progress.picked_count}/{progress.member_count} picked",
            data={
                "type": "pick_changed" if moved else "pick_made",
                "league_id": member.league_id,
                "url": f"/leagues/{member.league_slug}/predictions",
            },
            tag=f"pick-made-{member.league_id}-{gameweek.id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        told += 1
    return told


def _completion_body(completion: GameweekCompletion) -> str:
    """``Dave picked Arsenal @ 1.80 · 12/12 picked — all picks are in``.

    Deliberately the ordinary pick line with a clause on the end rather than a message of
    its own. It replaces that alert rather than following it, so it has to carry what the
    alert would have carried: the last member's name is the one piece of the round nobody
    else in the league can see coming, and burying it under a bare "all picks are in"
    would make the completion the *less* informative of the two events.

    Every value comes off the row, frozen at the transition. A retry can run after that
    member has moved their pick, and the event is what happened when the coupon filled.
    """
    return (
        f"{completion.final_picker_name} picked {completion.selection} "
        f"@ {completion.odds:.2f} · {completion.member_count}/{completion.member_count} "
        f"picked — all picks are in"
    )


async def announce_all_picked(session: AsyncSession, gameweek: Gameweek) -> int | None:
    """Deliver this round's completion event, if one is waiting to be delivered.

    Returns the number of members told, or ``None`` when there was nothing to do — the
    round is not complete, its event has already gone out, or another request holds it.
    The caller commits; a raise here leaves ``delivered_at`` null and the next submission
    on the round tries again.

    **Everybody, including the final picker.** Every other pick alert excludes the person
    who caused it, because telling someone what they just did is noise. This one is the
    exception and the reason is the whole point of the batch: the member who completes the
    coupon is the one person for whom something has changed — the round is now worth
    copying and placing, and they are the one holding it.
    """
    completion = await claim_pending_completion(session, gameweek)
    if completion is None:
        return None

    body = _completion_body(completion)
    told = 0
    for member in await notification_targets(session, gameweek):
        await send_notification(
            session,
            uuid.UUID(member.player_id),
            member.league_name,
            body,
            data={
                "type": "all_picked",
                "league_id": member.league_id,
                "url": coupon_section_url(member.league_slug, gameweek.id),
            },
            tag=f"all-picked-{member.league_id}-{gameweek.id}",
            timezone_name=member.timezone,
            league_id=uuid.UUID(member.league_id),
        )
        told += 1

    mark_delivered(completion)
    return told
