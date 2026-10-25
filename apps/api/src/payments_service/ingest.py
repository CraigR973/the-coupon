"""From a Monzo transaction to a ledger entry. Batch 208; the owner's top-ups, Batch 214.

ADR 0009's sixth rule. Only money that came in through a league's payment link counts — the
owner's other money from the same friends (a dinner split, say) never reaches the ledger.
The one exception is the owner's own: a top-up from the connected account into a league's
pot is the owner's payment (owner decision, 2026-10-24: the owner never puts anyone else's
cash into the pot). The payer is matched on who paid, not on a reference:

* a payer using the Monzo app has a stable ``user_…`` id, matched through the league's
  payer map by that id — and so is the owner topping up, by the id of whoever moved it;
* a card payer arrives with a fresh ``anonuser_…`` id every time, so is matched by name,
  normalised the way the organiser's assignment stores it;
* anyone the map does not know is queued for the organiser, who assigns them once.

A top-up counts only into a pot that the league's own link payments name, which this
module learns from them (:func:`learn_pots`), and only if it was made after that pot was
learned: what the owner moved before then was recorded by hand. Link payments name the pot
``collectionpot_…``, but pot deposits name it ``pot_…``; that second name is learned from
the deposit Monzo makes to file each link payment into the pot (:func:`filing`,
:func:`learn_pots_from_filing`, Batch 216). A filing is the member's money moving, already
counted as their link payment, so it is never a top-up.

Each payment is written at most once, keyed by Monzo's transaction id: the webhook's
``transaction.created`` and ``transaction.updated`` and every catch-up read all arrive at
the same row. A transaction this module turns away is simply not a payment; nothing about
it is kept, and nothing is logged beyond its id — except the structure-only line the reader
logs about a pot move it cannot place, until the first top-up is recognised
(:func:`transaction_shape`).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.models.monzo_connection import MonzoPot
from src.services.dues import normalise_payer_name

TRANSACTION_ID = re.compile(r"tx_[A-Za-z0-9]+")
LINK_ID = re.compile(r"unipaylink_[A-Za-z0-9]+")
LINK_ID_FIELD = "universal_payment_link_id"
#: A pot's own id: a regular pot's ``pot_…`` or a collection pot's ``collectionpot_…``. Not
#: a pot deposit's ``potdep_…`` or a withdrawal's ``potwdr_…``.
POT_ID = re.compile(r"(?:collection)?pot_[A-Za-z0-9]+")
#: A pot's own ledger account, which counts only under a key that names a pot.
ACCOUNT_ID = re.compile(r"acc_[A-Za-z0-9]+")
#: How Monzo files money moved between a current account and a pot (the owner's July
#: samples): a deposit is negative, a withdrawal positive.
POT_TRANSFER = "uk_retail_pot"
#: How Monzo marks the deposit that files a link payment into its pot, and who contributed
#: it: an app payer's user id, or a card payer's name (production, 25 Oct 2026).
FILING_TRIGGER = "collection_pot"
CONTRIBUTOR_FIELDS = (
    "collection_pot_contributor_user_id",
    "contributor_user_id",
    "contributor_name",
)
#: How far apart a link payment and the deposit filing it may be. Monzo files at once; this
#: only bounds the search.
FILING_WINDOW = timedelta(minutes=10)
#: A pot the link payments name, as against the id pot deposits use for the same pot.
LINK_POT_PREFIX = "collectionpot_"
#: The ledger's own column widths.
_MAX_NAME = 140
_MAX_ID = 64


@dataclass(frozen=True)
class LinkPayment:
    transaction_id: str
    link_id: str
    amount_pence: int
    #: UTC, naive, like every timestamp in the database.
    occurred_at: datetime
    #: Only a Monzo-app payer's stable ``user_…`` id. A card payer's per-payment
    #: ``anonuser_…`` id identifies nobody and is not kept.
    payer_user_id: str | None
    payer_name: str | None
    #: The pot the link filed the money into: every identifier the payment gives for it,
    #: each with the field it was found in (Batch 214).
    pots: tuple[tuple[str, str], ...] = ()

    @property
    def pot_refs(self) -> frozenset[str]:
        return frozenset(ref for ref, _field in self.pots)


@dataclass(frozen=True)
class PotTopUp:
    """Money moved from a current account on the connected login into a pot. Batch 214."""

    transaction_id: str
    pot_refs: frozenset[str]
    #: What went into the pot, as the positive payment it is.
    amount_pence: int
    occurred_at: datetime
    #: The Monzo user who moved it, when Monzo says (``metadata.user_id``).
    payer_user_id: str | None


@dataclass(frozen=True)
class Filing:
    """Monzo filing a link payment into its pot, a deposit of its own. Batch 216.

    It names the pot the way pot deposits do (``pot_…`` and its ``acc_…`` ledger), which is
    how the owner's own moves name it too, so it is where that name is learned. It is never
    a payment: the money is the member's link payment, already counted.
    """

    transaction_id: str
    pots: tuple[tuple[str, str], ...]
    amount_pence: int
    occurred_at: datetime
    #: Who contributed: an app payer's stable user id, or a card payer's name.
    contributor_user_id: str | None
    contributor_name: str | None

    @property
    def pot_refs(self) -> frozenset[str]:
        return frozenset(ref for ref, _field in self.pots)


@dataclass(frozen=True)
class AccountHolders:
    """Who holds the connected accounts, from ``/accounts``' owners. Batch 214."""

    #: A holder's preferred name by their user id: what the queue shows for a top-up.
    names: Mapping[str, str]
    #: An account's only holder, by account id: who moved money out of it, when the
    #: transaction does not say.
    sole_holder: Mapping[str, str]


