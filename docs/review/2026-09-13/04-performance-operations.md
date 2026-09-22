# 04 — Performance and operations

Neither prior review measured performance, so this one states numbers. The API
was measured in process against scratch PostgreSQL with a statement-counting
listener, at two data shapes: **production's** (5 leagues, largest 12 members,
6-7 rounds each, a shared pool of about a thousand fixtures) and a **stress
shape** (an added 50-member league with a full season of about 40 settled rounds
at ~200 fixtures each and a pick per member per round). Timings were repeated and
taken as median and 95th percentile on a shared four-core machine, so **query
counts and plans are the primary evidence and wall times are indicative**.

## The numbers

Production shape → stress shape. "stmts" is SQL statements per request.

| endpoint | stmts | DB ms | p50 | p95 | bytes |
| --- | --- | --- | --- | --- | --- |
| home cross-league summary | 15 → 15 | 20.1 → 22.8 | 47 → 53 ms | 114 → 125 ms | 5.4 KB |
| current round / slate | 12 → 12 | 12.2 → 11.2 | 30 → 34 ms | 31 → 43 ms | up to 84 KB |
| combined coupon | 6 | — | — | — | — |
| standings (with and without season) | 5 | — | — | — | — |
| results | 7 | — | — | — | — |
| rounds list | 8 | — | — | — | — |
| **pick submit** | **12 → 12** | — | 33-38 ms | — | 0.4 KB |

**There is no N+1 anywhere.** Every statement count is identical at both shapes,
and identical for a member in one league versus three. That is the single most
important performance result in this review and it is worth protecting.

Under 20 concurrent home-summary requests the same call goes from 53 ms to
**1,254 ms each**, with p50 equal to p95 equal to the maximum — the signature of
a queue rather than contention. About three quarters of that wall time is Python
CPU, not database.

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| OPS-11 | HIGH | live | verified | Node 20 passed end-of-life in April and is still what CI and the web build use |
| OPS-12 | HIGH | live | verified | Every shipment that carries a migration leaves the API with no rollback target |
| OPS-13 | HIGH | live | verified | There is no working backup: recovery point unbounded, recovery time undefined |
| OPS-14 | MED | live | plausible | The silence and provider alarms only reach a dashboard; nothing pages the owner |
| PERF-01 | MED | main-only | verified | The new season-calendar labelling loads every round in the deployment, twice per home request |
| PERF-02 | MED | live | verified | One worker: concurrent requests queue rather than overlap |
| PERF-03 | MED | live | verified | An 84 KB slate is served uncompressed |
| PERF-04 | MED | live | verified | The round-sweep queries cannot use the pick index that exists, and the round date column has none |
| PERF-05 | LOW | live | verified | The connection pool is sized for concurrency the process cannot use |
| OPS-15 | LOW | live | plausible | The web build toolchain is several majors behind |
| OPS-16 | INFO | live | verified | A docstring claims nine queries where there are fifteen |
| PERF-06 | HIGH | live | verified | The hourly slate refresh walks the whole competition pool, twice a day |
| PERF-07 | HIGH | live | verified | A third league window breaks both the hourly and the daily provider plan |
| PERF-08 | HIGH | live | verified | The plan counter cannot see roughly half the requests, including the largest consumer |
| PERF-09 | HIGH | live | verified | The per-league pick bucket does not bound the installation: 20 leagues can spend ten times the plan |
| PERF-10 | MED | live | verified | Submitting a pick waits for every push in the league to be sent, one after another |
| OPS-17 | MED | live | verified | No scheduled job sets a misfire grace time, so all thirteen take the one-second default |
| PERF-11 | MED | live | verified | The service worker precaches the entire app, undoing the route splitting |
| PERF-12 | MED | live | verified | An animation library is 14% of all JavaScript and 62% unused on home |
| PERF-13 | MED | live | verified | The lock countdown re-renders the whole pick screen every second |
| PERF-14 | MED | live | verified | Standings blocks the main thread for 915 ms on a throttled phone |
| PERF-15 | LOW | live | verified | Two context values are rebuilt on every render |
| PERF-16 | LOW | live | verified | Query keys are ad-hoc, and one omits the season it depends on |
| PERF-17 | LOW | live | verified | Three font files load on the sign-in screen, one of them preloaded |
| OPS-18 | LOW | live | verified | Four jobs share the top of the hour and an overrun is dropped rather than queued |

