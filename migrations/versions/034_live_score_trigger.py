"""widen matches_score_results AFTER trigger to re-fire on every live score change.

Migration 005 created the AFTER UPDATE trigger ``matches_score_results`` with a
WHEN clause that only fires on the NULL → non-null transition (a result entered
for the first time). U63 writes running in-play scores during a match, so the
trigger must now re-fire on *every* real score change (0-0 → 1-0 → 2-1) to
cascade each goal into predictions + leaderboard snapshots — while still
skipping no-op sync ticks where the score has not moved (``IS DISTINCT FROM``).

Only the trigger's WHEN clause changes; the ``matches_score_results()`` function
body is untouched. The BEFORE trigger ``matches_set_result_entered_at`` keeps its
original NULL → non-null gate, so ``result_entered_at`` is stamped at the first
score write (≈ kickoff) — an accepted trade-off, not the final whistle.

Revision ID: 034
Revises: 033
Create Date: 2026-06-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Function body is unchanged from migration 005 — only the trigger's WHEN
    # clause is widened. Drop + recreate the trigger against the existing fn.
    op.execute("DROP TRIGGER IF EXISTS matches_score_results ON matches")
    op.execute("""
        CREATE TRIGGER matches_score_results
        AFTER UPDATE OF actual_home_score, actual_away_score ON matches
        FOR EACH ROW
        WHEN (
            NEW.actual_home_score IS NOT NULL
            AND NEW.actual_away_score IS NOT NULL
            AND (
                OLD.actual_home_score IS DISTINCT FROM NEW.actual_home_score
                OR  OLD.actual_away_score IS DISTINCT FROM NEW.actual_away_score
            )
        )
        EXECUTE FUNCTION matches_score_results();
    """)


def downgrade() -> None:
    # Restore migration 005's NULL → non-null-only WHEN clause.
    op.execute("DROP TRIGGER IF EXISTS matches_score_results ON matches")
    op.execute("""
        CREATE TRIGGER matches_score_results
        AFTER UPDATE OF actual_home_score, actual_away_score ON matches
        FOR EACH ROW
        WHEN (
            (OLD.actual_home_score IS NULL OR OLD.actual_away_score IS NULL)
            AND NEW.actual_home_score IS NOT NULL
            AND NEW.actual_away_score IS NOT NULL
        )
        EXECUTE FUNCTION matches_score_results();
    """)
