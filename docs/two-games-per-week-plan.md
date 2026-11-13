# Draft plan: two games in each football week

**Status:** revised planning draft, 12 Nov 2026, incorporating all eight findings
in `docs/two-games-per-week-plan-review.md`. The review remains the record of the
earlier draft. No build batch has started and no live league setting has changed.
The ten slices below now map to Batches 219–228 in `docs/BUILD_PLAN.md`. The owner has
resolved all four rule decisions: £1 per member every week regardless of play
or outcomes, with decisions 2–4 approved. Provider feasibility and its concrete
capacity/coverage evidence remain open before live activation. Local implementation
and fake-provider/database-backed tests can proceed with the new format disabled.

The [11 Nov feasibility assessment](two-games-per-week-feasibility.md) records
23 passing offline tests and confirmed limits in submission admission, retry
accounting, discovery and settlement. It proposes concrete capacity/coverage
criteria and a bounded live-evidence procedure. Those are not live acceptance
or a provider purchase. The owner subsequently authorised all
necessary feasibility checks. The [live findings](two-games-per-week-live-feasibility.md)
now establish both fixture windows, some next-week prices and current account
limits. The [scheduled free-tier assessment](two-games-per-week-free-tier-assessment.md)
supersedes the paid-first recommendation: the current 14-membership spread and
specified rush scenarios fit scheduled retrieval plus fresh slot saves. Larger
rushes still exceed capacity; this is model evidence, not implemented behaviour
or a restriction on league size. Keep the existing free account as the planning
baseline. Early price coverage remains incomplete. A one-off observation is
scheduled for 14 Nov noon to inform the coverage and activation decision. It does
not block batch definition, inactive implementation or local verification.

## Player contract

One league football week has two independent games. Every member owes £1 every
week, whether they play either game or not, whatever they pick, and regardless
of results, voids, cancelled games or fixture-free weeks. This is one weekly
charge covering both games, never a charge per entry or selection. Picking a
future fantasy week early requires being paid up through that week early.
Billing follows Monday 00:00 to the following Monday 00:00 Europe/London,
labelled by its Saturday, independently of whether a game opens (owner, 12 Nov).
The games admit the same members and share one week number, but have their own
fixture sets, pick collections, locks and results. The decisions are recorded
below; the £1 rule supersedes the earlier proposed refund exceptions.

| | Group coupon | Fantasy table |
| --- | --- | --- |
| Fixture window | Saturday 15:00 kick-offs only | Saturday 12:30 through Sunday 23:59 kick-offs, Europe/London |
| Pick deadline | Saturday 14:30 | Saturday 12:00, including Sunday fixtures |
| Contribution | One selection per member, with one pick per fixture across the whole group | Up to six selections per member, on six different fixtures; different members may choose the same selection; a partial entry counts |
| Price | No odds fetched, stored or displayed for new group picks; no combined price | Odds frozen when each pick is submitted |
| Result | The group succeeds when every non-void leg wins; a void leg is neutral and an all-void coupon is void | Each leg scores separately under the existing rounded odds × 10 win rule; losing and void legs score zero; the weekly sum feeds the table |
| Changes | A member may change their contribution before its own lock, subject to the group claim rule | A member may fill or replace slots before the fantasy lock |
| Next week | The Saturday group coupon follows its existing schedule | The next scheduled fantasy week opens at the current Saturday noon pick lock, while current matches are still pending. Consecutive weeks give seven days before the next lock. |

A member may choose the same selection in both games, and that selection is
available to every eligible member in fantasy regardless of who chose it for
the group. Within the group, one member's pick reserves the whole fixture.
Within fantasy, a member can use a fixture once, while every other member can
also use it once. Each submission creates a distinct entry with different
effects; submitting one never submits the other. A group claim never blocks a
fantasy pick or vice versa. The group coupon never adds fantasy points. A fantasy loss
never wipes out another fantasy pick. The group coupon may finish after
Saturday's matches; the fantasy week may
show provisional points as matches finish, but its final result waits for the
Sunday window and pending fixtures. The group coupon's Saturday-only window
must **not** be widened to implement fantasy.

