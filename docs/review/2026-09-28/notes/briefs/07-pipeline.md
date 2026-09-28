# Lens 07 — Agent delivery pipeline

Output: `docs/review/2026-09-28/07-agent-pipeline.md`. Notes: `docs/review/2026-09-28/notes/07-pipeline/`.
No ports. New finding ids start at **PIPE-10**.

The app ships no LLM features, so the AI-engineering lens points at what does use
AI: agents build this repo, and since 2026-08-27 a green batch closes out
automatically, including the push that Vercel deploys. **49 batches shipped since
the last review with no human review first**, so audit what the agents *did*, not
only the rules. Facts the lead verified from `docs/BUILD_PLAN.md` ticks: Batch 152
(the gate repair) closed 22 Sep; **25 batches carry a 23 Sep tick** (123-126,
128-133, 137-139, 141, 143-145, 147, 156, 157, 159-162, 167). Confirm against git
commit timestamps before you rely on it.

## Your slice of the 2026-09-13 register

| id | sev then | batch | check |
| --- | --- | --- | --- |
| PIPE-01 | HIGH | owner, by hand | `.claude/settings.local.json` (mtime 30 Jul per the lead's `ls`; STATUS says still unfixed on 24 Sep). Read it for **structure only** — which MCP servers, which allow rules — and never copy a value, token or key into your notes |
| PIPE-02 | MED | 153 | both stop hooks (`.claude/settings.json`, `.codex/hooks.json`) now agree with `AGENTS.md` |
| PIPE-03 | MED | 152 | the prod-bundle smoke fails loudly when port 4173 is held (read `scripts/run-prod-bundle-smoke.sh`; rehearse only in your worktree and only on a different port if the lead's gate might be running — check `lsof -i :4173` first) |
| PIPE-04 | MED | 152 | test counts recorded and ratcheted (`scripts/ci-test-counts.env`); gate/lint/type config edits refused (`scripts/assert-quality-guardrails.sh`) |
| PIPE-05 | MED | 152 | drift checked **before** the push; split-half batch refused (`scripts/check-closeout-safety.sh`, `docs/agent-commands/phase-closeout.md`) |
| PIPE-06 | MED | 153 | gate numbers in docs current and dated |
| PIPE-07 | MED | 154 | cold-start cost |
| PIPE-08 | MED | 155 | names out of the working tree |
| PIPE-09 | LOW | folded into 127 | pnpm pinned in the gate |

## What to do

1. **Sample the batch diffs for tests weakened alongside code.** For every batch
   since `2ce6f42` (use `git log --format` and the close-out commits), look for:
   loosened assertions, changed expected values, new `skip`/`xfail`/`.skip`/
   `.only`/`todo`, deleted test cases or files, `# type: ignore`,
   `eslint-disable`, `noqa`, lowered thresholds, and ratchet raises in
   `ci-test-counts.env` without a matching number of new tests (note: the web
   suite's `viewport.test.ts` adds one test per new `.tsx` file, so a raise can
   legitimately exceed the tests written). Batch 131 was *expected* to change an
   oracle test — check it was reported, as `AGENTS.md` requires. Batch 166 closed
   with no code change — check that is honest. Commit `fix: stop four
   round-population tests asserting on the day of the week` (23 Sep) deserves a
   close look. Record every suspicious hunk with its commit.
2. **Try to weaken the gate on a throwaway local branch, never pushed.** Use a
   separate worktree so the main tree is untouched:
   `git -C /Users/craigrobinson/the-coupon worktree add <scratchpad>/wt-pipeline -b throwaway/pipeline-probe main`.
   In it, try each weakening one at a time and run
   `scripts/assert-quality-guardrails.sh` (and the count logic, if you can
   exercise it cheaply): skip a backend test, `xfail` one, delete one and lower
   the ratchet, loosen an assertion in place, add `# type: ignore`, add an
   eslint-disable, relax a ruff/mypy/eslint/tsconfig setting, edit
   `ci-local.sh`, edit the guardrail script itself, edit `phase-closeout.md`,
   add a new approval line for an open batch in the guardrail. Record which are
   caught and which pass. If you run the full gate there, use
   `SKIP_PROD_BUNDLE=1` (port 4173 is the lead's) and run `pnpm install
   --frozen-lockfile --offline` in the worktree first. Remove the worktree and
   delete the throwaway branch when done (`git worktree remove`, `git branch -D`).
3. **What an automatic push can break before CI reports** — walk
   `docs/agent-commands/phase-closeout.md` and `batch-start.md` step by step;
   what reaches members, when, and what stops it. Check whether CI actually ran
   and passed on the pushed commits since 2ce6f42 if `gh` can tell you
   (read-only `gh run list`; do not trigger anything).
4. **Contradictions or stale facts** across `AGENTS.md`, `CLAUDE.md`,
   `docs/agent-commands/*`, `.claude/commands/*`, `.claude/settings.json`,
   `.codex/` (hooks and config), `scripts/ci-local.sh`, `STATUS.md`, and the
   head of `docs/BUILD_PLAN.md`. Examples to check, not assume: AGENTS.md says
   "520 Postgres-backed tests" and "780 passed, 520 skipped" at 1,300 tests
   while the ratchet is 1,350; STATUS.md's toolchain section repeats the ratchet
   twice; the "Open batches" heading holds seven ticked rows.
5. **Cold-start cost after Batch 154.** `docs/BUILD_PLAN.md` is 5,122 lines.
   Measure (bytes and an estimate of tokens) exactly what `/next-batch-prompt`,
   `/batch-start` and `/group-start` instruct an agent to read today, against
   Batch 154's "529 KB before, 38 KB after". Say whether closed rows should move
   out of the file, and what the `session-log.md` size now costs.
6. **Enforced by script vs only by prose** — rebuild the 2026-09-13 table
   (07-agent-pipeline.md there) against today's scripts.
7. **An AI product feature**: only if it solves a concrete member problem better
   than a non-AI fix. "None" is acceptable.
