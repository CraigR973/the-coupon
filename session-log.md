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

## Batch 43 — Every time this app shows is an hour wrong
**Commits:** 29b2104 · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The fix is one annotation, `UtcDatetime` in `apps/api/src/schemas.py`**, applied to every
  datetime a response model carries. It is a `PlainSerializer` returning an *aware* datetime,
  not a string, so OpenAPI still says `format: date-time` and a Python-mode `model_dump()`
  still yields a `datetime`. Pydantic renders that as `…Z`, not `+00:00` as the row's wording
  suggested — same instant, and it needs no bespoke string serialiser.
- **`tests/test_wire_datetimes.py` walks `app.routes` and the models they nest**, so a model
  written next year is covered the day it is added. Proven to bite: reverting one field to a
  bare `datetime` fails it naming `CurrentRound.locks_at_utc`. Storage stays naive UTC — no
  migration, no column change, and the backend's naive-to-naive comparisons are untouched.
- **The test runner's zone is now pinned to `America/New_York` (`vite.config.ts`).** This is
  the load-bearing half of the frontend work: in a UTC process a mis-parsed instant and a
  correct one are the same number, so CI (UTC) could never see this while this Mac
  (Europe/London) could. Do not "simplify" that env line away.
- The frontend fixtures now carry the **offset-less** shape the API really sends, not the
  `Z` form they were written with. Some `created_at` fixtures still use `Z` — deliberately:
  both shapes are live at once during the ship gap.
- The client keeps its own defence (`parseInstant` in `src/lib/time.ts`) even though the API
  is fixed, because Vercel deploys `main` on merge and the API waits for `/ship-prod`.
  **Until that ship-prod runs, the client-side half is the only half in production.**
- **`starts_on` is a calendar date, not an instant.** `new Date('2026-08-22')` is UTC
  midnight, so `formatInTimeZone` into any American zone rendered the previous day — the
  round announced for a Friday. `formatCalendarDate` renders the day it names and converts
  nothing. `GameweekNav`, `ResultsPage`, `PlayerProfilePage` and `CouponCombinedPage` no
  longer take a `timezone` prop at all.
- Reverting `parseInstant`/`formatCalendarDate` fails **14 tests across 4 files**, including
  three that predate this batch — that is the regression gate, and it did not exist before.

**Next:** Batch 44 — Turning avatars on.

## Batch 44 — Turning avatars on
**Commits:** 4d1d665 · verified: `scripts/ci-local.sh` PASS (11 checks), venv rebuilt from the new pin

### Key facts for future sessions
- **The feature is complete and switched off.** `AVATAR_STORAGE` defaults to `none`, so every
  environment behaves exactly as it did after Batch 42 — 503 on upload, no card in Settings.
  Turning it on is `docs/runbooks/avatar-storage.md`, and it is an **owner action**: it needs
  the Supabase dashboard and seals a service-role key. Nothing was provisioned by this batch.
- **Pillow is the API's first imaging dependency** and pinned to the newest patched line on
  purpose — it is the one dependency here whose whole job is parsing bytes a stranger chose.
  `ci-local.sh` rebuilt its venv from the changed pin and passed, so the manylinux wheel
  resolves; nixpacks installs from the same file.
- **The bomb guard is an ordering, not a check.** `Image.open` parses the header only, so
  dimensions are known while refusing is still cheap. The 2 MB body cap bounds what *arrives*
  and says nothing about what a decoder allocates — a 4000×4000 1-bit PNG is under 100 KB.
  Do not move the pixel check after the decode.
- **`avatar_url` is a plain public URL and the random key is the access control** (ADR 0006).
  Player ids are on every league page, so a key derived from the id alone would make every
  member's picture enumerable. Replacing a picture deletes the old objects, which is what
  makes `immutable` caching safe and what makes a leaked URL stop resolving.
- Private-bucket signed URLs were the stronger posture and were rejected on cost: the column
  becomes a path and every member list becomes a Supabase round trip per picture. The owner
  accepted the trade-off on 2026-08-20.
- **`GET /api/v1/config` is read live, never cached at login.** It was deliberately *not* put
  on `PlayerInfo`: the client stores that at login and refreshes it only on the next one, so
  a member signed in before the bucket existed would carry a stale `false` indefinitely.
- A 404 from `/api/v1/config` must read as "feature off", not as an error — Vercel ships this
  app from `main` on merge while the API waits for `/ship-prod`, so the route is genuinely
  absent for a few days. `useClientConfig` has `retry: false` and falls back to all-off.
- **A test fixture whose catch-all returns 401 will tear down the page's auth.** Adding the
  `/config` call to `SettingsPage` broke four unrelated tests that way before the fixture
  answered the route explicitly. `apiFetch` treats 401 as an expired session and redirects.

**Next:** Batch 45 — A sweep that fails completely and reports success.

## Batch 45 — A sweep that fails completely and reports success
**Commits:** 8f72d0d · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **A list of reports cannot answer the job's question**, and that is the whole batch. A
  competition that *raised* leaves no report, so an empty list means both "the card was
  empty" and "all 21 failed" — opposite verdicts. `FootballSweep` carries `attempted`
  alongside the reports because it cannot be derived from them.
- `carried_nothing` is `attempted > 0 and carried == 0`. One condition covers **both**
  shapes of total failure — every competition raising, and every competition being
  honestly empty — because `carried` counts reports and a raiser has none.
- **The sweep's per-competition tolerance was not touched and must not be.** One division
  the provider dropped must not cost the other twenty-nine their tables. The verdict is
  the caller's job; that separation is the design, not an accident.
- Both legitimate zero-work runs stay green and are tested: no provider configured
  (returns before a sweep starts) and an empty fixture pool (`attempted == 0`). Batch 16's
  docstring warns against exactly the regression of failing an opted-out deployment daily.
- **A card where every competition genuinely has nothing yet would now be called a
  failure.** Accepted deliberately: across twenty-odd British divisions that is not a
  state that lasts, and a morning where nothing at all could be ingested is worth
  surfacing.
- The partial-failure threshold the row suggested (18 of 21 raising is not healthy) was
  **not** implemented — the row says the total-failure case should not wait for agreement
  on a ratio. The log line now carries `attempted`, `reported`, `failed` and `carried`, so
  whoever wants a ratio has the data.
- `backfill_season` got the same verdict and the same return type. Same defect one
  function away, and a human reads that one's output.
- `run_scheduled.main` already maps `False` to `SystemExit(1)`, so the cron became honest
  with no change there — `test_main_exits_nonzero_when_job_fails` already covered it.
- Reverting the verdict fails two scheduler tests, and the log output they print is the
  literal production line: `football data synced attempted=21 carried=0`.

**Next:** No unchecked build batches remain except Batch 40 (deferred pending a product
decision). Launch L5 — launch and first-Saturday watch — is the remaining launch work.

## Batch 40 — A round the pick window never reached
**Commits:** 15d3b3a · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The forward-only rule stands, and the admin restamp was deliberately not built.** The
  row's own 2026-08-20 production read settled it: `the-coupon` had all three rounds at
  `picks_open_at_utc = NULL`, only the 08-22 round was affected, and it held zero picks.
  A one-round transitional problem does not justify standing machinery that invites the
  exact edit `leagues.py:873` forbids — moving a deadline members were already told.
- **What shipped is visibility, not behaviour.** No API change, no migration; both instants
  already rode on `GameweekListEntry`. `PickOpenSchedule` lists the rounds an opening can
  still apply to and says what each will actually do.
- **`picks_open_at_utc = NULL` means no gate at all — not an older offset.** `pick_refusal`
  gates only when the column `is not None`, so such a round is claimable from the moment
  discovery writes it. That is the case that reads as "my setting was ignored", so it is
  worded most plainly: "Open now — no opening time was set".
- Locked and settled rounds are excluded on purpose. Their opening is history, and showing
  it would invite the restamp this batch decided against.
- **Adding `useAuth` to `LeagueSettingsPage` broke all 9 of its existing tests at once** —
  the file's `renderPage` never wrapped `AuthProvider`, though the real app always does.
  Expect this for any page-level test harness here that has not needed the player before.
- `formReady()` is defined per-describe in that file, not at module scope; a new block
  needs its own. The barrier matters for the same reason Batch 27's note gave — the
  assertions that follow do not all retry.
- `PickOpenSchedule` guards with `Array.isArray` rather than trusting its prop. The web
  app deploys ahead of the API, and a settings page that throws is worse than one that
  shows nothing.

**Next:** No unchecked build batches remain. Launch L5 — launch and first-Saturday watch.

## Batch 46 — Reading the whole card from a source that has it
**Commits:** beb070b · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **Probe before you trust ADR 0007's coverage claim.** It was written as settled with
  only the *tables* checked; `fetch_results` — half the port, and the source of the pick
  card's form strip — was never verified. The probe closed it and changed the design.
- **One request returns both halves.** `/api/data/leagues?id=X` carries `table` *and*
  `fixtures`. The ADR assumed api-football's two-per-competition shape. `fetch_table`
  and `fetch_results` share one memo, so `8947`'s four competitions cost one request.
- **Tables split; results do not.** A composite payload has `data.tables` with a
  `leagueId` per division. `fixtures.allMatches` is flat — 1104 matches for `8944` —
  with **no** division marker on a match. Do not go looking for one; `round`/`roundName`
  are matchweek numbers.
- **Attribution is by team id, never by name.** Table rows carry integer ids, giving a
  team-id → division index. Live measurement: 1104/1104 and 67/67 attributed, and 67/67
  finished matches had both teams in the same division. Removing the filter fails
  `test_results_are_attributed_by_team_id_not_by_name`.
- **Country-scoping is load-bearing, not tidiness.** Name-only matching put Scotland's
  League One on England's `108`, Scotland's Championship on England's `48`, and
  Scotland's Premiership on Northern Ireland's `129` — against the live catalogue. Same
  class as Batch 37. odds-api.io says "England Amateur", so the trailing word is stripped
  before the country lookup.
- **Group ids, read live on 2026-08-20:** `8944` → 940360 NL North, 940374 NL South;
  `8947` → 941117 Southern Central, 941118 Southern South, 941116 Northern Premier,
  941109 Isthmian; `9545` → 1000001473 Highland, plus both Lowland groups we do not use.
- **A 404 must raise.** `/api/leagues?id=47` 404s while `/api/data/leagues` works; a
  swallowed 404 would turn a path change into a silent empty sweep, which is exactly what
  Batch 45 exists to catch.
- Recorded payloads live in `tests/fixtures/fotmob_payloads.json` — **full** table rows,
  because trimming them to three per group emptied the division index and made the
  attribution test vacuous.
