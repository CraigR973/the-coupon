# Two games per week — local implementation report

17 Nov 2026 · frozen local recovery checkpoint. Production unchanged; no shipment,
activation or formal close-out. Canonical batch rows remain unchecked.

## Final verification snapshot and outcome

At this document freeze, nine historical milestones (219–227) retain their
verified local commits. Batch 228 has independent 21-case source review and
strict 30-story desktop/installed-phone acceptance. It remains unaccepted and
uncommitted because the complete canonical gate returned 11 of 12, not PASS.

The latest full run passed all 2,067 backend tests, all 1,496 frontend test
assertions, 38 production-bundle smoke stories and the seeded journey, with zero
skips. The unchanged gate rejected the frontend count because ANSI escape bytes
separated `Tests` from `1496`. This is a confirmed wrapper-environment defect,
not a failed frontend assertion. No PASS stamp exists. The older backend/journey
failures have passing component evidence in full order; the full gate is still red.
The [failed canonical certificate](../.local/overnight-two-games/recovery-canonical-attempt2.certificate.json)
and [complete gate log](../.local/overnight-two-games/recovery-canonical-attempt2.log)
retain that exact-tree result (`2116dae3106bf939c7b6db0d84a614984839f14f`).

The sanitised wrapper dropped the parent's colour controls. Independent read-only
review confirmed installed Vitest enables ANSI with both controls absent. The
concrete fix is explicit `NO_COLOR=1`, `TERM=dumb`, with `FORCE_COLOR` absent in
the sanitised environment. Original source, parser, tests, counts, deadlines,
configuration and full gate remain unchanged. No historical output is replayed,
cleaned into acceptance or used to manufacture a stamp.
Review: [frontend count investigation](../.local/overnight-two-games/recovery-frontend-count-review.md).

Both backend families and the journey family have used all three renewed actual
attempts. Their last component results passed, but another complete gate would
execute attempt four. It therefore requires fresh, exact approval for one further
full local `scripts/ci-local.sh` run (about 30 minutes), with the two presentation
controls above. No extra full gate is run under a silent extension of the cap.
No source repair, release, push or activation is part of that proposed approval.

Strict browser attempt 2 passed all 30 on the failed-gate tree in 249.018 seconds,
zero failed/flaky/skipped, retries zero. The report/STATUS update for this honest
checkpoint changes only documentation. To verify this final frozen tree exactly,
the third and final already-authorised browser attempt runs after this freeze.
Its actual outcome is recorded in
[final-tree browser evidence](../.local/overnight-two-games/recovery-browser-attempt3.json).
No runtime source/test change is made and no failed story is retried hoping for green.

The actual final outcome, accepted tree and matching local commit belong only to
the [final local acceptance certificate](../.local/overnight-two-games/recovery-final-acceptance.json).
It may be created only after an authorised unmodified complete gate passes on
this unchanged document/source tree, the strict browser result matches that tree,
independent runtime review passes, and the explicit local commit matches it.
An absent/failing certificate means Batch 228 is not accepted. Keeping actual
outcomes in ignored evidence avoids document drift or reuse of an old PASS stamp.
The [resumable checkpoint](../.local/overnight-two-games/recovery-blocked-checkpoint.json)
records exact refs, scope, attempts and the missing approval. Production remains
unchanged; owner review, exact-head CI, tested production recovery, same-head
API/payments shipment before web and exact-week activation remain separate gates.

## Recovery evidence before the final freeze

The owner expressly authorised separate baseline recovery, only two new legacy
POST status corrections, a fresh maximum three attempts per failing family
including diagnostics/full runs, and reviewed explicit local commits.
All original failures and prior attempt history remain in this report/journal.
No baseline source patch was justified; no worktree was created. Main,
planning and all nine earlier milestone branch references remain unchanged.

Renewed baseline observation 1 encountered confirmed low-battery system sleep
for 68 seconds, followed by offline Home queries. Its 51.797-second animation
wait and 54.892-second metrics gap coincide with system power records.
This establishes the evening interruption, not the older afternoon timeouts'
cause. The Mac was then on AC and charging; a temporary owned awake assertion
protected verification without persistent power settings or unrelated changes.

Exact unchanged main, canonical runner/test/config, fresh migration 031 and
fake providers then passed the retained journey: one passed, zero failed,
skipped or flaky, in 1.7 minutes. Original 240-second overall and 30-second
teardown limits remain. Evidence is `recovery-baseline-diagnostic2.*` plus
the power/timing investigation under `.local/overnight-two-games/`.
No baseline source recovery commit is invented.

The two newly written mixed-week POST expectations now require the established
201 for initial save and replacement. The correct backend, other response,
pressed-state, destination and database-isolation oracles remain unchanged.
The shared-selection story overlaps Bob's real login with independent Alice
interactions and Bob's real save only after Alice's first accepted selection.
Every original request/success/share assertion, WCAG scan, theme, screenshot,
viewport, focus and 44 px target check remains. All seven Fantasy route queries
and the unchanged cancellation regression are retained.

The strict original runner passed all 30 stories in 221.171 seconds:
15 desktop and 15 installed-phone, zero failures/flaky/skipped, retries zero.
Shared-selection/accessibility completed in 11.089 seconds on desktop and
12.007 on phone, within its original 30-second limit. Those timings reflect
both current environment and overlapping setup; the full improvement is not
attributed to scheduling alone. Browser-tested tree:
`5c890d4d924936f464f70d9f08c2acc4b3ff5593`; only report/STATUS change for freeze.
Evidence: `recovery-browser-attempt1.json` and
`recovery-browser-attempt1-evidence/`, with JSON, logs and desktop/phone
light/dark screenshots. Representative captures were inspected.
The runner still rejects an incomplete count or any failure, skip or flaky case.

