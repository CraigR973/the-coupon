---
description: Start a numbered Coupon batch, implement it, and verify it.
---

# /batch-start

`$ARGUMENTS` must be one batch number from `docs/BUILD_PLAN.md`.

1. Find the exact row:

   ```bash
   grep -nE "^- \[[ x]\] \*\*Batch $ARGUMENTS " /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```

   Stop if it does not exist or is already checked. Read the full row (it may
   wrap across multiple lines) and any Verification section it references.

2. Require a clean worktree and local `main`:

   ```bash
   git -C /Users/craigrobinson/the-coupon status --porcelain
   git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD
   ```

3. Derive a short lowercase slug from the row title and create
   `feat/batch-$ARGUMENTS-<slug>`:

   ```bash
   git -C /Users/craigrobinson/the-coupon checkout -b feat/batch-N-short-slug
   ```

4. Implement the batch on this branch: make the code changes described by the
   row, plus any tests the Verification section calls for. Stay scoped to
   this batch only — do not fold in unrelated cleanup or later batches.

5. Run the same checks `/batch-verify $ARGUMENTS` would run (see
   `docs/agent-commands/batch-verify.md`): backend ruff/mypy/pytest, frontend
   lint/typecheck/build/test, and DB or browser checks if the batch touches
   those. Report every command and result.

   Fix failures and rerun the whole gate until green, up to **three attempts at
   the same failing check** — but follow `AGENTS.md`'s "A red gate: fix it, but
   only in one direction" first. In short: fix what this batch broke; reset the
   environment when it is the reused-cluster `test_seeds` artifact; **stop and
   report** on a pre-existing red on `main` (it gets its own `fix/` branch) or
   when the fix would breach this batch's scope boundary. Never reach green by
   deleting, skipping, loosening or `xfail`-ing a check.

6. Report the branch, source row, implementation summary, verification results,
   and **every gate failure and how it was fixed** — including ones fixed first
   try. Close-out deploys, so this is the only record of what went wrong.

7. If the gate is fully green, continue straight into
   `docs/agent-commands/phase-closeout.md` for this batch — build-batch close-out
   is automatic (owner decision, 2026-08-27; see `AGENTS.md`). Stop after step 6
   and report instead if the three attempts are exhausted, the failure is not
   this batch's to fix, or the worktree holds changes beyond this batch.

Do not fetch, pull, or assume a remote exists. (Close-out's own step 8 pushes;
nothing in this workflow does.)
