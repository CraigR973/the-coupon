"""Somewhere to record that a member was told their sign-in name changed

Batch 93, from FEAT-A08. Batch 74 rewrote three ``profiles.display_name`` values on
2026-08-26. That column is the login identifier, so those three people sign in differently
now — and none of them was told, because nobody was signed out: the JWT subject is the
player id, so their sessions kept working and the surprise waits for the next session
expiry or forgotten-PIN request.

``action_type`` gains ``'display_name_changed'``. Unlike every other value here it is not
primarily an audit trail — it is an **idempotency marker**. ``services/rename_notice.py``
runs on every boot and writes one row per member it actually reaches; the row is what stops
the next boot telling them again. Batch 101 made the same argument for its alert cooldown:
the "have we already said this" has to survive a redeploy, and an in-process flag does not.

It is an audit row as well, and a truthful one — a system actor recording that the product
told a member something about their own account, at a time somebody can look up afterwards.

``ALTER TYPE … ADD VALUE`` inside a transaction is permitted from PostgreSQL 12 provided
the value is not *used* in the same one — this migration only defines it, exactly as 019
defined ``'football_provider_degraded'``, and no row is written until the application
writes one on the first boot after this deploys.

No Supabase lockdown block: ``audit_log`` already has RLS forced by 003/004 and an enum is
not a table.

**Recovery.** The downgrade rebuilds the type without the value, mapping any row that holds
it to ``'player_pin_reset'`` — PostgreSQL has no ``DROP VALUE``, so a rebuild is the only
way, and that is the nearest neighbour: both are the system recording something it did to
one member's credentials. The cost of losing the distinction is specific and small, but it
is not nothing: the marker rows are what stop the notice being re-sent, so a downgrade that
rewrites them lets the next boot tell those three people a second time.

Revision ID: 020
Revises: 019
Create Date: 2026-08-30

"""

from collections.abc import Sequence

from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUE = "display_name_changed"


def upgrade() -> None:
    op.execute(f"ALTER TYPE action_type ADD VALUE IF NOT EXISTS '{_NEW_VALUE}'")


def downgrade() -> None:
    op.execute("ALTER TYPE action_type RENAME TO action_type_old")
    op.execute("""
        CREATE TYPE action_type AS ENUM (
            'backup_failed', 'backup_downloaded', 'football_provider_degraded',
            'player_pin_reset',
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
                    WHEN '{_NEW_VALUE}' THEN 'player_pin_reset'
                    ELSE action_type::text
                END
            )::action_type
    """)
    op.execute("DROP TYPE action_type_old")
