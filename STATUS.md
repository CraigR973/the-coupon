# Status — The Coupon

## Now

Batches 1-51 are closed. The Coupon is a verified
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

Batch 38 made the coupon say *when* a selection was taken, not just who by.
`Pick.created_at` had always been on the row and nothing carried it out. The
field is additive and optional on the client, because Vercel deploys the web app
from `main` while the API waits for `/ship-prod` — a renamed or required field
would break the coupon in that gap.

Batch 42 modelled profile pictures without enabling them, and Batch 44 met the
three conditions it recorded. Uploaded bytes are now **re-encoded** — Pillow
decodes the image and a fresh WebP is written from the pixels, so a payload
riding behind a valid PNG signature does not survive, and a decompression bomb
is refused from its header before a pixel is decoded. The bucket's access rules
are written explicitly (ADR 0006): public-read with an unguessable object key,
because the private-and-signed alternative turns `avatar_url` into a stored path
and every member list into a round trip per picture. Removal already existed on
both sides. **The feature is complete and still switched off**: `AVATAR_STORAGE`
defaults to `none`, so every environment answers 503 exactly as before, and
`GET /api/v1/config` tells the web app to leave the upload card unmounted.
Turning it on is `docs/runbooks/avatar-storage.md` and it is an **owner action** —
it needs the Supabase dashboard and seals a service-role key. This narrows, and
does not overturn, the launch-plan decision to use Supabase as managed
PostgreSQL only: Storage, one bucket, one feature, API-side only.

Batch 43 stamped the UTC offset on every instant the API sends. The columns are
naive UTC and the backend compares naive to naive correctly throughout, but
pydantic rendered that as `2026-08-22T13:30:00` and JavaScript reads an
offset-less date-time as *local* time, so the wall-clock number displayed
equalled the stored UTC number in every zone — a 14:30 London lock shown as
13:30. The countdown ran on the same mis-parsed instant and `locked` derives
from it, so **the pick screen shut an hour before the API stopped taking
picks**. Invisible from late October to late March, and it returns without a
deploy. `UtcDatetime` is applied at the API boundary and a test walks the app's
own routes so a later model cannot miss it. The client parses defensively too,
because Vercel deploys `main` on merge while the API waits for `/ship-prod` —
**until that ship-prod runs, the client half is the only half in production.**
`starts_on` is now rendered as the calendar date it is rather than converted
into a zone, which had announced the round a day early west of UTC. The test
runner's zone is pinned to `America/New_York`: in a UTC process a mis-parsed
instant and a correct one are the same number, which is why 325 green tests
never saw this.

Batch 41 gave the round a name. The coupon showed a date where members expect
"Gameweek N" and no number existed to show; migration 014 adds one and backfills
per league, per season, in `starts_on` order. It is stored rather than derived
because Batch 35 made a one-off round legitimate, and an ordinal recomputed on
read renumbers every round after it the moment one is inserted — a member's
"Gameweek 12" would become a different week. A one-off simply takes the next
number. The number is a display concern only: nothing in locking, settlement or
scoring keys on it, and every read falls back to the date when it is absent.

Batch 37 stopped a lower division resolving to the Premier League. `similarity`
awarded a flat subset bonus whenever one name's tokens sat inside the other's,
so "Southern League, Premier Division South" scored 0.950 against England's top
flight and 0.800 against its real counterpart — the wrong answer above threshold
and the right one below it, confidently and uniquely, so no ambiguity margin
could catch it. The bonus is now withheld on the competition path only (it is
load-bearing for club names), `MATCH_MARGIN` is applied where it never was, and
four divisions the two catalogues do not name alike carry an explicit override
read from both live catalogues. Coverage was never the problem: a probe on
2026-08-19 confirmed the free plan *lists* every British division for season
2026 — what it does not do is serve their standings, which the 2026-08-20 sweep
established the day after. The corrective data cleanup this paragraph used to
say was owed is not: the tables were empty then and are empty now, so there is
nothing mis-ingested to clear. Batch 40 is no longer deferred — it closed on
2026-08-20 by taking the forward-only rule.

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

