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

**The odds-budget and scheduler measurements were not completed** — requests per
scheduled job and per member action, the hour-by-hour Saturday budget against the
100/hour and 500/day plan, scheduler job durations and overlap, and event-loop
blocking from the synchronous push sends. **The web performance pass was not
started**: no bundle breakdown, no Lighthouse numbers, no route-splitting
analysis, no re-render or query-key hygiene. Both are listed in
`08-sequencing.md`. Nothing was measured against production, and admin,
authentication and notification routes were not measured at all.
