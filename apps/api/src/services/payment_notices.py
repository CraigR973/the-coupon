"""Payment notices: what the API's scheduler tells people about the league's money. Batch 213.

ADR 0009 option B keeps the payments service free of push keys, so it only writes the
ledger and the Monzo connection's health columns. This module reads both and sends three
notices from the API:

* **a payment waiting to be matched** — to the site admins, once per queued payment;
* **the Monzo link** — to the site admins, once when it needs connecting again or has not
  read anything for an hour, and once when it reads again; never once per failed read;
* **a payment recorded** — to the member whose link payment was matched or assigned,
  with the amount and whether they can now pick. Never the payer's name or a Monzo id.
  Cash an organiser records sends nothing (owner, 2026-10-18).

**Each goes out once.** Before a notice is sent its ``(kind, subject)`` pair is inserted
into ``notification_sends`` under a unique constraint, in the same transaction as its
inbox row. Two runs overlapping a redeploy race on that insert: the second waits for the
first to commit and then inserts nothing, so it sends nothing. Pushes go out only after
that commit (:func:`src.scheduler.run_payment_notices`), so a push is never repeated; a
crash between the commit and the push loses the push but keeps the inbox row.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import ColumnElement, String, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.monzo_connection import MonzoConnection, MonzoLinkStatus
from src.models.notification import NotificationSend
from src.models.profile import Profile
from src.services.dues import fee_standings, format_pence, member_balance
from src.services.gameweek import PICKABLE_STATES
from src.services.notification_triggers import PreparedFanout, _admin_players
from src.services.push_notification_service import (
    collect_notification_intents,
    prepare_collected_notifications,
    send_notification,
)

PAYMENT_QUEUED = "payment_queued"
PAYMENT_RECORDED = "payment_recorded"
MONZO_LINK_DOWN = "monzo_link_down"
MONZO_LINK_RECOVERED = "monzo_link_recovered"

#: How far back a run looks for payments nobody has been told about. Migration 030 marked
#: everything before it as told; this only bounds the scan, and still covers a scheduler
#: that was down for days.
LOOKBACK = timedelta(days=7)

#: "Has failed to read for an hour" (owner, 2026-10-18): measured from the last successful
#: read, so it catches a payments service that has stopped as well as one that fails.
LINK_STALE_AFTER = timedelta(hours=1)

#: The subject of an outage that began before the connection had ever read anything.
NEVER_READ = "never"

_PAYER_NAME_LIMIT = 60


def _payments_url(league: League) -> str:
    return f"/leagues/{league.slug}/admin/payments"


def _local_label(moment: datetime, timezone_name: str) -> str:
    """``Sat 14:30`` on the reader's own clock, falling back to UTC."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return moment.replace(tzinfo=UTC).astimezone(zone).strftime("%a %H:%M")


async def _claim(session: AsyncSession, kind: str, subject: str, now: datetime) -> bool:
    """Record that this notice is going out; ``False`` when it already has."""
    claimed = await session.execute(
        insert(NotificationSend)
        .values(id=uuid.uuid4(), kind=kind, subject=subject, sent_at=now)
        .on_conflict_do_nothing(constraint="uq_notification_sends_kind_subject")
        .returning(NotificationSend.id)
    )
    return claimed.scalar_one_or_none() is not None


def _not_yet_sent(kind: str) -> ColumnElement[bool]:
    return ~exists().where(
        NotificationSend.kind == kind,
        NotificationSend.subject == LedgerEntry.id.cast(String),
    )


# ── A payment waiting to be matched ─────────────────────────────────────────────


