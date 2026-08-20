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

## Batch 9 — Coupon presentation
**Commits:** `3c3f5b5` · verified: 289 pytest + Ruff/mypy · 301 pytest on clean `pgserver` through `007` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- `latest_gameweek` takes the maximum `saturday_date`, and two edge-case tests
  in `test_picks_flow.py` commit gameweeks dated *after* `SAMPLE_SATURDAY`. Any
  test that reads the slate endpoint must out-date every other gameweek in the
  shared committed database or it silently asserts against another test's
  gameweek; `_open_sample_gameweek_as_latest` claims a distinct far-future
  Saturday per call. This trap is waiting for Batch 12.
- The browser flow needs `FRONTEND_ORIGIN=http://127.0.0.1:4173`. CORS allows
  exactly one origin and Playwright serves the preview there, so without it
  every login fails silently and the spec only reports "still on /login".
- `odds_format` is display only. `toFractional` snaps to the traditional UK
  ladder rather than converting arithmetically, because the exact fraction of
  1.91 is 91/100 where every real coupon says 10/11.
- `useOptionalAuth` exists so `useOddsFormat` degrades to decimal outside an
  AuthProvider. `CombinedAccaView` and `usePickEditor` are tested without one,
  and how a price is spelled is not worth coupling them to auth.
- The roster discloses nothing new before lock: the slate already labels each
  taken selection with its holder. What it adds is the members who have picked
  *nothing*, who by definition appear nowhere in the slate.
- Fixture-level `taken_by_names` is a list because the selection-level rule
  lets several members hold one game. Batch 10 makes it at most one.

**Next:** Batch 10 — One pick per fixture

## Batch 10 — One pick per fixture
**Commits:** `329daa6` · verified: 289 pytest + Ruff/mypy · 307 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- The rule is per-league but uniqueness is a database constraint, and a
  PostgreSQL index predicate cannot join to another table. So `pick_scope` is
  **denormalised onto `picks`** at write time and the fixture key is a partial
  unique index `WHERE pick_scope = 'fixture'`. `picks.pick_scope` is never the
  league's current setting — only the index reads it.
- `uq_picks_league_gameweek_selection` was **kept**, not replaced as the batch
  row said. Fixture uniqueness implies selection uniqueness, so it is true in
  both modes, and it is the only backstop selection-rule leagues have.
- The slate had to change with it: under `fixture`, every selection on a claimed
  game reports that holder, or the coupon offers selections the submit endpoint
  must refuse. Any future read of the slate has to keep honouring the scope.
- Changing a league's scope is a data migration in miniature. Tightening is
  refused with `PICK_SCOPE_CONFLICT` if two members already share a game;
  succeeding restamps **pending** picks only, because a settled gameweek was
  played under the rule then in force.
- Default is `selection` everywhere — column, API, and league creation — so
  nothing changes for an existing league until an admin opts in.
- The pick pool shrinks roughly fivefold under the fixture rule (three
  match-odds outcomes plus two BTTS collapse to one claim). A 15-member league
  needs 15 fixtures, not three. The launch Saturday carries 131.

**Next:** Batch 11 — Daily slate pre-fetch

## Batch 11 — Daily slate pre-fetch
**Commits:** `5b77972` · verified: 314 pytest + Ruff/mypy · 334 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- **The daily cap binds, not the hourly one.** 500/day minus ~60 for discovery
  leaves 440 for odds — 31 sweeps of the 131-fixture card at 14 requests each.
  The first tier values written for this batch failed that (704/day) and were
  recomputed backwards from the limit. Any future work that adds request-path
  provider calls must re-run `tests/test_request_budget.py`.
- `fetch_odds(..., max_age_seconds=)` **tightens but never loosens** the TTL.
  Browsing passes the lock-aware tier; the submit path passes 60s for the single
  fixture being picked. That asymmetry — 14 requests to browse the card versus 1
  to freeze a price — is the whole design.
- Consequence for the UI: a browsed price can be up to 30 minutes old near lock,
  so the odds a member taps may differ slightly from the odds they are scored on.
  The submit response carries the actual frozen price.
- Discovery does **not** fetch odds, deliberately. A price only means anything at
  the instant it is frozen, so pre-fetching prices would spend the budget on
  numbers nobody is scored on.
- `refresh_slate` is no longer the midweek job — it is the Saturday late pass.
  `discover_fixtures` covers midweek. Both are idempotent on `(gameweek,
  provider_event_id)`.
- Three places must stay in step when a job is added: `create_scheduler`,
  `run_scheduled.JOBS`, and their two guard tests in `test_scheduler.py` /
  `test_run_scheduled.py`, which assert the exact job set and cron strings.

**Next:** Batch 12 — Gameweek history

## Batch 12 — Gameweek history
**Commits:** `1be9f0d` · verified: 314 pytest + Ruff/mypy · 337 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 182 Vitest · production-bundle browser flow

### Key facts for future sessions
- `resolve_gameweek(db, gameweek_id)` is the single entry point for "which
  gameweek is this read about". The slate and coupon both go through it, so
  anything added later that reads a gameweek should too, or the two surfaces
  will disagree about what "current" means.
- React Query keys are `['gameweek', slug, gameweekId]` and
  `['coupon', slug, gameweekId]`, with `undefined` meaning latest. Invalidation
  after a grab is **prefix-matched** on `['gameweek', slug]` so every viewed
  week refreshes, plus `['gameweeks', slug]` for the season list's pick counts.
- Selection lives in the `?gw=` search param, not component state. That is what
  makes a past week linkable and back-button-navigable, and it means the default
  URL stays clean and the default query key stays stable.
- A `gameweek_id` that is not a UUID is a **404, not a 500** — the value comes
  straight off the query string, and an impossible id is a miss like any other.
- `test_picks_flow.py`'s `_open_sample_gameweek_as_latest` (added Batch 9) is
  what makes these tests possible: each call claims a distinct far-future
  Saturday, so a test can create two gameweeks and know which one is newest.
- The season list is unpaged on purpose — about forty rows a season.

**Next:** Batch 13 — Profile

## Batch 13 — Profile
**Commits:** `096818f` · verified: 314 pytest + Ruff/mypy · 340 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 186 Vitest · production-bundle browser flow

### Key facts for future sessions
- The profile is **per-league**, and that was the open decision in the batch row.
  Picks are league-scoped, and since Batch 10 the claim rule is too, so a career
  total would sum leagues playing different games. Route is
  `/leagues/:slug/players/:playerId`.
- Season figures come from `standings()` rather than a second query, so the
  profile and the leaderboard cannot drift apart. Anything added to one should
  be added there, not recomputed.
- `win_rate_pct` is `null`, not `0`, before anything settles — an untested
  record is not a bad one. The page renders "—" and says why.
- History excludes `pending` picks on purpose: an unsettled pick is already on
  the coupon, and repeating it here would be a worse copy of that view.
- Only ~130 of the source page's 774 lines were applicable. The World Cup
  predictor's exact-score rate, streaks, submit timing, and group/knockout
  sections have no counterpart in an accumulator game. Avatar **upload** was not
  ported — Launch L1 removed it deliberately.
- Reading a profile requires membership of the league it is read through
  (`LeagueMemberDep`), and a player not in that league is a 404, not an empty
  record.

**Next:** Batch 14 — Per-league gameweeks (the architectural pair with Batch 15)

## Toolchain trap found closing Batch 13
**Commit:** `48a7a58`