The next consecutive fantasy week opens at the previous Saturday noon and locks
seven London calendar days later, not necessarily 168 elapsed hours across DST.
For 2-1 Hibs, that creates a Saturday overlap: this week's
fantasy results are in play, next week's fantasy picks are open, and this week's
group coupon remains open until 14:30. The home screen must show all three
states without hiding the next pickable week. A discovered fixture card may
still lack live prices a week ahead; an
empty provider response may leave no card. The release gate must measure both
fixture and price availability at opening and show any gap honestly.
For a confirmed break, the next known eligible fantasy card opens under decision
2 below. Skipping a game week does not skip its £1 charge. The app cannot promise
a pickable opening until the target card and its live prices exist.

## Why the existing model cannot simply be relabelled

Today one `picks` row supplies the member's unique coupon leg, frozen price,
points, combined odds and season standings. One `gameweeks` row owns one fixture
window and lock. The backend permits one pick per member and reserves a
selection across members. The front end, reminders and results call that one
pick a completed week. Changing only the pick limit would mix the two games and
their results. Today's home screen prioritises a week being played over the
next pickable week, so it would hide the seven-day fantasy opening.

Two ordinary `gameweeks` in the same football week are also unsuitable:
round identity and numbering assume one normal weekly round, and the payment
ledger charges dues per round. A second ordinary round could charge the fee
twice. The implementation should keep one football-week parent and add explicit
game-specific schedule, fixture membership and pick records beneath it.

The recommended migration is additive. Leave historical `picks` and their
settled results intact; mark each week as legacy or two-game; create separate
unpriced group-pick and priced fantasy-pick records for future two-game weeks.
No historical pick is silently copied into either new game. Old results retain
their original presentation and points. The existing season total carries on:
legacy points already earned plus future fantasy points, each counted exactly
once. There is no retroactive multiplier on legacy weeks. This makes future
six-pick weeks weigh more than past one-pick weeks, which is the direct cost of
continuing the existing total. Multiplying old scores would change recorded
results and is outside the owner's instruction.

The new group fixture limit overrides a league's old `selection` claim scope
for future two-game weeks only. Historical weeks keep their recorded claim
rules. Fantasy does not inherit the group fixture reservation.

## Storage and API contracts

One parent identifies a league's football week, season and week number. Two
child games own their fixture membership, stored London-derived opening and lock
instants, lifecycle and results. Dues belong to the parent; a billable calendar
week exists even when discovery returns no fixtures or both games are cancelled.
Do not use successful discovery or a game's opening as the billing trigger.
The parent must not
be offered or settled as a third legacy game. Legacy jobs and endpoints must
select only the format they understand; unaffected leagues continue unchanged.

The format is immutable once a week is published, opened, charged or picked.
New children cannot attach to a legacy week, and legacy picks cannot attach to a
two-game week. Enforce these relationships in the database as well as the API,
including same-league/week ownership and eligible fixture membership. A settings
edit or emergency suspension cannot relabel populated weeks.

Group storage enforces unique `(week, member)` and `(week, fixture)` contributions.
Fantasy storage enforces slots 1–6, unique `(week, member, slot)` and unique
`(week, member, fixture)`. Other members and the other game remain unrestricted
by those claims. Slot replacement is atomic: a conflict leaves the previous
selection and frozen price intact. Group records and event payloads contain no
price or points; no group read or submission requires a price lookup.

New writes explicitly name league, football week and game; fantasy writes also
name the slot. They never infer the target from fixture identity or a default
current round. Reads, URLs, cache keys and uncertain-write reconciliation use
the same identity. A stale client's legacy submission into an activated week
must be refused without writing a pick, charging a due or calling odds. Legacy
archives and links keep their meaning; define an explicit unsupported-format
response for old clients, rather than returning a misleading empty coupon.

The backend supplies all actionable games and current results per league. The
mandatory Saturday overlap is current group, current fantasy results and next
fantasy entry, each with its own week, game, deadline, progress and fee status.
Do not cap the response at three if another game is also actionable. Home,
history, profiles, results and payment notices use explicit destinations. Ship
these read contracts before either web batch; changing current-round ordering
alone cannot deliver this view.

## Provider feasibility and scheduling

### Implementation evidence and live activation evidence

Define the supported league/member load and coverage criterion, then assess
the whole provider pipeline: catalogue/discovery, both game windows, both
visible weeks, refreshes, cache warming, browsing, six submissions per member,
replacements, result sweeps and retries. Include cold and warm caches and
refusal/cooldown behaviour. A passing pick-only capacity test is insufficient.
Record unresolved live criteria while implementing against fake providers and
scratch databases. They gate activation, not all engineering work. A known
failure in an affected component still blocks that component's completion; an
inactive feature flag does not turn a failing test into acceptance.

