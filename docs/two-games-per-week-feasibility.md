# Two games per week: feasibility assessment

11 Nov 2026 · source `dfb39fef90dd4a171248c79117d6bdc72d63ce8d`

**Follow-up:** the owner subsequently authorised live feasibility checks. The
[live findings](two-games-per-week-live-feasibility.md) supersede this report's
unverified account/card counts and its pending one-request approval. They retain
the confirmed software constraints. A one-off actual-opening check is scheduled
for 14 Nov at noon; the final coverage/provider decision remains open.
The [12 Nov scheduled free-tier assessment](two-games-per-week-free-tier-assessment.md)
adds aggregate activity and paced timelines: the current-group cases fit a
candidate free-tier design. Earlier burst envelopes remain stress evidence,
not a traffic forecast or an automatic reason to buy a subscription. The 12 Nov
gate correction permits inactive implementation in Batches 219–228 while the
actual-opening observation remains an activation requirement.

**Original 11 Nov verdict, superseded by the 12 Nov build/activation split:**
not ready for implementation batches. The rules are approved, but
the current request limits cannot support the proposed six-pick workload.
Provider capacity and prices at the promised week-ahead opening remain release
blockers. A larger provider plan is a possible solution, not an approved purchase
or proof of coverage.

This assessment supplements the [revised plan](two-games-per-week-plan.md) and
preserves the [original review](two-games-per-week-plan-review.md). Work was
limited to current source/tests, offline simulations and public provider
documentation. No authenticated provider, Betfair, Monzo or production request
was made. No product code, settings, database or build rows changed.

## Confirmed constraints, ranked

### P1 — Existing submission limits would reject valid six-pick demand

The current limits are 10 submissions/member/hour, 50/league/hour and
100/league/day. A separate installation allowance permits 50 cold pricing
refills/hour and 211/day. The league limit counts submissions even when prices
are already cached. These limits protect the existing one-pick game; copying
them into fantasy would be incorrect.

Budget-only simulations through the current limiter/cache functions found:

| One-hour input | Accepted | Refused |
| --- | ---: | ---: |
| 13 members × six, distinct cold prices | 50 | 28 |
| 13 members × six, all prices warm | 50 | 28 |
| Two 13-member leagues × six, distinct cold prices | 50 | 106 |

Thirteen is a historical example, not a fresh member count. Fifty remains the
existing configurable maximum per league. At the noon boundary, finishing six
current-week picks and starting six next-week picks can require 12 submissions
per member in the same hour, exceeding the member limit too. These simulations
do not implement or prove fantasy slots, fees, persistence or concurrency.

