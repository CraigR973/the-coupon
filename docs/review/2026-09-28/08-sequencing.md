# 08 — Sequencing: how Batches 169-203 group

The same discipline as 2026-09-13: `/batch-start N` takes one batch, on its own branch,
through its own gate, with its own automatic close-out. A group only decides order and
where a production shipment has to fall.

**The deploy asymmetry still governs everything.** Every close-out pushes `main` and Vercel
releases the web app from it; Railway moves only on `/ship-prod`. A web half that calls a
route the deployed API does not serve is broken in production for the length of that gap —
and PIPE-14 shows the guard does not stop the two-batch version of that.

**Start from level.** Production and `main` are in sync (API `b08a47f3`, migration 026; web
at `4121cf0`), so no shipment is owed before Group AA starts.

## What to do before any batch — owner actions, not batches

| action | why now |
| --- | --- |
| **Switch on the weekly backup** (Batch 95 is built and off) | production has had **no backup for 56 days** (since launch, 4 Aug); lens 02 proved the job and its restore against a local fake target, so the remaining work is the bucket, the key and one hand-run. Steps: `docs/runbooks/backup-restore.md` |
| **Rescope the local agent configuration** (PIPE-01) | unchanged since 30 Jul; this review's own session was offered the Supabase write tools bound to another product |
| **Do not run the season-calendar backfill until Batch 188 has shipped** | a deleted league's early round would renumber every live league (CORR-25) |
| Answer the decisions in the README | eleven batches wait on one |

## Group AA — Web fixes members meet today · Batches 169, 170, 172, 173, 174 · **web-only** → no shipment

| batch | finding |
| --- | --- |
| 169 | DES-10 every toast illegible in dark mode — shipped by Batch 149's last commit on 28 Sep |
| 172 | UX-31 offline pick spinner (= DES-16), UX-25 failures shown as empty, DES-17 first-run copy while loading |
| 173 | UX-18 (never batched), UX-21, DES-15, DES-20, CORR-26 — the settled state |
| 174 | UX-28, UX-30, UX-22, UX-29, UX-33, UX-23 — keyboard focus and landmarks |
| 170 | UX-26, UX-24, UX-32, UX-27 — tab bar, labels, zoomed header |

**169 first and alone** — it is extra-small and the one finding here that every member in
the default theme meets on the pick path. 172 next: on a Saturday it is the difference
between "no coupon this week" and "try again". Each reaches members on its own push.

## Group AG — The pipeline · Batches 198, 200, 199, 201 · **tooling-only, deploys nothing**

| batch | finding |
| --- | --- |
| 198 | PIPE-10, PIPE-11 — the gate judged by its own copy; config files that switch checks off |
| 200 | PIPE-13 — the end-to-end journey outside the gate |
| 199 | PIPE-12 — CI red, pushes on red, nothing reads it (**owner decision 6**) |
| 201 | PIPE-14 — split-half clearance unrecorded; two-batch split passes |

**Take 198 straight after 169**, for the reason 152 went first last time: every later batch
is verified by the gate it repairs, and close-out deploys on green. All four edit protected
files, so each needs the owner's gate-maintenance approval recorded in the guardrail before
it starts (the 127/153 pattern). 200 before 199, because putting the journey in the gate is
what makes CI's result worth waiting for.

## Group AC — Security · Batches 180, 179, 181, 182 · **API + web** → `/ship-prod`

| batch | finding |
| --- | --- |
| 180 | SEC-28 the per-source backoff never stops a lock |
| 179 | SEC-32 (HIGH), SEC-27 — league-admin resets reach every member and their other leagues (**owner decision 1**) |
| 181 | SEC-29, FEAT-A15 — per-league names (**owner decision 5**) |
| 182 | SEC-31, CSP hygiene, one stale comment |

180 needs no decision, so it can start while 179's is pending. 179's web half is copy only and
safe before the API ships.

## Group AD — Correctness and data · Batches 183, 188, 184, 185, 186, 187 · **API-carrying (186, 187 with web)** → `/ship-prod`

