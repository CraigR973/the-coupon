"""Matches say where they stand, not just whether they are over

Batch 110. ``matches`` had one bit of state — ``finished`` — and everything else lived in
``status``, which is free provider text ("FT", "PP", a live minute, sometimes nothing).
That was enough while the store only ever held finished matches, which it did, because
FotMob ingestion discarded every other kind on the way in.

It is not enough to answer "show me this club's season". A season contains matches that
have not been played, and a reader needs to tell three ``finished = false`` rows apart:
one being played now, one on next Saturday's card, and one called off. ``status`` cannot
do it — it is display text, it is not a closed set, and it is not something a query can
filter or compare on.

**Why a string and not an enum type.** The values are The Coupon's own vocabulary
(:class:`~src.services.football_provider.MatchState`), and a provider that later
distinguishes "abandoned" from "cancelled" should cost a code change and not a migration
against a live table. Every other status-ish column in this schema is a constrained
string for the same reason.

**Backfill.** Existing rows are exactly the two states the old column could express:
``finished = true`` becomes ``finished``, and everything else becomes ``scheduled``.
There is nothing to guess. The rows the old ingestion threw away are simply absent, and
the next sweep writes them — this migration does not and cannot recover them.

**Recovery.** Dropping the column loses the distinction and nothing else: ``finished``
still says what it always said, and every read that predates Batch 110 gates on it. The
team-season endpoint is the only caller that needs ``state``, so a downgrade takes that
screen out and leaves tables, results and form exactly as they were.

Revision ID: 022
Revises: 021
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("state", sa.String(length=16), nullable=False, server_default="scheduled"),
    )
    # The old column's whole vocabulary, in the new one's words.
    op.execute("UPDATE matches SET state = 'finished' WHERE finished")
    op.create_index(
        "ix_matches_competition_season_state",
        "matches",
        ["competition_id", "season", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_matches_competition_season_state", table_name="matches")
    op.drop_column("matches", "state")
