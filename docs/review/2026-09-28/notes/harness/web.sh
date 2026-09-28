#!/usr/bin/env bash
# Build the production web bundle against a local API and serve it on a strict port.
#   bash web.sh <name> <api-origin> <web-port>
# Builds into <scratchpad>/web-<name> (never apps/web/dist, which the gate owns), with
# VITE_API_URL in the process environment — Vite gives that precedence over
# apps/web/.env.local, which points at another product's API.
set -euo pipefail
NAME="$1"; API="$2"; PORT="$3"
ROOT=/Users/craigrobinson/the-coupon
SCRATCH="${REVIEW_SCRATCH:-/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad}"
OUT="$SCRATCH/web-$NAME"
. "$HOME/.nvm/nvm.sh" >/dev/null && nvm use 24 --silent
VITE_API_URL="$API" node "$ROOT/apps/web/node_modules/vite/bin/vite.js" build "$ROOT/apps/web" \
  --outDir "$OUT" --emptyOutDir >"$SCRATCH/web-$NAME.build.log" 2>&1
grep -rl "$API" "$OUT/assets" >/dev/null || { echo "bundle does not reference $API" >&2; exit 1; }
exec node "$ROOT/apps/web/node_modules/vite/bin/vite.js" preview "$ROOT/apps/web" \
  --outDir "$OUT" --host 127.0.0.1 --port "$PORT" --strictPort
