# Lens 07 progress — agent delivery pipeline

Resume from this file. Brief: `notes/briefs/common.md` + `notes/briefs/07-pipeline.md`.
Deliverable: `docs/review/2026-09-28/07-agent-pipeline.md`. No ports.
Interrupted 28 Sep ~23:04 by a usage limit; resumed 29 Sep 08:40.
Working findings so far: `findings-draft.md` (read it first).

## State

| step | state | notes file |
| --- | --- | --- |
| read briefs, prompt, 2026-09-13 lens + README | done 28 Sep | — |
| commits since 2ce6f42, API/web classification | done | `commits-since-2ce6f42.txt`, `classify.sh`, `classify-output.txt` |
| CI runs since 20 Sep (read-only gh) | done | `gh-runs.txt`, `gh-failed-runs-summary.txt`, `gh-failed-pytest.txt` |
| 1 test-diff scan | scan done; manual review part-done | `scan_test_diffs.py`, `scan-test-diffs.txt`, `findings-draft.md` |
| 1b how the 7 API+web batches passed the split-half guard | todo | `findings-draft.md` |
| 2 weaken the gate in a throwaway worktree | todo | `gate-probes.md` |
| 2b replay guardrail on the three 22 Sep fix branches (scratch clone) | todo | `gate-probes.md` |
| 3 automatic push walk | todo | `push-walk.md` |
| 4 contradictions / stale facts | part (see draft) | `contradictions.md` |
| 5 cold-start cost | todo | `cold-start.md` |
| 6 enforced vs prose table | todo | in lens doc |
| prior findings PIPE-01..09 | PIPE-01 read (not fixed) | `findings-draft.md` |
| lens document | todo | `../../07-agent-pipeline.md` |

Do not touch the pre-existing worktree `/private/tmp/the-coupon-main-batch149` (detached at
7a1a7c7); record only.

## Exact next step

(29 Sep 14:17) Worktree `<scratchpad>/wt-pipeline` exists on `throwaway/pipeline-probe`
at eb18bcb with `pnpm install --offline` done. Scratch clone `<scratchpad>/replay` (origin
removed) exists for historical replays. Next: guardrail-only probes in the worktree (one at a
time, `git -C wt checkout -- .` between), then config-precedence probes (ruff.toml,
mypy.ini, nested .eslintrc, vitest.config.ts), then one combined SKIP_PROD_BUNDLE=1 gate.
Write findings into `../../07-agent-pipeline.md` as each is verified.

## Working findings so far (resume context; evidence files are beside this one)

Prior register, first read:
- PIPE-01 not fixed. settings.local.json mtime 30 Jul. Structure only, no values copied:
  47 allow rules incl. `Bash(*)`, `Edit`, `Write`, `mcp__supabase__execute_sql`,
  `list_tables`, `get_project_url`, `search_docs`; `rm -rf` rules for other repos and
  `~/Library/Caches/*`; `enableAllProjectMcpServers: true`, `enabledMcpjsonServers:
  ["supabase"]`. `.mcp.json` (gitignored, mtime 22 Jun) binds Supabase to a ref that is
  neither the staging ref (.codex/config.toml) nor production (STATUS), no `read_only`
  (checked by equality, ref never printed). This review session's deferred tool list
  offered the whole Supabase MCP family (execute_sql, apply_migration, delete_branch,
  merge_branch, deploy_edge_function) — live today. Never called.
- PIPE-02 text held; but the hook fires only on a CLEAN non-main branch — in the automatic
  flow the diff is uncommitted until close-out step 4, so it is silent at the decision
  point, and it fires on any clean non-main branch (e.g. this review branch). Rehearse.
- PIPE-03 reads right (strict port, readiness line + HTTP probe). Rehearse.
- PIPE-04 partial: counts ratcheted; skip/xfail/.only caught via counts. Expected not
  caught (prove): in-place loosened assert, type: ignore, eslint-disable, swap a test for a
  trivial one, `.todo`, conftest deselection masked by an added test, unconstrained ratchet
  raise. SELF-REFERENCE: ci-local.sh runs the working-tree guardrail; the approval table is
  inside the guardrail; a branch can approve itself (Batch 153 eabe49d did, with owner
  approval). Script checks only that the row is open, not that approval is recorded.
- PIPE-05 partial: drift before push + API+web refusal exist. Gaps: drift exit 1 is only
  reported (web-only batch needing an undeployed route passes); a split across two
  consecutive batches defeats the per-batch refusal.
- PIPE-06: AGENTS.md "520 Postgres-backed", "780 passed, 520 skipped" at 1,300;
  phase-closeout.md + batch-verify.md repeat 780/520; ratchet 1,350. AGENTS.md says
  "step 8's push"/"Step 8 pushes main" — push is step 9 since Batch 152.

