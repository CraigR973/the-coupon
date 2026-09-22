# 09 — Commands, model and effort for running Batches 120-168

The batch row in `docs/BUILD_PLAN.md` **is** the prompt: `/batch-start N` greps
it, reads it whole, and implements from it. Nothing else needs writing for a
batch to start from a cold session. What was missing is what this document adds
— **which model and effort each batch needs**, and the copy-paste order.

## Model and effort

Taken from the convention the owner established in the `mcu_app` repository
(`docs/phase-batches.md`), deliberately unchanged so one rule governs both.

**Name the need, not the model.** Model names decay — this repository's own
`BUILD_PLAN.md` already carries 59 inline `*(Opus)*` / `*(Sonnet)*` annotations
from a lineup that has since moved on, which is exactly the rot the split
avoids. The need is stable; the mapping lives here, in one small table, and is
the only line to edit when a lineup changes.

| Need | When | Claude Code | Codex |
| --- | --- | --- | --- |
| **Deep** | Silent failure modes, irreversible actions, credentials, a public surface, or a spec you expect to be wrong | Opus 5 | GPT-5.6 Sol |
| **Standard** | Ordinary feature work against a clear spec, caught by tests when wrong | Sonnet 5 | GPT-5.6 Terra |
| **Light** | Mechanical, well-specified, small blast radius | Haiku 4.5 | GPT-5.6 Luna |

### Effort

| Claude Code | Codex | Used here for |
| --- | --- | --- |
| `medium` | Medium | Doc restructuring, small independent UI, work closer to drafting than engineering |
| `high` | High | **The default.** Ordinary feature work — most batches |
| `xhigh` | Extra High | Irreversible actions, credentials, a public surface, or a known-bad spec |
| `max` | Max | Silent wrong data, or the machinery every other batch is verified by — **four batches** |

**`high` is the baseline, not the exception.** And, as `mcu_app` puts it,
**effort tracks risk, not size.** This review proves the point twice over: the
largest single finding by blast radius is a **three-word focus style**
(`outline-none` plus a glow), and the most dangerous is a **missing argument**
on one function call that lets a stray round score.

### Why four batches are `max`

- **152** — the gate itself. It can currently pass a bundle it never tested, and
  close-out auto-deploys on green. Every other batch in this plan is verified by
  the thing 152 repairs; if it is wrong, nothing downstream means anything.
- **121** — a stray round settles and scores, silently. Points come out wrong and
  the standings look entirely plausible. That is the definition of silent wrong data.
- **134** — correcting a mis-settled pick rewrites awarded points. Irreversible,
  and it is the batch that exists because doing it by hand already happened once.
- **95** — the only copy of the game's scored history. A backup that silently
  writes nothing is worse than no backup, because it is trusted.

## The per-batch table

Effort above the `high` baseline carries its reason. Everything unannotated is
ordinary feature work.

| batch | need | effort | why, where it is not the default |
| --- | --- | --- | --- |
| 120 | Deep | xhigh | a concurrency race on the Saturday path |
| 121 | Deep | **max** | silent wrong points |
| 122 | Deep | xhigh | account takeover, credentials |
| 123 | Deep | xhigh | authentication and lockout |
| 124 | Deep | high | access control |
| 125 | Deep | high | access control |
| 126 | Deep | high | identity, and the name is the whole identity here |
| 127 | Standard | high | toolchain bump, caught by the gate |
| 128 | Deep | high | the rule that governs every future migrating ship |
| 129 | Standard | high | |
| 130 | Standard | high | |
| 131 | Deep | xhigh | changes an oracle test that encodes the wrong behaviour |
| 132 | Deep | xhigh | silently renames rounds members have played |
| 133 | Deep | high | provider budget |
| 134 | Deep | **max** | rewrites awarded points, irreversible |
| 135 | Standard | high | |
| 136 | Deep | xhigh | irreversible, personal data |
| 137 | Standard | medium | mechanical, axe-verifiable |
| 138 | Standard | medium | two token changes, measurable |
| 139 | Standard | high | |
| 140 | Standard | high | the largest visual change in the plan |
| 141 | Deep | high | a public surface |
| 142 | Standard | high | |
| 143 | Standard | high | |
| 144 | Standard | high | |
| 145 | Standard | high | |
| 146 | Deep | xhigh | a migration, and it removes the rollback target |
| 147 | Standard | high | |
| 148 | Standard | high | |
| 149 | Standard | medium | independent UI |
| 150 | Standard | medium | independent UI |
| 151 | Standard | high | touches many components |
| 152 | Deep | **max** | the machinery everything else is verified by |
| 153 | Standard | medium | documentation and one hook string |
| 154 | Standard | high | the cold-start context every future batch reads |
| 155 | Deep | high | privacy, in a public repository |
| 156 | Standard | high | changes a number members see |
| 157 | Standard | high | removes an API field a deployed client reads |
| 158 | Standard | high | |
| 159 | Deep | high | provider budget, and it 429s silently |
| 160 | Deep | xhigh | the gauge the pick reserve trusts is wrong |
| 161 | Deep | high | provider budget across the installation |
| 162 | Standard | high | |
| 163 | Deep | high | the service worker — a wrong precache breaks offline quietly |
| 164 | Standard | high | |
| 165 | Standard | high | one of the three is a cache-correctness bug |
| 166 | Standard | high | re-measure before starting |
| 167 | Standard | medium | |
| 168 | Standard | medium | |
| 95 | Deep | **max** | the only copy of the scored history |