async def notify_queued_payments(session: AsyncSession, now: datetime) -> int:
    """Tell the site admins about each link payment newly waiting in the queue."""
    rows = (
        await session.execute(
            select(LedgerEntry, League)
            .join(League, League.id == LedgerEntry.league_id)
            .where(
                LedgerEntry.kind == LedgerKind.payment,
                LedgerEntry.player_id.is_(None),
                LedgerEntry.monzo_transaction_id.is_not(None),
                LedgerEntry.created_at >= now - LOOKBACK,
                _not_yet_sent(PAYMENT_QUEUED),
            )
            .order_by(LedgerEntry.created_at, LedgerEntry.id)
        )
    ).all()
    if not rows:
        return 0
    admins = await _admin_players(session)
    told = 0
    for entry, league in rows:
        if not await _claim(session, PAYMENT_QUEUED, str(entry.id), now):
            continue
        payer = (entry.payer_name or "").strip()[:_PAYER_NAME_LIMIT] or "a payer"
        body = (
            f"{format_pence(entry.amount_pence)} from {payer} to {league.name} "
            "is waiting to be matched to a member."
        )
        for admin in admins:
            await send_notification(
                session,
                admin.id,
                "Payment waiting to be matched",
                body,
                data={
                    "type": PAYMENT_QUEUED,
                    "league_id": str(league.id),
                    "url": _payments_url(league),
                },
                tag=f"payment-queued-{entry.id}",
                timezone_name=admin.timezone,
                now_utc=now,
                league_id=league.id,
            )
            told += 1
    return told


# ── A member's payment, recorded ───────────────────────────────────────────────


