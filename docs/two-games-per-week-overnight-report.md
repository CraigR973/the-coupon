# Two games per week — local implementation report

13 Nov 2026 · work in progress. Production unchanged; no shipment, activation or
formal batch close-out performed. Canonical batch rows remain unchecked.

## Current checkpoint

2 of 10 batches locally verified. Batch 219 contracts passed independent review
and the unmodified full 12-check gate: backend 1,650, frontend 1,418, seeded
journey 1, zero skips. Exact verified tree `532b4c0ae32249051381f4f4c0192d8a3fc5e2d9`
matches commit `1a0ca8f2d78c6334bd14e1caf5c74e41943238b0`; evidence is in
`.local/overnight-two-games/219-gate-attempt1.log`. Later Batch 220 edits are not
covered by that stamp.

Batch 220 storage/isolation passed independent review and its corrected full
12-check gate: backend 1,683, frontend 1,418, seeded journey 1, zero skips.
Verified tree `bb0a4067b0c99994b0ca7a540cac79a48a32ff0e` matches local commit
`e458ec8c8b93eae747c52c088750ee6db42ef2a2`; log
`.local/overnight-two-games/220-gate-attempt2.log`. The report in that commit
records the pending gate at invocation; this later branch records its result.
Current Batch 221 edits are not covered by either earlier stamp.

Batch 221 provider work is in progress. Batches 222–228 have not started.
Production remains unchanged. Both new UI flows remain unimplemented.

Batch 221's implementation now passes independent source review. Focused
transport/quote/provider/scheduler checks passed 290 tests with zero skips;
health, mixed-format fixture moves, storage and scheduler regressions then
passed 115 with zero skips. The latest API lint/format and mypy checks pass.
These focused results predate the final milestone gate and do not verify the
entire candidate. No full Batch 221 gate has run yet.

The draft includes shared paginated census, independent windows and London/DST
clocks, confirmed-break lookahead/recovery, short token-fenced quote/work leases,
actual-attempt rolling admission across legacy and new callers, receipt-aware
header accounting, fair price isolation and active-only scheduled health.
Unknown/empty data never declares a break. The current configured source's
pagination must be supported; real Betfair census is explicitly unsupported.

Eight counted capacity checks pass, zero skips. The 14-member cold rush admits
85 foreground plus five opening calls; 30/100 rushes refuse 92/515 foreground
requests. Two 264-fixture cards make 240 background calls and 110 admission
refusals across 48 hours, leaving a 17-hour oldest snapshot. Coverage and
supported load remain unaccepted for activation. The exact declared scenarios,
smaller-card results and evidence limits are in
`docs/two-games-per-week-local-capacity.md`. No membership was restricted and no
stale quote was treated as fresh to fit the meter.

Batch 220 focused verification passed 60 PostgreSQL-backed tests with zero
skips, including 33 added storage/migration tests. Synthetic populated 031→032
upgrade preserves paid and free/custom-window leagues, legacy UUIDs, picks,
points, dues/reversals, matched/queued fake payments and notification history.
Old running payment writes/deduplication/assignment continue. Synthetic
dump/restore and forward restart retain committed quota, cooldown and cursor.
Real concurrent storage claims admit exactly one writer; failed group/fantasy
replacement preserves the original. All 15 new tables force RLS, revoke public
grants and have indexed foreign keys. These focused checks preceded the full
gate; acceptance rests on the corrected exact-tree full rerun above.

The first full storage gate failed its backend check: 1,680 passed, three
failed, zero skipped. New format checking loaded API settings into the separate
payments process and opened a business transaction between a completed legacy
discovery commit and a later provider failure. The settings import is now lazy;
format fences are prepared before the provider walk, preserving rollback and
committed-chunk semantics. The new label test also reused the legacy pick-flow
season; its synthetic fixture moved to an unused season without changing any
assertion. All 86 focused regression checks now pass with zero skips, including
the unchanged legacy failures and the predecessor tests that exposed the season
collision. The corrected complete gate then passed before storage was accepted.
Independent review accepts these corrections. Discovery takes its format snapshot
before the walk; a concurrent cutover may still spend an already-in-flight legacy
provider request, while later source/database fences prevent a legacy write.
The first gate finished 11/12: frontend 1,418 and seeded journey 1 passed with
zero skips. Corrections made after its backend failed are not verified by that
run. The second gate verified the entire corrected tree.

| Batch | Local status | Branch / parent |
| --- | --- | --- |
| 219 contracts | Locally verified; commit `1a0ca8f` | `feat/batch-219-two-game-contracts` / `dfb39fe` |
| 220 storage/isolation | Locally verified; commit `e458ec8` | `feat/batch-220-two-game-storage` / `1a0ca8f` |
| 221 provider work | In progress | `feat/batch-221-two-game-provider` / `e458ec8` |
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
remain untouched. Current API/new migration lint and the corrected full gate pass.

## Provider implementation failures and corrections (221)

- Initial meter clock setup put an attempt exactly outside the rolling day;
  the synthetic Friday time moved one hour, preserving all assertions.
- Quote tests initially indexed the adapter's first selection as HOME; their
  helper now addresses HOME by identity. The expected prices stay unchanged.
  Both empty response and fixture-with-no-selections negatives are covered.
- Independent review found concurrent header races in both completion orders.
  Durable response receipts now deduct requests not certainly included upstream;
  equal timestamps stay conservative. Real blocked-transport tests cover both.
- The first discovery slice passed 277 and failed one new test: newly queued
  fair price work ran before the page failure the fixture meant to select.
  Its synthetic queue selection now isolates both page attempts. Original
  cursor/error/count assertions remain intact; subsequent regressions pass.
- Review corrected expired work rotation, exact cutover collision reporting,
  long-offset lookahead continuation, void/moved eligibility, opening-only
  work scope, negative backoff preservation, mixed legacy/new cached writers
  and new-format discovery health. Dedicated regressions cover the causes.

Iteration lint/type failures were source import/format, typed query return,
explicit import and optional timestamp errors; all were fixed without
suppressions. One lint invocation used repository-relative paths from the API
working directory and performed no edits; absolute paths corrected it. A static
AST count diagnostic could not evaluate date constructor literals; it changed no
source or assertions. No full milestone failure is hidden by focused passes.

## Remaining release gates and exact next step

Run the unmodified full Batch 221 gate on the documented candidate. Stack 222
only on its exact verified local commit, then continue through both web flows
and final review. The last tree stamps above do not cover 221. Do not merge or push.

Owner review/release follows completion: review the local stack and report,
integrate under normal gates with fresh exact-head CI, create/test a production
recovery point before migration, explicitly ship API then payments on the same
SHA/head with mode off, then release web. Separate exact future league/week
activation requires live opening coverage/quota and supported traffic/latency
acceptance. Natural member use, payments and notification receipt remain open.
