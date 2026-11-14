# Two games per week — local implementation report

14 Nov 2026 · work in progress. Production unchanged; no shipment, activation or
formal batch close-out performed. Canonical batch rows remain unchecked.

## Current checkpoint

5 of 10 batches locally verified. Batch 219 contracts passed independent review
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
Later batch edits are not covered by either earlier stamp.

Batch 223 group API passed full gate 3 on corrected tree
`a013bb2526b6b9c2ab6bbc2d108ffde031d1d621`, matching local commit
`8dfd28d5b2cecbecdc0d48efc1245097b63e6b69`: backend 1,852, frontend 1,418,
journey 1, zero skips. Log: `.local/overnight-two-games/223-gate-attempt3.log`.
Its report records the pending invocation; this branch records the result.
Batch 224 fantasy API is now in progress; 225–228 have not started.
Production remains unchanged. Both new UI flows remain unimplemented.

Batch 221's implementation now passes independent source review. Focused
transport/quote/provider/scheduler checks passed 290 tests with zero skips;
health, mixed-format fixture moves, storage and scheduler regressions then
passed 115 with zero skips. The latest API lint/format and mypy checks pass.
These focused results preceded the full milestone gate. Its unmodified first
full gate then passed all 12 checks: backend 1,749, frontend 1,418 and seeded
journey 1, zero skips. Tree `b24a51d85e5a5cbdba0375d15239e183d40708e0` matches
local commit `278e1fa578f222503e9f4c852764aa70795ec837`; log
`.local/overnight-two-games/221-gate-attempt1.log`. The report in that commit
records the pending gate at invocation; this branch records its result. The
221 stamp does not cover later 222 changes.

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
| 221 provider work | Locally verified; commit `278e1fa` | `feat/batch-221-two-game-provider` / `e458ec8` |
| 222 weekly billing | Locally verified; commit `7a98d95` | `feat/batch-222-weekly-dues` / `278e1fa` |
| 223 group API | Locally verified; commit `8dfd28d` | `feat/batch-223-group-api` / `7a98d95` |
| 224 fantasy API | In progress | `feat/batch-224-fantasy-api` / `8dfd28d` |
| 225 results/lifecycle | Not started | Pending verified 224 |
| 226 read APIs | Not started | Pending verified 225 |
| 227 group web | Not started | Pending verified 226 |
| 228 fantasy web | Not started | Pending verified 227 |

## Fantasy API implementation (224, full gate pending)

Six independent UUID-addressed slots now save and replace one leg at a time.
The slot envelope includes its nullable pick, revision and operation UUID;
readback includes release tombstones. Members share fixtures, including group
claims; only the same member's other fantasy slots reserve that fixture.
Partial entries remain valid. Group DTOs stay unpriced.

The save validates its exact target and replay before mutable admission,
commits early/intervening fees separately, then obtains the named fixture's
fresh quote without a request/auth/financial/fixture transaction. The final
short transaction refreshes access, slot revision, membership, eligibility,
paid-through status and deadline, and freezes the named price only through
exactly 60 seconds. It checks time and price after its last database wait,
immediately before mutation. Accepted operation and slot commit together.
After a quote failure, a short replay/state reconciliation still returns an
already accepted operation or the current lock/revision refusal. No second
provider request or fee is bought to do this.

Quote snapshots now have a DB-only reader that can reuse the caller's session.
Only the committed refresh-lease owner acquires a client. Fresh cache hits,
negatives, coalesced waiters and locked/browse reads acquire none. Slow login
rechecks token ownership before pricing. A cancelled dispatch retains spend
and its conservative lease; ordinary failure releases only owned tokens.
Known provider JSON/schema/decimal failures become sanitised quote refusal;
a failed login never publishes a fixture-negative. Actual source/bookmaker
identity is checked at production acquisition and used by the discovery factory
as well. Betfair Exchange is no longer stamped with the OddsAPI bookmaker.
Real Betfair census/activation acceptance remains unsupported and unperformed.

Local design decisions: prices use exact four-place decimal confirmation and
storage, from 0.0001 through 999999.9999; unrepresentable source values refuse
instead of rounding. Equivalent trailing zeros canonicalise before hashing.
A representable moved price returns PRICE_MOVED and needs a new explicit
operation at that named price. Legacy two-place comparison stays unchanged.
Actual upstream 429 and local budget refusal both return 429 PICKS_BUSY as
capacity refusals, with retry delay; provider authentication/plan and unusable
quote failures return 503 ODDS_UNAVAILABLE. Read-rate abuse remains separate.
The approved 120/member/hour and 2,000/league/hour edit ceilings share both games;
actual transport attempts retain the separate assumed installation meter.

