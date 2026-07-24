# Runbook: Re-score Knockout Advancement Points

Use this when a **knockout match decided on penalties (or by an extra-time goal)
shows the correct bracket progression but awards 0 advancement points** to the
players who picked the team that went through.

---

## Root cause

The `matches_score_results` trigger grades advancement off `penalty_winner_id`,
but until migration **037** it only re-fired when `actual_home_score` /
`actual_away_score` *changed* (the `IS DISTINCT FROM` guard added for U63 live
scores). On the auto-sync path a level knockout is written like this:

1. live in-play sync draws the match level (e.g. 1-1) — trigger fires,
   `penalty_winner_id` still NULL, advancement graded 0 (correct, undecided);
2. the final whistle sets `penalty_winner_id` but writes the same 1-1 score.

Step 2 changed no score column, so the trigger did not re-fire and the round
points (5/10/15/20/25) were never awarded. Migration 037 widens the trigger to
also fire when `penalty_winner_id` changes, fixing it **going forward**. Matches
that already settled under the old trigger need a one-off re-score.

> Unaffected: knockouts won inside 90 minutes (graded live on the deciding goal),
> admin manual entry/override that changed the score, and bracket slot-filling
> (the resolver reads `penalty_winner_id` directly, so progression was correct).

---

## Precondition — migration 037 must be deployed to prod

Re-firing the trigger only re-scores correctly once the fixed trigger is live.
Confirm it is applied before doing anything else:

```sql
SELECT version_num FROM alembic_version;   -- expect 037 (or later)
```

If this is below 037, deploy first (the backend runs `alembic upgrade head` on
boot) and re-check. Do **not** attempt the re-score against the old trigger.

---

## Step 1 — Take a backup

```bash
curl -X POST "https://<prod-api-domain>/api/v1/admin/backup" \
  -H "Authorization: Bearer <admin-jwt-token>"
```

---

## Step 2 — Detect affected matches (read-only)

A completed knockout that was level after 90, has an advancer recorded, yet a
player who picked that advancer still shows 0 points, is unscored:

```sql
SELECT m.id, m.match_number, m.stage,
       m.actual_home_score, m.actual_away_score, m.penalty_winner_id,
       count(*) FILTER (
         WHERE kp.predicted_winner_id = m.penalty_winner_id
       ) AS advancer_pickers,
       count(*) FILTER (
         WHERE kp.predicted_winner_id = m.penalty_winner_id AND kp.points_awarded = 0
       ) AS ungraded_pickers
FROM matches m
JOIN knockout_predictions kp ON kp.match_id = m.id
WHERE m.stage <> 'group'
  AND m.status = 'completed'
  AND m.actual_home_score = m.actual_away_score
  AND m.penalty_winner_id IS NOT NULL
GROUP BY m.id
HAVING count(*) FILTER (
         WHERE kp.predicted_winner_id = m.penalty_winner_id AND kp.points_awarded = 0
       ) > 0
ORDER BY m.match_number;
```

No rows ⇒ nothing to do.

---

## Step 3 — Re-score (idempotent)

Re-assert each affected match's advancer so the fixed trigger re-fires. The
90-minute score is unchanged, so only toggling `penalty_winner_id` re-fires it;
the NULL flicker is inside the transaction and never observed. Safe to run over
**all** completed knockout draws — re-grading an already-correct match is a no-op.

```sql
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT id, penalty_winner_id
    FROM matches
    WHERE stage <> 'group'
      AND status = 'completed'
      AND actual_home_score = actual_away_score
      AND penalty_winner_id IS NOT NULL
  LOOP
    UPDATE matches SET penalty_winner_id = NULL              WHERE id = r.id;
    UPDATE matches SET penalty_winner_id = r.penalty_winner_id WHERE id = r.id;
  END LOOP;
END $$;
```

This only touches `penalty_winner_id`, so the BEFORE trigger leaves
`result_entered_at` (first-score time) untouched. Each re-fire writes a fresh
leaderboard snapshot per player — expected.

---

## Step 4 — Verify

Re-run the Step 2 query — it should now return no rows. Spot-check one match:

```sql
SELECT pf.display_name, kp.predicted_winner_id, kp.points_awarded
FROM knockout_predictions kp JOIN profiles pf ON pf.id = kp.player_id
WHERE kp.match_id = '<MATCH_ID>'
ORDER BY kp.points_awarded DESC;
```

Pickers of `penalty_winner_id` should hold the round value (r32 5, r16 10, qf 15,
sf 20, third_place 10, final 25); everyone else 0. Then confirm the leaderboard
reflects the restored totals:

```bash
curl "https://<prod-api-domain>/api/v1/leaderboard" \
  -H "Authorization: Bearer <admin-jwt-token>" | jq '.[0:5]'
```

---

## Notes

- The reproduction is locked in by `test_knockout_penalty_winner_awards_points_after_live_draw`
  in `apps/api/tests/test_scoring_trigger.py` (live draw → penalty finish → points).
- Same root cause covered an admin override that corrected **only**
  `penalty_winner_id` on an unchanged scoreline; 037 fixes that too.
