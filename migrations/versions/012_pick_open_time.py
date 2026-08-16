"""Configurable pick-open time: a league setting, a round instant, and a round state

Batch 27. A round had one configured instant — ``locks_at_utc`` — and became
claimable at whatever moment ``run_refresh_slate`` happened to write it (09:00 or
13:00, depending on the day). That start was neither announced nor the same each
week, so "picks are up" was something members discovered rather than something a
league could say. This adds the other end of the claim period.

Three changes, all additive, all defaulting to exactly today's behaviour:

* ``leagues.pick_open_offset_minutes`` (integer, **nullable**). How long before the
  league's window opens picks open — measured back from the same anchor as
  ``lock_offset_minutes``, so a bigger number is earlier and the two compare
  directly. ``NULL`` means the league announces no opening, which is what every
  existing league does, so nothing changes for any of them. A check keeps the
  period from closing before it opens; ``NULL`` is exempt because it is "no
  opening", not an offset of zero.

* ``gameweeks.picks_open_at_utc`` (timestamp, nullable). The derived instant,
  frozen onto the round when it is discovered and never re-derived — the same rule
  ``locks_at_utc`` already follows, so editing the setting cannot move a deadline
  members have already been told. ``NULL`` on every existing row, which reads as
  "claimable from discovery": the pre-batch rule, preserved without a backfill.

* ``gameweek_status`` gains ``'scheduled'``, before ``'open'``. ``open`` meant both
  "this round has been discovered" and "you may claim on it"; a round that exists
  but has not opened needs those separated. Added with ``ALTER TYPE … ADD VALUE``,
  which PostgreSQL 12+ permits inside a transaction provided the new value is not
  *used* in the same one — this migration only defines it, and no row is written
  as ``scheduled`` until the application does so.

No Supabase lockdown block: both columns live on tables that already have RLS
forced by 003/004, and a column inherits its table's policies. Only a brand-new
table needs the block (009, 011).

The downgrade is lossless for configuration but not for state, and cannot be
otherwise: PostgreSQL has no ``DROP VALUE``, so the enum is rebuilt without
``'scheduled'`` and any round sitting in that state is mapped to ``'open'`` on the
way past. That is the pre-batch reading of such a round anyway — it exists, so it
is claimable.

Revision ID: 012
Revises: 011
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lifecycle order, so the type reads scheduled → open → locked → settled and any
    # ``ORDER BY status`` follows the round rather than the alphabet.
    op.execute("ALTER TYPE gameweek_status ADD VALUE IF NOT EXISTS 'scheduled' BEFORE 'open'")

    op.add_column(
        "leagues",
        sa.Column("pick_open_offset_minutes", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_leagues_pick_open_before_lock",
        "leagues",
        "pick_open_offset_minutes IS NULL OR pick_open_offset_minutes >= lock_offset_minutes",
    )

    op.add_column(
        "gameweeks",
        sa.Column("picks_open_at_utc", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gameweeks", "picks_open_at_utc")
    op.drop_constraint("ck_leagues_pick_open_before_lock", "leagues", type_="check")
    op.drop_column("leagues", "pick_open_offset_minutes")

    # No ``DROP VALUE`` exists, so the type is rebuilt. Rounds still ``scheduled``
    # become ``open`` — the reading this batch replaced, and the only one the older
    # code understands.
    op.execute("ALTER TYPE gameweek_status RENAME TO gameweek_status_old")
    op.execute("CREATE TYPE gameweek_status AS ENUM ('open', 'locked', 'settled')")
    op.execute("ALTER TABLE gameweeks ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE gameweeks ALTER COLUMN status TYPE gameweek_status "
        "USING (CASE WHEN status::text = 'scheduled' THEN 'open' ELSE status::text END)"
        "::gameweek_status"
    )
    op.execute("ALTER TABLE gameweeks ALTER COLUMN status SET DEFAULT 'open'")
    op.execute("DROP TYPE gameweek_status_old")
