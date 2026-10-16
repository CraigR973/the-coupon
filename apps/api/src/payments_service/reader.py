"""Connecting to Monzo, and reading league payments from it unattended. Batch 208.

ADR 0009 option B. Everything that spends the Monzo token is here, behind one lock, so the
token is refreshed by one caller at a time. The process runs as exactly one replica (its
boot refuses more), because a refresh rotates the refresh token: two processes refreshing
would each invalidate the other.

How a payment arrives::

    Monzo ──webhook (unsigned, so only a nudge)──▶ nudge(tx id) ──re-read──┐
    every 5 min ──────────────────────────────────▶ catch_up() ──read─────┤
                                                                           ▼
                                        ingest.link_payment → record_link_payment → ledger

Neither path trusts anything it did not read from Monzo's API itself. A failure records a
short code and a time for the organiser's link-health line and changes nothing else; the
next catch-up starts again from the last complete read. Manual entry on the API never
depends on any of it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.league import League
from src.models.monzo_connection import MonzoConnection, MonzoLinkStatus
from src.payments_service.crypto import TokenCipher, TokenCipherUnavailable, TokenUnreadable
from src.payments_service.ingest import Recorded, link_payment, record_link_payment
from src.payments_service.monzo import (
    MonzoClient,
    MonzoError,
    MonzoForbidden,
    MonzoRefused,
    MonzoUnauthorised,
    TokenGrant,
    authorise_url,
)
from src.payments_service.settings import MonzoSettings

log = logging.getLogger("payments.reader")

#: How often the catch-up runs (the row: "every five minutes").
CATCH_UP_INTERVAL = timedelta(minutes=5)
#: Each read starts this far before the last complete one, so a transaction Monzo lists a
#: little late is still seen. Overlap costs nothing: a payment is written once.
READ_OVERLAP = timedelta(hours=1)
#: Monzo serves only the last 90 days to a token more than five minutes old.
HISTORY_LIMIT = timedelta(days=89)
#: Refresh this long before the access token expires, never at the last second.
REFRESH_MARGIN = timedelta(minutes=10)
#: How long a started connect stays valid.
CONNECT_WINDOW = timedelta(minutes=10)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _rfc3339(moment: datetime) -> str:
    return moment.replace(microsecond=0, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


class ConnectOutcome(StrEnum):
    awaiting_approval = "awaiting_approval"
    bad_state = "bad_state"
    other_user = "other_user"
    refused = "refused"
    unavailable = "unavailable"


class ReadOutcome(StrEnum):
    idle = "idle"
    awaiting_approval = "awaiting_approval"
    read = "read"
    failed = "failed"


@dataclass
class ReadReport:
    outcome: ReadOutcome
    recorded: dict[Recorded, int]


class NotConnected(RuntimeError):
    """No usable token: nothing to spend."""


class PaymentsReader:
    def __init__(
        self,
        settings: MonzoSettings,
        sessions: async_sessionmaker[AsyncSession],
        client: MonzoClient | None = None,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.settings = settings
        self._sessions = sessions
        self._client = client or MonzoClient()
        self._now = now
        self._lock = asyncio.Lock()
        self._cipher = TokenCipher(settings.encryption_key)

    # ── The row ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def _connection(db: AsyncSession, *, lock: bool = False) -> MonzoConnection | None:
        query = select(MonzoConnection).execution_options(populate_existing=True)
        if lock:
            query = query.with_for_update()
        return (await db.execute(query)).scalar_one_or_none()

    async def _record_error(self, code: str) -> None:
        """A failure, kept apart from the work it interrupted (which is rolled back)."""
        async with self._sessions() as db:
            connection = await self._connection(db, lock=True)
            if connection is None:
                return
            connection.last_error = code[:40]
            connection.last_error_at = self._now()
            connection.updated_at = self._now()
            await db.commit()
        log.warning("monzo link error: %s", code)

    # ── Connecting (the owner, once: browser, then the Monzo app) ────────────────

    async def start_connect(self) -> str:
        """A fresh OAuth ``state``, remembered by its hash, and the Monzo address to visit."""
        state = secrets.token_urlsafe(32)
        now = self._now()
        async with self._sessions() as db:
            connection = await self._connection(db, lock=True)
            if connection is None:
                connection = MonzoConnection(status=MonzoLinkStatus.not_connected)
                db.add(connection)
            connection.oauth_state_hash = _state_hash(state)
            connection.oauth_state_expires_at = now + CONNECT_WINDOW
            connection.updated_at = now
            await db.commit()
        return authorise_url(self.settings.client_id, self.settings.redirect_uri, state)

    async def finish_connect(self, code: str, state: str) -> ConnectOutcome:
        """Trade the browser's code for tokens. Monzo then waits for the in-app approval."""
        async with self._lock, self._sessions() as db:
            connection = await self._connection(db, lock=True)
            now = self._now()
            if (
                connection is None
                or connection.oauth_state_hash is None
                or connection.oauth_state_expires_at is None
                or connection.oauth_state_expires_at < now
                or not hmac.compare_digest(connection.oauth_state_hash, _state_hash(state))
            ):
                return ConnectOutcome.bad_state
            # One use only, whatever happens next.
            connection.oauth_state_hash = None
            connection.oauth_state_expires_at = None
            await db.commit()
            try:
                grant = await self._client.exchange_code(
                    client_id=self.settings.client_id,
                    client_secret=self.settings.client_secret,
                    redirect_uri=self.settings.redirect_uri,
                    code=code,
                )
            except MonzoRefused:
                return ConnectOutcome.refused
            except MonzoError:
                return ConnectOutcome.unavailable
            connection = await self._connection(db, lock=True)
            assert connection is not None
            held = connection.status in (
                MonzoLinkStatus.awaiting_approval,
                MonzoLinkStatus.connected,
            )
            if held and connection.monzo_user_id not in (None, grant.user_id):
                # Someone else's account must never replace the owner's.
                return ConnectOutcome.other_user
            if connection.monzo_user_id != grant.user_id:
                # A different account (or the first): its payments count from now.
                connection.counting_since = now
                connection.read_through = None
                connection.webhook_registered_at = None
            elif connection.counting_since is None:
                connection.counting_since = now
            connection.monzo_user_id = grant.user_id
            self._store(connection, grant, now)
            connection.status = MonzoLinkStatus.awaiting_approval
            connection.last_error = None
            connection.last_error_at = None
            await db.commit()
        log.info("monzo connect finished in the browser; awaiting approval in the app")
        return ConnectOutcome.awaiting_approval

    # ── The token ────────────────────────────────────────────────────────────────

    def _store(self, connection: MonzoConnection, grant: TokenGrant, now: datetime) -> None:
        connection.access_token_encrypted = self._cipher.seal(grant.access_token)
        connection.refresh_token_encrypted = self._cipher.seal(grant.refresh_token)
        connection.access_expires_at = now + timedelta(seconds=grant.expires_in)
        connection.updated_at = now

    async def _access_token(self, db: AsyncSession, connection: MonzoConnection) -> str:
        """A usable access token, refreshed (and the refresh token rotated) when due.

        A refresh token is spent the moment Monzo issues the next one, so the pair is
        committed together, before anything else uses it.
        """
        if not (connection.access_token_encrypted and connection.refresh_token_encrypted):
            raise NotConnected("no stored token")
        now = self._now()
        if connection.access_expires_at is None or (
            connection.access_expires_at - now <= REFRESH_MARGIN
        ):
            await self._refresh(db, connection)
        assert connection.access_token_encrypted is not None
        return self._cipher.open(connection.access_token_encrypted)

    async def _refreshed_token(self, db: AsyncSession, connection: MonzoConnection) -> str:
        await self._refresh(db, connection)
        assert connection.access_token_encrypted is not None
        return self._cipher.open(connection.access_token_encrypted)

    async def _refresh(self, db: AsyncSession, connection: MonzoConnection) -> None:
        assert connection.refresh_token_encrypted is not None
        refresh_token = self._cipher.open(connection.refresh_token_encrypted)
        try:
            grant = await self._client.refresh(
                client_id=self.settings.client_id,
                client_secret=self.settings.client_secret,
                refresh_token=refresh_token,
            )
        except (MonzoRefused, MonzoUnauthorised):
            # The refresh token is dead; only the owner connecting again helps.
            connection.status = MonzoLinkStatus.needs_reconnect
            connection.access_token_encrypted = None
            connection.refresh_token_encrypted = None
            connection.access_expires_at = None
            connection.last_error = "refresh_refused"
            connection.last_error_at = self._now()
            connection.updated_at = self._now()
            await db.commit()
            log.warning("monzo refused the refresh token; the owner must connect again")
            raise NotConnected("refresh refused") from None
        self._store(connection, grant, self._now())
        await db.commit()
        log.info("monzo token refreshed")

    # ── Reading ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def _league_links(db: AsyncSession) -> set[str]:
        rows = await db.scalars(
            select(League.monzo_link_id).where(League.monzo_link_id.is_not(None))
        )
        return {link for link in rows if link}

    async def _register_webhooks(self, access_token: str, account_ids: list[str]) -> None:
        url = self.settings.webhook_url
        for account_id in account_ids:
            existing = await self._client.webhooks(access_token, account_id)
            if not any(hook.get("url") == url for hook in existing):
                await self._client.register_webhook(access_token, account_id, url)

    async def catch_up(self) -> ReadReport:
        """Read every league-link payment since the last complete read. Runs every 5 min."""
        recorded: dict[Recorded, int] = {}
        async with self._lock:
            try:
                async with self._sessions() as db:
                    connection = await self._connection(db, lock=True)
                    if connection is None or connection.status not in (
                        MonzoLinkStatus.awaiting_approval,
                        MonzoLinkStatus.connected,
                    ):
                        return ReadReport(ReadOutcome.idle, recorded)
                    access_token = await self._access_token(db, connection)
                    try:
                        try:
                            accounts = await self._client.accounts(access_token)
                        except MonzoUnauthorised:
                            # Revoked before it expired: one refresh, one retry.
                            access_token = await self._refreshed_token(db, connection)
                            accounts = await self._client.accounts(access_token)
                    except MonzoForbidden:
                        if connection.status == MonzoLinkStatus.awaiting_approval:
                            await db.commit()
                            return ReadReport(ReadOutcome.awaiting_approval, recorded)
                        raise
                    account_ids = [
                        str(account["id"])
                        for account in accounts
                        if isinstance(account.get("id"), str) and not account.get("closed")
                    ]
                    started = self._now()
                    if connection.status == MonzoLinkStatus.awaiting_approval:
                        connection.status = MonzoLinkStatus.connected
                        log.info("monzo approved in the app; reading")
                    webhook_error: str | None = None
                    if connection.webhook_registered_at is None:
                        # Not fatal: the catch-up below is what guarantees nothing is
                        # missed, and registering is retried on the next run.
                        try:
                            await self._register_webhooks(access_token, account_ids)
                            connection.webhook_registered_at = started
                        except MonzoError:
                            webhook_error = "webhook_unregistered"

                    links = await self._league_links(db)
                    if links and connection.counting_since is not None:
                        floor = max(connection.counting_since, started - HISTORY_LIMIT)
                        since = floor
                        if connection.read_through is not None:
                            since = max(floor, connection.read_through - READ_OVERLAP)
                        for account_id in account_ids:
                            for transaction in await self._client.transactions(
                                access_token, account_id, _rfc3339(since)
                            ):
                                payment = link_payment(transaction)
                                if payment is None or payment.link_id not in links:
                                    continue
                                outcome = await record_link_payment(
                                    db, payment, counting_since=connection.counting_since
                                )
                                recorded[outcome] = recorded.get(outcome, 0) + 1
                        # Only a read that reached every account moves the start point.
                        connection.read_through = started
                    connection.last_success_at = started
                    if webhook_error is not None:
                        connection.last_error = webhook_error
                        connection.last_error_at = started
                    connection.updated_at = started
                    await db.commit()
            except NotConnected:
                return ReadReport(ReadOutcome.failed, recorded)
            except (MonzoError, TokenUnreadable, TokenCipherUnavailable) as failure:
                await self._record_error(getattr(failure, "code", "token_unreadable"))
                return ReadReport(ReadOutcome.failed, {})
        self._log_recorded("catch-up", recorded)
        return ReadReport(ReadOutcome.read, recorded)

    async def nudge(self, transaction_id: str) -> ReadReport:
        """A webhook said this transaction exists. Re-read it; trust nothing else."""
        recorded: dict[Recorded, int] = {}
        async with self._lock:
            try:
                async with self._sessions() as db:
                    connection = await self._connection(db, lock=True)
                    if (
                        connection is None
                        or connection.status != MonzoLinkStatus.connected
                        or connection.counting_since is None
                    ):
                        return ReadReport(ReadOutcome.idle, recorded)
                    links = await self._league_links(db)
                    if not links:
                        return ReadReport(ReadOutcome.idle, recorded)
                    access_token = await self._access_token(db, connection)
                    try:
                        transaction = await self._client.transaction(access_token, transaction_id)
                    except MonzoUnauthorised:
                        access_token = await self._refreshed_token(db, connection)
                        transaction = await self._client.transaction(access_token, transaction_id)
                    payment = link_payment(transaction)
                    if payment is not None and payment.link_id in links:
                        outcome = await record_link_payment(
                            db, payment, counting_since=connection.counting_since
                        )
                        recorded[outcome] = 1
                    connection.last_success_at = self._now()
                    connection.updated_at = self._now()
                    await db.commit()
            except NotConnected:
                return ReadReport(ReadOutcome.failed, recorded)
            except (MonzoError, TokenUnreadable, TokenCipherUnavailable) as failure:
                await self._record_error(getattr(failure, "code", "token_unreadable"))
                return ReadReport(ReadOutcome.failed, {})
        self._log_recorded("webhook", recorded)
        return ReadReport(ReadOutcome.read, recorded)

    @staticmethod
    def _log_recorded(source: str, recorded: dict[Recorded, int]) -> None:
        # Counts only: never a transaction body, an amount or a payer's name.
        if recorded:
            log.info(
                "monzo %s recorded payments: %s",
                source,
                ", ".join(
                    f"{outcome.value}={count}" for outcome, count in sorted(recorded.items())
                ),
            )


async def run_catch_up_forever(
    reader: PaymentsReader, interval: timedelta = CATCH_UP_INTERVAL
) -> None:
    """The five-minute loop. A failure is logged by type and the loop carries on."""
    while True:
        try:
            await reader.catch_up()
        except Exception as failure:  # the loop must outlive any one read
            log.error("monzo catch-up crashed: %s", type(failure).__name__)
        await asyncio.sleep(interval.total_seconds())
