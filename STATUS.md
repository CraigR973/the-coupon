# Status — The Coupon

## Now

Batches 1-36 and 39 are closed. The Coupon is a verified
private weekly football accumulator PWA, and it is a **per-league** game: a
member may play in several leagues at once and each owns its rounds, window,
markets, competitions and claim size. Members sign in with display name and PIN,
claim one unique selection per league per round, score frozen odds after
settlement, compare standings, and view the shared combined coupon. The
single-Saturday, 14:30-lock rule is now the *default* an unconfigured league
plays, not an assumption the schema or the API makes.

Batch 31 closed the multi-league audit's cost half — settlement now reads a
fixture once per run rather than once per league holding it. Batch 32 gave a
member a per-league mute alongside the existing global mute and quiet hours,
so a member in several leagues can turn off one without losing the rest — the
flag lives on `league_memberships`, not a new table, so it dies with the
membership. Batch 34 made the league switcher keep the reader on the surface
they are on: it had pointed every league at its leaderboard, so a member in two
leagues could not change which league's coupon they were reading.

Batch 35 closed the last of the multi-league audit: a one-off round
(`POST /leagues/{slug}/gameweeks`) was the one admin action never checked
against the contract. "This week" is no longer the newest `starts_on` but the
round a league is actually on — among rounds accepting picks now, the one
locking soonest — defined once in `current_round_order` and used by both the
per-league read and the cross-league one, so the Coupon tab and the home card
cannot disagree. The endpoint's `6/hour` limit permitted ~180 provider requests
an hour against a 100/hour allowance and is now `2/hour;3/day`, derived from a
measured budget rather than a modelled one. The ad-hoc fetch asks only for the
competitions the league plays, since nothing shares it. And discovery now walks
the cadence *union* the dates of unlocked rounds, so a one-off is refreshed
rather than frozen at creation.

Batch 36 stopped provider API keys reaching the logs. odds-api.io takes its key
as a query parameter and httpx logs every request URL at INFO, so each odds call
published a live credential into Railway's logs — observed 2026-08-19 in the
running production deployment. Redaction now happens at the JSON renderer, which
covers the message, keyword values, nested structures and any third-party
library in one mechanism, and holds if a quieted logger is re-enabled later;
httpx and httpcore are also quieted to WARNING. **Rotating the exposed key
remains an owner action that this batch does not perform.**

Batch 39 collapsed a league admin's six action buttons into one overflow menu.
Batch 22 had made the row wrap rather than overflow, but six chips folding into
a narrow column beside a `flex-1 min-w-0` title was the same complaint in a new
shape. A member keeps their single `Leave` button in the open, since one button
never overflowed. The Radix dropdown primitive brings focus management,
Escape-to-close and outside-click dismissal, which is the substance of the fix.

Investigation on 2026-08-19 also reconciled seven reported snags into Batches
36-42 (`docs/BUILD_PLAN.md`). Two findings changed the picture: the football tab
is empty because competition matching resolves lower English divisions to the
*Premier League* — `SUBSET_SCORE` treats "Premier League" as a token subset of
"Southern League Premier Division South" — and not for want of coverage, since a
catalogue probe confirmed the free plan carries every British division needed for
season 2026, closing the question Batch 33 left open. Batch 40 is deferred
pending a product decision.

Batch 6 completed the product rebrand, removed inherited surfaces, corrected
the frontend auth and invite wiring, and added a deterministic production-
preview browser flow backed by scratch PostgreSQL and `FakeBetfair`.

Batch 7 replaced the Betfair Exchange with `odds-api.io` priced by Bet365,
behind a provider-neutral `OddsProvider` port. This unblocks production: the
Exchange never priced the Scottish lower divisions and refused the production
login from every available region, so no gameweek could exist. Settlement is
now derived from published scores, the schema carries no provider identifiers
(revision `005`), and request-path odds are cached against the provider's rate
limit.

