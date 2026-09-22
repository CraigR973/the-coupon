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
   scheduler; step 9 below pushes `main`, and Vercel deploys the web app from it, so a
   batch can reach members without the core of the game having run. Record the
   backend and frontend test counts printed by the gate; the close-out report and
   session-log entry must name both counts, not merely say "green". For Batch 6
   this also includes browser screenshots.
3. Before any commit, merge, or push, run the close-out safety guard on the
   feature branch:

   ```bash
   /Users/craigrobinson/the-coupon/scripts/check-closeout-safety.sh N
   ```

   This runs the deployment-drift check while the web app is still untouched,
   classifies the batch's own diff, and refuses an API+web batch because the push
   would release its web half first. Stop and ask the owner to schedule the
   matching `/ship-prod`. Only after that explicit instruction, rerun the guard
   with the acknowledgement below; never infer or add it yourself:

   ```bash
   /Users/craigrobinson/the-coupon/scripts/check-closeout-safety.sh N --shipment-scheduled
   ```

   API-only batches may continue and report that `/ship-prod` will be owed;
   web-only and tooling/documentation batches add no API shipment. Existing
   drift or an inconclusive live check must be reported even when this batch is
   not split-half.
4. Stage only the batch's explicit files and create a Conventional Commit.
5. Capture the feature branch and commit SHA, then fast-forward local `main`:

   ```bash
   git -C /Users/craigrobinson/the-coupon checkout main
   git -C /Users/craigrobinson/the-coupon merge --ff-only <feature-branch>
   ```

   Stop on any failure; never force.
6. Invoke `/strike-batch N`.
7. Append one lean `session-log.md` section:

   ```text
   ## Batch N — Title
   **Commits:** <hashes> · verified: <green gates; backend and frontend test counts>

   ### Key facts for future sessions
   - <only non-obvious facts, at most six bullets>

   **Next:** <first unchecked batch, or launch planning>
   ```

8. Refresh `STATUS.md`, stage only the three close-out documents, and commit:
   `docs: close out Batch N — tick BUILD_PLAN + session log`.
9. Push local `main` to `origin`:

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

10. Report the pre-push drift result from step 3, the batch's API/web
    classification, and whether `/ship-prod` is owed or explicitly scheduled.
    Do not rerun the first drift check only after the deploy: that is too late to
    protect members. Pushing `main` auto-deploys the **web app** through Vercel's
    GitHub integration, but the **API** moves only when `/ship-prod` runs. Do not
    deploy here.

Do not poll CI or deploy — those remain separate, explicit actions.
