---
description: Run The Coupon's local verification gate.
---

# /batch-verify

`$ARGUMENTS` must identify a batch in `docs/BUILD_PLAN.md`. Read that row and
the Verification section before running checks.

Confirm the current branch is not `main`, then run:

**Ruff — use the version CI pins, not the shared venv's.** The venv this repo
borrows (app-starter's) ships a much newer ruff than `requirements-dev.txt`
pins, and the two disagree about formatting. Because `ruff format --check` is
the *first* backend step in `.github/workflows/ci.yml`, a disagreement fails the
job before `mypy`, `alembic upgrade head`, and `pytest` ever run — so a green
local gate can hide a red main entirely. That happened across Batches 11-13.

Take the version from the pin itself so this cannot drift when the pin changes:

```bash
RUFF="ruff==$(sed -n 's/^ruff==//p' /Users/craigrobinson/the-coupon/apps/api/requirements-dev.txt)"
uvx "$RUFF" check /Users/craigrobinson/the-coupon/apps/api
uvx "$RUFF" format --check /Users/craigrobinson/the-coupon/apps/api
```

`uvx` fetches and caches the pinned build; it needs no venv, because ruff does
not need the project's dependencies the way mypy does. Passing the directory
rather than `.` keeps the "never `cd`" rule and still finds
`apps/api/pyproject.toml`, so the non-default `line-length = 100` applies.

Then the rest, from the shared venv:

```bash
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/mypy \
  /Users/craigrobinson/the-coupon/apps/api/src
PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api \
  /Users/craigrobinson/app-starter/apps/api/.venv/bin/python -m pytest \
  /Users/craigrobinson/the-coupon/apps/api/tests
```

`pytest` matches the pin exactly. **`mypy` does not** — the pin is `1.11.0` and
the venv runs 2.x. Both currently pass, so this is a divergence to know about
rather than a break to fix; reproducing the pinned mypy locally means building
the whole dependency tree from source, which is slower and less reliable than
the CI run that already checks it. If mypy ever fails in CI but passes locally,
this is why.

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