Agents' behaviour, 2ce6f42..main:
- classify-output.txt: 7 API+web batches by the guard's rules — 123 37c6e40, 124 da8a13d,
  143 5c02dcd, 156 46b8d29, 157 e8b5fe4, 136 baae8ed, 148 c5be640. Check how each passed.
- Gate edited outside batches: fix/deterministic-delivery-gates d1b9ee9,
  fix/preview-readiness-signal 7ef953d, fix/preview-readiness-ansi 89217f8 (22 Sep) edit
  protected run-prod-bundle-smoke.sh; branch names not batch-N → guardrail refuses → gate
  could not be green there. No session-log entry, no row, no commit body. Replay in clone.
- CI red unread (gh-*.txt): six consecutive red main pushes 22 Sep (c7a50bb 152 close-out,
  a689a57 120, 48b6627 121, 0ff3e8c 122, d1b9ee9, 7ef953d; prod-bundle job) — 120-122
  deployed on red CI. Flaky reds: test_durable_rate_limit::test_an_unknown_name_is_charged_
  even_though_the_handler_commits_nothing (401 vs 429, ac54a71) and test_scheduler_jobs::
  test_home_and_the_coupon_pick_the_same_round_in_every_state (uq_leagues_join_code,
  bf97763). Unrecorded anywhere; tests untouched since. phase-closeout: "Do not poll CI".
- Scan: no new skip/xfail/.only/.todo in tests (pytestmark skipif-no-DB is standard; gate
  refuses skips). Product suppressions: 37c6e40 `# type: ignore[assignment]` on `= None`
  dependency default in routers/auth.py + eslint-disable exhaustive-deps AuthContext.tsx;
  7e37b9b eslint-disable exhaustive-deps useSlidingIndicator.ts. Judge them.
- Reviewed: 139 7d0e56b spec'd change, reported, fine. 161 39b299f inverted 201→429 on
  purpose, reported in body; +10 parametrised tautologies (`bounded=min(x,cap); assert
  bounded<=cap`) = count padding. 99b5fc9 dated tripwire remeasured (intended). 115
  828f42d DB-read round shape + floor (in review). Still to read: 157 e8b5fe4, 155 ca62213,
  150 afea45f, 164 7e37b9b, 4121cf0 (-1 assert), 83facaf (e2e), 137 8ed2740.
- 131 8eff2bb oracle change reported + quoted — held. 2f7d742 honest; misattributes
  `_future_window` to Batch 112 (came from d1b9ee9).
- 9a1467e: Batch 144's ratchet raise sits in the close-out docs commit, not the batch
  commit (batch commit alone fails its own gate; step 8 says stage three docs only).
- Orphaned follow-ups: Batch 138 → UX-18 `opacity-60` payout (PickRow.tsx:238 `lost &&
  'opacity-60'`), "no batch row"; Batch 131 → void-only win-rate copy PlayerProfilePage.tsx:100.
  No rows; no open rows.
- 25 "23 Sep" ticks match 25 close-out commits dated 23 Sep. 23 Sep 01:04-03:41: ten
  batches at 12-28 min intervals each claiming a full gate (11-13 min) — tight, not proof.

Added 29 Sep 08:40-08:50 (verified):
- replay_guards.sh + replay-guards-output.txt: the guards as they existed at each commit,
  in a push-less clone, drift stubbed. Guardrail REFUSES d1b9ee9, 7ef953d, 89217f8 (so no
  green gate on those branches). Close-out guard REFUSES all 7 API+web batches (123, 124,
  143, 156, 157, 136, 148). Only 136 and 148 record owner scheduling; 123/124/143/156/157
  have no durable record of how the refusal was cleared. All other commits pass both.
- 29 commits carry no agent trailer (152, 120-122, the three gate fixes, 115, walk fix,
  83facaf, Group Z 151/140/168/150/149 + toast fix) — a second agent toolchain; unrecorded.
- CI (.github/workflows/ci.yml) runs no guardrail, no ratchet, no zero-skip check; only
  pushes to main ever trigger it (close-out never pushes branches). main is unprotected
  (gh api .../branches/main/protection → 404; rulesets []). Repo is PUBLIC.
- coupon-flow.spec.ts (the only full register→pick→settle journey) is in neither the gate
  nor CI (playwright.prod-bundle.config.ts matches prod-bundle*.spec.ts only). It rotted
  from 23 Sep (Batch 139 opened first group: pick-card count 0 → 1; Batch 157 removed the
  "Averaged over" text) until 83facaf on 28 Sep, an out-of-batch fix.
- Batch 149 closed out and pushed before its seeded browser run; that run found the toast
  offset/contrast defect; 4121cf0 fixed it ~23 min later ("post-close-out correction").