## OPS-11 · HIGH · live · verified — the runtime is past end-of-life

Node 20 reached end-of-life on 30 April 2026. It is pinned for CI and is what
the web app is built with; the package manifest only sets a floor that has never
been raised. Python 3.12 on the API is fine (supported to late 2028).

**Member impact:** the web app is built and tested on a runtime that no longer
receives security fixes.

**Fix:** move CI, the local gate and the Vercel build to Node 22, raise the
engines floor, and re-run the gate.

## OPS-12 · HIGH · live · verified — a migrating shipment removes the rollback target

A previous deployment can only be rolled back to if its image can boot against
the database as it now stands. Any shipment that applies a migration leaves the
previous image unable to resolve the new revision, so the moment it lands there
is nothing to roll back to at the API tier — recovery is forward-only until the
next shipment that applies no migration. `STATUS.md` has recorded this
situation repeatedly, each time as a one-off. It is structural, and it applies to
the shipment that is currently owed (migration 025).

**Member impact:** if a shipment breaks the Saturday, the fix has to be written
and deployed under pressure; there is no way back.

**Fix:** require a written forward-recovery note for any batch that adds a
migration (the repo has done this by hand before), and make the deployment
workflow assert one exists. Longer term, prefer expand-then-contract migrations
so the previous image can always boot.

## OPS-13 · HIGH · live · verified — there is still no backup

No scheduled backup job is registered. The backup service writes to a local
directory whose default is inside the container, which does not survive a
redeploy. The restore-rehearsal script exists but has no off-box destination. So
the recovery point is unbounded and the recovery time undefined: a database loss
today loses every pick, price and point the game has recorded.

This is not a new discovery — it is the known Batch 95 gap, deferred by the owner
twice and soft-blocked on the unattributed storage-egress consumer. It is
restated here with its current cost measured, because it remains the largest
standing risk in the product and it has now been open across three reviews.

## OPS-14 · MED · live · plausible — the alarms do not reach a person

The discovery-silence alarms and the football-provider trigger write to the admin
dashboard and the logs. Nothing pushes, emails or otherwise reaches the owner. The
failure they exist to catch — discovery producing nothing — went unnoticed for a
week before, and the mechanism that would surface it now still requires somebody
to look.

**Fix:** route the existing alarms to the push channel the product already has.

## PERF-01 · MED · main-only · verified — the new labelling reads the whole deployment

The season-calendar labelling helper loads **every round in the deployment** as
ORM objects to derive labels, and the home summary calls it twice. At 76 rounds
that is 3.5 ms per call; at 963 rounds it is 16 ms, and it grows with every round
every league ever plays. A distinct-value projection measured 7.6× cheaper.

Not live yet — it arrives with the owed shipment.

**Fix:** project only the columns the labels need, and compute once per request.

## PERF-02 · MED · live · verified — one worker

The API runs a single uvicorn worker with no `--workers`, so requests do not
overlap and a burst queues behind whatever is in front of it. Measured above:
twenty concurrent home summaries take 1,254 ms each.

Considered for HIGH and rejected: with today's membership, genuinely concurrent
in-flight requests are single digits, and the numbers only become member-visible
near roughly 150 concurrent. It flips to HIGH as the deployment grows.

**Complication:** the scheduler runs inside the web process, so adding workers
would multiply the scheduler too. That makes this an owner decision rather than
a straightforward fix.

## PERF-03, PERF-04, PERF-05

**PERF-03** — a fully-priced 264-fixture slate is about 84 KB of JSON, served
with no compression anywhere in the API and no `vary: accept-encoding` from
production. That is the single biggest payload a member downloads, on a phone,
on a Saturday morning.

**PERF-04** — `picks` *is* indexed, by a composite on `(league_id, gameweek_id)`,
but that index is left-anchored on the league, so it cannot serve the lookups
filtering on the round alone — the existence check inside stranded-round
retirement and the settle sweep — which is what the stress-shape plans showed
scanning. `gameweeks.starts_on`, which retirement and discovery range over, has
no index at all. Invisible at today's size; the first thing to bite as rounds
accumulate. (Corrected on reconciliation — the first write-up said picks were
unindexed; see `09-reconciliation.md`.)

