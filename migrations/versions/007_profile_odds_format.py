"""Add profiles.odds_format for the per-user odds display preference

Batch 9 lets each member read prices as decimal (``2.50``) or traditional UK
fractional (``6/4``). The preference is **display only**: ``picks.odds`` stays
``Numeric(6, 2)`` decimal and settlement keeps scoring ``round(odds × 10)``, so
nothing here touches how a pick is priced or what it is worth. Two members of
the same league can therefore read the same coupon in different notations and
still be on the same points.

It lives on ``profiles`` rather than ``league_memberships`` because it is a
property of how a person reads odds, not of a league they are in — someone in
three leagues wants fractional in all three.

Backfilled to ``decimal`` via the server default, which is what every existing
member already sees, so no one's display changes on deploy.

Revision ID: 007
Revises: 006
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgENUM

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE odds_format AS ENUM ('decimal', 'fractional');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.add_column(
        "profiles",
        sa.Column(
            "odds_format",
            PgENUM(name="odds_format", create_type=False),
            nullable=False,
            server_default="decimal",
        ),
    )


def downgrade() -> None:
    op.drop_column("profiles", "odds_format")
    op.execute("DROP TYPE IF EXISTS odds_format")
