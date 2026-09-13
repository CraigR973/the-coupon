"""A deployment-wide season calendar and additive round labels

Batch 113. A league joining in September used to start again at Gameweek 1 because
``gameweeks.number`` is deliberately a per-league, never-reused ordinal. This revision
adds the deployment calendar that gives the same football week the same public name in
every league, without changing that internal ordinal.

The migration deliberately creates an empty table. The separately invoked backfill
derives the anchor from the earliest stored round, reports every public label that will
move, and writes the calendar only with ``--apply``. Shipping the schema therefore never
silently renames a round members have already played.

Revision ID: 025
Revises: 024
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "season_calendars",
        sa.Column("season", sa.Integer(), primary_key=True),
        sa.Column("week_one_anchor", sa.Date(), nullable=False),
        sa.Column(
            "extra_weeks",
            ARRAY(sa.Date()),
            server_default=sa.text("ARRAY[]::date[]"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Site-admin API only. The browser never reads this table through Supabase's data
    # API, so the anon/authenticated roles get no fallback path around FastAPI's gate.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.season_calendars ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.season_calendars FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.season_calendars
                    FROM anon, authenticated;
                DROP POLICY IF EXISTS deny_anon_authenticated ON public.season_calendars;
                CREATE POLICY deny_anon_authenticated ON public.season_calendars
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)
def downgrade() -> None:
    op.drop_table("season_calendars")