The feasibility assessment confirms that reusing today's submission limits
would reject 28 of 78 attempts for thirteen full entries even with warm prices.
Replace member/league submission limits and installation pricing admission as
part of the capacity design; budget current-week last picks and next-week first
picks within the same rolling hour. Count every actual HTTP attempt, including
adapter retries, rather than assuming a cache refill costs one request. Keep
group cards and locked results unpriced. Preserve the current pick-time price
freshness contract; bulk saving is a candidate interaction, not an approved
change. A paid quota alone does not remove these application constraints.

The review found three constraints in current source/tests: two windows over
two dates at the historical 23-competition test shape cost 92 discovery calls
against a cap of 90; the 11:05 refresh overlaps the new final fantasy hour; and
settlement reads all pending fixtures before saving results. These are design
inputs, not current live measurements. The revised design must deduplicate
overlapping discovery where possible, prioritise every card promised at noon,
schedule refreshes clear of the final picking hour or prove a reserved budget,
and settle in bounded, fair chunks that retain completed progress. Avoid polling
not-yet-started Sunday fixtures during Saturday settlement merely because they
have picks. Tests must prove eventual progress under budget exhaustion.

Owner-run evidence must record fixtures, offered markets, priced selections and
competition coverage for the next weekend at the actual Saturday noon opening,
including Sunday. Record the configured bookmaker and quota at that time;
STATUS.md records Betfair Sportsbook on 31 Oct, which is not evidence of current
week-ahead availability. Set the sufficiency criterion before measuring it.
The owner has now authorised the necessary live feasibility checks; the 11 Nov
read confirmed Betfair Sportsbook and 100 requests/hour. The recorded 500/day
limit remains independently unverified. No Betfair-account or Monzo read was
needed. The scheduled opening observation must report actual execution time and
quota limitations; scheduling it is not acceptance evidence.

The live run also demonstrated a lower-cost discovery option: one global
football weekend request, followed by the existing local competition filter and
separate game filters. Both sampled weekends fit one 5,000-event page. Model
pagination and truncated/incomplete censuses explicitly; do not assume all
future weekends fit one page. This candidate replaces duplicated competition
walks and surveys competitions not yet present in the Saturday fixture pool.

If live evidence shows the provider cannot support the rules and capacity,
keep activation blocked and present alternatives with their actual cost. Continue
provider-neutral work that remains valid; revise affected behaviour before
claiming its acceptance. Do not silently reduce
six picks, accept stale prices or shorten the opening window. Fake-provider
tests demonstrate application behaviour only; live feasibility remains a
separate gate.

### Scheduled free-tier candidate — 12 Nov reassessment

The owner asked to spread retrieval through the week and assess realistic member
activity before buying more quota. Use the existing free account as the baseline;
retain independent slot saves and the current positive-quote freshness rule.
The earlier all-members/two-weeks-in-one-hour calculation remains an overload
test, not a demand forecast or evidence that a subscription is required.

The [assessment](two-games-per-week-free-tier-assessment.md) records eight
completed weeks' aggregate first-save timing, 32 offline timelines and 13 passing
current tests. Its candidate uses one durable global budget of 90 attempts/hour
and a provisional 450/rolling-day limit; provider headers can only reduce the
remaining allowance. Count every transport attempt, including retries, manual
operations and legacy callers. The recorded 500/day entitlement still needs
confirmation. These are proposed parameters, not changed production settings.

Queue global weekend discovery and ten-fixture price chunks across the week,
with bounded concurrency and fair, persisted progress. At the observed 77/120
fixture shape, target four price sweeps/day; browsing reads the shared snapshot
and its age. Do not trigger full-card refills per page view. Adapt cadence to
larger cards without silently shrinking competition coverage; visible refresh
latency is a separate acceptance gate. Persist budget/cursor/cache state so a
restart does not create fresh quota or a cold-card request storm.

Pause optional background calls Saturday 10:00–13:00. The model reserves five
actual opening-check attempts from noon, with the remainder queued, while fresh
slot saves may use the shared remaining allowance. All 14-member rush requests
fit at 90 total attempts/hour, but only four of twelve opening price batches
complete in that hour under simulated retry conditions. Therefore prewarming
and this reserve do not establish complete noon price coverage. Resolve that
contract from the actual opening evidence, not from a quota calculation.

