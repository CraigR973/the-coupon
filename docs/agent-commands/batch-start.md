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
   those. Fix failures and rerun until everything is green. Report every
   command and result.

6. Report the branch, source row, implementation summary, and verification
   results. Do not commit, merge, or tick the checklist — close-out remains a
   separate action, run only via `/phase-closeout N`.

Do not fetch, pull, push, or assume a remote exists.
