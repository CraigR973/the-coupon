"""baseline schema — auth spine + leagues

The clone-and-own baseline for The Coupon: name + PIN auth with JWT refresh and
single-use activation codes, web-push subscriptions, per-user notification
preferences, an audit log, and the leagues / memberships / join-requests /
invites that make up a "leaderboard" group.

Gameweek / fixture / pick tables (the weekly accumulator mechanic) are added in
Batch 3. Everything lands in the default (public) schema — point this app at its
own database.

Revision ID: 001
Revises:
Create Date: 2026-07-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgENUM
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ENUM types ---
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE player_role AS ENUM ('player', 'admin');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE actor_type AS ENUM ('admin', 'player', 'system');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE action_type AS ENUM (
                'backup_failed', 'backup_downloaded', 'player_pin_reset',
                'league_created', 'league_updated', 'league_deleted',
                'league_privacy_changed', 'league_join_code_rotated',
                'league_invite_created', 'league_invite_revoked',
                'league_member_pin_reset',
                'member_joined', 'member_left', 'member_removed',
                'member_promoted', 'member_demoted',
                'join_request_created', 'join_request_approved', 'join_request_rejected'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE league_privacy AS ENUM ('private', 'public_request', 'public_open');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE league_member_role AS ENUM ('admin', 'player');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE join_request_status AS ENUM ('pending', 'approved', 'rejected', 'cancelled');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # --- profiles ---
    op.create_table(
        "profiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("pin_hash", sa.String(60), nullable=False),
        sa.Column(
            "role",
            PgENUM(name="player_role", create_type=False),
            nullable=False,
            server_default="player",
        ),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("display_name", name="uq_profiles_display_name"),
    )

    # --- refresh_tokens (JWT refresh + passwordless device / activation codes) ---
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("device_hint", sa.String(100), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        # 'refresh' (PIN-login JWT refresh), 'device' (passwordless long-lived
        # device token), or 'activation' (single-use code exchanged for a device token).
        sa.Column("purpose", sa.String(20), nullable=False, server_default="refresh"),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # --- push_subscriptions (web push) ---
    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subscription", JSONB, nullable=False),
        sa.Column("device_hint", sa.String(100), nullable=True),
        sa.Column("failed_send_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    # --- notification_preferences ---
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("global_mute", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quiet_hours_start", sa.DateTime(), nullable=True),
        sa.Column("quiet_hours_end", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_type", PgENUM(name="actor_type", create_type=False), nullable=False),
        sa.Column("action_type", PgENUM(name="action_type", create_type=False), nullable=False),
        sa.Column("target_table", sa.String(50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("changes", JSONB, nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_action_type", "audit_log", ["action_type"])

    # --- leagues (a "leaderboard" group) ---
    op.create_table(
        "leagues",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "privacy",
            PgENUM(name="league_privacy", create_type=False),
            nullable=False,
            server_default="private",
        ),
        sa.Column("max_members", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column(
            "join_code",
            sa.String(8),
            nullable=True,
            server_default=sa.text("upper(substr(md5(random()::text), 1, 6))"),
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("slug", name="uq_leagues_slug"),
        sa.UniqueConstraint("join_code", name="uq_leagues_join_code"),
        sa.CheckConstraint("max_members BETWEEN 2 AND 50", name="ck_leagues_max_members_range"),
    )
    op.create_index("ix_leagues_created_by", "leagues", ["created_by"])

    # --- league_memberships ---
    op.create_table(
        "league_memberships",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column(
            "role",
            PgENUM(name="league_member_role", create_type=False),
            nullable=False,
            server_default="player",
        ),
        sa.Column("display_name_override", sa.String(100), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "league_id", "player_id", name="uq_league_memberships_league_player"
        ),
    )
    op.create_index("ix_league_memberships_league_id", "league_memberships", ["league_id"])
    op.create_index("ix_league_memberships_player_id", "league_memberships", ["player_id"])

    # --- league_join_requests ---
    op.create_table(
        "league_join_requests",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column(
            "status",
            PgENUM(name="join_request_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "decided_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
            nullable=True,
        ),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_league_join_requests_league_id", "league_join_requests", ["league_id"])
    op.create_index("ix_league_join_requests_player_id", "league_join_requests", ["player_id"])

    # --- invites (single-use league invite links) ---
    op.create_table(
        "invites",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("display_name_hint", sa.String(100), nullable=True),
        sa.Column("league_id", UUID(as_uuid=True), sa.ForeignKey("leagues.id"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column(
            "claimed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id"),
            nullable=True,
        ),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("token", name="uq_invites_token"),
    )
    op.create_index("ix_invites_league_id", "invites", ["league_id"])

    # --- updated_at trigger (shared) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("profiles", "leagues", "league_memberships", "league_join_requests"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )

    # --- RLS policies (Supabase only — skipped on plain Postgres) ---
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.schemata WHERE schema_name = 'auth'
            ) THEN
                ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
                ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
                ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
                ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
                ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

                CREATE POLICY "profiles_select_own"
                    ON profiles FOR SELECT USING (auth.uid() = id);
                CREATE POLICY "profiles_update_own"
                    ON profiles FOR UPDATE USING (auth.uid() = id);

                CREATE POLICY "refresh_tokens_select_own"
                    ON refresh_tokens FOR SELECT USING (auth.uid() = user_id);
                CREATE POLICY "refresh_tokens_insert_own"
                    ON refresh_tokens FOR INSERT WITH CHECK (auth.uid() = user_id);
                CREATE POLICY "refresh_tokens_delete_own"
                    ON refresh_tokens FOR DELETE USING (auth.uid() = user_id);

                CREATE POLICY "push_subscriptions_select_own"
                    ON push_subscriptions FOR SELECT USING (auth.uid() = user_id);
                CREATE POLICY "push_subscriptions_insert_own"
                    ON push_subscriptions FOR INSERT WITH CHECK (auth.uid() = user_id);

                CREATE POLICY "notification_preferences_select_own"
                    ON notification_preferences FOR SELECT USING (auth.uid() = user_id);
                CREATE POLICY "notification_preferences_update_own"
                    ON notification_preferences FOR UPDATE USING (auth.uid() = user_id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("invites")
    op.drop_table("league_join_requests")
    op.drop_table("league_memberships")
    op.drop_table("leagues")
    op.drop_table("audit_log")
    op.drop_table("notification_preferences")
    op.drop_table("push_subscriptions")
    op.drop_table("refresh_tokens")
    op.drop_table("profiles")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
    op.execute("DROP TYPE IF EXISTS join_request_status")
    op.execute("DROP TYPE IF EXISTS league_member_role")
    op.execute("DROP TYPE IF EXISTS league_privacy")
    op.execute("DROP TYPE IF EXISTS action_type")
    op.execute("DROP TYPE IF EXISTS actor_type")
    op.execute("DROP TYPE IF EXISTS player_role")
