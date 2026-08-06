# The Coupon — build plan

## Product contract

The Coupon is a private weekly football accumulator game for friends.

- One global gameweek contains that Saturday's 15:00 fixtures.
- Each leaderboard member makes one `MATCH_ODDS` or
  `BOTH_TEAMS_TO_SCORE` pick.
- A selection can be held by only one member of a leaderboard.
- Odds are read from Betfair and frozen when the pick is submitted.
- Picks lock at 14:30 Europe/London.
- A winning pick scores `round(odds × 10)`; a losing pick scores zero.
- Standings are the season sum of settled pick points.
- The combined coupon multiplies every member's frozen odds.
- The product is for points and fun and never places a wager.

## Architecture

The FastAPI backend owns auth, leagues, the weekly slate, pick uniqueness,
settlement, standings, notifications, and scheduled jobs. PostgreSQL is the
source of truth. The React PWA consumes snake_case `/api/v1/` JSON.

`BetfairAdapter` contains the domain mapping for slate, prices, and market
results. `Betfair` implements the live HTTP client. `FakeBetfair` supplies the
same catalogue and market-book shapes for deterministic tests.

## Build batches

This checklist is the batch source of record. Close-out ticks a batch only
after the user invokes `/phase-closeout <N>`.

- [x] **Batch 1 — Application spine** ✅ 2026-07-25 — PIN auth, profiles,
  notifications, leagues, memberships, join requests, invites, scheduler
  framework, and baseline migration.
- [x] **Batch 2 — Betfair adapter** ✅ 2026-07-25 — live client, shared domain
  mapping, canned implementation, retries, prices, and settlement.
- [x] **Batch 3 — Pick and scoring engine** ✅ 2026-07-26 — gameweeks, fixtures,
  picks, both uniqueness constraints, odds scoring, standings, and combined
  coupon.
- [x] **Batch 4 — Scheduler** ✅ 2026-07-26 — slate refresh, reminders, locking,
  settlement, and shared live-session lifecycle.
- [x] **Batch 5 — Frontend reshape** ✅ 2026-07-26 — weekly pick UI, combined
  coupon, home, standings, and current API binding.
- [x] **Batch 6 — Verify + rebrand pass** ✅ 2026-07-26 — run every verification gate below,
  remove inherited product naming and unused surfaces, replace inherited
  documentation and assets, and delete the temporary handoff document.
- [x] **Batch 7 — Odds provider replacement** ✅ 2026-08-04 — replace the Betfair Exchange
  with `odds-api.io` priced by Bet365, for full UK coverage including the
  Scottish lower divisions the Exchange does not price. Extract a
  provider-neutral port, derive settlement from scores rather than Exchange
  runner status, cache odds against the request-path rate limit, and migrate
  the provider-named columns. Scope and evidence:
  `docs/adr/0002-replace-betfair-exchange-with-odds-api-io.md`.

Batches 8 onward come from the owner's 2026-08-05 feedback pass. Three of those
points are already satisfied and need no batch: joining by invite code, changing
a pick until lock, and showing combined plus per-leg odds on the coupon.

The bracketed model on each row is a recommendation sized to that batch's blast
radius, not a rule — `/next-batch-prompt` still leaves the choice to the user.

- [x] **Batch 8 — League-aware coupon** ✅ 2026-08-05 *(Sonnet)* — bind the coupon,
  combined-acca, and home pages to the active league rather than the hardcoded
  `DEFAULT_LEAGUE_SLUG` in `apps/web/src/lib/api.ts`. Small, but every
  per-league feature below is wrong without it, so it goes first.

- [x] **Batch 9 — Coupon presentation** ✅ 2026-08-06 *(Sonnet)* — group the slate by
  competition then kick-off with each competition collapsible; a per-user
  decimal/fractional odds preference; the full member roster for a gameweek
  showing each member's pick and who has yet to pick; and a fixture-level
  "already picked" marker alongside the existing per-selection one. Backend is
  one endpoint exposing `members_missing_picks` and a profile preference column;
  the rest is `CouponPickPage`, `PickCard`, and `formatOdds`. Fractional odds
  are display only — prices stay `Numeric(6, 2)` and scoring stays
  `round(odds × 10)`.

- [x] **Batch 10 — One pick per fixture** ✅ 2026-08-06 *(Opus)* — replace
  `uq_picks_league_gameweek_selection` with a `(league, gameweek, fixture)` key
  so claiming any market on a game takes the whole game, behind a per-league
  setting that keeps the selection-level rule available. Supersedes the "a
  selection can be held by only one member" bullet in the product contract.
  Migration plus the pre-check in `routers/picks.py`. Note this shrinks the pick
  pool roughly fivefold, which matters against a 15-member roster.

- [x] **Batch 11 — Daily slate pre-fetch** ✅ 2026-08-06 *(Opus)* — split fixture discovery
  from pricing. A daily job walks the coming week's fixtures into `fixtures`;
  odds stay on demand behind a cache that tightens as lock approaches, because a
  price is frozen the moment a member picks and someone picking on Tuesday still
  needs a live one. Foundation for Batches 15 and 16, which cannot afford their
  request budget without it. Must stay inside 100 requests/hour and 500/day.