- Ships dark. `FOOTBALL_DATA_PROVIDER` still defaults to `none`; `fotmob` needs no key.

**Next:** Turning it on is one variable plus a staging sweep. Launch L5 remains.

## Batch 47 — A league with no rounds until tomorrow morning
**Commits:** `f03a6bb` · verified: `scripts/ci-local.sh` PASS (11 checks) — 635 pytest
with a database (499 without), Ruff 0.5.4 check/format, strict mypy, clean `pgserver`
through `015`, 355 Vitest, Node 20 build, prod-bundle Playwright; plus a live browser
run against `tests/e2e_server` on a scratch Postgres

### Key facts for future sessions
- **The pool *is* the second entry point.** `discover_fixtures` already fetches each
  `(window, date)` once, so `pooled_slate` turns existing `fixtures` rows back into a
  `Slate` — same `query_bounds` in SQL, same `contains` in Python — and `sync_slate`
  cannot tell it from a fetched one. The common case costs **zero** provider requests.
  Caveat worth knowing: a date whose only fetch was an ad-hoc one holds just that
  league's competitions, so a pooled read can be a partial card. The daily run heals it.
- **Sharing a slowapi limit needs both halves.** `slowapi` evaluates a limit as
  `limiter.limiter.hit(item, key, scope)` with `per_method=False`, so a route decorated
  `shared_limit(value, scope)` and `consume_shared_limit(key, value, scope)` draw one
  bucket. The imperative half exists because a decorator charges every request that
  reaches the route, and charging the free pooled case would price the common one out.
- **The bucket counts sweeps, not calls.** One unit ≈ one league-scoped `/events` sweep
  (≤30 requests), charged per *date* the pool cannot serve. With `slate_horizon_weeks=2`
  an unpooled league spends the whole `2/hour` in one refresh — which is what keeps
  `PROVIDER_SLATE_FETCH_LIMIT`'s arithmetic true however many routes spend it.
- **`create_league` must not resolve `OddsProviderDep`** — it raises 503 when the
  provider is unreachable, which would wire creating a league to odds-api.io being up.
  New `get_optional_odds_provider` returns `None` instead; tests overriding the provider
  must override **both** functions (`test_picks_flow`, `e2e_server`) or creation silently
  reaches the real session.
- **The window is the filter, so moving it changes which pooled fixtures qualify.** A
  refresh after a window move links the new window's fixtures and keeps the old ones —
  `sync_slate` adds links and never removes them — while `picks_open_at_utc` and
  `locks_at_utc` stay as stamped. A test that pools fixtures only at the *old* time and
  then moves the window will see a fetch, not a rebuild; that was a real red.
- **A fetch that found nothing is not "nothing to do".** The live run exposed a false
  toast: the endpoint swept both cadence dates, the provider carried no card for either,
  and the UI said "Rounds are already up to date". `fetched_dates` non-empty with zero
  rounds is the ordinary out-of-season answer and now says so.

**Next:** Batch 48 — the pick screen dies when the odds provider says no. This batch is
API-side, so it is invisible in production until a `/ship-prod` runs.

## Batch 48 — The pick screen dies when the odds provider says no
**Commits:** `1f16873` · verified: `scripts/ci-local.sh` PASS (11 checks) — 647 pytest
with a database (508 without), Ruff 0.5.4 check/format, strict mypy, clean `pgserver`
through `015`, 357 Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The fallback lives behind the port, not in the router.** `fetch_odds_best_effort`
  returns `OddsSnapshot(odds, degraded)` and never raises: the base implementation on
  `OddsProvider` degrades to *no* prices, and `CachingOddsProvider` overrides it to serve
  the entries it is already holding past their TTL. `fetch_odds` is untouched and still
  raises, which is the whole of "browsing degrades, picking must not" — the two
  request-path callers get opposite treatment without the router knowing which provider
  it holds.
- **A failed refresh must not restamp the entries**, or recovery would wait a full TTL
  instead of a page load. The corollary is that a degraded slate re-attempts upstream on
  *every* load (one chunked sweep each). Fail-fast on `429` is what makes that
  affordable; no failure cooldown was added, and that is the thing to reach for if a
  long outage ever proves it needs one.
- **A FastAPI dependency override must close over its instance, never take a default
  argument.** `lambda cached=CachingOddsProvider(...): cached` is read as a *query
  parameter*, and pydantic deep-copies the default per request — so every request got its
  own empty cache and the warm-cache test proved nothing while appearing to pass. That
  cost a red before it was spotted.
- **`429` is now terminal in `OddsApiProvider._get`.** `betfair.py` and `api_football.py`
  still retry it — deliberately out of scope, and neither is the production odds source.
  Settlement inherits the change: a rate-limited settle run now fails on its first
  attempt and waits for the next scheduled tick rather than spending 4x the quota to
  fail anyway.
- **The pick submit path answers `503 ODDS_UNAVAILABLE`** where an unreachable provider
  used to be an unhandled 500. Still a refusal, still loud, but one the client can name —
  `pickErrorMessage` says the pick was *not saved*, which a generic error did not.
- **app-starter's venv can no longer run this suite.** It has no Pillow, so ten test
  files fail at collection through `avatar_storage.py`, and it ships fastapi 0.139
  against the pinned 0.111. `scripts/ci-local.sh` (venv at `~/.cache/the-coupon/`) is the
  real gate; `AGENTS.md` and `docs/agent-commands/batch-verify.md` still document the old
  path and are wrong.

**Next:** no unchecked batches remain in `docs/BUILD_PLAN.md`. Launch L5 — launch and
first-Saturday watch — is the remaining work. This batch changes both halves, so the web
banner deploys on merge while the API fallback waits for a `/ship-prod`; until then the
flag is simply absent and the client reads that as "not degraded".

## Batch 49 — A postponed fixture nobody can take off the card
**Commits:** `d1a95d4` · verified: `scripts/ci-local.sh` PASS (11 checks) — 652 pytest
with a database, Ruff 0.5.4 check/format, strict mypy, clean `pgserver` through `015`,
357 Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The provider's answer was neither of the two the plan anticipated, and this matters.**
  Probed live 2026-08-21: `/events` *does* carry a status and *does* emit void words — 2
  of the 1,599 fixtures listed for 2026-08-22 came back `cancelled` — but Hibernian v
  Kilmarnock, the fixture that prompted the batch, was still `pending` despite being
  called off. So the general case is closed and the observed one is not. Do not expect
  pre-lock removal to catch every postponement; settlement's `void` is still the backstop.
  api-football cannot second-opinion it — the free plan refuses any 2026-season query.
- **`SlateFixture.status` defaults to `""` and that default is load-bearing.** It means
  "this source does not say", which is the truth for `FakeBetfair` (a catalogue of open
  markets) and for `pooled_slate` (rebuilt from `fixtures`, where no status is stored).
  Both therefore *cannot* unlink anything, which is what keeps a pooled refresh and an
  ad-hoc rebuild safe without either of them knowing about Batch 49.
- **Removal is gated on `locks_at_utc`, never on `GameweekStatus`.** The label is only
  what the hourly jobs keep up with; the instant is the fact. A test dated in the past
  would therefore pass for the wrong reason, which is why `_upcoming_saturday()` derives
  a date from `uk_today()` rather than reusing `SAMPLE_SATURDAY` (2026-08-01).
- **`gameweek_fixtures` has no cascade to `picks`** — it is a composite-key join, and
  `Pick` references `fixtures`/`gameweeks` directly. Unlinking alone leaves a pick off
  the screen but still visible to settlement. Anything that removes a link in future has
  to delete the pick too.
- **The postponement notification lives in `services/gameweek.py`, not
  `notification_triggers.py`**, because that module imports this one
  (`members_missing_picks`) and the cycle is real. `data.type` is free-form, so
  `"fixture_postponed"` needed no enum and no migration; an `ActionType` would have.
- **Round creation now keys on the *playable* fixtures**, so a date whose whole card is
  called off produces no round rather than an empty one. Slightly wider than the row
  asked for, and the natural corollary of the rest.

**Next:** Batch 50 — the three omissions on the pick card. This batch is API-side, so it
is invisible in production until a `/ship-prod` runs; until then the deployed API keeps
carrying a called-off fixture on the card.

## Batch 50 — What the pick card leaves out
**Commits:** `e821d95` · verified: pnpm lint (0 errors), typecheck, build, 361 Vitest — all
green. Frontend-only batch (scope boundary: no API change), so the backend gate and
browser checks are out of scope.

### Key facts for future sessions
- **The names row and context strip are now one grid, not two.** `PickCard`'s team names
  used to be an inline sentence (`Home v Away`) sitting over a separate `grid-cols-2`
  strip below it — they aligned by text-length coincidence. Both rows are now children of
  the same `grid grid-cols-2` container, with the context cells wrapped in a
  `display: contents` div so the `fixture-context-{id}` test id still resolves to just
  those two cells.
- **The "v" separator is absolutely positioned but kept in DOM order between the two
  names**, not appended after both — otherwise a screen reader would announce "Home,
  Away, v" instead of "Home, v, Away".
- **`potentialPoints()` was already free to keep on-screen in every claim state** — it's a
  pure `round(odds × 10)` of the displayed price, so showing it on "taken by X" and "your
  pick" needed no new prop, just dropping the exclusive three-way branch in
  `SelectionButton`.

**Next:** Batch 51 — untying Football Stats from the coupon's league-competition scope.

## Batch 51 — Football Stats is not a coupon surface
**Commits:** `4d94888` · verified: `scripts/ci-local.sh` PASS (11 checks) — 655 pytest with
a database, Ruff 0.5.4 check/format, strict mypy, clean `pgserver` through `015`, 366
Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The screen's data was never league-scoped — only its read was.** `pooled_competitions`
  already walked the whole fixture pool and `teams` / `matches` / `standings` carry no
  league column, so untying it cost **zero** extra provider requests. Anything that looks
  league-scoped in the football half is worth checking against this before it is believed.
- **A competition is in the pool only if a `fixtures` row names it.** `pooled_competitions`
  derives from `fixtures.competition_id`, not from `standings`, so "every competition we
  hold" means every one some league's card has drawn from. That is what the empty states
  now say, and it is why `test_football_router.py` must seed `Fixture` rows — the old seed
  wrote standings alone and would return nothing at all against the new endpoints.
- **The pool is shared, so those tests assert containment, not length.** Every assertion
  filters the response to the run's own tagged slugs; `test_picks_flow` and
  `test_round_population` both commit fixtures that survive into this suite's view.
  `Match` is unique on `provider_match_id` globally and `sync_results` re-points
  `competition_id`, so a crashed run leaves no duplicate — only a moved row.
