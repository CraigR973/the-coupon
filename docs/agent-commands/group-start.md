---
description: Implement a documented Coupon batch group without collapsing its batch or deployment boundaries.
---

# /group-start

`$ARGUMENTS` must be one group letter from **I** through **M**, as documented in
`docs/review/2026-08-26/07-sequencing.md`, or **N** through **Y**, as documented in
`docs/review/2026-09-13/08-sequencing.md`. Treat the letter case-insensitively.

For an N-Y group, read the model and effort it runs at from
`docs/review/2026-09-13/09-prompts.md` — a group runs at the **strictest setting any
of its batches asks for**, and that value is derived from the per-batch table there,
never typed independently.

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
| N | 120 → 121 → 122 → **stop for `/ship-prod`** |
| O | 123 → 124 → 125 → 126 → **stop for `/ship-prod`** |
| P | 127 → 128 → 129 → **stop for `/ship-prod`** |
| Q | 130 → 131 → 132 → 133 → **stop for `/ship-prod`** |
| R | 134 → 135 → 136 → **stop for `/ship-prod`** |
| S | 137 → 138 → 139 → 140 |
| T | 141 → 142 → 143 → **stop for `/ship-prod`** |
| U | 144 → 145 → 146 → **stop for `/ship-prod`** |
| V | 147 → 148 → **stop for `/ship-prod`** |
| W | 149 → 150 → 151 |
| X | 152 → 153 → 154 → 155 |
| Y | 158 → 159 → 160 → 161 → 162 → **stop for `/ship-prod`** → 163 → 164 → 165 → 166 → 167 → 168 |

Groups S and W are web-only and carry no shipment. Group X deploys nothing at
all. **Batch 95 is deliberately in no group**: it stays blocked on the
storage-egress attribution, which is an owner action.

**The nine-phase run order in `docs/review/2026-09-13/09-prompts.md` supersedes
these letters for sequencing.** Several phases take only part of a group — the
gate repair takes 152 alone out of X, for instance — and are run as a sequence
of `/batch-start` calls. The letters remain the thematic grouping and are what
this command accepts.

1. Validate the argument against that manifest. Find and read the exact group
   section in `docs/review/2026-08-26/07-sequencing.md` (groups I-M) or
   `docs/review/2026-09-13/08-sequencing.md` (groups N-Y), then read every batch
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
