"""The one Monzo connection the payments service reads league payments through. Batch 208.

ADR 0009 option B. The owner connects once, in a browser and then in the Monzo app, and the
payments service keeps the result here: the tokens, encrypted with a key only that service
holds (``MONZO_TOKEN_ENCRYPTION_KEY``), and what it needs to keep reading unattended.

The API reads the *health* columns of this row for the organiser's payments screen and
nothing else. It never holds the key, so the two token columns are opaque to it, and to
anyone else who can read the database.

There is at most one row (``singleton``): one owner, one bank login, one live token, since
Monzo invalidates a client's previous token whenever a new one is issued.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class MonzoLinkStatus(StrEnum):
    """Where the connection is. Only ``connected`` reads anything.

    ``not_connected`` — nobody has finished connecting (a connect may be half-way through).
    ``awaiting_approval`` — the browser half is done; Monzo will not release account data
    until the owner also approves in the Monzo app. ``connected`` — reading.
    ``needs_reconnect`` — Monzo refused the refresh token, so only a fresh connect helps.
    """

    not_connected = "not_connected"
    awaiting_approval = "awaiting_approval"
    connected = "connected"
    needs_reconnect = "needs_reconnect"


class MonzoConnection(Base):
    __tablename__ = "monzo_connections"
    __table_args__ = (
        CheckConstraint("singleton", name="ck_monzo_connections_singleton"),
        CheckConstraint(
            "status IN ('not_connected', 'awaiting_approval', 'connected', 'needs_reconnect')",
            name="ck_monzo_connections_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: Always true, and unique: the database's own guarantee that there is one row.
    singleton: Mapped[bool] = mapped_column(
        Boolean, nullable=False, unique=True, server_default=text("true"), default=True
    )
    status: Mapped[MonzoLinkStatus] = mapped_column(
        Enum(
            MonzoLinkStatus,
            name="monzo_link_status",
            native_enum=False,
            create_constraint=False,
            length=30,
            values_callable=lambda kinds: [kind.value for kind in kinds],
        ),
        nullable=False,
        default=MonzoLinkStatus.not_connected,
    )
    #: The Monzo user whose account this reads. A connect by anyone else is refused while
    #: this one holds it.
    monzo_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Fernet tokens, never the bearer tokens themselves.
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    #: Payments made before this instant are never counted automatically: the owner records
    #: them as opening balances (ADR 0009 launch step 8). Set by the first connect and kept
    #: through every reconnect by the same Monzo user.
    counting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    #: The start of the last complete catch-up read. The next one reads from an hour before
    #: it, so a transaction Monzo lists late is still seen.
    read_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    webhook_registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    #: A half-finished connect: the SHA-256 of the OAuth ``state`` it sent, and when that
    #: stops being accepted. Cleared when the callback uses it.
    oauth_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oauth_state_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    #: Link health for the organiser's screen. ``last_error`` is a short code, never a
    #: response body.
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
