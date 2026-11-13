# Two games per football week — API and persistence contract

13 Nov 2026 · Batch 219 · local implementation contract, inactive in production.
The approved plan and acceptance examples remain authoritative. This document
defines the implementation target; later batch evidence proves behaviour.

## Identity, format and safety

The existing `gameweeks.id` UUID remains the football-week parent (`week_id` in
new API paths), unique by `(league_id, starts_on)`. Add `format` with values
`legacy` (the default for every existing row and old writer) and `two_game`.
For `two_game`, `starts_on` is the Saturday label of the London billing week.
Keep `number` and season derivation; children never become a third ordinary round.
Historical UUIDs, fixtures, prices, points, dues, reversals and events stay intact.
No old pick is copied into a child. A fixture can belong to several games/leagues.

Each child is identified by `(league_id, week_id, game_kind)`, where `game_kind`
is `group` or `fantasy`. It has its own UUID `game_id`, stored UTC instants
`opens_at`, `locks_at`, `window_start`, `window_end`, lifecycle and fixture set.
Group's exact kick-off predicate supplements its window; a range never widens it.
Child/pick composite foreign keys enforce the named league/week/game/fixture.
Parent format cannot change; children require `two_game`, legacy picks require
`legacy`, including writes from older images. Published legacy weeks cannot be
converted by changing a league flag. A week containing dues is already touched.

For new-format and billing-only parents, required legacy `locks_at_utc` stores
the labelled Saturday 14:30 UTC-derived instant, `picks_open_at_utc` is null and
`status` is `locked` as a non-entry sentinel. Only new-format aggregate
finalisation may move it to `settled`; child schedules/statuses are authoritative.
A billing-only parent has no children until eligible discovery. Its sentinel
never authorises a legacy entry, reminder, void/refund or empty-round settlement.
Every legacy open/lock/settle/reminder/dues/default-current selector must filter
`format='legacy'`. Legacy discovery must also exclude activated future cutover
dates before a new parent exists. Its date-collision lookup must see both formats
and skip/refuse a new-format parent before links or mutation, rather than treating
it as absent and attempting a duplicate parent. Direct addressed legacy reads
detect the format and return `409 UNSUPPORTED_FORMAT`; default/list readers
filter out the new format. Database fences reject legacy picks and legacy fixture
membership on new parents, and reject format mutation. Existing old-image
readers/writers remain compatible while the feature is off (no new parents);
new-format activation follows successful API/payments shipment. Use a separate
Monday billing-calendar helper; the legacy Wednesday–Tuesday football-week
helper and historical tests retain their existing meaning.

`TWO_GAMES_ENABLED=false` is the installation default. A separate league rollout
record names `first_week`, `effective_opening` and `suspended`. Both installation
enablement and exact league/week cutover are required. Disabled code creates no
new-format parents, games, dues, notices or provider work. Existing legacy work
continues. Suspension stops new entries/replacements/openings, while billing,
accepted-pick settlement, corrections and history continue for activated weeks.
No activation route or production activation is authorised by this local run.

All paths below are relative to `/api/v1`. Every read requires authenticated
league membership (including retained own historical access under existing
account policy); another league's IDs return `404`, never another member's data.
Every write requires current active membership. All JSON uses snake_case.
Datetimes are ISO 8601 UTC with `Z`; dates are `YYYY-MM-DD`; money is integer pence;
odds are decimal strings. Stored instants decide boundaries before any job tick.

## Schedule and states

| Field/rule | Group | Fantasy |
| --- | --- | --- |
| Eligible kick-off, London | Saturday 15:00 exactly | Saturday 12:30 inclusive to Monday 00:00 exclusive |
| Lock, London | Saturday 14:30 | Saturday 12:00 |
| Opening | Stored league opening policy, never later than lock | Previous eligible Saturday 12:00, including first new week |
| Pick identity | `(week_id, player_id)` | `(week_id, player_id, slot)`; slot 1–6 |
| Fixture claim | Unique `(week_id, fixture_id)` across group | Unique `(week_id, player_id, fixture_id)` |
| Price/points | Neither stored, fetched nor exposed | Positive fresh quote frozen on save; separate leg points |

