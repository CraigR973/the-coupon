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

- [ ] **Batch 24 — Share the coupon as text** *(Sonnet)* — the one thing ADR 0004
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

- [ ] **Batch 25 — Gameweek results** *(Sonnet)* — a settled week is reachable
  today only by stepping back through `GameweekNav` one round at a time, and only
  once two rounds exist, which is not how anyone looks up what happened last
  week. Add a results view to the coupon tab listing every settled gameweek with
  its winner, points and combined-coupon outcome, each row opening that week's
  coupon; the reads are already parameterised by `gameweek_id` from Batch 12, so
  this is mostly presentation over endpoints that exist. Reach it from the
  profile as well — `PlayerProfilePage` lists a member's settled picks but never
  says how the week went around them. Previous *football* results are explicitly
  not this: they stay in the Football tab where Batch 16 put them.

- [ ] **Batch 26 — Multi-league home and profile** *(Opus)* — the home page and
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

- [ ] **Batch 27 — Configurable pick-open time** *(Opus)* — let a league admin
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
