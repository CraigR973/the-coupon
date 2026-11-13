"""Isolated inactive group/fantasy storage, provenance and durable work.

Revision ID: 032
Revises: 031
Create Date: 2026-11-13

DDL below is frozen in this revision; it does not import evolving ORM models.
Recovery is forward-only so accepted picks, ledger provenance and spent quota
cannot disappear through an image rollback.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "032"
down_revision: str | None = "031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "two_game_rollouts",
    "two_games",
    "two_game_fixtures",
    "group_picks",
    "fantasy_picks",
    "membership_intervals",
    "weekly_fee_obligations",
    "provider_attempts",
    "provider_controls",
    "provider_snapshots",
    "provider_work",
    "provider_refusals",
    "two_game_operations",
    "two_game_events",
    "two_game_breaks",
)

DDL = (
    """
CREATE TABLE provider_attempts (
meter VARCHAR(80) NOT NULL,
category VARCHAR(24) NOT NULL,
reserved_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id)
)
    """,
    """
CREATE INDEX ix_provider_attempts_meter_time ON provider_attempts (meter, reserved_at)
    """,
    """
CREATE TABLE provider_controls (
meter VARCHAR(80) NOT NULL,
cooldown_until TIMESTAMP WITHOUT TIME ZONE,
header_remaining INTEGER,
header_reset_at TIMESTAMP WITHOUT TIME ZONE,
last_clock_at TIMESTAMP WITHOUT TIME ZONE,
PRIMARY KEY (meter)
)
    """,
    """
CREATE TABLE provider_refusals (
meter VARCHAR(80) NOT NULL,
category VARCHAR(24) NOT NULL,
refused_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
retry_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
reason VARCHAR(40) NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id)
)
    """,
    """
CREATE INDEX ix_provider_refusals_meter_time ON provider_refusals (meter, refused_at)
    """,
    """
CREATE TABLE provider_snapshots (
key VARCHAR(240) NOT NULL,
fixture_id UUID,
payload JSONB NOT NULL,
observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
negative_recheck_at TIMESTAMP WITHOUT TIME ZONE,
lease_until TIMESTAMP WITHOUT TIME ZONE,
lease_token UUID,
PRIMARY KEY (key),
FOREIGN KEY(fixture_id) REFERENCES fixtures (id)
)
    """,
    """
CREATE INDEX ix_provider_snapshots_fixture ON provider_snapshots (fixture_id)
    """,
    """
CREATE TABLE provider_work (
key VARCHAR(240) NOT NULL,
kind VARCHAR(24) NOT NULL,
fixture_id UUID,
payload JSONB NOT NULL,
cursor VARCHAR(240),
next_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
lease_until TIMESTAMP WITHOUT TIME ZONE,
lease_token UUID,
completed_at TIMESTAMP WITHOUT TIME ZONE,
attempts INTEGER DEFAULT '0' NOT NULL,
last_error VARCHAR(200),
PRIMARY KEY (key),
FOREIGN KEY(fixture_id) REFERENCES fixtures (id)
)
    """,
    """
CREATE INDEX ix_provider_work_due ON provider_work (kind, next_at, key)
    """,
    """
CREATE INDEX ix_provider_work_fixture ON provider_work (fixture_id)
    """,
    """
CREATE TABLE two_game_breaks (
league_id UUID NOT NULL,
week_label DATE NOT NULL,
evidence TEXT NOT NULL,
confirmed_by UUID NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id),
CONSTRAINT uq_two_game_break_week UNIQUE (league_id, week_label),
CONSTRAINT ck_two_game_break_evidence CHECK (length(evidence) > 0),
FOREIGN KEY(league_id) REFERENCES leagues (id),
FOREIGN KEY(confirmed_by) REFERENCES profiles (id)
)
    """,
    """
CREATE INDEX ix_two_game_breaks_confirmed_by ON two_game_breaks (confirmed_by)
    """,
    """
CREATE TABLE two_game_rollouts (
league_id UUID NOT NULL,
first_week DATE NOT NULL,
effective_opening TIMESTAMP WITHOUT TIME ZONE NOT NULL,
enabled BOOLEAN DEFAULT 'false' NOT NULL,
suspended BOOLEAN DEFAULT 'false' NOT NULL,
PRIMARY KEY (league_id),
CONSTRAINT ck_rollout_saturday CHECK (extract(isodow from first_week) = 6),
FOREIGN KEY(league_id) REFERENCES leagues (id)
)
    """,
    """