**A group or phase runs at the strictest setting any of its batches asks for.**
That value is derived from this table, never typed independently.

## Run order — the nine phases

These supersede the group letters in `08-sequencing.md` **for ordering only**;
the letters remain as the thematic grouping and `/group-start` still uses them.
Where a phase takes only part of a group, it is a sequence of `/batch-start`
calls rather than a group command.

### Phase 1 — Gate repair · Deep · max · deploys nothing

```text
/batch-start 152
```

### Phase 2 — The Saturday defects · Deep · max → `/ship-prod`

```text
/group-start N
```
Group N is 120 → 121 → 122. No migration, so this shipment **restores a
rollback baseline** — the first since 025.

### Phase 3 — Web fixes, each reaching members on its own push · Standard · high

```text
/batch-start 158
/batch-start 137
/batch-start 138
/batch-start 139
/batch-start 167
```
158 first: it is the only HIGH here and it is on every screen. 139 assumes 120
has shipped, so that its conflict state is real before it is styled.

### Phase 4 — Security remainder · Deep · xhigh → `/ship-prod`

```text
/group-start O
/batch-start 141
/batch-start 143
```

### Phase 5 — Provider budget and scheduler · Deep · xhigh → `/ship-prod`

```text
/batch-start 159
/batch-start 160
/batch-start 161
/batch-start 133
/batch-start 162
/batch-start 129
/batch-start 147
```
**Order is load-bearing here.** 159 halves what a window costs, so 133 sizes its
budget against the real number; 160 makes the counter honest before anything is
tuned against it.

### Phase 6 — Correctness follow-ups · Deep · xhigh → `/ship-prod`

```text
/batch-start 130
/batch-start 131
/batch-start 132
/batch-start 156
/batch-start 157
```
**131 will stop and report** — it changes an oracle test, which `AGENTS.md`
makes a decision rather than a batch's own call.

### Phase 7 — Performance · Deep · xhigh → `/ship-prod`

```text
/batch-start 144
/batch-start 145
/batch-start 146
/batch-start 163
/batch-start 164
/batch-start 165
/batch-start 166
```
146 is the plan's only migration: it removes the rollback target, so 128 should
land first if it has been pulled forward. **166 last, and re-measure before
starting it** — its 915 ms may be mostly 164 and 165.

### Phase 8 — What members are missing · Deep · max → `/ship-prod`

```text
/batch-start 134
/batch-start 135
/batch-start 136
/batch-start 148
```

### Phase 9 — Infrastructure, docs, visual · Deep · max → `/ship-prod`

```text
/batch-start 127
/batch-start 128
/batch-start 142
/batch-start 154
/batch-start 155
/batch-start 95
/batch-start 140
/batch-start 149
/batch-start 150
/batch-start 151
/batch-start 168
```
**95 is still blocked** on the storage-egress attribution, which is an owner
action and not a batch. 168 pairs with 140 — verify them together at 200% zoom.

## Two things that are not batches

- **Rescope the local agent database configuration** (PIPE-01) — a file on the
  owner's machine binding a write-capable database tool to the wrong project.
  An agent governed by that configuration should not be the one to edit it.
- **Attribute the storage-egress consumer** (FEAT-A09) — investigation, not
  code, and the only route to Batch 95.

## A deliberate deviation, recorded

The inline `*(Opus)*` / `*(Sonnet)*` bracket the existing rows carry was **not**
added to Batches 120-168. Doing so would have put a decaying model name on 49
more rows, against the reasoning above. The existing 59 annotations are left
alone as the historical record of what those batches were run with. If repo-internal
consistency is preferred over the split, the brackets can be added from the table
above in one pass — say so and it is a five-minute edit.
