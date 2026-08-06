#!/usr/bin/env bash
# Report whether the deployed API is behind origin/main.
#
# Vercel auto-deploys main on every push; Railway only moves when /ship-prod runs.
# On 2026-08-06 that let the API sit thirteen batches behind the web app, which
# broke the Coupon tab: Batch 14 renamed the slate's date field on both sides at
# once, only the web half shipped, and the page threw on `new Date(undefined)`.
# Nothing surfaced it because the web kept working.
#
# Exit 0 in sync · 1 drifted · 2 could not tell.
set -uo pipefail

ROOT="/Users/craigrobinson/the-coupon"
API="${API_ORIGIN:-https://api-production-109b1.up.railway.app}"

# Routes that only exist from a given batch onward. A 404 here means the API
# predates that batch; anything else (403 behind auth, 200) means it is present.
# This is the fallback for when the deployed commit is not reported.
PROBE_PATH="/api/v1/leagues/probe-drift/gameweeks"
PROBE_SINCE="Batch 12"

git -C "$ROOT" fetch origin --quiet 2>/dev/null
EXPECTED="$(git -C "$ROOT" rev-parse origin/main 2>/dev/null)"
if [[ -z "$EXPECTED" ]]; then
  echo "Could not resolve origin/main." >&2
  exit 2
fi

HEALTH="$(curl -fsS --max-time 15 "$API/api/v1/health" 2>/dev/null)"
if [[ -z "$HEALTH" ]]; then
  echo "API unreachable at $API" >&2
  exit 2
fi

DEPLOYED="$(printf '%s' "$HEALTH" | sed -nE 's/.*"sha"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/p')"

echo "origin/main   ${EXPECTED:0:8}  $(git -C "$ROOT" log -1 --format=%s origin/main | cut -c1-56)"

if [[ -n "$DEPLOYED" && "$DEPLOYED" != "unknown" ]]; then
  echo "deployed API  ${DEPLOYED:0:8}"
  if [[ "$DEPLOYED" == "$EXPECTED" ]]; then
    echo "in sync"
    exit 0
  fi
  if git -C "$ROOT" cat-file -e "$DEPLOYED^{commit}" 2>/dev/null; then
    BEHIND="$(git -C "$ROOT" rev-list --count "$DEPLOYED..origin/main" 2>/dev/null)"
    echo "DRIFTED — the API is $BEHIND commit(s) behind origin/main"
    git -C "$ROOT" log --oneline "$DEPLOYED..origin/main" 2>/dev/null | head -15 | sed 's/^/    /'
  else
    echo "DRIFTED — deployed commit is not in this checkout (fetch, or it was never pushed)"
  fi
  echo
  echo "Ship it with /ship-prod, which also refreshes RAILWAY_GIT_COMMIT_SHA."
  exit 1
fi

# No commit reported — fall back to probing for a route added in a known batch.
echo "deployed API  unknown (RAILWAY_GIT_COMMIT_SHA not set on this deployment)"
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$API$PROBE_PATH" 2>/dev/null)"
if [[ "$CODE" == "404" ]]; then
  echo "DRIFTED — $PROBE_PATH is missing, so the API predates $PROBE_SINCE"
  exit 1
fi
echo "probe         $PROBE_PATH -> $CODE (present, so the API is at least $PROBE_SINCE)"
echo "INCONCLUSIVE — cannot confirm the exact commit until the next deploy seals"
echo "RAILWAY_GIT_COMMIT_SHA. Re-run after the next /ship-prod."
exit 2