CREATE TABLE membership_intervals (
league_id UUID NOT NULL,
player_id UUID NOT NULL,
joined_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
left_at TIMESTAMP WITHOUT TIME ZONE,
provenance VARCHAR(40) NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(league_id, player_id) REFERENCES league_memberships (league_id, player_id),
CONSTRAINT uq_membership_interval_owner UNIQUE (id, league_id, player_id),
CONSTRAINT ck_membership_interval CHECK (left_at IS NULL OR left_at >= joined_at)
)
    """,
    """
CREATE INDEX ix_membership_intervals_member ON membership_intervals (league_id, player_id)
    """,
    """
CREATE UNIQUE INDEX uq_membership_intervals_active ON membership_intervals (league_id,
player_id) WHERE left_at IS NULL
    """,
    """
CREATE TABLE two_games (
league_id UUID NOT NULL,
week_id UUID NOT NULL,
kind VARCHAR(8) NOT NULL,
opens_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
locks_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
window_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
window_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
status VARCHAR(12) DEFAULT 'scheduled' NOT NULL,
coverage_state VARCHAR(20) DEFAULT 'pending' NOT NULL,
result_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
result_version INTEGER DEFAULT '0' NOT NULL,
finalized_at TIMESTAMP WITHOUT TIME ZONE,
id UUID NOT NULL,
updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(week_id, league_id) REFERENCES gameweeks (id, league_id),
CONSTRAINT uq_two_games_week_kind UNIQUE (week_id, kind),
CONSTRAINT uq_two_games_owner UNIQUE (id, league_id, week_id, kind),
CONSTRAINT ck_two_games_kind CHECK (kind IN ('group', 'fantasy')),
CONSTRAINT ck_two_games_open_before_lock CHECK (opens_at <= locks_at),
CONSTRAINT ck_two_games_window CHECK (window_start <= window_end),
CONSTRAINT ck_two_games_status CHECK (status IN
('scheduled','open','locked','settled','cancelled')),
CONSTRAINT ck_two_games_coverage CHECK (coverage_state IN
('pending','unavailable','complete','confirmed_empty'))
)
    """,
    """
CREATE INDEX ix_two_games_league_lock ON two_games (league_id, locks_at)
    """,
    """
CREATE INDEX ix_two_games_week_league ON two_games (week_id, league_id)
    """,
    """
CREATE TABLE two_game_events (
game_id UUID NOT NULL,
league_id UUID NOT NULL,
week_id UUID NOT NULL,
game_kind VARCHAR(8) NOT NULL,
kind VARCHAR(40) NOT NULL,
version INTEGER NOT NULL,
payload JSONB NOT NULL,
delivered_at TIMESTAMP WITHOUT TIME ZONE,
id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(game_id, league_id, week_id, game_kind) REFERENCES two_games (id, league_id,
week_id, kind),
CONSTRAINT uq_two_game_events_version UNIQUE (game_id, kind, version),
CONSTRAINT ck_two_game_group_event_unpriced CHECK (game_kind <> 'group' OR NOT (payload ?|
ARRAY['odds','points','combined_odds']))
)
    """,
    """
CREATE INDEX ix_two_game_events_league ON two_game_events (league_id)
    """,
    """
CREATE INDEX ix_two_game_events_owner ON two_game_events (game_id, league_id, week_id,
game_kind)
    """,
    """
CREATE TABLE two_game_fixtures (
game_id UUID NOT NULL,
fixture_id UUID NOT NULL,
PRIMARY KEY (game_id, fixture_id),
FOREIGN KEY(game_id) REFERENCES two_games (id),
FOREIGN KEY(fixture_id) REFERENCES fixtures (id)
)
    """,
    """
CREATE INDEX ix_two_game_fixtures_fixture ON two_game_fixtures (fixture_id)
    """,
    """