Launch phase L0 records the public repository, fresh project names and
owner accounts, no-cost platform hostname strategy, regions, budget controls,
15-player roster handling, and connector boundaries.

Launch phase L1 hardened the application and deployment path. Launch phase L2
provides fresh, isolated Supabase, Railway, and Vercel staging targets, with
stable web/API origins and a target-specific shipment workflow. Launch phase
L3 verified the full canned-odds staging story, phone push lifecycle,
scheduler, backup/restore, platform logs, and rollback.

Launch phase L4 provisioned and verified the production stack. Production is
deployed, healthy, and serving at
`https://the-coupon-production.vercel.app`, backed by
`https://api-production-109b1.up.railway.app` and a locked-down London Supabase
project holding one bootstrapped administrator.

The odds source works: verified live for Saturday 2026-08-08, `odds-api.io`
carries 30 UK leagues, 131 qualifying 15:00 fixtures, and 280 distinct priced
selections against the 15 a full league needs, with both Scottish lower
divisions fully priced.

**Production runs `13560cdb` on both stacks as of 2026-08-16**, at migration
`012`. `/api/v1/health` reports that commit and the migration head bundled in
the image, so `scripts/check-deploy-drift.sh` now answers exactly (`in sync`)
rather than falling back to probing. `ODDS_API_KEY` is sealed,
`ODDS_PROVIDER=oddsapi`, and `SCHEDULER_ENABLED=true`; the paragraph above about
a Betfair build and an unsealed key described the state before the 2026-08-04
and 2026-08-06 shipments. Batches 33, 30, 31 and 32 are on `main` and **not**
yet shipped, so the API is behind local `main` — `scripts/check-deploy-drift.sh`
reported `DRIFTED` at Batch 31's close-out. Batch 30 changes the API's reminder
payload (a `url` and a per-league lock time), Batch 31 is backend-only, and
Batch 32 adds `league_memberships.notification_muted` (migration `013`) plus
the per-league fields on `/api/v1/notifications/preferences` — none of that
reaches production until `/ship-prod` runs and carries migration `013` with it.

The football-data provider is fully configured in production —
`FOOTBALL_DATA_PROVIDER=apifootball`, `FOOTBALL_API_KEY` sealed 2026-08-15 — and
the Football tab is still empty, for the third distinct reason in a row. Batch 16
built it, Batch 28 found the undocumented 10/minute ceiling, and Batch 33 found
what that was hiding: `/leagues` returns `"code": null` for the countryless
competitions, one entry failed validation, and the whole catalogue went with it.
Only the catalogue request has ever succeeded against the live API, so **whether
the free plan carries the lower British divisions for season 2026 is still
unobserved**. The next run answers it in the log —
`api-football catalogue loaded leagues=N dropped=M`, then one
`api-football competition unmatched` per division that fails to resolve. Until a
`/ship-prod` carries Batch 33 and a `sync-football` run follows, the tab and the
pick card's position-and-form strip stay dark.

Note that the two stacks ship differently: **Vercel auto-deploys `main` on every
push; Railway moves only when `/ship-prod` runs.** Between 2026-08-04 and
2026-08-06 that let the API fall thirteen batches behind the web app and broke
the Coupon tab in production. `scripts/check-deploy-drift.sh` reports the gap
and `/phase-closeout` now runs it.

Launch also ships with **no database backup**, by owner decision recorded in
`docs/launch/L0_PROJECT_IDENTITY.md`.

Batches 8 onward come from the owner's 2026-08-05 feedback pass and proceed
alongside launch. Batch 8 bound the coupon, combined-acca, and home pages to
`LeagueContext`'s new `activeSlug` (last-viewed league, falling back to the
member's first league) instead of the hardcoded `DEFAULT_LEAGUE_SLUG`.

Batch 9 reshaped the pick screen: the slate groups by competition behind
collapsible headers, a member roster shows every member's pick and who is still
to pick, each fixture carries an "already picked" marker beside the existing
per-selection one, and `profiles.odds_format` (migration `007`) lets a member
read prices as decimal or traditional UK fractional. The format is display only
— prices stay `Numeric(6, 2)` and a winner still scores `round(odds × 10)`.

