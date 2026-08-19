"""Name the round: a per-season sequence number on gameweeks

Batch 41. The coupon showed a date where members expect "Gameweek N", in two
places — the pick screen's header and the back/forward control — and no number
existed anywhere to show. ``gameweeks`` carried ``starts_on``, ``status``,
``locks_at_utc``, ``picks_open_at_utc`` and ``settled_at``, and nothing else.

Deriving an ordinal on read was the cheaper option and is the wrong one. It was
defensible until Batch 35, which made "the round a league is on" no longer the
newest ``starts_on``: a one-off round (Boxing Day, say) sits *mid-sequence*, so
an ordinal recomputed on every read renumbers every round after it the moment an
admin inserts one. A member's "Gameweek 12" would silently become a different
week. Storing it keeps history stable, and makes a one-off simply the next number
— which is honest, because it is the next round that league plays.

One additive, nullable column:

* ``gameweeks.number`` (integer, nullable). Assigned at discovery as one past the
  highest the league already holds in the same season. ``NULL`` is tolerated
  throughout — a round may predate this migration's backfill in a database
  restored from an older dump — and every read treats a missing number as "do not
  label this round" rather than as an error.

The backfill numbers existing rounds per league, per season, in ``starts_on``
order. The season expression duplicates :func:`src.services.football_provider.season_for`
(a season is named by its starting year and rolls over in July) because a
migration must not import application code that will keep changing underneath it.
If that rollover month ever moves, this migration stays correct for the rows it
wrote and the application takes over from there.

No unique constraint. The season a number is unique *within* is derived from
``starts_on``, not stored, so the database cannot express the invariant without a
second column that nothing else needs. It is held by ``next_gameweek_number``.

No Supabase lockdown block: ``gameweeks`` already has RLS forced by 003/004, and
a column inherits its table's policies. Only a brand-new table needs the block
(009, 011).

The downgrade drops the column, which loses the numbering. That is lossless in
the sense that matters — every number is recoverable by re-running the same
backfill, because it is a pure function of ``league_id`` and ``starts_on``.

Revision ID: 014
Revises: 013
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `season_for` in SQL: a season is named by its starting year and rolls over in July,
# so August 2026 and February 2027 are both season 2026.
_SEASON_EXPRESSION = """
    CASE WHEN EXTRACT(MONTH FROM starts_on) >= 7
         THEN EXTRACT(YEAR FROM starts_on)
         ELSE EXTRACT(YEAR FROM starts_on) - 1
    END
"""


def upgrade() -> None:
    op.add_column("gameweeks", sa.Column("number", sa.Integer(), nullable=True))
    op.execute(
        f"""
        UPDATE gameweeks AS g
        SET number = numbered.rn
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY league_id, {_SEASON_EXPRESSION}
                       ORDER BY starts_on
                   ) AS rn
            FROM gameweeks
        ) AS numbered
        WHERE g.id = numbered.id
        """
    )


def downgrade() -> None:
    op.drop_column("gameweeks", "number")
