"""Football data: teams, aliases, matches, standings

Batch 16. The product stored no football, only betting. ``fixtures.home`` / ``away``
are free text from the odds provider, scores were consumed by settlement and thrown
away, and there was no ``Team`` table at all — so a league table, a previous result,
or a run of form could not be shown even for matches the game had itself settled.

Four tables, all additive. Nothing existing is altered, so the downgrade is a clean
drop and no other batch's data is at risk:

* ``teams`` — one club, keyed on the football provider's id, never on its name.
  ``normalised_name`` is stored so reconciliation is an indexed lookup.
* ``team_aliases`` — the name-reconciliation layer, ``(competition_id, normalised)``
  → team. Keyed by competition because club names are only unique within a division:
  Bangor plays in both Wales and Northern Ireland. Every spelling either provider
  uses lands here, which makes a wrong link one visible, correctable row.
* ``matches`` — a played match with its score. Separate from ``fixtures``, not an
  extension of it: a fixture is something a league can pick on, a match is something
  that happened, and most matches are neither. The slate has only ever fetched
  kick-offs inside a league's window, so Sunday, Monday and midweek games have never
  existed in this database.
* ``standings`` — a competition's table as published, not computed from ``matches``.
  Points deductions and each competition's own ordering rules are not reproducible
  from scores, and a table that quietly disagrees with the official one is worse than
  no table.

``competition_id`` throughout is the **odds** provider's slug, matching
``fixtures.competition_id``, so a fixture, a match and a table row all name a
competition the same way. It is not a foreign key: competitions are not a table here,
and a club changes division on promotion.

All four are new tables, so each carries the Supabase lockdown block that 003/004
established and 009 last needed — RLS forced and the Data API roles denied.

Revision ID: 011
Revises: 010
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("teams", "team_aliases", "matches", "standings")

_UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"))
_NOW = dict(nullable=False, server_default=sa.text("NOW()"))


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), **_UUID_PK),
        sa.Column("provider_team_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("short_name", sa.String(60), nullable=False, server_default=""),
        sa.Column("normalised_name", sa.String(120), nullable=False),
        sa.Column("competition_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("country", sa.String(60), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), **_NOW),
        sa.Column("updated_at", sa.DateTime(), **_NOW),
        sa.UniqueConstraint("provider_team_id", name="uq_teams_provider_team"),
    )
    op.create_index(
        "ix_teams_competition_normalised", "teams", ["competition_id", "normalised_name"]
    )

    op.create_table(
        "team_aliases",
        sa.Column("competition_id", sa.String(120), primary_key=True),
        sa.Column("normalised", sa.String(120), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(120), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="provider"),
    )

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), **_UUID_PK),
        sa.Column("provider_match_id", sa.String(64), nullable=False),
        sa.Column("competition_id", sa.String(120), nullable=False),
        sa.Column("competition", sa.String(120), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "home_team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "away_team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("home_goals", sa.SmallInteger(), nullable=True),
        sa.Column("away_goals", sa.SmallInteger(), nullable=True),
        sa.Column("finished", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(24), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), **_NOW),
        sa.Column("updated_at", sa.DateTime(), **_NOW),
        sa.UniqueConstraint("provider_match_id", name="uq_matches_provider_match"),
    )
    op.create_index(
        "ix_matches_competition_season_kickoff",
        "matches",
        ["competition_id", "season", "kickoff_utc"],
    )
    # Form is "this club's last five, home or away", so both sides are indexed with
    # the kick-off that orders them.
    op.create_index("ix_matches_home_team_kickoff", "matches", ["home_team_id", "kickoff_utc"])
    op.create_index("ix_matches_away_team_kickoff", "matches", ["away_team_id", "kickoff_utc"])

    op.create_table(
        "standings",
        sa.Column("id", postgresql.UUID(as_uuid=True), **_UUID_PK),
        sa.Column("competition_id", sa.String(120), nullable=False),
        sa.Column("competition", sa.String(120), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("played", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("won", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("drawn", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("lost", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("goals_for", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("goals_against", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("points", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("form", sa.String(10), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), **_NOW),
        sa.Column("updated_at", sa.DateTime(), **_NOW),
        sa.UniqueConstraint(
            "competition_id", "season", "team_id", name="uq_standings_competition_season_team"
        ),
    )
    op.create_index(
        "ix_standings_competition_season_position",
        "standings",
        ["competition_id", "season", "position"],
    )

    # ── Supabase lockdown for the new tables (mirrors 003/004/009) ───────────
    for table in _TABLES:
        op.execute(f"""
            DO $$ BEGIN
                IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                    ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
                    REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM anon, authenticated;
                    DROP POLICY IF EXISTS deny_anon_authenticated ON public.{table};
                    CREATE POLICY deny_anon_authenticated ON public.{table}
                        AS RESTRICTIVE FOR ALL TO anon, authenticated
                        USING (false) WITH CHECK (false);
                END IF;
            END $$;
        """)


def downgrade() -> None:
    # Dropped children-first so the foreign keys onto `teams` go with them. Everything
    # here is re-fetchable from the provider, so nothing irreplaceable is lost.
    op.drop_table("standings")
    op.drop_table("matches")
    op.drop_table("team_aliases")
    op.drop_table("teams")
