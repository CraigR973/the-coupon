# The Coupon — session log

## Batch 1 — Application spine
**Commits:** `8513a02` · verified: Ruff · mypy · 76 pytest · migration + league flow

### Key facts for future sessions
- No local backend venv; use the sibling template venv with this repo's `PYTHONPATH`.
- Scratch database checks use pip `pgserver`.
- The baseline migration contains profiles, tokens, notifications, leagues,
  memberships, join requests, and invites.

**Next:** Batch 2 — Betfair adapter

## Batch 2 — Betfair adapter
**Commits:** `21078d6` · verified: Ruff · mypy · 98 pytest

### Key facts for future sessions
- Domain mapping lives on `BetfairAdapter`; live and canned implementations
  override only raw API primitives.
- `FakeBetfair.with_sample_data()` includes an English top-flight match, a
  Scottish fourth-tier match, a non-15:00 decoy, and one unpriced selection.
- Never use the owner's live account in agent verification.

**Next:** Batch 3 — Pick and scoring engine

## Batch 3 — Pick and scoring engine
**Commits:** `433f0ae` · verified: Ruff · mypy · 116 pytest · scratch migration + pick flow

### Key facts for future sessions
- Gameweeks and fixtures are global; picks are league-scoped.
- The submit endpoint reads odds server-side and snapshots the chosen price.
- HTTP pick-flow tests commit; reset the scratch schema before rerunning them.
- `alembic check` has known model/default drift; `upgrade head` is the gate.

**Next:** Batch 4 — Scheduler

## Batch 4 — Scheduler
**Commits:** `bc40245` · verified: Ruff · mypy · 149 pytest on scratch PostgreSQL

### Key facts for future sessions
- Jobs use Europe/London wall time and own their database transaction.
- The live adapter uses one shared login with keep-alive and transparent
  reauthentication; tests override the dependency with `FakeBetfair`.
- Lock and settlement jobs are also callable from the external cron entrypoint.

**Next:** Batch 5 — Frontend reshape

## Batch 5 — Frontend reshape
**Commits:** `25133f0` · verified: build · TypeScript · 169 Vitest

### Key facts for future sessions
- Pick, combined-coupon, and standings screens use the snake_case API directly.
- Query keys are centralised in `usePickEditor`; standings use
  `['standings', slug]`.
- The top-level coupon is a single-leaderboard MVP; per-league coupon routing is
  later product work.

**Next:** Batch 6 — Verify + rebrand pass

## Batch 6 — Verify + rebrand pass
**Commits:** `72945c0` · verified: 149 pytest + Ruff/mypy · scratch migration · build/TypeScript + 168 Vitest · mocked browser E2E · grep clean

### Key facts for future sessions
- Browser verification uses `tests.e2e_server:app`, disposable PostgreSQL, and
  `FakeBetfair`; production never imports the test control endpoints.
- The MVP default league slug is `the-coupon`; browser storage and cache keys
  use the `coupon_*` namespace.
- Display-name + PIN auth and invite claiming now use only the live snake_case
  API surface.
- Inherited product documentation, assets, routes, scripts, and the temporary
  handoff document were removed.
- The owner's live Betfair account remains outside agent automation.

**Next:** Launch planning (all build batches closed)

## Batch 7 — Odds provider replacement
**Commits:** `c17e996` · verified: 294 pytest + Ruff/mypy · clean scratch migration through `005` · Node build/TypeScript/ESLint + 160 Vitest · production-bundle browser flow · live provider coverage probe

### Key facts for future sessions
- Settlement reads `GET /v3/events/{id}`, never the odds endpoints: once a
  fixture settles `/odds` keeps `status` but drops `scores`, and `/odds/multi`
  omits it entirely. There is no batch form — `/events` ignores an `eventIds`
  filter — so it is one request per unresolved fixture.
- Status is the settlement gate, not the presence of a score. A `pending`
  fixture reports `scores: {0, 0}` and a `live` one reports the score so far;
  the vocabulary is `pending` → `live` → `settled`, plus `cancelled`. Fixtures
  settle from ~2h after kick-off, so the 18:00 Saturday job has ample margin.
- Leagues carry no `country` field — the country is only in the name — and
  England's lower tiers sit under `England Amateur - …`. Matching must strip
  that qualifier and stay exact afterwards, because `Ukraine` begins with `uk`.
- Event `id` is a JSON number and `league` a nested `{name, slug}` object;
  `coerce_numbers_to_str` is what keeps the slate from coming back empty.
- No provider identifier reaches the database. `(fixture, market, outcome)` is
  both the league's uniqueness key and what settlement resolves against, so
  `005` dropped the Betfair market/selection columns rather than renaming them.
- `fetch_odds` runs in the request path against 100/hour and 500/day. The
  launch Saturday's 131 fixtures batch ten at a time into 14 calls, so
  `ODDS_CACHE_TTL_SECONDS` defaults to 900; the daily cap binds first under
  sustained match-day refreshing.
- Errors must never carry the request URL — the API key travels in the query
  string, so `raise_for_status()` would print it into platform logs.

**Next:** Launch L5 — the odds-api.io key must be sealed into production
(`ODDS_API_KEY`) and staging's `BF_FAKE_MODE` migrated to `ODDS_PROVIDER=fake`
before the first-Saturday watch.

## Batch 8 — League-aware coupon
**Commits:** `6d6451e`, `990b6f8` · verified: 286 pytest + Ruff/mypy · Node build/TypeScript/ESLint + 163 Vitest

### Key facts for future sessions
- `DashboardPage`, `CouponPickPage`, and `CouponCombinedPage` have no `:slug`
  route param — they previously hardcoded `DEFAULT_LEAGUE_SLUG` because
  there was nowhere else to read a league from.
- `LeagueContext` now derives `activeSlug`: the last-viewed league from
  `leagueRecency.ts`'s localStorage key if the member still belongs to it,
  else their first league from `/leagues/mine`, else `DEFAULT_LEAGUE_SLUG`
  while that query is still loading/empty.
- `/batch-start` was changed this session to implement and verify a batch
  inline rather than stopping after branch creation; that workflow doc
  change rode along on this branch as its own commit (`6d6451e`).

**Next:** Batch 9 — Coupon presentation