Batch 10 added `leagues.pick_scope` (migration `008`): a league may make one
claim take the whole game rather than a single selection, enforced by a partial
unique index on a scope denormalised onto each pick. The default is unchanged
behaviour, so opting in is deliberate — it shrinks the pick pool roughly
fivefold, which a 15-member roster feels.

Batch 11 split fixture discovery from pricing. A daily 06:00 job walks the next
two Saturdays into `fixtures` at a fixed cost; odds stay on demand behind a cache
whose freshness ceiling tightens as lock approaches, with the price frozen onto a
pick refreshed separately for that one fixture. `tests/test_request_budget.py`
asserts the whole arrangement against the provider's 100/hour and 500/day — the
daily cap is the binding one.

Batch 12 made the season browsable. A gameweek list endpoint plus a `gameweek_id`
parameter on the slate and coupon reads replaced the hardcoded `latest_gameweek`,
and the client keeps the selection in the URL so a past week is linkable. Every
gameweek ever synced is retained, so the history needed no backfill.

Batch 13 added a per-league member profile at `/leagues/:slug/players/:playerId`:
season figures taken from `standings()` so the two cannot disagree, a win rate,
and every settled pick behind them. Per-league rather than career-wide, because
picks are league-scoped and the claim rule is too.

Batch 14 split the schema so leagues can play different football. `gameweeks` is
per-league (migration `009`, `saturday_date` renamed `starts_on`), fixtures are a
shared pool joined through `gameweek_fixtures`, and the weekly window — which days,
which kick-off times, how long before lock — is per-league configuration stored as
a range. Defaults reproduce the Saturday 15:00 slate exactly. Discovery groups
leagues by window so a second league on the default costs no extra provider
requests.

Batch 15 put those settings under admin control and added two more. The fixture
window is now editable (Batch 14 only stored it); a league also chooses its
competitions — `leagues.competitions` (migration `010`), `NULL` for the "all UK
leagues" group or an explicit list applied as a link-time filter in `sync_slate`, so
narrowing costs no extra provider requests — and its offered markets, a subset of the
`pick_market` enum stored as an array. Admins can add a one-off round for a date off
the usual cadence, such as Boxing Day. All of it is gated by `LeagueAdminDep`.

Batch 16 added real football. Tables, previous results, and form come from a
second, independent provider (API-Football, ADR 0003) because `odds-api.io`
publishes no standings, and our own fixtures could not supply a table — the slate
has only ever stored Saturday 15:00 kick-offs, and scores were never persisted.
Migration `011` adds `teams`, `team_aliases`, `matches`, and `standings`; a match
is a separate record from a fixture, since most matches are neither pickable nor
picked. The free plan allows **100 requests a day**, so no screen ever reaches a
provider: a capped, rotating 06:30 job writes the tables and every read serves
them. Team names are reconciled between the two providers' spellings by an alias
layer that refuses to guess. Two surfaces — a Football section at
`/predictions/football`, and each club's position and form inline on the pick card,
which degrades to the pre-batch card when a club does not resolve.
`FOOTBALL_DATA_PROVIDER` defaults to `none`, so production is unchanged until the
owner runs a live probe and seals a key.

Batch 17 was a timeboxed spike and ships no code — its output is ADR 0004, which
decides **not** to build betslip export. Bet365 publishes no betslip API; Bet Share
carries a full accumulator but only a logged-in Bet365 customer can mint one; the
affiliate add-to-betslip link is one we could create and carries a single
selection. Two walls settle it either way: nothing we can generate composes an
accumulator, and `odds_at_pick` is frozen, so an exported acca prices live at the
book and disagrees with the coupon's headline number. An outbound bet link would
also make this gambling advertising, and there is no age gate anywhere in the
application. The combined coupon stays a scoreboard.

