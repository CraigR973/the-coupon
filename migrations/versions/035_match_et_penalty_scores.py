"""extra-time and penalty shootout scores for display.

The matches table records only the 90-minute scoreline (``actual_home_score`` /
``actual_away_score`` — the basis for prediction scoring per §7) plus the
``extra_time`` / ``penalties`` flags and ``penalty_winner_id``. To show the full
story of a knockout match we also persist the score at the end of extra time and
the penalty shootout tally. These columns are display-only — prediction scoring
is unaffected and still keys off the 90-minute score.

All four are nullable: NULL for matches that never reached that phase (every
group game, and any knockout settled inside 90 minutes).

Revision ID: 035
Revises: 034
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("extra_time_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("extra_time_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("penalty_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("penalty_away_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "penalty_away_score")
    op.drop_column("matches", "penalty_home_score")
    op.drop_column("matches", "extra_time_away_score")
    op.drop_column("matches", "extra_time_home_score")