One renewed observation-only backend diagnostic passed both unchanged failing
tests on fresh 032, zero skips, in 53.92 seconds. Observed response-before-
notification: 0.198928 seconds to body, 0.240255 afterwards. The burst prepared
twelve 49-recipient audiences and completed all 588 synthetic sends, with no
observed phase/transport exception; original exact Counter, total-send and
returned-pool assertions pass. Observation delegates original code and the
test's actual slow transport, buffering direct JSONL outside file I/O.
Its overhead makes it diagnostic only, not canonical acceptance.

The older full-order missing audience and relative-timing failures retain
unproved causes. In-process migration setup can disable existing loggers, so
absent exception logs did not exclude a swallowed exception. No invented patch,
environment attribution or removed mandatory parent-format fence is used.
Only the final unmodified full-order gate clears their current acceptance
requirement; its actual outcome belongs to the linked final certificate.
Diagnostic evidence is `recovery-backend-isolated-attempt1.*`.

Independent review directly inspected all 21 F1–F6/C1–C6/Q1–Q9 source mechanisms
and meaningful regression assertions plus current Fantasy/Home/queue/session
behaviour. No confirmed material functional defect was found.
Review: `recovery-independent-review.md`. The final canonical gate and full
browser suite revalidate migration recovery/legacy compatibility, provider admission, Monday fees/FIFO/
membership, both entry APIs/replay, settlement/corrections/season totals,
read-only summaries, and earlier Group/legacy web behaviour.

Home now exposes independent exact game/week targets. Six Fantasy slots retain
their own revisions/operations, two offline choices and uncertain-write readback.
Fresh named-price consent precedes each atomic save; Group never reserves
Fantasy choices. Authoritative results retain legacy plus Fantasy points once.
Monday-to-Monday £1 dues remain independent of participation with pooled FIFO.
The single architecture map in BUILD_PLAN records this inactive structure.

```text
Exact Home game/week
        ↓
Slot read + revision → member-bound operation queue
        ↓
Fresh named price → atomic slot → authoritative result/fee refresh
```

Recovery decisions: retain all seven freshness/cancellation queries; overlap
only independent test setup; use temporary awake protection; preserve unexplained
historical failures rather than invent a source repair. No product, money,
authentication or release decision changed.

Reproduce with the pinned Node 24 PATH and pinned CI-local Python running
`scripts/verify-two-game-web.py`. It builds the real web bundle, creates and
migrates disposable PostgreSQL, owns loopback-only API/web servers and uses
fake transports/synthetic members, then cleans up. The exact command remains
below. Production, provider availability, delivery receipt and natural payment
acceptance remain separate and unperformed.

One proposed final canonical invocation was interrupted before its seeded
journey for a provider-environment review. The agent mistakenly interpreted
fake transports as requiring global ODDS_PROVIDER=fake. The actual request
requires fake football/odds/banking transports and synthetic credentials.
Its full backend passed 2,067 tests with zero skips; guardrails, installer,
deployment, lint and types passed. Frontend output was partial at interruption;
its count-read failure is not a confirmed unit-test failure. No full PASS or
stamp is claimed. Only owned gate descendants were interrupted.
Read-only preflight found that global fake would fail the unchanged test of the
oddsapi default. The full rerun therefore leaves ODDS_PROVIDER unset for that
configuration oracle, while preserving fake/injected transports and synthetic
credentials. No production credential file is loaded; the canonical E2E server
binds FakeBetfair. No test, gate or provider implementation is changed.
Superseded output/certificate remain in recovery-canonical-attempt1.*.
The unnecessary interruption costs another full gate; it is not a source repair.
The corrected run is backend family attempt 3 of 3. The interrupted invocation
never executed its reserved canonical journey; that cancelled reservation is
retained separately, leaving two actual journey runs before correction.
The final strict 30-story suite also runs once more on the exact final frozen
tree, within the approved three-attempt bound.
Actual final outcomes remain only in the linked ignored certificate.

## Historical milestone evidence

Batch 219 contracts passed independent review
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
Batch 224 fantasy API passed full gate 3: backend 1,963, frontend 1,418,
journey 1, zero skips. Verified tree `f219e657a98d9d5d20faa0ac3eeb68b02dfc319d`
matches local commit `f29adbc0a6f09669adf8966d91e8edd96ff691e0`; log
`.local/overnight-two-games/224-gate-attempt3.log`. Eight existing AsyncMock
coroutine warnings remain in the backend log. Batch 225 passed all 12 checks:
backend 2,028, frontend 1,418 and journey 1, zero skips. Verified tree
`fab96dcde4f36e34cef455aa44b147f310594aaf` matches local commit
`92c903b776739d6c2a285774aa608dd1dd2f4f96`; log
`.local/overnight-two-games/225-gate-attempt1.log`. Backend took 1,772.42 seconds
and retained the same eight existing AsyncMock warnings. Batch 226 passed all 12
checks: backend 2,067, frontend 1,418 and journey 1, zero skips. Verified tree
`70f382573b7cee924584d264a2fcc24e3ae4e40c` matches local commit
`94659e26bd9426ce3b4e5409c3b7d0d4b589c5ad`; log
`.local/overnight-two-games/226-gate-attempt1.log`. Its committed report records
the pending invocation; this branch records the result. Batch 227 passes all 12
checks: 2,067 backend / 1,472 frontend / journey 1, zero skips. Exact tree
`3b140c8111958301719c451b147e5ca624a829fa` matches local commit
`1fbc6df28fbc2319491a9f34dd06733f958d6841`; log
`.local/overnight-two-games/227-gate-attempt1.log`. Backend raw summary is
2,067 passed, eight existing AsyncMock warnings, 1,124.90 seconds. This later
branch records that result; the report in 227 records its pending invocation.
Batch 228 has a draft Fantasy editor; browser acceptance is blocked as above. Production unchanged.

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
| 224 fantasy API | Locally verified; commit `f29adbc` | `feat/batch-224-fantasy-api` / `8dfd28d` |
| 225 results/lifecycle | Locally verified; commit `92c903b` | `feat/batch-225-two-game-results` / `f29adbc` |
| 226 read APIs | Locally verified; commit `94659e2` | `feat/batch-226-game-reads` / `92c903b` |
| 227 group web | Locally verified; commit `1fbc6df` | `feat/batch-227-group-web` / `94659e2` |
| 228 fantasy web | Final candidate; linked certificate records acceptance/commit | `feat/batch-228-fantasy-web` / `1fbc6df` |