- **`isLeagueHubPath` now tests the predictions *shape*, not the section list.** Dropping
  `/football` from `PREDICTIONS_SECTIONS` made `predictionsSection()` return `null` for
  the retired addresses, which would have lit the Leagues tab for the frame before the
  redirect. Any future section removal has the same trap.
- **`scripts/check-deploy-drift.sh`'s tier-3 probe named the route this batch deleted.**
  Left alone it would have called a *current* image DRIFTED. Repointed to
  `/api/v1/football/tables` / Batch 51. Deleting a route means moving that probe.
- **"Football Stats" fits the mobile tab bar on one line** — measured against the built CSS
  in Outfit at 57.7px, in a 75px tab at 375px and a 64px tab at 320px. No wrap, no
  clipping, no CSS change needed. Roughly one more character of slack is all there is.

**Next:** Batch 52 — the Form column hidden on every phone, and results grouped by day
alone. This batch is API-side as well as web, so the two halves separate on merge: Vercel
takes the new `/football` screen immediately while the deployed API still serves only the
league-scoped endpoints, which the untied page does not call. **A `/ship-prod` is owed
before the tab works in production.**

## Batch 52 — A table that hides the column it exists to show
**Commits:** `6b1950c` · verified: pnpm lint (0 errors), typecheck, build, 369 Vitest — all
green. Frontend-only batch (scope boundary: no API change, both fields already served), so
the backend gate and browser checks are out of scope.

### Key facts for future sessions
- **Batch 51's "Next" note calling this batch API-side was wrong** — both `form` and
  `competition`/`competition_id` were already served on `CompetitionTable` and
  `ResultEntry`; nothing needed adding on the API side.
- **The narrow-width trade flipped, it didn't grow.** `LeagueTableCard` still hides four
  columns below `sm`, just not the same four: Goal Difference now carries `narrowHidden`
  and Form does not, since form is one of the two things a member opens the screen to read.
- **`groupByDay` now nests a `Map<competition_id, CompetitionGroup>` inside the day map**,
  so a Saturday across four competitions produces one heading per competition instead of
  one undifferentiated eighty-match list. The per-row competition label only survives when
  a day has exactly one competition, so a single-competition day doesn't grow a redundant
  second heading.
- **Precondition confirmed before starting: ingestion is still broken.**
  `run_sync_football_data`'s docstring ([scheduler.py:259](apps/api/src/scheduler.py:259))
  still records the 2026-08-20 all-competition failure; this batch improves the
  presentation of what may currently be an empty screen, and that's expected — no ingestion
  change was in scope.

**Next:** Batch 53 — form pips that open into the matches behind them.

## Batch 53 — Form you cannot open
**Commits:** `0235e9f` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff
check/format, mypy, alembic upgrade head + pytest on scratch pgserver,
deployment-config, pnpm lint/typecheck/test/build, playwright deep-link smoke. Plus
targeted runs: 16 football backend tests against a real `pgserver`, 66 Vitest across
`FormLine`/`PickCard`/`FootballPage`.

### Key facts for future sessions
- **The batch arrived already implemented, uncommitted, on an existing branch.** A prior
  session had left ~770 lines on `feat/batch-53-form-disclosure` with the row still
  unchecked. `/batch-start`'s clean-worktree-on-`main` precondition does not describe
  every real start; audit against the row before assuming a fresh one is wanted.
- **`docs/agent-commands/batch-verify.md` is still wrong and cost a full cycle again.** Its
  backend commands point at app-starter's venv, which has no Pillow (pinned since Batch
  44), so pytest dies at collection in ten files. `scripts/ci-local.sh` is the only
  correct gate; its venv is reusable at `~/.cache/the-coupon/ci-local-venv/bin/`. A task
  chip is open to fix the doc — this has now bitten Batches 48 and 53.
- **`league_tables()` no longer trusts `standings.form`.** It derives the string from the
  matches it just loaded (`form_string(recent) or standing.form`). The provider writes
  that string from a *different* upstream call and it can disagree with `matches`; once
  the pips open, a disclosure contradicting the thing that opened it is worse than none.
  The stored string survives only as the fallback for a club with a table line and no
  matches — pips the client deliberately leaves inert.
- **A disclosure cannot live inside `role="img"`.** That role swallows its subtree, leaving
  `aria-expanded` nothing to describe. `FormLine` keeps the role only while it is a plain
  graphic and moves the *same* accessible name onto a real `<button>` when `onToggle`
  arrives. The name did not need rewording — it names the same thing either way.
- **The panel is placed by the caller, never inside the pips.** In the table's Form cell it
  would have forced sideways scrolling and undone exactly what Batch 52's hidden columns
  protect; so the table opens a `colSpan` row and the pick card opens full-card-width
  under the header.
- **Results print oldest-first, against the usual results-list habit**, so the nth row is
  the nth pip. Reversing one list against the other to identify a pip is a puzzle, not an
  answer. Scores are for-and-against from the club's own side with H/A saying which end,
  which keeps them readable without colour — the same rule the pips follow.
- **Precondition still unresolved:** `run_sync_football_data`'s docstring
  ([scheduler.py:259](apps/api/src/scheduler.py:259)) still records the 2026-08-20
  all-competition sweep failure. On current production data these pips may open onto
  nothing anywhere. The degradation is correct (inert, no empty panel), but the feature
  cannot be judged live until ingestion is fixed.

**Next:** no unchecked batches remain — `docs/BUILD_PLAN.md` is complete through Batch 53.
Launch planning resumes at **L5 — Launch and first-Saturday watch**, the only open phase in
`docs/LAUNCH_PLAN.md`. This batch is API-side as well as web, so the halves separate on
merge: Vercel takes the client immediately while the deployed API still serves
`TableEntry` without `recent`. `TableEntry.recent` is optional precisely for that window —
table pips simply will not open until **a `/ship-prod` is owed and run**.

## Batch 54 — A palette that was only ever checked against two of its four surfaces
**Commits:** f31cfbf · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 660 (clean schema, 0 skips) · lint · tsc · build · vitest 425

### Key facts for future sessions
- `--text-muted` is now `#8690A6` (dark) / `#666F7D` (light). Both were chosen as the
  *smallest* change that clears 4.5:1 on all four surface tiers; do not nudge them
  back toward the old greys without re-running `src/test/contrast.test.ts`.
- **`accessibility.test.tsx` cannot see colour and never will.** jsdom will not resolve a
  CSS custom property, so axe's `color-contrast` rule is disabled there. That is why
  `contrast.test.ts` exists and reads `index.css` off disk instead — Vitest stubs CSS
  imports, so both a plain import and `?raw` hand back an empty string.
- Six contrast failures remain in light mode and are deliberate: `--primary` and
  `--warning` used as text. One value cannot fix them — as text on white a colour needs
  relative luminance ≤ 0.183, as a fill under `--on-primary` it needs ≥ 0.208. They need a
  brand-as-ink token distinct from brand-as-surface. `KNOWN_DUAL_ROLE_DEBT` in the test
  asserts that list is exactly right, so it cannot silently grow.
- `--locked` is defined in both palettes and referenced by **nothing** — 0 text, 0 fill,
  0 border uses. Kept in sync with `--text-muted` rather than deleted, but it is dead.
- The full review this came from is `docs/review/2026-08-22/`, and Batches 55-60 are
  specified from it.

**Next:** Batch 55 — the viewport meta disables pinch-zoom app-wide.

## Batch 55 — The app takes zoom away from the people who need it
**Commits:** f92ba17 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 660 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **If iOS Safari starts zooming a focused field, do not put `user-scalable=no` back.**
  The cause is an input under 16px; fix the input. `src/test/viewport.test.ts` asserts
  both halves so the attribute cannot return quietly.
- That test's element scanner tracks brace depth deliberately. An earlier draft used
  `[^>]*` to grab attributes, which stops at the `>` inside `onChange={(e) => ...}` — so
  it never reached `className` and the whole file passed vacuously. It was only caught by
  reverting a known-bad input and finding the test still green. Any similar JSX-scanning
  test needs the same care.
- `min-h-6` on `FormLine`'s disclosure is WCAG 2.2 SC 2.5.8 (24x24), not decoration.
  Measured 70x22 before, 70x24 after.
- The five "Find a league" links are 82x18 and **conformant** — SC 2.5.8 exempts a target
  inline in a sentence. Do not "fix" them.
- Pick screen now reports **zero** axe violations at 390px in both themes.

**Next:** Batch 56 — changing a PIN revokes nothing and the reset flow notifies nobody.

## Batch 56 — Two halves of account recovery, neither of which works
**Commits:** 5f88f41 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 667 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **Changing a PIN now logs the member out everywhere, including the device they used.**
  That is deliberate, not a bug: the endpoint authenticates with an *access* token so the
  API cannot tell which refresh token is the caller's, and `device_hint` would spare an
  attacker who copied the User-Agent. `lib/api.ts` already bounces a failed refresh to
  /login, so the member is simply asked for the new PIN.
- The 24-hour access token still cannot be recalled — it is stateless. A revoked session
  keeps working until that token expires, then dies at refresh. Shortening `ACCESS_TTL`
  is a separate decision nobody has taken.
- `pin/reset-request` writes `ActionType.player_pin_reset` with `changes.stage =
  "requested"` rather than a new enum value. `ALTER TYPE ... ADD VALUE` is irreversible
  and production has no restore point, which is not a trade worth making for a label.
- **`audit_log` has no reader anywhere** — no query in `src/`, no frontend surface. That
  is why the reset request also pushes. If an admin surface is ever built, that table is
  where the history already is.
- **Open question for the owner:** `_notify_site_admins` looks for `UserRole.admin`
  profiles. The e2e seed creates none, so nothing was pushed in local verification. Worth
  confirming production actually has a site admin with a live push subscription, or the
  audit row is again the only trace.
- A **`/ship-prod` is owed** from this batch — it is the first backend change since the
  review and Railway does not move on a push to `main`.

**Next:** Batch 57 — three things wrong in the file that takes the pick.

## Batch 57 — Three things wrong in the file that takes the pick
**Commits:** 43183ad · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 674 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **The provider budget is fully committed.** Measured: peak browsing hour 28, ad-hoc
  rounds 60/hour, leaving ~12 of the 100/hour plan. Any new provider call in the request
  path has nowhere to come from — check `test_request_budget.py` before adding one.