Current six-hour negative caching also overrides a requested 60-second price
ceiling. Add a bounded opening/new-market recheck policy and distinguish old
absence from a newly verified absence; preserve strict freshness for a positive
price frozen on a pick. Test provider publication during the protected window,
partial checks and pending/error responses without repeated quota exhaustion.

Settle only eligible picked fixtures, deduplicated across games/leagues, in fair
chunks with each completed result committed. The model's 30/hour, 200/day
settlement allocation is subordinate to the same global budget. Its original
120/day allowance delayed the measured-card stress case into Monday and was
rejected. Larger-card cases still expose multi-day delay: eventual progress
alone does not prove acceptable result latency.

Preserve configured membership limits. Passing 14-member cases does not prove
the configured 30-member rush or reference 100-member load; both remain in the
acceptance evidence with their refusals. Define supported traffic, acceptable
snapshot/result delays and coverage as explicit activation criteria; before activation,
verify the candidate through concurrent HTTP/database tests, restart recovery
and measured attempt/cache/queue rates. Revisit paid capacity only if those
requirements cannot fit, with a separate spending decision.

### Calendar and missing-data states

Store each game's own window and deadlines. Fantasy admits kick-offs from
Saturday 12:30 until Monday 00:00 exclusive in Europe/London; the group admits
Saturday 15:00 only. Refreshing fantasy membership must not widen the group or
move a locked game's announced deadline. Share real fixtures/results while
keeping each game's membership and picks independent.

For consecutive weeks the fantasy opening is the previous Saturday noon. The
existing local-time offset is 10,110 minutes before Saturday 12:30. Test both
DST crossings: seven London calendar days can be 167 or 169 elapsed hours.
Opening/lock checks use stored instants even before a scheduler tick. Weekly
billing has its own calendar-driven trigger, including weeks with no game to
open; recovery after a missed job applies openings, dues and notices idempotently.

A calendar entry is not proof of fixture availability. Distinguish scheduled,
pending discovery, temporarily unavailable, confirmed empty and playable; keep
price availability separate from fixture availability. An empty provider
response alone cannot mark a week skipped, cancel a due or erase an existing
card. Even an authoritatively confirmed break does not cancel the weekly fee.
Use the approved schedule-evidence rule in decision 2 below. Define a bounded
lookahead and request budget that can
reach the approved next eligible week, rather than assuming the existing
two-date horizon suffices.

Test one and several skipped weekends, empty responses, late discovery,
recovery without duplicate rounds/dues/notices, season end and declared extra
dates. Extra dates must not silently broaden the approved Saturday/Sunday
format. When no next eligible card is known at noon, expose the uncertainty;
that state does not satisfy the pickable-from-noon acceptance rule.

## One fee and independent game lifecycles

Keep one idempotent £1 due per member/calendar week throughout membership,
including missed, skipped, empty, cancelled and suspended game weeks. This
calendar week is Monday 00:00 inclusive to the following Monday 00:00 exclusive,
Europe/London, labelled by its Saturday (owner, 12 Nov). Each week intersecting
active membership is charged once; joining is inclusive and departure exclusive.
Normal dues arise at Monday's boundary, or on joining later, with catch-up;
early future entry may materialise them sooner without changing their identity.
For example, a Friday 20 Nov join owes £1 for 21 Nov, not for 14 Nov. This
rollout's £1 amount remains league-scoped; do not overwrite unrelated leagues'
settings. Generate weekly obligations independently of fixtures and game state,
and make the target week's fee payable before accepting an early fantasy pick.
An early pick cannot bypass intervening chargeable weeks during a break: the
paid-through calculation must include the calendar's weekly dues through the
target, with later scheduled billing unable to duplicate them. Both games check
entitlement through their own parent week. Payments remain
pooled league credit and clear the oldest dues first; do not attach a Monzo
transaction to a particular week. Picking, changing a pick and using the other
game create no extra charge. Preserve the existing protection that next week's
unpaid due cannot block a paid current-week group contribution.