Prior focused verification passed 159 PostgreSQL-backed tests, zero skips
(31.00s): 86 new checks and 73 unchanged quote/provider-budget/legacy oracles.
The current two new files add 87 checks after a further port/storage boundary
oracle described below. They cover six partial slots,
real independent-session races, failed replacement, canonical named-price
confirmation, sharing/isolation, uncertain lost success and exact readback,
actual retries and pre-dispatch refusal, real mock Betfair-login cancellation,
price cancellation/restart, current/next/another league/opening shared capacity,
twelve saves across noon, sixty-second and post-lock-wait freshness, future
observations, exact Saturday/Sunday/Monday boundaries, retained early £3 dues,
rollback/cache/spend persistence, a shared one-connection pool, actual production
factory provenance, parser failures, departure/tombstone/rejoin and mid-HTTP
roster/suspension/void/move races. The minimum positive quote uses an explicit
port/storage oracle, not a claim that OddsAPI offers sub-1 betting prices.
Independent review accepts the source and both added competition/confirmation
oracles. Full gate 1 passed all executed tests but failed its count check;
gate 2 was later interrupted for cumulative findings; full gate 3 is pending.

Failures and fixes: the first new identity fixture omitted required cache TTL;
its setup was corrected without changing assertions (then 21/21 passed).
The first API fixture incorrectly linked a Monday-exclusive fixture, which the
storage trigger correctly refused: all 36 API setups failed before HTTP.
It now links a valid fixture, then models a census move to Monday; all original
boundary assertions remain. The next matrix passed 56 and failed one real
state-precedence case: a long quote wait crossed noon and its lease, returning
refresh-busy instead of LOCKED. Post-error replay/state reconciliation fixed
that source defect; all 57 then passed. The expanded matrix passed 132.
Four later new tests lacked a restored ProviderSnapshot import after an earlier
unused-import cleanup: 151 passed and four failed; the import was fixed and
all 157 then passed. Two independent-review gaps were then added: a four-way
actual current/next/other-league/opening barrier races for one remaining
dispatch after one legacy dispatch; and a second price movement preserves the
old slot until its newly named price is confirmed. All 159 now pass. Source lint/format and six initial mypy errors were corrected
with explicit types, timestamp narrowing and the existing cooldown setting;
no suppressions or assertions changed. One lint command used a repository path
from the API directory; corrected absolute paths pass. Patch-context misses
made no edits and were reapplied against the formatted source.

Full gate 1 failed 1 of 12 checks: all 1,938 backend tests passed with zero
skips, but the expected count was 1,939. I miscounted the additions as 87
instead of 86; collect-only confirms 71 API plus 15 quote tests. Frontend
1,418, seeded journey 1 and every other check passed. No tests were removed,
and the threshold was retained at 1,939 for that repair. The log is
`.local/overnight-two-games/224-gate-attempt1.log`.

Independent review identified a missing direct port/storage lower-bound oracle:
OddsAPI filters sub-1 prices before storage admission, so its existing invalid
HTTP tests cannot prove refusal of a positive 0.00001 port quote. A new test
passes that raw price through SharedQuotes and the HTTP save, requires sanitised
503 on two attempts, and proves the raw cached value is never rounded into a
pick or substituted for the original slot/revision/operation. Existing dues
and actual spend remain unchanged. The new test and its accepted 0.0001
counterpart pass 2/2, zero skips (4.21s); this is explicitly port/storage evidence,
not new actual HTTP capacity evidence. No old assertion changed, and that
repair retained the 1,939 threshold; later new regressions legitimately raise it.
Those two files now collect 87 new tests. No 224 commit exists.

Cumulative independent review then found an accepted-operation replay handoff
defect introduced in the group API (223) and fantasy API (224). Two identical
requests can both pass initial admission; one commits while the other waits
for fee preflight. A later lock, suspension, global-off, departure, unpaid
projection or action refusal could mask that already accepted receipt. Gate 2
was interrupted after 616 backend passes (218.74s, one warning), with lint,
format and types passing. It has no acceptance stamp. The log is
`.local/overnight-two-games/224-gate-attempt2.log`.

Thirteen deterministic independent-request cases reproduced 11 failures and
two passing different-operation controls before repair. Both services now
reconcile mutable fee/payment refusals through a short baseline-authorised
league-locked accepted-operation read; fantasy also reconciles its action
refusal. If no matching accepted operation exists, the original refusal stays.
This does not repeat fees, quote acquisition or provider I/O. Seventeen final
race checks include unchanged-body success, wrong-body operation conflict,
different-operation refusal and deleted-league baseline denial. A combined
entry/fee/quote/group run passes 217 tests, zero skips (40.49s).