**Production runs `1272dde` on both stacks as of 2026-08-21**, at migration
`015` — Railway `854a24ec`, Vercel `dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE`. That
shipment carried Batches 47 and 48, closing the gap the Batch 48 close-out had
left: the new-league-rounds fix and the odds-provider-degradation fix are both
now live, and `main` and the API agree again. `/api/v1/health` reports that
commit and the migration head bundled in the image, so
`scripts/check-deploy-drift.sh` answers exactly (`in sync`) rather than falling
back to probing. `ODDS_API_KEY` is sealed and rotated, `ODDS_PROVIDER=oddsapi`,
and `SCHEDULER_ENABLED=true`; the paragraph above about a Betfair build and an
unsealed key described the state before the 2026-08-04 and 2026-08-06
shipments.

That shipment took 91 minutes for reasons that were **not** the build: Railway
paused deploys platform-wide while the container was already running, so the
`HEALTHCHECK` deployment event hung for 83 minutes past its own 300-second
timeout before completing on its own. `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`
records how to recognise it — a stalled step with a healthy container is a
platform problem, and `railway up` refuses outright with
`Deploys have been paused due to an upstream issue`. Production served the
previous deployment throughout. Note that a stall of that kind leaves **two
schedulers running**; nothing double-fired here, but it would have reached the
11:00 pick reminders had it lasted the night.

The football-data provider is **switched off in production**
(`FOOTBALL_DATA_PROVIDER=none`, owner decision 2026-08-20), and the Football tab
is empty because there is nothing to show it. That closes a question this file
carried for weeks. Batch 16 built the feature, Batch 28 found the undocumented
10/minute ceiling, and Batch 33 found what that was hiding in the catalogue —
but the 2026-08-20 sweep, the first to get past all three, answered the real one:
**api-football's Free plan carries no season after 2024.** Not the lower
British divisions — *nothing*, the Premier League included. All 18 competitions
that resolved a league id were rejected at `/standings` with *"Free plans do not
have access to this season, try from 2022 to 2024"*; the remaining 3 are cups
that resolve no id and have no table anyway.

A follow-up probe the same day, run with the sealed key via `railway run`, showed
that the sweep had understated it twice. The refusal is **plan-wide, not a
`/standings` problem**: `/fixtures` and `/teams` refuse season 2026 with the
identical error, and `/fixtures` with a date window and no season is rejected
outright (*"The Season field is required"*), so there is no way round the gate.
And **season 2025 is refused too** — the most recent data the plan can reach is
2024/25, which ended 2025-05-25, two seasons back. The key is valid, the plan is
active to 2027-07-24, and season 2024 returns a complete table. This is an
entitlement wall, not a defect, and no amount of code fixes it.

`teams`, `team_aliases`, `matches` and `standings` are empty and have never held
a row, in any environment. The team-matching defect this was read as does not
exist: `/standings` fails before a single team is stored, so the candidate list
is empty and `candidates=0` follows from that, not from a name that failed to
match. Anyone reopening this should start at the plan, not the matcher.

That question now has an answer: **FotMob replaces api-football as the
football-data provider** (ADR 0007, owner decision 2026-08-20), scoped as Batch
46. It was the only free source found that carries the English step 6-7
divisions — National League North and South, Southern Premier Central and South,
Northern Premier, Isthmian Premier — which are 203 fixtures, **49% of the card**.
FotMob carries 17 of the 18 leagues and 368 of the 389 league fixtures, missing
only `northern-ireland-championship-1`. The alternatives were measured, not
assumed: football-data.org's free tier is 12 competitions (British ones the
Premier League and Championship only), TheSportsDB truncates every table to five
rows, and football-data.co.uk publishes no tables at all.

The trade is recorded rather than glossed. FotMob's terms prohibit automated
access, and its interface is undocumented and moves — `/api/leagues?id=47`
already 404s, and the working path is `/api/data/allLeagues`. ADR 0007 holds both,
and TheSportsDB at roughly $9/month is the measured fallback.

