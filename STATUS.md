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
now provides fresh, isolated Supabase, Railway, and Vercel staging targets,
with stable web/API origins and a target-specific shipment workflow.

## Verified

- Backend: 158 pytest, Ruff check/format, and strict mypy
- Database: clean `pgserver` migration through revision `004`, with forced RLS
  on all 13 public tables under a Supabase-like role setup
- Frontend: Node 20 production build, TypeScript, ESLint, and 159 Vitest
- Browser: production-bundle smoke plus live staging root and SPA deep-link
  refresh checks
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

The owner's real Betfair session remains outside agent automation and should be
checked immediately before launch.

## Next

L3 staging verification. Exercise the complete canned-odds browser story,
confirm one scheduler execution per job, scan platform logs, rehearse a
disposable restore, and verify push on a supported real device. Launch phases use
`/launch-start <L0-L5>`, `/launch-verify <L0-L5>`, and explicit
`/launch-closeout <L0-L5>`.

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