CI pins `ruff==0.5.4` (`apps/api/requirements-dev.txt`, `pyproject.toml`) but the
local toolchain `/batch-verify` mandates — app-starter's venv — ships **0.16.0**.
They format `assert X, (msg)` differently, so a locally-clean file can fail CI.

It went unnoticed for three batches because `ruff format --check` is the **first**
backend step: it failed the job before `mypy`, `alembic upgrade head`, and
`pytest` ever ran, so Batches 11-13 merged onto a red main and the DB-backed
suite was never actually exercised remotely. It has been since — 340 passed in CI
on `48a7a58`, migration `008` applied.

Check formatting with the pinned version, not the venv:

    cd apps/api && uvx ruff@0.5.4 format --check . && uvx ruff@0.5.4 check .

A green local gate is not evidence of a green CI until this is reconciled.

## Batch 14 — Per-league gameweeks
**Commits:** `3d95e5e` · verified: 331 pytest + Ruff/mypy · 365 pytest on clean `pgserver` through `009` · pre-009 backfill + downgrade round-trip · Node build/TypeScript/ESLint + 186 Vitest · production-bundle browser flow

### Key facts for future sessions
- **`saturday_date` is now `starts_on`, and it is not necessarily a Saturday.**
  `gameweeks` is unique on `(league_id, starts_on)`; `fixtures` is a pool unique
  on `provider_event_id`; `gameweek_fixtures` says which pooled fixtures a round
  plays. A fixture no longer names its round.
- `SlateWindow` (in `odds_provider.py`, so the port stays ORM-free) replaced
  `SATURDAY`/`KICKOFF_HOUR`/`_LOCK_HOUR`/`_LOCK_MINUTE`/`_SATURDAY`. It is a
  **range**, and today's rule is the degenerate case where start equals end.
  `query_bounds` is deliberately wider than `contains` — providers filter by
  range, so a point window still has to be asked for as a whole day.
- **Discovery groups by window, not by league.** That is the only reason
  per-league windows do not multiply the provider bill. Anything that adds a
  provider call per league will break the 500/day budget; there is a test.
- `POST /picks` resolves the round from **league + fixture**, preferring a
  still-open one. If Batch 15 lets windows overlap more, an explicit
  `gameweek_id` on submit may become the better API.
- A clean-DB `alembic upgrade head` proves nothing about a data migration.
  `tests/test_migration_009.py` builds its **own** database, migrates to `008`,
  writes pre-split shapes, then upgrades — and that is what caught 009 dropping
  the old global unique key *after* the clones that violate it.
- The scheduler crons no longer filter on a weekday. A Saturday-only
  `lock_gameweeks` would never lock a Friday league's round.
- Deleted `_open_sample_gameweek_as_latest` (Batch 9) — it only existed because
  `saturday_date` was globally unique.

**Next:** Batch 15 — League admin configuration (builds directly on this migration)

## Batch 15 — League admin configuration
**Commits:** `4cb6267` · verified: 331 pytest + Ruff/mypy · 378 pytest on clean `pgserver` through `010` · 010 up/down round-trip + defaults + non-empty check · Node build/TypeScript/ESLint + 192 Vitest · browser e2e is owner-run (`ODDS_PROVIDER=fake`)

### Key facts for future sessions
- **Competition selection is a link-time filter in `sync_slate`, never a provider-query
  change.** `leagues.competitions` is JSONB: `NULL` = all UK, a `[{slug,name}]` list narrows
  which pooled fixtures a round links. The per-window fetch is still all-UK, so the request
  budget and the "discovery groups by window" tests are untouched. `sync_slate` now returns
  `Gameweek | None` (no empty round for an excluded window) and still never unlinks.
- **`offered_markets` is `pick_market[]` — an array of the *existing* enum, not new values.**
  Widening the markets themselves is still a migration. Enforced twice: the slate read
  (`_selection_options`) hides them, and submit rejects with `MARKET_NOT_OFFERED`.
- **`PickMarket` now lives in `models/league.py`** (re-exported from `pick.py`, so
  `from src.models.pick import PickMarket` still works). It moved to let `League.offered_markets`
  type against it without a league↔pick import cycle.
- **The competition catalogue (`GET /{slug}/competitions`) is `SELECT DISTINCT competition_id,
  competition FROM fixtures`** — zero provider cost, but empty until discovery has pooled
  fixtures (production had none at close-out; the default all-UK works without it).
- **Ad-hoc round `POST /{slug}/gameweeks` walks the provider in the request path** (~one
  `/events` per UK competition), so it is rate-limited to 6/hour. A past date gives an
  already-locked (unpickable) round; a date with no qualifying fixtures is `422 NO_FIXTURES`.
- **`competitions` on PATCH uses `model_fields_set`** to separate "omitted (unchanged)" from
  "explicit `null` (all UK)"; every other field keeps the null-means-unchanged convention.

**Next:** Batch 16 — Football data (real tables/results/form; needs a second provider). Launch
L5 — launch and first-Saturday watch runs in parallel.

## Batch 16 — Football data
**Commits:** `10f11f4` · verified: 375 pytest + Ruff 0.5.4 check/format + strict mypy · 453 pytest on clean `pgserver` through `011` · Node build/TypeScript/ESLint (0 errors) + 217 Vitest · browser flow driven locally against `tests/e2e_server` (`ODDS_PROVIDER=fake`, canned football), mobile + desktop, light + dark

### Key facts for future sessions
- **The 100-requests-a-*day* free plan is the whole design, not a caveat.** Nothing may
  reach a football provider from the request path — ingestion writes `teams`/`matches`/
  `standings` on the 06:30 job and every screen reads those. `tests/test_football_router.py`
  booby-traps `football_session.acquire` and asserts both endpoints still answer, so a
  future provider call in a read path fails loudly.
- **A competition costs exactly two requests** (`/standings` + `/fixtures`), so 30 UK
  competitions is 61 with the memoised catalogue. `FOOTBALL_COMPETITIONS_PER_RUN` caps a
  run and `pooled_competitions` orders least-recently-synced first; the season backfill is
  a deliberate one-off (`python -m src.run_scheduled football-backfill`), never scheduled.
- **`standings.updated_at` is stamped by hand in `sync_table`.** `UpdatedAtMixin` has no
  `onupdate` and there is no trigger, so it froze at insert — which broke the "as of" line
  *and* froze the rotation ordering, starving every competition past the cap after the
  first pass. A server default is no use either: `NOW()` is the transaction's start time,
  so one run's competitions would share an indistinguishable timestamp.
- **Aliases are learned at ingestion, not read time**, which is what makes the pick screen's
  inline form a primary-key lookup. `resolve_names` refuses ambiguous names outright — two
  clubs equally close resolve to nothing, because no form line beats the wrong club's.
- **`FOOTBALL_DATA_PROVIDER` defaults to `none`** so sealed production is untouched; `none`
  disables *ingestion* only and the screens still read what is stored. The canned data is
  season 2025 while the canned slate is 2026-27, so anything using `FakeFootballData` must
  pin `FOOTBALL_SEASON=2025` (`tests/e2e_server.py` sets it directly).
- **`apps/web/.env.local` on this machine points at a dead wc2026 Railway URL**, so the web
  dev server never reaches a local API until it is repointed. It is gitignored, so this is a
  machine artifact rather than a repo bug — but it silently renders every screen empty.

**Next:** Batch 17 — Betslip export spike (timeboxed, ends in an ADR). Launch L5 — launch and
first-Saturday watch runs in parallel.

