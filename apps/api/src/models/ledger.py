"""What members owe a league that charges a fee, and what they have paid. Batch 205.

ADR 0009. A league may carry ``entry_fee_pence``; every active member owes that much for
every round, and must be paid up to pick. The money itself moves outside the app, through
the league's payment link. These tables only record it.

**Every entry is permanent.** Nothing here is updated or deleted to correct a mistake: a
correction is another entry, recorded with who made it. The one column that is filled in
after the fact is a queued payment's member, which is null until a site admin says whose
payment it was (and is never changed again — a wrong assignment is corrected with
adjustments, like anything else).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDPrimaryKeyMixin


class LedgerKind(StrEnum):
    """The five things a ledger entry can record. Amounts are signed pence.

    ``payment`` (+) is money in: through the league's link (queued until assigned when the
    payer is not yet known) or cash handed to the organiser. ``round_due`` (-) is one
    round's fee, at most one per member per round. ``due_reversal`` undoes a round's
    standing due (+) when the round is voided or withdrawn, or the member leaves before it
    locks; a member who rejoins while that round is still open has the reversal undone by
    an opposite one (-), so a round's due and its reversals always net to the fee or to
    nothing. ``cash_out`` (-) is credit repaid outside the app. ``adjustment`` (+/-) is a
    site admin's correction or opening balance, always with a note.
    """

    payment = "payment"
    round_due = "round_due"
    due_reversal = "due_reversal"
    cash_out = "cash_out"
    adjustment = "adjustment"


#: The kinds that belong to one round. Their sum for a ``(round, member)`` is what that
#: member owes for the round: minus the fee, or zero.
DUE_KINDS = (LedgerKind.round_due, LedgerKind.due_reversal)


class LedgerEntry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('payment', 'round_due', 'due_reversal', 'cash_out', 'adjustment')",
            name="ck_ledger_entries_kind",
        ),
        CheckConstraint(
            "(kind = 'payment' AND amount_pence > 0)"
            " OR (kind IN ('round_due', 'cash_out') AND amount_pence < 0)"
            " OR (kind IN ('due_reversal', 'adjustment') AND amount_pence <> 0)",
            name="ck_ledger_entries_sign",
        ),
        # A due names its round. The reverse is enforced here, not that: a round that is
        # withdrawn takes its id off its (reversed) dues rather than taking them with it.
        CheckConstraint(
            "kind IN ('round_due', 'due_reversal') OR gameweek_id IS NULL",
            name="ck_ledger_entries_round_only_on_dues",
        ),
        # Only money that arrived through the link can be waiting for its member.
        CheckConstraint(
            "player_id IS NOT NULL OR (kind = 'payment' AND monzo_transaction_id IS NOT NULL)",
            name="ck_ledger_entries_queued_payment",
        ),
        UniqueConstraint("monzo_transaction_id", name="uq_ledger_entries_monzo_transaction"),
        # What makes recording a round's dues idempotent, however often the opening runs.
        Index(
            "uq_ledger_entries_round_due",
            "gameweek_id",
            "player_id",
            unique=True,
            postgresql_where=text("kind = 'round_due'"),
        ),
        Index("ix_ledger_entries_league_player", "league_id", "player_id"),
        Index("ix_ledger_entries_gameweek_player", "gameweek_id", "player_id"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id"), nullable=False
    )
    #: Null only for a payment that arrived through the link from a payer nobody has
    #: matched to a member yet — the admin queue.
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=True
    )
    kind: Mapped[LedgerKind] = mapped_column(
        Enum(
            LedgerKind,
            name="ledger_entry_kind",
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda kinds: [kind.value for kind in kinds],
        ),
        nullable=False,
    )
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    gameweek_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gameweeks.id", ondelete="SET NULL"), nullable=True
    )
    #: The bank's id for a payment through the link. Unique, so the same transaction can
    #: never be counted twice however often it is read.
    monzo_transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The payer's stable bank user id, set only when the bank gives one (a payer using
    #: the bank's own app). A card payer's per-payment anonymous id is not stored here.
    payer_monzo_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The name the payment arrived under, as the bank reported it.
    payer_name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: When the money moved, or when the round fell due. ``created_at`` is when it was
    #: written down, which for a payment read late or recorded by hand is later.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    #: Who wrote the entry; null for the system (a round opening, a member leaving).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    #: Who said whose a queued payment was, and when.
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class PayerMapping(Base, UUIDPrimaryKeyMixin):
    """Who a payer is, once a site admin has said so: one key per row, per league.

    A payer using the bank's app is known by their stable user id. A card payer arrives
    with a fresh anonymous id every time, so they are known by their name, normalised
    (:func:`~src.services.dues.normalise_payer_name`). Matching by name can be wrong; the
    queue and reversing adjustments are the remedy, and assigning again re-points the key.
    """

    __tablename__ = "payer_mappings"
    __table_args__ = (
        CheckConstraint(
            "(monzo_user_id IS NULL) <> (normalised_name IS NULL)",
            name="ck_payer_mappings_one_key",
        ),
        Index(
            "uq_payer_mappings_league_monzo_user",
            "league_id",
            "monzo_user_id",
            unique=True,
            postgresql_where=text("monzo_user_id IS NOT NULL"),
        ),
        Index(
            "uq_payer_mappings_league_name",
            "league_id",
            "normalised_name",
            unique=True,
            postgresql_where=text("normalised_name IS NOT NULL"),
        ),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leagues.id"), nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False
    )
    monzo_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalised_name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