- `PICK_SUBMIT_LIMIT` bounds **one member**, not the league. Fifteen members at 10/hour is
  150 against a 100/hour plan. `test_the_pick_path_is_not_bounded_in_total_and_this_is_known`
  asserts that gap still exists; if it ever fails, the gap was closed and the test should be
  replaced rather than deleted.
- The lock re-check reads the **clock**, not the row: `pick_refusal` gets the ORM object
  already loaded in the request's session, so a `locks_at_utc` changed by another session
  is invisible to it. Any test of that race must move time, not the deadline.
- `ruff format` wanted two files after this batch's edits and `ruff check` did not. Format
  is the *first* CI step, so a check-only pass locally still fails the job — run both.

**Next:** Batch 58 — the rate limits that are decorative (X-Forwarded-For, token reuse,
correlation id, token pruning, weak PINs).

## Batch 58 — The rate limits that are decorative, and the ones that are not
**Commits:** 9ecaa00 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 687 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- `client_address` counts **from the right** now. `trusted_proxy_count` (default 1) is how
  many proxies in front of the app are ours. Raise it only if a CDN is put in front of
  Railway — getting it too high reads a caller-supplied hop again, which is the bug.
- **Do not prune `refresh_tokens` aggressively.** A revoked row is the only evidence
  `/auth/refresh` has that a token was *replayed* rather than merely unknown. The 7-day
  `REFRESH_TOKEN_RETENTION` is what keeps reuse detection working; shortening it re-hides
  theft.
- Reuse detection revokes **every** token for the member, because rotation leaves no
  lineage to walk. If per-family revocation is ever wanted, the rows need a family id.
- `WEAK_PINS` is deliberately ~34 entries. Two existing tests broke on it (Batch 56 had
  used `5678`), which is the list working. Growing it much further starts refusing PINs
  people picked for real reasons.
- `Cache-Control: no-store` does **not** affect the PWA's offline cache — the Cache Storage
  API ignores HTTP cache headers, and Workbox's `CacheableResponsePlugin` filters on status.
- Two tests asserted the old, wrong behaviour and were rewritten:
  `test_client_address_prefers_first_forwarded_for_ip` and `test_correlation_id_passthrough`.
- A **`/ship-prod` is still owed** — Batches 56, 57 and 58 are all backend.

**Next:** Batch 59 — dependency advisories (starlette/FastAPI, cryptography, react-router).

## Batch 59 — Twenty-nine advisories, three packages, one real upgrade *(part)*
**Commits:** 576d4d5 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 692 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **cryptography does see untrusted input**, contrary to what `requirements.in` claimed
  until now: `push/subscribe` stores the browser's `keys` verbatim and `webpush()` parses
  `p256dh` as an EC public key. Any future reasoning about that pin has to start there.
- The bound is now `==48.0.1`, with a **ceiling** as well as a floor, and
  `tests/test_dependency_floors.py` asserts both with the reachability argument attached.
  49.0.0 publishes no macOS wheel at all — that is what `--only-binary=cryptography` in
  `ci-local.sh` is now waiting to catch.
- "No Intel wheel above 46.0.3" was not quite right: there is no *x86_64-tagged* wheel, but
  `universal2` carries an x86_64 slice and installs on Intel. Verified with the exact
  `--only-binary` invocation `ci-local.sh` uses.
- **The FastAPI upgrade was actually built and run, not estimated.** `fastapi 0.141.1 /
  starlette 1.6.0 / pydantic 2.13.4` gives 684/687. Do not repeat that exploration —
  Batch 61's row records the three failures and what each one costs.
- Of those three, the one that matters most is `test_wire_datetimes.py`: its model walk
  returns an **empty set** under pydantic 2.13, so the guard on Batch 43's 14:30-shown-as-13:30
  fix would go quiet rather than fail loudly. Rewrite it *and* prove it still catches the bug.
- react-router's open-redirect advisory is **not reachable**: the only data-built navigate
  targets are `/leagues/${league_slug}` and `_slugify` reduces a slug to `[a-z0-9-]`.

**Next:** Batch 60 — make the gate run what it claims to run.

## Batch 60 — Make the gate run what it claims to run
**Commits:** bc18bb1 · verified: `scripts/ci-local.sh` PASS (10 checks, 0 skips)

### Key facts for future sessions
- **`scripts/ci-local.sh` is the gate.** One command: pinned venv, clean `pgserver`,
  `alembic upgrade head`, full pytest, deployment-config assertions, frontend
  lint/typecheck/test/build. `SKIP_PROD_BUNDLE=1` drops only the Playwright smoke.
  It already existed before this batch — the batch was specified to build it.
- Its header comment already documented the FastAPI 403→401 `HTTPBearer` change that
  Batch 59's upgrade trial rediscovered, and records that it once cost nine days of
  local-pass/CI-fail. Read that file before touching the pins.
- Hand-run pytest **must start from a clean schema every time**. The pick-flow test and
  the e2e seeder both commit, so a reused cluster fails `test_seeds` on the second run.
  That cost time twice during this review before it was written down.
- **Still open (OPS-04):** the service worker gives `/api/v1/` GETs a 3-second
  `networkTimeoutSeconds`. Tight for mobile data against a service that can cold start;
  raising it trades a slower first paint for fewer outright failures. Left out of this
  batch because its scope boundary was tooling and docs only.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 62 — The half of the palette Batch 54 could not fix
**Commits:** 69c2f08 · verified: `scripts/ci-local.sh` PASS (10 checks) · axe 0 violations both themes

### Key facts for future sessions
- **`text-*` and `bg-*` no longer resolve to the same value for brand names.**
  `tailwind.config.ts` has a `textColor` scale pointing at `--*-ink`; `colors` still backs
  every fill, border and ring. Adding a new brand colour means adding *both*.
- **Never darken a fill to fix contrast.** That is the wrong half — it makes the near-black
  `--on-primary` sitting on it worse. `contrast.test.ts` asserts the fill pairing precisely
  so that move fails loudly.
- **A `tailwind.config.ts` change needs the dev server restarted.** HMR picks up `index.css`
  but not the config, so the old utilities keep being served — which looked exactly like a
  broken token for a while.
- `--text-inverse` pairs with an inverted *ground*, not with a brand fill. Text on a fill is
  `--on-primary`. An assertion confusing the two fails on a pairing the app never renders.
- axe measured immediately after a theme toggle catches `transition-colors` mid-flight and
  reports the outgoing palette's value. Let it settle before trusting a reading.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 63 — The product had no way to make an account
**Commits:** fbb0403 · verified: `scripts/ci-local.sh` PASS (11 checks) · browser end-to-end on the desktop and mobile paths

### Key facts for future sessions
- **A display name is now claimable by anyone, permanently.** It is globally unique, it is
  the login identifier, and `Profile` has no email or phone — so there is no way to prove
  who owns one and the only recovery is `pin/reset-request` paging a site admin. The
  uniqueness check deliberately **includes soft-deleted rows**: `deleted_at` must not
  release a departed member's identity to a stranger.
