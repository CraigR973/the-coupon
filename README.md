# The Coupon

The Coupon is a private weekly football accumulator game for friends. Each
leaderboard opens one Saturday 3pm slate, every member claims one unique priced
selection, and winning picks score `round(odds × 10)` points. The combined
coupon shows every member's frozen pick as one accumulator.

The game is for points and fun; it does not place bets or handle money.

## Stack

- React 18, TypeScript, Tailwind CSS, Vite, and PWA support
- FastAPI, SQLAlchemy, Alembic, and PostgreSQL
- Betfair Exchange adapter with a fully canned test implementation

## Repository

```text
apps/api/       FastAPI backend and tests
apps/web/       React PWA, unit tests, and Playwright verification
migrations/     Alembic migrations
docs/           Build plan and agent workflows
```

`docs/BUILD_PLAN.md` is the product and batch source of record.

## Local setup

Requirements: Node 20, pnpm 9, Python 3.12, and PostgreSQL.

```bash
cp .env.example .env
pnpm install
```

This repository intentionally has no Python virtual environment. The local
toolchain uses the sibling template environment:

```bash
export PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api
/Users/craigrobinson/app-starter/apps/api/.venv/bin/python -m alembic \
  -c /Users/craigrobinson/the-coupon/apps/api/alembic.ini upgrade head
/Users/craigrobinson/app-starter/apps/api/.venv/bin/python -m uvicorn \
  src.main:app --app-dir /Users/craigrobinson/the-coupon/apps/api --reload
```

In another terminal:

```bash
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" \
  pnpm --dir /Users/craigrobinson/the-coupon/apps/web dev
```

Use the canned Betfair adapter for automated tests. Live Betfair access is a
manual owner-only check because the account is money-linked.

## Verification

See `docs/agent-commands/batch-verify.md` for the exact backend, database,
frontend, and browser checks.

## License

MIT
