"""Connecting to Monzo, and reading league payments from it unattended. Batch 208.

ADR 0009 option B. Everything that spends the Monzo token is here, behind one lock, so the
token is refreshed by one caller at a time. The process runs as exactly one replica (its
boot refuses more), because a refresh rotates the refresh token: two processes refreshing
would each invalidate the other.

How a payment arrives::

    Monzo ──webhook (unsigned, so only a nudge)──▶ nudge(tx id) ──re-read──┐
    every 5 min ──────────────────────────────────▶ catch_up() ──read─────┤
                                                                           ▼
                     ingest.link_payment → record_link_payment → ledger, + learn_pots
                     ingest.filing → its link payment's league? → learn its pot's name
                     ingest.pot_top_up → a league's pot? → record_top_up → ledger

The owner's own top-ups (Batch 214) are moves from the connected account into a pot that
some league's link payments name. Monzo also files every link payment into its pot with a
deposit of its own, which names the pot the way the owner's moves do (``pot_…``), so that
name is learned from those filings, tied to their link payments (Batch 216); a filing is
never a payment. A read handles its link payments first, then its filings, so a pot they
name counts a top-up in the same read. While some league with a link id has no pot yet,
the first catch-up of the process reads back to the counting start, so the pot is learned
from the payments already in Monzo's history rather than waiting for the next one.

Neither path trusts anything it did not read from Monzo's API itself. A failure records a
short code and a time for the organiser's link-health line and changes nothing else; the
next catch-up starts again from the last complete read. A webhook re-read Monzo refuses is
logged with its reason and not recorded: the catch-up finds the payment anyway. Manual
entry on the API never depends on any of it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.league import League
from src.models.monzo_connection import MonzoConnection, MonzoLinkStatus
from src.payments_service.crypto import TokenCipher, TokenCipherUnavailable, TokenUnreadable
from src.payments_service.ingest import (
    POT_TRANSFER,
    AccountHolders,
    Filing,
    LinkPayment,
    PotTopUp,
    Recorded,
    a_league_lacks_its_pot,
    a_top_up_was_recognised,
    account_holders,
    filing,
    league_pot_refs,
    learn_pots,
    learn_pots_from_filing,
    link_payment,
    pot_ref_fields,
    pot_top_up,
    record_link_payment,
    record_top_up,
    transaction_shape,
)
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
#: How many transaction ids the structure-only capture remembers having described, so a
#: pot move re-read by every overlapping catch-up is logged once.
CAPTURE_MEMORY = 5_000


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _rfc3339(moment: datetime) -> str:
    return moment.replace(microsecond=0, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _names_a_pot(transaction: Mapping[str, Any]) -> bool:
    """A move between a current account and a pot, or anything else that names a pot."""
    return transaction.get("scheme") == POT_TRANSFER or bool(pot_ref_fields(transaction))


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
        #: From the last catch-up's accounts: who a top-up is from, and their name.
        self._holders = AccountHolders(names={}, sole_holder={})
        #: Whether this process has read back to the counting start to learn the leagues'
        #: pots. Once per process: a pot that no link payment names is not found by
        #: reading history every five minutes.
        self._history_read = False
        #: The structure-only capture's memory, and whether it has said that the league's
        #: link payments name no pot.
        self._described: set[str] = set()
        self._said_no_pot = False

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
                        # Monzo has released the account: its 90 days start now.
                        connection.approved_at = started
                        log.info("monzo approved in the app; reading")
                    self._holders = account_holders(accounts)
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
                        learning = not self._history_read and await a_league_lacks_its_pot(db)
                        if connection.read_through is not None and not learning:
                            since = max(floor, connection.read_through - READ_OVERLAP)
                        filings: list[tuple[Mapping[str, Any], Filing]] = []
                        top_ups: list[tuple[Mapping[str, Any], PotTopUp]] = []
                        unplaced: list[Mapping[str, Any]] = []
                        for account_id in account_ids:
                            for transaction in await self._client.transactions(
                                access_token, account_id, _rfc3339(since)
                            ):
                                payment = link_payment(transaction)
                                if payment is not None:
                                    if payment.link_id in links:
                                        outcome = await self._link_payment(
                                            db, transaction, payment, connection.counting_since
                                        )
                                        recorded[outcome] = recorded.get(outcome, 0) + 1
                                    continue
                                filed = filing(transaction)
                                if filed is not None:
                                    filings.append((transaction, filed))
                                    continue
                                top_up = pot_top_up(transaction)
                                if top_up is not None:
                                    top_ups.append(
                                        (transaction, self._with_mover(top_up, account_id))
                                    )
                                elif _names_a_pot(transaction):
                                    unplaced.append(transaction)
                        # After the read's link payments: a filing is tied to one, and either
                        # may name the pot.
                        for moved, filed in filings:
                            if not await self._filing(db, filed):
                                unplaced.append(moved)
                        pots = await league_pot_refs(db)
                        for moved, top_up in top_ups:
                            if not top_up.pot_refs & pots:
                                unplaced.append(moved)
                                continue
                            outcome = await self._top_up(db, top_up, connection.counting_since)
                            recorded[outcome] = recorded.get(outcome, 0) + 1
                        await self._describe_unplaced(db, unplaced, pots)
                        if learning:
                            self._history_read = True
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
                    filed = filing(transaction) if payment is None else None
                    top_up = pot_top_up(transaction) if payment is None else None
                    if payment is not None and payment.link_id in links:
                        outcome = await self._link_payment(
                            db, transaction, payment, connection.counting_since
                        )
                        recorded[outcome] = 1
                    elif filed is not None:
                        await self._filing(db, filed)
                    elif top_up is not None and top_up.pot_refs & await league_pot_refs(db):
                        account = transaction.get("account_id")
                        if isinstance(account, str):
                            top_up = self._with_mover(top_up, account)
                        outcome = await self._top_up(db, top_up, connection.counting_since)
                        recorded[outcome] = 1
                    connection.last_success_at = self._now()
                    connection.updated_at = self._now()
                    await db.commit()
            except NotConnected:
                return ReadReport(ReadOutcome.failed, recorded)
            except MonzoRefused as refused:
                # Monzo will not show this one transaction (every re-read was refused on
                # 24 Oct 2026). The catch-up still finds the payment within five minutes,
                # so it is no problem of the link's: logged for its reason, not recorded.
                log.info(
                    "monzo webhook re-read refused: status=%s code=%s",
                    refused.status,
                    refused.monzo_code or "none",
                )
                return ReadReport(ReadOutcome.failed, {})
            except (MonzoError, TokenUnreadable, TokenCipherUnavailable) as failure:
                await self._record_error(getattr(failure, "code", "token_unreadable"))
                return ReadReport(ReadOutcome.failed, {})
        self._log_recorded("webhook", recorded)
        return ReadReport(ReadOutcome.read, recorded)

    # ── Link payments and top-ups ───────────────────────────────────────────────

    async def _link_payment(
        self,
        db: AsyncSession,
        transaction: Mapping[str, Any],
        payment: LinkPayment,
        counting_since: datetime,
    ) -> Recorded:
        """Record a league's link payment, and learn the pot it was filed into."""
        outcome = await record_link_payment(db, payment, counting_since=counting_since)
        learned = await learn_pots(db, payment, now=self._now())
        if learned.fields:
            # Which field held it is what ADR 0009's evidence never recorded.
            log.info(
                "monzo pot learned from a league's link payment: fields=%s",
                ",".join(sorted(learned.fields)),
            )
        if learned.clash:
            log.warning("monzo pot already belongs to another league's link; it stays theirs")
        if not payment.pots and not self._said_no_pot:
            self._said_no_pot = True
            log.info("monzo link payment names no pot: %s", transaction_shape(transaction, ()))
        return outcome

    async def _filing(self, db: AsyncSession, filed: Filing) -> bool:
        """Learn the pot's deposit name from Monzo filing a link payment; never a payment.

        Returns whether the filing was placed: tied to a league's link payment, or into a pot
        already known. One that is not is described by the structure-only capture.
        """
        learned = await learn_pots_from_filing(db, filed, now=self._now())
        if learned.fields:
            log.info(
                "monzo pot learned from a link payment's filing: fields=%s joined_by=%s",
                ",".join(sorted(learned.fields)),
                learned.joined_by,
            )
        if learned.clash:
            log.warning("monzo pot already belongs to another league's link; it stays theirs")
        return learned.joined_by is not None or bool(filed.pot_refs & await league_pot_refs(db))

    def _with_mover(self, top_up: PotTopUp, account_id: str) -> PotTopUp:
        """Who moved the money: as Monzo says, else the account's only holder."""
        if top_up.payer_user_id is not None:
            return top_up
        holder = self._holders.sole_holder.get(account_id)
        return replace(top_up, payer_user_id=holder) if holder is not None else top_up

    async def _top_up(
        self, db: AsyncSession, top_up: PotTopUp, counting_since: datetime
    ) -> Recorded:
        outcome = await record_top_up(
            db,
            top_up,
            counting_since=counting_since,
            payer_name=self._holders.names.get(top_up.payer_user_id or ""),
            now=self._now(),
        )
        if outcome in (Recorded.matched, Recorded.queued):
            log.info("monzo top-up recorded: %s", outcome.value)
        return outcome

    async def _describe_unplaced(
        self, db: AsyncSession, transactions: list[Mapping[str, Any]], pots: set[str]
    ) -> None:
        """Until a top-up is recognised, describe each pot move that could not be placed.

        Structure only (:func:`~src.payments_service.ingest.transaction_shape`), once per
        transaction however many overlapping reads see it. It stops for good once any top-up
        has been recognised: from then on the shape is known.
        """
        fresh = [t for t in transactions if str(t.get("id")) not in self._described]
        if not fresh or await a_top_up_was_recognised(db):
            return
        if len(self._described) > CAPTURE_MEMORY:
            self._described.clear()
        for transaction in fresh:
            self._described.add(str(transaction.get("id")))
            log.info("monzo pot move not placed: %s", transaction_shape(transaction, pots))

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
