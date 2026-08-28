"""The limits that guard credentials survive a redeploy

Batch 99. Every rate-limit counter in the app lived in process memory — ``limits``'
``MemoryStorage``, reached through ``slowapi`` — so a Railway restart handed every
IP-keyed limiter a brand new bucket. This project redeploys often, and a deploy is
something an attacker can simply *wait for*: five login attempts against a name,
a deploy, five more, indefinitely, with no counter ever reaching its ceiling.

Only the limits where a reset is a **security event** move here:

* ``/auth/login`` — ``5/15 minutes`` per ``login:<name>:<ip>``;
* ``/auth/pin/reset-request`` — ``3/hour`` per client address.

The provider-budget limiters (``PICK_SUBMIT_SHARED_LIMIT``,
``PROVIDER_SLATE_FETCH_LIMIT``, ``PICK_SUBMIT_LIMIT``) deliberately stay in memory. A
reset there costs provider requests, not protection, and paying a database round trip on
the pick path to protect a quota that refills hourly would be the wrong trade. Batch 99's
tests assert that split in both directions so it stays a decision rather than an
accident.

The per-profile PIN lockout (``profiles.failed_login_count`` / ``locked_until``) was
already durable and is untouched. This closes the IP-keyed half that sits in front of it.

**Shape.** One row per live bucket, not one per window: the upsert rolls
``window_start`` forward in place, so a key hit every fifteen minutes for a season is one
row. ``(bucket_key, limit_item)`` is the primary key — ``limit_item`` is
``RateLimitItem.key_for()``, so a route carrying two windows cannot collapse them into
one counter. ``expires_at`` is indexed for the nightly prune and for nothing else.

**Recovery.** Nothing reads this table except the limiter, and an empty table is exactly
the state today's process has after every restart. If the migration has to be rolled
back, dropping it costs at most one window of accumulated counts — which is the
behaviour this batch replaces, not a regression against it. That is the forward recovery
plan: there is no data here to lose.

Revision ID: 018
Revises: 017
Create Date: 2026-08-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket_key", sa.String(200), primary_key=True),
        sa.Column("limit_item", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=False), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=False), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_counters_expires_at", "rate_limit_counters", ["expires_at"]
    )

    # ── Supabase lockdown for the new table (mirrors 003/004/009/011) ────────
    # This one matters more than most: the rows carry a display name and a client IP,
    # which is exactly the pairing the anon key must never be able to read.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.rate_limit_counters ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.rate_limit_counters FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.rate_limit_counters FROM anon, authenticated;
                DROP POLICY IF EXISTS deny_anon_authenticated ON public.rate_limit_counters;
                CREATE POLICY deny_anon_authenticated ON public.rate_limit_counters
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_expires_at", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
