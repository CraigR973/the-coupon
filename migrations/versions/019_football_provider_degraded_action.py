"""Somewhere to record that the football data source has bitten

Batch 101, from FEAT-A07. FotMob's terms prohibit automated access. The owner took that
knowingly and it stays revisitable — what was missing was the signal to revisit *on*.
Three shipped features rest on it (Football Stats, the void-fixture cross-check before
lock, live in-play scores) and TheSportsDB is named as the fallback with nothing tracking
when to reach for it.

``action_type`` gains ``'football_provider_degraded'``, the durable half of that signal.
It is the same shape ``'backup_failed'`` has had since 001: a system-actor row saying a
thing that should work did not, at a time somebody can look up afterwards. The push that
goes with it is ephemeral — the row is what is still there on Monday.

It is also what the alert **cooldown** reads. A ten-minute job noticing the same outage
must not push every ten minutes, and the "when did we last say this" that stops it has to
survive a redeploy or the first deploy of the day starts the noise again. Batch 99 made
that argument for the login limiter; it applies here for the same reason and with the same
answer.

``ALTER TYPE … ADD VALUE`` inside a transaction is permitted from PostgreSQL 12 provided
the value is not *used* in the same one — this migration only defines it, exactly as 012
defined ``'scheduled'``, and no row is written until the application writes one.

No Supabase lockdown block: ``audit_log`` already has RLS forced by 003/004 and an enum
is not a table.

**Recovery.** The downgrade rebuilds the type without the value, mapping any row that
holds it to ``'backup_failed'`` — PostgreSQL has no ``DROP VALUE``, so a rebuild is the
only way, and the two are the same kind of thing: a system-recorded failure. Losing the
distinction costs the ability to tell which subsystem complained, on rows that exist only
if the alert has already fired.

Revision ID: 019
Revises: 018
Create Date: 2026-08-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUE = "football_provider_degraded"


def upgrade() -> None:
    op.execute(f"ALTER TYPE action_type ADD VALUE IF NOT EXISTS '{_NEW_VALUE}'")


def downgrade() -> None:
    op.execute("ALTER TYPE action_type RENAME TO action_type_old")
    op.execute("""
        CREATE TYPE action_type AS ENUM (
            'backup_failed', 'backup_downloaded', 'player_pin_reset',
            'league_created', 'league_updated', 'league_deleted',
            'league_privacy_changed', 'league_join_code_rotated',
            'league_invite_created', 'league_invite_revoked',
            'league_member_pin_reset',
            'member_joined', 'member_left', 'member_removed',
            'member_promoted', 'member_demoted',
            'join_request_created', 'join_request_approved', 'join_request_rejected'
        )
    """)
    op.execute(f"""
        ALTER TABLE audit_log
            ALTER COLUMN action_type TYPE action_type
            USING (
                CASE action_type::text
                    WHEN '{_NEW_VALUE}' THEN 'backup_failed'
                    ELSE action_type::text
                END
            )::action_type
    """)
    op.execute("DROP TYPE action_type_old")
