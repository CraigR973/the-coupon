# The Coupon — build plan

## Product contract

The Coupon is a private weekly football accumulator game for friends. A member
may play in several leagues at once, and every rule below is per-league.

- A league owns its rounds. Each round covers that league's weekly fixture
  window — a range in Europe/London, defaulting to the single Saturday 15:00
  kick-off the product started with.
- Each member of a league claims one selection per round.
- A claim is unique within its league. Under `selection` scope it takes one
  `(fixture, market, outcome)`; under `fixture` scope it takes the whole game.
- A league offers `MATCH_ODDS`, `BOTH_TEAMS_TO_SCORE`, or both, across all UK
  competitions or an explicit subset of them.
- Picks lock `lock_offset_minutes` before the window opens — 14:30 under the
  defaults — and open `pick_open_offset_minutes` before it, or as soon as the
  round is discovered when the league announces no opening.
- Odds are read from the configured provider and frozen when the pick is
  submitted.
- A winning pick scores `round(odds × 10)`; a losing pick scores zero; a void
  pick scores nothing rather than counting as a loss.
- Standings are the season sum of settled pick points within a league. Across
  leagues, points and win rate aggregate; rank does not.
- The combined coupon multiplies every member's frozen odds for one league's
  round.
- The product is for points and fun and never places a wager.

## Architecture

The FastAPI backend owns auth, leagues, the weekly slate, pick uniqueness,
settlement, standings, notifications, and scheduled jobs. PostgreSQL is the
source of truth. The React PWA consumes snake_case `/api/v1/` JSON.

Odds sit behind the provider-neutral `OddsProvider` port
(`services/odds_provider.py`). `OddsApiProvider` is production — odds-api.io
priced by Bet365, per ADR 0002 — with `BetfairAdapter` / `Betfair` retained as a
fallback and `FakeBetfair` supplying deterministic catalogue and market-book
shapes for tests (`ODDS_PROVIDER=fake`). Football tables and results come through
a second port, `FootballDataProvider`, live as `ApiFootballProvider` and canned as
`FakeFootballData`.

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

- [x] **Batch 18 — Production static assets** ✅ 2026-08-06 *(Sonnet)* — the `vercel.json` rewrite
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

- [x] **Batch 19 — Coupon page crash** ✅ 2026-08-06 *(Opus)* — the owner reports the coupon page
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

- [x] **Batch 20 — League identity, profile and invite wayfinding** ✅ 2026-08-06 *(Sonnet)* — three
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

- [x] **Batch 21 — Competition catalogue from the provider** ✅ 2026-08-06 *(Opus)* — Batch 15 shipped
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

Batches 22 onward come from the owner's 2026-08-15 feedback pass, reconciled
against the code before being written up. One of those points needs no batch:
the pick screen and the combined coupon stay separate surfaces, because they
answer different questions at different moments and merging them would put a
hundred-fixture slate above the thing you read after lock.

A second point was written up as needing none, and that was wrong. Each club's
position and form beside a fixture is already built and shipped by Batch 16, and
both surfaces render blank only for want of ingested data — which read as an
owner action rather than work. Sealing `FOOTBALL_API_KEY` on 2026-08-15
disproved it: the key is valid and the ingestion still writes nothing, because
it cannot complete against a per-minute ceiling nobody had recorded. That is
Batch 28, and the congestion question this paragraph used to defer cannot be
answered until it lands, because until then there is no data to look at.

- [x] **Batch 22 — Wayfinding and layout** ✅ 2026-08-15 *(Sonnet)* — four reported gaps, all
  frontend-only with no API change. `FootballPage` is reachable only from
  `CouponSubNav`, so a member who never opens the coupon never learns it exists;
  `TabBar` has room for it in `PRIMARY` or in the More sheet. `PageHeader` wraps
  its `action` slot in `shrink-0`, so `LeagueActionsMenu`'s own `flex-wrap` never
  engages and six buttons run off the side of a phone — the wrapper is the fix,
  not the menu. The Members button is shown to every member but points at
  `/leagues/{slug}/admin/members`, whose only non-list content is promote, demote
  and remove, all admin-gated: put it behind `isAdmin` and let the leaderboard be
  the member list, since it already is one. And `CouponLeg` and `SettledPick`
  both already carry `competition`, which neither `CombinedAccaView` nor
  `PlayerProfilePage`'s `HistoryRow` renders.

- [x] **Batch 23 — Slate ordering and collapse** ✅ 2026-08-15 *(Sonnet)* — the slate opens
  every competition expanded and orders them by earliest kick-off
  (`groupByCompetition` in `CouponPickPage`), so a hundred-fixture card means
  scrolling past whatever happens to lock first to reach the Premier League.
  Collapse every group by default and order by the league pyramid: England's top
  four tiers, then Scotland's top four, then each nation's remaining league
  tiers highest to lowest, then everything else. Order on
  `fixtures.competition_id` — the provider's slug — and not on the display name,
  which carries sponsors and has already changed under this codebase once; the
  slug is on the model and needs adding to `FixtureSlate`.

  Cups have no tier, so the pyramid cannot place them, and neither can it place
  a competition the table does not name. Both fall to a second sort: **most
  fixtures on this slate first**. A thirty-two-tie cup round outranks a
  four-tie one, which is the order a member scanning the card wants, and it
  needs no catalogue — the count is already in hand from the grouping. It also
  means an unrecognised competition degrades into a sensible position rather
  than blocking, so the provider's roughly thirty UK competitions never have to
  be enumerated up front.
  While in `routers/gameweek.py`: `GameweekMember` is the one pick-bearing
  response with no `competition` field, which is why `MemberRoster` can show
  another member's selection without saying which league it came from.

- [x] **Batch 24 — Share the coupon as text** ✅ 2026-08-16 *(Sonnet)* — the one thing ADR 0004
  left standing when it rejected betslip export. Render the combined coupon's
  legs, selections, prices and combined odds as plain text a member can copy into
  a group chat and type into whatever book they use, then share that book's own
  link back themselves. No bookmaker integration and no outbound bet link, so
  none of the gambling-advertising and age-gating obligations that decided the
  ADR are incurred. Frontend only: `CombinedAccaView` already holds every field
  and `GET /leagues/{slug}/coupon` needs no export-shaped addition. The ADR's
  second wall still applies to the text itself — `odds_at_pick` is frozen, so the
  combined figure is historical and the copy must say so rather than implying the
  acca prices at that number today.

- [x] **Batch 25 — Gameweek results** ✅ 2026-08-16 *(Sonnet)* — a settled week is reachable
  today only by stepping back through `GameweekNav` one round at a time, and only
  once two rounds exist, which is not how anyone looks up what happened last
  week. Add a results view to the coupon tab listing every settled gameweek with
  its winner, points and combined-coupon outcome, each row opening that week's
  coupon; the reads are already parameterised by `gameweek_id` from Batch 12, so
  this is mostly presentation over endpoints that exist. Reach it from the
  profile as well — `PlayerProfilePage` lists a member's settled picks but never
  says how the week went around them. Previous *football* results are explicitly
  not this: they stay in the Football tab where Batch 16 put them.

- [x] **Batch 26 — Multi-league home and profile** ✅ 2026-08-16 *(Opus)* — the home page and
  the profile each answer for one league at a time, which is wrong for a member
  in several: `DashboardPage` renders one pick, one coupon peek and one standings
  card for `activeSlug`, and `TabBar`'s My profile silently binds to the same
  slug. Port the shape from `~/wc_2026_predictor`'s
  `GET /api/v1/me/cross-league-summary` in `routers/me.py` — `avg_rank`,
  `total_points`, and a `per_league` breakdown of slug, name, rank and member
  count, in fixed queries rather than one per league. One adaptation: wc2026
  reads rank from a `LeaderboardSnapshot` table this codebase does not have, so
  rank comes from `scoring.standings()` per league instead. Home becomes a card
  per league carrying that league's pick and standing, one tap to that week's
  coupon.

  For the profile, split the question by figure rather than answering it once.
  Batch 13 rejected career-wide framing wholesale, and that was too broad:
  **points and win rate aggregate cleanly** — every league scores
  `round(odds × 10)` off the same scale, so a season total across three leagues
  is a real number — while **rank does not**, because first of three and first
  of fifteen are not the same achievement. wc2026 already solved exactly this
  and the guard is worth porting with the endpoint: `_MIN_MEMBERS_FOR_AVG = 3`
  excludes leagues too small to rank against from the average, so a two-person
  league cannot flatter it.

  So: `TabBar`'s My profile stops binding to `activeSlug` and goes to a new
  career-scoped route carrying the aggregate header and a per-league breakdown
  that links into each league's own profile. The existing
  `/leagues/:slug/players/:playerId` stays exactly as it is and stays reachable
  from that league's leaderboard, because clicking a name in a table should show
  that member's record *in that table*. Settled-pick history stays league-scoped
  too — a pick's meaning is partly who else could have taken it, which is a
  league-local fact.

- [x] **Batch 27 — Configurable pick-open time** ✅ 2026-08-16 *(Opus)* — let a league admin
  choose when picks open for a round. No such concept exists: a gameweek is
  created `open` and only `locks_at_utc` is stored, so picks become claimable
  whenever `run_refresh_slate` next runs (09:00 and 13:00 daily), which is
  neither announced nor the same each week. Beware the naming collision —
  `SlateWindow.opens_at` in `services/odds_provider.py` is when the *fixture
  window* opens (Saturday 15:00, the thing locking is measured back from), not
  when picks open; this is a third instant and needs its own name. Add it to
  `gameweeks` derived from a per-league offset stored beside
  `lock_offset_minutes`, gate `POST /leagues/{slug}/picks` on it, and put the
  control in `LeagueSettingsPage` behind `LeagueAdminDep` with the rest of the
  Batch 15 window settings. `GameweekStatus` needs a state for a round that
  exists but has not opened — `open` currently means both. Discovery and pricing
  must stay on their existing schedule: this gates when members may *claim*, not
  when fixtures are fetched, and coupling the two would put Batch 11's request
  budget under a configuration knob.

- [x] **Batch 28 — Football ingestion rate limiting** ✅ 2026-08-15 *(Sonnet)* — **run this
  first, ahead of Batch 22.** The football provider is configured and its key is
  valid, and the ingestion still writes nothing: `sync-football` run against
  production on 2026-08-15 returned
  `carried=0 competitions=0 matches=0 table_rows=0`. API-Football's free plan
  enforces **10 requests per minute** as well as the 100 per day that ADR 0003
  is built around, and `sync_football_data` fires its two-requests-per-competition
  loop with no pacing, so the minute allowance is gone in seconds. The failure is
  hard rather than transient because of how the limit arrives: api-football
  reports it as **HTTP 200 carrying an `errors` object**, so the 429-and-5xx
  backoff in `_request` never engages, and `_raise_for_errors` sorts `rateLimit`
  into the unretried `FootballDataAPIError` branch beside genuine faults — the
  same function already special-cases the daily-quota key, so the shape of the
  fix is established. Add `rateLimit` to the transient set so it backs off, and
  pace the sweep below ten a minute: at two requests per competition that is
  roughly a twelve-second gap, putting a thirty-competition sweep near six
  minutes, which is fine for a 06:30 job and is precisely why the sweep belongs
  on the scheduler rather than in an interactive run. Correct ADR 0003 while
  here — it records only the daily ceiling, and recording one of two limits is
  what produced this. Until this lands, the Football tab and the pick card's
  position-and-form strip are both dark, so Batch 22's football wayfinding and
  the deferred congestion judgement have nothing to act on.

