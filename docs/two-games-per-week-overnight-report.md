# Two games per week — local implementation report

13 Nov 2026 · work in progress. Production unchanged; no shipment, activation or
formal batch close-out performed. Canonical batch rows remain unchecked.

## Current checkpoint

1 of 10 batches locally verified. Batch 219 contracts passed independent review
and the unmodified full 12-check gate: backend 1,650, frontend 1,418, seeded
journey 1, zero skips. Exact verified tree `532b4c0ae32249051381f4f4c0192d8a3fc5e2d9`
matches commit `1a0ca8f2d78c6334bd14e1caf5c74e41943238b0`; evidence is in
`.local/overnight-two-games/219-gate-attempt1.log`. Later Batch 220 edits are not
covered by that stamp.

Batch 220 storage/isolation is in progress. Batches 221–228 have not started.
Production remains unchanged. Both new UI flows remain unimplemented.

Batch 220 focused verification passed 60 PostgreSQL-backed tests with zero
skips, including 33 added storage/migration tests. Synthetic populated 031→032
upgrade preserves paid and free/custom-window leagues, legacy UUIDs, picks,
points, dues/reversals, matched/queued fake payments and notification history.
Old running payment writes/deduplication/assignment continue. Synthetic
dump/restore and forward restart retain committed quota, cooldown and cursor.
Real concurrent storage claims admit exactly one writer; failed group/fantasy
replacement preserves the original. All 15 new tables force RLS, revoke public
grants and have indexed foreign keys. The full gate is still pending; these
focused checks do not accept the milestone.

The first full storage gate failed its backend check: 1,680 passed, three
failed, zero skipped. New format checking loaded API settings into the separate
payments process and opened a business transaction between a completed legacy
discovery commit and a later provider failure. The settings import is now lazy;
format fences are prepared before the provider walk, preserving rollback and
committed-chunk semantics. The new label test also reused the legacy pick-flow
season; its synthetic fixture moved to an unused season without changing any
assertion. All 86 focused regression checks now pass with zero skips, including
the unchanged legacy failures and the predecessor tests that exposed the season
collision. Another complete gate remains required before accepting storage.
Independent review accepts these corrections. Discovery takes its format snapshot
before the walk; a concurrent cutover may still spend an already-in-flight legacy
provider request, while later source/database fences prevent a legacy write.
The first gate finished 11/12: frontend 1,418 and seeded journey 1 passed with
zero skips. Corrections made after its backend failed are not verified by that
run. The next gate must verify the entire corrected tree.

| Batch | Local status | Branch / parent |
| --- | --- | --- |
| 219 contracts | Locally verified; commit `1a0ca8f` | `feat/batch-219-two-game-contracts` / `dfb39fe` |
| 220 storage/isolation | In progress | `feat/batch-220-two-game-storage` / `1a0ca8f` |
| 221 provider work | Not started | Pending verified 220 |
| 222 weekly billing | Not started | Pending verified 221 |
| 223 group API | Not started | Pending verified 222 |
| 224 fantasy API | Not started | Pending verified 223 |
| 225 results/lifecycle | Not started | Pending verified 224 |
| 226 read APIs | Not started | Pending verified 225 |
| 227 group web | Not started | Pending verified 226 |
| 228 fantasy web | Not started | Pending verified 227 |

## Evidence and recovery

The starting branch, HEAD/main and planning diff matched the saved prompt.
Existing planning files are preserved for explicit inclusion in Batch 219.
Main remains `dfb39fef90dd4a171248c79117d6bdc72d63ce8d`.
Local draft commit `fd7db37dd8d20a368d97fb1c1a7fbf21d2911cc5` contains exactly
13 in-scope planning/contract/report files. It is not a verified milestone.
The ignored `.local/overnight-two-games/` contains the initial diff/status,
`state.json`, append-only `journal.md` and gate logs. Resume from that state and
verify current Git state before taking the recorded next action.

The baseline gate was red, began before document edits and cannot verify the final
Batch 219 tree. Each accepted milestone requires its own full exact-tree gate.
No `SKIP_PROD_BUNDLE` acceptance, gate changes or weakened assertions are allowed.
Local servers/tests use fake football/odds/banking and disposable databases.
No production credentials are loaded into local servers.

## Decisions made within the approved design

- Keep existing football-week UUIDs as parents, add immutable format, and keep
  group/fantasy child data isolated; retain the existing pooled ledger.
- Use operation IDs plus revisions for exact-target retries and concurrent edits.
- Bound each lookahead pass to 12 Saturdays, persist progress and expose unknown
  coverage instead of inferring a break from an empty provider response.
- Keep 90/hour and 450/rolling-day provider caps configurable assumptions;
  overload, unsupported traffic and stale/missing browse prices stay visible.
- Leave protected AGENTS.md's legacy summary unchanged; alignment needs separate
  approval during integration.

## Failures and fixes

Independent contract review found and resolved accepted-operation replay after
lock and undefined legacy fields on new-format parents. Replay now precedes
mutable entry gates, and parent sentinel fields plus mandatory legacy filters
and database fences are explicit. Baseline browser failures were transient;
Batch 219's later full gate passed without changing source or assertions.

- Deep-link smoke: fixed port 4173 was held by another project’s active MCU test
  preview. It was preserved and has now exited; no port/gate workaround was applied.
- Seeded journey: the home-card assertion failed with the app showing offline
  and a lazy-chunk update fallback. Runtime source/tests/scripts are byte-for-byte
  unchanged from local main. The retained trace archive is truncated. System
  load was 99 when diagnosed; timing pressure is a possible cause, not proved.
- An unmodified journey-only diagnostic passed: one test, zero skipped, against
  the same main runtime source and fresh scratch database, without changes to
  timeouts/assertions. The first failure was transient; its exact cause is not
  proved. This diagnostic is not a substitute for the full gate.

A read-only exploration used an absent
`models/membership.py` path; membership wiring was located through league routes.
This changed no files or acceptance assertions.

Storage review found five legacy readers still including new parents: results,
season counts, week labels, discovery recency and explicitly addressed pick
reads. Format filters/refusals and a dedicated reader test now cover them.
Earlier schema review corrected equal opening/lock support, immutable IDs,
membership intersection and conditional protection of linked new weekly dues.
Focused Ruff/type checks found import/format errors and an iterable/query mismatch
in legacy reversal logging; source fixes retain every assertion. An ambient
Python 3.7 AST script initially inserted guards inside docstrings; managed
Python 3.12 corrected all nine placements before tests. No suppression was added.
An over-broad optional format diagnostic included historical migrations outside
the canonical formatting scope; it reported 14 pre-existing files. Those files
remain untouched. Current API/new migration lint passes; full gate pending.

## Remaining release gates and exact next step

Continue the authorised local run on Batch 220: finish legacy format fences,
clean/populated migrations, RLS/constraint/recovery tests and the full gate.
Then stack 221 on its verified local commit. Do not merge or push.

Owner review/release follows completion: review the local stack and report,
integrate under normal gates with fresh exact-head CI, create/test a production
recovery point before migration, explicitly ship API then payments on the same
SHA/head with mode off, then release web. Separate exact future league/week
activation requires live opening coverage/quota and supported traffic/latency
acceptance. Natural member use, payments and notification receipt remain open.