- [x] **Batch 12 — Gameweek history** ✅ 2026-08-06 *(Sonnet)* — a gameweek list endpoint and
  a `gameweek_id` parameter on the slate and coupon reads, replacing the
  hardcoded `latest_gameweek` in `routers/coupon.py` and `routers/gameweek.py`,
  plus navigation so past scores and every member's picks are browsable the way
  a fantasy-football season is. The rows are all retained; nothing needs
  backfilling.

- [x] **Batch 13 — Profile** ✅ 2026-08-06 *(Sonnet)* — port `PlayerProfilePage` from
  `~/wc_2026_predictor/apps/web/src/pages/`, add a settled-pick history
  endpoint, and surface win rate from the `picks_played` / `picks_won` figures
  `standings()` already computes. Decide career-wide versus per-league framing:
  picks are league-scoped, so a member in three leagues has three records.

- [x] **Batch 14 — Per-league gameweeks** ✅ 2026-08-06 *(Opus)* — the architectural change
  the configuration work depends on. `gameweeks` is global and unique on
  `saturday_date`, so two leagues cannot play different fixtures. Split it into
  a shared fixture pool and a per-league gameweek selecting from that pool, and
  lift the hardcoded window — `KICKOFF_HOUR`, `is_saturday_kickoff`,
  `_SATURDAY`, `_LOCK_HOUR` / `_LOCK_MINUTE`, `upcoming_saturday` — into
  per-league configuration. Supersedes the "one global gameweek" bullet in the
  product contract.

- [x] **Batch 15 — League admin configuration** ✅ 2026-08-06 *(Opus)* — admin surfaces on
  Batch 14: fixture window (the 15:00 Saturday slate, or an arbitrary range such
  as Friday 19:00 to Monday 22:00), competition selection both individually and
  by group ("all UK leagues"), the offered market set, and ad-hoc gameweeks for
  rounds like Boxing Day — all settable at league creation and editable
  afterwards, gated by `LeagueAdminDep`. Competition scope is bounded by the
  provider's rate limit rather than by preference: the slate costs one `/events`
  request per competition, so "every league the API carries" is 728 requests
  against a 100/hour budget and is not affordable on the free plan. Markets are
  a PostgreSQL enum, so widening the set is a migration, not configuration
  alone.

- [x] **Batch 16 — Football data** ✅ 2026-08-06 *(Opus)* — real league tables, previous
  results, and recent form, both as their own section and inline on the pick
  screen. Needs a second provider, because odds-api.io publishes no standings;
  `teams` / `matches` / `standings` tables; ingestion on the Batch 11 schedule;
  a season backfill; and a name-reconciliation layer between the two providers'
  team spellings, since `fixtures.home` / `away` are free text and there is no
  `Team` table. Our own fixtures cannot supply a table: the slate has only ever
  stored Saturday 15:00 UK kick-offs, so Sunday, Monday, and midweek games were
  never fetched. Scores are not persisted at all today — `settle_gameweek`
  consumes the result and writes only pick status and points. The largest batch
  on this list.

- [x] **Batch 17 — Betslip export spike** ✅ 2026-08-06 *(Opus)* — timeboxed investigation
  into pushing a completed coupon to a bookmaker account, Bet365 first, ending
  in an ADR rather than a feature. Bet365 publishes no betslip API; the likely
  finding is a shareable betslip link for books that support one. Independent of
  every batch above, and to be weighed against the "never places a wager"
  contract bullet.

Batches 18 onward come from the owner's 2026-08-06 feedback pass, reconciled
against the code before being written up. Two of the five reported points were
not what they looked like: the competition picker is built and reachable but
starved of data (Batch 21), and the missing league label is the *mini-league*
name, not the football competition — the owner confirmed the reading, and the
competition is already on every leg's fixture row. Batch 18 is not from the
feedback pass; it is a live production defect found while reconciling it.

- [ ] **Batch 18 — Production static assets** *(Sonnet)* — the `vercel.json` rewrite
  sends everything that is not `assets/`, `icons/`, `favicon`, `robots.txt`,
  `manifest.webmanifest`, `workbox-` or `sw.js` to `index.html`, but the app's
  static files do not match that list. The four self-hosted `fonts/*.woff2`, all
  five `icon-*.png`, `apple-touch-icon.png` and `coupon-icon.svg` live at the
  document root, so production serves HTML for every font and every PWA icon —
  the app falls back to system fonts and the installed-app icon is broken.
  `icons/` is excluded and no such directory exists. All eleven are in the built
  precache manifest (verified in `dist/sw.js` after `vite build`), so the service
  worker stores the HTML too and the fault survives into the installed app rather
  than being a first-load miss. Broken in production now, which is why it goes
  ahead of the feedback items; the fix is the rewrite's negative lookahead, and
  the gate is that each of the eleven returns its own content type.