## Batch 17 — Betslip export spike
**Commits:** `12ffcb4` · verified: 375 pytest + Ruff 0.5.4 check/format + strict mypy · Node build/TypeScript/ESLint (0 errors) + 217 Vitest · no DB or browser gate — the batch ships no code, so neither is in scope

### Key facts for future sessions
- **The decision is not to build betslip export**, and the ADR is the whole batch —
  `docs/adr/0004-betslip-export.md`. Two walls, either sufficient alone: nothing we can
  generate composes an accumulator, and `odds_at_pick` is frozen, so any exported acca
  prices live at the book and disagrees with the coupon's headline number every week.
- **Bet Share and the affiliate link split the two capabilities and never combine them.**
  Bet Share carries a full acca but is minted inside an authenticated Bet365 session, from
  a bet the customer already holds — only they can create it. The affiliate
  add-to-betslip link is one we *could* create, with a Bet365 Partners account, and carries
  exactly one selection. Booking codes elsewhere (Betway Book-a-Bet, Betano) are the same
  shape: customer-minted, multi-leg. That is why the only low-friction design is a captain
  relaying their own link, not us generating one.
- **odds-api.io already returns bookmaker links and we discard them.** `/odds` carries an
  event-level `urls` map (`{"Bet365": ...}`) plus `homeLink`/`drawLink`/`awayLink` per
  entry. `OAEventOdds` doesn't declare `urls` so pydantic drops it, and `_selections_for`
  (`services/odds_api.py:494`) reads only the price keys, so the links sit unread in dicts
  we already hold. Surfacing one costs zero extra requests — cost was never the obstacle.
  There is no `yesLink`/`noLink`, so BTTS is unlinkable regardless.
- **Logging into a member's Bet365 from the app was considered and rejected.** PINs are
  bcrypt-hashed and unrecoverable; replaying a bookmaker login needs a *reversible* secret,
  which this app has never held, guarded by a 4-digit PIN. Bet365's terms also prohibit
  automated access, and the realistic outcome is a member's account suspended with funds
  frozen. Not in the ADR — worth adding if it is asked again.
- **An outbound bet link changes the product's regulatory category.** There is no age gate,
  no date of birth, and no responsible-gambling copy anywhere in `apps/web/src` or
  `apps/api/src`, which is fine for a points game and not fine for a surface that routes
  people to a bookmaker. Age-gating is the precondition for any bookmaker link, not a
  follow-up to it.
- **The odds-api.io Zscaler block is gone** (rechecked 2026-08-06: `api`, `api2` and `docs`
  all answer from their real origins). Live probes are still owner-run, but because no
  `ODDS_API_KEY` exists on this machine — a credentials problem a key would fix, not a
  network one needing a different connection.

**Next:** the build plan is complete — Batches 1–17 all struck. Launch L5 — launch and
first-Saturday watch is the only open phase, and production is still not playable: it runs
the pre-Batch-7 build with no `ODDS_API_KEY` sealed.

## Batch 18 — Production static assets
**Commits:** `e28155c` · verified: lint · typecheck · build (precache manifest checked) · 217 Vitest

### Key facts for future sessions
- `vercel.json`'s SPA-fallback rewrite excluded `icons/`, a directory that never existed;
  the eleven root-level static files (`fonts/*.woff2`, five `icon-*.png` in the manifest,
  `apple-touch-icon.png`, `coupon-icon.svg`) all fell through to `index.html` in
  production and were precached as HTML by the service worker, breaking fonts and the
  installed-app icon.
- Fix is `fonts/|icon-|apple-touch-icon\.png|coupon-icon\.svg` added to the negative
  lookahead — verified with a regex simulation against all eleven paths plus the existing
  SPA and static-passthrough cases, not by deploying.

**Next:** Batch 19 — Coupon page crash.

## Batch 19 — Coupon page crash
**Commits:** `6c71163` · verified: lint · typecheck · build · 234 Vitest

### Key facts for future sessions
- The "Something went wrong" report was a stale route chunk, not coupon code: every route
  is `lazy()`, a deploy drops the previous build's chunk hashes, and `sw.ts`'s
  `skipWaiting()`/`clientsClaim()` hands an open tab to the new worker while it still runs
  old JS — so the *first* route change after a deploy 404s.
- Reproduced against a real production bundle (`vite build` → `vite preview`) by deleting
  a built chunk after load and navigating to it — see `docs/adr/0005-stale-chunk-recovery.md`.
- Fix is `lib/lazyRoute.ts`: wraps `React.lazy`, matches the rejected-import wording across
  Chrome/Firefox/Safari/Vite, reloads once (skipped offline or within a 30s cooldown), and
  lets `ErrorBoundary` show a "Coupon has been updated" message with only Reload — not "Try
  again", since React caches a rejected `lazy` payload permanently.
- Applies to all eighteen routes and `Layout`, not just the coupon pages — the coupon was
  simply the first tap after a deploy, not a special case.

**Next:** Batch 20 — League identity, profile and invite wayfinding.

## Batch 20 — League identity, profile and invite wayfinding
**Commits:** `a784ca6` · verified: Ruff 0.5.4 check/format · strict mypy · 375 pytest · lint · typecheck · build · 234 Vitest

