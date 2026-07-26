---
description: Start a numbered Coupon batch on a clean feature branch.
---

# /batch-start

`$ARGUMENTS` must be one batch number from `docs/BUILD_PLAN.md`.

1. Find the exact row:

   ```bash
   grep -nE "^- \[[ x]\] \*\*Batch $ARGUMENTS " /Users/craigrobinson/the-coupon/docs/BUILD_PLAN.md
   ```

   Stop if it does not exist or is already checked.

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

4. Report the branch, source row, and reminder to run `/batch-verify N` and
   wait for `/phase-closeout N`.

Do not fetch, pull, push, or assume a remote exists.
