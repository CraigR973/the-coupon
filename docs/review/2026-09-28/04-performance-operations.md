# 04 — Performance and operations

Status: **in progress** (sections marked *pending* are not yet measured).

## Method

The API was measured in process against a scratch PostgreSQL (the shared harness's
`stack.py --name perf --no-api`, migration 026) with a statement listener on the app's own
engine, at the two data shapes the 2026-09-13 pass used, rebuilt from its description
because its seeding scripts were lost (`notes/04-perf/seed_shapes.py`):

- **production shape** — 5 leagues (largest 12 members), 6 settled + 1 open round each,
  1,174 pooled fixtures; the open round holds 264 fixtures across 23 competitions
  (production's largest measured round); one league on a Friday window, so two windows.
- **stress shape** — that plus a 50-member league with 40 settled rounds (34 in 2025/26,
  6 in 2026/27) at 200 fixtures each and one pick per member per round: 76 rounds,
  8,364 fixtures, 2,295 picks. Season calendars exist for both seasons (production's
  table is empty today, so production pays slightly less for labels than measured).

Statements are split at the moment the final response body leaves the app, so the
Batch 162 background fan-out is counted apart from the member's request. Odds come from
an in-process fake that prices every fixture in both markets — the fully-priced upper
bound for payload size. `notes/04-perf/measure_api.py` → `api-production.json`,
`api-stress.json`, and the SQL of every request in `api-*-sql.txt`.

The machine is shared with other passes; `uptime` is recorded beside every timing, and
**counts, plans and bytes are the evidence**. Production was touched only for response
headers on `GET /api/v1/health`.

## The numbers

Production shape → stress shape. "stmts" is SQL statements on the member's request.

| endpoint | stmts 13 Sep | stmts now | bytes identity → gzip |
| --- | --- | --- | --- |
| home summary (1 league, 3 leagues) | 15 → 15 | **13 → 13** | 2.0 KB; 5.5 KB → 1.5 KB |
| current round / slate | 12 → 12 | **56 → 66** | 299 KB → **15.2 KB** (264 fully priced) |
| combined coupon | 6 | 6 → 6 | 3.2 KB; 11.7 KB → 2.4 KB (50 legs) |
| standings (with and without season) | 5 | 5 → 5 | 10.4 KB → 1.2 KB; 43 KB → 3.7 KB |
| results | 7 | 7 → 7 | 1.3 KB; **500 at stress** (PERF-19) |
| rounds list | 8 | 8 → 8 | 1.7 KB; 10 KB → 1.9 KB |
| account export (new) | — | 6 → 6 | 6.1 KB → 1.0 KB; 11 KB → 1.7 KB |
| pick submit | 12 → 12 | **11** + 3 after the response | 0.5 KB |

Every count is identical at both shapes **except the slate**, which grows with the
number of competitions on the card rather than with data volume (PERF-18). The home
summary at the stress shape returned **500** for a member of the 50-member league
(PERF-19).

## The web client, measured

Production bundle built by the harness against the local API and served by
`vite preview`; real Chromium (Playwright 1.x, Node 24), service worker blocked for the
page counts. `notes/04-perf/bundle.mjs` → `bundle.json`; `browser.mjs` →
`browser-run1.json` (120 s idle) and `browser.json` (render counts).

| | 13 Sep | now |
| --- | --- | --- |
| bundle | 823.6 KB JS raw, 278.8 KB gzip, 67 chunks | **697.3 KiB raw, 237.6 KiB gzip, 68 chunks** |
| cold `/login` | 9 requests, 166.6 KB | 9 requests, 168.6 KiB gzip (439 KiB raw) |
| reaching home | ~34 requests, ~253 KB | 23 requests after sign-in; a warm reload of home 31 requests, 224 KiB gzip |
| service worker precache | 82 files, 974 KiB, admin included | **70 entries, admin excluded** (0 admin chunks fetched, 70 in the precache cache) |
| API calls per screen | home 2 · round 4 · standings 4 | home 3 (5.9 KiB) · round 5 · standings 5 (13 KiB) |
| idle requests | 0 in 5 min | **0 in 120 s** on home, the round screen and standings |
| idle renders per 5 s, round screen | whole screen every second | **5 commits × 1 component** |
| Lighthouse mobile | 98 · 92 · 95 · 77 | *pending a quiet machine* |

## The provider budget, measured

`notes/04-perf/provider_budget.py`: the real `OddsApiProvider` on an `httpx.MockTransport`
that serves a synthetic odds-api.io (67 UK competitions, 41 played; a pool history of 36
competitions, 23 played; 264 fixtures on a Saturday, a third unpriced) and counts every
request — the ground truth — wrapped in the real `CachingOddsProvider` and installed as
the process-wide `odds_session`. The real jobs run on a virtual clock from Thu 1 Oct
05:00 to Sun 4 Oct 00:00 London; members load every league's current round once a
minute from 08:00 to 23:00 through the pick screen's own `askable` →
`fetch_odds_best_effort` → `record_observations` path, and 15 prices are frozen on
Saturday morning. Saturday is the measured day. `budget-1w.json`, `budget-3w.json`,
`budget-5w.json`, `budget-summary.txt`.

| Saturday | 13 Sep | 1 window | 3 windows | 5 windows |
| --- | --- | --- | --- | --- |
| day total (plan 500) | 283 | **289** | **337** | 376 |
| worst hour (plan 100) | 63 | 54 (07:00) | 72 (09:00) | **118 (09:00 and 11:00)** |
| `refresh_slate`, per run | 41 per window | **23** | 69 | **115** |
| `discover_fixtures` (06:00) | — | 46 | 46 | 46 |
| `warm_odds_marker` (07:00) | — | 54 | 32 | 37 |
| settle (18:00 / 20:00 / 22:00) | — | 12 / 0 / 0 | 12 / 0 / 0 | 12 / 0 / 0 |
| a frozen pick | 1 | 1 | 1 | 1 |

Discovery is 46 at every window count because its budget (90) prices each walk at the
raw pool of 36 competitions while 23 are walked, so it stops after two `(window, date)`
walks: at three windows the third window and every second date go unwalked by the daily
run (lens 02's CORR-24 found the same from the code). The refresh job has no budget at
all and is linear in windows.

### How "the certified worst day is 481" is derived — and why it is not a bound

`tests/test_request_budget.py` sums five terms (`session-log.md`, Batch 115 fix):
saturated browsing **252** (one 264-fixture round, 89 unpriced, browsed continuously
for 24 hours through the 4h / 2h / 1h tiers) + daily discovery **92** (23 competitions ×
2 windows × 2 dates) + the Sunday full-catalogue walk **41** + one cold warm pass **27**
(`ceil(264/10)`) + the whole manual admin allowance **69** (3 walks a day × 23) = **481**.

Each term is honestly derived, but the sum is not the day's ceiling:

- **the twice-daily refresh is missing** — 2 × 23 × windows, **92 at the two windows the
  discovery term assumes** (46 at one);
- settlement (one `/events/{id}` per distinct pending fixture, 12 at production) and a
  second warm round (the warm pass covers every round inside a week — 54, not 27, at one
  window) are missing;
- the pick path's own 100/day installation bucket is certified only against browsing +
  discovery, never beside the rest;
- browsing is priced for one round while discovery is priced for two windows; each extra
  window is another round to browse;
- the discovery term (92) is above discovery's own 90 budget, and in practice discovery
  spends 46 because of the mispricing above.

At its own two-window assumption the omitted scheduled terms add roughly 130 a day
(refresh 92, settle 12, a second warm round 27), before any pick. What actually keeps a
day inside the plan is the runtime valve — browsing widens 2× and 4× as the tighter of
the hourly and daily allowance falls below half and a quarter, and is withheld below the
50-request pick reserve — and Batch 160 made the gauge that valve reads honest. The
certificate is a useful tripwire on the terms it covers; **the measured Saturday (289 at
one window) is the better number to quote.** No finding is raised on the test itself
(it is lens 07's gate), but STATUS's "certified worst day is 481" should say what it
leaves out (see Doc corrections).

## Prior findings

*Partial — rows are added as each is re-driven.*

| id | batch | verdict | evidence |
| --- | --- | --- | --- |
| PERF-01 + OPS-16 | 144 | **held** | home summary 13 statements at both shapes and for 1 or 3 leagues (was 15); one `SELECT DISTINCT gameweeks.starts_on` projection, not whole rounds (`api-*-sql.txt`) |
| PERF-04 | 146 (migration 026) | **held** | the SQL the app actually runs, captured from `retire_stranded_rounds` and the settle sweep at the stress shape and explained: retirement's pick-existence check is an `Index Only Scan using ix_picks_gameweek_id`, the settle sweep's pending-pick read a `Bitmap Index Scan on ix_picks_gameweek_id` — both by the planner's own choice. The 76-row `gameweeks` table is still sequentially scanned, correctly at one page; with seq scans disabled both reads take `ix_gameweeks_starts_on` (`explain-stress.txt`) |
| PERF-05 | 146 | **held** | pool is 5 + 5 with a 10 s `pool_timeout` (`database.py`), down from 10 + 10 — but see PERF-20 for what now holds a connection |
| PERF-06 / PERF-07 | 159 | **held at three windows; the cliff moved to four** | counting fake (below): the refresh job walks 23 competitions per window per run, not 41. Three windows: Saturday peak **72/hour**, day **337** (was 145 and 527). Five windows: **118/hour** in both refresh hours — see PERF-21 |
| PERF-08 | 160 | **held** | across three simulated days at 1, 3 and 5 windows the plan counter's hourly figure equalled the transport's count in **every hour** (0 mismatches), and `requests_made` equalled the transport total (744, 929, 1,118) |
| PERF-11 | 163 | **held as scoped** | the build's manifest is still every emitted file (83 entries; the plugin prints 745.7 KiB), but `sw.ts` filters it through `isRoleGatedChunk` before `precacheAndRoute`: 13 admin and league-admin chunks (61.5 KiB) are dropped, so a member's service worker fetches **70 entries, 798 KiB on disk** — 55 member-route JS chunks (636 KiB), 9 icons (64 KiB), 3 fonts, the CSS and the shell. That is what Batch 163 asked for (keep the routes every member uses); the saving is 7 %, because the admin chunks were never the bulk (`bundle.json`) |
| PERF-12 | 164 | **held** | no chunk contains framer-motion or its runtime (`chunks_mentioning_framer_motion: []`); JS is **697.3 KiB raw / 237.6 KiB gzip in 68 chunks** (was 823.6 KB / 278.8 KB in 67). The dependency is still declared (PERF-22) |
| OPS-11 | 127 | **held** | Node 24 in all three CI jobs (`ci.yml:61,78,97`), in the gate (`ci-local.sh:188`, `nvm use 24`), `.nvmrc` 24 and `apps/web` `engines.node: 24.x`, which is what the Vercel project builds from. Vercel's runtime itself is not observable read-only |
| OPS-15 | not batched (owner, 24 Sep) | **not fixed, wider** | declared → current on npm today (`npm-latest.txt`): Vite 5 → 8, ESLint 8 → 10, Tailwind 3 → 4, Vitest 2 → 5, vite-plugin-pwa 0.20 → 1.3, React 18 → 19, TypeScript 5 → 7. Three majors behind on the build tool now, against "several" on 13 Sep |
| PERF-13 | 165 | **held** | a stub DevTools hook counting components that actually rendered in each commit (cloned fiber + `PerformedWork`), 3 × 5 s idle on the 264-fixture round screen at 390 px: **5 commits, 1 component each** — the countdown alone (`browser.mjs`, run 2). Home: 5 commits of 3 components. Standings: none |
| PERF-15 | 165 | **held** | both context values are `useMemo`'d (`AuthContext.tsx:315`, `LeagueContext.tsx:87`) |
| PERF-16 | 165 | **held for the standings key; factory partial** | `queryKeys.standings.forSeason` keys `'current'` apart from a named season; 42 inline `queryKey: [...]` literals remain outside the factory |
| PERF-17 | 164 | **not fixed** | cold `/login` still downloads **three font files, 48.8 KiB, one preloaded** (`jetbrains-mono-600`, `outfit-400`, `outfit-600`) — the same payload as 13 Sep. Batch 164 removed a fourth file from the app, not from the sign-in screen (`browser-run1.json`) |
| PERF-10 | 162 | **held** | real uvicorn on :8141, every webpush replaced by a 179 ms sleep in the executor (the per-send time implied by 49 sends in 8,759 ms): a pick in the **50-member league answered in 63 ms**, its fan-out finished 9.5 s later; in the 12-member league 213 ms, fan-out 2.2 s later. Each eligible member got **exactly one** send, the picker none (`push-fanout.json`). But see PERF-20 |
| PERF-09 | 161 | **held** | the real limiter, charged in the route's order (league bucket, then installation): 1, 2, 5 and 20 leagues × 60 attempts each allow **50 provider-spending submissions in the hour in every case** (was 50 × leagues). `pick-buckets.txt`. The price is PERF-23 |
| PERF-02 | owner decision (one worker; move the scheduler out before ~10 leagues) | **unchanged, as decided** | still one uvicorn process with the scheduler inside it (`nixpacks.toml` start command, `main.py` lifespan); one live league. Concurrency re-timing *pending a quiet machine* |
| OPS-17 | none | **not fixed** | `create_scheduler()` started paused: all **13** registered jobs have `misfire_grace_time = 1`; only the switched-off `offsite_backup` sets 3,600 (`jobs.json`). Re-driven: the real `lock_gameweeks` job, due while the loop was busy 0.5 s, ran; busy 1.5 s, it was **dropped** — "was missed by 0:00:01.4" (`misfire-demo.txt`) |
| OPS-18 | none | **not fixed** | on a Saturday **every hour** at :00 runs `lock_gameweeks` + `live_scores`, and 06:00, 07:00, 09:00, 11:00, 18:00, 20:00 and 22:00 add discovery, the warm pass, the refresh or settle — three jobs in one second. `coalesce=True, max_instances=1` still drops an overrun. At the stress shape with an instant provider the costliest are settle (32 statements, ~1.0 s at load 6) and discovery (19, 88 ms); the rest are 1-2 statements (`jobs.json`) |
| OPS-12 | 128 | **held** | rehearsed locally (`ops12-recovery-rehearsal.txt`): `--deployed 026` → PASS, nothing applied; `--deployed 025` → PASS, 026's 99-line plan found; `--deployed 024` → **exit 1**, "025 FAIL — no plan"; `--plan-for 025 026` → exit 1. `ship-prod.md` step 7 runs it and says exit 1 or 2 may not be uploaded past. Enforcement is the workflow's instruction to an agent, not a hook (lens 07's territory) |
| OPS-13 | 95 (built, switched off) | **not fixed — open across four reviews** | Batch 95's weekly job registers only when `BACKUP_STORAGE` is not `none` (`scheduler.py:1070`, default `none`, `config.py:326`); STATUS (28 Sep) records it off and "no backup yet". Not observable read-only. **RPO today: unbounded** — no durable copy of production has ever existed (Batch 75 removed a nightly dump that only ever wrote to `/tmp`); **RTO: undefined**, because there is nothing to restore. Raised as FEAT-A02 (HIGH) on 26 Aug and OPS-13 (HIGH) on 13 Sep; deferred by the owner since 30 Jul. What remains is owner work, not code: the bucket, the key, the egress check (FEAT-A09's consumer is still unattributed) and one manual run |
| OPS-14 | 129 | **held** | real `report_discovery_silence()` on the scratch DB with every round aged 10 days and one site admin subscribed: run 1 alarm + **1 push**, runs 2 and 3 alarm + **0 pushes** (durable cooldown), healthy run **0** (`alarm-push.txt`) |
| PERF-03 | 145 | **held locally; not checkable in production read-only** | 264-fixture slate 299,134 B → 15,202 B with `content-encoding: gzip`, `vary: Accept-Encoding`; responses under 4 KB deliberately uncompressed. Production's only public API responses (`/health`, 82 B) sit below the floor, so no header could prove it (`prod-health-headers.txt`) |

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| PERF-19 | HIGH | live | verified | A league of 40-50 members breaks its home screen and results once the combined odds pass about 10^26 |
| PERF-20 | MED | live | verified | Each background fan-out holds a pooled connection for its whole run: a burst of picks in a big league exhausts the pool, fails picks with 500 and silently drops alerts |
| PERF-21 | MED | live | verified | The slate refresh has no budget: five league windows spend 118 requests in each refresh hour |
| PERF-23 | MED | live | verified (hour) | The installation pick bucket caps the whole deployment at 50 submissions an hour and 100 a day, counting changes of mind |
| OPS-19 | LOW | tooling | verified | The deploy and rollback commands still run the Railway and Vercel CLIs on Node 20 |
| PERF-22 | LOW | live | verified | framer-motion is still a declared dependency though nothing imports it |
| PERF-18 | MED | live | verified | The slate makes two queries per competition on the card — 56 statements at production's 23 competitions |

## PERF-19 · HIGH · live · verified — the combined odds overflow in large leagues

`combined_odds` (`services/coupon.py:30-40`) multiplies every leg and quantizes to two
decimal places under Python's default 28-digit decimal context. A product at or above
about 10^26 cannot be represented to 2 dp there and raises `decimal.InvalidOperation`,
which is uncaught on all four call sites: the home summary (`routers/me.py:469`, `:552`),
the combined coupon (`services/coupon.py:179`) and the results screen
(`services/scoring.py:773`).

Measured with the app's own function (`notes/04-perf/combined-odds-limit.txt`): 20 legs
fail only at 19.96 each, but **30 legs fail at an average leg of 7.36, 40 at 4.47 and 50
at 3.32**. At the stress shape (50 members, prices 1.30-9.00) the home summary and the
results screen both returned **500** for members of that league; the 12-member leagues
beside it were unaffected (`api-stress.json`).

Tried to disprove: no decimal context is set anywhere in `apps/api/src` (grep for
`getcontext`/`localcontext` is empty); the threshold is a property of the arithmetic,
not the seed; `max_members` accepts up to 50 (`routers/leagues.py`); and the game scores
`round(odds × 10)`, so members are rewarded for longer prices, which pushes the average
leg up rather than down. Not live pressure today — production has one league of 13 — but
nothing refuses the league size that triggers it.

**Member impact:** in a big league, the home screen fails for every member (the summary
is one call across all their leagues) and the results history fails for the league once
any settled round's accumulator passes the limit — permanently, since history does not
change.

**Fix:** quantize inside `decimal.localcontext()` with enough precision (or cap the
displayed price and flag it), and add a 50-leg test at realistic prices.

## PERF-20 · MED · live · verified — the fan-out holds a connection; a burst exhausts the pool

Batch 162 moved the pick alert after the response, into `_announce_after_response`
(`routers/picks.py:492-553`). That function opens one session and keeps it across every
send — `send_notification` reads the member's mute, preferences and subscriptions on it,
then awaits the webpush in the executor, member after member — so each fan-out holds a
pooled connection for its whole duration: ~9 s at 50 members. Batch 146 sized the pool
at 5 + 5 on the reasoning that ten is "more than the scheduler and a Saturday-morning
league can occupy at once" (`database.py:13`); ten fan-outs in flight is exactly ten.

Measured over real HTTP (`push_fanout.py`, `push-fanout-errors.txt`): **12 members of
the 50-member league submitting at once** → 10 answered 201, **2 answered 500 after
10.15 s** (`QueuePool limit of size 5 overflow 5 reached, connection timed out`), and of
the 10 successful picks **only 4 fan-outs ran** — the other 6 died acquiring a connection
at the top of `_announce_after_response`, outside the `_announce` wrapper that swallows
failures, so 294 alerts were never sent and nothing retries them (Batch 107's retry
covers only the all-picked completion). The pool sat at 10 checked out for the whole
fan-out window.

Considered for HIGH and rejected: no pick is lost — the two 500s failed before commit and
a retry succeeds — and the condition needs roughly ten picks inside one fan-out window in
a large, well-subscribed league (at production's 13 members with 7 subscriptions a
fan-out is about a second). It is the lock-time rush in a 30-50 member league that
reaches it. Load average 3.5-4.7 during the run; the mechanism (one connection per
fan-out, ten in the pool) does not depend on it.

**Member impact:** in a big league at the deadline, some members' picks fail with an
error they read as "may not have been sent", and most of the league is never told who
picked what.

**Fix:** release the connection during sends — read the recipients and their
subscriptions up front, commit/close, send without a session, then record delivery in a
short second transaction — and bound concurrent fan-outs (a semaphore) below the pool
size. Catch failures for the whole background task, not only inside `_announce`.

## PERF-21 · MED · live · verified — the refresh job has no budget of its own

`run_refresh_slate` (`scheduler.py:546-608`) calls discovery with the narrowed pool but
no `request_budget`, so it costs 23 requests per distinct window per run, at 09:00 and
11:00 London. Measured: 23 at one window, 69 at three, **115 at five — 118 in each of
those two hours with browsing**, against 100/hour. Four windows is 92 before a single
card load. Discovery beside it is budgeted (Batch 133), which is what makes the
omission visible.

Tried to disprove: the count is the mock transport's own tally and equals
`OddsApiProvider.requests_made`; the refresh horizon is 1, so there is no smaller walk
to hope for; the hours are a setting (`ODDS_REFRESH_SLATE_HOURS`) but moving them moves
the spike rather than shrinking it. Rated MED rather than HIGH because production runs
one window today and the failure is a five-minute `429` cooldown rather than lost data —
but that cooldown holds the pick path too ("a 429 cooldown holds everybody",
`odds_cache.py:580`), and it lands in the 09:00 and 11:00 hours of a Saturday.

**Member impact:** with four or more league windows, a member trying to pick on a
Saturday morning can be refused a price for five minutes, twice.

**Fix:** give the refresh job the same `request_budget` discovery has (or a share of one
hour between them), and price the walk at the played intersection rather than the raw
pool (CORR-24).

## PERF-23 · MED · live · verified (hourly; daily by configuration) — one bucket for every league's picks

Batch 161 closed PERF-09 by charging a shared installation bucket beneath the per-league
one, and both are `50/hour;100/day` (`routers/picks.py:118`, `:138`). Measured with the
real limiter: however many leagues there are, **50 submissions an hour get through, in
total** (`pick-buckets.txt`). The bucket counts *submissions*, not provider requests —
by design it over-counts a re-pick — and a member changing their mind is a submission.

So the deployment, not the league, now has room for one full league per hour and 100
submissions per day. Two 25-member leagues whose members mostly pick in the hour before a
shared 14:30 lock reach the hourly ceiling; 50 members across any number of leagues each
picking once and changing once reach the daily one. The next member is refused with
`PICKS_BUSY`. The suite asserts
exactly this capacity (`test_the_installation_bucket_still_lets_a_full_league_take_its_picks`
checks one league) and nothing checks two. The measured Saturday at one window spends
289 of 500, so the day has room the bucket does not grant.

Not reachable today (one league of 13). Rated MED because it refuses genuine picks, with
a message, at a size the product is designed for.

**Member impact:** as the deployment grows past one busy league, members are refused
their pick at the deadline for a budget that is not actually spent.

**Fix:** charge the installation bucket only when the pick path actually goes upstream
(the cache knows whether the 60-second price was a hit), and size its day from what the
measured day leaves spare rather than a round 100.

## Deploy and rollback hygiene

The rollback target today is a plain redeploy of Railway `e77dde8f` (the `c671ccf9`
image), which STATUS records as booting against the current schema because the
27 Sep shipment applied no migration. That reasoning is sound and the recovery gate
confirms nothing is pending (`--deployed 026` → PASS), but **nothing asserts the
rollback target itself** — the gate checks that pending revisions have plans, not that a
named baseline image carries the deployed revision. It is recorded by hand in STATUS and
in each shipment's session-log entry. Given migrations are additive-only by convention
(`docs/runbooks/migrations.md`) that is acceptable; a one-line check that the baseline's
image reports the same `migration` would make it mechanical.

## OPS-19 · LOW · tooling · verified — the operator's CLIs run on an end-of-life Node

Batch 127 moved CI, the gate and the web build to Node 24, but `ship-prod.md` still puts
`~/.nvm/versions/node/v20.20.2` in front of the Vercel and Railway CLIs in nine places,
including both rollback commands (`ship-prod.md:337`, `:344`), and STATUS says "run it
with Node 20 first on PATH". Node 20 has been end-of-life since 30 April. Nothing member-
facing runs on it; the risk is that the one procedure used under pressure depends on a
runtime that no longer gets fixes and may be removed by the next `nvm` tidy.

**Fix:** re-test both CLIs on Node 24 and update `ship-prod.md` and STATUS together.

## PERF-22 · LOW · live · verified — a removed library is still installed

`apps/web/package.json:34` still declares `framer-motion ^11.3.2`. Nothing imports it
(`src/test/animations.test.ts` enforces that) and no emitted chunk contains it, so
members download none of it. What it still costs is an install, a lockfile entry that
dependency scanners will keep reporting, and a trap: the next agent that reaches for an
animation will find it "available". `package.json` is a protected file, so removing it
needs the owner to name the batch.

**Fix:** drop the dependency in the next batch that is allowed to touch
`apps/web/package.json`.

## PERF-18 · MED · live · verified — the slate queries per competition

The round screen's statement count is **10 + 2 × competitions on the card**: 56 at
production's 23 competitions, 66 at 28. `fixture_context` (`services/football_data.py:923-990`)
calls `resolve_names` once per competition (`:950`), and each call reads the alias table
and then the competition's teams (`services/team_matching.py:263`, `:284`). Its docstring
says "three queries for a slate of any size". The code is unchanged since Batch 16; the
2026-09-13 pass measured 12 because its round spanned one competition, so **its "no N+1
anywhere" was wrong for this screen** — the counts did not vary with the one factor that
drives them.

Bounded — at most the 41 played competitions, 92 statements — but these are serial round
trips on the most-used screen on a Saturday morning: at a 5-10 ms Railway→Supabase round
trip (not measured; production cannot be probed read-only) the 46 extra statements are
roughly 0.2-0.5 s per card load.

**Member impact:** the pick screen is slower than it needs to be, and slower the wider
the card.

**Fix:** resolve every competition's names in two queries (`IN` over competition ids),
as the docstring already claims.

## Checked and found nothing material

*pending*

## Proposed batches

*pending*

## Owner decisions

*pending*

## Doc corrections

*pending*

## What this pass did not do

*pending*