A second cumulative finding came from discovery (221): a fixture postponed
in W0, moved active to W1 and then reinstated in W0 by another legacy league
via its real empty-pool on-demand refresh could be deleted from both new cards
by W0's stale cached void status. The initial overlapping-range hypothesis was
withdrawn after checking canonical non-overlapping census keys; the actual
legacy-writer path was then reproduced. Its new regression failed with no
links before repair. Cleanup now consistently trusts the current shared
fixture/status facts, as insertion already does, retaining accepted history.
Discovery/storage then pass 61 tests, zero skips (12.05s), including existing
active-to-void and moved-fixture assertions unchanged. The new observation
uses a provider-port seam after two counted census HTTP calls; it is writer/
recovery evidence, not an additional HTTP-capacity claim.

The reinstatement check was expanded to four actual fresh-status combinations,
including a fresh all-void legacy response that creates no parent. Three of four
then exposed missing publication of the fresh legacy status: old W1 status could
still veto a newly active W0 fixture. Fresh on-demand fetches now publish actual
native-source metadata/status atomically; cached/pooled DTOs never publish status.
The first expanded fixture IDs exceeded the schema's 64-character limit; shorter
synthetic IDs fixed setup without changing assertions. Discovery/storage then
passed 64 tests, zero skips (13.19s); old population/lifecycle passed 25 (6.95s),
and the independent payments runtime passed 19 (1.77s).

Review of that repair confirmed a new calendar/fixture lock inversion: fresh
publication held a fixture before a later legacy season reanchor, while cached
legacy creation could hold the calendar before changing that fixture. Parent
creation/refusal/reanchor now precedes fixture writes. Fresh facts still publish
when no legacy parent is created. Fresh and genuinely changed legacy metadata
use one provider-event ordering; unchanged cached metadata retains no-write
behaviour. Three new PostgreSQL lock regressions pass (2.29s), proving a blocked
reanchor owns no fixture lock and both writers use the same ordering even when
DTO/UUID ordering is reversed. Independent review accepts this repair; it does
not claim all pre-existing repeated-sync transaction lock cycles are eliminated.
An earlier combined affected regression run passed 108, zero skips (19.59s);
the final combined run passes 111, zero skips (19.78s), including all three new
lock cases and the unchanged-row preservation refinement.

The replay fixture import first triggered Ruff F811 shadowing; an explicit
fixture alias assignment fixes it without suppression. Removing stale void
handling also left an unused import, removed without suppressions. Final API
lint/format and mypy (123 source files) pass. All 1,963 backend tests collect (3.37s). The ratchet increases
to 1,963: the prior 1,939 plus 17 replay cases, four fresh-observation cases
and three lock-order cases. No old assertions or protected gates changed.
Full gate 3 must verify these independently reviewed cumulative repairs
on the 224 tree. Earlier 221/223 stamps remain historical evidence for their
then-tested trees and do not cover these later fixes.

## Group API implementation (223, locally verified)

Explicit UUID group reads, saves and replacements now use an unpriced DTO and
local fixture/market labels. No provider is acquired. A whole fixture belongs
to one member in that group; fantasy and another league can use the same match.
Incomplete participation remains valid; zero entries reads “No coupon”. Both
children use the stored parent week number, without changing legacy labels.

A save first authorises its exact target and checks accepted-operation replay,
then validates its free local choices under the league lock. It releases that
transaction before independently committing any early/intervening weekly fees.
The final short transaction reacquires the league lock, replays an operation
that committed while it waited, and refreshes membership, schedule, entitlement,
revision and fixture eligibility. Fixture SHARE stabilises census metadata and
its status publication; the deadline is checked again after waits. Replacement
updates the existing pick atomically with its next revision and saved operation
response. A failed replacement leaves the original unchanged. Historical replay
returns the old response without recreating an old pick or charging again.

Design decisions made locally: group save/read use one nullable `GroupEntry`
envelope with exact target/revision/operation identity; week-only fees name the
exact group `#payment` destination; the web panels/anchors remain acceptance
work for 227/228. Existing legacy rate limits, responses and season labels stay
unchanged. New action ceilings are the approved 120/member/hour and
2,000/league/hour; twelve legitimate edits and replay after refusal are tested.

