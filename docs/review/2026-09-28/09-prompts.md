# 09 — Model, effort and run order for Batches 169-203

The batch row in `docs/BUILD_PLAN.md` **is** the prompt: `/batch-start N` reads it whole
and implements from it. This file adds only the need, the effort and the copy-paste order,
using the table in `docs/review/2026-09-13/09-prompts.md` unchanged.

| Need | When | Claude Code | Codex |
| --- | --- | --- | --- |
| **Deep** | Silent failure modes, irreversible actions, credentials, a public surface, or a spec you expect to be wrong | Opus 5 | GPT-5.6 Sol |
| **Standard** | Ordinary feature work against a clear spec, caught by tests when wrong | Sonnet 5 | GPT-5.6 Terra |
| **Light** | Mechanical, well-specified, small blast radius | Haiku 4.5 | GPT-5.6 Luna |

Effort: `medium` for small independent UI and docs, `high` the default, `xhigh` for
irreversible actions, credentials or a public surface, `max` for silent wrong data or the
machinery every other batch is verified by. **Effort tracks risk, not size.** A group or
phase runs at the strictest setting any of its batches asks for.

## Why three batches are `max`

- **198** — the gate. It currently lets a branch switch its own checks off, and close-out
  deploys on green; everything after it is verified by it.
- **184** — voids picks members made in good faith, and changes which rounds are offered;
  a mistake here is silently wrong points.
- **187** — re-scores every settled pick on a fixture in every league. Irreversible, and it
  is the second time the product has needed it.

## The per-batch table

| batch | need | effort | why, where not the default |
| --- | --- | --- | --- |
| 169 | Standard | high | the Saturday feedback channel, both themes |
| 170 | Standard | medium | small, measurable |
| 171 | Standard | high | 126 uses across 40 files; every contrast pair moves |
| 172 | Deep | high | the offline pick path (Batch 90's semantics) |
| 173 | Standard | high | |
| 174 | Standard | high | |
| 175 | Standard | high | the most-used screen's layout |
| 176 | Standard | medium | |
| 177 | Standard | medium | |
| 178 | Standard | medium | waits on decision 11 |
| 179 | Deep | xhigh | account takeover; decision 1 |
| 180 | Deep | xhigh | authentication and lockout |
| 181 | Deep | high | identity; decision 5 |
| 182 | Standard | high | a CSP change can break the app if wrong |
| 183 | Deep | high | silent 500s on history that never heals |
| 184 | Deep | **max** | voids picks; decision 3 |
| 185 | Deep | xhigh | deletes unlocked picks; decision 2 |
| 186 | Standard | high | |
| 187 | Deep | **max** | rewrites awarded points across leagues; decision 4 |
| 188 | Deep | xhigh | relabels played weeks; gates an owner action |
| 189 | Deep | high | provider budget; 429s silently |
| 190 | Deep | high | refuses picks when wrong |
| 191 | Deep | xhigh | the pick path under load; silent alert loss |
| 192 | Standard | high | |
| 193 | Standard | high | |
| 194 | Deep | xhigh | a migration, removes the rollback target; decision 9 |
| 195 | Standard | high | decision 10 |
| 196 | Standard | medium | |
| 197 | Deep | high | a public read keyed by a secret token; decision 12 |
| 198 | Deep | **max** | the gate itself; owner-approved gate maintenance |
| 199 | Deep | xhigh | changes close-out; decision 6 |
| 200 | Deep | high | gate maintenance |
| 201 | Deep | high | gate maintenance |
| 202 | Standard | high | decision 8; majors one at a time |
| 203 | Standard | medium | hygiene |

## Run order

Since 30 Sep each phase after the first is one `/group-start` group (manifest in
`docs/agent-commands/group-start.md`), and every stop for `/ship-prod` is a checkpoint in it.

### Phase 1 — The toast fix · Standard · high · web-only

```text
/batch-start 169
```

### Phase 2 — Gate integrity · Deep · max → a behaviour-neutral `/ship-prod`

The owner's gate-maintenance approvals for 198-203 (and 178) were recorded in
`scripts/assert-quality-guardrails.sh` on the review branch (decision 7, 30 Sep), and are live
now that it is on `main`.

```text
/group-start AG
```
Group AG is 198 → 200 → 199 → 201, then a `/ship-prod`: 199's two backend test fixes count as
API changes to the drift check, and from 201 on close-out refuses web work while a shipment is
owed. The shipment migrates nothing.

### Phase 3 — Web fixes members meet today · Deep · high · web-only

```text
/group-start AA
```
Group AA is 172 → 173 → 174 → 170; its fifth batch, 169, was Phase 1.

### Phase 4 — Security · Deep · xhigh → `/ship-prod`

```text
/group-start AC
```
Group AC is 180 → 179 → 181 → 182. Decisions 1 and 5, which 179 and 181 waited on, were
answered on 30 Sep.

### Phase 5 — Correctness and data · Deep · max → `/ship-prod` after 188 and at the end

```text
/group-start AD
```
Group AD is 183 → 188 → `/ship-prod` → 184 → 185 → 186 → 187 → `/ship-prod`. The first shipment
lets the owner run the backfill four batches sooner (owner, 30 Sep).

### Phase 6 — Provider budget and scheduler · Deep · xhigh → `/ship-prod`

```text
/group-start AE
```
Group AE is 189 → 190 → 191 → 192 → 193.

### Phase 7 — The visual pass · Standard · high · web-only

```text
/group-start AB
```
Group AB is 171 → 175 → 176 → 177 → 178.

### Phase 8 — Member features · Deep · xhigh → `/ship-prod` before 194 and after it

```text
/group-start AF
```
Group AF is 196 → 195 → 197 → `/ship-prod` → 194 → `/ship-prod`, so the migration ships on its
own.

### Phase 9 — Toolchain and hygiene · Standard · high → a behaviour-neutral `/ship-prod`

```text
/group-start AH
```
Group AH is 202 → 203, then a `/ship-prod` for 203's edits under `apps/api` (the stale pins and
Batch 161's tests).

## Two things that are not batches

- **Switch on the backup** — the owner's steps in `docs/runbooks/backup-restore.md`.
- **Rescope the local agent configuration** (PIPE-01) — by hand; an agent governed by it
  should not edit it.

Group letters in `08-sequencing.md` (AA-AH) are thematic and not in run order: invoke them in
the phase order above. `/group-start` accepts them since 30 Sep, at the owner's request; its
manifest in `docs/agent-commands/group-start.md` is the authority on each group's batches and
checkpoints, and `08-sequencing.md` records why each stop falls where it does.