async def _standing_line(
    session: AsyncSession, league: League, player_id: uuid.UUID, now: datetime
) -> str:
    """Whether the member can now pick, in one sentence, with no ledger detail."""
    gameweek = (
        await session.execute(
            select(Gameweek)
            .where(
                Gameweek.league_id == league.id,
                Gameweek.status.in_(PICKABLE_STATES),
                Gameweek.locks_at_utc > now,
            )
            .order_by(Gameweek.locks_at_utc, Gameweek.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if gameweek is not None and league.entry_fee_pence is not None:
        standing = (await fee_standings(session, league, gameweek, [player_id]))[player_id]
        if standing.owed_pence <= 0:
            return "You're paid up and can pick."
        return f"You still owe {format_pence(standing.owed_pence)} before you can pick."
    balance = await member_balance(session, league.id, player_id)
    if balance < 0:
        return f"You still owe {format_pence(-balance)}."
    if league.entry_fee_pence is not None and balance >= league.entry_fee_pence:
        return "You're paid up for the next round."
    return "You're paid up to date."


async def notify_recorded_payments(session: AsyncSession, now: datetime) -> int:
    """Tell each member when a link payment of theirs is matched or assigned."""
    became_theirs = func.coalesce(LedgerEntry.assigned_at, LedgerEntry.created_at)
    rows = (
        await session.execute(
            select(LedgerEntry, League, Profile)
            .join(League, League.id == LedgerEntry.league_id)
            .join(Profile, Profile.id == LedgerEntry.player_id)
            .where(
                LedgerEntry.kind == LedgerKind.payment,
                LedgerEntry.player_id.is_not(None),
                LedgerEntry.monzo_transaction_id.is_not(None),
                became_theirs >= now - LOOKBACK,
                Profile.deleted_at.is_(None),
                _not_yet_sent(PAYMENT_RECORDED),
            )
            .order_by(became_theirs, LedgerEntry.id)
        )
    ).all()
    told = 0
    for entry, league, member in rows:
        if not await _claim(session, PAYMENT_RECORDED, str(entry.id), now):
            continue
        standing = await _standing_line(session, league, member.id, now)
        await send_notification(
            session,
            member.id,
            "Payment received",
            f"Your {format_pence(entry.amount_pence)} payment to {league.name} is in. {standing}",
            data={
                "type": PAYMENT_RECORDED,
                "league_id": str(league.id),
                "url": f"/leagues/{league.slug}/predictions",
            },
            tag=f"payment-recorded-{entry.id}",
            timezone_name=member.timezone,
            now_utc=now,
            league_id=league.id,
        )
        told += 1
    return told


# ── The Monzo link ──────────────────────────────────────────────────────────────


async def _link_league(session: AsyncSession) -> League | None:
    """The league whose payment link Monzo reads, which the notice's inbox row hangs on."""
    return (
        await session.execute(
            select(League)
            .where(League.monzo_link_id.is_not(None), League.deleted_at.is_(None))
            .order_by(League.name, League.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _tell_admins(
    session: AsyncSession,
    kind: str,
    title: str,
    body_for: Callable[[Profile], str],
    now: datetime,
) -> int:
    league = await _link_league(session)
    told = 0
    for admin in await _admin_players(session):
        await send_notification(
            session,
            admin.id,
            title,
            body_for(admin),
            data={
                "type": kind,
                "url": _payments_url(league) if league is not None else "/admin",
                **({"league_id": str(league.id)} if league is not None else {}),
            },
            tag="monzo-link",
            timezone_name=admin.timezone,
            now_utc=now,
            league_id=league.id if league is not None else None,
        )
        told += 1
    return told


async def notify_monzo_link(session: AsyncSession, now: datetime) -> int:
    """One notice when the link goes down, one when it reads again.

    An outage is named by the last successful read before it, which stays put for as
    long as the outage lasts: that is the subject both notices are claimed under, so the
    whole outage sends one of each however many runs see it.
    """
    row = (
        await session.execute(
            select(
                MonzoConnection.status,
                MonzoConnection.last_success_at,
                MonzoConnection.last_error,
                MonzoConnection.last_error_at,
                MonzoConnection.created_at,
            )
        )
    ).one_or_none()
    if row is None:
        return 0
    status = MonzoLinkStatus(row.status)
    outage = row.last_success_at.isoformat() if row.last_success_at is not None else NEVER_READ

    if status == MonzoLinkStatus.needs_reconnect:
        if not await _claim(session, MONZO_LINK_DOWN, outage, now):
            return 0
        return await _tell_admins(
            session,
            MONZO_LINK_DOWN,
            "Monzo needs connecting again",
            lambda _admin: (
                "Monzo refused the app's login, so no payments are being read until you "
                "connect again."
            ),
            now,
        )

    if status != MonzoLinkStatus.connected:
        # Not connected yet, or half-way through a connect: nothing to report.
        return 0

    since = row.last_success_at or row.created_at
    if now - since >= LINK_STALE_AFTER:
        if not await _claim(session, MONZO_LINK_DOWN, outage, now):
            return 0
        failing = row.last_error_at is not None and (
            row.last_success_at is None or row.last_error_at > row.last_success_at
        )
        problem = f" The last problem was {row.last_error}." if failing and row.last_error else ""
        return await _tell_admins(
            session,
            MONZO_LINK_DOWN,
            "Monzo has stopped reading",
            lambda admin: (
                "The app has not read from Monzo since "
                f"{_local_label(since, admin.timezone)}.{problem}"
            ),
            now,
        )

    # Reading. If the latest outage has not been closed, close it once.
    latest = (
        await session.execute(
            select(NotificationSend.subject)
            .where(NotificationSend.kind == MONZO_LINK_DOWN)
            .order_by(NotificationSend.sent_at.desc(), NotificationSend.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None or latest == outage:
        return 0
    if not await _claim(session, MONZO_LINK_RECOVERED, latest, now):
        return 0
    return await _tell_admins(
        session,
        MONZO_LINK_RECOVERED,
        "Monzo is reading again",
        lambda _admin: "Payments are being read again, including any made while it was down.",
        now,
    )


# ── One run ─────────────────────────────────────────────────────────────────────


async def prepare_payment_notices(session: AsyncSession, now: datetime) -> PreparedFanout:
    """Claim every notice due, write their inbox rows and copy their pushes.

    The caller commits, and only then delivers the returned pushes.
    """
    with collect_notification_intents() as intents:
        targeted = (
            await notify_queued_payments(session, now)
            + await notify_monzo_link(session, now)
            + await notify_recorded_payments(session, now)
        )
    notifications = await prepare_collected_notifications(session, intents)
    return PreparedFanout(notifications=tuple(notifications), targeted=targeted)
