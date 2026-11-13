# Local provider implementation and counted capacity

13 Nov 2026 · Batch 221 local evidence, not production or activation acceptance.
The implementation remains disabled by default. Full milestone verification is
recorded separately in the overnight report; these focused results alone are not
an acceptance stamp.

## Mechanism

```text
Legacy / new entries / scheduled work
                 ↓
Durable rolling installation admission
                 ↓ commit, release lock
Actual HTTP attempt, including each retry
                 ↓
Receipt / lower header allowance / cooldown

Stored census pages → shared real fixtures
                    → independent game windows
Short work leases   → at most ten price fixtures
                    → shared timestamped quotes
Browse reads        → stored prices and visible age
Pick-time reads     → positive quote at most 60 seconds old
```

Accepted reservations remain spent after business rollback, cancellation and
restart. Response receipts account for earlier unresolved, later and equally
timestamped concurrent requests before provider headers can lower capacity.
No budget or work transaction spans provider I/O. Expired owners cannot overwrite
newer quote/page work. Claim rotation and persisted deferral prevent a failing
prefix starving later work; rejected multi-fixture price chunks split into
single-fixture work rather than endlessly repurchasing the same bad chunk.

The configurable 90/hour and 450/rolling-day ceilings are assumptions. Background
work shares those ceilings, has 10/hour, 120/day and six-minute actual-attempt
spacing, and pauses Saturday 10:00–13:00 London. At noon only the opening fantasy
card's census/pricing can use the shared maximum of five opening attempts;
unrelated optional work stays paused. A once-per-opening generation preserves
failure/backoff timing. Remaining work can re-enter background scheduling at
13:00, still subject to the global meter. These ceilings do not promise five
reserved units if other traffic consumes global capacity first.

Discovery shares a source-scoped Sat00–Mon00 census across both games and
compatible legacy windows. Other legacy weekdays retain their own day ranges.
Each page/cursor commits separately; full pages require continuation. Complete
legacy generations survive partial refreshes and are reconciled against current
shared fixture facts before legacy writes. Moves/voids remove unclaimed links;
accepted history remains. Eligibility is stored independently so a retained
accepted link cannot cause new pricing of a void fixture.

The public [Odds API OpenAPI](https://docs.odds-api.io/api-reference/openapi.json)
documents `/events` with `from`, `to`, `limit` (maximum 5,000) and `skip`, returning
an array. The implementation does not require a price or bookmaker filter for
its census. Local Monday exclusion is explicit. Unsupported pagination, malformed
or truncated responses remain unknown/unavailable; empty data never creates a
confirmed break. The real Betfair fallback has no implemented census port and
returns an explicit unsupported-provider error in the new worker. Its existing
default-off legacy flow remains intact. No live provider was probed.

## Counted cold-quote timelines

These implementation tests use real concurrent PostgreSQL callers and counting
HTTP mock transports. Every requested quote has a distinct cold key; they claim
no cache-sharing discount. They exercise quote admission, not completed API
entries (those are repeated in Batch 224). Memberships can span several leagues;
no member or six-slot limit was reduced.

At noon, five opening calls occur first, then the stated foreground requests
contend for the remaining shared hourly allowance:

| Membership scenario | Foreground admitted / requested | Refused |
| --- | ---: | ---: |
| 14, rush | 85 / 85 | 0 |
| 30, rush | 85 / 177 | 92 |
| 100, cold rush | 85 / 600 | 515 |

Every row makes exactly 90 actual HTTP calls including opening checks. Successful
quote age is zero in the injected clock. Refusals dispatch no HTTP and never
freeze a stale quote. These are declared scenarios, not forecasts or counts of
affected people. Their timing differs from the earlier planning simulation.

For spread traffic, each membership makes six cold slot quotes plus one cold
replacement across five weekdays, at most ten memberships in each two-hour
slot. A quarter rounded up request seven early-next-week quotes at Saturday
noon, after five opening calls:

| Memberships | Total actual HTTP | Refused |
| --- | ---: | ---: |
| 14 | 131 | 0 |
| 30 | 271 | 0 |
| 100 | 790 | 90 |

The 100-membership row admits 700 weekday calls, 85 early-next-week calls and
five opening calls. The remaining 90 early requests are refused. The 14/30 rows
admit all their declared requests. These results do not establish daily account
entitlement or acceptable real request latency.

## Two-card background replay

A scratch league has two future cards, fake priced fixtures and persisted work.
The clock advances six minutes per tick for 48 hours. No member requests occur.
Each HTTP request passes the actual meter, including page and price work.

| Card sizes | HTTP / refusals | Oldest snapshot at end |
| --- | ---: | ---: |
| 77 + 120 | 176 / 0 | 5h 48m |
| 264 + 264 | 240 / 110 | 17h |

All 197/528 distinct fixtures receive snapshots. Every rolling hour stays at
most 10 background attempts; every rolling day stays at most 120. Browse reads
make zero refill calls and retain age/degraded state. Refusals are admission
records, not provider calls. The large-card result fails an unqualified six-hour
coverage promise; the implementation exposes that backlog rather than treating
stale prices as fresh. Settlement/concurrent-entry result latency is tested in
Batch 225 and is not established by this background-only replay.

Evidence: eight focused tests, zero skips; private machine logs and JUnit
properties are in `.local/overnight-two-games/221-capacity-second.log` and
`221-capacity-final.xml`. That run predates the final health/legacy reconstruction
fixes; the full milestone gate must verify the final tree. The initial seven-case
run passed with seven JUnit-family metadata warnings; the expanded eight-case
run used the compatible metadata output format and had no warnings. No gate,
protected fixture or assertion was weakened.

## Activation remains unaccepted

Live opening fixture/market coverage, actual daily entitlement, supported
traffic, acceptable snapshot/result delay and real foreground latency are still
owner acceptance gates. No arbitrary coverage percentage or membership cap is
introduced. Local overload evidence does not authorise purchases, a new provider,
shipment or activation. The saved 14 Nov observation remains separate and was
not run, altered or awaited by this implementation.
