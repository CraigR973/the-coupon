"""predictions: partial unique (player_id, match_id) WHERE deleted_at IS NULL

The prediction upsert soft-deletes rather than hard-deletes (``deleted_at``), but
``uq_predictions_player_match`` was created as a *plain*
``UNIQUE (player_id, match_id)`` that indexes soft-deleted rows too. Once a row is
soft-deleted the player can never be re-inserted: the backend upsert filters
``deleted_at IS NULL``, finds nothing, takes the INSERT path, and the INSERT
collides with the still-indexed soft-deleted row -> IntegrityError -> 500,
surfaced to the player as the generic "Prediction not saved -- check your
connection" toast.

This first bit in anger when the 2026-07-03 R16 bracket-fix purge *soft-deleted*
71 wrong-team predictions on matches 89/90/91: every one of those players was
then unable to re-predict the corrected fixture.

Fix: make the uniqueness partial on ``deleted_at IS NULL`` (the pattern already
used across migration 011), so it constrains only live rows and a fresh
prediction can be inserted alongside an old soft-deleted one. Written idempotent
(IF EXISTS / IF NOT EXISTS) because it was applied to production out-of-band
during the incident, so this migration must no-op cleanly on the prod DB while
still converting a fresh DB built from the earlier plain constraint.

Revision ID: 040
Revises: 039
Create Date: 2026-07-04

"""

from typing import Sequence, Union

from alembic import op

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dropping the constraint also drops its backing plain unique index, freeing
    # the name for the partial index below.
    op.execute(
        "ALTER TABLE predictions DROP CONSTRAINT IF EXISTS uq_predictions_player_match"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_predictions_player_match "
        "ON predictions (player_id, match_id) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Reverting to a plain constraint fails if any (player_id, match_id) now has
    # both a live and a soft-deleted row -- a state the partial index allows but
    # the plain constraint forbids. Acceptable: downgrade is a dev/rollback path.
    op.execute("DROP INDEX IF EXISTS uq_predictions_player_match")
    op.execute(
        "ALTER TABLE predictions ADD CONSTRAINT uq_predictions_player_match "
        "UNIQUE (player_id, match_id)"
    )
