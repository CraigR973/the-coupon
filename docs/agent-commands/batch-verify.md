---
description: Run The Coupon's local verification gate.
---

# /batch-verify

`$ARGUMENTS` must identify a batch in `docs/BUILD_PLAN.md`. Read that row and
the Verification section before running checks.

Confirm the current branch is not `main`, then run:

```bash
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/ruff check \
  /Users/craigrobinson/the-coupon/apps/api
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/ruff format --check \
  /Users/craigrobinson/the-coupon/apps/api
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/mypy \
  /Users/craigrobinson/the-coupon/apps/api/src
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/python -m pytest \
  /Users/craigrobinson/the-coupon/apps/api/tests
```

```bash
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" \
  pnpm --dir /Users/craigrobinson/the-coupon/apps/web lint
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" \
  pnpm --dir /Users/craigrobinson/the-coupon/apps/web typecheck
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" \
  pnpm --dir /Users/craigrobinson/the-coupon/apps/web build
PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" \
  pnpm --dir /Users/craigrobinson/the-coupon/apps/web test
```

When database behavior is in scope, use a clean pip `pgserver` instance, run
`alembic upgrade head`, then rerun pytest with `DATABASE_URL` set. When browser
behavior is in scope, run the production-preview Playwright flow and retain its
screenshots.

Report every command and result. Do not commit or merge; close-out remains a
separate user-triggered action.
