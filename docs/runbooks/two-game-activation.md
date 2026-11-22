# Two-game activation, suspension and resume

Batch 231, 22 Nov 2026. How one league is switched to two games per football week, how it
is suspended in an emergency, and how a suspension is lifted. Every step here needs the
owner's explicit approval at the time; nothing in this runbook is standing permission.

The actions live in `apps/api/src/services/two_game_rollout_admin.py`. Two entry points run
the same functions with the same checks and the same audit row:

- site-admin routes: `GET /api/v1/admin/leagues/{league_id}/two-game`, and `POST` to
  `…/two-game/activate`, `…/two-game/suspend`, `…/two-game/resume`. Each `POST` previews
  unless its body has `"apply": true`.
- the operator command `python -m src.two_game_rollout`, which previews unless `--apply`
  is given and names the site admin with `--actor <profile id>`.

Neither restarts a service. Audit rows are `league_updated` against `two_game_rollouts`
with the league as `target_id`, so they appear in the league's own audit log.

## Before activation

1. Batch 228's activation checkpoint is accepted by the owner: opening-time fixture and
   price coverage, the odds quota and scheduler headroom, supported traffic, refresh and
   result latency, a fresh backup that restores, this suspension procedure, and every
   member's season total recorded.
2. `TWO_GAMES_ENABLED=true` on **both** `api` and `payments`, with no rollout row, and
   legacy verified unchanged afterwards (health, `scripts/check-deploy-drift.sh`, a
   read-only audit, the next morning's legacy jobs).

**Where the lossless undo ends.** `docs/runbooks/migration-032-undo.sql` refuses once any
two-game table holds a row. With the flag on, every odds-api.io request — legacy ones
included — reserves a `provider_attempts` row, and joins and departures record
`membership_intervals`. So the undo ends at the flag, not at activation. Take the fresh
backup before turning the flag on; from then on recovery is a forward fix or that backup
(`docs/runbooks/migration-032-recovery.md`, `docs/runbooks/backup-restore.md`).

## Activation

What the action checks, all in one transaction, refusing with a code and changing nothing:

| Code | Meaning |
| --- | --- |
| `FORMAT_DISABLED` | `TWO_GAMES_ENABLED` is off in the process running the action |
| `NOT_SITE_ADMIN` | the actor is not an active site admin |
| `NOT_A_SATURDAY` | the first week is not a Saturday label |
| `ALREADY_ACTIVATED` | the league already has a rollout row |
| `TWO_GAME_STATE_PRESENT` | the league already holds a two-game week, game, due or break |
| `TOO_LATE` | the first week's Saturday-noon fantasy lock has passed |
| `LEGACY_WEEK_TOUCHED` | a legacy round from five days before the first week onwards has opened, or holds a pick, ledger entry, completion or notice |
| `LEGACY_WEEK_PRESENT` | untouched legacy rounds are on the board and `retire_untouched_legacy` was not requested |
| `OPENING_PASSED` | the first week's rule opening (previous Saturday noon) has passed and `open_at_activation` was not requested |

**Untouched legacy rounds.** Discovery writes each league's rounds two weeks ahead, so a
near Saturday usually already holds a scheduled legacy round. With
`retire_untouched_legacy` the action deletes those rounds — only if every one is still
scheduled, has a future announced opening and has no pick, ledger entry, completion or
notice — in the same transaction as the rollout row. It is the rule
`retire_stranded_rounds` already applies to rounds a league no longer plays. After the
row exists the database fence refuses any new legacy round from the cut-over onwards.

**Owner decision, 22 Nov 2026 — opening at activation.** When the first week's rule
opening has passed (28 Nov's was 21 Nov), `open_at_activation` lets the first week open at
activation instead, provided no member was ever shown anything about that two-game week:
the league must hold no two-game state at all. The rollout's `effective_opening` and the
audit row record the activation instant. The game rows keep the rule's stored opening,
because migration 032's fence accepts only a preceding Saturday noon there; nothing could
enter them before they existed, and no member screen shows an opening that has passed.

Steps, from this Mac against production (`railway run --no-local` with the explicit
production selectors; rewrite `DATABASE_URL` to the London session pooler in memory and
never print it — see the production-observability notes):

1. `python -m src.two_game_rollout status --league <slug>` — no rollout, the legacy rounds
   in reach.
2. Preview: `python -m src.two_game_rollout activate --league <slug> --first-week <Saturday>
   --actor <owner's profile id> [--retire-untouched-legacy] [--open-at-activation]`.
   Read the retired rounds, the rule opening and the effective opening.
3. The owner approves exactly what the preview printed. Rerun it with `--apply`.
4. Within two minutes the scheduler's discovery pass builds the first two weeks. Check with
   `status`: group and fantasy games for both weeks, the first group's opening and lock as
   announced, `calendar:<league id>` not in `schedule_conflict`, and one £1 obligation per
   member for the first week once the weekly-fee pass runs (every minute).
5. Confirm both first-week games accept entries for a member who has paid; the app sends
   its own "open" notices. Post the owner's message in the group chat (owner only).

## Suspension

Use it when entries or openings are misbehaving: wrong cards or prices, entries refused or
accepted wrongly, a game opening at the wrong time. It does not stop money.

- Command: `python -m src.two_game_rollout suspend --league <slug> --actor <id>
  --reason "<why>" --apply`, or the site-admin route with `"apply": true`.
- Effect, immediately and without a restart: every new entry, replacement and early fee
  for that league is refused with `SUSPENDED`; the calendar creates no new games and the
  lifecycle opens none and sends no "open" notice.
- Unchanged: weekly £1 billing (owner rule, 11 Nov), settlement of accepted picks,
  corrections, history and reads, and locking at each stored deadline.
- Never use `TWO_GAMES_ENABLED` as an emergency stop. Turning it off also stops weekly
  billing and settlement, strands accepted picks, and leaves the legacy cut-over fence in
  place, so the league would play nothing at all.

## Resume

1. Preview: `python -m src.two_game_rollout resume --league <slug> --actor <id>` prints the
   reconciliation: games whose opening passed and that will open now, games that locked
   while suspended (they stay locked — a locked game is never reopened), and any member
   week that should be billed but is not.
2. A billing gap refuses the resume (`BILLING_GAPS`). Find out why billing missed it and
   fix that first; the fee kept accruing while suspended.
3. The owner confirms the printed reconciliation. Rerun with `--confirm-reconciliation
   --apply`.

## After activation

Recovery is forward-only (`docs/runbooks/migration-032-recovery.md`). Natural acceptance
follows the plan's step 5: observe the first opening, both locks, real submissions
(including the same selection in both games), results through Sunday and the next opening.
