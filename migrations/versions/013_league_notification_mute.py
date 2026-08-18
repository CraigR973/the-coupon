"""Per-league notification mute

Batch 32. A member's only control over reminders was all-or-nothing
(``notification_preferences.global_mute``), and the volume it governs grows with
every league they join. ``send_pick_reminders`` nudges once per league by design,
so a member in five leagues takes five pushes every Saturday morning and the one
switch that reduces that also silences the league they care about.

Adds ``league_memberships.notification_muted`` (boolean, not null, default
``false``) rather than a new table: that row is already exactly the
``(player, league)`` tuple, already carries per-membership state in ``role`` and
``display_name_override``, and dies with the membership, so a member who leaves
and rejoins does not inherit a stale mute.

Revision ID: 013
Revises: 012
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "league_memberships",
        sa.Column(
            "notification_muted", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("league_memberships", "notification_muted")
