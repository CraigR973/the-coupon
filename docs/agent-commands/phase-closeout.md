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
8. Push local `main` to `origin`:

   ```bash
   git -C /Users/craigrobinson/the-coupon push origin main
   ```

   This must be a plain (non-force) push of `main` only — never push the
   feature branch, never force-push, never push any other branch. Stop and
   report if the push is rejected (e.g. `origin/main` has diverged); never
   force past a rejection.

9. Report the deployed-API gap, without acting on it:

   ```bash
   /Users/craigrobinson/the-coupon/scripts/check-deploy-drift.sh
   ```

   Pushing `main` auto-deploys the **web app** through Vercel's GitHub
   integration, but the **API** only moves when `/ship-prod` runs. Nothing else
   surfaces that gap, and it is invisible from the browser until a batch changes
   a field both sides read: Batches 8–21 shipped frontend-only that way, and the
   Coupon tab broke on 2026-08-06 because Batch 14 renamed the slate's date
   field and only the web half reached production. Print the result and say
   whether a `/ship-prod` is owed. Do not deploy here.

Do not poll CI or deploy — those remain separate, explicit actions.
