# 08 — Sequencing: how Batches 169-203 group

The same discipline as 2026-09-13: `/batch-start N` takes one batch, on its own branch,
through its own gate, with its own automatic close-out. A group only decides order and
where a production shipment has to fall.

**The deploy asymmetry still governs everything.** Every close-out pushes `main` and Vercel
releases the web app from it; Railway moves only on `/ship-prod`. A web half that calls a
route the deployed API does not serve is broken in production for the length of that gap —
and PIPE-14 shows the guard does not stop the two-batch version of that.

**Start from level.** Production and `main` are in sync (API `b08a47f3`, migration 026; web
at `4121cf0`), so no shipment is owed before Batch 169 starts.

## What to do before any batch — owner actions, not batches

| action | why now |
| --- | --- |
| **Switch on the weekly backup** (Batch 95 is built and off) | production has had **no backup for 56 days** (since launch, 4 Aug); lens 02 proved the job and its restore against a local fake target, so the remaining work is the bucket, the key and one hand-run. Steps: `docs/runbooks/backup-restore.md` |
| **Rescope the local agent configuration** (PIPE-01) | unchanged since 30 Jul; this review's own session was offered the Supabase write tools bound to another product |
| **Do not run the season-calendar backfill until Batch 188 has shipped** | a deleted league's early round would renumber every live league (CORR-25) |
| ~~Answer the decisions in the README~~ | **answered "yes to all" on 30 Sep**; recorded in each row and, for gate maintenance, in the guardrail |

## The run order, as `/group-start` runs it (2026-09-30)

At the owner's request (30 Sep) these groups are in the `/group-start` manifest
(`docs/agent-commands/group-start.md`). With 169 run on its own, every phase in
`09-prompts.md` after the first is exactly one group, so the whole plan is nine commands:

```text
/batch-start 169    169
/group-start AG     198 → 200 → 199 → 201 → /ship-prod
/group-start AA     172 → 173 → 174 → 170
/group-start AC     180 → 179 → 181 → 182 → /ship-prod
/group-start AD     183 → 188 → /ship-prod → 184 → 185 → 186 → 187 → /ship-prod
/group-start AE     189 → 190 → 191 → 192 → 193 → /ship-prod
/group-start AB     171 → 175 → 176 → 177 → 178
/group-start AF     196 → 195 → 197 → /ship-prod → 194 → /ship-prod
/group-start AH     202 → 203 → /ship-prod
```

Four things differ from the groups as first drafted below; each is recorded in its group.

- **169 runs alone**, outside AA, so `/group-start AA` cannot carry on into 172 before AG has
  repaired the gate. The command also refuses any AA-AH group but AG while an AG batch is open.
- **AG and AH end in a `/ship-prod`.** Neither is application work, but 199 and 203 edit files
  under `apps/api`, which the drift check counts as reaching the API image — and from Batch 201
  on, close-out refuses any web change while a shipment is owed.
- **AD ships after 188** as well as at its end, so 183's HIGH is live and the owner can run the
  season-calendar backfill four batches sooner.
- **AF ships before 194** as well as after it, so the review's only migration ships alone.

**Pauses inside a group.** Close-out refuses a batch that changes both API and web until the
owner schedules the matching `/ship-prod` (`phase-closeout.md` step 3), so AC pauses at 179 and
182, AD at 186 and 187, and AF at every batch. The shipment scheduled there can be the group's
next checkpoint: it directly follows 187 and 194; 179 and 186 are specified to work before their
API half ships, and 195 and 197 are too since 30 Sep; and the web halves of 182 (a CSP change)
and 196 (a filter the old API ignores, a join code it already returns) break nothing in the gap.

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

Since 30 Sep, Batch 169 sits outside the `/group-start AA` manifest: it runs as
`/batch-start 169`, then Group AG, then `/group-start AA` (172 → 173 → 174 → 170).

## Group AG — The pipeline · Batches 198, 200, 199, 201 · **tooling-only** → a behaviour-neutral `/ship-prod`

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

**It still ends in a `/ship-prod`** (30 Sep). 199 fixes two backend tests
(`apps/api/tests/test_durable_rate_limit.py` and `test_scheduler_jobs.py`), and
`scripts/check-deploy-drift.sh` counts everything under `apps/api` as reaching the API image, so
after 199 the drift check reports a shipment owed. 201 then makes close-out refuse any web change
while one is owed, so without the ship Group AA's first batch would be refused. The shipment
migrates nothing and changes no behaviour, so its rollback is a plain redeploy; if 199 lands
without touching `apps/api`, the checkpoint finds drift in sync and passes.

## Group AC — Security · Batches 180, 179, 181, 182 · **API + web** → `/ship-prod`

| batch | finding |
| --- | --- |
| 180 | SEC-28 the per-source backoff never stops a lock |
| 179 | SEC-32 (HIGH), SEC-27 — league-admin resets reach every member and their other leagues (**owner decision 1**) |
| 181 | SEC-29, FEAT-A15 — per-league names (**owner decision 5**) |
| 182 | SEC-31, CSP hygiene, one stale comment |

180 first; the decisions 179 and 181 waited on (1 and 5) were answered on 30 Sep. 179's web half
is copy only and safe before the API ships, and 182's is a CSP change, so both close-out pauses
can schedule the group's one `/ship-prod`.

## Group AD — Correctness and data · Batches 183, 188, 184, 185, 186, 187 · **API-carrying (186, 187 with web)** → `/ship-prod` after 188 and at the end

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

**A `/ship-prod` after 188** (owner, 30 Sep; first drafted as optional): 183 and 188 ship
together, so the HIGH is live and the backfill unblocked before the four batches that remain,
which include both of the group's max-effort batches. The closing shipment directly follows 187,
whose admin action calls a route the deployed API does not yet serve.

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

## Group AF — Member features · Batches 196, 195, 197, 194 · **API + web; 194 migrates** → `/ship-prod` before 194 and after it

| batch | finding |
| --- | --- |
| 196 | FEAT-B09, FEAT-B12 — results season filter; share the join code |
| 195 | FEAT-A12 closed sign-ups (**owner decision 10**) |
| 197 | DES-23 invite preview (**owner decision 12**) |
| 194 | FEAT-B10, FEAT-B11 — notification history (**owner decision 9**) |

**194 last and shipped on its own**: it is the review's only migration, so it removes the
rollback target until the next non-migrating shipment and needs its recovery note (Batch 128).
The manifest therefore stops for `/ship-prod` after 197 as well as after 194. 195 and 197 each
add a route their own web half calls; since 30 Sep both rows require that web half to behave as
today until the route ships, so the three batches before the first stop can share it.

## Group AH — Toolchain and hygiene · Batches 202, 203 · **tooling** → a behaviour-neutral `/ship-prod`

| batch | finding |
| --- | --- |
| 202 | SEC-30, OPS-15, PERF-22 — toolchain refresh (**owner decision 8**) |
| 203 | PIPE-15, 16, 17, 19, OPS-19 — hygiene |

Both touch protected files; 202 is a sequence of majors with the gate green after each.

It ends in a `/ship-prod` for the reason AG does: 203 drops the stale pins in
`apps/api/pyproject.toml` and rewrites Batch 161's backend tests. That also fixes the order
inside the group — the close-out guard counts 202 as a web change (`apps/web/package.json` and
the lockfile), so it must close out before 203 leaves a shipment owed.

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
