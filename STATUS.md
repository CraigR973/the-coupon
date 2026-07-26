# Status — The Coupon

## Now

Batch 5 is closed on local `main` at `9ca4c8e`. Batch 6 is in progress on
`feat/batch-6-verify-rebrand`.

The backend provides display-name + PIN auth, leagues and memberships, weekly
gameweeks and fixtures, unique picks, frozen odds, settlement, standings, and a
combined coupon. The frontend provides the weekly pick screen, combined coupon,
standings, league management, settings, and the PWA shell.

## Verification target

Batch 6 must leave all of these green:

- Backend pytest, Ruff check/format, and strict mypy
- Alembic upgrade on clean scratch PostgreSQL with only Coupon tables
- Frontend production build, TypeScript, and Vitest
- Playwright browser flow on a real scratch database with `FakeBetfair`
- Repository inherited-name audit

The live Betfair slate check remains owner-only and is not an automated gate.
Do not log into the owner's account.

## Toolchain

- Backend Python tools:
  `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path:
  `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`

See `docs/BUILD_PLAN.md` for acceptance and `session-log.md` for completed-batch
implementation notes.
