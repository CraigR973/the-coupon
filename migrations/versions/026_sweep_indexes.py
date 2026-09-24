"""Indexes for the reads that sweep rounds, which had none they could use

Batch 146. Two reads walk the whole table today and will keep doing so as rounds
accumulate:

* stranded-round retirement and discovery range over ``gameweeks.starts_on``, which had
  no index at all — the unique constraint on ``(league_id, starts_on)`` is left-anchored
  on the league and cannot serve a date range across every league;
* the settle sweep and retirement's "has anyone picked on this round?" existence check
  filter ``picks`` by ``gameweek_id`` alone, and ``ix_picks_league_gameweek`` is
  left-anchored on ``league_id``. A round belongs to exactly one league since Batch 14,
  so those reads have no league to hand it.

Both are additive. Nothing is dropped, no column changes type, and no row is rewritten —
the deployed image is entirely unaffected by the presence of two more indexes. The
recovery note this revision ships with is
``docs/runbooks/migration-026-recovery.md``.

Plain ``CREATE INDEX`` rather than ``CONCURRENTLY``: Alembic runs a revision inside a
transaction and ``CONCURRENTLY`` cannot, and at production's size — 87 picks, 24
gameweeks, measured 2026-09-23 — the build is sub-millisecond. The write lock it takes is
not worth engineering around until these tables are orders of magnitude larger; the
recovery note says at what point that stops being true.

Revision ID: 026
Revises: 025
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_gameweeks_starts_on", "gameweeks", ["starts_on"])
    op.create_index("ix_picks_gameweek_id", "picks", ["gameweek_id"])


def downgrade() -> None:
    op.drop_index("ix_picks_gameweek_id", table_name="picks")
    op.drop_index("ix_gameweeks_starts_on", table_name="gameweeks")