### Key facts for future sessions
- Three built-but-unreachable surfaces, no API change: `DashboardPage` never named the
  active league (fixed via the `PageHeader` eyebrow, which covers all three home cards, not
  just one); there was no self-profile route (added "My profile" to both `TopBar`'s avatar
  menu and `TabBar`'s mobile More sheet, pointing at `/leagues/${activeSlug}/players/${player.id}`);
  and `LeagueJoinRequestsPage`/`LeagueAdminInvitesPage` were routed but linked from nowhere
  (added admin-only buttons to `LeagueActionsMenu`, behind its existing `isAdmin` guard).
- `SettingsPage` already linked to `/about`, which had no route — the catch-all silently
  bounced it home. Added `AboutPage.tsx` reusing the existing scoring-rules copy from
  `OddsGuide.tsx` rather than writing new copy.
- `TopBar`/`TabBar` now call `useLeague()`, so any test rendering them needs a
  `LeagueProvider` (or a `@/contexts/LeagueContext` mock) in the tree — updated
  `TopBar.test.tsx`, `TabBar.test.tsx`, and `accessibility.test.tsx` accordingly.

**Next:** Batch 21 — Competition catalogue from the provider.

## Batch 21 — Competition catalogue from the provider
**Commits:** `74378f8` · verified: Ruff 0.5.4 check/format · strict mypy · 382 pytest (461 on clean `pgserver` through `011`) · lint · typecheck · build · 235 Vitest · browser picker against `tests/e2e_server`

### Key facts for future sessions
- `fetch_competitions()` is an `@abstractmethod` on `OddsProvider`, chosen over a
  non-abstract default returning `[]`: a default would have left `FakeBetfair` — which
  backs every test, staging, and the browser flow — showing exactly the empty picker the
  batch existed to fix. The cost is four implementations, all a few lines.
- **Do not name a port method `list_competitions`** — `BetfairAdapter` already has one as
  a raw primitive with a different signature, so the port method is `fetch_competitions`.
- `OddsApiProvider._uk_leagues()` is now shared by `fetch_slate` and `fetch_competitions`,
  so the picker cannot offer a competition the slate ignores or hide one it takes.
  `_all_leagues()`'s per-client memo is what keeps the endpoint free of an upstream
  request; `CachingOddsProvider` therefore delegates it *uncached* on purpose.
- The endpoint keeps the old `SELECT DISTINCT … FROM fixtures` query as an
  `OddsProviderError` fallback. The picker is also how an admin *un*-narrows a league, so
  a 503 would leave them unable to change a selection they can no longer see.
- `fixtures` is a pool shared by every league, so "this league has pooled nothing" is not
  assertable in the committed test database. The discriminator is the canned
  `Spanish La Liga` (`99999`): `fetch_slate` drops it on the country rule, so no round can
  ever pool it and its presence proves the catalogue came from the provider.
- **`apps/web/.env.local` points the dev server at the production Railway API.** Any local
  browser check must override it (a `.env.development.local` wins and is gitignored) or it
  silently drives production.

**Next:** no build batches remain open; Launch L5 — launch and first-Saturday watch.

## Batch 28 — Football ingestion rate limiting
**Commits:** `d77062a` · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- API-Football's free plan has two limits, not one: 100/day and 10/minute. ADR 0003 now
  records both because missing the minute cap is what made production ingestion write
  nothing.
- The minute throttle arrives as HTTP 200 with `errors.rateLimit`, so the adapter now
  treats that body key as transient and retries through the existing backoff path.
- Scheduled `sync_football_data` spaces competition attempts by
  `FOOTBALL_COMPETITION_SPACING_SECONDS` (default 12.0), sleeping only between attempts
  and injectable in tests.
- A 30-competition sweep is now expected to take about six minutes, which is fine for the
  06:30 scheduler job and is why this belongs off the request path.

**Next:** Batch 22 — Wayfinding and layout.

## Batch 22 — Wayfinding and layout
**Commits:** `ee888f7` · verified: Ruff 0.5.4 check/format · strict mypy · 387 pytest · lint · typecheck · build · 240 Vitest

### Key facts for future sessions
- Football is now top-level wayfinding on both desktop `TopBar` and mobile `TabBar`,
  while `CouponSubNav` still keeps it beside the pick and combined-coupon surfaces.
- The Coupon nav item excludes `/predictions/football`, and both navs set current state
  explicitly so Football does not double-highlight Coupon for sighted users or screen readers.
- `PageHeader`'s action wrapper changed from `shrink-0` to a shrinkable max-width wrapper;
  `LeagueActionsMenu` keeps its own `flex-wrap`, so future phone overflow fixes should avoid
  reintroducing a non-shrinking parent.
- Members administration is now behind the existing `isAdmin` prop; regular members should
  use the leaderboard as the member list.
- Combined coupon rows and profile history rows now render the `competition` field that the
  API already supplied on `CouponLeg` and `SettledPick`.
- The close-out gate exposed an ASCII-locale health bug: `apps/api/alembic.ini` had a
  non-ASCII comment, so Alembic config parsing failed and `/health` reported
  `migration: unknown`; the file is ASCII now and reports `011`.

**Next:** Batch 23 — Slate ordering and collapse.

## Batch 23 — Slate ordering and collapse
**Commits:** `f5496e1` · verified: Ruff 0.5.4 check/format · strict mypy · 387 pytest · clean pgserver migration + DB slate test · lint · typecheck · build · 241 Vitest · production-preview Playwright coupon flow

### Key facts for future sessions
- `FixtureSlate` now exposes `competition_id`; the picker groups and sorts on that stable provider slug, not sponsor-prone display names.
- Competition groups are closed by default so a large slate scans as league headers first.
- The picker order is England top four, Scotland top four, remaining England/Scotland tiers, then everything else by fixture count.
- `GameweekMember` now carries `competition`, and the roster renders it beside the picked market.
- The browser flow opens competition sections explicitly and stores Batch 23 screenshots in `artifacts/batch-23/`.

**Next:** Batch 24 — Share the coupon as text.

## Batch 24 — Share the coupon as text
**Commits:** `b3139d3` · verified: lint · typecheck · build · 243 Vitest (incl. new clipboard/copy coverage)

### Key facts for future sessions
- `CombinedAccaView.tsx` exports `buildCouponShareText(coupon)`, a pure function rendering legs,
  selections, prices and combined odds as plain text with a note that prices were frozen at pick
  time — no bookmaker link, satisfying ADR 0004's second wall.
- The "Copy text" button uses `navigator.clipboard.writeText` and toasts success/failure; no new
  API surface, since `GET /leagues/{slug}/coupon` already carries every field used.
- Frontend-only batch; backend, migrations and Ruff/mypy/pytest gates were untouched and not rerun.

**Next:** Batch 25 — Gameweek results.

## Batch 25 — Gameweek results
**Commits:** `51d0258` · verified: Ruff 0.5.4 check/format · strict mypy · clean pgserver migration + 388 pytest (incl. new DB-backed results test) · lint · typecheck · build · Vitest (incl. new ResultsPage suite)

### Key facts for future sessions
- New `GET /leagues/{slug}/results` (`src/routers/coupon.py`) backed by `scoring.gameweek_results()`:
  one query over every settled round, winner(s) by top `points_awarded` (ties named together),
  `all_won`/`combined_odds` computed the same way `coupon.build_coupon` does.
- A settled round with zero picks in a league still gets a row (`winner_names: []`,
  `all_won: null`) rather than being silently dropped — the outer-join keeps it visible.
- Frontend: new `/predictions/results` (`ResultsPage.tsx`) added to `CouponSubNav`; each row
  navigates to `/predictions/coupon?gw=<id>`, which `useGameweekHistory`'s `gw` query param
  already resolves to that round.
- `PlayerProfilePage` now links to Results ("How each week went") — profile still answers
  per-pick, results answers per-week; neither replaces the other.
- No browser/Playwright check this batch — a local `pnpm dev` server points at the production
  Railway API by default (`apps/web/.env.local`), so verification relied on the DB-backed
  pytest test and the Vitest suite instead of a live preview.

**Next:** Batch 26 — Multi-league home and profile.

## Batch 26 — Multi-league home and profile
**Commits:** `780f70e` · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver migration + 473 pytest (incl. 5 new DB-backed cross-league tests) · lint · typecheck · build · Vitest 265 (incl. new DashboardPage + CareerProfilePage suites) · prod-bundle Playwright smoke · extended production-preview coupon-flow e2e with screenshots in `artifacts/batch-26/`

### Key facts for future sessions
- New `GET /api/v1/me/cross-league-summary` (`src/routers/me.py`): five fixed queries whatever the
  league count. `per_league` carries slug/name/rank/member_count/points **and** `current_round`
  (status, `locks_at_utc`, `leg_count`, `combined_odds`, `my_pick`), so home is one request rather
  than three per league.
- `scoring.standings_by_league(db, league_ids)` is the new primitive — one grouped query for a set
  of leagues — and `standings(db, league_id)` is now a one-id wrapper over it. Any future
  multi-league read should use it rather than looping `standings`.
- Aggregation rule, encoded in the response: points/win rate sum across leagues (same
  `round(odds × 10)` scale); rank does not. `_MIN_MEMBERS_FOR_AVG = 3` excludes leagues too small
  to rank against from `avg_rank`, and `avg_rank_leagues` reports how many it actually spanned.
- `LeagueContext` gained `selectLeague(slug)`. `activeSlug` is *derived*, so writing the recency
  store alone does not re-render — a screen that opens a league other than the bound one must call
  this, not `setLastViewedLeague`.
- My profile is now `/profile` (career-scoped) in **both** `TabBar` and `TopBar`'s avatar menu;
  `/leagues/:slug/players/:playerId` is unchanged and still reached from that league's leaderboard
  and from the career breakdown.
- Browser verification is viable again despite `.env.local` pointing at production: build with
  `VITE_API_URL=http://127.0.0.1:8000` against `uvicorn tests.e2e_server:app` on a scratch
  pgserver, then run `playwright.config.ts` (the `coupon-flow` project seeds/locks/settles itself).

**Next:** Batch 27 — Configurable pick-open time.

## Batch 27 — Configurable pick-open time
**Commits:** `007ec97` · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver `alembic upgrade head` (001→012) + pytest · deployment-config assertions · lint · typecheck · build · Vitest 273 · prod-bundle Playwright smoke. Separately: the DB-backed Batch 27 set on its own clean pgserver, 63 passed / 0 skipped.

### Key facts for future sessions
- Three instants now, and the names matter: `SlateWindow.opens_at` is when the *fixture window*
  opens (the anchor), `locks_at_utc` is when claiming stops, `picks_open_at_utc` is when it
  starts. Both offsets are measured back from the anchor via `SlateWindow.utc_before_open`, so a
  **bigger** offset is **earlier** and `pick_open_offset_minutes >= lock_offset_minutes` is the
  validity rule (enforced in the API as 422 *and* by a DB check).
- `pick_refusal(gameweek, now)` in `services/gameweek.py` is the single gate — `is_open_for_picks`
  is now a thin wrapper. Time decides both ends; `status` only rules out rounds settlement has
  finished with. So a `scheduled` round past its instant is accepted *before* the hourly open job
  relabels it, exactly as an `open` round past its lock is refused before the lock job runs. Any
  new caller should use `pick_refusal`, not read `status == open`.
- `pick_open_offset_minutes` lives on `League`, deliberately **not** on `SlateWindow`:
  `discover_fixtures` groups leagues by window, so putting it there would multiply the provider
  bill by the number of distinct announcements. `test_the_pick_open_offset_is_not_part_of_the_window_identity`
  pins this — do not "tidy" it into the dataclass.
- `NULL` on both new columns is the pre-batch rule (claimable from discovery), so 012 needs no
  backfill. On PATCH, `pick_open_offset_minutes` is read from `model_fields_set` because null is
  meaningful ("stop announcing"), the same treatment `competitions` already gets.
- **jsdom form-submit trap, cost ~2h this batch.** `LeagueSettingsPage`'s name input is `required`
  and is filled by an effect *after* the query resolves. A test that waits only for a rendered
  element can click Save while it is still empty, and jsdom then refuses to dispatch `submit` at
  all — no handler, no toast, no PATCH, and a `waitFor` that can only time out (raising the
  timeout does not help). Await `findByDisplayValue('The Coupon')` before clicking Save. The
  Batch 15 test `widens the window and saves the new range` still has this latent.
- `slate_odds_max_age` gives every non-`open` state the loosest tier, so a `scheduled` round whose
  opening has passed shows browse prices up to `far_ttl` until the hourly job flips it. Display
  only and bounded by an hour — submits price independently via `odds_cache_pick_ttl_seconds`.

**Next:** all 28 build batches are struck. Launch phase L5 — Launch and first-Saturday watch.

## Batch 33 — Football ingestion shape tolerance
**Commits:** `df53b49` (scope) · `94715a9` (fix) · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver `alembic upgrade head` + pytest (incl. 4 new adapter tests) · deployment-config · lint · typecheck · build · Vitest 273 · prod-bundle Playwright smoke

### Key facts for future sessions
- **A pydantic default covers an *absent* key, not one present as `null`.** API-Football sends
  `"code": null` for the countryless competitions and `"form": null` until a team has played, and
  `str = ""` rejects both. `AFModel`'s before-validator drops nulls so null reads as absent for
  every raw payload model — patch new fields there, not one field at a time.
- The catalogue is the one parse **every** competition shares, so it is the only one that needs
  per-entry tolerance; `_all_leagues` now drops an unreadable row and memoises the survivors.
  Per-competition parses need none — `sync_football_data` already isolates a failure to its own
  competition.
- Raising before a memo is assigned is a quota bug, not just a correctness bug: it cost a fresh
  `/leagues` request per competition, 21 of 100 in one morning. Any future memo on this client
  must be assigned even on partial success.
- **Coverage is still unobserved.** Only the catalogue request has ever succeeded against the live
  API. The next run answers it: `api-football catalogue loaded leagues=N dropped=M`, then one
  `api-football competition unmatched` per division that fails to resolve. Read those before
  treating the Football tab as fixed.
- Ingestion cost ceiling, recorded not fixed: 1 catalogue + 2 requests per competition against
  100/day caps a day at ~49 distinct competitions, and `FOOTBALL_COMPETITIONS_PER_RUN` defaults to
  30. Past that the rotation still feeds everything but no table is fresher than ⌈union ÷ cap⌉
  days — the symptom of many leagues is **stale** tables, not missing ones.
- `LeagueSettingsPage.test.tsx`'s `loads a stored offset with the switch already on` is **flaky**
  and failed this batch's first gate run before passing twice: `findByRole` waits for the switch
  to exist, but it renders `aria-checked="false"` and only flips once the query resolves. Batch
  27's log predicted this class in this file. Wait on the settled value, not on presence.

**Next:** Batches 29-32 are open (start with 29 — League identity on the coupon tab). Batch 33 needs a `/ship-prod`; the Football tab stays dark until the API moves and `sync-football` runs.

## Batch 29 — League identity on the coupon tab
**Commits:** `57c8cb3` · verified: frontend gate — `pnpm lint` (0 errors, pre-existing warnings only) · `pnpm typecheck` clean · `pnpm build` succeeds · `pnpm test` 38 files / 285 tests pass (12 new/updated, covering league-name headers, the switch strip on multi-league members, and the no-league gate). Frontend-only batch; backend/DB checks out of scope.

### Key facts for future sessions
- `LeagueContext` now exposes `activeLeagueName` and `hasLeagues` alongside `activeSlug` —
  `hasLeagues` is `leagues.length > 0` and is the correct gate for any query that binds to
  `activeSlug`, since that falls back to `DEFAULT_LEAGUE_SLUG` while `leagues` is loading/empty.
- `LeagueSwitchStrip` now calls `selectLeague(currentSlug)` in its mount/update effect instead of
  writing the recency store directly. This closes the drift Batch 29 was scoped from: browsing
  `LeaderboardPage` (URL-driven slug) previously updated the store but not `activeSlug`, so a later
  tap on the Coupon tab (`activeSlug`-driven) could silently reopen the wrong league.
  `selectLeague` still writes the store itself, so no caller needs both.
- `useGameweekHistory(slug, enabled = true)` gained an `enabled` param so `CouponPickPage` and
  `CouponCombinedPage` can defer the `/gameweeks` fetch until `hasLeagues` is true, matching the
  gate now applied to every other coupon-surface query.
- The four `/predictions/*` pages share one "You're not in a league yet" empty state (title +
  "Find a league" link), copied from `DashboardPage`'s pattern rather than factored into a shared
  component — kept inline per-page since each needs a different early-return shape around its own
  header.
- Slug-addressed coupon routes (making the binding shareable/bookmarkable) are explicitly out of
  scope here — that is Batch 30, next.

**Next:** Batch 30 — Slug-addressed coupon routes.

## Batch 30 — Slug-addressed coupon routes
**Commits:** `f33674d` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 306 tests), Playwright prod-bundle deep-link smoke. Plus the full browser end-to-end (`coupon-flow`, production preview + scratch PostgreSQL + `FakeBetfair`) — 1 passed, screenshots in `artifacts/batch-30/`; and the reminder tests re-run explicitly against scratch Postgres (7 passed) because they skip without `DATABASE_URL`.