Turning it back on stays one variable (`FOOTBALL_DATA_PROVIDER=fotmob`) but now
waits on Batch 46's adapter. Pinning `FOOTBALL_SEASON` to 2024 was never the
workaround it looked like — it would render tables and form from **two** seasons
back against 2026/27 fixtures.

Batch 45 fixed the reason this took so long to see. The sweep failed all 21
competitions, logged `football data synced`, and exited `0`, because
`run_sync_football_data` returned `True` on any run that reached the provider —
so the 06:30 cron reported a healthy run every morning while ingesting nothing.
A list of reports could never answer the question: a competition that *raised*
leaves no report, so an empty list meant both "the card was empty" and "every
competition failed". The sweep now carries how much of the card it attempted,
and a run that attempted a non-empty card and carried none of it is a failure —
which `run_scheduled` already turns into a non-zero exit. The per-competition
tolerance is untouched: one division the provider dropped still must not cost
the other twenty-nine their tables.

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

Batch 47 gave a new league its rounds at creation. Discovery runs once a day at
06:00, so a league created at any other hour had no round, no card and no coupon
until the next morning, and the only remedy was `discover-fixtures` inside the
production container — an owner action for a problem every admin hits. It is
nearly free, because `discover_fixtures` already fetches each `(window, date)`
once and shares it: `pooled_slate` reads a window's card back out of the shared
`fixtures` pool, so a league on the default Saturday everyone else plays is
`sync_slate` against rows that exist and costs **zero** provider requests.
`populate_cadence_rounds` walks the cadence and nothing else — an off-cadence
date belongs to the league that asked for it — and falls back to a real fetch
only where the pool is empty. That fallback is charged one unit per sweep to
`PROVIDER_SLATE_FETCH_LIMIT`, the ad-hoc round endpoint's `2/hour;3/day` renamed
now that three routes share it, through `limiter.shared_limit` on the route and
`consume_shared_limit` in the populate path, so the two cannot be combined to
exceed the budget and a pooled populate charges nothing. The same path is an
admin action — `POST /leagues/{slug}/gameweeks/refresh` and a Rounds card on
league settings — because an admin who moves the fixture window has rounds built
against the old one. Creation resolves the provider through a new
`OptionalOddsProviderDep`, so a provider outage leaves a league with no rounds
*yet* rather than failing the creation. Both ends of a round's claim period stay
stamped as created, and a locked or settled round is skipped rather than rebuilt.
No migration, and `discover_fixtures` keeps its cadence-union-off-cadence
behaviour exactly as Batch 35 left it.

Batch 48 stopped the pick screen dying with the odds provider. `_live_odds` called
`fetch_odds` with no fallback, so any provider failure propagated and
`GET /leagues/{slug}/gameweek/current` returned 500 — the screen every member opens to
make their pick had its availability wired to a third party's rate limit. Observed in
production on 2026-08-21, the day before launch, when `/odds/multi` answered `429` and
the Football tab beside it kept working because it reads only the database. The cache
already held the remedy: when an upstream call raises, its entries are still there,
merely past their TTL. `fetch_odds_best_effort` catches the failure and falls through to
them, returning an `OddsSnapshot(odds, degraded)` — last known prices, or a card with no
prices at all, which still shows the fixtures. **The pick path is untouched and still
raises**, because a winner scores `round(odds x 10)` from the price frozen at that
instant, so a stale one is not a degraded pick but a wrong score; an unreachable provider
now refuses the submission with `503 ODDS_UNAVAILABLE` rather than crashing. `_get` no
longer retries a `429`: retrying "you are over budget" is the one response guaranteed to
keep you over it, and the three retries with doubling backoff turned a single rate-limited
slate load into four upstream calls, which is how that afternoon's breach sustained
itself. 5xx and network errors retry as before. The slate carries `odds_degraded` and the
pick screen says "prices may be out of date" — additive and optional, because Vercel
deploys `main` on merge while the API waits for `/ship-prod`. No schema change, and the
TTL tiers are untouched.

