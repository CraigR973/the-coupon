"""A completion event remembers which fixture it was

Batch 116. ``_completion_body`` reads ``gameweek_completions.selection``, a string copied
from ``Pick.runner_name`` at the transition, and that column is composed from the *market*
alone: a draw stores ``The Draw`` and a Both-Teams-To-Score claim stores ``Yes``. So the
one alert a round only ever sends once could reach twelve phones reading

    Dave picked Yes @ 1.80 · 12/12 picked — all picks are in

with no fixture in it anywhere.

The row is **deliberately frozen** — a retry runs after that member may have moved their
pick, and the event is what happened when the coupon filled — so the fixture cannot be
re-read at delivery. It has to be carried.

**Four columns, not one composed phrase.** Storing ``Both teams score (Forfar v Brechin)``
would work today and would make the next copy revision a migration: the stored value would
stop being a datum and become a rendered sentence. These four are the *data* a phrase is
rendered from (``src/services/selection_text.py``), and the copy stays in code where it can
be changed by changing code.

**Nullable, and read with a fallback.** A completion written before this migration has no
fixture to carry and no way to find one — the round may since have settled and the picker
may since have moved. ``_completion_body`` falls back to ``selection`` for those rows, which
is exactly the alert they would have produced anyway. A backfill would have to join back
through ``picks`` on a row that no longer describes the transition, which is the one thing
this table exists to avoid.

**Recovery.** Dropping all four restores the old behaviour completely: ``selection`` is
untouched and still carries what it always did, and ``_completion_body``'s fallback branch
*is* the pre-Batch-116 body. Nothing else reads them, and no pick, price or point is
derived from them.

Revision ID: 024
Revises: 023
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgENUM

revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The existing `pick_market` / `pick_outcome` types, reused rather than duplicated:
    # the value stored here is the same fact the pick carries, and a second enum would be
    # free to drift from it.
    op.add_column(
        "gameweek_completions",
        sa.Column("market", PgENUM(name="pick_market", create_type=False), nullable=True),
    )
    op.add_column(
        "gameweek_completions",
        sa.Column("outcome", PgENUM(name="pick_outcome", create_type=False), nullable=True),
    )
    # Same width as `fixtures.home` / `fixtures.away`, which is where they are copied from.
    op.add_column(
        "gameweek_completions", sa.Column("fixture_home", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "gameweek_completions", sa.Column("fixture_away", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("gameweek_completions", "fixture_away")
    op.drop_column("gameweek_completions", "fixture_home")
    op.drop_column("gameweek_completions", "outcome")
    op.drop_column("gameweek_completions", "market")
