# Lens 04 progress — performance and operations

A fresh session resumes from this file alone. Brief: `../briefs/common.md` + `../briefs/04-perf.md`.
Ports: API 8140 (8141 spare), web 4340. New ids from PERF-18 / OPS-19.
Commit only own paths: `git -C <repo> commit -m "..." -- docs/review/2026-09-28/notes/04-perf docs/review/2026-09-28/04-performance-operations.md`

## Timeline

- 29 Sep 08:39 started; usage limit stopped it ~08:50. Resumed 14:47 (load 3.28/5.24/7.94).
- Branch history rewritten 14:50 by lead (privacy scrub) — old hashes stale.

## Stack

`stack.py --name perf --api-port 8140 --no-api` (DB only), restarted 14:48. DB url in
`<scratch>/stack-perf.json`. Kill with SIGTERM at the end.

## Done

- read briefs, 00-prompt, 2026-09-13 README + 04 doc, AGENTS.md, STATUS.md
- code survey: scheduler (13 jobs, only offsite_backup has misfire_grace_time), main.py
  (GZip min 4096, level 6, innermost), database.py (pool 5+5, timeout 10), one uvicorn
  worker (nixpacks start cmd), picks.py fan-out now BackgroundTasks, push sends in
  default executor, session held across whole fan-out (candidate finding: pool hold),
  request budget test (481 = browsing 252 + discovery 92 + weekly 41 + warm 27 + manual 69;
  omits refresh_slate, settle, pick path; browsing priced for ONE round)
- `seed_shapes.py` written (production + stress), not yet run

## Cross-lens facts (lead, 14:55)

- lens 02 CORR-24: discovery budget prices each walk at raw pool (36) while 23 walked;
  run_refresh_slate has no budget. Measure refresh per-window cost, 3- and 5-window hours myself.
- lens 07: no-DB pytest split today 800 passed / 550 skipped.
- timings only under load 4; 03 and 05 running.

## Measured so far (production shape seeded 14:49: 5 leagues, 1,174 fixtures, 35 rounds, 265 picks)

`api-production.json` / `api-production-sql.txt` (measure_api.py):
- home summary 13 stmts (Solo 1 league and Alice 3 leagues) — was 15 → Batch 144 held
- current round 56 stmts = 10 + 2 per competition (23) — fixture_context loops
  resolve_names per competition (football_data.py:950), unchanged since Batch 16 → NEW
  finding PERF-18 (prior "no N+1" claim wrong for the slate; its shape had few competitions)
- slate fully priced 264 fx: 299,134 B identity → 15,202 B gzip; standings 10.4 KB → 1.2 KB;
  <4 KB responses uncompressed by design (BREACH note in main.py)
- coupon 6, standings 5 (±season), results 7, rounds 8, pick submit 11 + 3 background
- production /health headers (prod-health-headers.txt): 82 B, below the 4 KB floor, so
  compression cannot be confirmed read-only (no public response >4 KB)

## Resumes

- 18:35 resumed (third stop). Lead: be economical, compact result files, commit each step.

## Measured since 18:35 (all in the lens doc)

- stress seeded; api-stress.json: all counts identical except slate (66); **PERF-19 HIGH**
  combined odds overflow → 500 on home summary + results at 50 members (combined-odds-limit.txt)
- explain-stress.txt: PERF-04 held (ix_picks_gameweek_id by planner's choice), PERF-05 held
- provider_budget.py 1/3/5 windows: PERF-06/07 held at 3w, PERF-08 held, **PERF-21** refresh
  no budget (118/hour at 5w); 481 derivation written; DB re-seeded (production+stress) after
- npm-latest.txt: current majors for OPS-15; OPS-11 Node 24 in CI/gate/.nvmrc/engines (not yet in doc)
- framer-motion: in package.json deps, zero imports (test enforces) — check bundle once built

## Measured 23:14-23:50 (all written into the lens doc and committed)

- web: bundle.json, browser-run1.json (idle 120 s), browser.json (render counts, corrected
  cloned-fiber method) → PERF-11/12/13/15/16 held, PERF-17 not fixed, PERF-22 (framer dep)
- push_fanout.py via run_push_api.sh (:8141, stopped) → PERF-10 held, **PERF-20** pool
  exhaustion (2×500, 6 of 10 fan-outs lost; push-fanout-errors.txt)
- pick_buckets.py → PERF-09 held, **PERF-23** installation cap 50/h 100/day
- jobs.py + misfire_demo.py → OPS-17 not fixed (verified drop), OPS-18 not fixed
- ops12-recovery-rehearsal.txt → OPS-12 held; alarm_push.py → OPS-14 held; OPS-13 prose;
  OPS-19 Node 20 in ship-prod CLIs
- DB note: jobs.py locked rounds; reopen.py + alarm_push.py restored Oct 2/3 rounds to open

## Still running

- perf API `run_api.sh` on :8140 (uvicorn perf_app) and web preview on :4340 (web.sh perf)
- stack perf (DB)

## 23:54 state

Lens doc complete except Lighthouse + timings (PERF-14, PERF-02 concurrency). Register:
PERF-19 HIGH; PERF-18, 20, 21, 23 MED; OPS-19, PERF-22 LOW. Prior: held 15, partial 1,
not fixed 5, by-decision 1, pending 1, regressed 0.

Lighthouse started 23:54 in background (lighthouse.mjs, WAIT_MIN=40, gates on load<4) →
writes lighthouse.json per page; log <scratch>/lighthouse.out.txt.

## TIMINGS PENDING QUIET MACHINE (stopped 23:55, load 9.5)

Everything else is done and in the lens doc. All processes stopped (API 8140, preview
4340, Lighthouse, stack perf). The seeded data is still in `<scratch>/pg-perf`.

## Next step — exact commands, run only when the 1-minute load average is under 4

```bash
S=/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad
N=/Users/craigrobinson/the-coupon/docs/review/2026-09-28/notes/04-perf
# 1. database, KEEPING the seeded shapes (without --keep-data the schema is reset;
#    then re-run: bash $N/run.sh seed_shapes.py production && bash $N/run.sh seed_shapes.py stress)
nohup ~/.cache/the-coupon/ci-local-venv/bin/python $N/../harness/stack.py --name perf --api-port 8140 --no-api --keep-data > $S/stack-perf.out.txt 2>&1 &
bash $N/run.sh reopen.py                      # 3 Oct rounds open
# 2. API (PricedFake) on 8140 and the prod bundle on 4340
nohup bash $N/run_api.sh > $S/perf-api.out.txt 2>&1 &
nohup bash $N/../harness/web.sh perf http://127.0.0.1:8140 4340 > $S/web-perf.out.txt 2>&1 &
# 3. fresh sign-in state (browser.mjs signs in once and writes it), then Lighthouse (gates on load < 4)
. ~/.nvm/nvm.sh && nvm use 24 --silent
STATE=$S/perf-state.json node $N/browser.mjs 2
STATE=$S/perf-state.json LH=$S/tools/lighthouse WAIT_MIN=40 node $N/lighthouse.mjs   # -> lighthouse.json
# 4. wall-clock: sequential p50/p95 and 20 concurrent home summaries (gates on load < 4)
bash $N/run.sh concurrency.py                 # -> timings.json
```

Then: add PERF-14 verdict (standings median score/TBT vs 77 / 915 ms), the Lighthouse row
of "The web client" table, the timings (PERF-02 concurrency vs 1,254 ms) to "The numbers";
remove the pending notes; stop everything; commit; reply to the lead.