- [ ] **Batch 19 — Coupon page crash** *(Opus)* — the owner reports the coupon page
  rendering `ErrorBoundary`'s "Something went wrong". Diagnosis is the batch:
  reconciliation cleared the whole render path — `CouponPickPage`,
  `CouponCombinedPage`, `CouponSubNav`, `GameweekNav`, `MemberRoster`,
  `PickCard`, `FormLine`, `CombinedAccaView`, `lib/coupon.ts`,
  `useGameweekHistory` — and the API models behind it, where the fields the
  frontend dereferences without a guard are all non-nullable (`CouponLeg.odds`,
  `Coupon.combined_odds`, `Standing.form`). Typecheck, 217 Vitest and a
  production build all pass, so the throw is not in the source and this cannot be
  specified as a code change yet. Start by capturing the console — the boundary
  already logs `render failed` with the component stack — plus the failing URL
  (`/predictions` or `/predictions/coupon`) and whether a hard reload clears it.
  Leading hypothesis is a stale lazy chunk after a redeploy: every route is
  `lazy()`, the service worker calls `skipWaiting()`, `clientsClaim()` and
  `cleanupOutdatedCaches()`, so a tab held open across a deploy requests a
  deleted chunk and the rejected `import()` surfaces at exactly that boundary. If
  that is confirmed the fix is chunk-error recovery, not coupon code, and it
  protects every route rather than this one. If the console says otherwise, the
  console wins. Timeboxed like Batch 17: if it cannot be reproduced, the
  deliverable is an ADR and a reload path, not a speculative patch.

- [ ] **Batch 20 — League identity, profile and invite wayfinding** *(Sonnet)* — three
  reported gaps, all of them surfaces that exist but cannot be reached or read.
  The home page never names the league it is showing: `DashboardPage` binds every
  query to `LeagueContext`'s `activeSlug` — last-viewed, else the member's first —
  so a member in several leagues cannot tell whose coupon, pick and standings
  they are looking at, and `LeagueSwitchStrip` only ever renders on
  `LeaderboardPage`. The name is already in context beside the slug; decide
  whether it labels the combined-coupon card alone or the page header, which
  covers all three cards. There is no route to one's own profile: `PlayerProfilePage`
  is league-scoped at `/leagues/:slug/players/:playerId` and reachable only by
  tapping someone else on the leaderboard, the `TopBar` avatar menu holds only
  Settings and Log out, and the mobile More sheet holds the same two — a
  self-profile entry needs a slug, and `activeSlug` is the one to use. And
  `LeagueAdminInvitesPage` and `LeagueJoinRequestsPage` are both fully built,
  routed, and linked from nowhere in the app; both want buttons in
  `LeagueActionsMenu` behind its existing `isAdmin` guard. Frontend only, no API
  change. While here: `SettingsPage` links to `/about`, which has no route and no
  page, so the catch-all bounces it to home.

- [ ] **Batch 21 — Competition catalogue from the provider** *(Opus)* — Batch 15 shipped
  per-competition selection and it works, but the picker is empty for most
  leagues, so "all UK leagues" is the only usable choice. The cause is the
  catalogue, not the UI: `GET /{slug}/competitions` builds `available` from
  `SELECT DISTINCT competition_id, competition FROM fixtures`, which is only what
  discovery has already pooled, so a league whose slate has never run has nothing
  to tick and gets the "appears once the first slate has been fetched" message.
  Source it from the provider instead. This does not run into Batch 15's rate
  limit, which is about the *slate* costing one `/events` per competition: the
  catalogue is `_all_leagues()`, a single `/leagues?sport=football` call already
  cached per client, and `_is_uk()` already narrows it to the four home nations —
  roughly thirty competitions. The cost is the port. `OddsProvider` exposes no
  competition listing, and adding one as an `@abstractmethod` touches every
  implementation — `OddsApiProvider`, `BetfairAdapter`, the `CachingOddsProvider`
  decorator, which must delegate, and the stubs in `test_odds_session.py` and
  `test_odds_cache.py`. A non-abstract default returning `[]` confines the change
  to `OddsApiProvider` at the cost of a silently empty picker on any other
  provider; pick one deliberately. Keep unioning the stored selection in, so a
  competition that has dropped out of the provider's list still shows as ticked,
  and keep the endpoint free of an upstream request on the common path.

## Verification

- **Backend:** pytest covers both pick-uniqueness directions, odds scoring,
  combined-odds multiplication, the canned Betfair adapter, locking, and
  settlement. Ruff check/format and strict mypy pass.
- **Database:** `alembic upgrade head` succeeds on clean `pgserver` PostgreSQL;
  the baseline tables exist and no legacy tables exist.
- **Frontend:** Node 20 production build, `tsc --noEmit`, and Vitest pass.
- **Browser end-to-end:** against a production preview, real scratch PostgreSQL,
  and `FakeBetfair`, seed a leaderboard and members; show the Saturday slate;
  submit two members' picks; show a third member blocked from a taken
  selection; lock; settle canned results; verify updated standings and the
  combined coupon; save screenshots.
- **Live Betfair:** the owner alone uses their session to confirm a real Saturday
  slate and prices. This is not an agent action.

## Launch gates

Fresh Supabase, Railway, Vercel, domain naming, real league membership, and any
non-interactive Betfair certificate are separate launch work. The audited,
ordered launch checklist is in `docs/LAUNCH_PLAN.md`.