Evidence: [submission limits and charging](../apps/api/src/routers/picks.py#L90),
[maximum membership](../apps/api/src/routers/leagues.py#L404),
[installation-budget tests](../apps/api/tests/test_request_budget.py#L949),
[dated membership snapshot](../STATUS.md#L21).

### P1 — A cache-call budget does not count every provider HTTP attempt

A mocked 503 caused four HTTP attempts through the real provider adapter, while
the price cache charged one request and the installation callback fired once.
The adapter records attempts, but pricing admission is charged outside its retry
loop. The whole-pipeline design must reserve/count each actual attempt, including
retries, and include discovery, manual operations and settlement. Raising only
the account quota or pick bucket is insufficient.

Evidence: [HTTP retry loop](../apps/api/src/services/odds_api.py#L683),
[price-cache charging](../apps/api/src/services/odds_cache.py#L374),
[installation callback](../apps/api/src/routers/picks.py#L356).

### P1 — Discovery can omit a promised card; settlement can return no progress

At the historical test shape of 23 competitions, two windows over two dates cost
92 discovery requests. The cap of 90 admits three complete walks, costing 69,
and omits the fourth. One shared Saturday–Sunday discovery per competition/date,
filtered locally into the two games, would cost 46 plus a cold catalogue read.
That is a design calculation, not measured Sunday coverage.

Settlement makes one request per distinct pending fixture and returns the whole
set before applying results. With 182 mocked fixtures and a 429 after 100
successful reads, two repeated attempts each made 101 requests and returned no
partial results. Previously committed database results were not erased; this
demonstrates failure before the provider-return/application boundary. Fair,
bounded chunks must preserve completed progress and avoid polling Sunday
fixtures before their results can exist.

Evidence: [discovery cap](../apps/api/src/config.py#L201),
[production-shape discovery test](../apps/api/tests/test_discovery_budget.py#L919),
[settlement requests](../apps/api/src/services/odds_api.py#L516),
[application boundary](../apps/api/src/services/scoring.py#L260).

### P2 — The refresh schedule protects the old lock, not fantasy noon

The configured refreshes run at 09:05 and 11:05. The latter falls inside the
final fantasy picking hour. The current safety test checks the 14:30 lock.
Reschedule or prove a sufficient reserved budget for both deadlines; include
current-week last entries and next-week first entries in the same rolling hour.

Evidence: [refresh configuration](../apps/api/src/config.py#L189),
[trigger test](../apps/api/tests/test_scheduler.py#L199),
[old-lock safety test](../apps/api/tests/test_scheduler.py#L400).

## What the offline evidence establishes

23 selected existing tests passed, zero skipped. They cover cache costs,
discovery arithmetic, submission budgets, cooldowns and the existing refresh
rule. Network access and environment-file loading were blocked. Additional
temporary simulations used fake providers or `httpx.MockTransport`; none was
database-backed. This was not the full CI gate or an end-to-end fantasy test.

Continuous-browsing simulations with current freshness tiers produced 100 daily
calls for an 85-fixture/seven-unpriced shape, 252 for the historical
264/89 shape, and 492 for a synthetic doubled 528/178 shape. They browsed the
current fantasy card until noon and the next card afterwards. Adaptive budget
widening was disabled to expose demand; no group or locked-result prices were
fetched. Warming was not added twice. These are demand envelopes, not live
traffic forecasts. See [cache simulation helpers](../apps/api/tests/test_request_budget.py#L175)
and [current freshness settings](../apps/api/src/config.py#L96).

## Capacity options and unresolved evidence

The recorded free-account limits are 100/hour and 500/day. For 13 members,
finishing this week and starting next week can require 156 distinct cold
single-slot price requests within one hour, before browsing or retries.
Consequently the free tier cannot guarantee that submission pattern unchanged.

An optional save of 1–6 slots together could fetch those prices in one batch:
26 initial-entry requests for the same example. Two cold historical-floor cards
would add 54, leaving 20 of 100 for everything else. This arithmetic does not
prove a viable daily budget, replacements or failure recovery. It also changes
the saving interaction and needs an explicit design choice. Partial entries and
per-leg frozen prices must remain valid.

For a reference load of two simultaneous 50-member leagues, even one batch per
six-slot entry can require 200 cold requests across the noon boundary. That
already exceeds the recorded free hourly limit. Two leagues are a useful minimum
test case, not a proposed product limit or a guarantee for unlimited leagues.

Public documentation checked on 11 Nov advertises Solo at £49/month with two
bookmakers and 5,000 requests/hour. New free accounts are paused. This documents
an alternative; it does not verify the existing account's current entitlement,
checkout price or week-ahead prices. The owner previously chose to stay free.
[Provider pricing](https://odds-api.io/pricing/free),
[31 Oct owner decision](adr/0002-replace-betfair-exchange-with-odds-api-io.md#L6).

The public API documents up to ten events per `/odds/multi` request and a
paid-only `/settlements` endpoint accepting up to 50 events. The latter is not
used by this checkout and its availability on the existing key is unverified.
It is a candidate adapter improvement, not present application behaviour.
[Official OpenAPI](https://docs.odds-api.io/api-reference/openapi.json).

Unknowns remain: current membership/league load, selected competitions and
markets, complete Sunday fixture inventory, prices at the actual opening,
account quota/headroom, and coverage across confirmed breaks. STATUS's 31 Oct
78/85 priced card proves none of those. Its recorded bookmaker is Betfair
Sportsbook, while source defaults remain Bet365; an evidence run must explicitly
confirm the effective bookmaker rather than use a local default.
[Recorded provider state](../STATUS.md#L22),
[source default](../apps/api/src/config.py#L90).

## Proposed acceptance criteria — require owner agreement before measurement

1. Preserve the existing 50-member league capacity; model the actual installation
   and at least two simultaneous leagues. Declare the installation load tested,
   peak submission/replacement allowance, competition/card sizes and maximum
   break lookahead. Do not present the old 13-account snapshot as a new limit.
2. Budget every HTTP attempt across both visible weeks, all leagues and all
   provider callers. Include cold/warm/restarted caches, final-hour/next-opening
   overlap, rejected batches and retries. Prove admission and eventual settlement
   progress within the verified hourly/daily quota without weakening pick-time
   freshness. Legacy games retain their capacity during rollout.
3. Reconcile fixtures with identified independent competition schedules. Report
   missing fixtures separately from missing prices, by competition, day and
   offered market. Group fixtures need no price. At least six distinct priced
   matches demonstrate a full fantasy entry is possible; six alone does not
   establish promised weekend coverage. Partial entries remain legitimate.
   Report group fixture shortages against membership; incomplete coupons remain
   valid. No unexplained gap or arbitrary percentage counts as acceptance.
4. Observe the next card near its actual Saturday noon opening, including Sunday
   prices. Confirmed breaks require evidence at the approved longer horizon too.
   A small sample, a later-week quote or an unavailable card does not close this
   gate. Retain the already accepted Highland pricing gap explicitly; do not
   silently extend that exception to new omissions.

## Bounded live-evidence procedure — prepared, not authorised or executed

The next consecutive opening to observe is Saturday **14 Nov at 12:00 London**,
for fantasy fixtures from **21 Nov 12:30 to 23 Nov 00:00 exclusive**. Group
fixtures are **21 Nov at 15:00 exactly**. Both dates are GMT. If that observation
is missed, choose a new actual Saturday opening; an off-schedule sample is not
equivalent.

Before any API read, the owner confirms the target league, selected competitions,
offered markets, effective bookmaker and account quota/headroom. Manual reads
share production's quota and are invisible to its in-process counters.

Proposed first approval is only **one catalogue request**, with no retries:
`GET https://api.odds-api.io/v3/leagues?sport=football`.
Use the existing key without printing it. This yields a concrete competition
manifest and an exact census request count for the next approval. It does not
fetch odds or prove feasibility. No request is authorised by this document.

Then prepare the exact census manifest and approve its count before execution:
one request per selected eligible competition for
`GET /v3/events?sport=football&league=<slug>&from=2026-11-21T00:00:00Z&to=2026-11-23T00:00:00Z`.
Do not filter discovery by bookmaker: that would hide unpriced group fixtures.
Record pagination/truncation; extra pages require a counted, approved bound.
Current source does not paginate this request.
[Discovery implementation](../apps/api/src/services/odds_api.py#L581).

After the census, deduplicate eligible fantasy event IDs and approve the exact
price manifest for the actual opening. Use `/v3/odds/multi` with at most ten IDs
and the confirmed bookmaker; the current one-ID path uses `/v3/odds`. For the
recorded bookmaker, the filter is `bookmakers=Betfair%20Sportsbook`. Do not
switch books. Record each request's timestamp, returned events, offered markets
and valid prices; sequential batches are not a simultaneous snapshot.
[Current request shapes](../apps/api/src/services/odds_api.py#L629).

For `C` competitions, `F` eligible fantasy fixtures and `K` approved extra pages,
the catalogue + census + one complete price snapshot costs
`1 + C + K + ceil(F / 10)` single-attempt requests. These quantities are not yet
known. Reserve space for scheduled production traffic and member picks before
approving a numerical cap. Do not reuse the helper's automatic four-attempt
retry policy for a single-attempt procedure.

Reconcile the saved census with current schedule evidence and returned metadata.
A pre-opening census plus opening prices cannot prove no new fixture was added
after the census; leave full discovery coverage open unless reconciled. Stop on
unknown headroom, the cap, refusal, 429, network/5xx failure, malformed/truncated
response, unexpected bookmaker or unexplained empty result. Preserve incomplete
evidence; no retry, broader scan, provider switch, live pick or job trigger.

## Original changes requested — now build and activation acceptance work

Agree the capacity/coverage criteria above and select a costed provider/submission
design. The design must replace the one-pick submission limits, count actual
HTTP attempts globally, deduplicate weekend discovery, protect the noon peak,
and settle in fair durable chunks. Batches 219–228 can implement and verify that
design while disabled. Demonstrate whole-pipeline capacity and complete the
authorised opening/coverage evidence before live activation. Keep migration
recovery, API/payments parity and exact-week activation gates from the plan.

The unconditional £1 weekly fee and the other approved game rules are unchanged.
No build run, paid subscription, live probe or activation is approved here.

<details>
<summary>Reproduce the 23 offline tests</summary>

Run from `/tmp` using the existing local CI environment. The command deliberately
disables environment files, outbound sockets, pytest cache and bytecode writes.
The temporary budget simulations described above were not saved as product tests.

```bash
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api ODDS_PROVIDER=fake FOOTBALL_DATA_PROVIDER=fake SCHEDULER_ENABLED=false /Users/craigrobinson/.cache/the-coupon/ci-local-venv/bin/python - <<'PY'
import socket
from pydantic_settings import BaseSettings
original_init = BaseSettings.__init__
def offline_settings(self, *args, **kwargs):
    kwargs['_env_file'] = None
    return original_init(self, *args, **kwargs)
BaseSettings.__init__ = offline_settings
def blocked(*args, **kwargs):
    raise AssertionError('offline feasibility: networking forbidden')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
import pytest
root = '/Users/craigrobinson/the-coupon/apps/api/tests/'
cases = {
 'test_request_budget.py': [
  'test_the_derived_shape_costs_only_its_priced_subset_after_learning',
  'test_the_unpriced_ties_are_re_asked_once_a_recheck_and_no_oftener',
  'test_saturated_browsing_near_lock_stays_inside_the_hourly_limit',
  'test_a_saturated_day_of_browsing_stays_inside_the_daily_limit',
  'test_freezing_every_members_pick_costs_one_request_each',
  'test_discovery_is_a_fixed_daily_cost_independent_of_traffic',
  'test_the_weekly_full_catalogue_walk_fits_its_own_hour',
  'test_the_configured_defaults_are_the_ones_this_module_budgets_for',
  'test_installation_hourly_budget_refuses_the_next_cold_pick_across_leagues',
  'test_installation_daily_budget_refuses_the_212th_cold_pick_across_leagues'],
 'test_scheduler.py': ['test_the_late_slate_pass_is_clear_of_the_lock_hour'],
 'test_odds_cache.py': [
  'test_ten_retries_after_a_rate_limit_cost_one_request',
  'test_the_pick_path_is_refused_inside_the_cooldown_without_calling_upstream',
  'test_the_pick_path_never_has_its_ceiling_widened',
  'test_a_refused_chunk_stops_the_refill_and_starts_the_hold_off']}
args = ['-q', '-p', 'no:cacheprovider'] + [
 root + file + '::' + case for file, names in cases.items() for case in names]
raise SystemExit(pytest.main(args))
PY
```

</details>
