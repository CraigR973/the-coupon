"""League admin configuration: competition selection and the offered market set

Batch 15. Batch 14 already lifted the weekly *window* onto ``leagues`` (five
integers, defaulting to Saturday 15:00); this adds the other two things an admin
configures, so a league is no longer bound to "every UK competition, both
markets".

Two columns, both on ``leagues``, both defaulting to exactly today's behaviour:

* ``competitions`` (JSONB, nullable). ``NULL`` means *all UK leagues* — the group
  the slate has always used — so every existing league is unchanged. A non-null
  value is an explicit list of ``{"slug", "name"}`` objects, and the round only
  plays those competitions (filtered at link time in ``sync_slate``). Stored as a
  value blob rather than a join table because it is always read and written whole,
  never queried by competition, and bounded small by the provider's rate limit.

* ``offered_markets`` (``pick_market[]``, not null, default both). Which of the two
  markets the league offers. It is an *array of the existing enum*, not new enum
  values: widening the markets themselves would be a new ``pick_market`` value and
  a data migration, but choosing a subset of the two we already price is
  configuration. A check keeps the set non-empty — a league offering no market
  could not be picked in at all.

No Supabase lockdown block here: both are columns on ``leagues``, which already
has RLS forced by migrations 003/004, and a column inherits its table's policies.
Migration 009 needed a block only because it created a brand-new table.

Reversible and lossless in both directions — dropping the columns restores the
pre-Batch-15 shape, and every league was on the defaults, so nothing configured
is lost on the way down.

Revision ID: 010
Revises: 009
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgENUM

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The two markets shipped as `pick_market` in migration 002 — the default set is
# both, which is exactly what every league offered before this batch.
_DEFAULT_MARKETS = "ARRAY['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE']::pick_market[]"


def upgrade() -> None:
    # NULL = "all UK leagues" (the group the slate has always used). A non-null
    # array narrows the round to named competitions.
    op.add_column("leagues", sa.Column("competitions", postgresql.JSONB(), nullable=True))

    # An array of the existing enum, never a new type — reference it with
    # create_type=False so this does not try to recreate `pick_market`.
    op.add_column(
        "leagues",
        sa.Column(
            "offered_markets",
            postgresql.ARRAY(PgENUM(name="pick_market", create_type=False)),
            nullable=False,
            server_default=sa.text(_DEFAULT_MARKETS),
        ),
    )
    op.create_check_constraint(
        "ck_leagues_offered_markets_nonempty",
        "leagues",
        "cardinality(offered_markets) >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_leagues_offered_markets_nonempty", "leagues", type_="check")
    op.drop_column("leagues", "offered_markets")
    op.drop_column("leagues", "competitions")