Focused verification: 134 PostgreSQL-backed checks pass, zero skips (21.28s),
including 58 added group HTTP/concurrency cases and 76 unchanged billing,
lifecycle and storage checks. The matrix covers actual fixture/member races,
real foreign league/week and fantasy-only fixtures, atomic failed replacement,
accepted operation races across lock waits, stale/tombstone revisions, actual
leave between committed fee and save, census writer blocking, moved/void data,
14:30 microseconds and inclusive opening, early £3 future-fee persistence,
business rollback, payment/refusal/replay and inactive invisibility. Every case
forbids provider acquisition and confirms no added ProviderAttempt; successful
nested responses have no price or points fields. API lint/format passes.
This focused run is not the full gate. Gate 2 passed all 12 checks with backend
1,845, frontend 1,418 and journey 1, zero skips, on tree
`e79a5393e6018ca1c25ac11326dff087cbcec911`. That stamp predates the authentication
fix below and does not verify the corrected tree. Gate 3 subsequently passed
all 12 checks with backend 1,852, frontend 1,418 and journey 1, zero skips,
on tree `a013bb2526b6b9c2ab6bbc2d108ffde031d1d621`, matching local commit
`8dfd28d5b2cecbecdc0d48efc1245097b63e6b69`. Later 224 edits are not covered.

Failures and fixes: the first 30-case run failed in the new JWT test helper
before requests because it omitted the required role. A subsequent single-case
diagnostic passed a string instead of the role enum; the helper now matches the
existing UUID/enum API, without changing assertions. The next matrix passed 29
and failed one real read: a legacy-only season label resolver excluded new
parents. Group now uses its already stored parent week number; legacy resolver
and assertions are untouched. Independent review found stale pre-lock fee time,
replay before baseline authorisation and concurrent census eligibility races.
Those source defects were fixed and regressed. Review then requested three
deterministic timing cases and real existing foreign-target cases, all present
in the 116-check run before validation additions. The fee destination previously named a nonexistent
member payments route; it now names the planned exact game payment panel.
Late review found typed malformed-input validation bypassed the explicit new
error envelope. Gate 1 was interrupted at 35% backend progress after lint,
format and mypy passed; it has no acceptance stamp. A scoped route wrapper now
maps typed malformed group/fee inputs to `422 INVALID_REQUEST`, raw parser
errors to `400 INVALID_REQUEST`, and read-rate refusal
to `429 TOO_MANY_TRIES` with Retry-After. Existing legacy handlers remain intact.
Seven malformed-input cases, a legacy validation preservation check and a real
121-read rate check now pass. Raw invalid-UTF8 JSON exercises the parser 400
path. A final fee-read race also needed the league financial lock: deletion
between initial access checks and projection could otherwise raise an internal
ValueError. Fee reads now refresh access after waiting and project in the same
transaction. Its deterministic deletion-wait regression returns structured 404
and creates no due. Independent review accepts both final fixes. The new legacy preservation test first targeted a
manually parsed string UUID route (404); its fixture now uses a genuinely typed
invalid legacy auth body, preserving its original 422/list assertion. The
corrected dedicated test passed before the integrated run. Full gate
3 passed the final corrected tree before local acceptance. No existing oracle, protected
fixture/config, gate, or assertion was weakened.

Late source review found request-lifetime authentication retained a database
connection while the group service opened its independent transactions. Both
GET and PUT reproduced QueuePoolTimeout with a shared one-connection pool.
Authentication on the new group routes now completes and releases its own
short session before service work, retaining the existing token/profile checks.
The returned profile is detached before commit, so expiration cannot cause
later implicit database access. Legacy authentication stays unchanged.
The same GET/PUT regressions pass with commit expiration both on and off;
two concurrent authenticated requests release all connections before entering
the service barrier. Inactive/deleted profiles still receive 401 and create no
entry or due. The integrated 134-check matrix passes without changing the pool
limits, timeouts or original failure assertions. One lint invocation used a
repository-relative path from the API directory and reported E902; the corrected
absolute-path checks pass, with no source or assertion change for that error.

## Weekly billing implementation (222, locally verified)

The corrected unmodified full gate passed all 12 checks: backend 1,794,
frontend 1,418, seeded journey 1, zero skips. Verified tree
`63483d4ab47aae9bffc665348ec185f7c9af161e` matches local commit
`7a98d95deb0eeaa82f4612b4a8ef29d80e0eaddd`; log `.local/overnight-two-games/222-gate-attempt2.log`.
The report in that commit records the pending gate at invocation; this next
branch records the result. Subsequent 223 edits are not covered by that stamp.


