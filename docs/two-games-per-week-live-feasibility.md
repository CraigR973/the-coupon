# Two games per week: live feasibility findings

11 Nov 2026 · source `dfb39fef90dd4a171248c79117d6bdc72d63ce8d`

**12 Nov reassessment:** the [scheduled free-tier assessment](two-games-per-week-free-tier-assessment.md)
supersedes this report's paid-first recommendation. Retained first-save timings
and paced simulations support the existing free account as the baseline for the
current group; deadline/growth overload and opening coverage remain explicit
activation gates. Inactive implementation and local verification can proceed as
Batches 219–228; the Saturday observation runs alongside them. The live
observations below are unchanged.

**Verdict: the two-game design is feasible in principle, but the full promised
service is not yet confirmed.** Fixture discovery and six-pick choice work with
the existing provider. Its free quota cannot guarantee the proposed independent
slot-saving workload. Early price coverage is incomplete. Complete the scheduled
14 Nov noon observation before accepting live opening coverage and activation.
Its timing is not a prerequisite for inactive implementation.

The owner authorised the necessary live checks on 11 Nov, superseding the earlier
no-probe restriction. No subscription, bookmaker setting, league rule, fee,
deployment or product code was changed. No Monzo or Betfair-account call was made.

## Confirmed live

At 18:42–18:49 GMT, read-only production and provider queries established:

| Item | Observed state |
| --- | --- |
| API and payments | Both healthy, revision `031`, SHA `c18e81e`; database readiness passed. |
| 2-1 Hibs | 12 active memberships, maximum 15, existing fee £1; both markets, all product-approved UK competitions. |
| Other active league | Two memberships, maximum 15, no fee; same competition/market scope. |
| Provider | `oddsapi`, Betfair Sportsbook; this is also the sole selected bookmaker. |
| Quota | Response headers confirm 100 requests/hour. The previously recorded 500/day was not independently confirmed. |
| Catalogue | 864 football competitions; current application filters recognise 67 UK and retain 32. |

The production read used an explicitly read-only PostgreSQL transaction. It read
league configuration, aggregate membership/fixture counts and scheduled rounds;
it did not read member identities, payments or credentials into the evidence.
API and payments health checks did not invoke jobs or banking reads.

### Fixtures and prices

Prices were requested once for every pending eligible fixture, using the actual
configured bookmaker and the current application's market/price parser.

| Observed card | 14–15 Nov | 21–22 Nov |
| --- | ---: | ---: |
| Pending fantasy fixtures | 77 | 120 |
| Saturday 15:00 group fixtures | 52 | 90 |
| Fixtures with valid prices | 42 | 27 |
| Sunday fixtures | 10 | 3 |
| Sunday fixtures with prices | 0 | 3 |

The first census additionally contained six cancelled 14 Nov fixtures. They are
excluded above. Every priced fixture had all three match-odds outcomes and both
BTTS outcomes. Price batches ran at 18:45:28–18:45:34 for 21–22 Nov and
18:46:50–18:46:57 for 14–15 Nov; this was not a simultaneous snapshot.

For 21–22 Nov, prices existed for nine Premier League, twelve Championship and
six Scottish Premiership matches. The other 93 fixtures were omitted by the
odds batch response. For 14–15 Nov, 35 were omitted, including all ten Sunday
fixtures. Individual reads of next week's Arbroath–Stenhousemuir and this Sunday's
Celtic–Rangers women's match returned HTTP 200 with empty bookmaker data: these
two gaps were not merely a batch-response parsing problem.

Twenty-seven priced matches already permit every member to choose six different
matches, because fantasy members may overlap. This proves meaningful early
choice; it does not prove every competition or fixture will be priced at opening.
The unpriced fixtures remain usable by the group if they meet its Saturday-15:00
window, since the group has no price dependency.

