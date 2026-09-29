#!/usr/bin/env bash
# Run a notes script against the perf scratch DB with the gate venv:  bash run.sh script.py args...
S=/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad
export DATABASE_URL=$(python3 -c "import json;print(json.load(open('$S/stack-perf.json'))['database_url'])")
export JWT_ACCESS_SECRET=review-access-secret-with-at-least-32-characters
export JWT_REFRESH_SECRET=review-refresh-secret-with-at-least-32-characters
export ODDS_PROVIDER=fake SCHEDULER_ENABLED=false FRONTEND_ORIGIN=http://127.0.0.1:4340
export PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api
unset ENVIRONMENT
exec ~/.cache/the-coupon/ci-local-venv/bin/python "$(dirname "$0")/$1" "${@:2}"