### Key facts for future sessions
- The coupon lives at `/leagues/:slug/predictions[/coupon|/results|/football]`. Build every link
  with `predictionsPath(slug, section)` from `lib/leagues.ts` — never a literal. It takes
  `string | null`, and `null` yields the slug-less path, which is the honest address while no
  league is bound (loading, or a member in none).
- **The URL binds the context, not the reverse.** `useRouteLeague()` returns `{slug, name}` and
  calls `selectLeague` on arrival; `activeSlug` is now only the default for an address naming no
  league. Batch 29's `LeagueSwitchStrip` effect was removed as part of this, so any *new* page
  under `/leagues/:slug/*` must call the hook or it will not bind — `LeaderboardPage` was switched
  to it for exactly that reason.
- Nav highlighting is deliberately slug-agnostic (`isCouponPath` / `isFootballPath` /
  `isLeagueHubPath`), against the BUILD_PLAN row's wording. Two reasons: a prefix built from the
  bound slug flickers off for a frame when tapping into another league, and `/leagues` would
  otherwise match the coupon and light the Leagues tab too.
- `MissingPickMember` carries `league_slug`, and the reminder sends
  `data.url = /leagues/{slug}/predictions` — the payload key `sw.ts` reads, which fell back to `/`
  before. Its body now formats `gameweek.locks_at_utc` in the member's timezone as `Sat 14:30`;
  anything re-hardcoding a lock time is wrong for a league not locking Saturday.
