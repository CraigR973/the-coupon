"""Lock down Supabase public schema metadata and defaults

Revision ID: 004
Revises: 003
Create Date: 2026-07-27

"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.schemata WHERE schema_name = 'auth'
            ) THEN
                ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.alembic_version FORCE ROW LEVEL SECURITY;

                REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
                    FROM anon, authenticated;
                REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public
                    FROM anon, authenticated;
                REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public
                    FROM PUBLIC, anon, authenticated;
                REVOKE USAGE ON SCHEMA public FROM PUBLIC, anon, authenticated;

                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

                ALTER FUNCTION public.set_updated_at()
                    SET search_path = pg_catalog;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.schemata WHERE schema_name = 'auth'
            ) THEN
                ALTER FUNCTION public.set_updated_at() RESET search_path;

                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT ALL PRIVILEGES ON TABLES TO anon, authenticated;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT ALL PRIVILEGES ON SEQUENCES TO anon, authenticated;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT EXECUTE ON FUNCTIONS TO PUBLIC, anon, authenticated;

                GRANT USAGE ON SCHEMA public TO PUBLIC;
                GRANT ALL PRIVILEGES ON TABLE public.alembic_version
                    TO anon, authenticated;
                GRANT EXECUTE ON FUNCTION public.set_updated_at()
                    TO PUBLIC, anon, authenticated;

                ALTER TABLE public.alembic_version NO FORCE ROW LEVEL SECURITY;
                ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY;
            END IF;
        END $$;
        """
    )
