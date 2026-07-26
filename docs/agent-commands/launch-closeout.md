---
description: Explicitly close one verified Coupon launch phase.
---

# /launch-closeout

This workflow runs only when the user explicitly invokes
`/launch-closeout <L0-L5>`.

`$ARGUMENTS` must be exactly one unchecked launch phase ID from `L0` through
`L5` in `docs/LAUNCH_PLAN.md`.

1. Confirm:
   - the current branch is the canonical branch from `/launch-start`;
   - the worktree contains only the intended phase changes;
   - every earlier launch phase is checked;
   - the requested phase is unchecked;
   - every direct task checkbox in the requested phase is checked;
   - every cross-section blocker incorporated by that phase is resolved;
   - `/launch-verify $ARGUMENTS` is GREEN for the current branch state;
   - every required owner-only check has explicit owner confirmation.

   Stop on missing or stale evidence. Do not weaken the gate to make close-out
   pass.
2. Stage only the phase's explicit implementation, configuration, test,
   runbook, and evidence files. Review the staged diff and create an appropriate
   Conventional Commit.
3. Capture the feature branch and commit SHA.
4. Read the repository mode explicitly documented during `L0`. If it is absent
   or ambiguous, stop and ask the owner.
5. In the branch that the documented mode will integrate, update only the
   matching phase status row in `docs/LAUNCH_PLAN.md`:
   - change `- [ ]` to `- [x]`;
   - append ` ✅ <today UTC YYYY-MM-DD>` immediately after the bold phase title.
6. Append one lean section to `launch-log.md`:

   ```text
   ## Lx — Title
   **Commits:** <hashes> · verified: <green phase gates>

   ### Key facts for future sessions
   - <only non-obvious facts, at most six bullets>

   **Next:** <next open launch phase, or post-launch operations>
   ```

   Never include secrets, PINs, tokens, private URLs containing credentials,
   certificate material, or real member personal data.
7. Refresh `STATUS.md`. Stage only `docs/LAUNCH_PLAN.md`, `launch-log.md`, and
   `STATUS.md`, then commit:

   ```text
   docs(launch): close out Lx — <short title>
   ```

8. Integrate using the documented mode:

   - **Local fast-forward:** switch to local `main`, require it to be the
     recorded phase base with no unexpected commits, and fast-forward it to the
     phase branch.
   - **Remote PR/required CI:** keep both commits on the phase branch, push that
     branch, open a pull request into `main`, wait for every documented required
     check, and merge only when all are green. Then fast-forward local `main` to
     the merged remote `main`.
   - **Empty-remote L0 bootstrap:** before pushing the phase branch, re-confirm
     that `origin` is the documented repository, its visibility matches the
     owner decision, and it has no refs. Push the unchanged pre-L0 local `main`
     as remote `main`, wait for its documented CI checks, then continue with the
     remote PR path. Never push the L0 implementation directly to `main`.

   Never force-push, bypass required CI, or invent a remote workflow. If a push,
   check, or merge fails, report the partial external state and do not claim the
   phase is closed.
9. Report the integrated implementation commit, close-out commit, pull request
   when applicable, verification evidence, current branch, and next open launch
   phase.

## Boundaries

- Close-out records completed work; it does not provision, deploy, seed, alter
  DNS, send invites, run a live Betfair probe, or perform phase implementation.
- Do not update `docs/BUILD_PLAN.md` or `session-log.md`; the six build batches
  are already closed.
- Do not push merely because `origin` exists. Push or PR actions must be part of
  the documented integration mode and this explicit close-out invocation.
- Never log into the owner's live Betfair account.