@dataclass(frozen=True)
class PotsLearned:
    #: The fields of the link payment that newly named the league's pot.
    fields: frozenset[str]
    #: The payment named a pot another league's link already files into, which stays
    #: that league's.
    clash: bool
    #: For a filing: how it was tied to its link payment, ``payer`` or ``amount_and_time``;
    #: ``None`` when no one league's link payment matched. Batch 216.
    joined_by: str | None = None


class Recorded(StrEnum):
    matched = "matched"
    queued = "queued"
    duplicate = "duplicate"
    not_a_league_link = "not_a_league_link"
    before_counting = "before_counting"
    #: A top-up made before its league's pot was learned. Batch 214.
    before_pot_known = "before_pot_known"
    #: A top-up into a pot that no one league's link names. Batch 214.
    not_a_league_pot = "not_a_league_pot"


def _link_id(transaction: Mapping[str, Any]) -> str | None:
    """The payment link a transaction came through, wherever Monzo puts it.

    Read from the transaction itself and from its ``metadata`` map, since which of the two
    Monzo uses for this field was not recorded when ADR 0009's evidence was gathered. Either
    way it must be a well-formed link id.
    """
    metadata = transaction.get("metadata")
    candidates = [transaction.get(LINK_ID_FIELD)]
    if isinstance(metadata, Mapping):
        candidates.append(metadata.get(LINK_ID_FIELD))
    for candidate in candidates:
        if (
            isinstance(candidate, str)
            and len(candidate) <= _MAX_ID
            and LINK_ID.fullmatch(candidate)
        ):
            return candidate
    return None