- **`PUBLIC_SIGNUP_ENABLED=false` closes the API but not the UI.** The "Create account"
  links on `/login`, `/join/:token` and `/welcome` stay visible and lead to a form that
  403s. Gating them needs `GET /api/v1/config` made unauthenticated, which reverses the
  decision written into `routers/config.py` ("nothing unauthenticated needs it, and it says
  a little about how the deployment is configured"). Left as an owner decision.
- **slowapi answers 429 with `{ error: ... }`, not `{ detail: ... }`.** Any client that
  reads `detail` silently turns a rate limit into a generic failure and invites a retry
  against a limit already spent. Fixed in `AuthContext.establishSession`; other `fetch`
  sites have not been audited for it.
- **`/register` is unreachable on an uninstalled mobile browser, by design.**
  `InstallPromptController` renders `BrowserOnboarding` full-screen over every route not in
  `SELF_MANAGED` (`/join/`, `/welcome`), so mobile installs first and registers inside the
  PWA. The onboarding copy now says exactly that. `next` does not survive the install.
- **A `public_open` league is now reachable by anyone with an account**, where before it
  was limited to members the operator provisioned. `the-coupon` is `private` and
  unaffected; the `test` league is `public_open`, and the 2026-08-20 decision to leave it
  in place was taken while account creation was closed.
- **This is the first batch whose Vercel/Railway gap is user-visible.** Pushing `main`
  deploys a "Create account" button that has no endpoint behind it until `/ship-prod` runs,
  and `/ship-prod` requires the commit to already be on `origin/main` — so the window
  cannot be avoided, only kept short. Batches 38 and 43 were built to tolerate that gap;
  this one cannot.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Fix — three member-reported bugs (claimed games, join, competition order)
**Commits:** 73245a7 · verified: `scripts/ci-local.sh` PASS (11 checks), 745 backend tests against real PostgreSQL

Not a `BUILD_PLAN` batch — reported from use, closed on the hotfix path like `b9e78fa`.

### Key facts for future sessions
- **Every production league is on `pick_scope = 'selection'`**, so "someone took Everton,
  I could still take the draw" was the configured rule, not a defect. The owner wants
  `fixture`. Switching is a **League Settings / PATCH** action, never raw SQL:
  `_apply_pick_scope_change` refuses the switch with `PICK_SCOPE_CONFLICT` when two members
  already share a pending game, and restamps pending rows — `picks.pick_scope` is what the
  partial unique index reads, so rows left on the old value are exempt from the new rule.
- **`zoe` cannot switch yet.** Zoe Waddell (HOME) and Craig (DRAW) both hold Everton v
  Crystal Palace on the 2026-08-22 round. That clash has to clear first. The other four
  leagues would take the switch today.
- **Ship the API before flipping the scope.** Production ran a slate that marked *every*
  selection on a game the caller holds as `mine`, which greys out the whole game client-side
  and locks the one member allowed to move between its markets out of doing so. Flipping
  first would have shipped that.
- **`mine` and "who blocks this" are two different questions.** `_selection_options` blocks
  only on a holder who is somebody *else* (matching `_claim_conflict`'s `holders - {player_id}`),
  and the exact holder of a selection outranks the fixture-level blocker. Reading the
  fixture blocker first hands the caller's own pick to the other member — which a league
  switched from `selection` to `fixture` will really have, since old rows survive.
- **A cache the UI gates on must be dropped, not invalidated.** `['leagues', 'mine']` is held
  for 60s and every coupon surface gates its query on `hasLeagues`; `invalidateQueries` keeps
  serving the stale list during the refetch, which is the "You're not in a league yet" empty
  state again. `dropStaleMemberships` uses `removeQueries` so the screen shows a skeleton.
- **Batch 64 (110f85b) never got a session-log entry or a STATUS mention.** Its close-out is
  incomplete; left alone here rather than reconstructed from the diff.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 64 — The card offered five games that were not being played
**Commits:** 5d2a964, merge 110f85b · verified: `scripts/ci-local.sh` PASS, 16 new backend
test cases, and a run against the live production card — 137 fixtures in, 8 marked off,
all 8 already removed by hand, nothing condemned that was on

Closed out retroactively: the code merged and reached production on 2026-08-22 before its
paperwork existed, which the preceding hotfix entry flagged.

### Key facts for future sessions
- **A postponement is invisible on date alone.** FotMob keeps a postponed match's
  *original* `utcTime`, so `status.cancelled` is the only tell. A date-only cross-check was
  written first, passed review, and cleared Rangers v St Mirren and St Johnstone v Celtic —
  the two most visible games on the card. The rule is `cancelled` **OR** date mismatch;
  either half alone is a silent failure that looks like success.
- **Bookmaker prices are not evidence a fixture is on.** Bet365 priced every postponed
  Premiership game. A price says *upcoming*, never *upcoming today*. Arguing from live odds
  cost a whole diagnostic pass.
- **`verify_slate` deliberately fails open, and the alias layer is why it can.**
  `team_matching`'s normaliser rates "RC Warwick" against "Racing Club Warwick" at 0.83
  where the naive token scorer written first gave 0.33 and would have deleted a real game.
  Both ends must clear `PAIR_THRESHOLD` 0.80 — that pair requirement is what makes the
  subset trap safe, since "Rangers" scores 0.95 against "Queens Park Rangers".
- **Hand-removing a fixture does not stick, and this is still true after Batch 64 for
  anything FotMob cannot see.** `sync_slate` only ever *adds* links and nothing persists the
  judgement — there is no status column on `fixtures`. Proved by running the real
  `refresh-slate` against production and rolling back: 10 of 12 hand-removed fixtures
  re-linked to both leagues, 90 minutes before the lock. FotMob carries neither NI
  Championship 1 nor the English non-league tiers, so a removal there is provisional until
  the round locks.
- **A production dry run spends the scheduler's own odds-api.io budget.** Anything routed
  through `fetch_slate` is a real metered call, not a probe. Two dry runs exhausted the
  100/hour, and the 13:00 `refresh-slate` then almost certainly hit the same 429 and
  no-opped — invisible except as `log.exception("slate refresh failed")`. Rebuild a `Slate`
  from `fixtures` rows instead; FotMob is unmetered and free to hit.
- **This batch never ran its own `/ship-prod` — it reached production as a passenger on
  `82a7a12`.** Confirmed on the running container, not inferred from git, because
  `railway up` uploads the *working directory* rather than the commit. That same property
  blocked the deploy earlier: a shared dirty worktree carrying another session's in-flight
  work would have shipped it, which is exactly what the clean-worktree preflight is for.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 65 — The week ends at the lock, and it should end at the results
**Commits:** a2a6dca (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 753 backend tests against real PostgreSQL), 9 new backend test cases

Two independent causes of one member report, fixed together because either alone leaves
the complaint half-standing.

### Key facts for future sessions
- **A correlated subquery is legal inside a PostgreSQL window `ORDER BY`.** That is what
  keeps `current_round_order` a self-contained bag of ORDER BY clauses: the in-play bound
  needs the owning league's window, and a *join* would have to be added to both call sites
  — where a future caller forgetting it produces a silent cross product rather than an
  error. Probed against pgserver before committing to the shape.
- **`span_days` needs `((a - b) % 7 + 7) % 7` in SQL.** PostgreSQL's `%` truncates
  toward zero, so a Friday-to-Monday window (`0 - 4`) computes as *minus four days* where
  Python's `%` gives three. The Python `SlateWindow.span_days` is correct; a naive
  transliteration into SQL is not.
- **The in-play bound is measured from the window's *close*, not the lock.** Measuring
  from the lock is right only for a league whose window is a single point — the default
  Saturday 15:00 — and drops a long-weekend league out of its own round while Monday's
  games are being played. Derived as `lock_offset + span_days + (end_minute -
  start_minute)` minutes after `locks_at_utc`, which needs no timezone conversion in SQL
  and is at most an hour out across a DST change.
- **Decision — the bound is 48 hours (`IN_PLAY_GRACE_MINUTES`), from the settlement
  cadence.** Settlement sweeps at 18:00, 20:00 and 22:00 daily, so two days is six
  consecutive sweeps: a round unresolved by then is stuck, not in play. Stated in
  `test_a_round_that_never_settles_stops_pinning_the_league` on both sides of the line.
- **Decision — `status` is not re-derived when a window edit restamps the instants.**
  Only `picks_open_at_utc` and `locks_at_utc` move. Flipping a round back from `open` to
  `scheduled` would tell members a round they may already hold a pick on has not opened,
  and it buys nothing: `pick_refusal` and `accepting_picks` both read the instant, and
  `open_due_gameweeks` re-labels on its next run.
- **Decision — the restamp is logged, not written into the audit row's `changes`.** That
  payload is a `{field: {from, to}}` map and a count does not fit it; Batch 69's console
  will render it. `league.claim_periods_restamped` carries the league and the round count.
- **Batch 27's "neither instant is ever re-derived" is now half-true and the docs said it
  in four places.** `models/gameweek.py`, `sync_slate`, `populate_cadence_rounds` and
  `test_round_population.py`'s header all asserted it. The surviving half is the
  load-bearing one: a *locked* round keeps the deadline it was claimed against.
- **Two existing tests asserted the old behaviour as their subject and were rewritten, not
  patched.** `test_refresh_rounds_rebuilds_a_moved_window_without_moving_the_announced_
  instants` held that a PATCH may not move an unlocked round's instants — now exactly
  backwards — and `test_slate_and_coupon_read_a_named_gameweek` defaulted to next week's
  round while last week's was still being played. Both now assert the new rule at the HTTP
  layer, which is where the member saw the defect.

**Next:** Batch 66 — a member who forgets their PIN has no way back in.

## Batch 66 — A member who forgets their PIN has no way back in
**Commits:** e765e75 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 769 backend tests against real PostgreSQL, 668 frontend), 16 new backend and
16 new frontend test cases, and the prod-bundle Playwright smoke extended to both new
routes

### Key facts for future sessions
- **This batch adds Alembic revision 016 — the only schema change in the 65→72 run.**
  `profiles.pin_hash` drops `NOT NULL`. No data moves and the constraint is only relaxed,
  so it is safe against a live database; the *downgrade* fails while any member is
  mid-reset, which is correct rather than a defect. Production has no restore point
  (owner's 2026-07-30 deferral), so the `/ship-prod` that carries this wants a written
  forward recovery plan.
- **The row's decision required the migration.** "Clears the credential and forces
  set-on-next-login" is only expressible if the column admits NULL. The alternative that
  avoids a migration — a sentinel value in `pin_hash` — puts an in-band signal in a
  credential column, which is how a "is this a hash or a marker?" bug gets written later.
  `Mapped[str | None]` makes mypy walk every read path instead.
- **A cleared PIN is claimable by whoever names the account, and that is inherent.** No
  secret passes through the admin, so nothing proves the caller is the member, and display
  names are on every leaderboard. Bounded rather than accepted: `PIN_RESET_CLAIM_WINDOW` is
  24 hours, read from the `player_pin_reset` audit row the reset already writes. **No new
  column** — `pin_hash IS NULL` already carries the state, and setting a PIN closes the
  window by making its own condition false, so it is single-use without a "used" flag.
- **The audit row is load-bearing, not decoration.** `/auth/pin/set` reads it for the
  window, so a reset that is not recorded is a reset that cannot be used. It has to be the
  *newest* row for that member: `pin/reset-request` writes the same `ActionType` at stage
  `requested`, so a member asking again must not re-open a window an admin did not.
- **A pre-existing league-admin PIN reset was found, and it was the defect the row
  describes.** `POST /leagues/{slug}/members/{id}/reset-pin` minted a temporary four-digit
  PIN, returned it for the admin to read out, skipped `is_weak_pin`, and **revoked
  nothing** — sessions opened under the old PIN kept renewing for thirty days past it.
  Nothing in `apps/web` called it and no test asserted `temp_pin`, so it was changeable
  without a deploy-window risk. It now shares `services/credentials.clear_pin`.
- **Decision — `temp_pin` stays in that response, always null, rather than being
  removed.** Vercel deploys the web app on merge while the API waits for `/ship-prod`, so
  a removed field breaks any client still reading it in the gap — the trap Batches 38, 41
  and 48 each recorded. It can go once both halves have shipped.
- **Decision — no new `ActionType` values.** `ALTER TYPE ... ADD VALUE` cannot be undone.
  The unlock endpoint therefore writes **no audit row at all** (structlog only) — it takes
  nothing away and grants no access, so that is the proportionate trade — and the site
  delete reuses `member_removed` with `target_table="profiles"` and `{"scope": "site"}`.
- **`from __future__ import annotations` breaks FastAPI dependency aliases.** Ten test
  modules failed at collection with `PydanticUndefinedAnnotation: name 'AdminUser' is not
  defined` until it was removed from `routers/admin.py`. No other router in the repo has
  it, which is now known to be the reason rather than a style choice.
- **The non-admin gate is asserted by walking `admin_router.routes`**, not by listing
  endpoints. A hand-written list only covers the routes somebody remembered to add to it —
  the same class of omission that left the league-admin reset unrevoked for ten batches.

**Next:** Batch 67 — what a round looks like once it has been played.

## Batch 67 — What a round looks like once it has been played
**Commits:** 7e28702 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 783 backend tests against real PostgreSQL, 675 frontend), 11 new backend
service tests, 3 new HTTP-level tests, 7 new frontend test cases

### Key facts for future sessions
- **Decision — the fixture-to-match link is resolved per read, not persisted.** The row
  left it open. Persisting adds a column *and* a backfill against a database with no
  restore point, and Batch 66 had already spent this run's one migration; resolving costs
  one extra query on a screen read a handful of times a week per league. The deciding
  argument was not cost: a stored link goes stale when an alias is **corrected**, and the
  alias layer is the part most likely to need correcting. If Batch 72 makes this hot, the
  shape to reach for is a cache in front of it, never a column.
- **`PAIR_THRESHOLD` and `pair_score` moved from `slate_verification` into
  `team_matching`.** Batch 64 put them where the first caller was. They are a judgement
  about club names, so they belong with the rest of the name matching; `pair_score` now
  takes four raw strings and normalises them itself, so a caller holding provider text and
  one holding a stored `normalised_name` cannot disagree about what was compared.
- **`CANDIDATE_WINDOW` is ±3 days, and the *order* of the two rules is what matters.**
  Name first, then date — never name score alone. A home-and-away pair inside one season
  matches both ends equally well, so "best score wins" would pick arbitrarily between two
  correct-looking answers. Batch 64 learned the same lesson from the other side, where
  choosing by name compared the card against a game six months out.
- **The ambiguity guard fired for real, in the test suite, on the first run.** Three
  finished "Arsenal v Chelsea" rows on one day, because `test_picks_flow.py` commits and
  the fixture pool is shared by `provider_event_id`, so every test in that module works
  against the *same* fixture row. `_record_played_match` now clears the competition's
  window before seeding. Worth knowing twice over: the guard works, and that module's
  non-hermetic seeding accumulates across tests in ways that look like product bugs.
- **UK-date comparison, not UTC-date.** A 23:30 UTC Friday kick-off is Saturday in UTC and
  Friday in London, and the two records store the same instant. Comparing raw dates would
  separate matches a member thinks of as the same night.
- **Only `finished` matches produce a scoreline, and only settled rounds ask for one.**
  Two gates, deliberately: an in-play match carries a partial score, and a partial score
  printed beside a settled pick would say the round is still moving. Batch 72 reads the
  in-play side and must not reuse this path unchanged.
- **All three new `CouponLeg` fields are optional with a default** — `points_awarded`,
  `home_goals`, `away_goals` — and there is a frontend test asserting the view still reads
  correctly when the deployed API sends none of them, which is exactly the Vercel-ahead-of-
  Railway window.

**Next:** Batch 69 — the operational half of the admin console. (Batch 68 is deliberately
out of the unattended run: it cannot start without an odds figure only the owner can
evidence.)

## Batch 69 — The operational half of the admin console
**Commits:** f6cd9b3 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 806 backend tests against real PostgreSQL, 687 frontend), 20 new backend test
cases, 3 new budget assertions in `test_request_budget.py`, 12 new frontend test cases