- The e2e harness needs `FRONTEND_ORIGIN=http://127.0.0.1:4173` (CORS allows exactly one origin)
  and one process must hold the `pgserver` handle for the whole run — the socket dies with the
  process that started it. A stale `uvicorn` on port 8000 will silently answer for a new one
  against a deleted database; check `lsof -ti tcp:8000` when the seed 500s.
- `docs/agent-commands/batch-verify.md` still names app-starter's venv for mypy/pytest. Use
  `scripts/ci-local.sh` instead, per the managed-venv rule — the doc is stale, not the rule.

**Next:** Batch 31 — Settlement cost per league.

## Batch 31 — Settlement cost per league
**Commits:** `2107dd9` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build, Playwright prod-bundle deep-link smoke. Run twice, before and after the commit.

### Key facts for future sessions
- **Settlement is now one provider read per run, not per round.**
  `settle_gameweeks_via_provider(db, provider, gameweeks)` de-duplicates every settleable
  round's outstanding fixtures, calls `provider.settle` once, and fans the settlements back
  out — `settle_gameweek` already ignores settlements its own picks don't reference. Anything
  that settles a round at a time re-introduces the per-league bill.
- `pending_event_ids` changed shape: it takes a *sequence* of rounds and returns
  `{gameweek_id: [event_id]}`. `settle_gameweek_via_provider` still exists as the plural over
  one round (`e2e_server.py` and the Batch 4 e2e slice use it), so there is one implementation.
- The dedupe works because a fixture is one pooled row since Batch 14 — two leagues holding the
  same match report the same `provider_event_id`. If fixtures ever stop being pooled, this
  collapses back to a per-league cost silently.
- **Step 2 of the row was not done and is not a defect.** Whether `/events` for a whole window
  carries `scores` for finished fixtures is unverified — it needs a live odds-api call and there
  is no key in the working tree. The open question is recorded on `OddsApiProvider._event_by_id`.
  Confirming it would turn a Saturday into one request per window instead of one per fixture.
- Running out of provider quota is **silent**: no error, picks just stay `pending` and the week
  never finishes. `_RecordingFake` in `test_scheduler_jobs.py` records what each `settle` call
  asked for, because that list is the bill — assert on it, not on wall-clock behaviour.
- `tests/test_football_router.py::test_an_anonymous_caller_is_refused` fails under app-starter's
  venv (401 vs the pinned FastAPI's 403). That is the documented pin divergence, not a
  regression — use `scripts/ci-local.sh`, which builds the pinned venv.

**Next:** Batch 32 — Per-league notification preferences.

## Batch 32 — Per-league notification preferences
**Commits:** `88d3a78` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build, Playwright prod-bundle deep-link smoke.

### Key facts for future sessions
- The mute flag lives on `league_memberships.notification_muted` (migration `013`), not a new
  table — that row already dies with the membership, so leaving and rejoining a league never
  inherits a stale mute.
- `members_missing_picks` filters muted memberships out at the query, so a muted league is never
  targeted rather than targeted and suppressed — `send_pick_reminders`' return count stays honest
  about who was actually nudged.
- `global_mute` and quiet hours are unchanged and still layered on top: the per-league flag
  decides whether a reminder is *wanted*; the user-level gate decides whether *now* is a good time.
- `GET`/`PATCH /api/v1/notifications/preferences` gained a `leagues: [{league_id, league_name,
  muted}]` list and a `PATCH` `league_mutes: {league_id: bool}` field — one settings read/write
  still serves the whole card. `PATCH` only touches memberships the caller actually belongs to.
- This closes the last open batch (1-33 are now all shipped on `main`); the only remaining build
  work is launch phase L5.

**Next:** Launch phase L5 — Launch and first-Saturday watch.

## Batch 34 — Switching league without leaving the coupon
**Commits:** `f97aa2b` (scoped in `6244575`) · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 314 tests), Playwright prod-bundle deep-link smoke. Run twice: after implementation and again against the exact tree committed. Frontend-only batch.

### Key facts for future sessions
- `leagueSwitchPath(slug, pathname)` in `lib/leagues.ts` is the whole rule: a league switch keeps
  the reader on the surface they are on. `LeagueSwitchStrip` derives it from `useLocation()` rather
  than taking it per call site, so a league-scoped surface added later is switchable without
  touching the component or its five mount points.
- **It takes a pathname and returns a path, and that is the `?gw=` guard** — structural, not
  remembered. A gameweek id is league-scoped and `resolve_gameweek` 404s on a foreign one, so
  "preserving state" across a switch would land on the empty state. Anyone widening the signature
  to a `Location` reopens the bug.
- Non-coupon surfaces fall back to the leaderboard deliberately, not lazily. A blanket slug-swap of
  the pathname is the tempting general form and is wrong: it carries a foreign player id into
  `/leagues/:slug/players/:id` and assumes admin of the target on `/admin/*`.
- The four `/admin/*` pages now call `useRouteLeague`, which pulls in `LeagueContext` — so their
  test harnesses need `LeagueProvider`. In `LeagueSettingsPage.test.tsx` the `/leagues/mine` matcher
  must sit **before** `/api/v1/leagues/[^/]+$`, which also matches it; serving a league *detail*
  where the context expects an array throws inside `activeSlug` on `leagues.some`, nowhere legible.
- Assert destination, not presence. `findByTestId('league-switch-strip')` was the only assertion
  either coupon test made, which is exactly how the leaderboard destination survived Batches 29 and
  30 — both aimed at this area.
- Two gaps left open on purpose: the leaderboard branch is covered in `leagues.test.ts` only (no
  `LeaderboardPage.test.tsx` exists and a harness for one href was disproportionate), and there is
  no browser check — it needs a two-league authenticated session, which `coupon-flow` does not seed
  and the prod-bundle smoke never reaches.

**Next:** Batch 35 — A one-off round in a multi-league game (current-round semantics, the ad-hoc rate limit sitting above the provider quota, narrowing the ad-hoc fetch by competition selection, and the never-refreshed one-off). Then launch phase L5 — Launch and first-Saturday watch.