def pot_mentions(transaction: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Every ``(identifier, field)`` naming a pot in a transaction, in the order found.

    Read from the transaction itself and from its ``metadata``, like :func:`_link_id`,
    because where a link payment names its pot was never recorded (ADR 0009's evidence saw
    a ``collectionpot_…`` id). A value counts when it is shaped like a pot's id, or is an
    account id under a key that names a pot (``pot_account_id``). Never the transaction's
    own ``account_id``: that is the current account, which every transaction names.
    """
    found: list[tuple[str, str]] = []
    places: list[tuple[str, Mapping[str, Any]]] = [("", transaction)]
    metadata = transaction.get("metadata")
    if isinstance(metadata, Mapping):
        places.append(("metadata.", metadata))
    for prefix, fields in places:
        for key, value in fields.items():
            if not (isinstance(key, str) and isinstance(value, str) and len(value) <= _MAX_ID):
                continue
            if not prefix and key == "account_id":
                continue
            if POT_ID.fullmatch(value) or ("pot" in key and ACCOUNT_ID.fullmatch(value)):
                found.append((value, prefix + key))
    return found


def pot_ref_fields(transaction: Mapping[str, Any]) -> dict[str, str]:
    """Every identifier a transaction gives for a pot, with the first field naming it."""
    found: dict[str, str] = {}
    for ref, field_name in pot_mentions(transaction):
        found.setdefault(ref, field_name)
    return found


def _transaction_id(transaction: Mapping[str, Any]) -> str | None:
    transaction_id = transaction.get("id")
    if (
        isinstance(transaction_id, str)
        and len(transaction_id) <= _MAX_ID
        and TRANSACTION_ID.fullmatch(transaction_id)
    ):
        return transaction_id
    return None


def _created(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _user_id(value: Any) -> str | None:
    """A Monzo user's stable id; a card payer's ``anonuser_…`` is not one."""
    if isinstance(value, str) and value.startswith("user_") and len(value) <= _MAX_ID:
        return value
    return None


def link_payment(transaction: Mapping[str, Any]) -> LinkPayment | None:
    """The payment a transaction is, if it is money in through a payment link; else None."""
    transaction_id = _transaction_id(transaction)
    if transaction_id is None:
        return None
    if transaction.get("decline_reason"):
        return None
    amount = transaction.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return None
    if transaction.get("currency") != "GBP":
        return None
    link_id = _link_id(transaction)
    if link_id is None:
        return None
    occurred_at = _created(transaction.get("created"))
    if occurred_at is None:
        return None

    counterparty = transaction.get("counterparty")
    if not isinstance(counterparty, Mapping):
        counterparty = {}
    name = counterparty.get("name")
    payer_name = (name.strip()[:_MAX_NAME] or None) if isinstance(name, str) else None
    return LinkPayment(
        transaction_id=transaction_id,
        link_id=link_id,
        amount_pence=amount,
        occurred_at=occurred_at,
        payer_user_id=_user_id(counterparty.get("user_id")),
        payer_name=payer_name,
        pots=tuple(sorted(set(pot_mentions(transaction)))),
    )


@dataclass(frozen=True)
class _PotDeposit:
    transaction_id: str
    pots: tuple[tuple[str, str], ...]
    amount_pence: int
    occurred_at: datetime
    metadata: Mapping[str, Any]

    @property
    def pot_refs(self) -> frozenset[str]:
        return frozenset(ref for ref, _field in self.pots)


def _pot_deposit(transaction: Mapping[str, Any]) -> _PotDeposit | None:
    """Money moved from a current account into a pot, whoever moved it.

    A deposit into a pot is money out of the current account, so its amount is negative.
    Money taken back out of a pot is never counted: the season's payout happens outside the
    app, and a top-up taken back out is corrected with an adjustment.
    """
    transaction_id = _transaction_id(transaction)
    if transaction_id is None or transaction.get("scheme") != POT_TRANSFER:
        return None
    if transaction.get("decline_reason"):
        return None
    amount = transaction.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount >= 0:
        return None
    if transaction.get("currency") != "GBP":
        return None
    if _link_id(transaction) is not None:
        # Money through a link is a link payment, never a pot deposit of its own.
        return None
    pots = tuple(sorted(set(pot_mentions(transaction))))
    occurred_at = _created(transaction.get("created"))
    if not pots or occurred_at is None:
        return None
    metadata = transaction.get("metadata")
    return _PotDeposit(
        transaction_id=transaction_id,
        pots=pots,
        amount_pence=-amount,
        occurred_at=occurred_at,
        metadata=metadata if isinstance(metadata, Mapping) else {},
    )


def _is_filing(metadata: Mapping[str, Any]) -> bool:
    """Whether a pot deposit is Monzo filing a link payment into its pot (Batch 216).

    Production's first read under Batch 214 showed every link payment followed by a deposit
    of its own into the pot, marked ``trigger=collection_pot`` and carrying who contributed.
    Either mark is enough: such a deposit is the member's money, already counted as their
    link payment, and must never also be counted as the owner's top-up.
    """
    return metadata.get("trigger") == FILING_TRIGGER or any(
        metadata.get(field_name) for field_name in CONTRIBUTOR_FIELDS
    )


def pot_top_up(transaction: Mapping[str, Any]) -> PotTopUp | None:
    """The top-up a transaction is, if someone moved money from a current account into a pot.

    Monzo filing a link payment into its pot is not one (:func:`filing`). Whether the pot is
    a league's is :func:`record_top_up`'s question.
    """
    deposit = _pot_deposit(transaction)
    if deposit is None or _is_filing(deposit.metadata):
        return None
    return PotTopUp(
        transaction_id=deposit.transaction_id,
        pot_refs=deposit.pot_refs,
        amount_pence=deposit.amount_pence,
        occurred_at=deposit.occurred_at,
        payer_user_id=_user_id(deposit.metadata.get("user_id")),
    )


def filing(transaction: Mapping[str, Any]) -> Filing | None:
    """The filing a transaction is, if it is Monzo moving a link payment into its pot."""
    deposit = _pot_deposit(transaction)
    if deposit is None or not _is_filing(deposit.metadata):
        return None
    metadata = deposit.metadata
    contributor = _user_id(metadata.get("collection_pot_contributor_user_id")) or _user_id(
        metadata.get("contributor_user_id")
    )
    name = metadata.get("contributor_name")
    return Filing(
        transaction_id=deposit.transaction_id,
        pots=deposit.pots,
        amount_pence=deposit.amount_pence,
        occurred_at=deposit.occurred_at,
        contributor_user_id=contributor,
        contributor_name=(name.strip()[:_MAX_NAME] or None) if isinstance(name, str) else None,
    )


def account_holders(accounts: Collection[Mapping[str, Any]]) -> AccountHolders:
    """Each connected account's holders, by their user ids, and their preferred names."""
    names: dict[str, str] = {}
    sole: dict[str, str] = {}
    for account in accounts:
        owners = account.get("owners")
        if not isinstance(owners, list):
            continue
        holders = []
        for owner in owners:
            if not isinstance(owner, Mapping):
                continue
            user_id = _user_id(owner.get("user_id"))
            if user_id is None:
                continue
            holders.append(user_id)
            name = owner.get("preferred_name")
            if isinstance(name, str) and name.strip():
                names[user_id] = name.strip()[:_MAX_NAME]
        account_id = account.get("id")
        if len(holders) == 1 and isinstance(account_id, str):
            sole[account_id] = holders[0]
    return AccountHolders(names=names, sole_holder=sole)


_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
_WORD = re.compile(r"[a-z][a-z0-9_-]{0,31}")
#: Fields whose value says what kind of move it was, never whose or how much.
_KIND_FIELDS = ("trigger", "p2p_initiator", "link_type")
_PREFIX = re.compile(r"[a-z]+_")


def _prefix(value: Any) -> str:
    if isinstance(value, str):
        found = _PREFIX.match(value)
        return f"{found.group(0)}…" if found else "<text>"
    return type(value).__name__


def transaction_shape(transaction: Mapping[str, Any], league_pots: Collection[str]) -> str:
    """One structure-only line about a transaction, for diagnosing an unplaced pot move.

    The scheme, the sign of the amount, the metadata's keys, the prefix of each id it
    holds, the fields that say what kind of move it was, the fields naming a pot, and
    whether any pot it names is a league's. Never an amount, a name, a note, a description
    or a whole id. Batch 214: the first real top-up is diagnosed from this.
    """
    amount = transaction.get("amount")
    sign = "0"
    if isinstance(amount, int) and not isinstance(amount, bool) and amount:
        sign = "-" if amount < 0 else "+"
    metadata = transaction.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    named = [key for key in metadata if isinstance(key, str) and _KEY.fullmatch(key)]
    others = len(metadata) - len(named)
    keys = sorted(named) + ([f"<{others} other>"] if others else [])
    ids = sorted(f"{key}={_prefix(metadata[key])}" for key in named if key.endswith("id"))
    kinds = sorted(
        f"{key}={value}"
        for key in _KIND_FIELDS
        if isinstance(value := metadata.get(key), str) and _WORD.fullmatch(value)
    )
    scheme = transaction.get("scheme")
    pots = pot_ref_fields(transaction)
    fields = sorted({field_name for _ref, field_name in pot_mentions(transaction)})
    return (
        f"scheme={scheme if isinstance(scheme, str) and _WORD.fullmatch(scheme) else '<other>'}"
        f" sign={sign} description={_prefix(transaction.get('description'))}"
        f" keys={','.join(keys) or '-'} ids={','.join(ids) or '-'}"
        f" kinds={','.join(kinds) or '-'} pot_fields={','.join(fields) or '-'}"
        f" league_pot={'yes' if set(pots) & set(league_pots) else 'no'}"
    )


async def _member_for(
    db: AsyncSession, league_id: uuid.UUID, payer_user_id: str | None, payer_name: str | None
) -> uuid.UUID | None:
    """The member the payer map says this payer is, if they still belong to the league."""
    if payer_user_id is not None:
        key = PayerMapping.monzo_user_id == payer_user_id
    elif payer_name and normalise_payer_name(payer_name):
        key = PayerMapping.normalised_name == normalise_payer_name(payer_name)
    else:
        return None
    player_id = await db.scalar(
        select(PayerMapping.player_id).where(PayerMapping.league_id == league_id, key)
    )
    if player_id is None:
        return None
    # The organiser's own rule for any entry: only for someone who is, or was, a member.
    member = await db.scalar(
        select(LeagueMembership.id).where(
            LeagueMembership.league_id == league_id, LeagueMembership.player_id == player_id
        )
    )
    return player_id if member is not None else None


async def _write_payment(
    db: AsyncSession,
    league_id: uuid.UUID,
    player_id: uuid.UUID | None,
    *,
    transaction_id: str,
    amount_pence: int,
    occurred_at: datetime,
    payer_user_id: str | None,
    payer_name: str | None,
) -> bool:
    """One payment from Monzo, written at most once by its transaction id."""
    written = await db.scalar(
        insert(LedgerEntry)
        .values(
            id=uuid.uuid4(),
            league_id=league_id,
            player_id=player_id,
            kind=LedgerKind.payment,
            amount_pence=amount_pence,
            monzo_transaction_id=transaction_id,
            payer_monzo_user_id=payer_user_id,
            payer_name=payer_name,
            occurred_at=occurred_at,
        )
        .on_conflict_do_nothing(constraint="uq_ledger_entries_monzo_transaction")
        .returning(LedgerEntry.id)
    )
    return written is not None


async def record_link_payment(
    db: AsyncSession, payment: LinkPayment, *, counting_since: datetime
) -> Recorded:
    """Write one link payment to its league's ledger, once. The caller commits."""
    if payment.occurred_at < counting_since:
        return Recorded.before_counting
    league_id = await db.scalar(select(League.id).where(League.monzo_link_id == payment.link_id))
    if league_id is None:
        return Recorded.not_a_league_link
    player_id = await _member_for(db, league_id, payment.payer_user_id, payment.payer_name)
    written = await _write_payment(
        db,
        league_id,
        player_id,
        transaction_id=payment.transaction_id,
        amount_pence=payment.amount_pence,
        occurred_at=payment.occurred_at,
        payer_user_id=payment.payer_user_id,
        payer_name=payment.payer_name,
    )
    if not written:
        return Recorded.duplicate
    return Recorded.matched if player_id is not None else Recorded.queued


async def _learn(
    db: AsyncSession, league_id: uuid.UUID, pots: tuple[tuple[str, str], ...], now: datetime
) -> PotsLearned:
    """Keep each pot identifier as this league's. One league per pot: a held one stays put."""
    refs = frozenset(ref for ref, _field in pots)
    rows = await db.execute(
        select(MonzoPot.pot_ref, MonzoPot.league_id).where(MonzoPot.pot_ref.in_(refs))
    )
    held: dict[str, uuid.UUID] = {row.pot_ref: row.league_id for row in rows}
    learned: set[str] = set()
    for ref in sorted(refs - held.keys()):
        inserted = await db.scalar(
            insert(MonzoPot)
            .values(id=uuid.uuid4(), league_id=league_id, pot_ref=ref, learned_at=now)
            .on_conflict_do_nothing(constraint="uq_monzo_pots_pot_ref")
            .returning(MonzoPot.id)
        )
        if inserted is not None:
            learned.add(ref)
    clash = any(holder != league_id for holder in held.values())
    fields = frozenset(field_name for ref, field_name in pots if ref in learned)
    return PotsLearned(fields=fields, clash=clash)


async def learn_pots(db: AsyncSession, payment: LinkPayment, *, now: datetime) -> PotsLearned:
    """Remember the pot this link payment was filed into as its league's. The caller commits.

    Learned from any of the league's link payments, however early or often read: each says
    the same thing. One league per pot, so a pot another league's link already files into
    stays that league's, and the clash is reported for the log.
    """
    league_id = await db.scalar(select(League.id).where(League.monzo_link_id == payment.link_id))
    if league_id is None or not payment.pots:
        return PotsLearned(fields=frozenset(), clash=False)
    return await _learn(db, league_id, payment.pots, now)


def _same_payer(filed: Filing, payer_user_id: str | None, payer_name: str | None) -> bool:
    """Whether a link payment's payer is who Monzo says contributed the filed money."""
    if filed.contributor_user_id is not None and payer_user_id is not None:
        return filed.contributor_user_id == payer_user_id
    if filed.contributor_name and payer_name:
        mine = normalise_payer_name(filed.contributor_name)
        return bool(mine) and mine == normalise_payer_name(payer_name)
    return False


async def learn_pots_from_filing(db: AsyncSession, filed: Filing, *, now: datetime) -> PotsLearned:
    """Learn how pot deposits name a league's pot, from Monzo filing one of its link payments.

    The filing is tied to its league through the link payment it files, which the ledger
    already holds: the same amount, made within :data:`FILING_WINDOW`, from the filing's
    contributor. If no contributor matches, a single league whose link payment fits the
    amount and time is taken; anything less certain teaches nothing. The caller commits.
    """
    candidates = (
        await db.execute(
            select(LedgerEntry.league_id, LedgerEntry.payer_monzo_user_id, LedgerEntry.payer_name)
            .join(League, League.id == LedgerEntry.league_id)
            .where(
                League.monzo_link_id.is_not(None),
                LedgerEntry.kind == LedgerKind.payment,
                LedgerEntry.monzo_transaction_id.is_not(None),
                LedgerEntry.amount_pence == filed.amount_pence,
                LedgerEntry.occurred_at >= filed.occurred_at - FILING_WINDOW,
                LedgerEntry.occurred_at <= filed.occurred_at + FILING_WINDOW,
            )
        )
    ).all()
    by_payer = {
        row.league_id
        for row in candidates
        if _same_payer(filed, row.payer_monzo_user_id, row.payer_name)
    }
    by_amount = {row.league_id for row in candidates}
    if len(by_payer) == 1:
        (league_id,) = by_payer
        joined_by = "payer"
    elif not by_payer and len(by_amount) == 1:
        (league_id,) = by_amount
        joined_by = "amount_and_time"
    else:
        return PotsLearned(fields=frozenset(), clash=False)
    learned = await _learn(db, league_id, filed.pots, now)
    return PotsLearned(fields=learned.fields, clash=learned.clash, joined_by=joined_by)


async def league_pot_refs(db: AsyncSession) -> set[str]:
    """Every pot identifier some league's link payments have named."""
    return set((await db.scalars(select(MonzoPot.pot_ref))).all())


async def a_league_lacks_its_pot(db: AsyncSession) -> bool:
    """Whether some league with a link id has no pot that pot deposits can name yet.

    Its link payments name the link's ``collectionpot_…``, but pot deposits, the owner's
    among them, name the same pot by ``pot_…`` (Batch 216), learned from Monzo's filings.
    Until a league has one of those, reading history once for them is worth it.
    """
    return bool(
        await db.scalar(
            select(
                exists().where(
                    League.monzo_link_id.is_not(None),
                    ~exists().where(
                        MonzoPot.league_id == League.id,
                        ~MonzoPot.pot_ref.startswith(LINK_POT_PREFIX),
                    ),
                )
            )
        )
    )


async def a_top_up_was_recognised(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(exists().where(MonzoPot.first_top_up_at.is_not(None)))))


