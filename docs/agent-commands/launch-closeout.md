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
4. Integrate using the repository mode explicitly documented during `L0`:
   - if the repository remains local-only, fast-forward local `main`;
   - if a PR/CI workflow is documented, follow that exact workflow;
   - if integration mode is absent or ambiguous, stop and ask the owner.

   Never force-push, bypass required CI, or invent a remote workflow.
5. On the integrated `main`, update only the matching phase status row in
   `docs/LAUNCH_PLAN.md`:
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

8. Report the integrated implementation commit, close-out commit, verification
   evidence, current branch, and next open launch phase.

## Boundaries

- Close-out records completed work; it does not provision, deploy, seed, alter
  DNS, send invites, run a live Betfair probe, or perform phase implementation.
- Do not update `docs/BUILD_PLAN.md` or `session-log.md`; the six build batches
  are already closed.
- Do not push merely because `origin` exists. Push or PR actions must be part of
  the documented integration mode and this explicit close-out invocation.
- Never log into the owner's live Betfair account.
