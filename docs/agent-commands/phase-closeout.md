---
description: Close a verified Coupon batch on local main.
---

# /phase-closeout

`$ARGUMENTS` must be a numeric batch present in `docs/BUILD_PLAN.md`.

This workflow runs **automatically** once `/batch-start <N>` has finished and the
full `scripts/ci-local.sh` gate is green (owner decision, 2026-08-27; see
`AGENTS.md`). It can still be invoked directly as `/phase-closeout <N>`. Do not
run it — stop and report instead — if the gate is red, if the worktree holds
changes beyond the batch, or if the batch row is already ticked.

1. Confirm the batch row is unchecked, the current branch matches
   `feat/*`, `fix/*`, or `chore/*`, and the worktree contains only the intended
   batch changes.
2. Run or confirm the complete `/batch-verify N` gate — which means
   `scripts/ci-local.sh`, not pytest on its own. Without a database that suite is
   `509 passed, 151 skipped` and the skips are the pick flow, settlement and the
   scheduler; step 8 below pushes `main`, and Vercel deploys the web app from it, so a
   batch can reach members without the core of the game having run. For Batch 6 this also
   includes browser screenshots.
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

   **This push deploys.** Vercel builds and releases the web app from `main` on every
   push, so the frontend half of the batch reaches members within a few minutes and
   before CI has necessarily reported. The API half does not move until `/ship-prod`.
   Nothing here waits for either, which is why step 2 has to be the real gate.

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
