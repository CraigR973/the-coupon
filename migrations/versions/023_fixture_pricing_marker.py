"""A fixture remembers that the bookmaker does not price it

Batch 114. ``CachingOddsProvider`` already cached "no price" as an entry — but only in
process, and on the same thirty-minute clock a real price expires on. So every restart
re-asked about every unpriceable fixture, and between restarts it re-asked twice an hour.

Measured against production on 2026-09-05: an open round held 202 fixtures, 103 of them
the FA Cup qualifying round, and Bet365 priced **none** of the 103. They cost 11 of the
21 requests in every sweep and rendered as rows no member could ever pick. The free
plan's 100/hour was gone by 08:06 on a match morning and members were refused with
``ODDS_UNAVAILABLE`` on a round whose lock was five hours away.

Two columns, because the marker and the last look at it answer different questions:

* ``odds_unpriced_since_utc`` — when the deployment first observed the bookmaker pricing
  nothing on this fixture. ``NULL`` means priced, or never looked at; the card shows those
  and asks about them. Non-``NULL`` takes the fixture off the card and out of the sweep.
* ``odds_checked_at_utc`` — when it last looked, marked or not. This is what bounds the
  marker: a fixture stays out of the sweep only until ``ODDS_UNPRICED_RECHECK_SECONDS``
  have passed, so a market a bookmaker opens late is still found and the row comes back.

**No backfill.** Every existing row starts ``NULL`` — unmarked, shown, asked about — which
is exactly the behaviour that shipped before this batch. The marker is a thing the
deployment *learns*, and the first card load after this migration teaches it. A backfill
would have to guess, and guessing wrong hides a fixture members can legitimately pick.

**Recovery.** Dropping both columns restores the old behaviour completely: nothing else
reads them, no price, pick or point is derived from them, and the in-process negative TTL
keeps working on its own. A downgrade costs the request saving and hides nothing.

Revision ID: 023
Revises: 022
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixtures",
        sa.Column("odds_unpriced_since_utc", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "fixtures",
        sa.Column("odds_checked_at_utc", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fixtures", "odds_checked_at_utc")
    op.drop_column("fixtures", "odds_unpriced_since_utc")
