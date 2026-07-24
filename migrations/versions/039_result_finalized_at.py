"""add matches.result_finalized_at — anchor for the auto-result self-heal window

``result_entered_at`` is stamped by a BEFORE trigger when ``actual_home_score`` /
``actual_away_score`` first go non-null. Because the live-score sync writes the
in-play score *during* the match, that fires minutes after kickoff — not at full
time — so it cannot answer "how long ago did this result finalize?".

``result_finalized_at`` is stamped exactly once, when ``result_source`` first
becomes non-null (the full-time settle). It bounds the window during which
auto-sync may still revise an *auto* result if football-data corrects a transient
post-match payload (e.g. the extra-time aggregate served before ``regularTime`` is
populated). Rows finalized before this migration have NULL and are treated as
outside the window (frozen), preserving today's idempotent behaviour.

Revision ID: 039
Revises: 038
Create Date: 2026-07-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("result_finalized_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("matches", "result_finalized_at")
