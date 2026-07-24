"""scoring trigger: stamp snapshots with statement_timestamp(), not now().

Background — why post-result rank-move notifications were wrong
---------------------------------------------------------------
``matches_score_results`` writes one ``leaderboard_snapshots`` *generation*
(one row per player per active league, tagged ``triggered_by_match_id``) on
every scoring UPDATE, stamping ``snapshot_at`` with ``now()``. But ``now()``
is ``transaction_timestamp()`` — **constant for a whole transaction**. The
auto-sync (``result_sync.sync_results``) finishes *every* match of a cycle and
commits once, so when two or more matches finish together (the final group
matchday plays two games at once; same-slot kickoffs finish minutes apart)
*all* their generations share one identical ``snapshot_at``.

That breaks the only way callers tell generations apart by recency:

* ``notify_leaderboard_shifts`` looked up the "previous" standing with
  ``ORDER BY snapshot_at DESC LIMIT 1`` — with the timestamps tied it picked
  an arbitrary *same-cycle sibling* generation as the baseline, so players got
  "Up to #X (was #Y)" pushes with the wrong (or nondeterministic) "was".
* the leaderboard read path (``routers.leaderboard``) breaks the tie with a
  random-UUID ``id DESC``, so it can momentarily surface an intermediate
  generation rather than the final standing.

The fix
-------
Stamp ``snapshot_at`` with ``statement_timestamp()`` — the start time of the
*current statement*. It is STABLE within one statement, so every row of a
single generation (one ``INSERT … SELECT``) still shares one timestamp; but
each match is a separate ``UPDATE matches`` statement, so successive
generations in the same transaction get distinct, strictly increasing
timestamps. ``snapshot_at`` then orders generations correctly and the
existing ``DESC`` lookups become accurate. The companion query change lives in
``notify_leaderboard_shifts`` (compare against the immediately-earlier
generation, ``snapshot_at < new.snapshot_at``).

Only the ``now()`` → ``statement_timestamp()`` token in the snapshot INSERT
changes. The rest of the body is migration 026 verbatim. The function is
recreated with ``SET search_path = public`` baked in: ``CREATE OR REPLACE
FUNCTION`` reassigns *all* function properties, so omitting it would silently
drop the lock migration 028 added (Supabase security advisor WARN). The
trigger's ``OF``/``WHEN`` clause (migration 037) is untouched — replacing the
function does not drop the trigger.

The Python twin ``src.services.leaderboard.recompute_leaderboard_snapshot`` is
updated in the same change to keep the two snapshot bodies in sync.

Revision ID: 038
Revises: 037
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Per-player totals + U38 tiebreak counts. Identical text lives in migration
# 026 and src/services/leaderboard.py; keep them in sync.
_PLAYER_TOTALS = """
    SELECT
        pr.id AS player_id,
        COALESCE((
            SELECT SUM(points_awarded)::int FROM predictions
            WHERE player_id = pr.id AND deleted_at IS NULL
        ), 0) AS match_points,
        COALESCE((
            SELECT SUM(points_awarded)::int FROM knockout_predictions
            WHERE player_id = pr.id
        ), 0) AS knockout_winner_points,
        COALESCE((
            SELECT SUM(points_awarded)::int FROM special_predictions
            WHERE player_id = pr.id
        ), 0) AS special_points,
        COALESCE((
            SELECT SUM(points_awarded)::int FROM predictions
            WHERE player_id = pr.id AND deleted_at IS NULL
        ), 0)
        + COALESCE((
            SELECT SUM(points_awarded)::int FROM knockout_predictions
            WHERE player_id = pr.id
        ), 0)
        + COALESCE((
            SELECT SUM(points_awarded)::int FROM special_predictions
            WHERE player_id = pr.id
        ), 0) AS total_points,
        COALESCE((
            SELECT COUNT(*)::int FROM predictions
            WHERE player_id = pr.id AND deleted_at IS NULL
              AND (points_breakdown->>'exact')::int > 0
        ), 0) AS exact_count,
        COALESCE((
            SELECT COUNT(*)::int FROM predictions
            WHERE player_id = pr.id AND deleted_at IS NULL
              AND (points_breakdown->>'result')::int > 0
        ), 0) AS correct_result_count,
        COALESCE((
            SELECT COUNT(*)::int FROM predictions
            WHERE player_id = pr.id AND deleted_at IS NULL
              AND (points_breakdown->>'goals')::int > 0
        ), 0) AS correct_goals_count,
        COALESCE((
            SELECT COUNT(*)::int FROM special_predictions
            WHERE player_id = pr.id AND points_awarded > 0
        ), 0) AS specials_correct_count,
        COALESCE((
            SELECT COUNT(*)::int FROM knockout_predictions
            WHERE player_id = pr.id AND points_awarded > 0
        ), 0) AS ko_winner_correct_count
    FROM profiles pr
    WHERE pr.deleted_at IS NULL