- [x] **Batch 29 — League identity on the coupon tab** ✅ 2026-08-17 *(Sonnet)* — the Coupon tab
  answers for one league and never says which. All four surfaces —
  `CouponPickPage`, `CouponCombinedPage`, `ResultsPage`, `FootballPage` — route
  without a slug (`/predictions/*` in `App.tsx`) and bind to `LeagueContext`'s
  `activeSlug`, while their `PageHeader`s read "This week's coupon", "Combined
  coupon", "Results" and "Football", and `TopBar` carries only the brand and the
  member's name. A member in three leagues cannot tell whose slate they are
  picking from, and a mis-bound tab is indistinguishable from a correct one — the
  lock countdown, the member roster and the taken-selection markers all describe
  a league the page never names. This is the Batch 20 complaint again: that batch
  fixed it for home and left the coupon alone, and Batch 26 then rebuilt home
  around a card per league without touching these four.

  Two further faults let the binding drift. `LeagueSwitchStrip` renders only on
  `LeaderboardPage`, so the tab has no switcher; and `selectLeague` is called from
  exactly one place — `DashboardPage`'s `openCoupon` — so tapping the Coupon tab
  directly lands on whatever was bound last. Worse, the strip writes the recency
  store but never calls `selectLeague`, and `activeSlug` prefers the in-memory
  `selectedSlug` over that store, so opening league B's coupon from home, browsing
  league A's leaderboard, then tapping Coupon returns to B without saying so. The
  store is only consulted again on a cold start.

  Name the league in the header of all four surfaces (the name is already in
  `LeagueContext` beside the slug), render `LeagueSwitchStrip` above
  `CouponSubNav`, and have the strip bind through `selectLeague` rather than
  writing recency alone — which fixes the leaderboard case as well. Frontend only,
  no API change and no route change: explicit slug routes are Batch 30 and this
  batch should not pre-empt them.

  While here, close the fallback that hides behind all of this. `activeSlug`
  returns the hardcoded `DEFAULT_LEAGUE_SLUG` (`'the-coupon'`) whenever `leagues`
  is loading or empty, and none of the four queries carries an `enabled` guard, so
  every cold load fires at that slug before the member's leagues arrive — Batch 8
  took the constant out of the pages and it survived in the context. For a member
  of that league it self-heals invisibly; for anyone else it is a wasted request
  and a refused one. A member in *no* league gets it permanently, and reads the
  403 as "No coupon this week yet" — home answers the same case correctly with
  "You're not in a league yet". Gate the queries on a resolved slug and give the
  no-league case its own empty state.

- [x] **Batch 30 — Slug-addressed coupon routes** ✅ 2026-08-17 *(Opus)* — making the bound league
  visible (Batch 29) does not make it addressable. `/predictions`,
  `/predictions/coupon`, `/predictions/results` and `/predictions/football` carry
  no slug, so which league they show is a fact about the client's memory rather
  than the URL: none of the four can be linked to, shared, bookmarked or reopened
  at a known league, and two browser tabs cannot hold two leagues at once.

  The cost is already being paid in push. `send_pick_reminders` names the league
  in the body — "You haven't made your pick in {league_name} yet" — and carries
  `league_id` in `data`, but sends no `url`, so `sw.ts`'s `notificationclick`
  falls back to `/`. There is no URL it could send instead, because no address in
  the app names a league's coupon. A reminder about league B therefore drops the
  member on home, which since Batch 26 is a list of every league they play, and
  they have to find B and tap in.

  It also quietly breaks a promise Batch 12 made. `useGameweekHistory` puts the
  selected round in the query string precisely "so a past week can be linked,
  reloaded, and reached with the browser's back button" — but a gameweek id is
  league-scoped and the URL holding it is not, so `/predictions/coupon?gw=<uuid>`
  resolves correctly only for a reader whose bound league is the one the link came
  from. For anyone else `GameweekNav` finds no matching row and falls back to the
  newest, so the link silently lands on a different league's different week rather
  than failing. Nothing shipped emits such a link today — Batch 24's share is
  clipboard text, not a URL, and `ResultsPage`'s row tap is internal — so this is
  latent rather than live, and it stays latent only while the coupon has no
  shareable address. Adding the slug is what makes the hook's own docstring true.

  Move the four surfaces under `/leagues/:slug/predictions/*`, redirecting the old
  paths through `activeSlug` so existing links keep working — `ResultsPage`'s row
  tap to `/predictions/coupon?gw=`, `PlayerProfilePage`'s link to
  `/predictions/results`, and the Playwright specs that `goto('/predictions')`.
  `CouponSubNav`'s items become slug-relative, and `TabBar` / `TopBar` — whose
  Coupon and Football entries are flat strings matched by prefix — need the active
  slug to build both their targets and their active-state prefixes. `activeSlug`
  survives as the default for a slug-less entry rather than as the source of
  truth, and `selectLeague` follows the route rather than the reverse. Then give
  the reminder a `url` pointing at that league's pick screen, and while there stop
  its body hardcoding "picks lock 14:30": lock time has been per-league since
  Batch 14 and admin-configurable since Batch 15, so a league playing Friday to
  Monday is currently told the wrong deadline.

  Explicitly not this: one screen stacking every league's open round. It reads as
  the natural multi-league answer and is not — rounds differ by slate window,
  deadline, offered markets and pick scope, so the countdown, roster and
  competition groups below the header would have no single league to belong to.
  Home's card-per-league already answers "what do I owe this week, everywhere";
  the coupon tab answers "play this league's round", and that question is singular
  by construction.

- [x] **Batch 31 — Settlement cost per league** ✅ 2026-08-17 *(Opus)* — settlement is the one path
  whose provider bill still multiplies by league count. `OddsAPI.settle` walks
  `for event_id in dict.fromkeys(event_ids)` issuing one `/events/{id}` per
  fixture, and `run_settle_gameweeks` calls it once per settleable round, so the
  de-duplication is *within* a league and never *across* them. Two leagues playing
  the default Saturday and holding any of the same fixtures each pay for those
  fixtures separately, against a plan allowing **100 requests/hour and 500/day**.
  At the 15-member roster the launch is sized for that is up to 15 distinct
  fixtures a league, so five leagues on one window approach 75 requests in a single
  run — most of them duplicates — and roughly seven exhaust the hourly budget
  outright. The Sunday and Monday retries then meet the same wall, and the visible
  symptom is not an error but picks staying `pending`: the week never finishes.

  `discover_fixtures` already solved this exact shape — leagues grouped by window
  so "the cost is the number of *distinct* windows, not the number of leagues" —
  and settlement never got the treatment because there was one league when it was
  written. Do the same here, in two steps of increasing ambition. First, dedupe
  event ids across every settleable round in a run and settle each fixture once,
  fanning the results back out per league; this is a pure win, needs no provider
  question answered, and alone removes the overlap. Second, and only if the
  provider supports it, replace the per-id walk with a windowed read: `OAEvent`
  carries `scores`, and `_league_events` already validates the `/events` list into
  that model, so a whole Saturday could cost one request per window rather than one
  per fixture — the way `_event_odds` already batches pricing through
  `/odds/multi`. That second step is a **hypothesis, not a finding**: the settle
  docstring's "`/events/{id}`, not the odds endpoints" was established against
  `/odds` and `/odds/multi`, and whether the *list* response carries scores for
  finished fixtures is unverified. Confirming it needs a live call, and live
  odds-api probes are owner-run — there is no key in the working tree — so treat a
  negative answer as fine and ship the first step regardless.

  This is gated on league count rather than the calendar: it is latent while
  production runs the leagues it has today, and it is invisible right up to the
  point the quota goes. Land it before the roster of leagues grows, not after.
  Independent of Batches 29 and 30 — no shared files, any order. Explicitly not in
  scope: the request path and discovery, both already shared across leagues
  (`odds_cache` is keyed per event, discovery groups by window), and pick
  semantics, which are per-league and correct.

- [x] **Batch 32 — Per-league notification preferences** ✅ 2026-08-18 *(Sonnet)* — a member's only
  control over reminders is all-or-nothing, and the volume it governs grows with
  every league they join. `NotificationPreferences` is keyed on `user_id` alone —
  `global_mute` plus quiet hours — and `send_notification` gates on
  `prefs.global_mute or _is_quiet(...)` with no league dimension anywhere in the
  path. `send_pick_reminders` nudges once per league by design, so a member in
  five leagues takes five pushes every Saturday morning and the one switch that
  reduces that also silences the league they care about. The more leagues someone
  joins, the more likely they turn off the reminder that was working.

  Put the flag on `league_memberships` rather than in a new table: that row is
  already exactly the `(player, league)` tuple, already carries per-membership
  state in `role` and `display_name_override`, and dies with the membership, so a
  member who leaves and rejoins does not inherit a stale mute. Migration `013`.
  Then filter in `members_missing_picks`, which already joins memberships and
  already carries `league_id` and `league_name` per row — a muted league is never
  targeted, rather than targeted and suppressed, which also keeps
  `send_pick_reminders`' return count honest about who was actually nudged.
  `global_mute` and quiet hours stay exactly as they are, layered on top: the
  per-league flag decides whether a reminder is *wanted*, the user-level gate
  decides whether *now* is a good time to deliver it.

  Surface it in `SettingsPage`'s existing notifications card as a per-league list
  under the global toggle — it is a notification preference and that is where a
  member goes to manage those. `LeagueSettingsPage` is the wrong home: it sits
  behind `LeagueAdminDep`, and this is a preference every member needs, not an
  admin one. Extend `GET`/`PATCH /api/v1/notifications/preferences` rather than
  adding a per-league endpoint, so the settings screen keeps making one read.

- [x] **Batch 33 — Football ingestion shape tolerance** ✅ 2026-08-17 *(Opus)* — Batch 28 shipped
  and the Football tab is still dark. The 06:30 sweep on 2026-08-17 failed 21
  times, once per competition, every one of them identically:
  `1 validation error for AFCatalogueEntry / country.code / Input should be a
  valid string [input_value=None]`. No `/standings` or `/fixtures` request was
  ever issued, so nothing downstream of the catalogue has yet run against the
  live API even once.

  API-Football returns `"code": null` for the countryless competitions — World,
  Europe — and `AFCountry.code` is `str = ""`. A default covers a key the
  provider *omits*; a key present as `null` is a different shape and pydantic
  rejects it however good the default is. That distinction is the whole defect,
  and ADR 0003 named the risk without being able to test for it: the adapter was
  written against documented shapes and the live probe is the owner's.

  Two details turned one bad row into total failure rather than one missing
  division. `_all_leagues` parsed the catalogue in a single list comprehension,
  so one entry's exception discarded every entry — including all thirty British
  divisions, none of which has a null country code. And the raise happened
  *before* `self._catalogue` was assigned, so the memo never filled and each
  competition re-fetched `/leagues`: 21 of the day's 100 requests spent, no rows
  written, and the per-run pacing Batch 28 added never reached the point where
  it mattered. Batch 28's diagnosis was correct and its fix is sound; it simply
  was not the only thing wrong, and its closing claim that the tab is dark
  "until this lands" outlived the landing.

  Fix the shape at the model boundary rather than the field: a base model whose
  before-validator drops nulls, so a key present as `null` reads as absent for
  every raw payload model. Per-field patching would leave the same trap on every
  other `str = ""` this provider fills, and one of those is already load-bearing
  — standings carry `"form": null` until a team has played, so an unpatched
  August would have emptied every table and then quietly filled itself in
  September, which is the hardest kind of gap to attribute. Make the catalogue
  parse drop an unreadable entry and memoise the survivors; per-competition
  parses need no such tolerance, because `sync_football_data` already isolates a
  failure to its own competition.

  What this cannot settle is coverage. Whether the free plan carries the lower
  British divisions for season 2026 has never been observed — only the catalogue
  request has ever succeeded — and the corrected run answers it in the log:
  `api-football catalogue loaded leagues=N dropped=M`, then one
  `api-football competition unmatched` line per division that fails to resolve.
  Read those before treating the tab as fixed. Ingestion is also invisible in
  the scheduler runbook, whose one-off list predates both football jobs;
  `sync-football` and `football-backfill` belong there with the cost of running
  them, since a run is how the tab fills the same day rather than at 06:30.

  Per the multi-league contract, the ingestion path was audited and is already
  correct: `league_competitions` scopes the read path per league, and
  `pooled_competitions` pools the *union* of competitions across leagues, so
  provider cost scales with distinct competitions rather than league count —
  the shape Batch 31 wants for settlement. Nothing here is Saturday-bound
  either; the sweep is a daily lookback window. One ceiling is worth recording
  rather than fixing: at one catalogue request plus two per competition, the
  100/day allowance caps a day at about 49 distinct competitions, and
  `FOOTBALL_COMPETITIONS_PER_RUN` defaults to 30. Once the pooled union outgrows
  the cap the rotation keeps every competition fed but no table is fresher than
  ⌈union ÷ cap⌉ days, so the symptom of too many leagues is staleness, not
  absence — and staleness reads as correctness.

  Implemented and gated locally (`scripts/ci-local.sh` PASS, 11 checks) but
  unshipped; the tab stays dark until `/ship-prod` carries it and a
  `sync-football` run follows.

