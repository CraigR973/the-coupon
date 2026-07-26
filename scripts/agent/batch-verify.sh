#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/craigrobinson/the-coupon"
PY_TOOLS="/Users/craigrobinson/app-starter/apps/api/.venv/bin"
NODE_PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
BATCH="${1:-batch}"

PYTHONPATH="$ROOT/apps/api" "$PY_TOOLS/ruff" check "$ROOT/apps/api"
PYTHONPATH="$ROOT/apps/api" "$PY_TOOLS/ruff" format --check "$ROOT/apps/api"
PYTHONPATH="$ROOT/apps/api" "$PY_TOOLS/mypy" "$ROOT/apps/api/src"
PYTHONPATH="$ROOT/apps/api" "$PY_TOOLS/python" -m pytest "$ROOT/apps/api/tests"

PATH="$NODE_PATH" pnpm --dir "$ROOT/apps/web" lint
PATH="$NODE_PATH" pnpm --dir "$ROOT/apps/web" typecheck
PATH="$NODE_PATH" pnpm --dir "$ROOT/apps/web" build
PATH="$NODE_PATH" pnpm --dir "$ROOT/apps/web" test

echo "Local code gate for Batch $BATCH is green."
echo "Run any required scratch-database and browser checks before close-out."