CREATE TABLE two_game_operations (
game_id UUID NOT NULL,
league_id UUID NOT NULL,
week_id UUID NOT NULL,
game_kind VARCHAR(8) NOT NULL,
player_id UUID NOT NULL,
slot INTEGER NOT NULL,
operation_id UUID NOT NULL,
body_hash VARCHAR(64) NOT NULL,
response JSONB NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(game_id, league_id, week_id, game_kind) REFERENCES two_games (id, league_id,
week_id, kind),
CONSTRAINT uq_two_game_operations_target UNIQUE (player_id, league_id, week_id, game_kind,
slot, operation_id),
CONSTRAINT ck_two_game_operations_slot CHECK ((game_kind = 'group' AND slot = 0) OR (game_kind
= 'fantasy' AND slot BETWEEN 1 AND 6)),
FOREIGN KEY(player_id) REFERENCES profiles (id)
)
    """,
    """
CREATE INDEX ix_two_game_operations_owner ON two_game_operations (game_id, league_id, week_id,
game_kind)
    """,
    """
CREATE INDEX ix_two_game_operations_player_id ON two_game_operations (player_id)
    """,
    """
CREATE TABLE weekly_fee_obligations (
league_id UUID NOT NULL,
player_id UUID NOT NULL,
week_id UUID NOT NULL,
week_label DATE NOT NULL,
interval_id UUID NOT NULL,
ledger_entry_id UUID NOT NULL,
amount_pence INTEGER DEFAULT '100' NOT NULL,
billing_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
billing_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
owed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
recorded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(week_id, league_id) REFERENCES gameweeks (id, league_id),
FOREIGN KEY(interval_id, league_id, player_id) REFERENCES membership_intervals (id, league_id,
player_id),
CONSTRAINT uq_weekly_fee_member_week UNIQUE (league_id, player_id, week_label),
CONSTRAINT uq_weekly_fee_parent_member UNIQUE (week_id, player_id),
CONSTRAINT ck_weekly_fee_amount CHECK (amount_pence = 100),
CONSTRAINT ck_weekly_fee_interval CHECK (billing_start < billing_end),
CONSTRAINT ck_weekly_fee_label CHECK (extract(isodow from week_label) = 6),
UNIQUE (ledger_entry_id),
FOREIGN KEY(ledger_entry_id) REFERENCES ledger_entries (id)
)
    """,
    """
CREATE INDEX ix_weekly_fee_interval ON weekly_fee_obligations (interval_id, league_id,
player_id)
    """,
    """
CREATE INDEX ix_weekly_fee_week_league ON weekly_fee_obligations (week_id, league_id)
    """,
    """
CREATE TABLE fantasy_picks (
game_kind VARCHAR(8) DEFAULT 'fantasy' NOT NULL,
slot INTEGER NOT NULL,
frozen_odds NUMERIC(10, 4) NOT NULL,
quoted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
provider VARCHAR(40) NOT NULL,
bookmaker VARCHAR(80) NOT NULL,
points_awarded INTEGER,
id UUID NOT NULL,
updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
league_id UUID NOT NULL,
week_id UUID NOT NULL,
game_id UUID NOT NULL,
fixture_id UUID NOT NULL,
player_id UUID NOT NULL,
market VARCHAR(24) NOT NULL,
outcome VARCHAR(8) NOT NULL,
runner_name VARCHAR(120) NOT NULL,
status VARCHAR(8) DEFAULT 'pending' NOT NULL,
revision INTEGER DEFAULT '1' NOT NULL,
operation_id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(game_id, league_id, week_id, game_kind) REFERENCES two_games (id, league_id,
week_id, kind),
FOREIGN KEY(game_id, fixture_id) REFERENCES two_game_fixtures (game_id, fixture_id),
FOREIGN KEY(league_id, player_id) REFERENCES league_memberships (league_id, player_id),
CONSTRAINT ck_fantasy_pick_kind CHECK (game_kind = 'fantasy'),
CONSTRAINT ck_fantasy_pick_selection CHECK ((market = 'MATCH_ODDS' AND outcome IN
('HOME','DRAW','AWAY')) OR (market = 'BOTH_TEAMS_TO_SCORE' AND outcome IN ('YES','NO'))),
CONSTRAINT ck_fantasy_pick_status CHECK (status IN ('pending','won','lost','void')),
CONSTRAINT ck_fantasy_pick_revision CHECK (revision >= 1),
CONSTRAINT uq_fantasy_pick_slot UNIQUE (week_id, player_id, slot),
CONSTRAINT uq_fantasy_pick_fixture UNIQUE (week_id, player_id, fixture_id),
CONSTRAINT ck_fantasy_pick_slot CHECK (slot BETWEEN 1 AND 6),
CONSTRAINT ck_fantasy_pick_price CHECK (frozen_odds > 0),
CONSTRAINT ck_fantasy_points CHECK (points_awarded IS NULL OR points_awarded >= 0),
FOREIGN KEY(player_id) REFERENCES profiles (id)
)
    """,
    """