## Group web implementation (227, locally verified)

The verified branch is `feat/batch-227-group-web`, stacked on verified 226 commit
`94659e2`. Exact UUID Group/Home/archive routes and target-specific payment panels
are implemented. A shell-level member-bound queue retains choices across route
remounts, reads before sending/retrying the same immutable operation, and ignores
late responses to older choices. Structured 402/409 responses survive a successful
401 refresh; an account switch during refresh cannot dispatch an old member's
choice or install a late token pair. Login preserves exact new-game payment links.
Legacy/inactive Home remains on its existing presentation; enabled Home uses
explicit cards and neutral action copy. Retained history uses the read-only226
results route when the current-entry view refuses access.

The final full gate passes 12/12: 2,067 backend / 1,472 frontend / journey 1,
zero skips. Its 44 explicit new unit cases plus ten automatic viewport cases
explain the 54-test web ratchet. Type checking and lint pass; lint retains 19
existing warnings. Commit `1fbc6df` matches the exact verified tree above.

Browser failures and corrections are retained under the ignored journal:

- Run 1 failed before tests: invalid inherited pgserver locale; the disposable
  runner now pins en_US.UTF-8. New harness Ruff long strings/imports were fixed.
- Run 2 passed 2 and failed 10 of 12: a Group market code leaked the word
  “odds”; human labels now keep Group unpriced. Synthetic disabled activation
  setup, reused seed login counters, lazy Home prewarming and clock setup were
  repaired without changing production limits or any baseline assertions.
- Run 3 was invalid: pausing timers also blocked React Query notifications. Only
  its owned Playwright process was interrupted; owned services cleaned up.
  Date-only fixed clocks now preserve normal timers and standard JWT lifetimes.
- Run 4 passed its first accessibility journey, then timed out during the race
  after two installed-PWA onboarding waits consumed the test budget. Normal
  browser setup removes those unrelated waits; the 30-second timeout stays.
- Run 5 passed two journeys, then exposed a real stale-revision bug in offline
  replacement. An accepted receipt advertised readiness before its authoritative
  GET finished. A paused-refresh component test failed before the fix. Edits
  now wait for refresh, failed refreshes keep controls unavailable and the same
  immutable operation can be checked again. Race evidence now requires both
  actual PUT responses (200 and 409 FIXTURE_TAKEN) and the loser's old pick.

Independent review also repaired session rejection losing its exact return URL,
including #payment; three real refusal-protocol tests cover that redirect.
Accepted operations refresh existing league, standings and results query roots;
query key shapes remain unchanged. API refresh/member-switch, visible Home500,
retained navigation, archive shell context and payment focus fixes are covered.
Run 6 passed the first three, then found a clock setup error: fixed Date does
not fire an existing deadline timer. Running installed clocks with fastForward
now exercise the actual boundary; the production expiry hook is unchanged.
Run 7 passed six, including both locks/settlement/history checks, then its
logout setup wrongly expected Home after Bob signed in; the actual preserved
Group destination is correct. That step now asserts Group and Bob's identity,
while keeping the no-replay/database assertions. Cold archive login also now
uses the shared exact-route predicate; its new mounted test failed 2 of 6 before
that fix. All six new unit files pass 44 tests. Lost/truncated 200 bodies retain
an uncertain operation for exact readback; cold refresh cannot restore an older
member over a newer login. Representative screenshots now preserve actual
1280px desktop and 390px phone viewports in both themes.

Run 8 was not accepted; only its eight desktop checks passed. The
reviewed full web suite passed 1,466 tests across 88 files before the last archive
fix and six new route cases. Independent count review reconciled the unchanged viewport test's automatic
case per TSX file: 1,418 baseline + 44 explicit new checks + 10 new TSX viewport
cases = 1,472. Only that legitimate frontend ratchet is raised; the final gate
must confirm 89 files and exactly 1,472 tests. A final new API test's two unknown
error type errors were fixed with an explicit ApiError instance assertion.

Run 8 passed all eight desktop journeys, then the actual phone UA encountered
the unchanged mobile installation gate before login. Run 9 now models installed
phones and the seeded members having already declined notification onboarding;
no subscription, permission request, product gate or login limit is bypassed.
Run 9 passed all 16 browser checks in 91.37 seconds: eight desktop and eight
installed-phone journeys, zero failures, flaky retries or skips. This covers
browser → real API → freshly migrated scratch PostgreSQL, real JWT/login/refresh,
concurrent whole-fixture claims with 200/409 and preserved loser, offline route
changes and uncertain readback, exact 14:30 boundary, real settlement, voids,
No coupon, retained/legacy history, inactive/404 compatibility, visible 500,
week-specific payment focus and member-switch discard. Counting fake transports
prove Group triggered no quote requests. Dark/light axe includes colour contrast;
320/640 reflow, 44px targets and keyboard focus pass. Actual 390px phone and
1280px desktop captures were inspected; screenshots are test evidence, not a
production preview. This supplemental pass does not replace the full gate.