There is no automatic fee waiver or reversal for no submissions, partial entries,
void picks, either/both games being cancelled, missing fixtures or suspension.
Leaving/removal/deletion releases unlocked claims under the game's own rules
but does not erase fees already owed, before or after either lock. Membership
determines who owes a week; game eligibility does not. Joining/rejoining cannot
create duplicate weekly charges or charge weeks before membership. Existing
ledger correction tools remain for genuine recording errors, not game-outcome
refunds; payments and historical dues/reversals are preserved. No retroactive
re-billing of legacy weeks is authorised by this forward-looking rule.
Joining/rejoining during the noon–14:30 overlap evaluates current-group and
next-fantasy entry separately while retaining the unconditional weekly fee.

Show settled fantasy-leg points as they arrive. The approved finalisation rule
is: final only after the Sunday window ends and no submitted fixture remains
pending. Finalisation must run idempotently without a new provider response or
any pending pick. Gate a Saturday-only fantasy entry that remains provisional
until Sunday ends, then finalises and announces once. Include all-void entries,
no-entry weeks and a Sunday 23:59 kick-off resolving on Monday. Group settlement
is independent and neutral voids never create an all-void win.

Legacy points plus fantasy points feed one season total exactly once. Weekly
winners and form aggregate by member/football week, not by slot; group picks
never enter a points denominator. Use the approved profile metrics in decision
4. Preserve the existing decimal scoring rule and legacy results.

Correction acceptance uses a shared fixture across legacy, group and fantasy
records in different leagues. One correction recomputes all applicable game
outcomes and fantasy weekly/season totals, preserves frozen prices, audits each
affected league and does not duplicate effects/messages on retry. Event claims,
completion records, push tags and deep links identify league, game and week;
correction events distinguish genuine later corrections from a retry. Saturday
group completion cannot suppress Sunday fantasy results. Group events remain
unpriced; fantasy result messages aggregate all submitted legs per member/week.

Mixed-format gates cover standings, home totals, weekly winners/form, profiles,
history, data export and account erasure. Export only the member's own records.
Leaving/deletion releases each game's unlocked claims while retaining locked
history under the existing anonymisation policy. Payment notices distinguish
“current group paid” from “next fantasy unpaid” and link to the named game/week.

## Build sequence — Batches 219–228

The source-of-record rows are now in `docs/BUILD_PLAN.md`. The earlier combined
weekly-results slice is separated into fees, results/lifecycle, and read APIs so
both web slices have complete backend contracts. Slice 1 fixes the contracts
and records the outstanding activation criteria. The four rule decisions are
approved, with decision 1 corrected as recorded below. Saturday's observation
can run alongside the inactive build; it is not a prerequisite for starting it.
Each executable batch retains its own branch, full `scripts/ci-local.sh` gate
and automatic close-out under `/batch-start`. This document invokes none of it.

The [second-review acceptance examples](two-games-per-week-acceptance-examples.md)
are now required in 219 and traced into the downstream rows: F1–F6 fix the exact
billing interval/cutover and early/intervening dues; C1–C6 cover the first live
legacy/new-format overlap; Q1–Q9 cover rolling boundaries, business rollback,
transport retries, admission and restart. Adding these requirements does not
complete 219's API/identity contracts or authorise storage work before them.

