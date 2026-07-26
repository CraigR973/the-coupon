# Status — The Coupon

## Now

All six build batches are closed on local `main`. The Coupon is a verified
private weekly football accumulator PWA: members sign in with display name and
PIN, claim one unique Saturday selection, score frozen odds after settlement,
compare standings, and view the shared combined coupon.

Batch 6 completed the product rebrand, removed inherited surfaces, corrected
the frontend auth and invite wiring, and added a deterministic production-
preview browser flow backed by scratch PostgreSQL and `FakeBetfair`.

## Verified

- Backend: 149 pytest, Ruff check/format, and strict mypy
- Database: clean `pgserver` migration to head with only Coupon-domain tables
- Frontend: Node 20 production build, TypeScript, ESLint, and 168 Vitest
- Browser: three-member uniqueness, lock, settlement, standings, and combined
  4.56 accumulator against real PostgreSQL and canned Betfair data
- Repository: inherited-name and stale-file audit clean

The owner's real Betfair session remains outside agent automation and should be
checked immediately before launch.

## Next

Launch planning: provision the fresh production services and domain, seed the
real league membership, configure secrets, and run the owner-only live Betfair
slate check. See the launch gates in `docs/BUILD_PLAN.md`.

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