Independent source review accepted the repaired readiness, lost-body, session
fences, cold archive routes and count accounting. Final type checking passes;
Ruff check/format of the new test-only server and runner pass. The candidate is
verified by the unmodified full 12-check gate: 2,067 backend / 1,472 web /
journey 1 with zero skips.

Reproduce the seeded browser journey from this checkout:

```bash
PATH=/Users/craigrobinson/.nvm/versions/node/v24.21.0/bin:$PATH /Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/python /Users/craigrobinson/the-coupon/scripts/verify-two-game-web.py
```

The runner owns disposable loopback API/web ports and a scratch database, uses
synthetic members/PINs and fake transports, and cleans up its own services.
View `.local/overnight-two-games/227-browser/group-phone.png` and
`group-phone-dark.png` (plus desktop counterparts); JSON stats and API/build logs
are beside them. These files are ignored local evidence. No live credentials,
provider account, banking or external payment link is used.

## Historical fantasy checkpoint before recovery (228)

This subsection preserves the stopped 15:57 checkpoint and original failures.
Its then-current blockers and approval needs are superseded by the recovery
snapshot above; no historical red result or missing criterion is erased.

The branch `feat/batch-228-fantasy-web` is stacked on verified 227. Six separate
slot/revision queries share the shell's exact member/league/week/kind/slot queue.
The chooser preserves named decimal prices, records a fresh UUID for every
explicit PRICE_MOVED confirmation and keeps other slots usable during a save.
Saved prices/results come from authoritative reads, never a historical receipt.
Slot reads poll with the view; explicit empty/tombstone reads cannot fall back to
an older pick. Weekly results, member totals/ties, recent mixed-format history,
exact payment targets and links to the existing canonical season table are shown.
The browser does not add weekly points to the season total itself.

Current focused component/protocol checks: 22 passed, zero skips. Browser suite
now has 30 strict checks (seven new Fantasy plus eight retained Group stories,
each desktop/phone). Its complete pass is blocked. Historical canonical gate 1
passed all 12 checks on candidate tree
`d5fe7719d989ff20d6fb4ebccf95211939074f9c`: backend 2,067, frontend 1,496,
seeded journey 1, zero skips. The production-bundle deep-link smoke also passes.
This is canonical-gate evidence for an unaccepted candidate, not Batch 228
acceptance. The log and identity certificate are
`.local/overnight-two-games/228-gate-attempt1.log` and
`228-gate-attempt1.certificate.json`. The staged tree stayed unchanged during
that run. Later report/status changes are not covered by that first stamp.

The final unmodified gate 2 ran from 14:16 to 15:40 UTC on 16 Nov and failed;
10 of 12 checks passed on frozen tree `5a96fd6f6b86b2f68718fe469073e9b78bb71a84`.
Only STATUS.md and this report differed from gate 1; runtime source and tests
were identical. Backend: 2,065 passed, two failed, zero skipped, eight existing
AsyncMock warnings, 3,884.56 seconds. Frontend: 1,496 passed across 92 files,
zero skipped, 362.58 seconds. Lint, format, types, frozen dependency install,
deployment assertions, build and all 38 production-bundle smoke cases passed.
The seeded journey failed: zero passed/skipped/flaky, one failed. Its exact
tree/result and full raw output are retained in
`228-gate-attempt2.certificate.json`, `228-gate-attempt2.log` and
`228-gate-attempt2-all-raw.log` under the ignored evidence directory.

The gate's staged tree and parent remained unchanged and no unstaged edits
occurred. There is no canonical PASS stamp. The wrapper's
`candidate_identity_matches: false` includes the missing PASS-stamp check;
it does not indicate observed source drift. This report/status update follows
the red run. Its exact final staged tree is saved separately in
`final-review-checkpoint.json`; that checkpoint verifies scope and identity,
not acceptance. No earlier stamp verifies the updated final document tree.

### Latest canonical failures and classification

1. The unchanged response-before-notification test failed for 12 members:
   response 0.512749913 seconds versus fan-out 0.413683573 seconds. HTTP 201,
   all 11 recipients and the minimum real fan-out duration passed. Independent
   review confirms sends are scheduled after the response with BackgroundTasks;
   the assertion's error text does not prove inline sending.
2. The unchanged 12-pick/50-member burst received all twelve HTTP 201 responses
   but failed its exact notification Counter. The abbreviated diff reports one
   identical endpoint and 49 differing endpoints. It suggests an absent audience
   but does not establish the exact actual send total. The expected total is
   588; the later pool-check assertion was not reached. This is not a timing
   assertion. No matching background exception is present in the captured log.
3. The unchanged seeded journey exceeded its 240-second overall deadline near
   the final registration step; the page remained `/register` instead of `/`.
   The API records successful registration/HTTP 201, without a registration
   rejection, 429 or 5xx. Trace teardown also exceeded 30 seconds and its zip is
   truncated. Client navigation versus aggregate elapsed time remains unresolved.
   All 68 preserved evidence files are in `228-gate2-journey-evidence/`.

Classification used bounded comparisons, not another full gate or altered
assertions. Both named backend tests are byte-for-byte identical to main.
The exact two tests on exported main `dfb39fe`, freshly migrated to 031, passed
in 73.79 seconds with zero skips. The same tests on the unchanged candidate and
fresh 032 then produced one failure/one pass in 78.50 seconds: response timing
failed again at 0.379385182 versus 0.303981636 seconds, while the burst's exact
Counter, 588 sends and free-pool assertions all passed. Thus the candidate timing
failure is reproduced; the full-order notification shortfall is not reproduced
in isolation. The latter pass does not erase the earlier failure.

