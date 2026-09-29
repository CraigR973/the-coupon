#!/usr/bin/env bash
# Serve corr_server:app on 8120 against the scratch DB held by `stack.py --name corr --no-api`.
#   bash corr_api.sh   (run in the background; SIGTERM to stop)
set -euo pipefail
SCRATCH=/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad
NOTES=/Users/craigrobinson/the-coupon/docs/review/2026-09-28/notes/02-correctness
PY=$HOME/.cache/the-coupon/ci-local-venv/bin/python
DB=$("$PY" -c "import json;print(json.load(open('$SCRATCH/stack-corr.json'))['database_url'])")
export DATABASE_URL="$DB"
export JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters"
export JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters"
export FOOTBALL_DATA_PROVIDER=none SCHEDULER_ENABLED=false ODDS_PROVIDER=fake FRONTEND_ORIGIN=http://127.0.0.1:4320
export VAPID_PUBLIC_KEY=review-dummy-public VAPID_PRIVATE_KEY=review-dummy-private
export PYTHONPATH="/Users/craigrobinson/the-coupon/apps/api:$NOTES"
unset ENVIRONMENT || true
exec "$PY" -m uvicorn corr_server:app --host 127.0.0.1 --port 8120 --app-dir "$NOTES"