Batch 49 stopped a called-off fixture staying pickable. `sync_slate` said it
outright — "Links are added, never removed" — so a fixture postponed after
discovery stayed on every round that had linked it and stayed claimable right
through the deadline, because nothing between discovery and the evening settle
sweep read the provider's status: `fetch_slate` built each `SlateFixture` from
the teams and the kick-off and dropped the rest, while `_VOID_STATUSES` was
consulted only by `_settlement_for`, hours after the round had been played.
`SlateFixture` now carries the provider's own word verbatim, the void vocabulary
moved to `odds_provider` so discovery and settlement cannot disagree about what a
postponement is, and `_drop_voided_fixtures` takes the link *and* the pick off an
open round — two deletes, because `gameweek_fixtures` is a composite-key join
with no cascade to `picks`, so unlinking alone leaves a pick off the screen and
still visible to settlement. It stops at the lock, gated on `locks_at_utc` rather
than the status label: a member who picked before the deadline cannot respond
after it, and settlement already writes `void` for exactly this status. Absence
never removes anything — a partial or failed fetch is indistinguishable from a
quiet one — so only an explicit status acts, and the empty default means a
Betfair catalogue and a pooled rebuild cannot unlink at all. The member is told
via a free-form `fixture_postponed` push and left with *no pick*, the one state
the game already understands. **Live probing found a third answer the plan had
not anticipated:** odds-api.io does emit void words (2 of 1,599 fixtures for
2026-08-22 came back `cancelled`) but was still returning the Hibernian v
Kilmarnock fixture as `pending` after it had been called off — so this closes the
general case, not the observed one, and settlement remains the backstop. No
migration: the status rides the DTO, because the pooled row stays for the leagues
still linking it.

Batch 50 fixed three omissions on the pick card, frontend-only. The context
strip and the team names now share one `grid-cols-2` container instead of an
inline sentence sitting over a separate grid, so a club's form aligns under
its name by construction rather than by text-length coincidence. The "Your
pick" summary on `CouponPickPage` now names the competition, matching
`CombinedAccaView`'s per-leg format. And `potentialPoints()` — a pure
`round(odds × 10)` of the displayed price — now stays visible alongside
"taken by X" and "your pick", not just on an unclaimed selection.

Batch 51 untied Football Stats from a league. The tables and results screen read
`/leagues/{slug}/football/…` and narrowed to the competitions that league plays,
which was never what it is for: a member opens it to look at football, not at the
subset of football their own coupon covers. **The data was never league-scoped —
only the read was.** `pooled_competitions` already walked the whole shared fixture
pool and `teams` / `matches` / `standings` carry no league column, so untying it
cost nothing upstream: no ingestion change, no migration, and the 100-a-day
API-Football budget is untouched. `/api/v1/football/tables` and `/results` now
take no slug and are gated on an authenticated player rather than
`LeagueMemberDep` — the router's own docstring had already conceded that gate was
consistency rather than privacy. The old routes and `league_competitions()` are
deleted rather than left dead. Because `CouponSubNav` is explicitly league-bound,
the tab left it for a top-level `/football`, and `LeagueSwitchStrip` came off the
page, where it would have been a control that changed nothing; the two old
addresses redirect. Renamed **Football Stats** while the nav was being edited —
57.7px in a 75px tab at 375px and a 64px tab at 320px, so it stays on one line on
the narrowest phone. One limit is recorded in the empty states: the pool holds
only competitions some league's card has drawn from, so "untied" means every
competition we have ever ingested, not every competition in Britain.

## Verified

- Backend: 655 pytest with a database, Ruff check/format, and
  strict mypy; Batch 51 close-out passed `scripts/ci-local.sh` end-to-end
  (11 checks), as every close-out since Batch 26 has. That script's pinned venv **is**
  the gate: app-starter's venv can no longer even collect the suite (no Pillow, so
  `avatar_storage.py` takes ten test files down with it) and `AGENTS.md` plus
  `docs/agent-commands/batch-verify.md` still document that stale path