CREATE INDEX ix_fantasy_picks_fixture ON fantasy_picks (fixture_id)
    """,
    """
CREATE INDEX ix_fantasy_picks_game_fixture ON fantasy_picks (game_id, fixture_id)
    """,
    """
CREATE INDEX ix_fantasy_picks_member ON fantasy_picks (league_id, player_id)
    """,
    """
CREATE INDEX ix_fantasy_picks_owner ON fantasy_picks (game_id, league_id, week_id, game_kind)
    """,
    """
CREATE INDEX ix_fantasy_picks_player ON fantasy_picks (player_id)
    """,
    """
CREATE TABLE group_picks (
game_kind VARCHAR(8) DEFAULT 'group' NOT NULL,
id UUID NOT NULL,
updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
league_id UUID NOT NULL,
week_id UUID NOT NULL,
game_id UUID NOT NULL,
fixture_id UUID NOT NULL,
player_id UUID NOT NULL,
market VARCHAR(24) NOT NULL,
outcome VARCHAR(8) NOT NULL,
runner_name VARCHAR(120) NOT NULL,
status VARCHAR(8) DEFAULT 'pending' NOT NULL,
revision INTEGER DEFAULT '1' NOT NULL,
operation_id UUID NOT NULL,
PRIMARY KEY (id),
FOREIGN KEY(game_id, league_id, week_id, game_kind) REFERENCES two_games (id, league_id,
week_id, kind),
FOREIGN KEY(game_id, fixture_id) REFERENCES two_game_fixtures (game_id, fixture_id),
FOREIGN KEY(league_id, player_id) REFERENCES league_memberships (league_id, player_id),
CONSTRAINT ck_group_pick_kind CHECK (game_kind = 'group'),
CONSTRAINT ck_group_pick_selection CHECK ((market = 'MATCH_ODDS' AND outcome IN
('HOME','DRAW','AWAY')) OR (market = 'BOTH_TEAMS_TO_SCORE' AND outcome IN ('YES','NO'))),
CONSTRAINT ck_group_pick_status CHECK (status IN ('pending','won','lost','void')),
CONSTRAINT ck_group_pick_revision CHECK (revision >= 1),
CONSTRAINT uq_group_pick_member UNIQUE (week_id, player_id),
CONSTRAINT uq_group_pick_fixture UNIQUE (week_id, fixture_id),
FOREIGN KEY(player_id) REFERENCES profiles (id)
)
    """,
    """
CREATE INDEX ix_group_picks_fixture ON group_picks (fixture_id)
    """,
    """
CREATE INDEX ix_group_picks_game_fixture ON group_picks (game_id, fixture_id)
    """,
    """
CREATE INDEX ix_group_picks_member ON group_picks (league_id, player_id)
    """,
    """
CREATE INDEX ix_group_picks_owner ON group_picks (game_id, league_id, week_id, game_kind)
    """,
    """
CREATE INDEX ix_group_picks_player ON group_picks (player_id)
    """,
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gameweeks ADD COLUMN format varchar(12) NOT NULL DEFAULT 'legacy'"
    )
    op.execute(
        "ALTER TABLE gameweeks ADD CONSTRAINT ck_gameweeks_format CHECK (format IN ('legacy','two_game'))"
    )
    op.execute(
        "ALTER TABLE gameweeks ADD CONSTRAINT uq_gameweeks_id_league UNIQUE (id, league_id)"
    )
    for statement in DDL:
        op.execute(statement)
    _fences()
    for table in TABLE_NAMES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM PUBLIC")
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM {role};
                END IF;
            END $$;""")


def downgrade() -> None:
    raise RuntimeError(
        "032 requires forward recovery; dropping accepted work or spent quota is forbidden"
    )