- [x] **Batch 34 — Switching league without leaving the coupon** ✅ 2026-08-19 *(Opus)* — a member in two
  leagues cannot change which league's coupon they are looking at.
  `LeagueSwitchStrip` hardcodes every entry to that league's
  `/leagues/{slug}/leaderboard`, and all four coupon surfaces mount it, so tapping
  the other league on the pick screen lands on that league's standings instead. Rendering `CouponCombinedPage` with two leagues and reading
  the href back returns `/leagues/friends-league/leaderboard` from
  `/leagues/the-coupon/predictions/coupon`. The way back is the Coupon tab, which
  has by then silently re-aimed — so the recovery is two taps through a screen the
  member did not ask for, and the switcher is indistinguishable from a broken one.

  Batches 29 and 30 were both aimed here and neither could have caught it. Batch
  29 mounted the strip on the coupon surfaces to give the tab a switcher, but the
  component was written for `LeaderboardPage` and its destination came with it —
  its own copy still reads "Jump between tables". Batch 30 then made the coupon
  addressable, which is the thing that makes the correct destination expressible
  at all, and did not revisit the strip. The tests are why it survived twice:
  `CouponPickPage.test.tsx` and `CouponCombinedPage.test.tsx` both assert only
  `findByTestId('league-switch-strip')`, presence and never destination.

  One rule, in the strip rather than at the call sites: a league switch keeps you
  on the surface you are on. Export `predictionsSection` from `lib/leagues.ts`,
  have the strip derive each href from `useLocation()` — a coupon surface yields
  `predictionsPath(slug, section)`, anything else keeps the leaderboard as the
  league's front door — and fix the copy. Deriving it once means every surface
  added under `/leagues/:slug/*` later is right without touching this file again.

  **Drop the query string on the switch.** A gameweek id is league-scoped and
  `resolve_gameweek` 404s on a foreign one, so carrying `?gw=` across a switch
  lands on "No coupon this week yet" — a worse failure than the bug being fixed,
  and the one an implementer reaching for `useLocation().search` will ship.
  `GameweekNav` already falls back to the newest round for the *label*; nothing
  guards the query, because until now nothing could cross a league with it.

  Fold in the same drift on the admin side. `LeagueSettingsPage`,
  `LeagueMembersPage`, `LeagueAdminInvitesPage` and `LeagueJoinRequestsPage` read
  `useParams` with a `DEFAULT_LEAGUE_SLUG` fallback instead of calling
  `useRouteLeague`, against the rule Batch 30 set for every page under
  `/leagues/:slug/*`. Reached through the league's leaderboard the binding is
  already correct and the fault is invisible; deep-linked from a notification or a
  bookmark it is not, and the Coupon tab afterwards reopens the previous league.

  Explicitly not this: rewriting the slug segment of an arbitrary pathname, which
  reads as the general form of the same rule and is not — it carries a foreign
  player id into `/leagues/:slug/players/:playerId` and assumes admin of the
  target on `/admin/*`. Nor one screen stacking every league's round, for the
  reasons Batch 30 already recorded. Moving the switcher into `PageHeader` to
  reduce three stacked nav rows to two is a real question and a design one; it
  needs its own row, not this one.

  Frontend only, no API change and no route change. Tests assert where the
  switcher points, from a coupon surface and from the leaderboard, and that no
  `gw` survives the switch.

- [x] **Batch 35 — A one-off round in a multi-league game** ✅ 2026-08-19 — an admin adding a round
  outside their league's cadence (`POST /leagues/{slug}/gameweeks`, "Boxing Day, say")
  is the one admin action never checked against the multi-league contract. Three parts
  already hold: fixtures pool on `provider_event_id` so two leagues adding the same date
  share rows; `open_due_gameweeks` / `lock_due_gameweeks` / settlement select on status
  and instants with no date filter, so a one-off is adopted by the scheduler like any
  round; and Batch 31's dedupe settles two leagues' Boxing Day rounds in one provider
  read. Four parts do not.

  **A future one-off hijacks "this week", for one league only.** `latest_gameweek` and
  `_latest_rounds` both order `starts_on DESC LIMIT 1` — `me.py`'s docstring says so
  explicitly, that they are one rule spelled twice. Add Boxing Day in August and that
  league's coupon, pick screen *and* home card jump to a round whose picks open in
  December, while the member's other leagues still show Saturday; home renders those
  cards side by side, which is where it reads as broken rather than as a setting. The
  only way back is `GameweekNav`'s older arrow, which hides itself below two rounds.
  Replace the ordering with the question a member is actually asking: among rounds
  accepting picks now, the one locking soonest; failing that the most recent
  `starts_on` at or before today; failing that the earliest ahead. The "locking soonest"
  tiebreak is load-bearing rather than decorative — once a Boxing Day round and the
  20 December Saturday are both open, the one a member must act on first is the one that
  shuts first. Both call sites move together or the tab and the home card disagree.

  **The endpoint's rate limit is set above the provider's quota.** `fetch_slate` costs
  one request per UK competition — ~30 at the last live count — and the limiter allows
  `6/hour` per user, so one admin may spend ~180 requests an hour against odds-api.io's
  100/hour. The daily arithmetic is tighter still: `config.py` budgets a saturated day at
  ~420 requests of browsing plus ~60 of discovery against 500, leaving roughly 20, and a
  single ad-hoc call is ~30. It does not fit, and exhaustion is **silent** — Batch 31
  recorded the failure mode, picks simply stay `pending` and the week never finishes.
  Bring the limit under what the budget can absorb and record the arithmetic in the
  comment style `odds_cache_ttl_seconds` already uses, so the next person to raise it
  sees the ceiling rather than rediscovering it.

  **The ad-hoc fetch buys ~30 competitions to keep as few as one.**
  `selected_competition_slugs` filters at link time, and its docstring says that is
  deliberate: narrowing "changes what a league *plays*, not what discovery *costs*",
  because the per-window fetch is shared between every league on that window. Correct for
  discovery — and it inverts here. `refresh_slate` has exactly one production caller, the
  ad-hoc endpoint: one league, one date, a fetch nobody else shares, so there is no
  sharing to protect and the filter is simply being applied after the money is spent.
  Pass the league's selection into `fetch_slate` on that path and a league playing two
  divisions pays two requests instead of thirty. Take the port change as an optional
  argument defaulting to "all UK" so `discover_fixtures`' shared call site is untouched;
  it lands on the abstract, `OddsApiProvider`, `Betfair`, the `CachingOddsProvider`
  passthrough and two test doubles. Note in passing that a narrowed ad-hoc fetch no
  longer warms the pool for a wider league on the same date — that is the correct
  trade and not a regression, because nothing shared that fetch to begin with.

  **A one-off is never refreshed.** `upcoming_slate_dates` returns
  `first + timedelta(weeks=offset)`, so the refresh job only ever revisits dates on the
  league's weekly cadence. An ad-hoc card is frozen at whatever the provider held at
  creation: a postponement, a late addition or a corrected kick-off never lands, and
  because `sync_slate` only ever adds links the round cannot self-correct either. Widen
  the job's date set to the cadence dates **union** the dates of existing rounds not yet
  locked within the same horizon, then group by window exactly as `discover_fixtures`
  already does, so two leagues that both added Boxing Day are refreshed on one fetch.

  Explicitly not this: **queueing the fetch onto the discovery run.** It is the right
  architecture — it would move the last provider call out of the request path, where the
  odds cache's own docstring still claims `fetch_slate` never runs, and make the sharing
  structural rather than dependent on an in-process TTL two admins would have to collide
  inside. It is deferred because the two fixes above remove the way this actually bites,
  and because half of it is worse than none: the endpoint answers `422 NO_FIXTURES`
  synchronously today, and an admin who queues a dead date and hears nothing discovers on
  Boxing Day that they scheduled nothing. Revisit when an all-UK league's one-off is
  observed colliding with a live browsing peak, and only together with a requested-date
  status the settings screen can show. A short-TTL slate cache is *not* the smaller
  version of this and should not be reached for instead: it leaves the first call — the
  one that actually happens — at full price.

  Backend-led; the frontend changes only in what the coupon and home default to, which
  is covered by the existing surfaces. Tests: the ordering rule against a league holding
  a far-future one-off beside a live Saturday, both open rounds tie-broken by lock time,
  the narrowed fetch asserted on requests issued rather than on rows written, and a
  refresh that reaches an ad-hoc date. `tests/test_request_budget.py` asserts the quota
  arithmetic against a real cache rather than trusting a comment — the new limit belongs
  there too.

- [x] **Batch 36 — The odds key in the production logs** ✅ 2026-08-19 *(Opus)* — every odds request writes the
  live odds-api.io key into Railway's logs in plaintext. `odds_api.py:640` builds
  `query = {**params, "apiKey": self._api_key}`, httpx logs the full request URL at INFO,
  and nothing sets that logger's level anywhere in the app — so
  `GET https://api.odds-api.io/v3/leagues?sport=football&apiKey=<the key>` is emitted
  verbatim, once per call. Observed 2026-08-19 in the running production deployment, with
  a complete and valid key readable in the retained window.

  Two remedies, and only one of them is code. The key is already exposed for the whole
  retention period, so it must be **rotated**; that is the owner's action and no code
  change substitutes for it. `docs/runbooks/incident.md` is the right home for the
  sequence. The code change stops the next occurrence: silence httpx's request logging
  (`logging.getLogger("httpx").setLevel(WARNING)` where logging is configured) and keep
  the adapter's own log lines free of the query string. Whether odds-api.io also accepts
  the key as a header is unverified — api-football does, and is called correctly that way
  via `x-apisports-key` — and is worth one probe, because a header is the fix that
  survives someone re-enabling httpx logging later.

  The regression test is the point of the batch and should assert the property rather
  than the setting: drive an odds call against a captured log stream and assert no emitted
  record contains the key. A test that only asserts a log level passes the day someone
  adds a second HTTP client.

