"""regenerate knockout placeholder labels from their source refs.

Each R16→final knockout row stores a human-readable display label
(``home_team_placeholder`` / ``away_team_placeholder``) alongside the positional
``home_source`` / ``away_source`` refs that drive bracket resolution. On
databases seeded before the bracket sources were corrected to the real FIFA 2026
wiring (``KNOCKOUT_BRACKET`` in ``src.services.knockout_progression``), the
labels were left following a naive consecutive pairing — so an unresolved
R16/QF/SF slot could display e.g. "Winner of Match 73" while its source ref is
actually ``winner_match_74``.

This backfill recomputes the label from the source ref for every match-fed
knockout slot, restoring the invariant ``placeholder == placeholder_label(source)``
(see ``src.services.knockout_progression.placeholder_label``, which the seed
already uses — so fresh databases are unaffected; this only repairs rows seeded
earlier). It is purely a display fix: no team ids, scoring, or bracket wiring
change.

Group-fed R32 rows (``winner_group_*`` / ``runner_up_group_*`` / ``third_group_*``)
are intentionally out of scope — those slots have already resolved to real teams,
so their labels are never displayed. Idempotent: each source ref maps to the same
label on every run.

Revision ID: 036
Revises: 035
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


# Mirrors placeholder_label()'s match-ref grammar:
#   winner_match_<n> -> "Winner of Match <n>"
#   loser_match_<n>  -> "Loser of Match <n>"
# Kept as two single-statement executes: the async (asyncpg) driver used for
# migrations rejects multiple ;-separated commands in one prepared statement.
_UPGRADE_HOME = """
    UPDATE matches
    SET home_team_placeholder = CASE
            WHEN home_source LIKE 'winner_match_%'
                THEN replace(home_source, 'winner_match_', 'Winner of Match ')
            WHEN home_source LIKE 'loser_match_%'
                THEN replace(home_source, 'loser_match_', 'Loser of Match ')
        END
    WHERE home_source LIKE 'winner_match_%' OR home_source LIKE 'loser_match_%'
"""

_UPGRADE_AWAY = """
    UPDATE matches
    SET away_team_placeholder = CASE
            WHEN away_source LIKE 'winner_match_%'
                THEN replace(away_source, 'winner_match_', 'Winner of Match ')
            WHEN away_source LIKE 'loser_match_%'
                THEN replace(away_source, 'loser_match_', 'Loser of Match ')
        END
    WHERE away_source LIKE 'winner_match_%' OR away_source LIKE 'loser_match_%'
"""


def upgrade() -> None:
    op.execute(_UPGRADE_HOME)
    op.execute(_UPGRADE_AWAY)


def downgrade() -> None:
    # Pure display backfill derived from the source refs. The prior (naive)
    # labels carried no information the source ref doesn't already encode and
    # cannot be reconstructed, so there is nothing to restore.
    pass
