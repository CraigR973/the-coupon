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
