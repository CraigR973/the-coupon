# Lens 02 — Correctness — progress

Ports: API 8120, web 4320. New ids from CORR-19. Stack name `corr`.
Command output is saved as `.txt` (`*.log` is gitignored).
Interrupted once by a usage limit (28 Sep ~23:04); resumed 29 Sep 08:40 on a fresh stack.

## Done
- Read common brief, lens brief, 00-prompt, BUILD_PLAN contract + rows 95/115/120/121/130-136/147/156/157/159-161, 2026-09-13 02-correctness + README.
- Code read (diff 2ce6f42..HEAD): picks router, gameweek (retire/discover/sync_slate), scoring (settle guard, win rate, results), coupon, season_calendar, round_completion, notification_triggers (settle notify, roster completion), account_erasure + me.py delete, admin correct_pick, scheduler (reminder UTC, discovery budget, refresh narrowing, offsite backup), backup_storage.

## Candidate findings from code reading (each needs a live repro)
1. **Void legs still multiplied on two surfaces.** `scoring.gameweek_results` (Results page) and `me._last_results` / `me._latest_rounds` (home "Last result" panel and card) call `combined_odds` over *every* leg; only `build_coupon` filters void (Batch 156). Screen vs results/home disagree.
2. **Self-deletion never re-evaluates round completion.** `routers/me.py delete_my_account` does not call `settle_completion_after_roster_change` (leave, remove and site-admin delete do — Batch 130). `round_progress` excludes inactive/deleted profiles, so the last outstanding picker deleting their account completes the round silently, and the next pick change fires the completion crediting that member = CORR-14 on a new path.
3. **Settle guard can strand a legitimately picked round.** `_same_week_round_may_settle` refuses an *intentional* round when an undeclared sibling in the same football week already settled (e.g. window Friday→Saturday or Saturday→Sunday changed after the old round settled). Discovery still creates the new round, members can pick it, and it can never settle (picks pending forever, error log each sweep).
4. **Pick correction is silent** — no re-notification after Batch 135 told the member the wrong result (spec does not require it; LOW/INFO). Check coupon scoreline vs corrected status.
5. `run_refresh_slate` has no `request_budget` (Batch 133 budgets only daily discovery). Measure at 3 windows.
6. Lock/open offsets use wall-clock arithmetic across DST (INFO unless an offset spans 01:00-02:00 on a change day).

## Next step
- Start fresh stack (old one killed by lead): `~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/harness/stack.py --name corr --api-port 8120 --origin http://127.0.0.1:4320 --seed` in background.
- Write `seed_two_leagues.py` (in-process, scratch DB) + a custom server `corr_server.py` if a richer FakeBetfair is needed (API's fake only prices e-epl-1 / e-sl2-1 on 2026-08-01).

## Prior findings status
| id | status | evidence file |
| --- | --- | --- |

## Harness state (29 Sep 14:17, after second interruption)
- DB holder: `stack.py --name corr --no-api` (scratch pg at pg-corr). API: `bash corr_api.sh` = `corr_server.py` on 8120
  (e2e app, provider overrides removed so requests use odds_session -> CachingOddsProvider -> `richfake` CountingFake;
  pushes captured at `GET/DELETE /__corr/pushes`; provider calls at `/__corr/calls`).
- Driver scripts: `bash run.sh <script.py>` (runs from scratchpad; `lib.py` points settings at the scratch DB).
- Seeded by `seed_two_leagues.py` (L1 Sat defaults MO/selection; L2 Fri 19-22 lock 60 both markets EPL+Champ fixture scope;
  L3/L4 race leagues 12 members each, selection/fixture). `add_subs.py` gives every profile a fake push subscription.
- Rounds after discovery: L1/L3/L4 Sat 3 Oct (lock 13:30Z), L2 Fri 2 Oct (lock 17:00Z). Calendar 2026 anchor 3 Oct.

## Verified so far (also written into 02-correctness.md)
- CORR-08 held (race.py, out/race.txt). NOTE: pick buckets are in-memory; restart corr_api.sh to reset the 50/hour installation bucket after ~45 submissions.
## Next
- DONE: CORR-14 partial + CORR-19 verified (completion.py). Next: settle-guard stranding (CORR-20 candidate), then void-leg surfaces, then CORR-09/13 window change.