- [x] **Batch 37 — A division that resolves to the Premier League** ✅ 2026-08-20 *(Opus)* — the Football tab is
  empty and every club's position/form strip is blank, and neither is a data-availability
  problem. Production is configured correctly: `FOOTBALL_DATA_PROVIDER=apifootball`, the
  exact literal `config.py:58` accepts, with `FOOTBALL_API_KEY` set. Coverage — the
  question Batch 33 left explicitly open, never once observed — is now observed and is
  adequate. A catalogue probe on 2026-08-19 returned 1240 leagues, 46 English, 24 carrying
  season 2026, including `National League - North` (50), `National League - South` (51)
  and all four `Non League Premier` divisions (58/59/931/60). Batch 33's pessimistic
  reading can be closed: the free plan carries the British divisions.

  What fails is competition resolution. `similarity` (`team_matching.py:114`) returns a
  flat `SUBSET_SCORE = 0.95` when one name's token set is wholly contained in the other's,
  and `{premier, league}` is a subset of `{southern, league, premier, division, south}`.
  So "Southern League Premier Division South" scores 0.950 against **Premier League** and
  0.800 against `Non League Premier - Southern South`: the correct entry falls below
  `MATCH_THRESHOLD = 0.86` while the wrong one clears it. `league_id_for`
  (`api_football.py:399`) therefore resolves the division to league id 39 confidently and
  uniquely — this is not an ambiguous tie that a margin alone would catch. Isthmian League
  Premier Division and Northern Premier League Premier Division fail identically. National
  League North and South are unaffected; they normalise to an exact match.

  The subset rule is sound where it was written. It exists for team names, where the
  shorter string is a genuine abbreviation ("Inverness Caledonian" for "Inverness
  Caledonian Thistle"), and `similarity`'s own docstring says the score "leans on
  `best_match`'s ambiguity guard". `league_id_for` reuses the function but hand-rolls its
  own loop, applying `MATCH_THRESHOLD` and never `MATCH_MARGIN` — the guard the score is
  calibrated to depend on is missing at the one call site whose candidate list contains a
  generic short name. Competition names are not team names: "Premier League" is a whole
  competition, not an abbreviation of a longer one.

  Fix on the competition path, not by moving the constant — `SUBSET_SCORE` is load-bearing
  for teams and lowering it there would unmatch clubs. Withhold the subset bonus when
  scoring competitions, apply `MATCH_MARGIN` at that call site, and back both with an
  explicit slug→provider-league-id override for the British divisions. The override is not
  a workaround: "Southern League Premier Division South" and "Non League Premier -
  Southern South" share four tokens of five and still only reach 0.800, so no threshold
  choice resolves two providers' naming conventions by ratio alone. A miss must stay a
  miss — `api-football competition unmatched` already logs it — because a wrong id is far
  worse than none.

  Cleaning up is part of the batch. `upsert_teams` (`football_data.py:225`) moves a club's
  `competition_id` to the competition it was last seen in, so a mis-resolved division has
  been writing Premier League clubs and tables against a non-League competition and may
  have dragged genuine clubs out of correctly-resolved ones. Fixing the matcher alone
  leaves the wrong rows in place and the tab wrong in a new way; the corrective run needs
  the affected competitions' teams and standings cleared first. The downstream symptom to
  watch disappear is `team name unresolved` with `candidates=0` — 424 of them in a
  three-hour window on 2026-08-19.

  This is also the whole of the "form and position never appear" report. `PickCard.tsx:48`
  has rendered position ordinal and W/D/L pips since Batch 16 and `worthShowing`
  (`PickCard.tsx:37`) hides the strip when a club has neither; both light up from ingested
  rows with no frontend work. Tests: the matcher against the real catalogue's English
  entries, asserting every configured division resolves to its own id and that league 39 is
  never returned for a name carrying extra discriminative tokens; the margin guard; and a
  fixture-backed sync asserting rows land against the competition requested. End-to-end
  confirmation costs a `sync-football` run — about 61 of the day's 100 requests, per the
  scheduler runbook — so budget it deliberately rather than re-running it to watch.

- [x] **Batch 38 — When a pick was taken** ✅ 2026-08-20 *(Opus)* — the coupon says who took a selection and never
  when. "Who" already ships, per-selection as `taken by {firstName}` (`PickCard.tsx:258`)
  and per-fixture as `Picked by …` (`PickCard.tsx:154`). "When" is absent end to end even
  though the data has always been there: `Pick` extends `UpdatedAtMixin` → `TimestampMixin`
  (`pick.py:51`, `base.py:21`), so every row carries `created_at`.

  The smallest item on the list and the only one needing no migration. `_selection_options`
  (`gameweek.py:403`) builds its taken-map from a `(player_id, name)` tuple; widen it to
  carry the timestamp, add the field to `SelectionOption` (`gameweek.py:58`) and its mirror
  in `types.ts:26`, and render it beside the two existing strings.

  The only real decision is presentational and belongs to the product: an absolute time is
  unambiguous but noisy on a card already carrying a name, a relative one reads better and
  goes stale in a cached view. Match whatever the coupon already does for the lock
  countdown rather than introducing a second time idiom, and render in `Europe/London` per
  the project's scheduling rule.

- [x] **Batch 39 — Six admin buttons beside a title** ✅ 2026-08-19 *(Opus)* — `LeagueActionsMenu`
  (`LeagueActionsMenu.tsx:90`) is not a menu. It is a flat row of six controls for an admin
  — Leave, Members, Requests, Invites, Settings, Delete — dropped into `PageHeader`'s
  action slot (`LeaderboardPage.tsx:42`) beside a `flex-1 min-w-0` title. Batch 22 went at
  this once and stopped one step short: the slot was `shrink-0`, so the row's own
  `flex-wrap` never engaged and the buttons ran off the side; the wrapper became
  `min-w-0 max-w-full` (`PageHeader.tsx:74`) and it wraps now. Wrapping is not fitting. Six
  chips folding into a narrow column next to a title is the same complaint in a new shape,
  and the option Batch 22 explicitly declined — "the wrapper is the fix, not the menu" — is
  the one left standing.

  Make it the overflow menu its name already claims. Promote at most the one or two actions
  an admin uses on most visits and collapse the rest behind a single trigger. The
  destructive pair belongs inside, visually separated, and Delete keeps whatever
  confirmation it has today. The substance of the work is accessibility rather than layout:
  a real menu needs focus management, Escape to close, and outside-click dismissal, none of
  which a row of buttons ever needed.

  Frontend-only, no API change. Tests: the collapsed state exposes the trigger and none of
  the six controls; opening reveals them; Escape closes and returns focus to the trigger; a
  non-admin's reduced set still renders correctly.

- [x] **Batch 40 — A round the pick window never reached** ✅ 2026-08-20 *(Opus)* — an admin who sets
  `pick_open_offset_minutes` and finds picks open anyway is seeing the documented rule
  rather than a bug, but the rule is invisible exactly when it bites. The config path is
  correct end to end: `league.py:166` → `picks_open_at` (`gameweek.py:109`) → window open
  minus offset, so a 12-hour offset on a 15:00 Saturday opens claims at 03:00 that morning.
  The catch is that `picks_open_at_utc` is stamped onto the row **at discovery**
  (`gameweek.py:335`) and the settings PATCH deliberately does not recompute existing
  rounds — `leagues.py:873` states why, and the reason is good: an edit must never move a
  deadline members were already told.

  The consequence is sharper than "it applies from next time". A round discovered before
  the offset existed has `picks_open_at_utc = NULL`, and `pick_refusal` (`gameweek.py:81`)
  gates only when the column `is not None`; `picks_open_at` documents `None` as "the
  pre-Batch-27 rule: claimable from the moment discovery writes it". So such a round is not
  on an older offset, it has **no gate at all**. With a two-week discovery horizon, every
  round already on the board when the setting changed behaves this way, which is why the
  symptom looks like the setting being ignored rather than deferred.

  **The rows were read on 2026-08-20 and settle the scope.** `the-coupon` holds
  `pick_open_offset_minutes = 720` exactly as configured, and all three of its rounds —
  08-08 settled, 08-15 locked, 08-22 open — carry `picks_open_at_utc = NULL`. The 08-29
  round does not exist yet, so it will be discovered with a correct gate. **Only the
  08-22 round is affected, and it holds zero picks.** This is a one-round transitional
  problem that resolves itself, not an ongoing defect.

  That makes the permanent admin restamp the wrong shape: it is standing machinery, an
  awkward asymmetry (why may an admin move the opening but not the lock?), and a
  standing invitation to the exact edit `leagues.py:873` forbids — all to shorten a
  window that closes on its own. Take the forward-only rule.

  What is worth building is the reason the rule was mistaken for a bug: **it is invisible
  at the moment it bites**. An admin sets 12 hours, saves, sees picks open, and nothing
  explains why or shows the round's actual state. So: say at the point of change that the
  setting applies to rounds discovered from now on and that scheduled rounds keep the
  window they were created with; and **surface the current round's real
  `picks_open_at_utc`** — the instant, or "opens immediately" when it is `NULL`. The
  second half is the substantive one, and it turns an invisible rule into something an
  admin can look at. Both instants already ride on `GameweekListEntry` and
  `GameweekSlateResponse`, so this is a frontend batch.

  The 08-22 round itself, if it should be correct this Saturday, is a one-off owner
  `UPDATE` setting `picks_open_at_utc` to `2026-08-22 02:00:00` (window opens 14:00 UTC,
  less the 720-minute offset) — not a feature. Note it would leave `status = 'open'` while
  `pick_refusal` returns `PICKS_NOT_OPEN`; that disagreement is by design, since
  `gameweek.py:81` makes time the authority and status merely the label the scheduler
  keeps up with.

  Reading production needs `railway ssh` and `psql`, not `railway run`: the database host
  is IPv6-only and resolves nowhere a local process can reach it.

- [x] **Batch 41 — Naming the round** ✅ 2026-08-20 *(Opus)* — the coupon shows a date where members expect
  "Gameweek N", in two places that must move together: the header eyebrow
  (`CouponPickPage.tsx:178`) and the back/forward control (`GameweekNav.tsx:49`, also
  mounted by `CouponCombinedPage`). Why only one league appears to show it is not per-league
  configuration — `GameweekNav.tsx:27` returns `null` below two gameweeks, so the league
  with history is simply the only one rendering the control at all. Consistency here means
  deciding whether the label always renders, not finding a setting.

  The blocker is that no number exists anywhere. `Gameweek` (`gameweek.py:55-73`) carries
  `starts_on`, `status`, `locks_at_utc`, `picks_open_at_utc` and `settled_at`, and
  `GameweekSummary` (`types.ts:157`) carries none either. Two routes, and the cheap one is
  now the wrong one. Deriving an ordinal by `starts_on` within a league-season was
  reasonable until Batch 35: the round a league is on is no longer the newest `starts_on`, a
  one-off sits mid-sequence, and an ordinal recomputed on every read renumbers every past
  round the moment an admin inserts a Boxing Day fixture — a member's "Gameweek 12" silently
  becomes a different week's.

  So store it: a nullable integer stamped at discovery, monotonic per league-season, never
  reused, with a migration backfilling existing rounds in `starts_on` order. A one-off round
  then simply takes the next number, which is honest — it is the next round played — and
  history stays stable. The number is a display concern only; nothing in locking, settlement
  or scoring may key on it. Two questions to settle first: what a one-off is called if
  anything distinguishes it, and whether the sequence resets at a season boundary
  (`current_season`, `football_provider.py:173`, already defines that boundary).

- [x] **Batch 42 — Profile pictures** ✅ 2026-08-20 *(Opus)* — the largest of these and the only one that is new
  capability rather than a defect. The Coupon has never had avatars: `Profile`
  (`profile.py:34`) has no column, both API surfaces hardcode `avatar_url=None` with the
  comment "avatars not modelled in The Coupon spine" (`league_memberships.py:181`,
  `leagues.py:809`), and `avatar.tsx` is display-only with an initials fallback. That is a
  recorded decision rather than a regression — `LAUNCH_PLAN.md:113` documents that the
  frontend called `/api/v1/auth/me/avatar` against an API with no such route or field, and
  the MVP action was to strip the upload controls and keep initials; it shipped that way in
  Launch L1 (`STATUS.md:344`).

  Restoring it is four pieces, and the storage decision governs the rest. Supabase is
  already the database provider (`docs/launch/L0_PROJECT_IDENTITY.md:156`), so Supabase
  Storage is the obvious bucket — and it needs its own access rules written deliberately,
  because migrations `003` and `004` locked the public schema and the Data API down on
  purpose and a storage bucket must not quietly reopen what those closed. Then: a nullable
  column on `Profile` with a migration; an upload endpoint with a size cap, a content-type
  allowlist, and server-side re-encoding rather than trusting the uploaded bytes; the two
  hardcoded `avatar_url=None` sites reading the column; and an upload control that keeps
  `avatar.tsx`'s initials fallback for members who never set one.

  Scope it deliberately rather than by analogy to another project. An avatar is a
  user-supplied image shown to every member of a league, which brings moderation and
  deletion into the MVP: at minimum an admin path to remove one and a member path to clear
  their own. Nothing above it in this list depends on it.

- [x] **Batch 43 — Every time this app shows is an hour wrong** ✅ 2026-08-20 *(Opus)* — the API serialises every
  instant as naive UTC with no offset (`"2026-08-22T13:30:00"`), and JavaScript parses a
  date-time string without an offset as **local** time. The value is then handed to
  `formatInTimeZone`, so the wall-clock number displayed equals the stored UTC number
  regardless of zone: a 13:30 UTC lock — 14:30 in London during BST — renders as 13:30.
  Confirmed against the real wire format on 2026-08-20, and against production's stored
  `locks_at_utc = 2026-08-22 13:30:00`.

  Reading the wrong time is the smaller half. `useCountdown` computes
  `new Date(targetIso).getTime() - Date.now()` on the same mis-parsed instant, so it
  reaches zero an hour early; `CouponPickPage` derives `locked` from `countdown.expired`,
  and **the pick screen therefore shuts an hour before the API stops accepting picks**.
  Members lose the last hour of a round while the backend — which compares naive UTC to
  naive UTC and is correct throughout — would still have taken the pick. The same skew
  applies to `picks_open_at_utc`, so a round also appears to open an hour early.

  The offset is zero under GMT and one hour under BST, so this is invisible from late
  October to late March and returns without a deploy. A bug that fixes and re-breaks
  itself twice a year is the kind that gets misattributed to something else entirely.

  Fix at the API boundary, not the client: a pydantic serialiser that stamps `+00:00` on
  the `*_utc` fields (or timezone-aware columns) corrects every consumer at once, where
  patching each `new Date(...)` corrects only the call sites someone remembers. Audit
  them anyway — `PickCard`'s kickoff line, `GameweekNav`, `useCountdown`, and the
  settlement-facing screens.

  **The frontend fixtures are why 319 green tests never caught this**: `PickCard.test.tsx`
  and its neighbours use `Z`-suffixed ISO strings, which parse correctly, so the suite
  exercises a wire format the API has never sent. Correcting the fixtures to the real
  shape is not tidying — it is the regression test, and without it the fix can silently
  come undone. A test that asserts a *rendered* time for a known instant in a known zone
  is what pins this; asserting the parse alone would pass on both behaviours.

- [x] **Batch 44 — Turning avatars on** ✅ 2026-08-20 *(Opus)* — Batch 42 landed the column, the port, the
  endpoints and the control, and deliberately enabled none of it: `UnconfiguredAvatarStorage`
  refuses every write, so `POST /auth/me/avatar` answers 503 everywhere and
  `AvatarUpload.tsx` is not mounted. Three things have to be true before that changes, and
  they are in `src/services/avatar_storage.py` because the port is where they bind.

  **Bytes must be re-encoded, not passed through.** This is the item that actually blocks
  the feature. `sniff_image_type` checks a magic-byte prefix, which proves a header and
  nothing else — a valid PNG signature can precede a payload that is not one. Re-encoding
  through an imaging library is what neutralises a hostile file, and no imaging library is
  a dependency of this project; adding one is a deliberate change to the API's build, not
  an incidental import. Until it lands the endpoint must keep failing closed.

  **The bucket's access rules must be written explicitly.** Migrations `003` and `004`
  locked the Supabase public schema and Data API down on purpose. A storage bucket is a
  separate surface with separate policies, and provisioning one must not quietly reopen
  what those closed. Decide read access deliberately: a public-read bucket makes every
  member's picture world-readable by URL, and signed URLs mean the stored `avatar_url` has
  an expiry, which changes what the column means.

  **Then, and only then, mount the control.** `AvatarUpload` goes into `SettingsPage` as a
  `SectionCard` beside Timezone; its own docstring says so. Removal already exists on both
  sides — a member clears their own, a site admin takes another's down — so moderation is
  not outstanding.

  A note for whoever picks this up: the 500-character `avatar_url` was sized against
  signed URLs, which carry a token and an expiry in the query string. If the bucket serves
  bare public paths the column is oversized rather than wrong, and nothing needs changing.

- [x] **Batch 45 — A sweep that fails completely and reports success** ✅ 2026-08-20 *(Opus)* —
  `run_sync_football_data` (`scheduler.py:259`) returns `True` unconditionally on any run
  that reached the provider. `sync_football_data` (`football_data.py:426`) catches each
  competition's exception, logs `football data sync failed`, and continues — deliberate,
  documented, and right: one division the provider has dropped must not cost the other
  twenty-nine their tables. What no one checks is the case where *every* competition
  failed, which is indistinguishable at the job boundary from a card with no football in
  it.

  This is not hypothetical. On 2026-08-20 the production sweep failed all 21 competitions
  — 18 rejected at `/standings` with `Free plans do not have access to this season, try
  from 2022 to 2024`, 3 unresolved cups — logged `football data synced` with
  `competitions=3 carried=0 table_rows=0 matches=0`, and exited `0`. The 06:30 cron had
  been reporting a healthy run every morning while ingesting nothing, and the empty
  `teams` table was misread as a team-matching defect for long enough to cost a batch's
  worth of investigation. The summary line carried the truth the whole time; nothing was
  reading it.

  Fix the job's verdict, not the sweep's tolerance. A run is a failure when it attempted
  a non-empty card and carried none of it — `carried == 0 and len(reports) > 0`, plus the
  case where every competition raised and `reports` is empty while `targets` was not.
  Distinguish that from the two legitimate zero-work runs: no provider configured (an
  early `return True` that never reaches the sweep) and a genuinely empty fixture pool.
  Both must stay green, or a deployment that has not opted in fails every morning — the
  exact regression Batch 16's docstring warns against.

  **`carried` already means the right thing** and needs no new plumbing:
  `sync_competition` sets `carried = table is not None or bool(results)`, so a competition
  the provider does not carry is honestly false rather than an error. The signal exists;
  only the verdict is missing.

  Worth pairing with a partial-failure threshold — a run where 18 of 21 competitions
  raised is not healthy even if the other three carried — but the total-failure case is
  what makes the cron trustworthy again and should not wait for agreement on a ratio.

  Test it against a provider stub that raises for every competition and asserts the job
  returns `False`; the existing counting provider in `tests/test_football_data.py` is the
  shape to borrow. `tests/test_run_scheduled.py` already covers the exit-code mapping, so
  a failing verdict becomes a non-zero exit for free.

- [x] **Batch 46 — Reading the whole card from a source that has it** ✅ 2026-08-20 *(Opus)* — the football
  feature is built, tested, shipped and switched off. `FOOTBALL_DATA_PROVIDER=none` since
  2026-08-20 because api-football's Free plan carries no part of the current season.
  Re-verified live on 2026-08-20 with the sealed production key: `/standings`, `/fixtures`
  *and* `/teams` all refuse season 2026 with *"Free plans do not have access to this
  season, try from 2022 to 2024"*, season **2025 is refused too**, and `/fixtures` without
  a season is rejected outright (`The Season field is required`) so there is no
  date-window way round it. The most recent data that plan can reach ended 2025-05-25.
  This is an entitlement wall, not a defect: the key is valid, the plan is active to
  2027-07-24, and season 2024 returns a complete table.

  **Add a FotMob adapter as a third implementation of the existing port** — owner
  decision, 2026-08-20, taken with the terms position below already on the record.
  Nothing about ADR 0003's architecture changes — the port, the
  ingestion-never-in-the-request-path rule, standings stored as published, and the alias
  layer all stand. Only the source behind them moves. The paid alternatives were
  considered and not taken; TheSportsDB, at roughly $9/month, was the cheapest carrying
  comparable coverage and remains the fallback if the terms or the fragility below turn
  out to bite.

  Coverage was measured against the live card rather than assumed. The card is 21
  competitions and 416 fixtures, of which **18 are leagues** — the other three are cups
  and have no table under any provider. FotMob carries **17 of those 18 leagues, 368 of
  the 389 league fixtures**, missing only `northern-ireland-championship-1`. Decisively,
  it is the one free source found that
  reaches the six English step 6–7 divisions — National League North and South, Southern
  Premier Central and South, Northern Premier, Isthmian Premier — which are **203
  fixtures, 49% of the card**. Every alternative checked stops at the National League or
  above: football-data.org's free tier is 12 competitions (verified unauthenticated
  against `/v4/competitions`, British ones being the Premier League and Championship
  only), openfootball carries two, TheSportsDB has the coverage but truncates every table
  to five rows and every results feed to one event, and football-data.co.uk reaches nine
  of the 21 and publishes no tables at all.

  **The genuinely new shape: one FotMob league id carries several of our competitions.**
  `8944` is National League North *and* South; `8947` is Southern Central, Southern South,
  Northern Premier *and* Isthmian Premier; `9545` is the Highland League with both Lowland
  divisions. api-football is 1:1, and the port calls `fetch_table` once per
  `CompetitionKey`, so the naive adapter fetches `8947` four times over. Memoise the
  league-id response for the life of the run — the same trick `ApiFootballProvider`
  already uses for its catalogue — so those four competitions cost one upstream request
  between them. Get this wrong and the batch quietly quadruples its own request count
  against an unmetered endpoint that will notice.

  The corollary is a correctness trap, not just an efficiency one: the adapter must
  attribute each returned group to the right `CompetitionKey` before any club is stored.
  A Southern Central side filed under Isthmian produces a wrong club inside a table that
  looks perfectly well-formed. `team_matching`'s fuzzy stage is scoped to one division
  precisely so it cannot make that mistake — a mis-attributed group hands it bad scope and
  defeats the guard.

  **No key, and no daily cliff.** `FOOTBALL_API_KEY` is meaningless here, and the
  validator at `config.py:287` must not demand one for the new provider — it currently
  requires a key whenever the provider is `apifootball`, and the `fotmob` branch must not
  inherit that. FotMob publishes no quota, so the 100/day ceiling that shaped Batch 16 is
  gone. Do **not** delete `football_competitions_per_run` or
  `football_competition_spacing_seconds`: they are still exactly right for `apifootball`,
  which stays selectable. Make the pacing the provider's to own rather than the sweep's,
  or a 12-second gap keeps costing six minutes a run for a limit that no longer applies.

  **The empty tables are a gift — spend it now.** `teams`, `team_aliases`, `matches` and
  `standings` have never held a row in any environment. A provider swap is normally an
  id-namespace migration, since `provider_team_id` is globally unique and two sources'
  ids would collide. Here there is nothing to migrate and nothing to purge. Done after
  those tables are populated, this is a materially larger and riskier batch.

  Two smaller seams: the port names a season by its starting year (`2026`) and FotMob
  answers `selectedSeason: '2026/2027'`, so convert at the boundary; and `team_matching`
  now reconciles three vocabularies rather than two, with FotMob's spellings landing as
  `source='provider'` rows beside the odds spellings.

  **Two things this batch must be honest about.** The interface is undocumented and it
  moves: during the 2026-08-20 investigation `/api/leagues?id=47` — the path every public
  wrapper uses — returned 404, and the working path is `/api/data/allLeagues`. No version,
  no deprecation, no changelog. Read every field defensively exactly as ADR 0003 required,
  and treat a 404 on a known path as an error rather than as "this competition has no
  table". Separately, **FotMob's terms prohibit automated access.** The owner took that
  decision knowingly on 2026-08-20, against a card whose usage is one sweep a day over 21
  competitions. Recording it as a decision is the point: it stays revisitable, rather than
  being rediscovered later as a surprise by whoever reads the adapter.

  Write **ADR 0007** first, before the adapter, recording the coverage measurement, the
  terms position and the fragility, and superseding ADR 0003's choice of provider while
  keeping its architecture. It goes first because it is the artefact that makes the terms
  decision explicit and dated; without it the next person rediscovers the free-plan wall
  from scratch, which is what this one cost.

  Batch 45 is what makes this dependency tolerable, and it has already shipped: a sweep
  that attempts a non-empty card and carries none of it now fails and exits non-zero, so a
  FotMob path change surfaces as a red cron rather than as a table that quietly stops
  moving. Do not weaken that verdict to accommodate a flaky source.

  Verification: a recorded-payload test per shape — the combined-id group split for
  `8944`/`8947`/`9545`, a single-division id (`117`), the season-string conversion, and a
  moved path raising rather than reading as an absent table. Assert the memoisation
  against a counting client, mirroring the counting provider already in
  `tests/test_football_data.py`. Probe live from Railway before shipping, not from a
  laptop: this machine cannot reach several of these hosts, and every probe behind this
  batch ran via `railway ssh`. Then sweep the real card in staging and read `attempted`
  against `carried` — expect **17 carried**, `northern-ireland-championship-1` the only
  league miss, and the three cups carrying nothing because they have no table.

  Scope boundary: **no screen changes.** The Football tab and the inline form already
  render whatever is stored, and this batch only changes where those rows come from.
  Turning it on in production stays one variable (`FOOTBALL_DATA_PROVIDER=fotmob`) and a
  separate owner-run step.