- Batch 149's gate: second full frontend run "timed out in two unrelated existing tests",
  third passed — unnamed flakes, rerun to green.
- Batch 140 changed an e2e expectation Alice→Bob (the batch's own new assertion; reported).
- Batch 115 doubled browse TTLs (2h/1h/30m → 4h/2h/1h) — owner-approved in the row; fine.
- .github/workflows/claude.yml: dormant @claude/auto-fix agent with contents: write, fed by
  issue text in a public repo; references a prod-monitor workflow that does not exist;
  `gh secret list` shows no secrets; all runs "skipped". LOW/INFO.
- apps/api/pyproject.toml [project] deps list fastapi 0.111.0 / starlette 0.37.2 while the
  gate runs 0.141.1 / 1.6.0 — stale metadata. INFO.
- check-closeout-safety.sh pattern `vercel.json` (root) is dead — file is apps/web/vercel.json
  (still covered by apps/web/*). check-deploy-drift.sh hardcodes ROOT and its tier-3 probe
  is "Batch 51". INFO.

Added 29 Sep 14:30 (verified, gate-probes-output.txt, self-approval-output.txt):
- Guardrail catches: ratchet lowered (G03), pyproject ruff/mypy (G07/G08), .eslintrc.cjs
  (G09), tsconfig (G10), ci-local.sh (G11), phase-closeout.md (G13), closeout guard (G21).
- Guardrail passes (by design or gap): skip/xfail (G01/G02 — left to the count step),
  loosened assert (G04), type: ignore in src (G05), eslint-disable (G06), ratchet raised
  (G14 — count step's exact match catches), NEW ruff.toml / mypy.ini / src/.eslintrc.json /
  vitest.config.ts / pytest.ini / .eslintignore (G15-G19, G22), conftest.py pyfunc hook
  (G20), check-migration-recovery.sh (G23), AGENTS.md + batch-start.md (G24).
- G12: prepend `exit 0` to the guardrail → rc 0, prints nothing: the gate runs the branch's
  own copy.
- Self-approval (clone, feat/batch-999-probe, open row): adding a `999)` line approving
  ci-local.sh + the guardrail → rc 0 and prints "Batch 999's owner-approved gate
  maintenance changes". Control with the row ticked → rc 1.
Next: tool-behaviour checks for the precedence files (ruff.toml, mypy.ini, nested eslintrc,
vitest.config.ts, conftest hook), then the combined SKIP_PROD_BUNDLE=1 gate.

Added 29 Sep 14:40 (verified, precedence-probes-output.txt): unprotected files change the
gate's tools. mypy.ini (ignore_errors) → a real type error passes; src/.eslintrc.json → an
explicit-any error passes; ruff.toml (line-length 100, select E) → an F841 passes;
vitest.config.ts replaces vite.config.ts; a 3-line conftest.py hook turns "1 failed, 9
passed" into "10 passed" with the count unchanged.
Next: write the lens document skeleton + verified findings, then the combined gate.

Added 29 Sep 14:50: combined gate running in background (notes/combined-gate-output.txt,
started 14:22). Cold start measured: next-batch-prompt reads STATUS 6,377 + BUILD_PLAN head
18,828 (of which the 7 ticked "Open batches" rows are 14,733) + last session-log section
2,191 + command 1,401 + AGENTS.md 9,259 = ~38 KB (~9.6k tokens). BUILD_PLAN 287→353 KB,
session-log 271→541 KB since 2ce6f42. Hook rehearsal (hook-rehearsal.txt): silent on a dirty
batch tree. Lens doc skeleton written (Method done). Contradictions found: batch-verify.md
tells agents to run pytest with the app-starter venv that AGENTS.md says cannot collect the
suite; AGENTS.md + agent-commands/README say `/group-start <I-Y>` (Z exists); phase-closeout
"For Batch 6" fossil; ci-local.sh header says it runs what CI runs (CI runs less); STATUS
ratchet twice; STATUS "no open batches" vs BUILD_PLAN "Open batches" with 7 ticked rows;
STATUS web last-verified b08a47f3 (lead saw 4121cf0 live); drift probe "Batch 51".

Added 29 Sep 15:00 (verified): PIPE-08 held — every proper-noun token Batch 155 removed has
0 hits on main (hashed, never printed; one dictionary-word hit was "Tooling"). PIPE-09 held
(pnpm-pin-rehearsal.txt: 9.14.2 shim refused, rc 1). Two-batch split
(two-batch-split-output.txt): web-only batch over owed drift → "PASS — web-only", rc 0.
Next: wait for combined gate; then revert worktree, hook clean-branch rehearsal, PIPE-03
rehearsal on an alternative port, no-DB pytest split for doc corrections; write the doc.
