# Status — The Coupon

## Now

Build batches 1–10 are closed. The Coupon is a verified private weekly
football accumulator PWA: members sign in with display name and
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

**Production is not yet playable, but the blocker is now deployment, not code.**
The odds source works: verified live for Saturday 2026-08-08, `odds-api.io`
carries 30 UK leagues, 131 qualifying 15:00 fixtures, and 280 distinct priced
selections against the 15 a full league needs, with both Scottish lower
divisions fully priced. Production still runs the Betfair build and has no
`ODDS_API_KEY` sealed, so the slate-refresh job keeps failing until Batch 7 is
deployed and configured.

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

## Verified

- Backend: 289 pytest (307 with a database), Ruff check/format, and strict mypy
- Database: clean `pgserver` migration through revision `008`, with forced RLS
  on all 13 public tables under a Supabase-like role setup
- Frontend: Node 20 production build, TypeScript, ESLint, and 180 Vitest
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

Batch 11 — Daily slate pre-fetch is the next unchecked build batch. In parallel,
Launch L5 — launch and first-Saturday watch. Batch 7 shipped the odds source,
so the remaining launch work is deployment and configuration:

- seal `ODDS_API_KEY` into production and confirm `ODDS_PROVIDER=oddsapi`;
- migrate staging from the deprecated `BF_FAKE_MODE` to `ODDS_PROVIDER=fake`;
- ship staging and then production, which runs migration `005`;
- re-run `.launch-private/weekend-fixtures.py` against the launch Saturday.

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
