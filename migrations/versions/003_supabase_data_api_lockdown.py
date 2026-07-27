"""Lock down Supabase Data API exposure

Revision ID: 003
Revises: 002
Create Date: 2026-07-26

"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES: tuple[str, ...] = (
    "profiles",
    "refresh_tokens",
    "push_subscriptions",
    "notification_preferences",
    "audit_log",
    "leagues",
    "league_memberships",
    "league_join_requests",
    "invites",
    "gameweeks",
    "fixtures",
    "picks",
)


def upgrade() -> None:
    table_list = ", ".join(f"'{table}'" for table in APP_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE
            table_name text;
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.schemata WHERE schema_name = 'auth'
            ) THEN
                FOREACH table_name IN ARRAY ARRAY[{table_list}]
                LOOP
                    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
                    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated',
                        table_name
                    );
                    EXECUTE format('DROP POLICY IF EXISTS deny_anon_authenticated ON public.%I', table_name);
                    EXECUTE format(
                        'CREATE POLICY deny_anon_authenticated ON public.%I '
                        'AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)',
                        table_name
                    );
                END LOOP;
                REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
                REVOKE USAGE ON SCHEMA public FROM anon, authenticated;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    table_list = ", ".join(f"'{table}'" for table in APP_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE
            table_name text;
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.schemata WHERE schema_name = 'auth'
            ) THEN
                FOREACH table_name IN ARRAY ARRAY[{table_list}]
                LOOP
                    EXECUTE format(
                        'DROP POLICY IF EXISTS deny_anon_authenticated ON public.%I',
                        table_name
                    );
                    EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', table_name);
                END LOOP;
            END IF;
        END $$;
        """
    )
