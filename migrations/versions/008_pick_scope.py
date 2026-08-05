"""Add the per-league pick scope and its fixture-level uniqueness index

Batch 10 makes "claiming any market on a game takes the whole game" available as
a per-league rule, superseding the product contract's "a selection can be held
by only one member" for leagues that opt in.

The rule is per-league but uniqueness is enforced by the database, and a
PostgreSQL index predicate may only reference columns of the table it indexes —
it cannot join to ``leagues``. So the scope is denormalised onto ``picks`` at
write time and the fixture-level index is *partial* on that column:

    uq_picks_league_gameweek_fixture
        ON picks (league_id, gameweek_id, fixture_id)
        WHERE pick_scope = 'fixture'

``uq_picks_league_gameweek_selection`` is deliberately **kept**. Fixture-level
uniqueness implies selection-level uniqueness — if a game can be held once, so
can any selection within it — so the older constraint is true in both modes, and
it remains the operative enforcement for leagues on the selection rule. Dropping
it would leave those leagues with no backstop at all.

Both defaults are ``selection``: every existing league keeps exactly today's
behaviour, and the backfill cannot violate the new index because the new index
ignores every row it writes. Opting a league in is a deliberate act.

Note for whoever sizes a league: the fixture rule shrinks the pick pool roughly
fivefold (three match-odds outcomes plus two BTTS outcomes collapse to one
claim), so a 15-member league needs 15 fixtures rather than three.

Revision ID: 008
Revises: 007
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgENUM

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pick_scope AS ENUM ('selection', 'fixture');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.add_column(
        "leagues",
        sa.Column(
            "pick_scope",
            PgENUM(name="pick_scope", create_type=False),
            nullable=False,
            server_default="selection",
        ),
    )
    op.add_column(
        "picks",
        sa.Column(
            "pick_scope",
            PgENUM(name="pick_scope", create_type=False),
            nullable=False,
            server_default="selection",
        ),
    )
    op.create_index(
        "uq_picks_league_gameweek_fixture",
        "picks",
        ["league_id", "gameweek_id", "fixture_id"],
        unique=True,
        postgresql_where=sa.text("pick_scope = 'fixture'"),
    )


def downgrade() -> None:
    op.drop_index("uq_picks_league_gameweek_fixture", table_name="picks")
    op.drop_column("picks", "pick_scope")
    op.drop_column("leagues", "pick_scope")
    op.execute("DROP TYPE IF EXISTS pick_scope")
