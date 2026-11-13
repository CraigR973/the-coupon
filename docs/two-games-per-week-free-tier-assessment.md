# Two games per week: scheduled free-tier assessment

12 Nov 2026 · source `dfb39fef90dd4a171248c79117d6bdc72d63ce8d`

**Verdict: use the existing free account as the planning baseline. A paid upgrade
is not justified by the earlier burst model alone.** Scheduled chunks plus fresh
quotes on save fit the current 14-membership scenarios below, including a
specified deadline rush. This is a credible design to validate, not proof that
the deployed app already supports fantasy or that every burst will fit.

This supersedes the paid-first recommendation in the [11 Nov live assessment](two-games-per-week-live-feasibility.md).
No product code, subscription, live setting, database data or build row changed.
The £1 weekly rule, independent slot saves, six-pick allowance and fresh frozen
prices remain unchanged. No additional odds, Betfair-account or Monzo calls were
made for this reassessment.

## Evidence about actual activity

A read-only production aggregate covered football dates 19 Sep–7 Nov: **94
surviving picks across eight Saturday rounds**, plus one pick in a Friday round
excluded from Saturday replay. The busiest rolling hour contained ten surviving
row creations. All 94 Saturday picks were first created on Saturday: 76 before
noon and 18 afterwards. There were no creation timestamps at/after their stored
lock, or earlier than the prior Saturday.

This supports modelling a Saturday rush, not claiming existing usage is evenly
distributed through the week. Earlier fantasy availability may spread activity;
that remains a behavioural assumption. The 31 Oct peak also coincides with the
recorded provider incident, so it is not an uncontaminated demand sample.

These are **surviving initial-row timestamps, not request logs**. Replacements
update the same row; failed submissions and deleted picks are absent. Settlement
also changes `updated_at`, so it cannot recover replacement timing. No member
identities, selections or payment rows were exported.