**PERF-05** — the connection pool allows ten plus ten overflow against one
Postgres, from a process that executes one statement at a time. Harmless, but it
is sized for a concurrency the process cannot produce.


## The provider budget, measured

A Saturday at production's shape — one league, twelve members, one window —
spends **283 of the 500-a-day plan**, peaking at **63 of 100 in the 09:00 and
11:00 hours**. Both peaks are the scheduler, not members: saturated browsing
costs 20 requests an hour, freezing a pick costs **one**, and a `PRICE_MOVED`
retry inside the cache window costs **nothing**.

That is the headline, and it reframes the whole budget question: **the members
are not the problem, the jobs are.**

| | requests |
| --- | --- |
| Saturday total, production shape | 283 / 500 |
| worst hour | 63 / 100 |
| of which `refresh_slate` | 82 a day, both peaks |
| saturated member browsing | 20 / hour |
| freezing a pick | 1 |
| `PRICE_MOVED` retry within 60s | 0 |
| **at three windows** | **145 / hour, 527 / day — both broken** |

### PERF-06 · HIGH — the hourly refresh walks everything

`run_refresh_slate` calls discovery with **no competition list**, so it walks the
full pool — 41 competitions where the daily job, narrowed by Batch 119, walks 20.
It is 82 of the day's 283 requests, and at three windows it alone is **123 in a
single hour**, twice a day. Batch 119 narrowed one caller and missed this one.
**Fix:** pass the same narrowed set the daily job passes.

### PERF-07 · HIGH — the third window is the cliff

Two windows already sits at 82 requests. A third takes the hour to **145** and
the day to **527**, breaking both limits. Production has one window today, so
this is not live pressure — it is one league-settings change away, and nothing
in the code refuses it. **Fix:** give discovery its own budget (Batch 133) and
land PERF-06 first, which halves the cost of every extra window.

### PERF-08 · HIGH — the counter is blind to its biggest consumer

The plan counter is charged **only from the odds cache** — `fetch_odds`
refreshes. `fetch_slate`, `fetch_competitions` and `settle` are separate provider
entry points that never reach it, so the gauge sees roughly **127 of 283**
requests. Both the cache's widening valve and the **50-request reserve that
protects the pick path** read that gauge. Batch 114 built the reserve precisely
so a member could still freeze a price on a busy morning; it is reserving
against a number that misses half the spend. **Fix:** charge every provider
entry point, not just the cached one.

### PERF-09 · HIGH — the per-league bucket is not an installation ceiling

The pick path charges a per-league bucket of 50/hour against a plan of 100/hour.
At **5 leagues that is 250/hour — 150 over**; at **20 leagues, 1,000/hour, ten
times the plan**. It is real spend rather than a ceiling because the refusal
path exempts the pick path deliberately. This is the OPS-10 residual the last
review recorded as unbounded, now with numbers. **Fix:** charge a shared
installation bucket beneath the per-league one.

### PERF-10 · MED — the pick waits for the whole league's phones

Measured: `notify_pick_made` performs **49 sequential sends taking 8,759 ms**,
added to the submitting member's request on a 50-member league — about **1.7
seconds at production's twelve**. The event loop is not blocked; the member's own
request is, on the one action the product is built around. **Fix:** hand the
fan-out to a background task and answer the member immediately.

### OPS-17 and OPS-18

**OPS-17** — not one of the thirteen scheduled jobs sets `misfire_grace_time`,
so every one takes the one-second default: a job that fires while the single
worker is busy is dropped rather than run late. Measured peak event-loop lag was
387 ms against a 33 ms baseline, so the window is real.

**OPS-18** — four jobs share the top of the hour, and an overrun is dropped
rather than queued.

Job durations against a 50-member, 38-round, 1,520-fixture database were all
**≤113 ms except `sync_football_data` at 931 ms** — and those are the database
and CPU floor only, since the fake provider answers instantly.

## The web client, measured