def _fences() -> None:
    functions = {
        "two_game_guard_parent": """
            IF TG_OP = 'UPDATE' AND OLD.format IS DISTINCT FROM NEW.format THEN
                RAISE EXCEPTION 'week format is immutable' USING ERRCODE = '23514';
            END IF;
            IF NEW.format = 'two_game' THEN
                IF extract(isodow from NEW.starts_on) <> 6
                   OR NEW.status NOT IN ('locked','settled')
                   OR NEW.picks_open_at_utc IS NOT NULL
                   OR NEW.locks_at_utc IS DISTINCT FROM
                     (((NEW.starts_on::timestamp + interval '14 hours 30 minutes')
                        AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC') THEN
                    RAISE EXCEPTION 'invalid non-entry week parent' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND ROW(OLD.id, OLD.league_id, OLD.starts_on, OLD.locks_at_utc)
                    IS DISTINCT FROM ROW(NEW.id, NEW.league_id, NEW.starts_on, NEW.locks_at_utc) THEN
                    RAISE EXCEPTION 'new week identity is immutable' USING ERRCODE = '23514';
                END IF;
            ELSIF TG_OP = 'INSERT' AND EXISTS (
                SELECT 1 FROM public.two_game_rollouts r
                WHERE r.league_id = NEW.league_id AND r.enabled
                  AND NEW.starts_on >= r.first_week - 5
            ) THEN
                RAISE EXCEPTION 'legacy discovery past two-game cutover' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        """,
        "two_game_guard_legacy": """
            IF EXISTS (SELECT 1 FROM public.gameweeks w
                       WHERE w.id = NEW.gameweek_id AND w.format = 'two_game') THEN
                RAISE EXCEPTION 'unsupported week format' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        """,
        "two_game_guard_child": """
            DECLARE w public.gameweeks%ROWTYPE; expected_lock timestamp;
                    expected_start timestamp; expected_end timestamp; local_open timestamp;
            BEGIN
                SELECT * INTO w FROM public.gameweeks WHERE id = NEW.week_id;
                IF w.format IS DISTINCT FROM 'two_game' OR w.league_id <> NEW.league_id THEN
                    RAISE EXCEPTION 'child requires its own two-game parent'
                        USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND ROW(OLD.id,OLD.week_id,OLD.league_id,OLD.kind,
                    OLD.opens_at,OLD.locks_at,OLD.window_start,OLD.window_end)
                    IS DISTINCT FROM ROW(NEW.id,NEW.week_id,NEW.league_id,NEW.kind,
                    NEW.opens_at,NEW.locks_at,NEW.window_start,NEW.window_end) THEN
                    RAISE EXCEPTION 'announced game identity and schedule are immutable'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.kind = 'group' THEN
                    expected_start := ((w.starts_on::timestamp + interval '15 hours')
                        AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC';
                    expected_end := expected_start;
                    expected_lock := expected_start - interval '30 minutes';
                ELSE
                    expected_start := ((w.starts_on::timestamp + interval '12 hours 30 minutes')
                        AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC';
                    expected_end := (((w.starts_on + 2)::timestamp)
                        AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC';
                    expected_lock := expected_start - interval '30 minutes';
                    local_open := (NEW.opens_at AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London';
                    IF extract(isodow from local_open) <> 6 OR local_open::time <> time '12:00'
                       OR local_open::date >= w.starts_on THEN
                        RAISE EXCEPTION 'fantasy opens on preceding eligible Saturday noon'
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
                IF ROW(NEW.locks_at,NEW.window_start,NEW.window_end)
                   IS DISTINCT FROM ROW(expected_lock,expected_start,expected_end) THEN
                    RAISE EXCEPTION 'invalid game window or lock' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
        """,
        "two_game_guard_fixture": """
            DECLARE g public.two_games%ROWTYPE; kickoff timestamp;
            BEGIN
                SELECT * INTO g FROM public.two_games WHERE id = NEW.game_id;
                SELECT kickoff_utc INTO kickoff FROM public.fixtures WHERE id = NEW.fixture_id;
                IF kickoff IS NULL OR
                   (g.kind = 'group' AND kickoff <> g.window_start) OR
                   (g.kind = 'fantasy' AND (kickoff < g.window_start OR kickoff >= g.window_end)) THEN
                    RAISE EXCEPTION 'fixture outside addressed game window' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
        """,
        "two_game_guard_fee": """
            DECLARE w public.gameweeks%ROWTYPE; e public.ledger_entries%ROWTYPE;
                    member_interval public.membership_intervals%ROWTYPE;
                    expected_start timestamp; expected_end timestamp;
            BEGIN
                IF TG_OP <> 'INSERT' THEN
                    RAISE EXCEPTION 'owed fee provenance is immutable' USING ERRCODE = '23514';
                END IF;
                SELECT * INTO w FROM public.gameweeks WHERE id = NEW.week_id;
                SELECT * INTO e FROM public.ledger_entries WHERE id = NEW.ledger_entry_id FOR UPDATE;
                SELECT * INTO member_interval FROM public.membership_intervals
                    WHERE id = NEW.interval_id;
                expected_start := (((NEW.week_label - 5)::timestamp)
                    AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC';
                expected_end := (((NEW.week_label + 2)::timestamp)
                    AT TIME ZONE 'Europe/London') AT TIME ZONE 'UTC';
                IF member_interval.joined_at >= NEW.billing_end
                   OR (member_interval.left_at IS NOT NULL
                       AND member_interval.left_at <= NEW.billing_start)
                   OR NEW.owed_at < member_interval.joined_at
                   OR (member_interval.left_at IS NOT NULL AND NEW.owed_at >= member_interval.left_at)
                   OR w.format IS DISTINCT FROM 'two_game' OR NEW.week_label <> w.starts_on
                   OR ROW(NEW.billing_start,NEW.billing_end)
                        IS DISTINCT FROM ROW(expected_start,expected_end)
                   OR ROW(e.league_id,e.player_id,e.gameweek_id,e.kind::text,e.amount_pence)
                        IS DISTINCT FROM ROW(NEW.league_id,NEW.player_id,NEW.week_id,
                                              'round_due'::text,-100) THEN
                    RAISE EXCEPTION 'fee must name its own weekly ledger due'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
        """,
        "two_game_guard_interval": """
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'membership provenance is retained' USING ERRCODE = '23514';
            END IF;
            IF ROW(OLD.id,OLD.league_id,OLD.player_id,OLD.joined_at,OLD.provenance)
                IS DISTINCT FROM ROW(NEW.id,NEW.league_id,NEW.player_id,NEW.joined_at,NEW.provenance)
                OR (OLD.left_at IS NOT NULL AND OLD.left_at IS DISTINCT FROM NEW.left_at) THEN
                RAISE EXCEPTION 'membership history cannot be rewritten' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        """,
        "two_game_guard_ledger": """
            IF EXISTS (SELECT 1 FROM public.weekly_fee_obligations
                       WHERE ledger_entry_id = OLD.id) THEN
                RAISE EXCEPTION 'owed weekly ledger entries are immutable' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        """,
        "two_game_guard_attempt": """
            RAISE EXCEPTION 'spent provider reservations are immutable' USING ERRCODE = '23514';
        """,
    }
    for name, body in functions.items():
        # DECLARE blocks carry their own BEGIN/END; the other bodies do not.
        block = body if body.lstrip().startswith("DECLARE") else f"BEGIN {body} END;"
        op.execute(f"""CREATE FUNCTION public.{name}() RETURNS trigger
            LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public
            AS $function$ {block} $function$""")
        op.execute(f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC")
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON FUNCTION public.{name}() FROM {role};
                END IF;
            END $$;""")
    triggers = (
        ("gameweeks", "INSERT OR UPDATE", "two_game_guard_parent"),
        ("picks", "INSERT OR UPDATE", "two_game_guard_legacy"),
        ("gameweek_fixtures", "INSERT OR UPDATE", "two_game_guard_legacy"),
        ("two_games", "INSERT OR UPDATE", "two_game_guard_child"),
        ("two_game_fixtures", "INSERT OR UPDATE", "two_game_guard_fixture"),
        ("weekly_fee_obligations", "INSERT OR UPDATE OR DELETE", "two_game_guard_fee"),
        ("membership_intervals", "UPDATE OR DELETE", "two_game_guard_interval"),
        ("provider_attempts", "UPDATE OR DELETE", "two_game_guard_attempt"),
        ("ledger_entries", "UPDATE OR DELETE", "two_game_guard_ledger"),
    )
    for table, events, function in triggers:
        op.execute(
            f"CREATE TRIGGER {table}_two_game_fence BEFORE {events} ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{function}()"
        )