| batch | finding |
| --- | --- |
| 183 | PERF-19 (HIGH) combined odds overflow at 30-50 members |
| 188 | CORR-25 backfill counts deleted leagues — **before the owner runs the backfill** |
| 184 | CORR-20, CORR-13 — non-scoring rounds still offered; shared labels (**owner decision 3**) |
| 185 | CORR-19, CORR-27 — departing members (**owner decision 2**) |
| 186 | CORR-21 void legs on two more surfaces |
| 187 | FEAT-A13, FEAT-A14, CORR-22, CORR-23 — correction as a tool (**owner decision 4**) |

183 first: it is the HIGH, and it needs no decision. 188 second because it unblocks an owner
action. 187 last: it rewrites awarded points across leagues and is the largest.

## Group AE — Provider budget and scheduler · Batches 189, 190, 191, 192, 193 · **API-carrying** → `/ship-prod`

| batch | finding |
| --- | --- |
| 189 | CORR-24, PERF-21 — discovery priced at the raw pool; the refresh unbudgeted |
| 190 | PERF-23 one pick bucket for the whole deployment |
| 191 | PERF-20 a pick burst exhausts the pool and drops alerts |
| 192 | PERF-18 two queries per competition on the pick screen |
| 193 | OPS-17, OPS-18 — misfire grace and the top of the hour |

**Order is load-bearing:** 189 changes what each job spends, so 190's sizing is taken
against the real number. 191 and 190 both touch the pick path; run them in that order, not
together.

## Group AB — The visual pass, finished · Batches 171, 175, 176, 177, 178 · **web-only** → no shipment

| batch | finding |
| --- | --- |
| 171 | DES-11 the tint layer compiles to nothing |
| 175 | DES-13, DES-14 — prices below the fold at caption size |
| 176 | DES-12 Z-order rankings at 1280 |
| 177 | DES-08, 19, 21, 22, PERF-16, PERF-17 — consistency and web-performance residue |
| 178 | DES-18 installed-app shell (**owner decision 11**) |

171 first: 176 and 175 use its tint tokens, and it has the widest contrast blast radius, so
everything after it is measured against the corrected palette.

## Group AF — Member features · Batches 196, 195, 197, 194 · **API + web; 194 migrates** → `/ship-prod`

| batch | finding |
| --- | --- |
| 196 | FEAT-B09, FEAT-B12 — results season filter; share the join code |
| 195 | FEAT-A12 closed sign-ups (**owner decision 10**) |
| 197 | DES-23 invite preview (**owner decision 12**) |
| 194 | FEAT-B10, FEAT-B11 — notification history (**owner decision 9**) |

**194 last and shipped on its own**: it is the review's only migration, so it removes the
rollback target until the next non-migrating shipment and needs its recovery note (Batch 128).

## Group AH — Toolchain and hygiene · Batches 202, 203 · **tooling**

| batch | finding |
| --- | --- |
| 202 | SEC-30, OPS-15, PERF-22 — toolchain refresh (**owner decision 8**) |
| 203 | PIPE-15, 16, 17, 19, OPS-19 — hygiene |

Both touch protected files; 202 is a sequence of majors with the gate green after each.

## Accepted with no action (carried)

- **CORR-16** — the season-rollover week split. Still true, still harmless (02).
- **PERF-02** — one worker with the scheduler in-process, by owner decision; revisit before
  about ten leagues (04 re-measured it).
- **Site-admin league-admin writes** in a league they have not joined — recommended **keep**
  as Batch 125's deliberate scope (README decision 13).
- SEC-14 and every other recorded decision are unchanged.

## What this review did not finish

- **Lighthouse and the wall-clock timings** (PERF-14 and the timing rows of lens 04) were
  staged but ran into the fourth usage limit; see `04-performance-operations.md` for their
  state at the final commit.
- **No real device.** WebKit will not install here, so iOS standalone rendering, the status
  bar and the splash are judged from files and geometry (DES-18), and there was no
  screen-reader run.
- **No production reads** beyond headers, `/api/v1/health` and public pages, by the
  guardrails; the backup state, push subscription counts and member B's rename notice come
  from `STATUS.md`.
