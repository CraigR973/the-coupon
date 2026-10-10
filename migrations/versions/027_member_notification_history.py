"""Store league notifications for members without push and add category mutes.

Revision ID: 027
Revises: 026
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027"
down_revision: str | None = "026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("mute_pick_activity", "mute_round_updates", "mute_results"):
        op.add_column(
            "notification_preferences",
            sa.Column(name, sa.Boolean(), nullable=False, server_default="false"),
        )

    op.create_table(
        "member_notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "league_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_member_notifications_user_created",
        "member_notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_member_notifications_created", "member_notifications", ["created_at"]
    )

    # Supabase Data API roles must not read a member's league messages directly.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.member_notifications ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.member_notifications FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.member_notifications
                    FROM PUBLIC, anon, authenticated;
                CREATE POLICY deny_anon_authenticated ON public.member_notifications
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_index("ix_member_notifications_created", table_name="member_notifications")
    op.drop_index(
        "ix_member_notifications_user_created", table_name="member_notifications"
    )
    op.drop_table("member_notifications")
    for name in ("mute_results", "mute_round_updates", "mute_pick_activity"):
        op.drop_column("notification_preferences", name)
