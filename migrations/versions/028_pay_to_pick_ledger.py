"""Pay to pick: a league entry fee, a ledger of dues and payments, and a payer map.

Batch 205, from ADR 0009. Additive only: two nullable league columns and one nullable
membership column, two new empty tables, and two check constraints that every existing
league already satisfies (none has a fee).

Revision ID: 028
Revises: 027
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028"
down_revision: str | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leagues", sa.Column("entry_fee_pence", sa.Integer(), nullable=True))
    op.add_column("leagues", sa.Column("payment_link_url", sa.String(500), nullable=True))
    op.create_check_constraint(
        "ck_leagues_entry_fee_positive",
        "leagues",
        "entry_fee_pence IS NULL OR entry_fee_pence > 0",
    )
    op.create_check_constraint(
        "ck_leagues_entry_fee_private",
        "leagues",
        "entry_fee_pence IS NULL OR privacy = 'private'",
    )
    op.add_column(
        "league_memberships",
        sa.Column("adult_confirmed_at", sa.DateTime(timezone=False), nullable=True),
    )

    op.create_table(
        "ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "league_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False
        ),
        sa.Column(
            "player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=True
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column(
            "gameweek_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gameweeks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("monzo_transaction_id", sa.String(64), nullable=True),
        sa.Column("payer_monzo_user_id", sa.String(64), nullable=True),
        sa.Column("payer_name", sa.String(140), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint(
            "kind IN ('payment', 'round_due', 'due_reversal', 'cash_out', 'adjustment')",
            name="ck_ledger_entries_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'payment' AND amount_pence > 0)"
            " OR (kind IN ('round_due', 'cash_out') AND amount_pence < 0)"
            " OR (kind IN ('due_reversal', 'adjustment') AND amount_pence <> 0)",
            name="ck_ledger_entries_sign",
        ),
        sa.CheckConstraint(
            "kind IN ('round_due', 'due_reversal') OR gameweek_id IS NULL",
            name="ck_ledger_entries_round_only_on_dues",
        ),
        sa.CheckConstraint(
            "player_id IS NOT NULL OR (kind = 'payment' AND monzo_transaction_id IS NOT NULL)",
            name="ck_ledger_entries_queued_payment",
        ),
        sa.UniqueConstraint("monzo_transaction_id", name="uq_ledger_entries_monzo_transaction"),
    )
    op.create_index(
        "uq_ledger_entries_round_due",
        "ledger_entries",
        ["gameweek_id", "player_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'round_due'"),
    )
    op.create_index("ix_ledger_entries_league_player", "ledger_entries", ["league_id", "player_id"])
    op.create_index(
        "ix_ledger_entries_gameweek_player", "ledger_entries", ["gameweek_id", "player_id"]
    )

    op.create_table(
        "payer_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "league_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False
        ),
        sa.Column(
            "player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
        ),
        sa.Column("monzo_user_id", sa.String(64), nullable=True),
        sa.Column("normalised_name", sa.String(140), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "(monzo_user_id IS NULL) <> (normalised_name IS NULL)",
            name="ck_payer_mappings_one_key",
        ),
    )
    op.create_index(
        "uq_payer_mappings_league_monzo_user",
        "payer_mappings",
        ["league_id", "monzo_user_id"],
        unique=True,
        postgresql_where=sa.text("monzo_user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payer_mappings_league_name",
        "payer_mappings",
        ["league_id", "normalised_name"],
        unique=True,
        postgresql_where=sa.text("normalised_name IS NOT NULL"),
    )

    # Supabase Data API roles must not read who owes what, who paid, or a payer's name.
    # Revision 027's pattern, once per new table.
    for table in ("ledger_entries", "payer_mappings"):
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                    ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
                    REVOKE ALL PRIVILEGES ON TABLE public.{table}
                        FROM PUBLIC, anon, authenticated;
                    CREATE POLICY deny_anon_authenticated ON public.{table}
                        AS RESTRICTIVE FOR ALL TO anon, authenticated
                        USING (false) WITH CHECK (false);
                END IF;
            END $$;
        """)


def downgrade() -> None:
    op.drop_index("uq_payer_mappings_league_name", table_name="payer_mappings")
    op.drop_index("uq_payer_mappings_league_monzo_user", table_name="payer_mappings")
    op.drop_table("payer_mappings")
    op.drop_index("ix_ledger_entries_gameweek_player", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_league_player", table_name="ledger_entries")
    op.drop_index("uq_ledger_entries_round_due", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_column("league_memberships", "adult_confirmed_at")
    op.drop_constraint("ck_leagues_entry_fee_private", "leagues", type_="check")
    op.drop_constraint("ck_leagues_entry_fee_positive", "leagues", type_="check")
    op.drop_column("leagues", "payment_link_url")
    op.drop_column("leagues", "entry_fee_pence")