"""


def _trigger_fn(snapshot_at_expr: str) -> str:
    """The matches_score_results() body with a swappable snapshot_at expression.

    ``SET search_path = public`` is baked in so CREATE OR REPLACE preserves the
    lock migration 028 added (it otherwise resets all function properties).
    """
    return f"""
        CREATE OR REPLACE FUNCTION matches_score_results()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = public
        AS $func$
        DECLARE
            v_winner_id  UUID;
            v_round_pts  INT;
        BEGIN
            -- 1. Score predictions (group + knockout matches).
            UPDATE predictions p
            SET points_breakdown = calculate_match_points(
                    p.predicted_home, p.predicted_away,
                    NEW.actual_home_score, NEW.actual_away_score,
                    NEW.stage
                ),
                points_awarded = (calculate_match_points(
                    p.predicted_home, p.predicted_away,
                    NEW.actual_home_score, NEW.actual_away_score,
                    NEW.stage
                )->>'total')::int
            WHERE p.match_id = NEW.id
              AND p.deleted_at IS NULL;

            -- 2. Knockout winner predictions: only for knockout-stage matches.
            IF NEW.stage <> 'group' THEN
                IF NEW.actual_home_score > NEW.actual_away_score THEN
                    v_winner_id := NEW.home_team_id;
                ELSIF NEW.actual_home_score < NEW.actual_away_score THEN
                    v_winner_id := NEW.away_team_id;
                ELSE
                    v_winner_id := NEW.penalty_winner_id;
                END IF;

                v_round_pts := CASE NEW.stage
                    WHEN 'r32'         THEN 5
                    WHEN 'r16'         THEN 10
                    WHEN 'qf'          THEN 15
                    WHEN 'sf'          THEN 20
                    WHEN 'third_place' THEN 10
                    WHEN 'final'       THEN 25
                    ELSE 0
                END;

                UPDATE knockout_predictions kp
                SET points_awarded = CASE
                        WHEN v_winner_id IS NOT NULL
                             AND kp.predicted_winner_id = v_winner_id
                        THEN v_round_pts
                        ELSE 0
                    END
                WHERE kp.match_id = NEW.id;
            END IF;

            -- 3. Leaderboard snapshots: fan out per (player, active league),
            --    ranked by the U38 merit cascade. RANK() ties two players only
            --    when they match on every merit axis AND have no distinguishing
            --    manual override — so a shared rank IS the all-axis tie.
            INSERT INTO leaderboard_snapshots (
                id, player_id, league_id, total_points, match_points,
                knockout_winner_points, special_points,
                exact_count, correct_result_count, correct_goals_count,
                specials_correct_count, ko_winner_correct_count,
                rank, snapshot_at, triggered_by_match_id
            )
            SELECT
                gen_random_uuid(),
                lm.player_id,
                lm.league_id,
                player_totals.total_points,
                player_totals.match_points,
                player_totals.knockout_winner_points,
                player_totals.special_points,
                player_totals.exact_count,
                player_totals.correct_result_count,
                player_totals.correct_goals_count,
                player_totals.specials_correct_count,
                player_totals.ko_winner_correct_count,
                RANK() OVER (
                    PARTITION BY lm.league_id
                    ORDER BY
                        player_totals.total_points DESC,
                        player_totals.exact_count DESC,
                        player_totals.correct_result_count DESC,
                        player_totals.correct_goals_count DESC,
                        player_totals.specials_correct_count DESC,
                        player_totals.ko_winner_correct_count DESC,
                        tbo.manual_order ASC NULLS LAST
                ),
                {snapshot_at_expr},
                NEW.id
            FROM league_memberships lm
            JOIN ({_PLAYER_TOTALS}) AS player_totals
                ON player_totals.player_id = lm.player_id
            LEFT JOIN leaderboard_tiebreak_overrides tbo
                ON tbo.league_id = lm.league_id
               AND tbo.player_id = lm.player_id
            WHERE lm.deleted_at IS NULL;

            RETURN NULL;
        END;
        $func$;
    """


def upgrade() -> None:
    op.execute(_trigger_fn("statement_timestamp()"))


def downgrade() -> None:
    op.execute(_trigger_fn("now()"))