Batches 18 onward come from the owner's 2026-08-06 feedback pass, reconciled
against the code before being written up. Batch 18 was a live production defect
found while reconciling it, not one of the five reported points: `vercel.json`'s
SPA rewrite sent every self-hosted font and PWA icon to `index.html` because its
negative lookahead excluded a directory (`icons/`) that never existed rather
than the actual root-level paths, and the service worker precached the HTML
substitutes into the installed app. Fixed by correcting the lookahead to match
`fonts/`, `icon-`, `apple-touch-icon.png`, and `coupon-icon.svg`.

Batch 19 diagnosed and fixed the owner's coupon-page crash report: not coupon
code, but a stale route chunk. Every route is `lazy()`, a deploy drops the
previous build's chunk hashes, and `sw.ts`'s `skipWaiting()`/`clientsClaim()`
hands an open tab to the new worker while it still runs old JS, so the first
route change after a deploy 404s. `lib/lazyRoute.ts` (ADR 0005) wraps
`React.lazy` for all eighteen routes and `Layout`, reloading once on a
recognized chunk-load failure and otherwise letting `ErrorBoundary` explain.

Batch 20 fixed three reported wayfinding gaps, all frontend-only with no API
change: the home page now names the active league in its `PageHeader` eyebrow
(covering all three home cards); a self-profile route now exists, reachable
from both `TopBar`'s avatar menu and `TabBar`'s mobile More sheet as "My
profile"; and the already-built `LeagueJoinRequestsPage` and
`LeagueAdminInvitesPage` gained admin-only buttons in `LeagueActionsMenu`.
Also fixed in passing: `SettingsPage`'s dangling `/about` link, which had no
route and silently bounced through the catch-all to home, now resolves to a
new `AboutPage` reusing the existing scoring-rules copy.

Batch 21 fixed the competition picker Batch 15 shipped, which was empty for
most leagues so "all UK leagues" was the only usable choice. The cause was the
catalogue, not the UI: `GET /{slug}/competitions` built its list from
`SELECT DISTINCT … FROM fixtures`, which is only what discovery had already
pooled, so a league whose slate had never run had nothing to tick. The odds
port gained `fetch_competitions()` as an `@abstractmethod` — a default
returning `[]` would have left `FakeBetfair`, which backs staging and the
browser flow, showing that same emptiness. It costs no upstream request on the
common path: the catalogue is one `/leagues` call memoised on the shared
client, not the per-competition `/events` fan-out the slate pays for. The
pooled-fixtures query survives as the fallback when the provider is
unreachable, because the picker is also how an admin *un*-narrows a league.

Batch 22 fixed the 2026-08-15 wayfinding and layout feedback without changing
the API contract. Football is now in primary navigation on both desktop and
mobile, with active state kept distinct from Coupon. `PageHeader` lets its
action slot shrink so `LeagueActionsMenu` can wrap on phones; Members is
admin-only; and both combined-coupon legs and player history rows render the
competition already present on `CouponLeg` and `SettledPick`. The close-out gate
also found and fixed a backend config trap: `apps/api/alembic.ini` had a
non-ASCII comment that made Alembic config parsing fail under an ASCII locale,
so `/health` could report `migration: unknown` even though revision `011` was
bundled.

Batch 23 made the large-slate picker scan by competition first. The gameweek
API now includes `fixtures.competition_id` in each `FixtureSlate`, and the web
groups on that stable provider slug rather than display names that may carry
sponsor text. Groups start collapsed and sort by the UK league pyramid —
England's top four tiers, Scotland's top four, then each nation's remaining
tiers, then everything else by fixture count. The member roster also carries
and renders the picked fixture's competition.

