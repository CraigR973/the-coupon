---
description: Implement a documented Coupon batch group without collapsing its batch or deployment boundaries.
---

# /group-start

`$ARGUMENTS` must be one group name: a letter from **I** through **M**, as documented
in `docs/review/2026-08-26/07-sequencing.md`; **N** through **Z**, as documented in
`docs/review/2026-09-13/08-sequencing.md`; or a double letter from **AA** through
**AH**, as documented in `docs/review/2026-09-28/08-sequencing.md`. Treat the name
case-insensitively.

For an N-Z group, read the model and effort it runs at from
`docs/review/2026-09-13/09-prompts.md`, and for an AA-AH group from
`docs/review/2026-09-28/09-prompts.md` — a group runs at the **strictest setting any
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
| S | 137 → 138 → 139 (140 moved to Z on 2026-09-27) |
| T | 141 → 142 → 143 → **stop for `/ship-prod`** |
| U | 144 → 145 → 146 → **stop for `/ship-prod`** |
| V | 147 → 148 → **stop for `/ship-prod`** |
| W | replaced by Z on 2026-09-27 — do not run |
| X | 152 → 153 → 154 → 155 |
| Y | 158 → 159 → 160 → 161 → 162 → **stop for `/ship-prod`** → 163 → 164 → 165 → 166 → 167 (168 moved to Z on 2026-09-27) |
| Z | 151 → 140 → 168 → 150 → 149 |
| AA | 172 → 173 → 174 → 170 (169 runs alone, before AG) |
| AB | 171 → 175 → 176 → 177 → 178 |
| AC | 180 → 179 → 181 → 182 → **stop for `/ship-prod`** |
| AD | 183 → 188 → **stop for `/ship-prod`** → 184 → 185 → 186 → 187 → **stop for `/ship-prod`** |
| AE | 189 → 190 → 191 → 192 → 193 → **stop for `/ship-prod`** |
| AF | 196 → 195 → 197 → **stop for `/ship-prod`** → 194 → **stop for `/ship-prod`** |
| AG | 198 → 200 → 199 → 201 → **stop for `/ship-prod`** |
| AH | 202 → 203 → **stop for `/ship-prod`** |

Groups S and Z are web-only and carry no shipment. Group X deploys nothing at
all. Group Z (owner, 2026-09-27) holds everything left of S, W and Y, reordered;
W's batches all moved into it. **Batch 95 is deliberately in no group**: it
stays blocked on the storage-egress attribution, which is an owner action.

**For N-Z, the nine-phase run order in `docs/review/2026-09-13/09-prompts.md`
supersedes the letters for sequencing.** Several phases take only part of a group — the
gate repair takes 152 alone out of X, for instance — and are run as a sequence
of `/batch-start` calls. The letters remain the thematic grouping and are what
this command accepts. Group Z is the exception: it was decided after the phases
and replaces Phase 9's order for the five batches it holds.

**Groups AA-AH (2026-09-30) are invoked in run order, not alphabetically:**
`/batch-start 169` alone, then AG, AA, AC, AD, AE, AB, AF, AH. That is the
nine-phase order in `docs/review/2026-09-28/09-prompts.md`, where every phase
after the first is exactly one of these groups. 169 is in AA by theme but runs on
its own, so that `/group-start AA` cannot carry on into 172 before AG has
repaired the gate. Groups AA and AB are web-only and carry no shipment.

AG and AH are tooling, yet each ends at a checkpoint. 199 fixes two backend tests
and 203 edits `apps/api/pyproject.toml` and backend tests; `scripts/check-deploy-drift.sh`
counts every path under `apps/api` as reaching the API image, so each leaves a
`/ship-prod` owed, and once Batch 201 has landed close-out refuses any web change
while one is owed. That shipment migrates nothing; if drift is already in sync
there, step 4 passes the checkpoint as usual.
AD stops after 188 so the owner can run the season-calendar backfill, and AF
stops before 194 so the review's only migration ships alone.

1. Validate the argument against that manifest. Find and read the exact group
   section in `docs/review/2026-08-26/07-sequencing.md` (groups I-M),
   `docs/review/2026-09-13/08-sequencing.md` (groups N-Z) or
   `docs/review/2026-09-28/08-sequencing.md` (groups AA-AH), then read every batch
   row and its verification and scope boundary in `docs/BUILD_PLAN.md` — open
   rows are at its head, closed ones under `## Closed batches`, so find each by
   `grep -nE "^- \[[ x]\] \*\*Batch N "` and read that row alone rather than the
   whole file. Also read `STATUS.md` (one page) and the relevant recent entries
   at the end of `session-log.md` before deciding where the group resumes. For
   any AA-AH group but AG, stop and report if a Group AG batch is unchecked: the
   gate repair runs first (2026-09-28 review, decision 7).

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