Evidence: [aggregate](../.local/two-game-feasibility/2026-11-11/traffic-aggregate.json),
[timestamp checks](../.local/two-game-feasibility/2026-11-11/traffic-timestamp-check.json),
[query](../.local/two-game-feasibility/traffic_probe.py),
[save/replace behaviour](../apps/api/src/routers/picks.py#L418),
[replacement test](../apps/api/tests/test_picks_flow.py#L298),
[31 Oct incident](../STATUS.md#L91). The aggregate is dated 11 Nov at 22:02 UTC;
this report records the subsequent reassessment. Private evidence is Git-ignored.

## Candidate schedule and shared budget

All values here are design parameters tested offline, not production settings
or an owner-approved reduction in service. One durable, installation-wide budget
must cover **every HTTP attempt**, including retries, legacy callers, manual
operations, discovery, prices and settlement. Use the lower of local allowance
and provider-reported remaining capacity; restarts must not reset spent quota.

| Work | Candidate policy |
| --- | --- |
| Global budget | 90 attempts per rolling hour against the observed 100/hour entitlement; provisional 450 per rolling 24 hours against the still-unverified recorded 500/day. |
| Fixture discovery | One paginated global football census per target weekend, filtered locally into both games; target both weekends at 05:05 and 17:05 London. One catalogue/day and three extra manual/catch-up pages are included. |
| Background prices | At most ten events/request, one queued request every six minutes; 10 background attempts/hour and 120/day, including discovery and retries. Target four sweeps/day for the measured 77+120 fixture shape. |
| Busy opening period | Pause optional background work Saturday 10:00–13:00. Allow at most five actual opening-check attempts from noon; queue remaining checks. Preload the known next card before this period. |
| Saving picks | Independently save each slot using a positive quote no older than 60 seconds; reuse the same fixture's fresh cache across members. Foreground calls may use remaining global quota, rather than inheriting today's 50/hour installation cap. |
| Settlement | Fair, persisted cursor over distinct picked fixtures whose results can exist; initially 30 attempts/hour and 200/day, underneath the same global caps. Pending/error results go to the back with a delay; successful results stay committed. |

These allocations are ceilings, not additive entitlements: 120 background + 200
settlement does not create a separate allowance outside the global 450/day.
Group picks and locked result screens spend no price calls. Browsing reads the
stored price snapshot and its age; it must not trigger another whole-card fetch.
Persist snapshots/cursors and coalesce duplicate work to avoid restart stampedes.

Four complete sweeps of 120 fixtures alone cost 48 requests/day. The model is
more conservative: it refreshes both 77/120 cards, requiring 20 calls/sweep,
80/day before discovery/retries. All cards are treated as priced, and every
pick quote is treated as a cold miss; no savings from overlapping picks or bulk
entry submission are assumed. The ten-event batching limit is documented by the
[provider](https://docs.odds-api.io/api-reference/openapi.json).

The cadence must follow card size and remaining budget. Two 264-fixture cards
need 54 calls/sweep (each card rounded separately), so four sweeps cannot fit the
background allocation. The model drops to one target sweep/day at that size;
that is an **unapproved degradation to assess**, not permission to hide fixtures
or promise six-hour price coverage at every scale. Queue delays and visible
price age must be measured separately from quota compliance.

## Results of the offline timelines

32 scenarios completed with network creation blocked. Each models independent
slot saves, rolling windows, both visible cards, background work, partial-result
settlement and counted retries. Most use six saves over 25 seconds, one later
replacement per entry, and approximately 10% extra HTTP traffic. Settlement
stress assumes two pending reads followed by a terminal third read per fixture.

“Spread” places current-week entry sessions across Monday–Friday, then a quarter
of members enter next week near noon. “Rush” puts half of current-week entries
into the last 30 minutes, plus a quarter entering next week in its first 20
minutes; the others enter earlier. These are explicit scenarios, not measured
probabilities or a member restriction.

| Scenario, one census page/weekend | Peak actual calls/hour | Peak calls/rolling day |
| --- | ---: | ---: |
| 14 memberships, spread | 40 | 343 |
| 14 memberships, deadline rush | 90 | 397 |
| Eight historical-pattern replays, expanded to six picks + edit | 40–83 | 426–434 |
| 30 memberships, spread | 66 | 373 |

All pick attempts in those rows were admitted by the simulated budget. Three-page
censuses also fit the 14-member spread/rush cases. The 14-member rush needs 85
foreground attempts plus five opening-check attempts: this is useful evidence,
but little local hourly margin. The provider's additional ten requests/hour are
kept as safety headroom, not sold twice.

Historical replay shifts local creation times 150 minutes earlier to align the
old 14:30 lock with noon, adds two weekday memberships and four early next-week
entries, then expands each entry into six saves plus an edit. It is a scenario
using historical timing, **not a replay of observed fantasy requests**.

Failures remain explicit:

- At 30 memberships, the same rush requests 177 foreground attempts/hour and
  refuses 87 attempts under the simulated cap. At 14 memberships, four edits
  per entry request 121/hour and refuse 33 attempts with opening checks sharing
  the budget. Refused attempts are not a count of affected people or lost picks.
- Every current member finishing this week and entering next week together
  requests 215 attempts/hour at 14 memberships and refuses 125. The earlier
  extreme burst remains a valid overload test; it is not the normal forecast.
- The 100-membership scenarios also exceed the budget, including the quarter
  entering next week together. Neither the existing 50-member league limit nor
  the configured 15+15 capacities have been reduced to make this assessment pass.
- With 77 selected fixtures and three result reads each, settlement completes
  Sunday at 19:19 in the model. A deliberately excessive all-120-selected case
  completes at 23:51 Sunday. All 264 selected fixtures take until Wednesday;
  that is unacceptable as an unqualified timely-results promise. These are
  finite-backlog latency tests, not live result availability predictions.

The initial 120/day settlement allowance delayed the 77-fixture case to Monday
17:54; it was rejected in favour of the tested 200/day candidate. The large-card
simulation initially exceeded its nine-day total observation window; the window
was extended to fourteen days to measure completion, retaining its assertion
and reporting the resulting multi-day delay. No product test was altered.

## Opening coverage and negative-cache gap

Scheduling cannot make an unpublished bookmaker price exist. The 11 Nov live
sample had prices on 27/120 next-week fixtures; the actual 14 Nov noon observation
remains necessary. Periodic retrieval can discover later publication, but its
latency must be included in the coverage promise.

Current code caches an unpriced answer for six hours **even when the caller asks
for a 60-second quote**. Merely moving jobs around would therefore leave some new
markets unavailable after the bookmaker publishes them. Opening checks need a
bounded way to revisit eligible negative entries, with age/provenance visible;
do not globally invalidate every absence or let retries exhaust the pick budget.
[Current negative-cache rule](../apps/api/src/services/odds_cache.py#L582),
[regression test](../apps/api/tests/test_odds_cache.py#L629).

In the 14-member rush model, five opening attempts complete only four of the
next card's twelve batches after a simulated failure; eight batches are queued
past 13:00. Background work can finish four hours after it became due in the
77/120 case. The 120/120 stress case reaches almost seven hours of queue delay.
Thus this schedule **does not prove every new price is visible at noon or every
browse price is at most six hours old**. Preserve the live-opening acceptance
gate; do not silently convert the existing partial-coverage evidence into full
coverage. A completed discovery census and a completed price sweep are distinct.

## 12 Nov follow-up: quota evidence and observation readiness

The one-off observation remains active for **14 Nov at 12:00 Europe/London**.
Its instructions now include this free-tier assessment, distinguish six-pick
choice from complete market coverage, and retain the request cap/reserve and
late-run caveat. It will record what the proposed five-attempt opening allowance
could cover without confusing that allowance with the separate evidence-run cap.

The daily limit remains unverified. Search-index snippets quoted 500/day, but
direct retrieval of the current [legacy-free FAQ](https://odds-api.io/pricing/free)
confirmed only 100/hour and two recreational bookmakers; the current
[pricing page](https://odds-api.io/pricing) also did not establish a legacy daily
allowance. The dashboard link redirected to sign-in, and no computer-use browser
was available for an authenticated account read. Do not treat stale snippets as
current account evidence or exhaust the quota to discover its refusal threshold.
The 450/day model remains a conservative assumption, not verified entitlement.

No new provider API request, production read or product change was made in this
follow-up. The full opening observation cannot be completed before Saturday;
no earlier sample or repeated offline run closes that gate.

## Verification, build gates and activation gates

13 current cache/scheduler tests passed, zero skipped, with environment-file
loading and networking disabled. They verify fresh positive pick quotes,
shared cache charges, cooldowns, retry/refusal behaviour and the existing refresh
rule. They do not test the proposed worker. The 32 model scenarios independently
check rolling global/category caps and finite settlement completion. Expected
overload refusals are recorded, not presented as successful entry capacity.

No full CI gate, database-backed scheduler/concurrency test, restart recovery,
new API/UI flow, provider outage drill or fantasy payment flow was run. The
exploration agent hit its session usage limit after reporting source findings;
the parent independently ran the 13 tests and completed the model.

Storage/API implementation and scratch-database/fake-provider tests can proceed
with the format disabled. Before live activation, resolve the opening-coverage
criterion, confirm daily entitlement, and define the supported load and acceptable
visible refresh/result delays. Keep 14, configured 30 and reference 100 memberships
in the evidence; do not select only the successful cases. Before activation, require:

1. Shared admission at the HTTP transport, atomic across concurrent callers,
   persisted across restarts; retries/headers/cooldowns and manual/legacy work
   included. Replace obsolete application submission caps without weakening
   abuse protection or positive-quote freshness.
2. Durable fair queues and snapshots, including rejected/pending chunks, new
   price publication, cold start, both weeks, skipped-week lookahead, larger cards
   and Sunday late kick-offs. Prove completed work survives restart and visible
   latency satisfies the agreed service contract.
3. HTTP/database-backed timelines for the passing cases and overload behaviour,
   followed by real attempt-rate/cache/queue-age measurements. An upgraded quota
   becomes a spending decision if realistic expected demand or the agreed
   coverage/latency contract cannot fit; it is not an automatic prerequisite.

The [original review](two-games-per-week-plan-review.md) still governs legacy
history, unconditional dues, corrections, API/payments parity, migration recovery
and safe activation. **Ready to continue inactive implementation; not ready for
live activation.** Batches 219–228 in `docs/BUILD_PLAN.md` define the work. The
scheduled 14 Nov noon observation runs alongside implementation-level verification
of this candidate schedule; waiting for it is not a general build prerequisite.

Reproduce the offline model (no credentials or network needed):

```bash
/Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/python /Users/craigrobinson/the-coupon/.local/two-game-feasibility/paced_capacity.py
```

[Model source](../.local/two-game-feasibility/paced_capacity.py) ·
[32 scenario results and assumptions](../.local/two-game-feasibility/paced-capacity-output.json) ·
[initial conservative-allocation results](../.local/two-game-feasibility/paced-capacity-initial-output.json).
