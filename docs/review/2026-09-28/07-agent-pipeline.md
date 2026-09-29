# 07 — Agent delivery pipeline

The application ships no LLM features, so this lens points at what does use AI: **agents
build this repository, and a green batch closes out automatically, including the push to
`main` that Vercel deploys to members.** Batches 120-168, 95 and 115 — 130 commits since
`2ce6f42` — all went out that way. This pass audited what the agents *did*, not only the
rules they were given.

**The short version.** The agents behaved well: across 55 code commits there is no new
skip, xfail or `.only`, every changed test expectation was specified by its row and
reported, and the one oracle change (Batch 131) stopped for the owner as the run order said
it would. The machinery around them is weaker than it looks. The gate judges each batch
with **that batch's own copy of the gate**, so it can be switched off from inside the
branch; it was changed three times on its first day on branches the guardrail refuses; CI
went red eight times in a week and nothing reads it; and the one end-to-end journey is
outside the gate and rotted for five days.

## Method

Everything below was run on 28-29 Sep 2026 against `main` at `eb18bcb`, which production
serves (web and API in sync per the lead's drift check), so every finding is **live**.

- **What the agents did.** Every commit since `2ce6f42` was listed with the main-branch
  reflog (which records the branch each merge came from), classified API / web / tooling
  with the close-out guard's own path rules, and scanned hunk by hunk for skip, xfail,
  `.only`, `.todo`, `type: ignore`, `eslint-disable`, `noqa`, removed test functions,
  removed or changed assertions and ratchet changes. Every hit was read by hand.
- **The guards, replayed.** In a push-less scratch clone, for each of the 55 non-docs
  commits, local `main` was set to its parent and the guardrail and close-out guard were run
  **as they existed at that commit** (the drift check stubbed, since the real one calls
  production).
- **The gate, attacked.** In a throwaway worktree (`throwaway/pipeline-probe`, never
  pushed): 24 single weakenings against the guardrail, five checks that unprotected config
  files change what ruff, mypy, eslint, vitest and pytest enforce, a self-approval probe on
  a batch-named branch (in the clone, to keep `feat/batch-*` refs out of the shared
  repository), and one full `SKIP_PROD_BUNDLE=1` gate over six simultaneous weakenings.
- **CI.** Read-only `gh run list` / `gh run view` for every run since 20 Sep; branch
  protection and rulesets read through `gh api`.
- **Documents.** Byte counts of exactly what `/next-batch-prompt`, `/batch-start` and
  `/group-start` instruct an agent to read; a contradiction sweep across `AGENTS.md`,
  `CLAUDE.md`, `docs/agent-commands/*`, `.claude/`, `.codex/`, `ci-local.sh`, `STATUS.md`
  and the head of `docs/BUILD_PLAN.md`.
- The local agent configuration was read for **structure only**; no value, key or project
  reference was copied.

Scripts and raw output: `notes/07-pipeline/` (`replay_guards.sh`, `gate_probes.sh`,
`precedence_probes.sh`, `self_approval_probe.sh`, `combined_weakening.py`,
`scan_test_diffs.py`, and a `*-output.txt` beside each).

## Prior findings

| id | batch | status | evidence |
| --- | --- | --- | --- |
| PIPE-01 | owner, by hand | **not fixed** | `.claude/settings.local.json` unchanged since 30 Jul: `Bash(*)`, `mcp__supabase__execute_sql` allowed, `rm -rf` rules for other repositories, `enableAllProjectMcpServers: true`. `.mcp.json` binds the Supabase server to a project that is neither the staging project in `.codex/config.toml` nor production, with no read-only flag (compared by equality, never printed). **Driven:** this review's own session was offered the whole Supabase tool family — `execute_sql`, `apply_migration`, `delete_branch`, `merge_branch`, `deploy_edge_function` — and did not call it |
| PIPE-02 | 153 | **partial** | Both hooks now say close out automatically (identical commands, `.claude/settings.json` = `.codex/hooks.json`). Re-driven in the worktree: the hook is **silent on a dirty batch tree**, which is the state at the close-out decision (the diff is uncommitted until close-out step 4), and speaks on any clean non-main branch — including a review branch with no batch. See PIPE-17 |
| PIPE-03 | 152 | PENDING | |
| PIPE-04 | 152 | **partial** | Counts are recorded and ratcheted, and a fall, a skip or an xfail fails the gate; lowering the ratchet is refused (probe G03). But a loosened assertion, a swapped-in trivial test, `type: ignore`, `eslint-disable`, `.todo`, and five unprotected config files all pass — and the guardrail can be switched off from the branch. See PIPE-10 |
| PIPE-05 | 152 | **partial** | Replayed: the guard as it stood refuses all seven API+web batches (123, 124, 143, 156, 157, 136, 148) and passes the other 48. Drift now runs before the push. But existing drift is only reported: a web-only batch over an owed `/ship-prod` passes (probe). See PIPE-14 |
| PIPE-06 | 153 | **partial** | Figures now carry dates, as the fix asked; they have drifted again — "780 passed, 520 skipped" at 1,300 tests in `AGENTS.md`, `batch-verify.md` and `phase-closeout.md` against a ratchet of 1,350 — and `AGENTS.md` still sends agents to "step 8's push", which is step 9 since Batch 152 inserted the safety step. PENDING-NODB |
| PIPE-07 | 154 | **held**, with a leak | `/next-batch-prompt` reads **38.3 KB** today (Batch 154 said 38 KB). But 14.7 KB of the 18.8 KB build-plan head is seven *ticked* rows, because nothing moves a row out when it closes. See PIPE-18 |
| PIPE-08 | 155 | **held** | Every proper-noun token Batch 155 removed has **zero** hits on `main` (checked by hashing, never printed). History was not rewritten, per the owner's decision |
| PIPE-09 | 127 | **held** | `ci-local.sh`'s pnpm check evaluated verbatim with a pnpm 9.14.2 shim first on `PATH`: refused, exit 1, "package.json pins '9.15.0'" |

**Tally: 3 held, 5 partial, 1 not fixed, 0 regressed.** PENDING-TALLY

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PIPE-10 | MED | live | verified | The gate is judged by the branch's own copy of the gate, and five unprotected config files switch its checks off |
| PIPE-11 | MED | live | verified | The protected smoke script was changed three times on branches the guardrail refuses, with no record |
| PIPE-12 | MED | live | verified | CI went red eight times in a week, three batches deployed on red, and nothing reads it |
| PIPE-13 | MED | live | verified | The only end-to-end journey is outside the gate; it rotted for five days and one batch deployed before running it |
| PIPE-14 | MED | live | verified | The split-half refusal is cleared by a flag with no durable record, and a two-batch split passes it |
| PIPE-15 | LOW | live | verified | Follow-ups agents record in the session log become nobody's work |
| PIPE-16 | LOW | live | verified | The ratchet counts tests, not what they check — and one batch padded it with tautologies |
| PIPE-17 | LOW | live | verified | The stop hook is silent at the close-out decision and speaks on branches with no batch |
| PIPE-18 | LOW | live | verified | Closed rows stay in the build plan's "Open batches" head, which is 78% closed rows |
| PIPE-19 | INFO | live | verified | Dormant or stale agent machinery: an issue-driven workflow, stale metadata, an orphaned worktree |

PENDING-SECTIONS
