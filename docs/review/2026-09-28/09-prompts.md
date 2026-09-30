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

### Phase 1 — The toast fix · Standard · high · web-only

```text
/batch-start 169
```

### Phase 2 — Gate integrity · Deep · max · deploys nothing

The owner's gate-maintenance approvals for 198-203 (and 178) were recorded in
`scripts/assert-quality-guardrails.sh` on the review branch (decision 7, 30 Sep), so they take
effect once that branch is merged.

```text
/batch-start 198
/batch-start 200
/batch-start 199
/batch-start 201
```

### Phase 3 — Web fixes members meet today · Deep · high · web-only

```text
/batch-start 172
/batch-start 173
/batch-start 174
/batch-start 170
```

### Phase 4 — Security · Deep · xhigh → `/ship-prod`

```text
/batch-start 180
/batch-start 179
/batch-start 181
/batch-start 182
```
179 and 181 wait on decisions 1 and 5; 180 does not.

### Phase 5 — Correctness and data · Deep · max → `/ship-prod`

```text
/batch-start 183
/batch-start 188
/batch-start 184
/batch-start 185
/batch-start 186
/batch-start 187
```
Ship after 188 if the owner wants to run the backfill sooner.

### Phase 6 — Provider budget and scheduler · Deep · xhigh → `/ship-prod`

```text
/batch-start 189
/batch-start 190
/batch-start 191
/batch-start 192
/batch-start 193
```

### Phase 7 — The visual pass · Standard · high · web-only

```text
/batch-start 171
/batch-start 175
/batch-start 176
/batch-start 177
/batch-start 178
```

### Phase 8 — Member features · Deep · xhigh → `/ship-prod` (194 on its own)

```text
/batch-start 196
/batch-start 195
/batch-start 197
/batch-start 194
```

### Phase 9 — Toolchain and hygiene · Standard · high

```text
/batch-start 202
/batch-start 203
```

## Two things that are not batches

- **Switch on the backup** — the owner's steps in `docs/runbooks/backup-restore.md`.
- **Rescope the local agent configuration** (PIPE-01) — by hand; an agent governed by it
  should not edit it.

Group letters in `08-sequencing.md` (AA-AH) are thematic; this phase order supersedes them
for ordering. `/group-start` does not accept them yet: `docs/agent-commands/group-start.md`
validates only I-M and N-Z against the two earlier reviews. Extending it to AA-AH is a small
edit to that (unprotected) workflow, left for the owner to ask for; until then each phase is
the `/batch-start` sequence above.