At 20:04, two additional reads examined the retained price history for
Ayr–Raith on 14 Nov. Both markets' recorded opening timestamp was **9 Nov at
18:18 GMT**, after the proposed previous-Saturday opening. Retained history is
evidence of that recorded opening, not a guarantee that no earlier quote ever
existed. It reinforces the need to measure when lower-division markets appear.
The provider documents the meaning and retention limits of this history in its
[official API schema](https://docs.odds-api.io/api-reference/openapi.json).

Evidence: [request journal](../.local/two-game-feasibility/2026-11-11/requests.jsonl),
[14 Nov coverage](../.local/two-game-feasibility/2026-11-11/price-coverage-2026-11-14.json),
[21 Nov coverage](../.local/two-game-feasibility/2026-11-11/price-coverage-2026-11-21.json),
[production aggregate read](../.local/two-game-feasibility/2026-11-11/production-readonly.json).
These supporting files are local and Git-ignored; they contain no API keys.

## Discovery has a cheaper, demonstrated route

The documented `/events` endpoint accepts a sport/date range without a league
filter. One request with `limit=5000` returned 2,421 football events for
14–15 Nov; another returned 2,511 for 21–22 Nov. Local filtering produced the
cards above. Neither response reached the limit. An event exactly at the upper
date boundary appeared in the first response, so the application must enforce
its own exclusive Monday boundary.

This can replace separate competition/window walks with one complete weekend
census and two local game filters. It also discovers competitions absent from
the existing Saturday fixture pool. The measured discovery cost is one page per
weekend, not 32 competition requests per window. That is a proposed adapter
change; the deployed application still uses its existing walks. Pagination,
truncation, cancellation handling, restart recovery and larger weekends need
implementation tests. A full page must never be mistaken for complete coverage.
[Documented event filters and pagination](https://docs.odds-api.io/api-reference/openapi.json).

Independent schedule reconciliation supports the dates and boundaries:

- All 14 Scottish Championship/League One/League Two fixtures on 21 Nov match
  the [official SPFL indexed listing](https://spfl.co.uk/?page=home_fixtures),
  including fantasy-only Montrose–Alloa at 17:30. Direct SPFL retrieval returned
  403; this comparison uses its dated indexed snapshot.
- All nine 21 Nov Highland fixtures match the directly readable
  [official Highland schedule](https://www.highlandfootballleague.com/Fixtures/).
- The two Sunday Premier League matches and Saturday 12:30/17:30 boundaries
  match the [official Premier League schedule](https://www.premierleague.com/en/news/4675097/all-380-fixtures-for-season-2026-27).
- All five Sunday 15 Nov SWPL2 matches and kick-offs match the
  [official SWPL2 page](https://swpl.uk/match-centre/swpl2/). The provider's
  cancelled Woking–Forest Green entry also agrees with the
  [club's postponement announcement](https://wokingfc.co.uk/10/30/forest-green-rovers-fixture-postponed/).

This is a substantial reconciliation, not an independent census of every
competition. National League regional divisions, Welsh competitions and parts
of the wider women's programme remain incompletely reconciled. The international
break does not make 14–15 Nov empty: the verified lower divisions still play.

## Original burst model — retained as stress evidence

Use shared, paginated weekend discovery, one global budget counting each actual
HTTP attempt, separate member/league abuse limits, and fair durable settlement
chunks. Keep prices off group cards and locked results. These changes are needed
on either provider tier; paying alone does not fix the existing software caps.

The offline model uses the observed 77/120 fixture cards and also assumes every
fixture later becomes priced. It includes both weeks' entries in a rolling hour,
one replacement per member per week, two cold browse cards and 10% extra HTTP
attempts. All figures below are modelled demand, not traffic sent to the provider.

| Supported memberships | Independent slot saves/hour | Optional six-slot save/hour |
| --- | ---: | ---: |
| Current 12 + 2 | 239 | 85 |
| Both existing leagues full: 15 + 15 | 486 | 156 |
| Reference load: 50 + 50 | 1,564 | 464 |

The model deliberately allows cold prices or reuse after the 60-second freshness
period; shared cache hits can reduce demand. Optional bulk saving is not an
approved interaction change. At the currently configured capacity of 30 members,
even that option exceeds the 100/hour quota once replacements are included.
It is not a robust free-tier guarantee.

**Original recommendation, superseded on 12 Nov:** paid capacity while retaining
independent slot saves. That recommendation over-weighted a deliberately
concentrated burst; it does not establish normal traffic needs an upgrade.
The [paced reassessment](two-games-per-week-free-tier-assessment.md) now takes
precedence. At the 11 Nov documentation check, Solo was publicly
priced at £49/month for 5,000 requests/hour and two bookmakers, with no self-serve
free trial. Retain Betfair Sportsbook as the price basis unless a separate
comparison justifies changing it. More quota does not itself create missing
prices. Verify checkout terms and daily entitlement before purchase.
[Official pricing and legacy-free terms](https://odds-api.io/pricing/free).

The larger stress case—two 50-member leagues, four replacements per member per
week, three discovery pages per weekend and 10% extra attempts—models 2,224
requests in the boundary hour and a conservative 2,635 rolling-day envelope.
That hourly demand fits the published 5,000/hour allowance. Complete provider
failure still requires controlled refusal; no tier guarantees successful picks
during an outage. This is a capacity design result, not a built-system guarantee.

Twelve offline scenarios ran with sockets blocked. Shared browse/warm accounting
was checked against the current cache using fake data; fair-chunk progress is
simulated, not database-backed. The earlier 23 selected tests also passed. The
full build gate was not run because this work changes no product code.
[Offline model](../.local/two-game-feasibility/capacity.py),
[reference stress result](../.local/two-game-feasibility/coupon-capacity-reference100-all_become_priced-3pages-output.json).

## What remains and what happens next

1. **Actual opening observation:** a one-off check is scheduled in this chat for
   **14 Nov at 12:00 Europe/London**, targeting 21–22 Nov. It will refresh fixture
   coverage and sample every eligible fixture's prices with recorded request
   times, no retries, at most 30 requests and a production quota reserve. If it
   runs late or lacks quota, it must report incomplete evidence. Codex must be
   available to run the local task; scheduling is not evidence of completion.
2. **Coverage decision after that result:** distinguish “members can enter six
   priced picks at opening” from “every eligible match is priced at opening”.
   The first already has supporting evidence today; the second does not.
   Accepting additional early unpriced fixtures, beyond the existing Highland
   exception, must be explicit. Do not silently shorten the window or freeze
   stale odds to make the gate pass.
3. **Capacity decision, revised 12 Nov:** assess the existing free account with
   scheduled chunks, shared quota and realistic traffic first. Agree supported
   load and visible refresh/result latency; upgrade only if that contract cannot
   fit. Nothing was purchased. The £1 weekly member rule remains unchanged.
4. **Build and activation gates:** Batches 219–228 can implement/test the new
   format while disabled; live acceptance points above gate activation. Keep
   the original storage, dues, legacy history,
   corrections, home overlap, migration recovery, API/payments parity and safe
   activation requirements. No future implementation or natural acceptance has
   been proved by this feasibility run.

Total provider reads: **28**, all HTTP 200, no retries: one selected-bookmaker
read, one catalogue, two event censuses, twenty price batches, two individual
diagnostic prices and two price-history reads. The first window ended with 75
requests remaining; the later history window ended with 98. No quota refusal
occurred. The official usage tool also reads hourly headers; it does not supply
independent daily-quota evidence.
[Official provider tooling](https://github.com/odds-api-io/odds-api-mcp-server).

Operational limits were kept visible: the platform's direct service-object
query returned `Not Authorized`, while the project-contained exact service
lookup and variables read succeeded; no different target was substituted.
Two exploratory workers stopped at their session usage limit; the retained
manifests and capacity model were checked and completed locally. These do not
close the remaining live-opening or full-schedule coverage gaps.