Source review found no confirmed timing cause. Existing legacy links add no
format-read SQL; free legacy dues remain query-free and imports precede the
timed request. Migration 032 adds the mandatory parent-format fence lookup to
legacy pick writes; its cost was not measured and it was not removed. There is
no evidence justifying a source fix or a claim that load/environment caused
either backend failure. The timing check has failed twice; another run is not
used to fish for green. Diagnostic logs/JSON are
`228-main-pick-tests-diagnostic1.*` and
`228-candidate-pick-tests-diagnostic1.*`.

The exact unchanged canonical journey runner body and test were then run on a
read-only main source export, fresh 031, fake providers and the same deadlines.
It also failed: zero passed/skipped/flaky, one failed, 240-second story timeout
and 30-second trace teardown/truncated zip. Main's output does not establish
the same registration stop. This reproduces a red main journey check, not its
underlying cause. Evidence is `228-main-journey-diagnostic1.log`, its JSON and
`228-main-journey-diagnostic1-evidence/`. AGENTS.md and the saved prompt require
stopping the affected chain and recovering the baseline separately. No baseline
fix, third full gate or further browser retry is folded into this batch.

All comparisons used synthetic credentials, loopback servers and disposable
databases without changing a checkout, branch, worktree, test, deadline or gate.
An initial diagnostic database startup inherited an invalid locale before any
test ran; pinning the helper process's LANG/LC_ALL corrected that environment
error. The raw-log observer raced temporary-log cleanup and reported FileNotFound
after preserving the gate output; it did not affect the gate. Optional py-spy
inspection was refused because macOS required root; no escalation was attempted.
The apparent slow backend run continued to completion; the proposed unbounded
future-week catch-up hypothesis was rejected by source review, not patched.

Independent cumulative source review of 219–227 found no confirmed material
breach in billing, quote admission, provider accounting, replay or results.
Independent 228 review found the stale cached-slot and explicit-null precedence
issues described above; both have source fixes and semantic regressions.
The stronger noon browser assertion also exposed stale Home cards in the mounted
shell. Home now refetches at exact opens/locks, rearms after successful reads and
polls enabled results every 30 seconds. Inactive installations do not gain that polling.

Failures and fixes so far:

- Browser 1: zero passed, one failed, 29 not run. A selected new control's light
  hover colour failed contrast; new editor controls now use the established
  outline/surface styles. No shared style, axe rule or threshold was changed.
- New unit run 1: 11 passed, four failed because test actions preceded the
  authoritative initial revision read. Waiting for enabled controls gives 15/15;
  adding passive settlement/correction and tombstone regressions gives 17/17.
- Browser 2: four passed, one failed, 25 not run. Advancing timers by 36 hours
  correctly fired the unchanged ten-second request deadline on a held receipt.
  The late-packet scenario now advances server/browser wall time with the
  documented setSystemTime API, preserving normal elapsed-time deadlines.
  Exact lock scenarios retain running timers and fastForward.
- Browser 3: three passed, one failed, 26 not run. The new simultaneous-state
  assertion exposed stale Home cards after noon. Deadline, passive result and
  inactive-poll regressions now pass with the Home refresh fix.
- Browser 4: one passed, one failed, 28 not run. A route was taken offline
  before its fresh reads completed. A background network failure also hid the
  cached Fantasy view. Cached views now survive network errors visibly, and a
  known offline slot can queue from its last received revision; HTTP/auth refusals
  remain blocking. Dispatch still requires exact fresh server readback. A mounted
  regression proves cached-view survival and zero blind writes. The browser waits
  for known revisions before going offline.
- Browser 5: zero passed, one failed, 29 not run. Sequentially prewarming eight
  synthetic quotes consumed the first story's 30-second budget. The fixture now
  uses the actual SharedQuotes eight-event chunk in one counted fake
  transport request. No timeout, quota, assertion or gate was loosened.
- Browser 6: zero passed, one failed, 29 not run. The fixture bulk prewarm
  selected background admission during the real opening pause. Explicit synthetic
  prewarming now uses foreground admission, as the prior get_fresh calls did.
  The actual budget/pause controls and production callers remain unchanged.
- Browser 7: zero passed, one failed, 29 not run. The unchanged 30-second
  story deadline expired before Group loaded, after three successful Fantasy
  saves. Independent trace review found an 8.6-second seed repeatedly hashing
  the same synthetic PIN. The guarded harness now hashes that fixed PIN once
  at startup; all profiles still use normal bcrypt login verification. This is
  the second duration failure; the corrected run is the third permitted attempt.
- Browser 8: one passed, one failed, 28 not run. The first story now meets
  its unchanged deadline. Reconnecting two offline fills resumed 20 reads,
  including seven for an abandoned Fantasy week; both writes reached 200,
  but confirmation missed its unchanged five-second check. Fantasy reads now
  consume React Query cancellation signals, so leaving a route cancels its
  paused reads while the shell-owned write queue survives. A new regression
  retains the mounted query client across offline navigation and reconnect.
- A draft type check rejected the new regression using Playwright-only `exact`
  in Testing Library. Anchored role-name matching preserves exactness; no
  assertion or suppression was relaxed.
- Browser 9: four passed, one failed, 25 not run. Offline fills/reconciliation,
  repeated price consent and noon/early payment pass. The late-results story
  reached the canonical table with 52 points, then used a heading locator for
  the existing paragraph season caption. The new test now requires the actual
  league heading and the exact season caption; its 52-point, correction and
  legacy assertions remain intact. Existing page/tests were not changed.