- [x] **Batch 47 — A league with no rounds until tomorrow morning** ✅ 2026-08-21 *(Opus)* — an admin creates a
  league in the app and there is nothing in it. Fixture discovery runs once a day at
  06:00 (`scheduler.py`, `run_discover_fixtures`), so a league created at any other hour
  has no round, no card and no coupon until the following morning, and **no in-app way
  to change that**. The remedy today is `python -m src.run_scheduled discover-fixtures`
  inside the production container, which needs a Railway shell and is therefore an owner
  action for a problem every admin will hit.

  The symptom is worse than an empty screen. The one-off round endpoint
  (`POST /leagues/{slug}/gameweeks`, Batch 15, hardened in Batch 35) is the only control
  that populates a round on demand, so it gets reached for as a workaround — creating a
  round *on the cadence date the league was going to get anyway*. That is not what it is
  for. It exists for Boxing Day, it is rate-limited `2/hour;3/day` against a measured
  provider budget, and using it to paper over a scheduling gap spends that budget and
  leaves a round the cadence will then also try to write.

  **The fix is nearly free, and the reason is already in `discover_fixtures`' docstring.**
  Leagues are grouped by window and each `(window, date)` is fetched exactly once, so
  "a second league on the default Saturday is free". The corollary has never been
  exploited: when the pool *already holds* that window's fixtures for the dates a new
  league wants, its rounds can be created and linked with **zero** provider calls. It is
  `sync_slate` against rows already in `fixtures`, not a fetch. On this product that is
  the common case, because the default Saturday window is what almost every league will
  play.

  So: **populate a new league's cadence rounds at creation, from the pool.** Fall back to
  a real fetch only when the pool is empty for those dates, and rate-limit *that* path
  the way Batch 35 rate-limited the one-off endpoint — for exactly the same reason, and
  ideally sharing the limit so the two cannot be combined to exceed it. A league created
  on an existing window should cost nothing and appear instantly; a league inventing a
  new window pays, visibly and boundedly.

  Add the same path as an admin action — **"refresh rounds"** — because creation is not
  the only moment it is needed. An admin who changes the fixture window has unlocked
  rounds built against the old one and, today, waits for 06:00 again.

  **Four rules this must not break**, all of them already load-bearing:

  * An off-cadence date belongs to the league that asked for it. `discover_fixtures`
    syncs one only to leagues already holding a round on it, precisely so a neighbour's
    Boxing Day is not invented for everyone sharing the window. A creation-time populate
    walks the *cadence* only.
  * `sync_slate` returns `None` when the league's competition selection excludes the
    whole window. That is a league with no round, not an error.
  * `picks_open_at_utc` is stamped once, at discovery, and never restamped — Batch 27
    set the rule and Batch 40 declined to add an admin override. "Refresh rounds" must
    respect it: it may create rounds and link fixtures, and it must not move the opening
    or the lock of a round that already exists.
  * A locked or settled round is not refreshable. Only unlocked rounds may be rebuilt,
    which is the same boundary `unlocked_round_dates` already draws.

  Verification: a counting provider (the shape in `tests/test_football_data.py`) proving
  a league created on an already-pooled window issues **zero** upstream requests and
  still gets its rounds with fixtures linked; a second test that an empty pool falls back
  to a fetch and is refused past the shared limit; a test that a neighbour's one-off date
  produces no round for the new league; and a test that "refresh rounds" leaves an
  existing round's `picks_open_at_utc` and `locks_at_utc` untouched.

  Scope boundary: **no migration and no change to the scheduled job.** `discover_fixtures`
  keeps its cadence-union-off-cadence behaviour exactly as Batch 35 left it; this batch
  adds a second, cheaper entry point to the same machinery and an endpoint in front of it.