- Database: clean `pgserver` migration through revision `013`, including a pre-009 backfill, a 009 downgrade round-trip, and a 010 up/down round-trip, with forced RLS
  on all 18 public tables under a Supabase-like role setup. The count was 13 at
  revision `004`; `009`-`013` added the rest, and every one of the 18 was
  confirmed RLS-enabled *and* forced against production on 2026-08-19, with
  `anon`, `authenticated` and `PUBLIC` holding no table privileges and no schema
  `USAGE`
- Frontend: Node 20 production build, TypeScript, ESLint, and 366 Vitest, the
  suite now pinned to a non-UTC zone (`America/New_York`) so an instant parsed
  as local time cannot pass unnoticed
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

`docs/BUILD_PLAN.md` carries **two unchecked batches**, 52-53, both about what the
screens leave out rather than what the game gets wrong: a table that hides the
Form column on every phone and results grouped by day alone (52); and form pips
that discard the matches behind them despite already holding them (53).

Batch 51 closed the one before those: Football Stats no longer narrows to the
competitions the reader's own league plays, and no longer lives under a slug.
**It is API-side as well as web, and the two halves separate on merge** — Vercel
takes the new top-level `/football` screen immediately, while the deployed API
still serves only `/leagues/{slug}/football/…`, which the untied page does not
call. Until a `/ship-prod` runs, the tab reaches production and its two requests
404. This is the sharper form of the usual gap: the batches before it left
production merely *stale*, this one leaves a screen broken until the API ships.

Batch 50 closed the one before that: the pick card's misaligned form strip,
unnamed competition and vanishing points, all frontend-only with no API change.

Batch 49 closed the one before it: a fixture the provider reports called off now comes
off an open round with the pick on it, before the deadline rather than at the
evening settle sweep. **It is API-side and has not shipped** — Vercel deploys
`main` on merge while the API waits for `/ship-prod`, so production keeps carrying
a postponed fixture on the card until one runs. Batch 48 closed the one before it:
the pick screen no longer dies with the odds provider — a failed refresh is
served from the cache's own entries with an `odds_degraded` flag instead of a
500, the pick path still refuses rather than freezing a price it could not
confirm, and a `429` is no longer retried into four. Batch 47 closed the one
before that: a league created at any hour but 06:00 now gets its cadence rounds
immediately, from the shared fixture pool and usually for no provider requests at
all, with the same path exposed as a "refresh rounds" admin action. **Those two
shipped to production on 2026-08-21** (`1272dde`, Railway `854a24ec`, Vercel
`dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE`); the gap where the API lagged the web half
was closed then and has reopened with Batch 49.

Batch 46 added FotMob as a
third implementation of the football port (ADR 0007) — the first source that
carries the current season, and the only free one reaching the six English step
6-7 divisions that are 49% of the card. It **ships dark**:
`FOOTBALL_DATA_PROVIDER` still defaults to `none`, and turning it on is one
variable plus a staging sweep. The shape that made it interesting is that one
FotMob league id serves up to four of our competitions, the table splits by
group but the match list does not, and the split is recovered by team id rather
than by name. Batch 40 closed the one before it
by taking the **forward-only** rule rather than building an admin restamp: a
2026-08-20 production read showed a single affected round holding zero picks, so
the problem was transitional, not ongoing. What shipped is visibility — the
league settings page now lists the rounds an opening time can still apply to and
says what each will actually do, including the case that reads as "my setting was
ignored", which is a round carrying `picks_open_at_utc = NULL` and therefore no
opening gate at all. The odds-api.io key exposed in the logs
before Batch 36 was rotated by the owner on 2026-08-20. Batch 37's production
data cleanup is no longer owed: `teams`, `team_aliases`, `matches` and
`standings` were confirmed empty in every environment on 2026-08-20 and have
never held a row, so there are no mis-ingested rows to clear.

