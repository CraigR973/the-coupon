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

## Next step

1. run `seed_shapes.py production`, then statement-count script (`measure_api.py`)
2. provider budget counting fake (`provider_budget.py`)
3. EXPLAIN at stress, bundle/precache, scheduler table, OPS checks