Batch 28 fixed API-Football ingestion rate limiting, deliberately ahead of
Batch 22. API-Football's free plan is not just 100/day; it is also 10/minute,
and the minute limit arrives as HTTP 200 with `errors.rateLimit`, so the old
429/5xx retry path never ran and the two-requests-per-competition sweep burned
through the minute allowance in seconds. The adapter now treats `rateLimit` as a
transient body error, and the scheduled sync spaces competition attempts by a
configurable 12 seconds so a 30-competition sweep takes about six minutes.
ADR 0003 now records both limits.

Batch 24 added a "Copy text" button to the combined coupon rendering every leg,
selection, price and the combined odds as plain text a member can paste into a
group chat, with a note that prices were frozen at pick time. No bookmaker
link and no new API surface — `buildCouponShareText()` is a pure function over
the fields `GET /leagues/{slug}/coupon` already returns, satisfying the second
wall ADR 0004 left standing.

Batch 25 added a gameweek results view. `GET /leagues/{slug}/results` returns
every settled round, newest first, with its winner (or tied winners), their
points, and the combined-coupon outcome — one query over `picks`, no new
table. The coupon tab gained a Results list alongside Your pick, Combined
coupon and Football, each row opening that week's coupon; the player profile
now links to it too, since it previously listed a member's settled picks
without ever saying how the week went around them.

Batch 26 made home and the profile answer for every league a member plays
rather than for whichever one was bound. `GET /api/v1/me/cross-league-summary`
returns the season across all of them in five fixed queries, carrying a
per-league breakdown plus that league's current round; `scoring.standings()` is
now a one-league wrapper over a new `standings_by_league()`. Points and win rate
aggregate (one `round(odds × 10)` scale); rank does not, so the average skips
leagues with fewer than three members and says how many it covered. Home is a
card per league — its pick, its standing, one tap to that week's coupon — and My
profile moved to a career-scoped `/profile`, in the tab bar and the avatar menu
alike. The per-league record at `/leagues/:slug/players/:playerId` is unchanged.