New-format members owe exactly £1 per intersected Monday-to-Monday London
calendar week, labelled Saturday. A minute catch-up job and natural membership
joins share one league financial lock and immutable obligation/ledger pairing.
No participation, fixture, result, confirmed break or suspension exempts a week.
Departure closes the interval exclusively before catch-up; early future dues
already owed stay owed. Default-disabled installations create no new money.
Recorded provenance continues closing/rejoining after a later gate shutdown,
so reactivation cannot mistake a departed member for continuously active.

Fee reads project intervening weeks without writing future obligations. An
eligible early-entry attempt separately commits its target/intervening dues
before later game/provider work can fail. Pooled ledger credit clears oldest
dues first; queued fake payments count only after the unchanged assignment
route matches them. `paid_through` is a boolean for the exact target, and
unallocated pooled credit is separate from the through-target amount owed.
No bank-reader or OAuth behaviour changed.

Per-member shared TRY/exclusive deletion barriers prevent first joins escaping
account erasure's roster collection. Deletion collects current leagues after
its barrier, takes league locks in order and uses one final departure instant.
Joins fail with a controlled retry instead of waiting on deletion while holding
a league lock. Avatar deletion and join notification delivery hold no financial
or member barrier lock. Unlocked new claims are released with durable revision
tombstones; locked fantasy history stays when group remains unlocked.
Accepted operation replay and actual entry writes are for 223/224.

Focused evidence: 102 billing/unchanged legacy, membership and erasure checks
passed, zero skips; six lifecycle concurrency/assignment/release checks then
passed, zero skips. The final expanded new monetary matrix passed 44 tests,
zero skips, including boundary milliseconds, 167/169-hour DST weeks, same-week
rejoin, closed catch-up, early due retention, actual partial/void picks and
confirmed breaks, new-current-group paid/next-fantasy unpaid, immutable erasure,
queued assignment, commit/rollback recovery and independent sessions.
The discovery calendar was subsequently added to the existing F6 race; its
final focused rerun passed, one test with zero skips. The expanded unchanged
auth/admin/scheduler slice passed 224 tests with zero skips before the last
billing-failure/current-game test additions; the full gate covers all of them. Latest
source lint and mypy pass. The count ratchet only increases 1,749→1,794;
no existing test assertion, fixture, guard or gate is weakened. Independent
source review accepted billing; late API-envelope review found the new fee
errors needed structured `code`/`message` and the exact legacy destination.
Those responses are corrected with an additional HTTP oracle. The first
full gate was interrupted during its backend run after lint/format/mypy passed;
its candidate has no acceptance stamp. A complete second full gate is mandatory.

### Failures, review corrections and limits

The first new billing slice passed 24 and failed two newly written tests:
its legacy entitlement assertion used `None` for an existing boolean helper
whose allowed state is `False`; the intended paid-up entitlement remains
unchanged. Its fake ingestion call omitted required `counting_since`, now
supplied with a synthetic cutover. No existing oracle was edited.
One broader diagnostic named absent test files and collected nothing; the
correct discovered test paths then passed. Strict typing found three optional/
Any errors and generic entry-model inference errors; explicit types fixed them.
Draft import/format lint errors were fixed without suppressions.

Independent review found and corrected monetary defects before the full gate:
Monday departure was planned while still open; cached league deletion could be
stale after a lock wait; an earlier attempt clock could admit a later rejoin
without an early due; name scrubbing could mutate a generated immutable due
note; and independently sampled departure/release clocks could cross a lock.
Closures now precede planning, league/member state refreshes under admission,
entry time follows the financial lock, system dues carry no personal note, and
one departure instant drives closure/stamps/release. Added real regressions
exercise these causes. One failing league now rolls back independently, later
leagues still commit, and aggregate failure remains visible; the next pass
charges only still-pending work. No full 222 gate or verification stamp exists
yet; local API entry flows and both web flows remain for later batches.
The additional envelope oracle initially omitted the legacy fixture's required
stored lock timestamp; its setup now supplies the Saturday 14:30 deadline,
with every error/destination assertion unchanged. The 44-test matrix and final
F6 integration results above precede this isolated response correction. The
45th test passed with zero skips after its fixture correction. Final independent
source review passes; the complete second gate is pending for the final tree.

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

Finish Batch 224 full gate 3 on verified local parent `8dfd28d`, then commit
only its verified tree and stack Batch 225. Continue the
authorised stack through both web flows and final review. Earlier stamps do not
cover the changed tree. Do not merge or push.

Owner review/release follows completion: review the local stack and report,
integrate under normal gates with fresh exact-head CI, create/test a production
recovery point before migration, explicitly ship API then payments on the same
SHA/head with mode off, then release web. Separate exact future league/week
activation requires live opening coverage/quota and supported traffic/latency
acceptance. Natural member use, payments and notification receipt remain open.