- Browser 10: five passed, one failed, 24 not run. The complete late-results,
  canonical 52-to-30 correction and legacy navigation story passes. The new
  away-choice helper requested a two-decimal button name although quotes retain
  four decimal places. The helper now names the exact server price; all result,
  tie, all-void and no-entry assertions remain unchanged.
- Browser 11: zero passed, one failed, 29 not run. The first story exhausted
  its unchanged 30-second overall deadline during light-theme axe. Shared-selection
  database assertions, dark-theme axe and captures had already completed; this
  does not prove an individual product or accessibility defect. It is the third
  total-duration failure (5/7/11), so no further retry, timeout increase or story
  split is authorised. Evidence is preserved in
  `.local/overnight-two-games/228-browser-attempt11-evidence/`.
- Independent browser diagnostic 1: five desktop stories passed, including partial
  zero-point ties/all-void/no-entry. Mixed-week navigation then failed because the
  newly written first legacy save assertion expects 200; the unchanged legacy
  route and baseline HTTP tests require 201, including replacement. The assertion
  remains unchanged. Twenty-two checks did not run. This diagnostic cannot accept
  the milestone; evidence is in
  `.local/overnight-two-games/228-independent-browser-attempt1-evidence/`.
- The first launch of the remaining diagnostic used an unquoted PATH containing
  an application name with a space; the shell refused before any test started.
  Quoting the environment assignment corrected the invocation without source edits.
- The new cached-view unit initially asserted before React Query notified the
  render; awaiting the visible error preserves its assertions. All 21 new cases
  passed at that checkpoint; the later cancellation case brings the current total to 22. Initial formatter path/cwd mistakes made no source change; the correct
  targeted formatting completed. New harness import sorting was fixed, without suppression.

Independent final source re-review accepts the offline guards, slot and Home
freshness fixes, per-target price consent and mixed legacy/Fantasy interaction
coverage. Runtime acceptance remains the full browser/gate responsibility.

The remaining independent diagnostic passed all 26 selected browser stories in
4.9 minutes: five Fantasy plus eight Group stories on both desktop and installed
phone, zero failures/flaky/skipped, retries 0. This proves two offline slot fills,
uncertain replacement reconciliation, repeated price consent, both noon states,
target-specific early payment, Sunday/late receipts, 52-to-30 correction,
partial-zero ties/all-void/no-entry and all retained Group stories on this draft.
The shared-selection/accessibility and mixed-week story families were not rerun;
these 26 passes cannot replace the full 30-story acceptance. The unchanged runner
correctly refused the incomplete count; the ignored wrapper labels it diagnostic
only. Evidence: `.local/overnight-two-games/228-independent-browser-remaining/`
and `228-remaining-browser-attempt1.log`.

Final independent candidate re-review found no additional confirmed material
production-source defect. It confirmed that the two new mixed-week response
expectations, rather than legacy API behaviour, require review. Its durable
notes are `.local/overnight-two-games/final-review-notes.md`.

To reproduce the full local browser flow after the verification blockers are
reviewed, run from the repository with the pinned Node directory on PATH:
`/Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/python /Users/craigrobinson/the-coupon/scripts/verify-two-game-web.py`.
This builds the actual web bundle, migrates a disposable local database and
starts loopback-only fake-provider API/web servers, then cleans up its servers.
The complete runner currently fails; do not treat its diagnostic subsets as
acceptance. Preserved desktop Fantasy images/traces are in
`.local/overnight-two-games/228-browser-attempt10-evidence/` and
`228-browser-attempt11-evidence/`; no completed Fantasy phone accessibility
capture is claimed. Group desktop/phone images remain in `227-browser/`.
The first canonical gate passed all 12 checks on its exact frozen candidate,
including the 22 added unit cases and two automatic viewport cases (1,496 total
frontend tests). The second full gate failed as detailed above. Its certificate
records the frozen tree, unchanged parent, 16 explicitly staged files and absent
PASS stamp. Later report/status corrections are identity-checked in the final
ignored review checkpoint but have no canonical PASS. No passing subset or
historical gate accepts Batch 228 until both the full canonical gate and all
30 browser checks pass on the final candidate.

No Batch 228 milestone acceptance, commit, production change or close-out is
claimed. Canonical stamps apply only to their recorded candidate trees; the
required full browser acceptance remains red. Browser evidence is retained under
`.local/overnight-two-games/228-browser`.

## Addressed read APIs (226, locally verified)

The verified branch is `feat/batch-226-game-reads`, stacked on verified 225 commit
`92c903b`. Home, league-games and exact-week results use one repeatable-read,
read-only snapshot and typed cards. Every actionable target remains outside
parent-key archive pagination. Group stays unpriced; fantasy exposes six exact
receipts and weekly results, with only public member/week aggregates after lock.
Loaded ledger/membership projection reuses pooled FIFO without creating dues;
legacy fees keep the recorded-round policy. Weekly form aggregates before its
five-week limit and preserves no-entry/all-void. Unknown next opening stays pending.

The API scheduler now composes one payment receipt per claimed payment using
those same real targets in its existing transaction. Current paid Group and
unpaid next Fantasy remain separate entitlements. Unavailable entry uses an exact
known payment target without promising a pick; a billing-only parent invents no
child. The payments process and pooled assignment remain unchanged.