| Slice | Deliverable | Acceptance boundary |
| --- | --- | --- |
| 1. Rules and contracts (219) | Carry forward the approved decisions, including unconditional weekly billing; distinguish build, shipment and activation gates; define API contracts and update the product contract/architecture map. | Contracts are testable; supported-load, coverage and latency assumptions and unresolved activation evidence are explicit. No live setting change or claim of provider acceptance. |
| 2. Storage and format isolation (220) | Add parent format, game schedules/membership, separate picks and database constraints; durable provider budget, snapshots and work cursors. Fence legacy writes and legacy jobs from new-format weeks. | Clean and populated current-head upgrades; concurrency, slot bounds, cross-league/format isolation and atomic replacement failures; forced RLS, indexed foreign keys, no public grants; old-client refusal; forward-recovery rehearsal; restart cannot reset spent quota or lose completed work. |
| 3. Discovery and scheduling (221) | Implement both windows, shared per-attempt provider admission, paced chunks, full-horizon deduplication, stored openings/locks, missing-data states and catch-up. | Every promised next card exists at opening within budget and agreed latency; negative-price publication rechecks, stale snapshots, queue fairness, 14/30/100-member timelines, larger cards and counted retries; Sunday additions leave group unchanged; skips, extra dates, DST and restart/misfire pass. |
| 4. Weekly fee and roster lifecycle (222) | Charge every member £1 every week independently of games/discovery, preserving FIFO credit and paid-through-week checks. | No-entry, all-void, cancelled, skipped, fixture-empty and suspended weeks still charge once; leaving between locks does not refund owed fees; current group paid/next fantasy unpaid; early future picks include intervening weekly dues; arrears, concurrent billing/payments, delayed matching and join/leave/rejoin create no omissions or duplicates. |
| 5. Group API (223) | Explicit-target unpriced submit/replace/read/settle with fixture-wide claims. | Concurrent member/fixture conflicts retain prior picks; unpriced fixture selectable; no price lookup, points or combined odds; identical fantasy selection unaffected; fee gate enforced. |
| 6. Fantasy API (224) | Explicit week/game/slot submit/replace/read; fresh pick-time pricing within the shared capacity design. | Concurrent fills, seventh slot and duplicate fixture refused; overlap across members/games allowed; price movement, partial entries, voids, refusal, retries and fee gate pass database-backed tests. |
| 7. Results, corrections and events (225) | Fair persisted settlement within the shared budget, independent finalisation, continuous season totals, mixed-format history, corrections, game-aware events and account lifecycle. | Pending/error chunks cannot starve later results; completed chunks survive restart; result latency measured under concurrent picking; no-pending Sunday finalisation; late Sunday result; shared-fixture correction/retry; all members' cutover totals unchanged; weekly aggregation; independent notifications; export/erasure coverage. |
| 8. Home, history and payment read APIs (226) | Ship all actionable/current games, addressed navigation/history, member progress and week-specific fee/notice contracts. | Three simultaneous Saturday states with exact destinations, multiple leagues, correct partial-entry state, legacy links and old-response compatibility; bounded query growth. |
| 9. Group web (227) | Separate Saturday group contribution/result, 14:30 lock and new read contracts; hidden until activation. | Phone/accessibility journey; exact game/week targets; no group prices/points; legacy archive and stale-client behaviour. |
| 10. Fantasy web (228) | Six slots, weekend slate, noon lock, leg outcomes/weekly sum, home overlap, table, navigation and guidance. | Two offline slot fills survive; replacement and uncertain-write reconciliation cannot cross slots/games/weeks; noon boundary and late group pick; three-state home; Sunday, partial-six, legacy and mobile/accessibility journeys. |

After slice 8, require explicit `/ship-prod` before the web close-outs/pushes:
API and migrations ship first with the mode off. Batch 227 may be built and
tested locally against the new backend before that shipment, then pauses at
close-out. Batch 228 follows successful shipment and 227 close-out; no stacked
branch workflow is introduced. A scheduling acknowledgement cannot substitute
for successful API/payments shipment. Both services must reach the same image
and migration head. Both web slices must tolerate old responses and
keep the new format hidden until activation; their automatic Vercel deployments
cannot be treated as the activation step. Confirm drift and the project's
shipment requirements before close-out. This draft does not authorise those
shipments or activation; an authorised build run retains the project's
automatic close-out and web-deployment rules.

## Release and acceptance checkpoints

1. Before production migration: freshly verify the production revision and affected weeks,
   schedules, picks, dues and event claims. STATUS.md records no backup; verify
   current reality, then create and test a recovery point under separate owner
   authority. Rehearse the populated current-head upgrade and recovery with
   legacy results, dues/reversals, matched/queued payments and notification
   claims. Compare identifiers, counts and totals; a clean empty upgrade alone
   is insufficient. The API migrates on boot; an older image is not a
   data-preserving rollback after a revision change.
2. API checkpoint: complete the full local gate and exact-head CI, obtain
   explicit `/ship-prod`, ship API then payments, and verify both served SHAs,
   migration/readiness, drift, RLS and legacy behaviour with the mode off. An
   old payments process refuses a mismatched revision on restart, but one
   already running may keep reading during migration. Prove old-reader/new-schema
   compatibility throughout that overlap; a red readiness response is not a
   stop switch. Verify catch-up, queued/matched state and deduplication after
   shipment without manufacturing payments or webhook evidence.
3. Web checkpoint: only then close out both web slices. Verify served SHA,
   mobile/accessibility journeys, all simultaneous games, exact links, both
   locks, offline/uncertain submissions and legacy history. Vercel can reach
   members before CI reports; old/new API compatibility and hidden new-mode
   behaviour are pre-push gates, not checks to defer until activation.