async def record_top_up(
    db: AsyncSession,
    top_up: PotTopUp,
    *,
    counting_since: datetime,
    payer_name: str | None,
    now: datetime,
) -> Recorded:
    """Write a top-up into a league's pot to that league's ledger, once. The caller commits."""
    if top_up.occurred_at < counting_since:
        return Recorded.before_counting
    pots = (await db.scalars(select(MonzoPot).where(MonzoPot.pot_ref.in_(top_up.pot_refs)))).all()
    leagues = {pot.league_id for pot in pots}
    if len(leagues) != 1:
        return Recorded.not_a_league_pot
    (league_id,) = leagues
    if top_up.occurred_at < min(pot.learned_at for pot in pots):
        return Recorded.before_pot_known
    player_id = await _member_for(db, league_id, top_up.payer_user_id, None)
    written = await _write_payment(
        db,
        league_id,
        player_id,
        transaction_id=top_up.transaction_id,
        amount_pence=top_up.amount_pence,
        occurred_at=top_up.occurred_at,
        payer_user_id=top_up.payer_user_id,
        payer_name=(payer_name or "").strip()[:_MAX_NAME] or None,
    )
    if not written:
        return Recorded.duplicate
    await db.execute(
        update(MonzoPot)
        .where(MonzoPot.id.in_([pot.id for pot in pots]), MonzoPot.first_top_up_at.is_(None))
        .values(first_top_up_at=now)
    )
    return Recorded.matched if player_id is not None else Recorded.queued