## Batch 35 — A one-off round in a multi-league game
**Commits:** `9c85983` (scoped in `8910af3`) · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 315 tests), Playwright prod-bundle deep-link smoke. Run twice: after implementation and again against the exact tree committed. 17 new tests (11 `test_scheduler_jobs.py`, 3 `test_request_budget.py`, 2 `test_picks_flow.py`, 1 Vitest).

### Key facts for future sessions
- `current_round_order(now, today)` in `services/gameweek.py` is the single definition of "the
  round a league is on", returned as ORDER BY clauses because it has two call sites that must move
  together: `latest_gameweek` per league, and the window function in `routers/me.py`. Home renders
  every league's card side by side, so a disagreement between them is visible in one glance.
  `accepting_picks(now)` is the SQL twin of `pick_refusal` — same three conditions, same order.
- **The "locking soonest" tiebreak is the rule, not decoration.** Two rounds open at once is the
  ordinary state, not the Boxing Day edge case: the 2-week discovery horizon plus a Batch 27
  pick-open offset produces it every week. Reordering by `starts_on` again would look harmless.
- **The budget comment in `config.py` overstates the saturated day.** It models ~420 requests of
  browsing; `test_request_budget.py` *measures* 336 (+60 discovery), leaving 104/day and 72/hour.
  `AD_HOC_GAMEWEEK_LIMIT = "2/hour;3/day"` is derived from the measured figures, and both caps are
  load-bearing — hourly alone permits 24x its number across a day, daily alone permits all of it
  inside the peak browsing hour. slowapi parses the `;` form into two enforced limits.
- `fetch_slate`'s `competition_ids` may only narrow a fetch **nobody shares**. `refresh_slate`
  (one production caller, the ad-hoc endpoint) passes it; `discover_fixtures` must not, because its
  fetch feeds every league on the window — narrowing there would deny the next league its fixtures.
  The two directions are asserted against each other in `test_scheduler_jobs.py`, on requests
  issued rather than rows written, since the rows were already right.
- `discover_fixtures` walks cadence dates **union** `unlocked_round_dates`, and syncs an off-cadence
  date only to leagues that already hold a round on it — otherwise a neighbour sharing the window
  has a Boxing Day round invented for it. `run_refresh_slate`'s horizon of 1 means a one-off is
  reached only in its final week, which is when postponements matter.
- The batch scope said the frontend was covered by existing surfaces; it was not.
  `useGameweekHistory` anchored `GameweekNav` on `gameweeks[0]`, correct only while the API's
  default *was* the newest `starts_on`. Both coupon surfaces now pass the id their own read
  resolved to, and `isLatest` means "no `gw` parameter" rather than "index 0".
- `_open_sample_gameweek`'s lock now moves with `weeks_later`. It was flat, which no test could see
  while "current" meant newest date and which makes the new rule untestable.

**Next:** Launch phase L5 — Launch and first-Saturday watch. All 35 build batches are shipped on `main`.

## Batch 36 — The odds key in the production logs
**Commits:** 7c4c1c4 (specs), 70e30e8 · verified: pinned ruff 0.5.4 check + format, mypy (59 files), pytest 425 passed/117 skipped, web lint/typecheck/build/test (315 passed)

### Key facts for future sessions
- **The exposed key still needs rotating — that is an owner action and this batch does not do it.**
  The code only stops future requests republishing it. Until rotation, the key in the retained
  Railway log window is live.
- Redaction happens in `_redacting_json_renderer` (`logging_config.py`), not at any call site.
  That is deliberate: it covers the event message, keyword values, nested structures, and any
  third-party library, and it survives someone re-enabling a quieted logger. `Settings.secret_values()`
  feeds it, sorted longest first so a secret containing another as a substring cannot be partially
  masked, and excluding values under 8 characters so an unset `""` cannot rewrite every line.
- `run_scheduled.py` never calls `configure_logging`, so one-off `railway run` jobs get stdlib
  defaults (WARNING) and neither leaked nor gained redaction. Left alone as out of scope, but a
  log level set there later would be unprotected — the redactor only guards configured processes.
- **The shared venv's ruff disagrees with the pin and will report a false failure.** It flagged
  `src/models/league.py` as unformatted; pinned ruff 0.5.4 reports all 94 files clean.
  `docs/agent-commands/batch-verify.md` says to use `uvx "ruff==$(...)"` for exactly this reason —
  the venv's ruff is not the gate and its formatting verdict should be ignored.
- The odds-api.io header question the batch row raised was **not** probed and no longer blocks
  anything: the renderer-level redactor already delivers what a header would have (survival past a
  re-enabled logger), so spending a live request to confirm it was not worth the quota.

**Next:** Batch 39 — Six admin buttons beside a title.

## Batch 39 — Six admin buttons beside a title
**Commits:** de5b3a6 · verified: pinned ruff 0.5.4 check + format, mypy (59 files), pytest 425 passed/117 skipped, web lint/typecheck/build/test (319 passed, +4)

### Key facts for future sessions
- **A member deliberately keeps a plain `Leave` button; only an admin gets the menu.** One
  button beside a title never overflowed, so collapsing it would cost a tap and save no width.
  The header therefore renders differently by role, which is intended rather than an oversight.
- The existing `ui/dropdown-menu.tsx` Radix primitive was already in the repo and unused by this
  component. It supplies focus management, Escape-to-close and outside-click dismissal, which is
  the substance of the batch — a row of buttons needed none of them.
- `DropdownMenuItem asChild` around a `Link` renders the anchor **as the menuitem**, so the items
  are `getByRole('menuitem')` and still carry `href`. Tests that looked for
  `getByRole('link', …)` no longer match; that is what the old admin test asserted.
- Radix's dropdown needed **no** jsdom shims here (no `hasPointerCapture`/`scrollIntoView`
  stubbing) — `userEvent.click` on the trigger opens it as-is. Worth knowing before adding
  polyfills to `test/setup.ts` for a future Radix component.
- `PageHeader.tsx`'s `min-w-0 max-w-full` action wrapper from Batch 22 was left alone. It is
  harmless with a single trigger and still correct for other pages using the slot.
- Not browser-verified: the component only renders for a signed-in league admin, and reaching
  that state needs credentials. Behaviour is covered by unit tests (collapsed, opened, Escape +
  focus return, and the delete dialog still gating deletion).

**Next:** Batch 38 — When a pick was taken.

## Batch 38 — When a pick was taken
**Commits:** 979a3bb · verified: `scripts/ci-local.sh` PASS (11 checks), including alembic upgrade head + the DB-backed pick flow

### Key facts for future sessions
- **Adding a timestamp changed what "distinct holder" means.** `_holders_by_fixture` deduped on
  the whole holder value, which was equivalent to per-player only while that value was
  `(player_id, name)`. Two selections claimed a minute apart are different values but the same
  person, so the fixture line would have named them twice. It now dedupes on `player_id` and
  keeps the **earliest** claim. Any future field added to `_Holder` faces the same trap.
- `taken_at` is **additive and optional on the client** on purpose. Vercel deploys the web app
  from `main` while the API waits for `/ship-prod`, so a renamed or required field would break
  the coupon in the gap. `types.ts` marks it `?` and `PickCard` renders the holder's name with
  no time when it is absent — there is a test for exactly that.
- The time is **absolute**, in the league's timezone, formatted `d MMM, HH:mm` — the kickoff
  line's format minus the weekday. Relative ("2h ago") was rejected: the coupon is cached, so a
  relative label is wrong as soon as it is re-read without a re-render, and a pick window that
  opens weeks ahead makes a bare weekday ambiguous.