- [x] **Batch 48 — The pick screen dies when the odds provider says no** ✅ 2026-08-21 *(Opus)* — `_live_odds`
  (`gameweek.py:403`) calls `fetch_odds` with no fallback, so any provider failure
  propagates and `GET /leagues/{slug}/gameweek/current` returns **500**. The core screen
  of the product — the one every member opens to make their pick — has its availability
  wired directly to a third party's rate limit.

  Observed in production on 2026-08-21, the day before launch: `/odds/multi` answered
  `429`, the slate 500ed, and the Football tab beside it kept working perfectly because
  it reads only the database. The cause that day was self-inflicted (diagnostic traffic
  exhausting the 100/hour window), which is the good version of this. The bad version is
  the provider having a bad afternoon at 14:00 on a Saturday.

  **The cache already holds everything needed to survive it.** `OddsCache._entries` keeps
  an `_Entry(odds, stored_at)` per event and only *refreshes* what has gone stale. When
  the upstream call raises, the exception escapes `fetch_odds` and the caller gets
  nothing — but the entries are still sitting there, merely past their TTL. Catching the
  inner failure and falling through to the existing results comprehension serves the last
  known prices instead of a 500. That is the substantive fix and it is a handful of lines.

  **Browsing degrades. Picking must not.** There are exactly two `fetch_odds` callers in
  the request path and they need opposite treatment:

  * `gameweek.py:403` — browsing the card. A slightly stale price is a far better
    outcome than a broken screen, and a card with *no* prices at all still shows the
    fixtures, which beats an error page.
  * `picks.py:258` — freezing `odds_at_pick` onto a pick. This must keep failing loudly.
    The price is frozen at that instant and a winner scores `round(odds × 10)` from it, so
    a stale or missing price is not a degraded pick, it is a wrong score. Refusing the
    submission is correct.

  **Stop retrying a 429.** `_get` treats `429` as transient alongside `5xx` and retries it
  up to `_MAX_RETRIES = 3` with doubling backoff, so one rate-limited request becomes
  four. Under a quota breach that is precisely backwards: the response to "you are over
  budget" is the one thing guaranteed to keep you over it. On 2026-08-21 two diagnostic
  slate loads cost roughly 40-80 upstream requests through this amplification and slowed
  their own recovery. Separate the cases — retry `5xx` and network errors, fail fast on
  `429`, and let the cache cover the gap.

  **Say that it is degraded.** The slate response should carry a flag when prices came
  from a failed refresh, so the client can say "prices may be out of date" rather than
  presenting stale numbers as current. Additive and optional on the client, for the
  reason Batches 38 and 41 already record: Vercel deploys `main` on merge while the API
  waits for `/ship-prod`, so a required field breaks the coupon in that gap.

  Verification: a provider stub that raises `OddsProviderAPIError` on `fetch_odds` and a
  warm cache, asserting the slate returns `200` with the cached prices and the degraded
  flag set; the same stub with a **cold** cache, asserting `200` with fixtures and no
  selections rather than `500`; a pick submission against the same stub, asserting it
  still refuses; and a counting client asserting a `429` produces exactly **one** upstream
  attempt while a `503` still retries.

  Scope boundary: **no schema change, and do not touch the TTL tiers.** The budget
  arithmetic in `config.py` and `tests/test_request_budget.py` is unchanged by this — it
  governs how often a healthy provider is called, which is a different question from what
  happens when an unhealthy one refuses.

