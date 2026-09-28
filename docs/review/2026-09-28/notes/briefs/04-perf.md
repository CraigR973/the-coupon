# Lens 04 — Performance and operations

Output: `docs/review/2026-09-28/04-performance-operations.md`. Notes: `docs/review/2026-09-28/notes/04-perf/`.
Ports: API **8140** (and **8141** if you need a second shape up at once), web **4340**.
New ids start at **PERF-18** and **OPS-19**.

Re-take the 2026-09-13 measurements **the same way, at the same two data shapes**,
and report **before → after** for each. Read `docs/review/2026-09-13/04-performance-operations.md`
first — its tables are your "before". Its seeding scripts were lost, so rebuild the
shapes from its description and keep yours in your notes:

- **production's shape**: 5 leagues, largest 12 members, 6-7 rounds each, a shared
  pool of about a thousand fixtures;
- **stress shape**: that, plus a 50-member league with a full season of ~40 settled
  rounds at ~200 fixtures each and a pick per member per round.

## Machine discipline (important)

The machine is a 4-core 8 GB Intel Mac shared with up to five other passes, and
the last review's timings carried ±30% because of it. So:

1. Do every **load-independent** measurement first: statement counts, EXPLAIN
   plans, bytes, chunk counts, precache manifest, provider request counts, job
   statement counts. These are the primary evidence.
2. Record `uptime` alongside **every** timing you take.
3. Take **Lighthouse and wall-clock timings only when the 1-minute load average
   is under 4**. If it is not, finish everything else, write `progress.md` with
   "timings pending quiet machine" and the exact commands to run, commit, and
   report back to the lead with status `TIMINGS PENDING`. The lead will message
   you when the other passes have finished.

## Your slice of the 2026-09-13 register

| id | sev then | batch | check |
| --- | --- | --- | --- |
| PERF-01 + OPS-16 | MED / INFO | 144 | home summary statement count and row volume at both shapes, labels identical |
| PERF-02 | MED | owner decision: one worker; move the scheduler out before ~10 leagues | still one worker? concurrency numbers re-taken (20 concurrent home summaries was 1,254 ms each) |
| PERF-03 | MED | 145 | slate compressed locally (bytes on/off); production `content-encoding` / `vary` only via a **public, unauthenticated** response if one is large enough — otherwise say it could not be checked read-only |
| PERF-04 / PERF-05 | MED / LOW | 146 (migration 026) | EXPLAIN (ANALYZE) of the retirement and settle queries at the stress shape — index scans now? pool size |
| PERF-06/07 | HIGH | 159 | refresh job request count with a counting fake; three-window shape inside 100/hour and 500/day |
| PERF-08 | HIGH | 160 | counter and counting fake agree across a full Saturday |
| PERF-09 | HIGH | 161 | N leagues each spending their bucket cannot exceed the installation plan |
| PERF-10 | MED | 162 | pick-submit latency with push fan-out at 12 and 50 members (use a fake push sender that sleeps a realistic per-send time, e.g. the ~179 ms implied by 49 sends in 8,759 ms), and that every eligible member still gets exactly one alert |
| PERF-11 | MED | 163 | precache manifest entries and KiB (was 82 files, 974 KiB). The lead's smoke build printed "precache 83 entries (709.93 KiB)" — explain what is in it and whether role-gated chunks are still there |
| PERF-12 / PERF-17 | MED / LOW | 164 | animation library gone from the bundle? (The lead noticed `framer-motion` is still listed in `apps/web/package.json` dependencies — find out whether anything imports it or it reaches a chunk.) Fonts on the sign-in screen |
| PERF-13/15/16 | MED / LOW | 165 | React commits per idle 5 s on home and the round screen; the standings query key includes the season |
| PERF-14 | MED | 166 (closed by re-measurement, no code change) | standings TBT, Lighthouse mobile median of 3 |
| OPS-11 | HIGH | 127 | Node 24 in CI, the gate and the Vercel build |
| OPS-12 | HIGH | 128 | the `/ship-prod` workflow refuses a migrating shipment with no recovery note — rehearse the assertion script locally (`scripts/check-migration-recovery.sh`), do not run `/ship-prod` |
| OPS-13 | HIGH | 95 built, switched off | production still has no backup — state RPO/RTO today, and how long it has been open across reviews |
| OPS-14 | MED | 129 | a stale-discovery condition pushes once to site admins, not every run; a healthy deployment sends none |
| OPS-15 | LOW | left out of 127 | toolchain majors behind — current versions |
| OPS-17 | MED | **no batch** (the lead found none in BUILD_PLAN) | misfire grace time on the scheduled jobs |
| OPS-18 | LOW | **no batch** | jobs sharing the top of the hour; overrun behaviour |

## Also measure

- Bundle: total JS raw/gzip, chunk count, what `/login` and home download cold,
  what the service worker precaches afterwards.
- **Lighthouse mobile (throttled)** on the prod bundle served locally for home,
  current round (the coupon) and standings, median of 3 (sign in once and reuse
  storage state). Lighthouse is not installed — put it under
  `<scratchpad>/tools/lighthouse` with npm and point it at Playwright's Chromium
  (`~/Library/Caches/ms-playwright/chromium-1223`); record the version.
- Query counts and EXPLAIN on the hot endpoints: home summary, current
  round/slate, standings (with and without season), results, rounds list,
  combined coupon, pick submit — plus the new ones since 2ce6f42 (settlement
  notification fan-out, account export, pick correction's recompute).
- odds-api.io requests per scheduled job and per member action against 100/hour
  and 500/day with a counting fake, at production's shape and at three windows.
  **Explain how the "certified worst day is 481" figure is derived** (Batch 115;
  `apps/api/tests/test_request_budget.py`) and whether it is honest.
- Scheduler: every job, its trigger, duration at the stress shape, overlap at the
  top of the hour, misfire grace, coalescing.
- Deploy and rollback hygiene (128) — read `docs/agent-commands/ship-prod.md`
  and `phase-closeout.md`; what is the rollback target today (STATUS says a plain
  redeploy of `e77dde8f`) and does anything assert it.
- No load of any kind against production.
