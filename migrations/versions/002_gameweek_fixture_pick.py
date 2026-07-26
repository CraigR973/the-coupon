"""gameweek + fixture + pick — the weekly accumulator mechanic

Adds the three tables the game runs on, on top of the ``001`` auth + leagues
baseline:

* ``gameweeks`` — one Saturday's slate (open → locked → settled), global.
* ``fixtures`` — that Saturday's matches, mapped from the Betfair slate.
* ``picks``    — one member's single, leaderboard-unique selection, with the odds
  snapshotted at pick time.

The two ``picks`` unique constraints implement the core rules: one pick per member
per gameweek, and no two members of a leaderboard holding the same selection.

Revision ID: 002
Revises: 001
Create Date: 2026-07-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgENUM
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ENUM types ---
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE gameweek_status AS ENUM ('open', 'locked', 'settled');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pick_market AS ENUM ('MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pick_outcome AS ENUM ('HOME', 'DRAW', 'AWAY', 'YES', 'NO');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pick_status AS ENUM ('pending', 'won', 'lost', 'void');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # --- gameweeks (one Saturday's slate; global) ---
    op.create_table(
        "gameweeks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("saturday_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            PgENUM(name="gameweek_status", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column("locks_at_utc", sa.DateTime(), nullable=False),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("saturday_date", name="uq_gameweeks_saturday_date"),
    )

    # --- fixtures (that Saturday's matches, from the Betfair slate) ---
    op.create_table(
        "fixtures",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "gameweek_id",
            UUID(as_uuid=True),
            sa.ForeignKey("gameweeks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("betfair_event_id", sa.String(32), nullable=False),
        sa.Column("home", sa.String(120), nullable=False),
        sa.Column("away", sa.String(120), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(), nullable=False),
        sa.Column("competition", sa.String(120), nullable=False),
        sa.Column("competition_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "gameweek_id", "betfair_event_id", name="uq_fixtures_gameweek_event"
        ),
    )
    op.create_index("ix_fixtures_gameweek_id", "fixtures", ["gameweek_id"])

    # --- picks (one leaderboard-unique selection per member per gameweek) ---
    op.create_table(
        "picks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "league_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gameweek_id",
            UUID(as_uuid=True),
            sa.ForeignKey("gameweeks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fixture_id",
            UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market", PgENUM(name="pick_market", create_type=False), nullable=False),
        sa.Column("outcome", PgENUM(name="pick_outcome", create_type=False), nullable=False),
        sa.Column("runner_name", sa.String(120), nullable=False),
        sa.Column("odds_at_pick", sa.Numeric(6, 2), nullable=False),
        sa.Column("betfair_market_id", sa.String(32), nullable=False),
        sa.Column("betfair_selection_id", sa.BigInteger(), nullable=False),
        sa.Column("points_awarded", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            PgENUM(name="pick_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        # One pick per member per gameweek.
        sa.UniqueConstraint(
            "league_id", "gameweek_id", "player_id", name="uq_picks_league_gameweek_player"
        ),
        # No two members of a leaderboard hold the same selection (fixture + market +
        # outcome — not the Betfair selection id, which repeats across BTTS markets).
        sa.UniqueConstraint(
            "league_id",
            "gameweek_id",
            "fixture_id",
            "market",
            "outcome",
            name="uq_picks_league_gameweek_selection",
        ),
    )
    op.create_index("ix_picks_league_gameweek", "picks", ["league_id", "gameweek_id"])
    op.create_index("ix_picks_player_id", "picks", ["player_id"])

    # --- updated_at triggers (set_updated_at() defined in 001) ---
    for table in ("gameweeks", "fixtures", "picks"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    op.drop_table("picks")
    op.drop_table("fixtures")
    op.drop_table("gameweeks")
    op.execute("DROP TYPE IF EXISTS pick_status")
    op.execute("DROP TYPE IF EXISTS pick_outcome")
    op.execute("DROP TYPE IF EXISTS pick_market")
    op.execute("DROP TYPE IF EXISTS gameweek_status")