Fantasy calendar arithmetic uses `Europe/London`, not fixed elapsed-hour offsets.
A consecutive opening-to-lock interval may span 167 or 169 hours across DST.
The group's stored opening follows that league's existing opening-offset policy
applied to Saturday 15:00; null means discovery time. Opening after lock is an
invalid schedule. A child window does not mutate its parent's historical rules.

Lifecycle: `scheduled → open → locked → settled`; `cancelled` is explicit.
Read `entry_state` is derived at request time: `not_open`, `open`, `locked`,
`suspended` or `cancelled`. Discovery has independent `coverage_state`:
`pending`, `unavailable`, `complete`, `confirmed_empty`. Price availability is
separate: `pending`, `available`, `unavailable`, with `observed_at` and age.
An empty, failed or truncated provider response cannot mean confirmed empty,
cancel a week, remove an accepted pick or waive billing.

The calendar stores confirmed breaks with schedule evidence and author. Search
at most 12 Saturdays ahead per pass (configurable operational bound, not a rule
that erases later weeks); persist a cursor and expose unresolved next-card state
when that bound is exhausted. A confirmed break opens the next known eligible
fantasy at the preceding eligible Saturday noon. No evidence means pending,
not a skipped week. Season-end and legacy extra dates never invent a weekday
two-game card. Insufficient horizon/coverage blocks activation, not payment.

## Routes and write protocol

| Method and path | Response | Purpose |
| --- | --- | --- |
| `GET /leagues/{league_id}/weeks/{week_id}/games/{game_kind}` | `200 GameView` | Addressed game, fixtures, own entries, progress, result, fee |
| `PUT /leagues/{league_id}/weeks/{week_id}/games/group/pick` | `200 GroupPick` | Atomically fill/replace own contribution |
| `GET /leagues/{league_id}/weeks/{week_id}/games/group/pick` | `200 {pick, revision}` | Own pick readback; null if absent |
| `PUT /leagues/{league_id}/weeks/{week_id}/games/fantasy/slots/{slot}` | `200 FantasyPick` | Atomically fill/replace one independent slot |
| `GET /leagues/{league_id}/weeks/{week_id}/games/fantasy/slots/{slot}` | `200 {pick, revision}` | Exact slot readback; null if empty |
| `GET /leagues/{league_id}/weeks/{week_id}/fee` | `200 WeekFee` | Paid-through obligation, pooled credit and amount owed |
| `GET /leagues/{league_id}/games` | `200 {games, legacy_rounds, next_cursor}` | All actionable/current games plus addressed history |
| `GET /me/games` | `200 {leagues}` | Batched home summary for all memberships |
| `GET /leagues/{league_id}/weeks/{week_id}/results` | `200 WeekResults` | Format-discriminated historical result |

Existing legacy routes and links retain their responses and behaviour for legacy
weeks. A legacy read targeting a new week explicitly returns `409
UNSUPPORTED_FORMAT` and its exact new destination; a legacy write refuses that
format before fees, odds admission or any pick mutation. A valid legacy W0 write
still works while W1 fantasy is open, regardless of the league's rollout flag.
New-game routes to a legacy week return `409 UNSUPPORTED_FORMAT`. Old backend
responses lacking the optional new summary keep the new web flow hidden.

