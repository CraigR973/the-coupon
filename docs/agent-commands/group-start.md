---
description: Implement a documented Coupon batch group without collapsing its batch or deployment boundaries.
---

# /group-start

`$ARGUMENTS` must be one group letter from **I** through **M**, as documented in
`docs/review/2026-08-26/07-sequencing.md`. Treat the letter case-insensitively.

This command is an orchestrator. It does not change `/batch-start`, automatic
batch close-out, or `/ship-prod`: every batch still gets its own branch, full
gate, commits, checklist tick, log entry and push; production API deployment is
still an explicit owner action.

The current manifest is:

| group | ordered batches and checkpoints |
| --- | --- |
| I | 103 |
| J | 104 → **stop for `/ship-prod`** |
| K | 105 → 106 |
| L | 107 → **stop for `/ship-prod`** → 108 |
| M | 109 → 110 → **stop for `/ship-prod`** → 111 |

1. Validate the argument against that manifest. Find and read the exact group
   section in `docs/review/2026-08-26/07-sequencing.md`, then read every batch
   row and its verification and scope boundary in `docs/BUILD_PLAN.md`. Also
   read `STATUS.md` and the relevant recent entries in `session-log.md` before
   deciding where the group resumes.

2. Require a clean worktree on local `main` before deriving progress, checking
   drift, or starting a batch:

   ```bash
   git -C /Users/craigrobinson/the-coupon status --porcelain
   git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD
   ```

   Stop rather than stashing, discarding or absorbing unrelated changes.

3. Derive progress from checked batch rows, but never infer that an API shipment
   happened from a checkbox. Checked batches are resumable progress, not an
   error. If a later batch in the group is checked while an earlier one is not,
   stop and report the invalid, out-of-order state.

4. At a deployment checkpoint whose preceding batch is checked, run:

   ```bash
   /Users/craigrobinson/the-coupon/scripts/check-deploy-drift.sh
   ```

   Continue past the checkpoint only when it exits zero and reports the API in
   sync. Otherwise stop and ask the user to invoke `/ship-prod`; do not invoke,
   emulate, or bypass that command. This applies at the end of Group J too: the
   first run closes Batch 104 and pauses, while a post-shipment rerun confirms
   Group J complete.

5. Before each unchecked batch that lies before the next checkpoint, require a
   clean worktree on local `main` and confirm every dependency stated in its
   source row is satisfied. Then follow
   `docs/agent-commands/batch-start.md` for **that one batch only**. It must use
   its own `feat/batch-N-<slug>` branch, run the complete `scripts/ci-local.sh`
   gate, and perform the existing automatic `/phase-closeout N` workflow when
   green.

6. Continue to the next batch in the same invocation only after close-out has
   returned to clean local `main`, the source row is checked, and its push
   succeeded. Never put two group batches on one feature branch or in one batch
   commit, and never skip an unchecked batch.

7. Stop the group immediately on the same conditions that stop `/batch-start`
   or `/phase-closeout`: an unrelated dirty worktree, a gate failure that cannot
   be fixed in scope, three exhausted attempts, a pre-existing red on `main`, a
   close-out or push failure, scope spill, or an invalid checklist state. Report
   the completed batches and the exact resume point.

8. When a group with no deployment checkpoint is fully checked, run
   `scripts/check-deploy-drift.sh` and report whether any unrelated API shipment
   remains owed. Do not deploy it. When a checkpointed group is fully checked,
   report completion only after its checkpoint has been verified in sync.

The command grants authority to implement and close out the documented batches
in the selected group. It grants no authority to deploy Railway or to modify the
contents, order, dependencies, or scope boundaries of the group.
