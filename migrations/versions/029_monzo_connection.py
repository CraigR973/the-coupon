"""The Monzo connection, and the payment-link id that says which league a payment is for.

Batch 208, from ADR 0009. Additive only: one nullable league column with a check constraint
and a partial unique index that every existing league satisfies (none has one), and one new
empty table.

Revision ID: 029
Revises: 028
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "029"
down_revision: str | None = "028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leagues", sa.Column("monzo_link_id", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_leagues_monzo_link_id_shape",
        "leagues",
        "monzo_link_id IS NULL OR monzo_link_id ~ '^unipaylink_[A-Za-z0-9]+$'",
    )
    # One league per link, so a payment can never be counted towards two.
    op.create_index(
        "uq_leagues_monzo_link_id",
        "leagues",
        ["monzo_link_id"],
        unique=True,
        postgresql_where=sa.text("monzo_link_id IS NOT NULL"),
    )

    op.create_table(
        "monzo_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "singleton", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("monzo_user_id", sa.String(64), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("counting_since", sa.DateTime(timezone=False), nullable=True),
        sa.Column("read_through", sa.DateTime(timezone=False), nullable=True),
        sa.Column("webhook_registered_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("oauth_state_hash", sa.String(64), nullable=True),
        sa.Column("oauth_state_expires_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_error", sa.String(40), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("singleton", name="uq_monzo_connections_singleton"),
        sa.CheckConstraint("singleton", name="ck_monzo_connections_singleton"),
        sa.CheckConstraint(
            "status IN ('not_connected', 'awaiting_approval', 'connected', 'needs_reconnect')",
            name="ck_monzo_connections_status",
        ),
    )

    # Supabase Data API roles must not read the encrypted tokens or the link's health.
    # Revision 027's pattern.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.monzo_connections ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.monzo_connections FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.monzo_connections
                    FROM PUBLIC, anon, authenticated;
                CREATE POLICY deny_anon_authenticated ON public.monzo_connections
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("monzo_connections")
    op.drop_index("uq_leagues_monzo_link_id", table_name="leagues")
    op.drop_constraint("ck_leagues_monzo_link_id_shape", "leagues", type_="check")
    op.drop_column("leagues", "monzo_link_id")
