"""The durable half of the rate limiter — one row per live bucket.

Batch 99. Every counter in the app lived in process memory (``limits``'
``MemoryStorage``, reached through ``slowapi``), so a Railway restart handed every
IP-keyed limiter a fresh bucket. This project redeploys often, and a deploy is
something an attacker can *wait for* rather than something they have to cause: five
login attempts, a redeploy, five more, indefinitely.

Not every limiter needed moving. The provider-budget ones — ``PICK_SUBMIT_SHARED_LIMIT``,
``PROVIDER_SLATE_FETCH_LIMIT`` — protect a *spend*, and a reset costs requests rather
than protection, so they stay in memory where they are fast and free. The two that stay
here are the ones where a reset is a security event: ``/auth/login`` and
``/auth/pin/reset-request``.

**One row per bucket, not one per window.** The upsert in
:func:`~src.rate_limit.consume_durable_limit` rolls ``window_start`` forward in place
rather than inserting a row per window, so a key that is hit every fifteen minutes for a
season occupies one row, not thousands.

**The table still grows with distinct keys, and that is deliberate.** ``login:<name>:<ip>``
takes the display name from the *unvalidated* request body, so a caller varying the name
writes a new row per attempt — the same property ``MemoryStorage`` has, moved from RAM to
disk. What bounds it in practice is that every such attempt pays a bcrypt hash against
:data:`~src.routers.auth._DUMMY_HASH` before it returns, and
``run_prune_rate_limit_counters`` deletes each expired row nightly.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

#: Widest ``bucket_key`` the table stores. ``login:<name>:<ip>`` is at most
#: ``6 + 100 + 1 + 45`` for a *valid* name, and the key is built from the raw body before
#: pydantic has rejected anything, so :func:`~src.rate_limit.durable_bucket_key` folds
#: anything longer into a digest rather than letting a 10 MB display name reach a
#: ``String`` column — or a btree index — and 500 the endpoint.
BUCKET_KEY_MAX_LENGTH = 200


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"

    #: The limiter key — ``login:<name>:<ip>`` or a bare client address.
    bucket_key: Mapped[str] = mapped_column(String(BUCKET_KEY_MAX_LENGTH), primary_key=True)
    #: ``RateLimitItem.key_for()`` — the canonical descriptor of the window, e.g.
    #: ``LIMITER/5/15/minute``. Part of the key so two limits on one route cannot
    #: share a counter.
    limit_item: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, index=True
    )
