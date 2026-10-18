"""Payment notices: three mute categories and the record of what has been sent.

Batch 213. Additive only: three ``boolean NOT NULL DEFAULT false`` mute columns on
``notification_preferences`` (revision 027's pattern) and one new table, ``notification_sends``,
whose unique ``(kind, subject)`` pair is what makes each notice go out once however many
scheduler runs overlap.

The table is seeded with every link payment already in the ledger, so the first run after
this lands tells nobody about payments that arrived before it.

Revision ID: 030
Revises: 029
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MUTES = ("mute_payment_queue", "mute_monzo_link", "mute_payments")

#: Every link payment already in the ledger counts as announced, and each one that already
#: has a member as recorded. A module constant so the test runs the same statement.
SEED_SENT_NOTICES = """
    INSERT INTO notification_sends (kind, subject)
    SELECT 'payment_queued', id::text FROM ledger_entries
    WHERE kind = 'payment' AND monzo_transaction_id IS NOT NULL
    UNION ALL
    SELECT 'payment_recorded', id::text FROM ledger_entries
    WHERE kind = 'payment' AND monzo_transaction_id IS NOT NULL AND player_id IS NOT NULL
    ON CONFLICT ON CONSTRAINT uq_notification_sends_kind_subject DO NOTHING
"""


def upgrade() -> None:
    for name in _MUTES:
        op.add_column(
            "notification_preferences",
            sa.Column(name, sa.Boolean(), nullable=False, server_default="false"),
        )

    op.create_table(
        "notification_sends",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(64), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("kind", "subject", name="uq_notification_sends_kind_subject"),
    )

    # What the ledger already holds has been seen on the payments screen: nobody is told
    # about it again. A payment still queued is marked as announced to the admins, and
    # will still tell its member once it is assigned.
    op.execute(SEED_SENT_NOTICES)

    # Supabase Data API roles must not read what was sent. Revision 027's pattern.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.notification_sends ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.notification_sends FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.notification_sends
                    FROM PUBLIC, anon, authenticated;
                CREATE POLICY deny_anon_authenticated ON public.notification_sends
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("notification_sends")
    for name in reversed(_MUTES):
        op.drop_column("notification_preferences", name)