The final focused matrix passed 139 tests, zero skips, in 45.12 seconds,
including 39 new read/receipt cases and 100 unchanged Group/legacy payment cases. They cover
C1–C6 actual legacy/new writes, actual concurrent W0 replacement and W1 save,
FIFO parity/intervening fees, both exact locks, three simultaneous targets,
five leagues and ten actionable cards with unchanged query count, both-child
archive pages, readonly repeatable snapshots, six-leg weekly aggregation,
no-entry/all-void/late join, global/exact-off retained totals, suspension,
retained pending history and delayed HTTP payment assignment with concurrent
single receipt claim. The isolated production-environment payments import
checks no API settings dependency. The no-child HTTP/receipt regression confirms
no invented game, fee, provider work or pick promise. Independent source review
passes after the recorded fixes. Its full gate passed all 12 checks on the exact
tree above; the frozen report recorded the pending invocation.

Independent review found malformed typed cursor payloads causing 500, inconsistent
locked Group audiences, unavailable-entry receipt links falling back to legacy,
deleted leagues starving other receipts, departed pending history disappearing,
a departed member's still-open sibling appearing actionable, and inactive
fantasy form links leading to 404. Source fixes and new regressions address these
without weakening existing oracles. The historical audience is membership at
lock plus accepted owners; pre-lock roster behaviour stays current.

New test setup failures were a shadowed fixture parameter, missing interval
provenance, a legacy route mistyped as `/my-pick`, and attempts to update an
immutable announced opening. Setup now uses valid provenance, the actual legacy
route and initial custom schedules. A new early-entry assertion initially used
the legacy refusal name; the saved contract explicitly defines new-game
`NOT_OPEN`, which the new test now checks. Existing assertions are unchanged.
The no-child test initially queried a nonexistent ProviderWork column; its
assertion now checks the actual whole work table is empty, a stronger negative.
Ruff/import/type iterations used explicit source types and normal imports,
including WeekFee's `amount_owed_pence`, with no suppressions. Mypy passed 133
source files after the last form filter. Collection is 2,067, exactly 39 above
the verified predecessor; only the legitimate backend count ratchet is raised.
The unmodified full gate passed with zero skips and no production-bundle override.

Group web is locally verified in 227; Fantasy editor acceptance is blocked in 228. The production checkpoint remains unperformed
under the owner's local-only exception: no recovery point, shipment, live setting,
provider/banking probe, activation or formal close-out is claimed.

## Results and lifecycle implementation (225, locally verified)

The active branch is `feat/batch-225-two-game-results`, stacked on verified
224 commit `f29adbc`. Its full unmodified gate passed on the exact tree recorded above; the report in that frozen commit recorded the pending invocation. Read APIs and Group web are verified in 226–227; Fantasy web acceptance remains blocked in 228.

Settlement now takes a persisted, leased unit for each distinct picked fixture.
One counted result request serves eligible legacy, group and fantasy claims
across leagues. Every completed unit commits independently; pending/error work
moves behind ready work. A cancelled request retains its lease and spent quota.
A reclaimed token or a later manual generation rejects an older response.
Shared fixture observations are rechecked under a Fixture SHARE fence before
claim locks: reinstating a postponed match cannot apply an earlier inferred void
or reuse an old provider void against a later accepted week. Already settled
historical legs retain their results. No business or budget session spans HTTP.

Group resolves without a price or point calculation. Fantasy sums independently
rounded frozen leg prices, keeping its result provisional through the exclusive
Monday window end and any late pending leg. Provider-free finalisers cover empty
and Saturday-only weeks and recover legacy rounds whose last chunks committed
independently. The same aggregate joins a UNION ALL of legacy and fantasy legs,
so each contributes once; group contributes no scoring rows. Fantasy void legs
are excluded from leg denominators; existing legacy void metrics are retained.
A late 30 Jun Sunday result belongs to its stored Saturday's season. Weekly
winners compare entered weekly sums; no-entry/all-void entries are excluded and
scored zero-point ties remain eligible. Weekly form presentation follows in 226.

Shared HTTP correction updates resolved claims in every affected league, with
one audit per league, immutable frozen prices, separate recursively unpriced
group changes, and semantic result versions. All four manual writers use the
same ordered league locks and per-fixture result generation. Scoped legacy
correction/settlement/void fences in-flight results without promoting its local
input to global fixture truth. Repeated correction is a no-op; a genuine later
change advances identity even when restoring earlier global input.

Game opening, lock, reminder, final result and correction facts have independent
recipient claims and exact destinations. Reminder delivery rechecks zero-entry
status. Existing mute and quiet-hour policy remains authoritative. Explicit
cancellation survives recomputation and suppresses entry lifecycle notices;
accepted results, history, corrections and weekly billing remain retained.
Legacy result/correction copy is frozen in the result transaction and sequenced
per parent so queued corrections follow the original result. The mixed-mode
correction HTTP response reports `members_told=0` and `delivery_pending=true`;
the enabled minute worker prepares inbox/claims, commits, closes its session,
then invokes transport. This is delivery pending, never proof of receipt.

Push retains the existing at-most-once limitation: a crash after claim commit
can lose an external send, while the inbox survives. Concurrent external
transports can arrive out of order; local sequencing is not a provider delivery
or receipt guarantee. All verification uses fake transports, never live push.
Requester-only export includes new entries, operation identities, membership
intervals and weekly dues without raw other-member/provider payloads. Actual
HTTP erasure releases unlocked group/next-fantasy entries, retains locked
frozen history and already-owed fees, and anonymises the profile.

Focused evidence before the final matrix: 42 new checks passed in separately
migrated scratch databases; mixed-statistics and June/July late-Sunday checks
passed 2/2; held-lock/concurrent/scoped manual HTTP races passed 6/6; the expanded
55-check new matrix passed with zero skips. During paused real counting-transport
settlement, next-week entry plus financial commit took 0.093–0.101 seconds in
local samples, with zero sessions held during HTTP. This is not supported-load
or production latency acceptance. These focused checks preceded the full 225 gate
recorded above. Production performance acceptance remains open.

