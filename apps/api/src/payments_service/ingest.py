"""From a Monzo transaction to a ledger entry. Batch 208.

ADR 0009's sixth rule. Only money that came in through a league's payment link counts — the
owner's other money from the same friends (a dinner split, say) never reaches the ledger.
The payer is matched on who paid, not on a reference:

* a payer using the Monzo app has a stable ``user_…`` id, matched through the league's
  payer map by that id;
* a card payer arrives with a fresh ``anonuser_…`` id every time, so is matched by name,
  normalised the way the organiser's assignment stores it;
* anyone the map does not know is queued for the organiser, who assigns them once.

Each payment is written at most once, keyed by Monzo's transaction id: the webhook's
``transaction.created`` and ``transaction.updated`` and every catch-up read all arrive at
the same row. A transaction this module turns away is simply not a payment; nothing about
it is kept, and nothing is logged beyond its id.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.services.dues import normalise_payer_name

TRANSACTION_ID = re.compile(r"tx_[A-Za-z0-9]+")
LINK_ID = re.compile(r"unipaylink_[A-Za-z0-9]+")
LINK_ID_FIELD = "universal_payment_link_id"
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


class Recorded(StrEnum):
    matched = "matched"
    queued = "queued"
    duplicate = "duplicate"
    not_a_league_link = "not_a_league_link"
    before_counting = "before_counting"


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


def link_payment(transaction: Mapping[str, Any]) -> LinkPayment | None:
    """The payment a transaction is, if it is money in through a payment link; else None."""
    transaction_id = transaction.get("id")
    if not (
        isinstance(transaction_id, str)
        and len(transaction_id) <= _MAX_ID
        and TRANSACTION_ID.fullmatch(transaction_id)
    ):
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
    user_id = counterparty.get("user_id")
    payer_user_id = (
        user_id
        if isinstance(user_id, str) and user_id.startswith("user_") and len(user_id) <= _MAX_ID
        else None
    )
    name = counterparty.get("name")
    payer_name = (name.strip()[:_MAX_NAME] or None) if isinstance(name, str) else None
    return LinkPayment(
        transaction_id=transaction_id,
        link_id=link_id,
        amount_pence=amount,
        occurred_at=occurred_at,
        payer_user_id=payer_user_id,
        payer_name=payer_name,
    )


async def _member_for(
    db: AsyncSession, league_id: uuid.UUID, payment: LinkPayment
) -> uuid.UUID | None:
    """The member the payer map says this payer is, if they still belong to the league."""
    if payment.payer_user_id is not None:
        key = PayerMapping.monzo_user_id == payment.payer_user_id
    elif payment.payer_name and normalise_payer_name(payment.payer_name):
        key = PayerMapping.normalised_name == normalise_payer_name(payment.payer_name)
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


async def record_link_payment(
    db: AsyncSession, payment: LinkPayment, *, counting_since: datetime
) -> Recorded:
    """Write one link payment to its league's ledger, once. The caller commits."""
    if payment.occurred_at < counting_since:
        return Recorded.before_counting
    league_id = await db.scalar(select(League.id).where(League.monzo_link_id == payment.link_id))
    if league_id is None:
        return Recorded.not_a_league_link
    player_id = await _member_for(db, league_id, payment)
    written = await db.scalar(
        insert(LedgerEntry)
        .values(
            id=uuid.uuid4(),
            league_id=league_id,
            player_id=player_id,
            kind=LedgerKind.payment,
            amount_pence=payment.amount_pence,
            monzo_transaction_id=payment.transaction_id,
            payer_monzo_user_id=payment.payer_user_id,
            payer_name=payment.payer_name,
            occurred_at=payment.occurred_at,
        )
        .on_conflict_do_nothing(constraint="uq_ledger_entries_monzo_transaction")
        .returning(LedgerEntry.id)
    )
    if written is None:
        return Recorded.duplicate
    return Recorded.matched if player_id is not None else Recorded.queued
