# Status — The Coupon

## Now

Build batches 1–21 and 28 are closed. Batch 28 intentionally ran ahead of the
remaining feedback batches because football ingestion was dark in production;
Batch 22 is the next unchecked build batch. The Coupon is a verified private
weekly football accumulator PWA: members sign in with display name and
PIN, claim one unique Saturday selection, score frozen odds after settlement,
compare standings, and view the shared combined coupon.

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

**Production runs `634467c8` on both stacks as of 2026-08-15**, at migration
`011`. `/api/v1/health` reports that commit and the migration head bundled in
the image, so `scripts/check-deploy-drift.sh` now answers exactly (`in sync`)
rather than falling back to probing. `ODDS_API_KEY` is sealed,
`ODDS_PROVIDER=oddsapi`, and `SCHEDULER_ENABLED=true`; the paragraph above about
a Betfair build and an unsealed key described the state before the 2026-08-04
and 2026-08-06 shipments.

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

Batch 28 fixed API-Football ingestion rate limiting, deliberately ahead of
Batch 22. API-Football's free plan is not just 100/day; it is also 10/minute,
and the minute limit arrives as HTTP 200 with `errors.rateLimit`, so the old
429/5xx retry path never ran and the two-requests-per-competition sweep burned
through the minute allowance in seconds. The adapter now treats `rateLimit` as a
transient body error, and the scheduled sync spaces competition attempts by a
configurable 12 seconds so a 30-competition sweep takes about six minutes.
ADR 0003 now records both limits.

## Verified

- Backend: 382 pytest (467 with a database), Ruff check/format, and strict mypy;
  Batch 28 close-out also passed `scripts/ci-local.sh` end-to-end (11 checks)
- Database: clean `pgserver` migration through revision `011`, including a pre-009 backfill, a 009 downgrade round-trip, and a 010 up/down round-trip, with forced RLS
  on all 13 public tables under a Supabase-like role setup
- Frontend: Node 20 production build, TypeScript, ESLint, and 235 Vitest
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

## Next

Batch 22 — Wayfinding and layout — is the first unchecked build batch in
`docs/BUILD_PLAN.md`. Launch L5 — launch and first-Saturday watch — remains
open too. Batch 7 shipped the odds source. Production is now deployed and
configured through Batch 21; what remains:

- ~~seal `ODDS_API_KEY` into production and confirm `ODDS_PROVIDER=oddsapi`~~ — done;
- ~~ship staging and then production~~ — production is at `aae3b51e` / migration `011`;
- migrate staging from the deprecated `BF_FAKE_MODE` to `ODDS_PROVIDER=fake`;
- re-run `.launch-private/weekend-fixtures.py` against the launch Saturday;
- decide whether to enable the football-data provider — `FOOTBALL_DATA_PROVIDER`
  is unsealed so it defaults to `none`, which leaves Batch 16's tables, results
  and form surfaces empty (not broken). Enabling it needs an api-sports.io key
  sealed as `FOOTBALL_API_KEY`.

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