Iteration failures and repairs (all retained assertions): the first expanded
matrix had a missing lifecycle import (30 passed/1 failed); the first lifecycle
matrix used a tuple as an object (10 passed/1 failed); a later integrated matrix
missed a GroupPick import (97 passed/1 failed). Erasure setup tried to enter next
week before its opening (17 passed/1 failed); its clock now advances to the
approved Saturday noon. A new legacy-outbox capture initially filtered a field
absent from the established legacy notice payload; it now selects the actual
league identity. New fixture SQL length/import/format and mypy annotations were
corrected. One lint command used a wrong relative directory; rerun uses absolute
paths. No baseline fixture, assertion, skip, timeout or gate was changed.

The combined subset of new tests plus selected old notification/scheduler tests
finished 188 passed/3 failed. Old notification fixtures had committed only their
synthetic competition into the global fixture pool, so later old refresh tests
narrowed discovery to that unrelated pool. The unchanged scheduler module then
passed all 42 checks on a fresh migrated scratch database (39.35 seconds).
No old assertion, fixture, source expectation or gate was altered. The full
canonical gate remains required with its normal ordering and complete seed set.
A separate new 60-check matrix passed in 49.60 seconds with zero skips; the two
new shared-correction scope-race checks passed in 9.69 seconds. Shared correction
now locks pending as well as resolved claim leagues and refuses a newly appearing
league with `409 RESULT_SCOPE_CHANGED` before any mutation. Queued entry notices
also recheck cancellation, suspension and the current deadline. Cancelled result
views use persisted finality, so accepted results do not stay provisional forever.

Independent review found and prompted actual source repairs: legacy-only locks
were skipped; non-empty all-resolved legacy recovery was missing; moved-future
postponements were not eligible; a preloaded result generation could be stale;
queued reminders could target a new entrant; UUID order could reverse game
result versions; two manual parent reads could miss settlement while waiting;
legacy correction hash order could reverse frozen notices; reinstatement could
reuse stale inferred/provider void; cancellation state could be overwritten;
shared→scoped→shared correction could reuse a notice identity; and shared
correction could discover a newly resolved league without owning its lock. Dedicated
regressions cover these repairs. The final expanded new matrix passed 65 checks, zero skips, in 54.98 seconds;
the additional cancelled-result HTTP views passed 3/3. A final measured
concurrent-entry run passed: paused-settlement entry plus fee commit took
0.343453 seconds; settlement completion and addressed result visibility while
another next-week slot committed took 0.883836 seconds. Earlier samples are
recorded above; no supported traffic or production threshold is claimed.
Independent source review confirmed the repaired races and found no further
material defect in its scope; its agent subsequently reached a usage limit.
The subsequent full gate passed all 12 checks. Backend collection is 2,028:
1,963 predecessor tests plus 65 new cases. The count ratchet rises only by those
new cases; frontend 1,418 and journey 1 are unchanged. New future-dated integration tests use an
additional fully migrated database in the gate's scratch PostgreSQL cluster,
preserving installation-wide selection and all baseline fixtures/data/oracles.

## Fantasy API implementation (224, locally verified)

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
gate 2 was later interrupted for cumulative findings; full gate 3 subsequently passed.

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
At that checkpoint those two files collected 87 new tests. The later cumulative repairs and verified 224 commit are recorded above.

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
Full gate 3 verified these independently reviewed cumulative repairs
on the exact 224 tree named above. Earlier 221/223 stamps remain historical evidence for their
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
charges only still-pending work. At that historical checkpoint no full 222 gate or verification stamp existed;
the corrected gate subsequently passed as recorded above.
The additional envelope oracle initially omitted the legacy fixture's required
stored lock timestamp; its setup now supplies the Saturday 14:30 deadline,
with every error/destination assertion unchanged. The 44-test matrix and final
F6 integration results above precede this isolated response correction. The
45th test passed with zero skips after its fixture correction. Final independent
source review passed; the complete second gate subsequently passed as recorded above.

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

## Final local action and separate release gates

At this document freeze, the remaining already-authorised verification is the
third strict 30-story browser run on this exact tree. Preserve its actual outcome,
then stop for fresh approval before any further complete gate: backend and
journey renewed attempts are exhausted. The concrete request is one additional
full local `scripts/ci-local.sh` without SKIP_PROD_BUNDLE, with explicit
NO_COLOR=1 and TERM=dumb, FORCE_COLOR absent, and no source/test/gate change.

If that additional run is approved, its pass must cover the full backend in
canonical order, all database tests, frontend, 38 production-bundle cases and
retained seeded journey. Record actual totals/skips and exact stamp/tree.
Only after that gate, the exact-tree browser and independent runtime review pass,
commit the explicitly reviewed 16 files locally and prove the commit matches.
Preserve original failures and all actual attempt counts. Do not edit this
frozen document to reuse a pass: the linked final certificate records any later
accepted outcome and local commit. Production release remains separate.

Owner review/release follows local acceptance: review this report and local
stack, integrate under normal gates with fresh exact-head CI, and create/test a
production recovery point before migration. Separately authorise API then
payments shipment on the same SHA/migration head with mode off, verify readiness/
RLS/legacy behaviour, then release web. Exact future untouched league/week/
opening activation requires separate owner approval plus accepted live opening
coverage/quota and supported traffic/latency evidence. Natural member use,
payments and notification receipt remain open.
No merge, push, PR, deployment, remote migration, live setting, activation or
provider/banking probe is authorised or performed by this local recovery.