### Key facts for future sessions
- **The durable fixture status is NOT in this batch, and the row's own instruction is
  why.** `fixtures` has no status column, so an admin removal that survives the next
  `refresh-slate` needs a migration; the row says to decide before starting and split it
  out if it does. It does. FotMob still carries neither NI Championship 1 nor the English
  non-league tiers, so a hand-removal there is still undone by the next refresh — the gap
  Batch 64 recorded is unchanged and now needs a batch of its own.
- **The manual trigger shares the ad-hoc slate bucket rather than taking one of its own.**
  `PROVIDER_SLATE_FETCH_LIMIT` / `PROVIDER_SLATE_FETCH_SCOPE`, imported from
  `routers/leagues.py`, and there is a test asserting the two are the same object. Two
  `2/hour` limits against a plan with room for two is `4/hour` — the arithmetic error
  Batch 57 found on the pick path.
- **The bucket is denominated in slate walks, not presses.** One ad-hoc fetch is one walk
  of the thirty UK competitions, so `ManualJob.budget_units` is `ceil(provider_requests /
  30)` and discovery — which walks the whole `slate_horizon_weeks` horizon — is charged
  twice. Charging it once would let an admin spend sixty requests against a bucket sized
  for thirty.
- **`backup` and `football-backfill` are deliberately not offered as buttons.** Backup
  writes a file to the container's disk that an admin pressing from a phone cannot reach;
  the backfill is a one-off whole-season pull. Both stay in `run_scheduled.JOBS` for the
  cron entry point, so excluding them from the screen is a list, not a removal.
- **Manual settlement takes a scoreline, not market verdicts.** Both markets follow from
  a score, and asking an admin to say separately whether both teams scored is asking for
  arithmetic the code can do and for a mistake nothing would catch. The score becomes an
  `EventSettlement` and goes into `settle_gameweek` **unchanged**, so hand-entered and
  provider-supplied results write identical rows — asserted field by field on two
  identical rounds settled each way.
- **A settled round refuses a second settlement (409).** This corrects a round that is
  stuck, not one that is finished; rewriting a settled week would move points members have
  already seen. A genuine correction means editing the pick, which is a different act.
- **A path parameter named `key` was shadowed by a local `key = per_user_key(request)`,**
  and the endpoint returned the rate-limit key as the job name. Caught by an exact-equality
  assertion on the response body, which a looser `status_code == 200` would have missed.
- **Run mypy the way `ci-local.sh` runs it.** `mypy /abs/path/src` with `PYTHONPATH` set
  passed while `mypy src` from `apps/api` failed with two `comparison-overlap` errors: the
  409 guard narrows `gameweek.status` to "not settled", and `settle_gameweek` is precisely
  the call that can have changed it since. Re-read through `GameweekStatus(...)` after the
  call rather than trusting the narrowed attribute.
- **`enabled` and `running` are separate fields on the scheduler status on purpose.** The
  configured intent and the fact come apart in the one case worth knowing about — a
  container whose APScheduler never started — and the runbook's answer to that is the
  external cron, which the manual triggers are now a third route to.

**Next:** Batch 70 — what kind of picks people are actually making.

## Batch 70 — What kind of picks are people actually making
**Commits:** 6b58d9e (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 814 backend tests against real PostgreSQL, 695 frontend), 7 new backend
service tests, 1 new HTTP-level agreement test, 8 new frontend test cases

### Key facts for future sessions
- **Decision — void picks count in `picks_played` and not in the odds figures.** The row
  called this the decision to record. A postponed fixture is a round the member took part
  in, so it stays in the played count; it is also a bet that never ran, so its price is
  not folded into a cumulative total. `picks_priced` (won + lost) is the new denominator
  and is on the wire, so the difference is visible in the data rather than only in prose.
- **"Say so in the UI" is a component, not a comment.** `VoidDenominatorNote` renders
  wherever the figures render and renders *nothing* when the two denominators agree —
  printing it always would train readers to ignore it by the time it mattered.
- **`LONGSHOT_ODDS` is 3.00 and travels on every row as `longshot_odds`.** Chosen against
  the scoring rule rather than by taste: a winner scores `round(odds × 10)`, so one hit at
  3.00 outscores two at evens, and 3.00 sits clear of the 1.50-2.50 band most match-odds
  favourites occupy. Carried per row so the screen labels the split from the value it was
  computed with — the same reason `odds_degraded` travels with the odds.
- **`round(2.675, 2)` is `2.67`, not `2.68`.** 10.70 / 4 is not exactly representable as a
  float. Left as it lands rather than nudged, because the same rounding runs on every
  surface and they therefore agree with each other; the test says so in a comment so it is
  not "fixed" later.
- **The profile's own win-rate computation was deleted, not kept alongside.** It divided
  the same two numbers the aggregate already had, which is precisely how a profile and a
  leaderboard end up a rounding step apart. There is now one computation, in `Standing`.
- **Cumulative odds is a *sum*, not a product.** An accumulator's product over a season is
  a number nobody can read. The cross-league summary sums across leagues and divides by
  the summed `picks_priced` rather than averaging three per-league means, which would
  weight a one-pick league like a full season.
- **`test_cross_league_summary_shows_an_unpicked_round_and_no_leagues` asserts the summary
  as an exact dict.** That is a feature: adding a field to that response fails there
  immediately, which is the same surface the deployed web app meets before `/ship-prod`.
  Any future field has to be added to that literal deliberately.
- **Longest streak is deliberately absent.** It needs ordered history rather than an
  aggregate — a second query on a path that costs one — and the row ruled it out.

**Next:** Batch 71 — Football Stats opens expanded and shows part of the results.

## Batch 71 — Football Stats opens expanded and shows part of the results
**Commits:** bfeb0bf (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 818 backend tests against real PostgreSQL, 695 frontend), 3 new backend
service tests, 1 new HTTP-level test, and a read-only production measurement before and
after

### Key facts for future sessions
- **The measurement, because "looks fuller" is not a verification.** Read-only against
  production on 2026-08-23, via the `railway ssh` form in
  `docs/runbooks/launch-readiness.md`:
  - the whole table: **567 finished matches across 18 competitions**, every one inside the
    30-day lookback — so **ingestion is healthy** and this was *not* Batch 45's failure
    mode, which is the thing the row insisted be checked rather than assumed;
  - Saturday 2026-08-22: **145 matches across 17 competitions**;
  - what the shipped `limit=20` returned: **20 rows covering 6 of those 17**;
  - what the new 3-day window returns on the same data: **150 rows, all 17 competitions,
    3 days** — inside the 400-row backstop.
- **A flat row count was the wrong shape, not just the wrong number.** The screen groups
  by day and then by competition, so the unit of the answer has to be the day; raising 20
  to 200 would have moved the cliff rather than removed it. `football_recent_results_limit`
  is gone; `football_results_days` (3) and `football_results_max_rows` (400) replace it.
  Neither was ever set in any deployment config, so the rename ships as a code default.
- **"Days that have results", not calendar days.** Production's distribution runs from one
  match a day to 145; counting calendar days would empty the screen every midweek.
- **A naive-UTC timestamp needs `AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/London'`.** One
  conversion alone reads the naive value *as* London time — an hour wrong in summer, and
  it puts a 23:30 Friday kick-off on the wrong day. Same rule as `match_link._uk_date`.
- **The comment beside the old setting was itself the misreading.** It said "how many
  results a competition shows on the football-data screen"; it was a global cap across
  every pooled competition at once. Worth remembering that a wrong comment beside a right
  constant is how a defect survives a review.
- **Collapsing every table cost six other tests their premise.** They read rows and form
  from the Premier League card without expanding it, because it used to open by default.
  They now call an `openTable()` helper, which is the honest shape: none of them was
  asserting what the screen shows on arrival.

**Next:** Batch 72 — live scores while the round is being played.

## Batch 72 — Live scores while the round is being played
**Commits:** f05aaaa (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 827 backend tests against real PostgreSQL, 700 frontend), 9 new backend tests,
5 new frontend test cases

### Key facts for future sessions
- **The FotMob payload memo is per client and the client is process-wide.** A live read
  through it returns whatever the first caller of the day saw — a poll every ten minutes
  reporting half-time until the container restarts. `_league(..., refresh=True)` replaces
  the memo rather than bypassing it, so the fresher payload is what everything else sees
  and the request is not paid for twice. This is the single easiest way to have shipped
  this batch broken and had every test pass.
- **`Match.finished` was already the right gate, and nothing needed to change to respect
  it.** `sync_results` writes `finished = result.finished and home_goals is not None`, so
  an in-play `MatchResult` stores its running score and stays out of the results screen,
  the form line and Batch 67's settled scorelines — all three filter on `finished`. The
  model's own docstring predicted this use.
