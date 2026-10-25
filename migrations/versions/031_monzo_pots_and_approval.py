"""The pots a league's link pays into, and when Monzo last approved the connection.

Batch 214. Additive only: one new table, ``monzo_pots``, and one nullable column,
``monzo_connections.approved_at``.

``monzo_pots`` is how the payments service recognises the owner's own top-ups. It learns
each league's pot from the pot identifiers that league's link payments carry, one league
per pot, and counts a top-up into that pot only if it was made after the pot was learned.
The table starts empty, so nothing the owner moved before this shipment is counted.

``approved_at`` is when the owner last approved the connection in the Monzo app. Monzo asks
for that again every 90 days, and the API warns the site admins a week before. The live
row is backfilled from ``webhook_registered_at``, which the first read after the approval
set.

Revision ID: 031
Revises: 030
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "031"
down_revision: str | None = "030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The connection already approved before this revision: the first connected read is when
#: Monzo released the account, and it registered the webhook in the same moment. A module
#: constant so the test runs the same statement.
BACKFILL_APPROVED_AT = """
    UPDATE monzo_connections
    SET approved_at = webhook_registered_at
    WHERE status = 'connected' AND approved_at IS NULL AND webhook_registered_at IS NOT NULL
"""


def upgrade() -> None:
    op.add_column(
        "monzo_connections",
        sa.Column("approved_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.execute(BACKFILL_APPROVED_AT)

    op.create_table(
        "monzo_pots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "league_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leagues.id"),
            nullable=False,
        ),
        sa.Column("pot_ref", sa.String(64), nullable=False),
        sa.Column(
            "learned_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("first_top_up_at", sa.DateTime(timezone=False), nullable=True),
        # One league per pot, so a top-up can never be counted towards two.
        sa.UniqueConstraint("pot_ref", name="uq_monzo_pots_pot_ref"),
    )
    op.create_index("ix_monzo_pots_league", "monzo_pots", ["league_id"])

    # Supabase Data API roles must not read which pots the owner's money moves into.
    # Revision 027's pattern.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.monzo_pots ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.monzo_pots FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.monzo_pots
                    FROM PUBLIC, anon, authenticated;
                CREATE POLICY deny_anon_authenticated ON public.monzo_pots
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_index("ix_monzo_pots_league", table_name="monzo_pots")
    op.drop_table("monzo_pots")
    op.drop_column("monzo_connections", "approved_at")