Batch 29 fixed the same gap on the coupon surfaces that Batch 20 fixed for
home: `CouponPickPage`, `CouponCombinedPage`, `ResultsPage` and `FootballPage`
now name the bound league in their header and render `LeagueSwitchStrip`
above `CouponSubNav`, so a member in several leagues can tell whose slate they
are picking from and switch without leaving the tab. `LeagueSwitchStrip` now
binds through `selectLeague` rather than writing the recency store alone,
closing a drift where browsing `LeaderboardPage` (URL-driven slug) updated
the store but not `activeSlug`, so a later tap on Coupon could reopen the
wrong league. All four surfaces' queries now gate on a resolved membership
(`LeagueContext`'s new `hasLeagues`) instead of firing at the
`DEFAULT_LEAGUE_SLUG` fallback, and a member of no league gets its own empty
state instead of a 404 read as "no coupon yet". Frontend-only, no API or
route change — slug-addressed routes are Batch 30.

Batch 30 gave each league's coupon an address. The four surfaces moved to
`/leagues/:slug/predictions[/coupon|/results|/football]`, so a week can be
linked, shared, bookmarked and reopened at the league it came from, and two
tabs can hold two leagues at once. The slug-less paths still land: they wait
for the member's leagues and redirect through the bound one, carrying the query
string so an old `?gw=` link survives — which also makes `useGameweekHistory`'s
promise true, since a gameweek id is league-scoped and the URL holding it was
not. The URL is now the source of truth: `useRouteLeague` binds the context on
arrival, so `activeSlug` is the default for an address naming no league rather
than the thing addresses derive from, and the binding left `LeagueSwitchStrip`
and home's select-then-navigate pair. The nav bars aim at the bound league but
highlight for any league's coupon. The pick reminder — the reason the addresses
were missing — now carries `url` to that league's pick screen instead of
letting `sw.ts` fall back to `/`, and reads the round's own `locks_at_utc` on
the member's clock rather than hardcoding "picks lock 14:30", which has been
wrong for any league not locking Saturday since Batch 14.

Batch 31 closed the last path whose provider bill multiplied by league count.
Settlement de-duplicated fixtures *within* a league and never *across* them, so
two leagues playing the same Saturday paid separately for every match they both
held — against a plan allowing 100 requests/hour, which roughly seven leagues on
one window would exhaust outright. `settle_gameweeks_via_provider` now gathers
every settleable round's outstanding fixtures, de-duplicates them across the
whole run, reads the provider once, and fans the settlements back out per round;
the cost is the number of *distinct* fixtures outstanding, not the number of
leagues holding them, which is the rule `discover_fixtures` already applied to
slate windows. It works because a fixture is one pooled row since Batch 14. The
row's second, more ambitious step — replacing the per-fixture `/events/{id}` walk
with a windowed read of the `/events` list — was **not** taken: whether that list
carries `scores` for finished fixtures is unverified, confirming it needs a live
odds-api call, and there is no key in the working tree. The open question is
recorded on `OddsApiProvider._event_by_id`. This was latent rather than broken —
running out of quota raises no error, it just leaves picks `pending` and the week
unfinished — so it had to land before the roster of leagues grows, not after.

## Verified

- Backend: 534 pytest with a database (418 without one), Ruff check/format, and
  strict mypy; Batch 35 close-out passed `scripts/ci-local.sh` end-to-end
  (11 checks), as every close-out since Batch 26 has
- Database: clean `pgserver` migration through revision `013`, including a pre-009 backfill, a 009 downgrade round-trip, and a 010 up/down round-trip, with forced RLS
  on all 18 public tables under a Supabase-like role setup. The count was 13 at
  revision `004`; `009`-`013` added the rest, and every one of the 18 was
  confirmed RLS-enabled *and* forced against production on 2026-08-19, with
  `anon`, `authenticated` and `PUBLIC` holding no table privileges and no schema
  `USAGE`
- Frontend: Node 20 production build, TypeScript, ESLint, and 315 Vitest
- Browser: production-bundle smoke plus the full live staging story, including
  deep links, auth, administration, picks, settlement, standings, combined
  coupon, phone push, and PWA update behavior
- Repository: inherited-name and stale-file audit clean
- Launch L0: owner-approved public GitHub origin, explicit fresh platform
  targets, scoped Supabase connector boundary, and recorded owner decisions
- Launch L1: durable PIN lockout, inactive-login rejection, removed avatar
  upload/passwordless activation/public reset/Sentry surfaces, staging-only
  `FakeBetfair`, Betfair certificate-login support, scheduler retries,
  migration-level Supabase Data API lockdown, deployment runbooks, CI coverage,
  and clean PostgreSQL-backed tests
- Launch L2: fresh London Supabase staging at migration `004`, one always-on
  resource-capped Amsterdam Railway replica, Vercel `apps/web` staging, stable
  origins, synthetic-only seed data, sealed staging configuration, and
  verified Data API denial
- Launch L3: CI and the complete synthetic staging story, exactly-one
  scheduler exercises, phone push subscribe/send/unsubscribe, clean platform
  logs, a disposable logical restore, recorded evidence, and tested rollback
  with the reviewed forward deployments restored

- Launch L4: London Supabase production at migration `004` with forced RLS,
  denied Data API and clean advisors; sealed Railway and Vercel production
  configuration; healthy first deployments with confirmed alias, TLS, CORS and
  SPA deep links; an idempotent administrator bootstrap with verified counts
  and end-to-end login; and clean production logs. Three Betfair defects found
  by live probing were fixed: certlogin field names, sponsored English
  competition names, and a division allow-list that starved the slate.

Batch 27 made the pick-open time a league setting. A round previously became
claimable at whatever moment `run_refresh_slate` happened to write it, which was
neither announced nor the same each week. `leagues.pick_open_offset_minutes`
(nullable) sits beside `lock_offset_minutes` and is measured back from the same
anchor, so a bigger number is earlier and the two must satisfy
`pick_open >= lock`. `gameweeks.picks_open_at_utc` is the derived instant, frozen
at discovery and never re-derived, so editing the setting cannot move a deadline
members were already told. `GameweekStatus` gained `scheduled` for a round that
exists but has not opened, and `pick_refusal` is now the single gate, answering
`PICKS_NOT_OPEN` as well as `PICKS_LOCKED`. Time decides both ends and `status`
is only the label the hourly open/lock jobs keep up with. `NULL` preserves the
old behaviour exactly, so migration 012 needs no backfill and no existing league
changes. The offset stays off `SlateWindow` on purpose — `discover_fixtures`
groups by window, so putting it there would multiply the provider bill.

## Next

`docs/BUILD_PLAN.md` carries four unchecked batches: **38** (when a pick was
taken), **37** (the competition matcher, which also fixes the blank form/position
strip), **41** (gameweek numbering) and **42** (profile pictures, code-only
against no storage bucket). Batch 40 is deferred
pending a decision on whether `pick_open_offset_minutes` stays forward-only or
gains an admin restamp. Two items sit outside the batches and are owner actions:
**rotating the odds-api.io key** exposed in the logs before Batch 36, and the
production data cleanup Batch 37 needs — mis-matched competitions have been
ingesting Premier League rows and must be cleared before a corrective
`sync-football` sweep.

Launch L5 — launch and first-Saturday watch — is the remaining launch work.
Batch 7 shipped the odds source.
Production is now deployed and configured through Batch 22; Batches 23–27 are
on local `main` pending a `/ship-prod` for the API contract changes from
Batches 23, 25, 26 and 27 (Batch 24 is frontend-only). That ship-prod is
load-bearing rather than optional, and Batch 27 raises the stakes twice over:
home already calls `GET /api/v1/me/cross-league-summary`, which does not exist
on the deployed API, and Batch 27 adds migration `012` plus a `scheduled`
gameweek state the deployed API cannot read. Shipping the web half alone would
leave home empty and the new pick-open control writing to a field production
does not have. What remains:

- ~~seal `ODDS_API_KEY` into production and confirm `ODDS_PROVIDER=oddsapi`~~ — done;
- ~~ship staging and then production~~ — production is at `13560cdb` / migration `012`;
- migrate staging from the deprecated `BF_FAKE_MODE` to `ODDS_PROVIDER=fake`;
- re-run `.launch-private/weekend-fixtures.py` against the launch Saturday;
- ~~decide whether to enable the football-data provider~~ — enabled;
  `FOOTBALL_DATA_PROVIDER=apifootball` with `FOOTBALL_API_KEY` sealed 2026-08-15.
  What remains is a `/ship-prod` for Batch 33 and a `sync-football` run, then
  reading the catalogue log to learn what the free plan actually carries;
- **rotate `ODDS_API_KEY`.** Beyond the two exposures already recorded, `httpx`
  logs the full request URL at INFO and the key is a query parameter, so
  production has been printing it in cleartext on every odds call — hundreds a
  day in Railway's log store. Redacting the log is code work; the rotation is the
  owner's;
- **delete the `BF_*` variables from Railway production.** `BF_USER`, `BF_PASS`,
  both PEM blobs and `BF_APP_KEY` are still set and are only read when
  `ODDS_PROVIDER=betfair`, which production does not use. A `BF_PASS` for a live
  Betfair account is sitting in an environment that has no use for it.

The `BF_*` variables and the Betfair certificate are no longer required in
production; they apply only if `ODDS_PROVIDER=betfair` is ever selected.

Build batches use `/batch-start <N>`, `/batch-verify <N>`, and
`/phase-closeout <N>`; launch phases use `/launch-start <L0-L5>`,
`/launch-verify <L0-L5>`, and explicit `/launch-closeout <L0-L5>`.

Two carried follow-ups: the administrator PIN is a known value and must be
changed at first login, and the `odds-api.io` key **must** be rotated — it was
shared during scoping and was printed in a request URL during Batch 7
verification.

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