- [x] **Batch 49 — A postponed fixture nobody can take off the card** ✅ 2026-08-21 *(Opus)* — `sync_slate`
  (`gameweek.py:352`) says it outright: "Links are added, never removed." A fixture
  postponed after discovery stays on every round that linked it, stays pickable, and stays
  pickable right through the deadline, because nothing between discovery and the evening
  settle sweep is looking. On 2026-08-21 the Scottish Premiership card carried Hibernian v
  Kilmarnock for the following day — a match that had already been called off.

  Nothing upstream of settlement even reads the status. `fetch_slate` (`odds_api.py:380`)
  builds each `SlateFixture` from the event's teams and kick-off and drops the rest on the
  floor, while `_VOID_STATUSES` (`odds_api.py:132`) — which already lists `postponed`,
  `cancelled` and `abandoned` — is consulted only by `_settlement_for`
  (`odds_api.py:746`), hours after the round has been played.

  **Carry the status, then act on it while the round is still open.** `SlateFixture`
  (`odds_provider.py:137`) gains the provider's status; `sync_slate` removes the
  `GameweekFixture` link for any fixture reported void-status, and deletes any pick held on
  it. That puts the member in the one state the game already understands — no pick — so
  they can pick again, the 11:00 reminder job nudges them if they don't, and the selection
  returns to the land-grab.

  **Two deletes, not one.** `Pick.fixture_id` and `Pick.gameweek_id` cascade from
  `fixtures` and `gameweeks`, but `GameweekFixture` (`models/gameweek.py:87`) is a
  composite-key join with no cascade to picks. Deleting the link alone leaves the pick
  alive and pointing at a fixture no longer on its round: gone from the screen, still found
  by settlement. Both rows go, in that order.

  **Stop at the lock.** A member who picked before the deadline did everything right and
  has no way to respond once it passes, and deleting their pick then would make them
  indistinguishable in the standings from someone who never picked at all. `void` already
  means "scores nothing rather than counting as a loss" (`models/pick.py`, `scoring.py:77`)
  and settlement already writes it for exactly this status — so **the locked case needs no
  code**. Removal must simply refuse any round whose `locks_at_utc` has passed. Refresh
  runs 09:00 and 13:00 against a 14:30 lock (`scheduler.py`), so a Saturday-morning
  postponement is caught and a 14:00 one is not; the late one becomes a `void` at
  settlement, which is the right answer rather than a gap.

  **Never infer a postponement from absence.** `discover_fixtures` skips any date the
  provider returns nothing for (`gameweek.py:554`), and a partial or failed fetch is
  indistinguishable from a quiet one. Removal keyed on "the fixture vanished from this
  refresh" would let a single provider hiccup strip a whole round of live picks. Only an
  explicit status removes anything. The price is that a postponement the provider signals
  by *dropping* the event goes uncaught before lock — settlement voids it, exactly as
  today.

  **Tell the member.** A pick that silently disappears is worse than the postponement.
  `send_notification` takes a free-form `data.type` (`notification_triggers.py:84`), so
  `"fixture_postponed"` needs no enum value and no migration; deliberately *not* an
  `ActionType`, which is a Postgres enum and would.

  Confirm before implementing: whether odds-api.io returned that Hibernian fixture with
  `status: "postponed"` or simply stopped returning it. Only the first shape is fixable
  here, and it decides whether this batch closes the observed case or merely the general
  one.

  Verification: a provider stub returning one fixture as `postponed` against an **open**
  round holding a pick on it, asserting the link and the pick are both gone and the member
  is notified; the same stub against a **locked** round, asserting link and pick are
  untouched and settlement still voids it; a stub returning an empty slate for a date whose
  round holds live picks, asserting **nothing** is removed; and a fixture linked to two
  rounds — one open, one locked — asserting only the open one loses it.

  Scope boundary: **no migration.** The status is carried on the pydantic `SlateFixture`,
  not stored on `fixtures` — the row stays in the pool because other leagues may still link
  it and settlement still needs it. Do not touch the settle path, and do not change
  `discover_fixtures`' cadence-union behaviour.

- [x] **Batch 50 — What the pick card leaves out** ✅ 2026-08-21 *(Sonnet)* — three small omissions on the one
  screen every member uses, grouped because they are the same file and the same fix
  session, not because they share a cause.

  **The context strip cannot line up with the names above it.** `PickCard.tsx:152` renders
  the clubs as a single inline sentence — `Home` `v` `Away` — while the position-and-form
  strip beneath it (`:159`) is a `grid grid-cols-2` with the away side pushed
  `justify-end`. The names flow by text length; the pips sit at fixed column edges. They
  align only by coincidence, and for most fixtures they visibly don't. Put both rows on the
  same two-column grid so a club's form sits under that club's name by construction.

  **"Your pick" doesn't say which competition.** The summary card
  (`CouponPickPage.tsx:262`) prints the selection, the odds and `home v away`, and stops.
  `CombinedAccaView` already prints `leg.competition` on every leg, so this is one surface
  out of step with its neighbour rather than a missing feature.

  **The points vanish the moment a selection is claimed.** `PickCard.tsx:278` picks exactly
  one of three branches — "taken by X", "your pick", or "win N pts" — so both claimed
  states drop the number. `potentialPoints()` (`lib/coupon.ts:87`) is a pure
  `round(odds × 10)` of the displayed price, so it costs nothing to keep alongside the
  claim state, and it is the figure that tells a member what the game is worth to whoever
  holds it.

  Verification: Vitest on `PickCard` asserting a fixture whose two clubs have differing
  name lengths puts each club's form in its own grid column; that a selection taken by
  another member renders both the taker and the points; that the member's own pick does the
  same; and on `CouponPickPage` that the summary names the competition.

  Scope boundary: **frontend only, no API change.** Everything needed is already on
  `FixtureSlate`. Do not touch the grab mutation or `usePickEditor`.

- [x] **Batch 51 — Football Stats is not a coupon surface** ✅ 2026-08-21 *(Opus)* — the tab reads
  `/leagues/{slug}/football/…` and narrows to the competitions that league plays
  (`league_competitions()`, `football_data.py:247`), which was never what the screen is
  for. A member opens it to look at football, not at the subset of football their coupon
  happens to cover.

  **The data was never league-scoped in the first place.** `pooled_competitions()`
  (`football_data.py:214`) walks every competition in the shared fixture pool,
  least-recently-synced first, and writes `teams` / `matches` / `standings` with no league
  anywhere in them. Only the *read* narrows. So untying is a read-path change with **zero
  extra provider cost** — the 100-requests-a-day API-Football budget is untouched, because
  nothing about what gets ingested changes.

  Serve `/api/v1/football/tables` and `/api/v1/football/results` with no slug, gated on an
  authenticated player rather than `LeagueMemberDep`. The router docstring
  (`routers/football.py`) already concedes the current gate is consistency rather than
  privacy — "a league table is public information".

  **The tab then has to leave the sub-nav.** `CouponSubNav` is explicitly league-bound
  ("Every item stays inside `slug`", `CouponSubNav.tsx:9`), so an untied screen is a
  top-level route: `TabBar.tsx:48` and `TopBar.tsx:35` stop resolving it through
  `predictionsPath(slug, '/football')`, and `LeagueSwitchStrip` comes off the page, where it
  would otherwise be a control that changes nothing.

  **Rename it to Football Stats** while the nav is being edited, rather than twice. Roughly
  79 test assertions mention the string, though most are hrefs rather than labels. Watch the
  mobile tab bar: "Football Stats" beside Home / Coupon / Leagues is the longest label there
  by some margin.

  One honest limit to record in the empty state: the pool holds only competitions some
  league's card has actually covered, so "untied" means every competition we have ever
  ingested, not every competition in Britain.

  Verification: the new endpoints return competitions drawn from the whole pool for a member
  whose league plays one division; they still require authentication; the old league-scoped
  routes are gone rather than left as dead code; and nav tests assert the tab reaches the
  screen without a slug in the path.

  Scope boundary: **no ingestion change and no migration.** `pooled_competitions`,
  `sync_football_data` and the per-run cap stay exactly as Batch 45 left them.

- [x] **Batch 52 — A table that hides the column it exists to show** ✅ 2026-08-21 *(Sonnet)* — the Form column is
  already built and already populated (`LeagueTableCard.tsx:74` and `:103`), and then
  `hidden sm:table-cell` takes it away on every phone. The card's docstring defends that
  trade for played/won/drawn/lost — points must stay visible without sideways scrolling —
  and it is the right call for those four counts and the wrong one for form, which is a
  glanceable five-glyph run and one of the two things a member opens the screen to read.
  Find it room at narrow widths; drop goal difference to `sm` before dropping form.

  **Results are grouped by day alone.** `groupByDay()` (`FootballPage.tsx:154`) buckets on
  the formatted date, so a Saturday reads as one undifferentiated column of eighty matches
  across four competitions — the exact failure its own docstring describes, one level up.
  `ResultEntry` already carries `competition` and `competition_id`, so group by competition
  within each day. Day stays the outer key: it is what a member scans for first.

  Precondition, and worth checking before this batch starts: `run_sync_football_data`'s
  docstring records that on 2026-08-20 the sweep failed all 21 competitions — 18 rejected at
  `/standings` because the free API-Football plan carries no part of the current season, 3
  cups resolving no id. Batch 45 made that failure loud but did not make it stop. If nothing
  is being ingested, this batch improves the presentation of an empty screen.

  Verification: Vitest asserting the form pips are present at mobile width; that results
  render a competition heading within a day and that two competitions on one day produce two
  groups; and that a day with a single competition does not grow a redundant second heading.

  Scope boundary: **frontend only.** No API change — both fields are already served.

- [x] **Batch 53 — Form you cannot open** ✅ 2026-08-21 *(Opus)* — the pick screen draws five W/D/L pips and
  discards the matches behind them, despite already holding them. `TeamContext.recent`
  (`football_data.py:757`) is served on every fixture with each match's opponent, home or
  away, goals for and against, result and kick-off, and it is already typed on the client at
  `types.ts:80`. `FormLine` takes `form: string` and nothing else, so the payload arrives and
  is thrown away on render.

  Make a club's form open to the results it is made of — opponent, score, home or away, date.
  On the pick screen that is **frontend only**: the data is already in the response.

  In the league table it is not. `TableEntry.form` is a bare string with no `recent`, so
  `league_tables()` has to load it the way `fixture_context` already does — `team_form()`
  (`football_data.py:655`) takes a set of team ids and answers in one query, over-fetching
  `limit × teams × 2` rows and trimming in Python, so a whole division costs one statement
  rather than twenty. Add it there and both surfaces share one shape.

  Optional field on `TableEntry`, for the reason Batches 38, 41 and 48 all record: Vercel
  deploys `main` on merge while the API waits for `/ship-prod`, so a required field breaks
  the screen in that gap.

  Verification: a club with five stored matches opens to five rows with the right
  opponent and orientation for both home and away fixtures; a club with none stays inert
  rather than opening an empty panel; the table endpoint returns `recent` for every row in
  one query (assert the count, as `tests/test_football_data.py` already does for the sweep);
  and the disclosure is reachable and labelled for keyboard and screen-reader use, which
  `FormLine`'s existing `role="img"` + `aria-label` will have to change shape to allow.

  Scope boundary: **no new provider call and no migration.** Everything here is already in
  `matches`; this batch only stops discarding it.

- [x] **Batch 54 — A palette that was only ever checked against two of its four surfaces** ✅ 2026-08-22 *(Opus)* —
  `index.css:87` records the contrast work that was done: on-primary and on-accent were
  measured and are ≥ 4.9:1 in both themes. `--text-muted` was not held to the same
  standard, and it fails.

  Measured against each tier the palette itself defines — dark `#7B859B`: `--bg` 5.22 pass,
  `--surface` 4.84 pass, `--surface-elevated` **4.38 fail**, `--surface-overlay` **3.91
  fail**. It was verified on the two lower tiers and shipped, so it breaks precisely where
  a card sits on a card, which is where the pick screen puts every `WIN n PTS` line, the
  competition chip and the inactive tab-bar labels. axe on the live page at 390px finds
  seven failing nodes in dark mode from that one pair.

  **Light mode is worse and is the reason this is one batch rather than a tweak.**
  `--text-muted #8A93A1` fails against *every* light surface — 2.78 on
  `--surface-elevated`, 3.10 on `--surface`, 2.91 on `--bg`. Twenty-one failing nodes on
  the pick screen alone, across five pairs: the muted grey, `#F59E0B` on white at **2.14**,
  `--primary #059669` used as text at 3.54–3.76, and `#28A47E` at 2.81. The amber pair
  carries the most important status line the product has — "You haven't grabbed a
  selection yet" — at 2.14:1.

  Fix the tokens, not the call sites; one pair is wrong in dozens of places and the
  call sites are all correct. Smallest values that clear 4.5:1 on every tier the palette
  defines: dark `--text-muted:#8690A6` (5.06 / 4.52, still distinct from
  `--text-secondary #94A3B8`), light `--text-muted:#666F7D` (4.57 / 4.78 / 5.08). The
  amber and the green-as-text need their own darker light-mode values; `--primary` is
  already `#059669` in light mode *as a fill*, and that is a separate token from primary
  used as text on a light ground.

  Verification: a unit test that computes WCAG contrast from the tokens themselves and
  asserts every text token against every surface token in both palettes — the check that
  would have caught this, and that jsdom cannot do through axe. Keep
  `test/accessibility.test.tsx` as it is; it is not the wrong test, it just cannot see
  colour.

  Scope boundary: **tokens only, both palettes, no component changes and no API change.**