Group body: `fixture_id`, `market`, `outcome`, `expected_revision`, `operation_id`.
Fantasy adds `odds` (the displayed/confirmed decimal price). `operation_id` is a
client UUID, scoped to member plus exact league/week/game/slot; the server retains
the accepted operation/result. Identical retries return the original success;
reuse with another body returns `409 OPERATION_CONFLICT`. Every current-entry
response carries monotonic `revision` and `operation_id`. An initial fill expects
revision 0; replace expects the observed revision. Two devices cannot silently
overwrite each other's accepted choice: stale revision returns `409
ENTRY_CHANGED` with current readback. No partial slot update is committed.

Validation order: authenticate and authorise the exact target → accepted-operation
lookup/replay → format/feature and current membership → stored opening/lock and
suspension → market/outcome/fixture membership → revision → entitlement → fantasy
quote/admission → atomic uniqueness/save. An authenticated owner can replay the
same accepted operation after the lock or suspension without another mutation,
fee or quote; a changed body still conflicts. Fresh operations remain fully
gated. A response lost just before noon therefore remains reconcilable after
noon. All refusal paths preserve
the previous choice. Persist early dues independently of a later pick refusal;
provider spend likewise survives business rollback. An ambiguous HTTP response
causes addressed readback before resend; equality of selection alone is not
proof that a different slot/week/game operation succeeded.

Group and fantasy are separate records. A group's fixture never reserves it
from fantasy; members may share the same fantasy selection, including one held
by another member in the group. Fantasy's seventh slot and own duplicate fixture
are refused. Partial entries count at 1–6 picks; empty slots have zero points.

## Response fields and refusals

`GameView` includes `league_id`, `week_id`, `week_label`, `week_number`, `format`,
`game_id`, `game_kind`, `destination`, `opens_at`, `locks_at`, `window_start`,
`window_end`, `entry_state`, `coverage_state`, `fixtures`, `my_entries`,
`progress`, `result`, `fee`. New destinations are
`/leagues/{league_id}/weeks/{week_id}/{game_kind}`; legacy links stay unchanged.
Cache keys and offline queue keys include every path identity and the member.

Fixture fields include `fixture_id`, teams, `competition_id`, `kickoff_at`,
`status`, allowed markets/outcomes and the claim status for this game. Fantasy
alone adds `quote` containing prices, bookmaker/provider, `observed_at`,
`age_seconds`, `availability`, `degraded`. A browse snapshot never triggers a
full-card price refill. Group and locked-result reads make zero pricing calls.
Group responses/events omit odds, combined price and points rather than hiding
priced values in the UI. Shared match results carry no shared game points.

Fantasy pick fields include exact target, `slot`, fixture/selection,
`frozen_odds`, `quoted_at`, `provider`, `bookmaker`, `revision`, `operation_id`,
`result` (`pending`, `won`, `lost`, `void`) and `points`. A positive quote must be
no more than 60 seconds old at acceptance; recheck after slow fetch/lock races.
`409 PRICE_MOVED` returns `current_odds`, `quoted_at` and exact slot target.
Confirmation resends that named price; it does not accept an unspecified future
price. A newly published market can be rechecked under the bounded negative
policy instead of being blocked by the legacy six-hour negative cache.

Errors use `{"detail":{"code":"…","message":"…",…}}`:

| Status/code | Meaning |
| --- | --- |
| `401` / existing auth response | Sign in required |
| `404 NOT_FOUND` | No accessible target/membership; feature inactive |
| `409 UNSUPPORTED_FORMAT` | Wrong legacy/new client format, with destination |
| `409 NOT_OPEN`, `409 LOCKED`, `409 SUSPENDED`, `409 CANCELLED` | Stored game boundary/state refuses write |
| `402 PAYMENT_REQUIRED` | `week_id`, `amount_owed_pence`, fee/payment destination |
| `409 FIXTURE_TAKEN`, `409 FIXTURE_ALREADY_PICKED` | Group claim or own fantasy fixture conflict |
| `409 ENTRY_CHANGED`, `409 OPERATION_CONFLICT` | Concurrent edit or mismatched retry |
| `409 PRICE_MOVED` | Explicit named-price confirmation required |
| `422 INVALID_SLOT`, `422 INVALID_SELECTION` | Slot outside 1–6 or ineligible fixture/market/outcome |
| `429 PICKS_BUSY`, `429 TOO_MANY_TRIES` | Shared capacity or per-member abuse refusal, `retry_after_seconds` |
| `503 ODDS_UNAVAILABLE` | No fresh valid quote/provider refusal; preserve old slot |

Format-aware abuse admission permits twelve legitimate saves across the noon
overlap plus edits; new-format defaults are configurable 120 actions/member/hour
and 2,000/league/hour, independent of provider allowance. These are abuse ceilings,
not a supported service promise or membership limit. Legacy limits remain intact.

## Membership, fee identity and allocation

For Saturday label `S`, billable interval is Monday `S−5 days` 00:00 inclusive
to Monday `S+2 days` 00:00 exclusive, London. Store those UTC bounds with the
label. Active intervals are `[joined_at, left_at)`; record every join/rejoin,
never overwrite the provenance of a previous interval. At activation, seed the
current interval from existing membership only from the approved cutover, not
retroactively from inferred historic participation. Overlapping/rejoined intervals
can produce only one due per `(league_id, week_label, player_id)`.

`weekly_fee_obligations` maps that identity to the unique parent UUID, interval
provenance, `amount_pence=100`, `owed_at`, `recorded_at` and existing immutable
`ledger_entries.id` (`round_due`, amount −100). Use the existing ledger, matching
and FIFO allocation, not a second money balance. Create billing-only parents
without requiring child games or discovery. Normal billing is Monday or later
joining; catch-up includes every intersecting active interval since cutover.
Early entry materialises target and intervening weeks while membership remains
active, even before their Monday. Leaving retains all already-owed future dues;
it stops new future obligations. Rejoin in the same week reuses the due.

W0 legacy dues and reversals are never rewritten, recharged or automatically
reversed by this policy. W1 is the explicit first new-format week. Existing
non-membership weeks and weeks before W1 cannot gain new dues. Payments remain
positive pooled league credit with no week earmark; queued bank payments count
only once assigned under the existing matching service. Oldest net obligations
consume credit first, including legacy arrears. A paid W0 contribution is not
blocked by unpaid W1; W1 cannot consume credit ahead of W0.

`WeekFee`: `league_id`, `week_id`, `week_label`, `billing_starts_at`,
`billing_ends_at`, `obligation_pence`, `amount_owed_pence` (through target),
`paid_through`, `pooled_credit_pence`, `payment_url`, `destination`,
`obligations` (parent UUID, stored label and remaining pence). `paid_through`
is a boolean for this addressed target; it is not a payment date. Virtual future
obligations may have a null parent UUID until materialised. A retained orphan
legacy balance has null parent/label and remains oldest in FIFO. Legacy custom
round dates remain their historical labels. Group and every fantasy slot share
the same target-week due. No picks, partial picks, all-void, cancellation,
confirmed breaks, missing fixtures or suspension never waive that due.
Leave/remove/delete releases only unlocked entries, retains locked anonymous
history and owed ledger entries; no automatic refund is authorised.

## Durable provider work and results

Every actual HTTP attempt, including retries and legacy/manual callers, first
commits an independent installation-wide reservation. Rolling timestamped attempts
count for 3,600 and 86,400 seconds; proposed caps 90/450 are configurable
assumptions, not production entitlement. Provider headers/cooldowns can reduce
admission, never mint local quota. A pre-dispatch refusal emits no HTTP request;
record it separately. An uncertain committed reservation stays spent after crash.
Business rollback, conflict, moved-price refusal and restart never refund spend.
No budget transaction/advisory lock spans network I/O. Short leases and durable
fresh snapshots coalesce same-fixture quote work safely across processes; a lease
owner crash expires work, not its spent allowance. Reuse only a fresh positive
quote. Each retry is separately admitted and charged.

Global census follows pages until confirmed complete, subject to a bounded
per-pass page budget and resumable cursor. Store all eligible fixtures before
applying separate windows. A full page is not evidence of completeness. Price
work uses up to ten fixtures/request with fair persisted cursors, provenance,
negative recheck times and snapshot ages. Optional work pauses Saturday
10:00–13:00; noon checks have a configurable five-attempt ceiling. Foreground,
background and settlement still share the same rolling global meter. Model 14,
30 and 100 memberships and larger cards; report refusals/delays explicitly.

Settlement visits distinct picked fixtures whose kick-offs permit results, with
persisted retry times and fair chunks. Commit each completed chunk; a later error
cannot roll it back. Pending/error fixtures move behind other eligible work.
Do not poll unstarted Sunday fixtures during Saturday settlement. Game finalisers
also run when there are no pending picks and no new provider result.

Group result is `no_coupon` at zero picks, `pending` while any submitted leg is
pending, `lost` if any resolved non-void leg loses, `void` if all submitted legs
are void, otherwise `won` once resolved. Missing contributors are explicit and
do not invalidate a non-empty coupon. Group awards no points.
Fantasy wins score the existing decimal `round(frozen_odds × 10)` rule; lost/void
legs score zero. Per-member weekly points sum submitted legs. `entered` means
at least one pick, `slots_filled` is 0–6, and `entry_result` distinguishes
`no_entry`, `all_void`, `pending`, `scored`. Points remain provisional until the
exclusive Monday window end and no pending submitted fixture. A Sunday 23:59
fixture can settle on Monday. Empty/Saturday-only entries finalise once without
a further odds call. Season totals are legacy settled points plus fantasy leg
points, each once; group never enters a scoring denominator.

Fixture corrections recompute all affected legacy/group/fantasy games and
league totals while preserving frozen odds. Audit affected leagues. A stable
result version distinguishes genuine corrections from retry; unique event
claims include league/week/game/kind/version and recipient. Existing mute/quiet
policies apply. Group completion cannot consume a fantasy completion claim.
Fantasy notices aggregate one member's week; zero-entry members alone receive
entry reminders. Every notice has an exact addressed destination and fee week.
No external message is sent by local acceptance work.

Statistics count resolved non-void fantasy legs for leg win rate, points/pick
and best leg return; weekly form/winners aggregate by member/week. Legacy metrics
retain their original contributions. Exports include only the requesting member's
new records. Erasure releases unlocked claims and anonymises retained locked
history under existing policy, preserving financial audit provenance.

## Home and state examples

`GET /me/games` returns each league's `games` array plus `legacy_rounds`, not
one current round. A game carries exact destination, purpose (`entry`/`results`),
deadline, progress and its own `WeekFee`. Return all actionable games, without
an artificial three-card cap. Use batched queries with bounded query growth;
group and locked results never request prices. A fixture-only cache key is invalid.

At Saturday 12:05 in steady state, home shows current group entry (14:30),
current fantasy results (locked noon), next fantasy entry (next Saturday noon).
Current group can be paid while next fantasy is unpaid. At first rollout,
W0's legacy entry/results remains beside W1 fantasy; no current fantasy is
fabricated for W0. At noon, only the named fantasy locks; group's 14:30 remains.
Offline intents are retained per member/league/week/game/slot. Two offline slot
fills survive together; replacing one cannot discard or reconcile the other.

Representative states (UUID values abbreviated here only):

```json
{
  "league_id": "L",
  "games": [
    {"week_id": "W0", "game_kind": "group", "entry_state": "open",
     "locks_at": "2026-11-14T14:30:00Z", "progress": {"picked": 8, "members": 12},
     "fee": {"week_label": "2026-11-14", "amount_owed_pence": 0}},
    {"week_id": "W0", "game_kind": "fantasy", "entry_state": "locked",
     "locks_at": "2026-11-14T12:00:00Z", "progress": {"slots_filled": 3, "entered": true},
     "result": {"final": false, "weekly_points": 0}},
    {"week_id": "W1", "game_kind": "fantasy", "entry_state": "open",
     "opens_at": "2026-11-14T12:00:00Z", "locks_at": "2026-11-21T12:00:00Z",
     "fee": {"week_label": "2026-11-21", "amount_owed_pence": 100}}
  ]
}
```

Every actual card additionally includes its full exact `destination` and target
fields above. A partial group final can be `{"status":"won","picked":8,
"members":12,"missing_contributors":4}`. Zero entries instead returns
`{"status":"no_coupon","picked":0}`; two void submitted legs return
`{"status":"void","picked":2}`. Neither response contains odds or points.
Three fantasy legs at frozen odds 2.15, 3.00 and 4.00 resolving won/lost/void
score 22/0/0 under existing half-up rounding, weekly sum 22; three unfilled slots
score zero. That score remains provisional until the window end and all submitted
fixtures resolve. An entry with only void legs is `all_void`; no saved legs is
`no_entry`, each with weekly sum zero and its normal £1 obligation.

## Acceptance trace

| Case | Concrete field/response or invariant | Test batch |
| --- | --- | --- |
| F1 | Membership interval intersection, `week_label`, `obligation_pence`: 22 Nov 23:59:59.999 owes W1+W2; 23 Nov 00:00/.001 owes W2 only; 20 Nov owes W1 | 220, 222 |
| F2 | Unique obligation across leave/rejoin; unlocked-only release; retain early future `owed_at` | 220, 222, 225 |
| F3 | Immutable `format`, first W1 rollout, W0 ledger IDs/reversals unchanged; one W1 due | 220, 222 |
| F4 | W0 group `200`; W1 slot `402` with target W1; one fee for both games/all slots | 222–224, 226, 228 |
| F5 | Billing-only W1/W2/W3 parents; through-W3 owed 300, payment 100 clears W1, payment 200 clears rest | 222, 228 |
| F6 | Concurrent unique obligation + serialized FIFO allocation, including delayed payment matching | 220, 222, 224 |
| C1 | W0 `legacy_rounds`, W1 `not_open`, no fabricated W0 fantasy; stored `opens_at` | 224, 226–228 |
| C2 | W0 exact legacy entry + W1 fantasy cards, separate `fee`, no noon suppression | 226–228 |
| C3 | Explicit targets, W0 legacy rules and independent W1 slot transaction | 224, 226–228 |
| C4 | W0 old-client success; W1 `409 UNSUPPORTED_FORMAT` before fee/provider/write | 220, 224, 226–228 |
| C5 | W0 results + W1 entry in array; W1 has no earned points on save | 225–228 |
| C6 | Legacy history unchanged, current group/results/next entry and continuous totals | 225–228 |
| Q1 | Rolling 3,600-second attempts: H−2 before hour boundary permits only two after | 220–221 |
| Q2 | Rolling 86,400-second attempts: D−1 before midnight permits only one after | 220–221 |
| Q3 | Attempt survives `PRICE_MOVED`, uniqueness conflict and request rollback; old slot unchanged | 221, 224 |
| Q4 | Three actual retry dispatches create three committed attempts, capped before each | 221, 224 |
| Q5 | `429 PICKS_BUSY` before dispatch; zero HTTP requests/pick mutation | 221, 224 |
| Q6 | Committed reservation/snapshot/operation survives restart and uncertain response | 220–221, 224, 228 |
| Q7 | Concurrent leagues/worker/retry admit only one remaining attempt; budget lock ends before I/O | 221, 224 |
| Q8 | Fresh shared positive quote reused within 60 seconds; stale/missing bounded fetch | 221, 224 |
| Q9 | Committed chunk, charges/results/event claims survive later failure/restart; no duplicate billing/points/notices | 225 |

## Review and release gates

Local completion requires each batch's unmodified full gate, database-backed
assertions with zero skips, independent final review and seeded real local
browser → API → scratch PostgreSQL flows for both games. Keep a recovery journal
and exact-tree evidence. Canonical rows remain unchecked during this local run.

Activation remains blocked on accepted opening fixture/market coverage, daily
account entitlement, supported 14/30/100 load and agreed browse/result delays.
No arbitrary numerical coverage percentage is adopted; passing a finite workload
does not promise every burst. Saturday's observation is separate and untouched.

Before release: owner reviews local branches/contracts; integrate under normal
review with fresh full gates/exact-head CI; create and test a production recovery
point before migration; explicitly ship API then payments at identical SHA/head
with mode off; verify readiness/RLS/legacy behaviour, then release web. Exact
future untouched league/week/opening activation needs separate owner approval.
Natural use, payments and notification receipt remain live acceptance gates.

Protected `AGENTS.md` currently summarises the legacy one-pick/priced model.
Leave it unchanged here; request separately approved alignment during integration.
Neither an older image nor a schema downgrade is a proven data-preserving
rollback; Batch 220 must rehearse populated forward recovery.
