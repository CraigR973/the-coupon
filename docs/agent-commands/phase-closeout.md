---
description: Close a verified Coupon batch on local main.
---

# /phase-closeout

This workflow runs only when the user explicitly invokes
`/phase-closeout <N>`. `$ARGUMENTS` must be a numeric batch present in
`docs/BUILD_PLAN.md`.

1. Confirm the batch row is unchecked, the current branch matches
   `feat/*`, `fix/*`, or `chore/*`, and the worktree contains only the intended
   batch changes.
2. Run or confirm the complete `/batch-verify N` gate. For Batch 6 this includes
   clean scratch-database migration and browser screenshots.
3. Stage only the batch's explicit files and create a Conventional Commit.
4. Capture the feature branch and commit SHA, then fast-forward local `main`:

   ```bash
   git -C /Users/craigrobinson/the-coupon checkout main
   git -C /Users/craigrobinson/the-coupon merge --ff-only <feature-branch>
   ```

   Stop on any failure; never force.
5. Invoke `/strike-batch N`.
6. Append one lean `session-log.md` section:

   ```text
   ## Batch N — Title
   **Commits:** <hashes> · verified: <green gates>

   ### Key facts for future sessions
   - <only non-obvious facts, at most six bullets>

   **Next:** <first unchecked batch, or launch planning>
   ```

7. Refresh `STATUS.md`, stage only the three close-out documents, and commit:
   `docs: close out Batch N — tick BUILD_PLAN + session log`.

This repository is local-only. Do not push, poll CI, or deploy.