Launch L5 — launch and first-Saturday watch — is the remaining launch work.
Batch 7 shipped the odds source. Every closed batch through **48** is in
production: the 2026-08-21 shipment of `1272dde` carried Batches 47–48, after
`16a64eff` carried Batch 46 and `33191ba2` carried Batches 43–45. **Batches 49
and 51 are merged and not shipped** — both are API-side, and Vercel takes `main`
on merge while the API waits for `/ship-prod`. Batch 51 is the sharper case: its
web half reaches production immediately and calls `/api/v1/football/tables`,
which the deployed image does not serve, so Football Stats 404s until the API
ships. `scripts/check-deploy-drift.sh` reports the gap. What remains:

- ~~seal `ODDS_API_KEY` into production and confirm `ODDS_PROVIDER=oddsapi`~~ — done;
- ~~ship staging and then production~~ — production is at `33191ba2` / migration `015`;
- ~~migrate staging from the deprecated `BF_FAKE_MODE` to `ODDS_PROVIDER=fake`~~ —
  done 2026-08-20: staging is `ODDS_PROVIDER=fake` and carries no `BF_*` at all;
- ~~re-run `.launch-private/weekend-fixtures.py` against the launch Saturday~~ —
  done 2026-08-20 for **Saturday 2026-08-22**: 134 qualifying 15:00 fixtures, 112
  of them priced, **474 distinct priced selections** against the 15 a full league
  needs. Both Scottish lower divisions price fully; the Premiership is patchy
  (3 of 5 unpriced), which is a bookmaker coverage fact, not a defect. The script
  needed repairing first — it still called the pre-Batch-14 `upcoming_saturday`
  and single-argument `fetch_slate(date)`, so it had been unrunnable since the
  slate window became per-league. Fixed in place; `.launch-private/` is
  gitignored, so that repair lives only on the owner's machine;
- ~~decide whether to enable the football-data provider~~ — **enabled, then
  switched back off on 2026-08-20**: `FOOTBALL_DATA_PROVIDER=none`. The
  `sync-football` run answered what the free plan carries — nothing after season
  2024. The provider question is now settled the other way: **FotMob replaces
  api-football** (ADR 0007, Batch 46), so this stays off until that adapter
  lands rather than until a paid plan is bought. `FOOTBALL_API_KEY` remains
  sealed and valid, and is irrelevant to FotMob;
- ~~rotate `ODDS_API_KEY`~~ — done by the owner on 2026-08-20, after the
  redaction shipped. `httpx` logged the full request URL at INFO and the key is a
  query parameter, so production had been printing it in cleartext on every odds
  call. Both halves are now closed and confirmed in production: `httpx` and
  `httpcore` are quieted to `WARNING`, and a live call with `httpx` forced back
  to `INFO` produced the key **0** times and `<redacted>` **1** time. The same
  call proved the rotated key valid — 63 UK competitions returned;
- ~~delete the `BF_*` variables from Railway production~~ — **done 2026-08-20.**
  All eight are gone from both production and staging. `variable delete` triggers
  no redeploy (verified on staging first), so production stayed on `88c4885c`
  throughout and all 13 required variables are intact. Reversible: every value is
  still in `.launch-private/`, and `seal-production-secrets.sh` re-seals them if
  `ODDS_PROVIDER=betfair` is ever selected again.

The `BF_*` variables and the Betfair certificate are no longer required in
production; they apply only if `ODDS_PROVIDER=betfair` is ever selected.

Build batches use `/batch-start <N>`, `/batch-verify <N>`, and
`/phase-closeout <N>`; launch phases use `/launch-start <L0-L5>`,
`/launch-verify <L0-L5>`, and explicit `/launch-closeout <L0-L5>`.

Both carried follow-ups are now closed. The `odds-api.io` key was rotated by the
owner on 2026-08-20 after the Batch 36 redaction shipped. The administrator PIN
is no longer the known bootstrap value: a login attempt with `roster.json`'s PIN
was refused against production on 2026-08-20, which is the evidence it was
changed. (That attempt incremented `failed_login_count` to 1 of 5 and it was
reset to 0 immediately — do not probe this by guessing, the lockout is durable
and locking the owner out before a Saturday is the worse failure.)

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
