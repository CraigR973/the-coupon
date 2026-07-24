"""score trigger: also re-fire when penalty_winner_id changes.

The ``matches_score_results`` AFTER trigger has, since migration 034 (U63 live
scores), fired only on a *change* to ``actual_home_score`` / ``actual_away_score``
(the ``IS DISTINCT FROM`` guard skips no-op live-sync ticks). That was correct
when the 90-minute score was the only scoring input.

It is no longer the only input. Migration 035 + result_sync now record the
advancer of a level-after-90 knockout in ``penalty_winner_id``, and the trigger's
own knockout grading falls back to ``penalty_winner_id`` to decide the winner of a
90-minute draw. But on the production auto-sync path that column is set *without*
moving the score:

  1. live in-play sync writes the running score up to e.g. 1-1 (trigger fires,
     ``penalty_winner_id`` still NULL -> advancement graded 0, correct);
  2. extra time leaves the 90-minute score pinned at 1-1 (no change);
  3. the final whistle sets ``penalty_winner_id`` but writes the same 1-1.

Step 3 changes no score column, so the trigger did not re-fire and the round
advancement points (5/10/15/20/25) were never awarded — every penalty-shootout
knockout silently lost its advancement scoring. The same gap hit an admin
override that corrected only ``penalty_winner_id`` on an unchanged scoreline.

This migration widens the trigger to also watch ``penalty_winner_id`` and to
re-fire when it changes. The ``matches_score_results()`` function body is
untouched; only the trigger's ``OF`` list and ``WHEN`` clause change. The BEFORE
trigger ``matches_set_result_entered_at`` is left alone — ``result_entered_at``
still means "first score write", not "advancer settled".

Revision ID: 037
Revises: 036
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Function body unchanged (migration 026, search_path set by 028) — only the
    # trigger's column list and WHEN clause widen to include penalty_winner_id.
    op.execute("DROP TRIGGER IF EXISTS matches_score_results ON matches")
    op.execute("""
        CREATE TRIGGER matches_score_results
        AFTER UPDATE OF actual_home_score, actual_away_score, penalty_winner_id ON matches
        FOR EACH ROW
        WHEN (
            NEW.actual_home_score IS NOT NULL
            AND NEW.actual_away_score IS NOT NULL
            AND (
                OLD.actual_home_score IS DISTINCT FROM NEW.actual_home_score
                OR  OLD.actual_away_score IS DISTINCT FROM NEW.actual_away_score
                OR  OLD.penalty_winner_id IS DISTINCT FROM NEW.penalty_winner_id
            )
        )
        EXECUTE FUNCTION matches_score_results();
    """)


def downgrade() -> None:
    # Restore migration 034's score-only WHEN clause.
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