| | |
| --- | --- |
| bundle | 823.6 KB JS raw, 278.8 KB gzip, **67 chunks** |
| cold `/login` | 9 requests, 166.6 KB |
| reaching home | ~34 requests, ~253 KB |
| then the service worker precaches | **974 KiB across 82 files**, admin chunks included |
| Lighthouse mobile (median of 3) | login **98** · home **92** · current round **95** · standings **77** |
| worst blocking time | standings **915 ms** |
| API calls per screen | home 2 / 2.1 KB · current round 4 / 8.7 KB · standings 4 / 4.3 KB |
| **idle polling** | **0 requests in 5 minutes** on home and on current round |

**The client does no background polling at all.** Between actions a member costs
the API nothing, which is why the provider pressure above is entirely
scheduler-side. Worth protecting.

### PERF-11 · MED — the service worker undoes the code splitting

The app *does* split routes — a `lazyRoute` helper, 67 emitted chunks. Then the
service worker precaches **all 82 files, 974 KiB**, including the admin console
chunks, on install. Every member downloads the whole application including
screens they can never open. **Fix:** exclude admin and other role-gated chunks
from the precache manifest and let them load on demand.

### PERF-12, PERF-13, PERF-14

**PERF-12** — the animation library is **107.1 KB minified, 13.9% of all
JavaScript, and 62.2% unused on home**.

**PERF-13** — `useCountdown` sits in the page body, so the lock countdown
re-renders the entire pick screen once a second. There is **no `React.memo`
anywhere in the codebase**, so nothing stops the cascade.

**PERF-14** — standings blocks the main thread for **915 ms** on a throttled
phone, the worst figure in the set. The number is solid; the cause was not
isolated, and PERF-12 and PERF-13 may account for most of it — **re-measure
after those two before chasing it.**

### PERF-15, PERF-16, PERF-17

The auth and league context values are rebuilt on every render (PERF-15). Query
keys are ad-hoc strings with no factory, and the standings key omits the season
it depends on — two seasons share one cache entry (PERF-16). Three of four font
files load on the sign-in screen, 49 KB, one preloaded (PERF-17).

## Deploy hygiene — checked

The drift script, the deployment-config assertions, the migration guard's
single-replica precondition and the health and readiness routes all behave as
documented. The Batch 113 admin Calendar route is confirmed absent from
production (404) while its page is live on the web — the expected consequence of
the owed shipment, and the subject of PIPE-05 in the pipeline lens.

Prior items unchanged: the local environment file still points at another
product's API (local only); the cryptography pin is still capped by the macOS
wheel constraint; the migration guard is wired end to end.

## Proposed batches

1. **The web app is built on a runtime that is past end-of-life** (OPS-11) — tooling-only.
2. **A migrating shipment leaves nothing to roll back to** (OPS-12) — tooling-only plus a workflow assertion.
3. **The game's scored history still has no second copy** (OPS-13) — this is the existing Batch 95; unblock it.
4. **The alarms that watch for silence do not reach anyone** (OPS-14) — API-carrying.
5. **Home reads every round in the deployment to draw its labels** (PERF-01) — API-carrying, before the next ship if possible.
6. **The slate is served uncompressed** (PERF-03) — API-carrying.
7. **Index the round date and the pick lookup** (PERF-04) — migration.

## Owner decisions

- **Does the API get more than one worker?** The scheduler lives in the web
  process, so more workers means more schedulers. Recommendation: stay at one
  worker now, and move the scheduler out before the deployment reaches roughly
  ten leagues.
- **Batch 95 backups**: the storage-egress investigation has still not happened,
  and it is what blocks the only fix for OPS-13. Recommendation: do the
  attribution, then land Batch 95.

## What this pass did not do

No measurement against production, and admin, authentication and notification
routes were not measured at all. Real provider latency is not measured — the
wall-clock estimates use a nominal 300 ms per call, so the **request counts are
the evidence and the timings are indicative**. `sync_football_data` was measured
on its failure path. FotMob's own daily plan was not modelled at 15 leagues.
Thread-pool saturation under concurrent submits was not tested.

The machine ran at a load average of 7-92 throughout, shared with two other
passes, so every millisecond figure carries roughly ±30% and the
load-independent numbers — request counts, bytes, chunk counts, query counts —
are what the findings rest on.
