# Status — The Coupon

## Now

All six build batches are closed. The Coupon is a verified private weekly
football accumulator PWA: members sign in with display name and
PIN, claim one unique Saturday selection, score frozen odds after settlement,
compare standings, and view the shared combined coupon.

Batch 6 completed the product rebrand, removed inherited surfaces, corrected
the frontend auth and invite wiring, and added a deterministic production-
preview browser flow backed by scratch PostgreSQL and `FakeBetfair`.

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

**Production is not yet playable.** Betfair refuses the production login with
`BETTING_RESTRICTED_LOCATION`: Railway serves only the Netherlands, the USA,
and Singapore, and Betfair Exchange is unavailable in all three, so no region
change resolves it. The scheduler's slate-refresh job therefore fails on every
run and no gameweek, fixture, or pick can exist until Batch 7 replaces the
odds source. Every other service and scheduled job is healthy.

Launch also ships with **no database backup**, by owner decision recorded in
`docs/launch/L0_PROJECT_IDENTITY.md`.

## Verified

- Backend: 176 pytest, Ruff check/format, and strict mypy
- Database: clean `pgserver` migration through revision `004`, with forced RLS
  on all 13 public tables under a Supabase-like role setup
- Frontend: Node 20 production build, TypeScript, ESLint, and 160 Vitest
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

Batch 7 — replace the Betfair Exchange with `odds-api.io` priced by Bet365.
This is required rather than optional: Betfair is geo-blocked from every
Railway region, so it is the only way production can obtain odds. It also
closes the coverage gap, since the Exchange never priced the Scottish lower
divisions. Scope and verified evidence are in
`docs/adr/0002-replace-betfair-exchange-with-odds-api-io.md`.

Then L5 launch and first-Saturday watch. Build batches use `/batch-start <N>`,
`/batch-verify <N>`, and `/phase-closeout <N>`; launch phases use
`/launch-start <L0-L5>`, `/launch-verify <L0-L5>`, and explicit
`/launch-closeout <L0-L5>`.

Two carried follow-ups: the administrator PIN is a known value and must be
changed at first login, and the `odds-api.io` key shared during scoping should
be rotated.

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