- [x] **Batch 55 — The app takes zoom away from the people who need it** ✅ 2026-08-22 *(Opus)* —
  `index.html:30` ships `maximum-scale=1.0, user-scalable=no`. It is the single axe
  violation present on every screen audited, axe rates it **critical**, and it is a plain
  WCAG 2.1 AA failure (1.4.4 Resize Text).

  It lands on the audience least able to absorb it. This is a phone-first PWA whose
  central screen is a grid of two-decimal odds set at 10px, and a member with low vision
  cannot enlarge any of it — not the price they are about to freeze, not the countdown,
  not the table. The attribute is almost always there to stop iOS Safari zooming when an
  input takes focus; the fix for *that* is a ≥16px font-size on the inputs, so check the
  inputs before removing it and raise any that are under 16px.

  **The same batch owes the form disclosure a target.** Batch 53 made the five form pips
  open onto the matches behind them, which was right, but measured live the control is
  **70 x 22 CSS px** — under the 24x24 that WCAG 2.2 SC 2.5.8 requires at AA. It is the
  only outright target-size failure in the app. The sub-nav chips (30px) and the account
  avatar (32px) clear 2.5.8 and sit under Apple's 44px guidance; raising them is optional
  and is a judgement call, not a conformance one.

  Verification: assert the viewport meta permits scaling; assert no input renders below
  16px; a Vitest check that the form disclosure's rendered box is at least 24x24. Re-run
  axe against the built app and show the critical violation gone.

  Scope boundary: **frontend only, no API change.** Do not restyle the pick card.

- [x] **Batch 56 — Two halves of account recovery, neither of which works** ✅ 2026-08-22 *(Opus)* —
  Changing a PIN is the thing a member does when they think someone else knows it, and
  `routers/auth.py:344-358` writes the new hash and commits. It does not revoke that
  member's `refresh_tokens`, does not clear `failed_login_count` or `locked_until`, and
  cannot reach the 24-hour access tokens already issued. So the session the member was
  trying to shut out survives, and keeps renewing itself on a 30-day rotating token.
  Rotation that does not end sessions is not rotation.

  The other half never worked at all. `pin_reset_request` (`auth.py:361-380`) looks the
  member up, writes one `log.info`, returns "an admin will be notified to reset your PIN",
  and notifies nobody. There is no notification row, no email, no queue — the only trace
  is a Railway log line, and `railway logs` caps at 500. `LAUNCH_PLAN.md` calls for "an
  admin-operated, one-time PIN reset flow"; what shipped is the message without the flow,
  and the message is untrue.

  These are one batch because they are one journey, and because SEC-04 makes them
  compound: `auth.py:181-199` resets `failed_login_count` only on a *successful* login, so
  once it reaches five, each expiry of `locked_until` buys exactly one attempt and a wrong
  answer re-locks for another fifteen minutes — permanently, at one guess per quarter
  hour. A member who mistypes five times has no way back in and no working way to ask.
  Reset the counter when the lockout expires; keep the window, drop the ratchet.

  Give the reset request somewhere to land that an admin actually sees. The app already
  has `notifications` and a push service; a row addressed to the league's admins reuses
  what exists rather than inventing a channel.

  Verification: changing a PIN revokes every other refresh token for that member and
  leaves the current session working; a revoked token is refused at `/auth/refresh`;
  a reset request creates something an admin can read, and still answers the same generic
  message to an unknown display name; a lockout that has expired admits five fresh
  attempts rather than one.

  Scope boundary: **no new external channel** — no email provider, no SMS. If a
  notification row needs a column, it is additive and forward-only, and it needs a written
  recovery plan under `ship-prod.md` because production has no restore point.

- [ ] **Batch 57 — Three things wrong in the file that takes the pick** —
  All three are in `routers/picks.py` and all three are cheap.

  **A malformed id is a 500.** `fixture_id` on the submit body (`picks.py:58`) and
  `gameweek_id` on the path (`picks.py:174`) are typed `str` and handed to SQLAlchemy
  against `UUID(as_uuid=True)` columns. Verified over HTTP: both answer **500**, while a
  well-formed id that does not exist correctly answers 404. The house already has the
  pattern — `routers/players.py:83-87` wraps `uuid.UUID(...)` in `try/except ValueError`
  and raises 404 — and every other router types its ids `uuid.UUID` and lets FastAPI
  answer 422. This one file is the exception.

  **The deadline is checked before the network call, not after.** `pick_refusal` runs at
  `picks.py:115`, `fetch_odds` goes out at `:127`, the commit lands at `:150`, and nothing
  looks at the clock again in between. The window is however long a third party takes to
  answer, on the one deadline the entire product is built around. `pick_refusal` is
  time-authoritative by design, so re-evaluating it against the same `now` after the
  snapshot costs one call.

  **A pick can outspend the provider.** `config.py:92-119` prices the browse path
  carefully and lands on 28 requests in the tightest hour against a 100/hour allowance.
  The pick path is priced at "one request per fixture" — but `submit_pick` is limited to
  `60/hour` per member (`picks.py:101`), and the 60-second cache only helps a member who
  re-picks the *same* fixture. Sixty changes of mind across sixty fixtures is sixty
  requests; two such members exceed the whole hourly allowance between them, before
  browsing or discovery has spent anything. Deciding between fixtures is what the hour
  before lock is *for*. Derive the per-user limit from the budget the way Batch 35 derived
  the one-off round's, rather than setting it independently.

  Verification: a malformed `fixture_id` and a malformed `gameweek_id` each answer 4xx,
  not 500, and a well-formed absent one still answers 404; a pick whose odds fetch returns
  after the deadline is refused with `PICKS_LOCKED` rather than written; a test that
  asserts the per-user submit limit against the measured provider budget, as
  `tests/test_request_budget.py` already does for the browse path.

  Scope boundary: **no migration, no schema change, no frontend change.**

- [ ] **Batch 58 — The rate limits that are decorative, and the ones that are not** —
  `rate_limit.py:18-23` takes the **first** entry of `X-Forwarded-For` as the client
  address. That value is entirely caller-supplied and Railway appends rather than
  replaces, so rotating the header gives a fresh bucket every request and every IP-keyed
  limit in the app — login at `5/15 minutes`, `pin/reset-request` at `3/hour`, the
  shared-scope provider budgets — is bypassable by anyone who thinks to try. The durable
  per-profile lockout still bounds PIN guessing, which is why this is not higher, but it
  is the only thing standing. Take the rightmost untrusted hop, or a fixed trusted-proxy
  depth counted from the right.

  Four smaller items belong with it, because they are all one file or one header:

  * **No refresh-token reuse detection** (`auth.py:218-258`). Rotation is implemented and
    the old row is revoked, but replaying a revoked token returns a plain 401. Reuse of a
    rotated refresh token is the signature of theft; the standard response is to revoke
    the family. Today the thief and the victim simply race.
  * **The correlation ID is attacker-controlled, unbounded and reflected**
    (`middleware.py:16-20`). Accept it only if it parses as a UUID, else mint one.
    Confirmed reflected in production response headers.
  * **`refresh_tokens` is append-only.** Every login and every refresh inserts a row and
    nothing ever deletes expired or revoked ones, on a Supabase Free project. The
    scheduler already runs periodic work; this is one more job.
  * **No weak-PIN policy** and **no `Cache-Control: no-store`** on authenticated JSON.
    Roughly a quarter of human-chosen four-digit PINs fall in about twenty values, so the
    effective keyspace is far under 10,000; a blocklist costs nothing.

  Verification: a spoofed `X-Forwarded-For` no longer earns a fresh login bucket; a
  replayed refresh token revokes the family and the test asserts the family is gone; a
  non-UUID correlation ID is replaced rather than echoed; the prune job removes expired
  rows and leaves live ones; a blocklisted PIN is refused at set time.

  Scope boundary: **no change to the lockout window itself** — that is Batch 56's, and the
  two must not both edit it.

- [ ] **Batch 59 — Twenty-nine advisories, three packages, one real upgrade** —
  An OSV query over the 130 pinned packages in `requirements.txt` hits three, all runtime:
  **starlette 0.37.2** (13 advisories, 3 HIGH), **cryptography 46.0.3** (4 HIGH), and
  **python-dotenv 1.0.1** (1, not reachable — the app only reads .env). The full report is
  `docs/review/2026-08-22/osv-python-advisories.txt`.

  The one that matters on its merits is CVE-2026-48710: missing Host-header validation
  poisons `request.url.path` and bypasses path-based checks. The multipart DoS pair
  (CVE-2024-47874, CVE-2025-54121) is not reachable — no route parses a form — and
  CVE-2026-48818 is Windows-only.

  `starlette` is pinned *by* `fastapi==0.111.0`, so this is a FastAPI upgrade rather than
  a line edit, and it has a known trap already documented in the code:
  `routers/auth.py:401-405` explains that `HTTP_413_REQUEST_ENTITY_TOO_LARGE` exists only
  on the pinned starlette and that following the newer deprecation warning turns a local
  warning into an `AttributeError` on the pins. Expect more of that shape.

  On the frontend, `pnpm audit` reports 34, of which almost all are build-time (vite,
  esbuild, @babel/core, brace-expansion, js-yaml) and never reach a browser. The exception
  is **react-router / react-router-dom**: open redirect via backslash in `<Link>` and
  `useNavigate`, rated as leading to XSS. Check whether any redirect target is
  attacker-influenced — the invite and join-by-code paths are where to look — before
  deciding how far to carry the upgrade.

  Verification: the full gate on the pinned toolchain, with the 151 Postgres-backed tests
  actually running; a fresh OSV query showing the runtime advisories cleared; the avatar
  size-cap path exercised, since it is the one that names a starlette symbol directly.

  Scope boundary: **dependencies and whatever their APIs force. No behaviour change.**
  If an upgrade demands a product decision, stop and record it rather than deciding it here.

- [ ] **Batch 60 — Make the gate run what it claims to run** —
  Three decisions compose into a hole. `conftest.py:38-41` skips Postgres-backed tests
  when `DATABASE_URL` is unset; `batch-verify.md` treats the database run as conditional;
  `phase-closeout.md` merges, ticks and **pushes `main`** while saying "Do not poll CI".
  So the routine gate is **509 passed, 151 skipped**, and the skipped set is the HTTP pick
  flow, settlement, the scheduler jobs, slate persistence, seeds and all four migration
  tests. A batch can go green, merge and auto-deploy the web app to production without the
  core game logic having executed once.

  With a `pgserver` instance and `alembic upgrade head` the same suite is **660 passed, 0
  skipped in 88 seconds**. That is the entire cost.

  **The documented toolchain cannot run the suite at all.** `AGENTS.md` and
  `batch-verify.md` point at app-starter's venv, which has no Pillow — Batch 44's
  dependency — so ten modules fail collection with `ModuleNotFoundError: No module named
  'PIL'`. A dedicated venv built from `requirements-dev.txt` fixes that *and* pins ruff
  0.5.4 and mypy 1.11.0 exactly, retiring the four paragraphs `batch-verify.md` spends
  apologising for the divergence. Both pass clean on the pinned versions.

  Make the database run the default rather than the exception, give the repo a venv of its
  own, and say in `phase-closeout.md` what the push actually does.

  Verification: a documented one-command local gate that starts the database, migrates,
  and runs everything with zero skips; `batch-verify.md` and `AGENTS.md` updated to match;
  a clean checkout can follow the docs and get a green suite.

  Scope boundary: **tooling and documentation only. No src/ change.**

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
