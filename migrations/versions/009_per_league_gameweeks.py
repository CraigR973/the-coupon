"""Split gameweeks per league and pool the fixtures

Batch 14. ``gameweeks`` was global and unique on ``saturday_date``, and ``fixtures``
were owned by a gameweek, so every league necessarily played the same card. This
supersedes the product contract's "One global gameweek contains that Saturday's
15:00 fixtures."

Three moves, in an order chosen so no step ever sees a state it cannot describe:

1. **Pool the fixtures.** ``fixtures.gameweek_id`` goes away and a fixture becomes
   one row per real match, unique on ``provider_event_id``. Duplicates across
   gameweeks are collapsed onto the oldest row and any picks pointing at a
   discarded copy are re-pointed first, so no pick is orphaned.

2. **Record which fixtures a round plays** in ``gameweek_fixtures``, backfilled from
   ``fixtures.gameweek_id`` *before* that column is dropped. This is what lets one
   match appear on several leagues' cards without being stored — or fetched — twice.

3. **Give each league its own rounds.** ``gameweeks`` gains ``league_id``,
   ``saturday_date`` becomes ``starts_on``, and uniqueness moves from the Saturday
   to ``(league, starts_on)``. Every existing global gameweek is cloned once per
   active league and each league's picks are re-pointed at its own clone, so no
   league loses its history and the season list stays populated.

Plus the per-league window on ``leagues``, whose defaults reproduce today's rule
exactly — Saturday 15:00, locking 14:30 — expressed as a degenerate range so
Batch 15 can widen it without another migration.

Production holds no gameweeks, fixtures or picks (the slate job has never succeeded
there), so steps 1-3 backfill nothing in production. Staging has data and exercises
all of it.

Reversible: ``gameweek_fixtures`` preserves exactly the ownership that
``fixtures.gameweek_id`` held, so the downgrade can put it back. The one thing a
downgrade cannot restore is which of several deduplicated fixture rows a pick
originally pointed at — that information is not meaningful anyway, since the rows
described the same match.

Revision ID: 009
Revises: 008
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors src.models.league: Saturday, 15:00, locking 30 minutes before.
_SATURDAY = 5
_THREE_PM = 15 * 60
_LOCK_OFFSET = 30


def upgrade() -> None:
    # ── The per-league window ────────────────────────────────────────────────
    op.add_column(
        "leagues",
        sa.Column(
            "slate_start_weekday", sa.SmallInteger(), nullable=False, server_default=str(_SATURDAY)
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "slate_start_minute", sa.SmallInteger(), nullable=False, server_default=str(_THREE_PM)
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "slate_end_weekday", sa.SmallInteger(), nullable=False, server_default=str(_SATURDAY)
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "slate_end_minute", sa.SmallInteger(), nullable=False, server_default=str(_THREE_PM)
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "lock_offset_minutes", sa.Integer(), nullable=False, server_default=str(_LOCK_OFFSET)
        ),
    )
    op.create_check_constraint(
        "ck_leagues_slate_weekdays",
        "leagues",
        "slate_start_weekday BETWEEN 0 AND 6 AND slate_end_weekday BETWEEN 0 AND 6",
    )
    op.create_check_constraint(
        "ck_leagues_slate_minutes",
        "leagues",
        "slate_start_minute BETWEEN 0 AND 1439 AND slate_end_minute BETWEEN 0 AND 1439",
    )
    op.create_check_constraint(
        "ck_leagues_lock_offset_non_negative", "leagues", "lock_offset_minutes >= 0"
    )

    # ── 2. The join table, filled from the ownership we are about to drop ─────
    op.create_table(
        "gameweek_fixtures",
        sa.Column(
            "gameweek_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gameweeks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "fixture_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.execute("""
        INSERT INTO gameweek_fixtures (gameweek_id, fixture_id)
        SELECT gameweek_id, id FROM fixtures
        ON CONFLICT DO NOTHING
    """)

    # ── 1. Pool the fixtures ─────────────────────────────────────────────────
    # Collapse duplicates onto the oldest row per provider_event_id. Picks are
    # re-pointed *before* the losers are deleted, so the FK never dangles; the
    # join table is re-pointed too, which is how a pooled fixture ends up on
    # several rounds.
    op.execute("""
        CREATE TEMP TABLE fixture_survivors AS
        SELECT DISTINCT ON (provider_event_id)
               provider_event_id, id AS keep_id
        FROM fixtures
        ORDER BY provider_event_id, created_at, id
    """)
    op.execute("""
        UPDATE picks p
        SET fixture_id = s.keep_id
        FROM fixtures f
        JOIN fixture_survivors s ON s.provider_event_id = f.provider_event_id
        WHERE p.fixture_id = f.id AND f.id <> s.keep_id
    """)
    op.execute("""
        UPDATE gameweek_fixtures gf
        SET fixture_id = s.keep_id
        FROM fixtures f
        JOIN fixture_survivors s ON s.provider_event_id = f.provider_event_id
        WHERE gf.fixture_id = f.id AND f.id <> s.keep_id
          AND NOT EXISTS (
              SELECT 1 FROM gameweek_fixtures existing
              WHERE existing.gameweek_id = gf.gameweek_id
                AND existing.fixture_id = s.keep_id
          )
    """)
    op.execute("""
        DELETE FROM gameweek_fixtures gf
        USING fixtures f
        JOIN fixture_survivors s ON s.provider_event_id = f.provider_event_id
        WHERE gf.fixture_id = f.id AND f.id <> s.keep_id
    """)
    op.execute("""
        DELETE FROM fixtures f
        USING fixture_survivors s
        WHERE f.provider_event_id = s.provider_event_id AND f.id <> s.keep_id
    """)
    op.execute("DROP TABLE fixture_survivors")

    op.drop_constraint("uq_fixtures_gameweek_event", "fixtures", type_="unique")
    op.drop_index("ix_fixtures_gameweek_id", table_name="fixtures")
    op.drop_column("fixtures", "gameweek_id")
    op.create_unique_constraint("uq_fixtures_provider_event", "fixtures", ["provider_event_id"])

    # ── 3. Give each league its own rounds ───────────────────────────────────
    op.alter_column("gameweeks", "saturday_date", new_column_name="starts_on")
    op.add_column(
        "gameweeks",
        sa.Column("league_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Drop the global key *before* cloning: the clones deliberately share a date
    # with the row they came from, which is exactly what this constraint forbade.
    op.drop_constraint("uq_gameweeks_saturday_date", "gameweeks", type_="unique")

    # Clone every existing global round once per active league, keeping the
    # original row for the first league so its id (and anything referencing it)
    # survives. Leagues are few, so the row multiplication is immaterial.
    op.execute("""
        CREATE TEMP TABLE league_order AS
        SELECT id AS league_id, row_number() OVER (ORDER BY created_at, id) AS rn
        FROM leagues
        WHERE deleted_at IS NULL
    """)
    op.execute("""
        UPDATE gameweeks g
        SET league_id = lo.league_id
        FROM league_order lo
        WHERE lo.rn = 1
    """)
    op.execute("""
        INSERT INTO gameweeks (
            id, league_id, starts_on, status, locks_at_utc, settled_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), lo.league_id, g.starts_on, g.status, g.locks_at_utc,
               g.settled_at, g.created_at, g.updated_at
        FROM gameweeks g
        CROSS JOIN league_order lo
        WHERE lo.rn > 1 AND g.league_id IS NOT NULL
    """)
    # Each clone plays the same fixtures the original did.
    op.execute("""
        INSERT INTO gameweek_fixtures (gameweek_id, fixture_id)
        SELECT clone.id, gf.fixture_id
        FROM gameweeks clone
        JOIN gameweeks original
          ON original.starts_on = clone.starts_on AND original.id <> clone.id
        JOIN gameweek_fixtures gf ON gf.gameweek_id = original.id
        WHERE NOT EXISTS (
            SELECT 1 FROM gameweek_fixtures existing
            WHERE existing.gameweek_id = clone.id AND existing.fixture_id = gf.fixture_id
        )
        ON CONFLICT DO NOTHING
    """)
    # Re-point every pick at its own league's round.
    op.execute("""
        UPDATE picks p
        SET gameweek_id = mine.id
        FROM gameweeks old, gameweeks mine
        WHERE p.gameweek_id = old.id
          AND mine.starts_on = old.starts_on
          AND mine.league_id = p.league_id
          AND mine.id <> old.id
    """)
    # A round belonging to no active league (every league soft-deleted) has
    # nothing left to describe; its picks went with the league.
    op.execute("DELETE FROM gameweeks WHERE league_id IS NULL")
    op.execute("DROP TABLE league_order")

    op.alter_column("gameweeks", "league_id", nullable=False)
    op.create_foreign_key(
        "fk_gameweeks_league_id",
        "gameweeks",
        "leagues",
        ["league_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_gameweeks_league_starts_on", "gameweeks", ["league_id", "starts_on"]
    )

    # ── Supabase lockdown for the new table (mirrors 003/004) ────────────────
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.gameweek_fixtures ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.gameweek_fixtures FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.gameweek_fixtures FROM anon, authenticated;
                DROP POLICY IF EXISTS deny_anon_authenticated ON public.gameweek_fixtures;
                CREATE POLICY deny_anon_authenticated ON public.gameweek_fixtures
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Collapse back to one global round per date, keeping the oldest league's.
    op.drop_constraint("uq_gameweeks_league_starts_on", "gameweeks", type_="unique")
    op.drop_constraint("fk_gameweeks_league_id", "gameweeks", type_="foreignkey")
    op.execute("""
        CREATE TEMP TABLE gameweek_survivors AS
        SELECT DISTINCT ON (starts_on) starts_on, id AS keep_id
        FROM gameweeks
        ORDER BY starts_on, created_at, id
    """)
    op.execute("""
        UPDATE picks p
        SET gameweek_id = s.keep_id
        FROM gameweeks g
        JOIN gameweek_survivors s ON s.starts_on = g.starts_on
        WHERE p.gameweek_id = g.id AND g.id <> s.keep_id
    """)
    op.execute("""
        DELETE FROM gameweeks g
        USING gameweek_survivors s
        WHERE g.starts_on = s.starts_on AND g.id <> s.keep_id
    """)
    op.execute("DROP TABLE gameweek_survivors")
    op.drop_column("gameweeks", "league_id")
    op.alter_column("gameweeks", "starts_on", new_column_name="saturday_date")
    op.create_unique_constraint("uq_gameweeks_saturday_date", "gameweeks", ["saturday_date"])

    # Re-own each fixture by the round that plays it. A fixture on several rounds
    # can only belong to one again, so the oldest round wins and the others lose
    # that fixture — the information the pool made expressible does not fit here.
    op.drop_constraint("uq_fixtures_provider_event", "fixtures", type_="unique")
    op.add_column(
        "fixtures",
        sa.Column("gameweek_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("""
        UPDATE fixtures f
        SET gameweek_id = pick_one.gameweek_id
        FROM (
            SELECT DISTINCT ON (fixture_id) fixture_id, gameweek_id
            FROM gameweek_fixtures
            ORDER BY fixture_id, gameweek_id
        ) pick_one
        WHERE pick_one.fixture_id = f.id
    """)
    op.execute("DELETE FROM fixtures WHERE gameweek_id IS NULL")
    op.alter_column("fixtures", "gameweek_id", nullable=False)
    op.create_foreign_key(
        "fixtures_gameweek_id_fkey",
        "fixtures",
        "gameweeks",
        ["gameweek_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_fixtures_gameweek_id", "fixtures", ["gameweek_id"])
    op.create_unique_constraint(
        "uq_fixtures_gameweek_event", "fixtures", ["gameweek_id", "provider_event_id"]
    )

    op.drop_table("gameweek_fixtures")

    op.drop_constraint("ck_leagues_lock_offset_non_negative", "leagues", type_="check")
    op.drop_constraint("ck_leagues_slate_minutes", "leagues", type_="check")
    op.drop_constraint("ck_leagues_slate_weekdays", "leagues", type_="check")
    for column in (
        "lock_offset_minutes",
        "slate_end_minute",
        "slate_end_weekday",
        "slate_start_minute",
        "slate_start_weekday",
    ):
        op.drop_column("leagues", column)