4. Activation: the owner approves an exact league, first football week and
   effective opening, before that week's promised fantasy opening. The first
   activation also requires accepted opening-time fixture/price coverage,
   account quota, supported traffic and refresh/result-latency evidence. The
   scheduled 14 Nov observation supplies provider evidence; it does not enable
   the new format or retroactively convert that target week. Until activation,
   the new format must not create live game weeks, picks, dues or notices, nor
   start its provider work. Legacy games continue under their existing rules.
   The first consecutive opening is the previous Saturday noon even if no prior fantasy
   week exists. Prefer a future week not yet published/opened/charged/picked.
   Pick-free alone is insufficient: inspect existing dues, announced deadlines
   and notices. Do not convert an affected legacy week; choose a later week or
   obtain a separately reviewed recovery plan. Confirm every member's season
   total unchanged and both old/new write fences. Record the approved suspension
   procedure; it must not reinterpret accepted picks as legacy.
5. Natural acceptance: observe the first fantasy opening and the subsequent
   weekend/next opening, not just the deployment. Read back actual fixture and
   price coverage, both locks, early-fee entitlement, independent claims and
   real submissions, including the same selection in both games. Verify group
   outcome and final fantasy points after Sunday/late results, plus addressed
   notifications and owner receipt where required. Synthetic fixtures, CI and
   delivery attempts cannot close live provider, member-use or receipt gates.

## Decisions received

- **Season points continue (owner, 11 Nov).** Existing points count towards
  the same season total. New fantasy points add to them. Keep past weekly
  results unchanged and visible.
- **Scoring stays (owner, 11 Nov).** Each winning fantasy pick scores
  `round(frozen_odds × 10)`; a loss or void scores zero.
- **Six different fixtures (owner, 11 Nov).** One fantasy pick per fixture per
  member. Different members may hold the same selection.
- **Immediate next opening (owner, 11 Nov).** The next fantasy week should open
  at the current Saturday noon pick lock, even while current results are pending.
  Consecutive football weeks have seven days from opening to the next lock.
- **£1 every week, paid early if picking early (owner, 11 Nov, clarified after
  review).** Every member owes £1 every week regardless of participation,
  selection or outcome. One weekly charge covers both games. An early fantasy
  entry requires being paid up through its week; absent/cancelled games do not
  waive dues. The earlier proposed automatic refunds are rejected.
- **Partial fantasy entries count (owner, 11 Nov).** Submitted legs score as
  usual; unused slots score zero. No automatic picks are made.
- **Independent games (owner, 11 Nov).** The same member or different members
  may choose the same selection across group and fantasy. Neither game's
  claims restrict the other. They are distinct pick records and settle from the
  same real match outcome without sharing points or coupon status.
- **Distinct fixtures inside each game (owner, 11 Nov).** The group gets at most
  one member contribution per fixture. A fantasy member gets at most one pick
  per fixture, while different fantasy members may use the same fixture.
- **Group voids are neutral (owner, 11 Nov).** The group succeeds if every
  non-void leg wins; an all-void coupon is void, not a win.
- **All Sunday kick-offs (owner, 11 Nov).** Fantasy admits fixtures kicking off
  through Sunday 23:59 Europe/London; the result may arrive later.

## Owner decisions approved — 11 Nov

The owner replaced decision 1 with “everyone should have to pay £1 every week
regardless of anything else, whether they play or not, what they pick etc.” and
approved decisions 2–4. The unconditional fee rule takes precedence over the
earlier cancellation refunds and proposed suspension of dues. This approves the
plan's rules, not a build run, live probe, deployment or live billing change.

12 Nov additions: the owner chose Monday-to-Monday London billing, labelled by
Saturday, and requested completion/testing locally overnight with production
left for review. The [overnight prompt](two-games-per-week-overnight-prompt.md)
defines the local stacked-batch exception when invoked; it does not authorise a
production shipment, migration, purchase or activation. Ordinary close-out and
shipment gates still apply afterwards.

### 1. Shared fee, cancellation and roster cutoffs

The £1 charge is independent of participation, claims, locks and results:

| Case | Approved rule | Effect on the member |
| --- | --- | --- |
| No picks, partial entries or any result including all-void | Charge £1 for the week once. | Participation and outcomes never waive the fee. |
| One/both games cancelled, confirmed break or no fixtures | Charge £1 for each calendar week once. | Skipping a game week does not skip payment. |
| Leave/remove/delete before or between locks | Release unlocked claims and retain locked history; keep fees already owed. | No automatic refund at either lock boundary. |
| Join/rejoin | Charge each week of membership once, including weeks with no open game; retain arrears and avoid duplicate dues. | Only still-open games permit entry; paying does not reopen them. |
| Emergency suspension | Continue weekly dues while entries/openings are suspended. | The £1 obligation continues independently of game availability. |

Future dues follow recorded membership; departure does not cancel an already
owed week. This is a forward-looking rule for the approved rollout, not an
instruction to charge past non-membership weeks or rewrite the historical
ledger. The cost is explicit: members pay through missed or unplayable weeks.

### 2. Breaks, unpublished cards and provider sufficiency

Use an explicit league calendar with recorded, owner-approved evidence of
breaks, derived from confirmed competition schedules rather than an empty odds
response. For a confirmed break, open the next known eligible fantasy week at
the current eligible week's noon lock and show its actual deadline; the gap may
exceed seven days. Define the maximum lookahead and request allowance in the
capacity design. Keep non-weekend extra dates out of the new format unless the
owner separately approves a rule change; retain legacy extra-date history.

If the eligible card or its prices are unknown, show pending/unavailable and
keep activation blocked: that display is not an accepted substitute for a
pickable card. The schedule-evidence policy is approved; the concrete coverage
criterion and supported capacity still need to be recorded before measurement.
Any alternative opening/pricing rule if feasibility fails requires a new owner
decision. No partial sample or numerical coverage threshold is adopted automatically.
Cost: possible release delay or a paid provider; obtain actual prices before
asking for a spending decision.

### 3. Partial group coupons, fantasy participation and reminders

Settle a non-empty group coupon from the submitted legs, while
showing missing contributors explicitly. Neutral voids and the approved
all-void rule still apply; no submissions means “No coupon”, never a win.
An incomplete group coupon is an accepted final result.

For fantasy, use “entered” for at least one submitted leg and “six slots
filled” only at six. Remind members with zero picks; show remaining optional
slots in the app without treating a valid partial entry as a failure. Do not
reuse the group's “all picked” event to imply that all fantasy members have
finished choosing. Finalise fantasy only after Sunday's window and no pending
submitted fixture, as specified above. Cost: separate participation/progress
states; members with partial entries would receive no fill-six reminder.

### 4. Statistics and emergency suspension

Use leg win rate over resolved non-void fantasy legs, points per pick and
best return as labelled leg metrics, and weekly form/winners over each member's
summed week score. Historical legs retain their original contribution to season
metrics; group picks contribute neither points nor scoring denominators. Show
no-entry and all-void weeks distinctly rather than forcing a six-leg week into
one legacy won/lost marker. Keep season points continuous as already approved.

Use a league-scoped suspension that stops new submissions/replacements and
future game openings while continuing accepted-pick settlement, corrections,
history and weekly billing. The owner's unconditional £1 rule overrides the
earlier suggestion to suspend dues. Suspension does not change week format,
remove accepted picks, move money or reverse fees. Before resuming, reconcile
missed openings/deadlines and verify that weekly billing has no gaps or duplicate
charges under explicit owner authority; never silently reopen a locked game.
Cost: a degraded entry period and additional recovery tests; members' accepted
entries remain and their weekly fee continues.

## Planning completion gate

All eight review findings now have a design requirement and acceptance gate in
this draft. That is document completion, not implementation or live acceptance.
All four rule decisions are recorded. The feasibility assessment now proposes
concrete capacity/coverage criteria and records the offline constraints. Live
fixture/pricing evidence and the whole-pipeline capacity models are recorded in
the follow-up reports. The scheduled free-tier candidate is the baseline; no
purchase is recommended solely from the extreme burst. Batches 219–228 are now
defined and can be implemented/tested locally with the new format disabled.
Complete the authorised 14 Nov observation in parallel, then settle the
early-coverage, supported-load and refresh/result-latency contracts before live
activation. Do not wait for Saturday merely to continue engineering work.
Recovery-point creation, production shipment and exact-week activation remain
separate owner-controlled actions.
