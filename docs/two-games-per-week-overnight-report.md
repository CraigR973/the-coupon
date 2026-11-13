# Two games per week — local implementation report

13 Nov 2026 · work in progress. Production unchanged; no shipment, activation or
formal batch close-out performed. Canonical batch rows remain unchecked.

## Current checkpoint

0 of 10 batches locally verified. Batch 219's concrete API contract, product
contract and architecture map passed independent review after two fixes. The
unmodified baseline gate failed its two browser checks; 10 of 12 checks passed.
Backend: 1,650 passed, zero skipped. Frontend: 1,418 passed, zero skipped.
The seeded journey passed zero of one. Subsequent batches
have not started; no missing check is represented as passed.

| Batch | Local status | Branch / parent |
| --- | --- | --- |
| 219 contracts | Contract review passed; gate pending | `feat/batch-219-two-game-contracts` / `dfb39fe` |
| 220 storage/isolation | Not started | Pending verified 219 |
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
and database fences are explicit. Baseline browser failures are under diagnosis; no milestone is accepted.

- Deep-link smoke: fixed port 4173 is held by another project’s active MCU test
  preview. It was preserved; no port/gate workaround was applied.
- Seeded journey: the home-card assertion failed with the app showing offline
  and a lazy-chunk update fallback. Runtime source/tests/scripts are byte-for-byte
  unchanged from local main. The retained trace archive is truncated. System
  load was 99 when diagnosed; timing pressure is a possible cause, not proved.
- An unmodified journey-only diagnostic is running against the same main runtime
  source and fresh scratch database, without changing timeouts or assertions.
  This is diagnosis, not a substitute for the full gate.

A read-only exploration used an absent
`models/membership.py` path; membership wiring was located through league routes.
This changed no files or acceptance assertions.

## Remaining release gates and exact next step

Continue the authorised local run: classify the red baseline browser checks,
then run the full Batch 219 gate, explicitly commit its in-scope files, and start 220 on a
local branch stacked on that verified commit. Do not merge or push.

Owner review/release follows completion: review the local stack and report,
integrate under normal gates with fresh exact-head CI, create/test a production
recovery point before migration, explicitly ship API then payments on the same
SHA/head with mode off, then release web. Separate exact future league/week
activation requires live opening coverage/quota and supported traffic/latency
acceptance. Natural member use, payments and notification receipt remain open.