- **`fetch_live_scores` is non-abstract on the port with a `[]` default**, the pattern
  `fetch_fixture_states` set for the same reason: only FotMob can answer, and a provider
  that cannot must cost nothing beyond the scores it does not supply. api-football and the
  fake needed no change at all.
- **The poll is bounded by Batch 65's `in_play`, and that does a second job here.** It
  stops a round the provider never settles being polled forever — Batch 64's phantom
  Premiership round would otherwise have kept a competition fetched every ten minutes
  until May. `is_in_play` (single-row) is a *query*, not a Python check, because the grace
  is measured from the league's window and that lives on a row the gameweek does not carry.
- **A kicked-off match with no published score is skipped, not stored as 0-0.** Nil-nil is
  a real scoreline and "we do not know" is not.
- **Four live-score tests passed alone and failed in the suite.** The poll is deliberately
  global — every league's in-play round — and other modules in the suite *commit*, so
  their rounds were in play too. The tests now scope every assertion to the competition
  slug they created, and the `_Live` fake answers for one slug rather than for whatever it
  is asked about. Worth remembering as a class: "assert nothing happened" is not a safe
  assertion against a shared committed database.
- **`Badge` renders a block, so it cannot go inside a `<p>`.** Caught by React's
  `validateDOMNesting` warning in a test that was otherwise passing; the browser silently
  rewrites the markup.
- **`score_is_final` defaults to `true` on the wire and in the client.** Absent has always
  meant final, so the deployed web app reads a pre-Batch-72 API exactly as it always did.

**Next:** Batch 68 (needs an odds figure only the owner can evidence) and Batch 61 (the
FastAPI/starlette upgrade), both deliberately outside the unattended run.

## Batch 68 — Two rounds that were played before the app was watching
**Commits:** 18dfb9f (ff-merged, pushed) · shipped to production as Railway
`5922cf17-1767-4ab8-b225-9c0d2fd6b44f` · **backfill applied to production 2026-08-24
21:27 UTC** · verified: `scripts/ci-local.sh` PASS (11 checks, 846 backend tests), 19 new
backend test cases, a production dry run, and a 24-leg hand tally

The owner supplied both bet365 slips and both coupons on 2026-08-24, which unblocked the
batch. 26 picks written across three rounds; the league's 12 members all now show three
rounds played.

### Key facts for future sessions
- **A betting slip states its own return, and that is the check worth writing.** The
  8 August slip is £3.50 to return £1,660.24; the twelve fractions multiply to 474.28, so
  474.28 × 3.50 = £1,659.99 — 0.015%, bet365's own rounding. A single mis-converted
  fraction (19/20 as 1.90) is invisible on re-reading and moves a member's points by a
  whole unit. A second test asserts each stored decimal is its own fraction rounded to 2dp,
  because the product alone survives two errors that cancel.
- **Do the product check on the fractions, not on the stored decimals.** The 2dp values
  drift ~1.1% high over twelve legs (4/6 → 1.67 three times), which is `Numeric(6, 2)`
  doing its job. My first version compared the decimals and failed at a tolerance tight
  enough to be worth having.
- **Nothing invents an outcome.** Picks were written `pending` with no points and settled
  by `settle_gameweek` against the scorelines already in `matches`. So the coupons say what
  was picked and FotMob says what happened, and `points_awarded` is *computed*. Verified
  in production: 36 settled picks, **0 mismatches** against `round(odds × 10)`.
- **The rehearsal is the thing that made this safe.** Dumping production's candidate
  matches and running the real `pair_score`/`PAIR_THRESHOLD` locally resolved 25 of 26
  before anything was written — and found **every FotMob scoreline agreeing with the
  settled 15 August slip's own ✓/✗ marks**. Two independent sources, no disagreement.
- **A naive SQL preflight lied.** Joining `teams.name = fixtures.home` reported 20 failures;
  the two providers spell clubs differently ("Everton" vs "Everton FC"), which is the entire
  reason Batch 67's join is similarity-based. If a check contradicts a shipped matcher,
  suspect the check.
- **Scotland League Cup Group C is carried by nothing.** Aberdeen v Dundee, 15 August, has
  zero finished matches in production — it joins NI Championship 1 and the English
  non-league tiers on that list. Handled by `KNOWN_SCORES`, which may only *fill* a hole:
  the run raises if an entry there would override a score the store holds. Owner confirmed
  3-0 independently of the slip, so that value has two sources — better attested than the
  two 22 August prices.
- **Decision — rounds land with `number = NULL`.** 22 August is "Gameweek 1" and members
  were told so. `next_gameweek_number` would name these 3 and 4, putting a later number on
  an earlier date; renumbering 22 August would rewrite a name in use. The column is nullable
  for exactly this and nothing keys on it.
- **Running a module against production needs the container's own environment.** The prod
  database is IPv6-only, so it has to run inside Railway — and `railway ssh` gives neither
  the venv (`/opt/venv/bin/python`) nor `LD_LIBRARY_PATH`, so greenlet fails to load
  `libstdc++.so.6`. Take it from `/proc/1/environ` without printing it; that file holds
  every secret the service has.
- **Test isolation, again.** `apply()` originally committed, which broke the rollback
  fixture for every later test; it now flushes and the CLI commits, matching the codebase
  convention. And unscoped `select(Pick)` assertions passed alone and failed in the full
  suite. Third batch running to hit that — assume the suite is non-hermetic by default.

**Next:** Batch 61 — the FastAPI/starlette upgrade, the last unchecked row.

## Batch 61 — The framework upgrade, and the two decisions inside it
**Commits:** a5966af (ff-merged, pushed) · preceded by dfc5291, an unrelated blocker fixed
on its own branch first · verified: `scripts/ci-local.sh` PASS (11 checks, **845 backend
tests against real PostgreSQL, zero skips**, whole frontend, Playwright deep-link smoke)
on `fastapi 0.141.1 / starlette 1.6.0 / pydantic 2.13.4`

### Key facts for future sessions
- **`main` was already red when this started, and it was a clock bomb.**
  `test_the_settings_edit_restamps_an_unlocked_round_and_the_refresh_leaves_it` took
  `rounds[0]` and assumed it was still claimable. `upcoming_slate_dates` includes today by
  *date* alone, never by time of day, so on the league's own weekday after its lock the
  round is born dead and `rederive_claim_periods` correctly refuses to restamp it. The test
  used a TUESDAY window, so it failed Tuesdays after 18:45 London and passed the other 167
  hours. Fixed separately in dfc5291 — **run the gate before branching**, or a red baseline
  looks like your change.
- **The datetime-wire guard had lost every route, not just its models.** The batch row
  predicted "the model walk finds nothing under pydantic 2.13"; the real cause is FastAPI's.
  0.141 stopped copying an included router's routes onto the parent and mounts a private
  `_IncludedRouter`, so `isinstance(route, APIRoute)` matched **0 of 18** where it had
  matched 73. Batch 43's guard was walking an empty set — any response model added since
  would have been unguarded. `_api_routes` now descends by structure (`.routes`, else
  `.original_router.routes`), which works on both shapes and names no private class.
- **A guard that finds nothing looks exactly like a guard with nothing to report.** That is
  why the walk now asserts floors (>50 routes, >20 models) as well as three named models:
  the named-model check alone is satisfiable while having lost almost everything.
- **The 401/403 decision is "change nothing in the client", and the reason matters.**
  `lib/api.ts` keys on 401 alone; the anonymous case moves there for free and improves.
  **Do not widen that branch to 403** — a real 403 is a signed-in member reaching an admin
  route, and refresh-then-redirect would sign them out for asking. Safe because every
  bearer-protected call is under `<ProtectedRoute />`.
- **The status-constant rename could only land with the upgrade.** Both old names still
  resolve on starlette 1.6.0 but now raise `StarletteDeprecationWarning`; on the old pins
  the new names were an `AttributeError`. `routers/auth.py` carried a comment warning
  against this exact rename and now carries its reverse.
- **19 transitives disappeared and none were used.** 0.111 bundled python-multipart,
  email-validator, jinja2, orjson, ujson, fastapi-cli, typer and rich; 0.141 puts them
  behind a `[standard]` extra. `routers/auth.py` already documents that avatar upload reads
  the raw body *specifically* so python-multipart never became a dependency — that decision
  is what made this drop free.
- **`/ship-prod` is owed and this one actually matters.** Every previous drift this session
  was docs and tests. This changes the API's dependency tree and its anonymous-caller status
  code, and Vercel has already shipped the web half.

**Next:** Batch 73 — the round badge that reads `status` rather than time.

## Batch 73 — A round can say "open" while it is refusing picks
**Commit:** 72b1c4a (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks, **715
frontend tests across 48 files**, plus the whole backend and the Playwright smoke)

### Key facts for future sessions
- **`lib/coupon.ts` now holds the rule.** `pickRefusal(round, now)` mirrors the API's
  `pick_refusal` case for case, **including the ordering**: the opening gate is tested
  before the deadline, so a round that has not opened answers `PICKS_NOT_OPEN` rather than
  `PICKS_LOCKED` and is still restampable. A fixture that locked before it opened is what
  proved this — the component kept the round, correctly, and the fixture was the wrong
  thing. Mirror the order, not just the outcomes.
- **`status` is a lagging label, everywhere.** `open_due_gameweeks` moves
  `scheduled -> open`; the lock job moves `open -> locked`; neither runs backwards and both
  are hourly. **Any screen that branches on `status` is wrong for up to an hour at each end
  of the claim period.** Two were found this batch; assume more when touching a surface
  that labels a round.
- **The settings page was actively lying to admins.** Its copy said a change "never
  restamps a round that already exists" — correct when Batch 40 wrote it, false from Batch
  65, and it is the sentence an admin reads *while making that change*. **When a batch
  changes a rule, grep the UI copy for the old rule.** Batch 65 did not.
- **The same screen's round list had the same bug.** `upcoming()` filtered on `status`, so
  a round past its deadline was listed as one the setting still moves, when
  `rederive_claim_periods` bounds on `locks_at_utc > now` and skips it.
- **A time-aware filter turns date-blind fixtures into a clock bomb.**
  `LeagueSettingsPage.test.tsx` carries absolute August 2026 dates. They were safe only
  because the old filter ignored dates entirely; the new one would have passed on
  2026-08-25 and failed from 2026-08-29. Pinned to a fixed `NOW` — the same failure
  `dfc5291` had just removed from the backend, nearly reintroduced on the frontend.