- Only the **per-selection** line carries the time. The fixture-level `Picked by …` summary was
  left as names: it is a summary of *who*, and duplicating the instant there reads as noise.
  This is a deliberate narrowing of the batch row, which asked for both.
- **Every instant this API returns is naive UTC** (`DateTime(timezone=False)` on `created_at`,
  `kickoff_utc`, `locks_at_utc`) and serialises without a `Z`, while the frontend parses with
  `new Date(...)`, which reads a bare string as *local*. `taken_at` was made consistent with its
  siblings rather than diverging. Worth noting that the app-wide convention means displayed
  times are off by the local UTC offset for any non-UTC viewer — pre-existing, not this batch.
- `scripts/ci-local.sh` is the gate that actually exercises the pick flow; a bare `pytest` skips
  41 DB-backed tests silently, so a green plain-pytest run proves less than it looks.

**Next:** Batch 37 — A division that resolves to the Premier League.

## Batch 37 — A division that resolves to the Premier League
**Commits:** 42be031 · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The tab is still empty after this ships, and that is expected.** The code no longer
  mis-resolves, but production already holds rows written under the wrong id: `upsert_teams`
  moves a club's `competition_id` to wherever it was last seen, so Premier League clubs and
  tables sit against non-League competitions and genuine clubs may have been dragged out of
  correctly-matched ones. **The affected competitions' teams and standings must be cleared
  before a corrective `sync-football` sweep.** That data work was deliberately excluded from
  this batch and is still owed.
- **Coverage is not the problem and the Batch 33 question is closed.** A catalogue probe on
  2026-08-19 returned 1240 leagues, 46 English, 24 carrying season 2026, including National
  League North/South (50/51) and all four Non League Premier divisions (58/59/931/60).
- `similarity(..., allow_subset=False)` is the fix, not a lower `SUBSET_SCORE`. The bonus is
  load-bearing for clubs ("Inverness Caledonian" for "…Thistle"); lowering it there unmatches
  real clubs. One flag, two opposite truths — a shorter *club* name is an abbreviation, a
  shorter *competition* name is a different competition.
- `league_id_for` now applies `MATCH_MARGIN` as well as `MATCH_THRESHOLD`. It never did,
  despite `similarity`'s docstring saying the subset score leans on that guard — the guard
  lived only in `best_match`, which the competition path does not use.
- **An override answers before `_all_leagues()` is called**, so an overridden competition
  costs zero catalogue requests. Both sides of the four entries were read from the live
  odds-api.io and api-football catalogues on 2026-08-19, not inferred from a spelling rule.
  Slugs are odds-api.io's (`england-amateur-southern-league-premier-division-south`).
- The National League regional slugs are **absent from the override table on purpose** —
  they normalise to an exact match, and listing them would imply they were broken.
- The old `LEAGUES` test fixture had no "Premier League" row, which is why no test caught
  this: the wrong answer was not in the candidate list. `ENGLISH_PYRAMID` now mirrors the
  real catalogue, and the regression test asserts `!= "39"` explicitly.
- Nothing was needed on the frontend. `PickCard` has rendered position and form since Batch
  16 and hides the strip only when a club has neither.

**Next:** Batch 41 — Naming the round.

## Batch 41 — Naming the round
**Commits:** 72bdae8 · verified: `scripts/ci-local.sh` PASS (11 checks), including migration 014 on a clean scratch database

### Key facts for future sessions
- **The number is stored, not derived, and Batch 35 is why.** An ordinal computed from
  `starts_on` order renumbers every later round the moment an admin inserts a one-off, so a
  member's "Gameweek 12" silently becomes a different week. Stored, a one-off takes the *next*
  number — it is the next round the league plays — and history is fixed. Do not "simplify" this
  back into a derived ordinal.
- Numbering is **one past the maximum**, not one past the count, so deleting a round leaves a
  gap rather than handing its number to the next round. Per league, per season.
- **No unique constraint exists and none can, cheaply.** The season a number is unique within is
  derived from `starts_on`, not stored, so the invariant lives in `next_gameweek_number` alone.
  Adding a `season` column purely to constrain it was judged not worth a column nothing reads.
- Migration 014's season expression is **duplicated SQL**, not an import — a migration must not
  depend on application code that keeps moving. `test_migration_014` is what holds the two
  definitions together; if `_SEASON_ROLLOVER_MONTH` ever changes, that test fails first.
- `DATE :param` is not valid SQL and asyncpg infers a bind's type from its cast — seeding a
  migration test needs real `date`/`datetime` objects passed as parameters, not strings cast in
  the statement. Cost two debugging rounds here.
- `number` is optional on **both** TS types and nullable in the API. The web app deploys ahead of
  the API, so a slate served before this ships has no number; `roundName` falls back to the date
  the round always showed. One helper serves the header and the nav so they cannot disagree.
- `roundName` tests `0` explicitly: `number || fallback` would drop a legitimate Gameweek 0.
- `GameweekNav` still hides below two rounds. That rule is about *navigation* having somewhere
  to go, not about naming — the header labels the round either way.

**Next:** Batch 42 — Profile pictures (code-only, no storage bucket).

## Batch 42 — Profile pictures
**Commits:** 531985a · verified: `scripts/ci-local.sh` PASS (11 checks), including migration 015 on a clean scratch database

### Key facts for future sessions
- **Avatars are modelled but not enabled, and uploading answers 503 in every environment.**
  `AvatarStorage` has exactly one implementation — `UnconfiguredAvatarStorage` — which refuses
  writes and no-ops deletes. `src/services/avatar_storage.py` lists the three things that must
  be true before a backend is wired; the outstanding one is that **bytes are never re-encoded**.
  Magic-byte sniffing proves a header, not a payload, and no imaging library is a dependency.
- The image is the **raw request body** typed by `Content-Type`, not multipart. Deliberate: one
  file needs no envelope and it keeps `python-multipart` off the API's dependency list. The
  client sends `fetch(url, {method:'POST', headers:{'Content-Type': file.type}, body: file})`.
- `_read_capped` streams and aborts past the cap rather than `await request.body()`, so an
  oversized upload is refused while it arrives instead of being buffered whole first.
- **Removal is a *site* admin action, not a league admin one.** An avatar is a profile field and
  follows a member into every league, which reaches past any single league's remit. Clearing
  your own works whether or not a backend exists, so enabling one is not a one-way door.
- `AvatarUpload.tsx` is **built and intentionally unmounted**. A visible control that always
  fails is worse for members than none; the component's docstring says exactly where it mounts
  (`SettingsPage`, a `SectionCard` beside Timezone) when a backend lands.
- The display half needed no work — `AuthContext`, `TopBar` and `LeagueMembersPage` already
  passed `src` to `Avatar`. It was null only because the API hardcoded it.
- **`MagicMock(spec=Profile)` returns a mock for any unset attribute**, and pydantic rejects
  that against `str | None`. Adding a field to `PlayerInfo` therefore breaks every auth test
  until `_make_user` sets it. Expect this again for the next profile field.
- **A deprecation warning from the shared venv can be a trap.** Newer starlette warns that
  `HTTP_413_REQUEST_ENTITY_TOO_LARGE` is deprecated; following that advice raises
  `AttributeError` on the pinned starlette==0.37.2 that CI and production run. Same class of
  divergence `batch-verify.md` records for ruff — trust the pins, not the dev venv.

**Next:** No unchecked build batches remain except Batch 40 (deferred pending a product decision).
