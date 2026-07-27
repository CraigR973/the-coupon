# Status — The Coupon

## Now

All six build batches are closed on local `main`. The Coupon is a verified
private weekly football accumulator PWA: members sign in with display name and
PIN, claim one unique Saturday selection, score frozen odds after settlement,
compare standings, and view the shared combined coupon.

Batch 6 completed the product rebrand, removed inherited surfaces, corrected
the frontend auth and invite wiring, and added a deterministic production-
preview browser flow backed by scratch PostgreSQL and `FakeBetfair`.

Launch phase L0 now records the private repository, fresh project names and
owner accounts, no-cost platform hostname strategy, regions, budget controls,
15-player roster handling, and connector boundaries.

Launch phase L1 is implemented and locally verified on
`feat/launch-l1-hardening`. The launch path now uses Railway's native Nixpacks
builder, not local container tooling.

## Verified

- Backend: 149 pytest, Ruff check/format, and strict mypy
- Database: clean `pgserver` migration to head with only Coupon-domain tables
- Frontend: Node 20 production build, TypeScript, ESLint, and 168 Vitest
- Browser: three-member uniqueness, lock, settlement, standings, and combined
  4.56 accumulator against real PostgreSQL and canned Betfair data
- Repository: inherited-name and stale-file audit clean
- Launch L0: owner-approved public GitHub origin, explicit fresh platform
  targets, docs-only Supabase MCP, and recorded owner decisions
- Launch L1: durable PIN lockout, inactive-login rejection, removed avatar
  upload/passwordless activation/public reset/Sentry surfaces, staging-only
  `FakeBetfair`, Betfair certificate-login support, scheduler retries,
  migration-level Supabase Data API lockdown, deployment runbooks, CI coverage,
  and clean PostgreSQL-backed tests

The owner's real Betfair session remains outside agent automation and should be
checked immediately before launch.

## Next

L2 fresh staging infrastructure. Provision only the documented fresh Supabase,
Railway, and Vercel staging targets; keep staging separate from production and
use the repo-root Railway/Nixpacks backend service. Launch phases use
`/launch-start <L0-L5>`, `/launch-verify <L0-L5>`, and explicit
`/launch-closeout <L0-L5>`.

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