- **`CouponPickPage` deliberately still states the rule a third time**, through
  `useCountdown`, because it must flip live while a member watches and it gates *submission*
  rather than a label. Both sides carry a pointer to the other. **Candidate follow-up:**
  fold it onto `pickRefusal` once someone is willing to test the submit path properly.
- **`PickShapeLine` lost the longshot split** (`avg 2.67 · 0 at 3.00+`) and is now
  `avg odds selected 2.67`. The split lives on `PickShapeGrid`, and the test proving the
  label tracks the league's configured line **moved there rather than being deleted** —
  the guarantee still applies on the surface that still shows it.

**Next:** Batch 74 — renumbering 2-1 Hibs' rounds and renaming three members.

## Batch 74 — Four rounds and three members in 2-1 Hibs are called the wrong thing
**Commit:** 9cf1686 (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks), 9 new
Postgres-backed tests · **script shipped, NOT applied to production**

### Key facts for future sessions
- **The production dry run is still owed.** `python -m src.backfill_names_and_numbers
  --dry-run`, then `--apply`, then **tell Craig, Marc and Lewis their new sign-in names**.
  `docs/backfills/2026-08-names-and-numbers.md` carries the pre-flight checklist.
- **A Supabase MCP timeout is not a database outage, and this session proved it.** Every
  query through the MCP timed out including `select 1`; `check-deploy-drift.sh` run
  immediately afterwards had the deployed API answering with `migration 016`, which it can
  only know by querying that same database. **Discriminate this way before reporting an
  outage** — the failure was confined to the MCP's connection path (probably the pooler
  endpoint rather than the direct DSN), while members were served normally throughout.
- **Renaming a profile releases its name more completely than deleting one does.**
  `auth.py:436` reserves names case-insensitively and **deliberately includes soft-deleted
  rows**, so a departed member keeps their name — but a rename leaves no row holding the
  old one, so "Craig", "Birch" and "Lewis" become registrable by anyone the moment this
  applies. Counter-intuitive and worth remembering before any future rename.
- **`display_name` is the login identifier**, matched exactly at `auth.py:228` and again at
  `auth.py:695` for PIN resets. The JWT subject is the player id, so a rename signs nobody
  out — it breaks their *next* sign-in instead, which is the failure nobody connects to a
  change made days earlier.
- **`(league_id, number)` carries no unique constraint** — `uq_gameweeks_league_starts_on`
  is the only one on `gameweeks`. Two rounds can both be "Gameweek 3" and only an explicit
  read catches it, which is why `_assert_season_reads` re-queries rather than trusting the
  plan it just applied.
- **This reverses Batch 68's numbering decision, and that decision was not wrong.** It
  weighed rewriting a name members had used against a season that read out of order; the
  owner has now weighed it the other way. Both comments say so, so neither reads as an
  oversight later.

**Next:** Batch 75 — removing the nightly `pg_dump` that writes to a tmpfs no volume backs.

## Batch 75 — The nightly backup pulls the whole database across the internet and throws it away
**Commit:** d012ebf (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **Production has no backup at all, and this batch made that visible rather than causing
  it.** `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md:105` records the owner's 2026-07-30
  deferral: no managed backup, no PITR. So `backup-restore.md`'s "Supabase managed
  backups are the source of record" is **aspirational, not current**. The nightly dump was
  never a fallback — it wrote to `/tmp` on a service with no volume — but it logged
  `"scheduled backup complete"` every night, which was a false signal. **The real gap is
  still open and is not this batch's to close.**
- **Removing it is not the egress fix and must not be cited as one.** 12 MB of database
  and this job put The Coupon near 1 GB/month against a 5 GB allowance, and Supabase meters
  egress **per organisation** — so the thing that spent the quota may be a different
  project entirely. That question is unanswered.
- **The schedule went; the capability stayed.** `python -m src.run_scheduled backup` runs
  the same coroutine. `services/backup.py`, `settings.backup_dir`, `test_backup.py` and the
  `backup_failed` / `backup_downloaded` enum values are all untouched — enum values are
  irreversible to remove, for the reason `unlock_player` records.
- **Assert a removed job absent, and pair the assertion.** `daily_backup is None` in
  `test_scheduler.py` plus "the manual path still resolves to the same coroutine" in
  `test_run_scheduled.py`. **Either alone passes the wrong change**: delete the coroutine
  and the first still passes; restore the nightly `add_job` and the second still passes.
- **A comment justifying a time can outlive the thing it referenced.**
  `prune_refresh_tokens` ran at 04:30 "after the 03:00 backup so a pruned row is in last
  night's copy". The hour kept a real reason — PITR holds that property *better*, since it
  recovers a row deleted at 04:30 to any second before it — rather than being left
  pointing at a job that no longer exists.
- **Launch-phase docs were deliberately not rewritten.** `LAUNCH_PLAN.md`, `L0` and `L3`
  describe the nightly dump; they are dated records of what was true then, the same
  convention Batch 74 applied to `invites.display_name_hint`.

**Next:** Batch 76 — notification triggers, and making the per-league mute actually work.

## Batch 76 — Notifications for the three moments that matter
**Commit:** dc4fe16 (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks), 11 new
Postgres-backed tests

### Key facts for future sessions
- **`send_notification` now takes `league_id`, and a trigger that forgets it fails
  silently.** The message still sends; only the mute goes unconsulted. That is why each
  trigger has an explicit assertion that it passes the kwarg — the behaviour is invisible
  otherwise. **Any new league-scoped notification must pass it.**
- **The mute gate fires only on an explicit `notification_muted = True`.** A missing
  membership does not suppress, deliberately, so Batch 76 is purely additive.
- **Testing the gate needs VAPID configured.** `send_notification` bails out at the top
  when VAPID keys are unset, so a test asserting `== 0` with them unset passes on the
  early return and proves nothing. Patch `settings.vapid_*` and
  `_send_push_sync` instead, and assert the push was not attempted.
- **`members_missing_picks` keeps its own mute filter on purpose.** Not belt-and-braces:
  `send_pick_reminders` returns who was *targeted*, so suppressing downstream instead
  would have that count claim a league was reminded when nobody was.
- **The reminder is hourly now and most runs match nothing** — that is the designed shape,
  which is why the empty case logs at debug. `gameweeks_due_a_reminder` selects
  `locks_at_utc` in `T-3h ± 30min`; an exact predicate cannot be hit by a cron.
- **Its eligibility mirrors `pick_refusal`, not `status == open`** — Batch 73's lesson, and
  it matters more here: with a 30-minute window, an hour of stale label loses the reminder
  rather than delaying it.
- **`submit_pick` builds its response before the alert block.** The block rolls back on
  failure and **a rollback expires every object in the session**, so serialising afterwards
  would lazy-load the committed row outside the transaction just discarded. Watch for this
  anywhere a post-commit side effect can roll back.
- **`moved` must be captured before `_apply_selection`.** The pick updates in place, so
  afterwards nothing distinguishes a claim from a move.
- **The pick alert sends inline**, matching `notify_member_joined` — up to eleven webpush
  calls on the submit path. Accepted, not overlooked: moving delivery off the request is a
  delivery-layer change. **Reach is 5 active subscriptions across 13 profiles**, so most of
  the 132-sends-per-round volume does not land today. Revisit before subscriptions grow.
- **`current_open_gameweeks` is now orphaned** — no caller in `src`. Kept because removing
  it forces timing rewrites in two tests whose subjects are elsewhere; its docstring says
  so and it is a fair removal candidate.
- **The picks-open trigger is dead code in 2-1 Hibs** until `pick_open_offset_minutes` is
  set on that league — its rounds are born `open` at discovery, so `open_due_gameweeks`
  never moves one. Correct for `the-coupon`, which carries the offset.

**Next:** `docs/BUILD_PLAN.md` has no unchecked batches. Owed: `/ship-prod`, and the
Batch 74 production run.

### Batch 74 — applied to production 2026-08-26
`--dry-run`, then `--apply` at 06:13:41 UTC, then an independent read to verify rather than
trusting the run's own output. 2-1 Hibs now reads Gameweek 1-4 in date order; the three
profiles carry their new names; **36 picks and 12 memberships untouched**. A second
`--apply` reported every row `==`, proving idempotency against production and not only in
a test.

- **`Craig`, `Birch` and `Lewis` are now free for anyone to register.** Renaming releases a
  name outright, unlike deleting a member — see the Batch 74 notes above.
- **The three have not been told.** Nobody was signed out (the JWT subject is the player
  id), so this only bites at the next sign-in or a PIN reset.
- The right path to production from this Mac is a **direct asyncpg connection**, DSN pulled
  from `railway variables --kv` into a file that never reaches context. **Not the Supabase
  MCP** — that points at `wc2026-predictor`, a different product, and its timeouts read
  exactly like a Coupon outage.

### 2026-08-26 — production configuration change, and Batch 77 written
The owner set `pick_open_offset_minutes = 720` on 2-1 Hibs. `rederive_claim_periods`
restamped Gameweek 4 correctly (`picks_open_at_utc = 2026-08-29 02:00`, twelve hours
before its 13:30 lock) and left `status = 'open'`.

- **This is Batch 73's scenario hit for real, and the fix held.** Picks were refused
  throughout (`pick_refusal` -> `PICKS_NOT_OPEN`, GW4 had zero picks) and the badge read
  "Not open". Nothing member-visible was wrong.
- **What was wrong was invisible.** `open_due_gameweeks` selects `status == scheduled`
  only, so it could never have fired Batch 76's picks-open notification for that round.
  A silent loss: refusal correct, badge correct, push absent.
- **`rederive_claim_periods`' own comment (`gameweek.py:208`) is half wrong.** It says
  status is not re-derived because `open_due_gameweeks` "re-labels on its next run". It
  does not. The *other* half of that comment is sound and must survive — a round holding
  picks must not be told it has not opened. That split is the whole design of Batch 77.
- **The owner asked for GW4 to be set to `locked`; that would have killed the round.**
  `pick_refusal` treats any status outside `scheduled`/`open` as terminally shut, so
  `locked` means unpickable forever, not "not open yet". Set to **`scheduled`** instead,
  guarded on `status='open'` + future `picks_open_at_utc` + zero picks. **"Locked" in this
  product is not the plain-English word** — check before honouring it.
- **The direct asyncpg route died mid-session.** The Supabase host is IPv6-only and this
  Mac's IPv6 route disappeared between the deploy and this change; `host` still resolved
  it while Python's `getaddrinfo` failed for both families. Fell back to `railway ssh`
  with a base64-uploaded script, which worked. **Both paths are worth keeping in mind —
  neither is reliably available.**

**Next:** Batch 77 — have `rederive_claim_periods` re-derive `status` where no picks exist.
