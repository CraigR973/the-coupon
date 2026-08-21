#!/usr/bin/env bash
# Report whether the deployed API is behind origin/main.
#
# Vercel auto-deploys main on every push; Railway only moves when /ship-prod runs.
# On 2026-08-06 that let the API sit thirteen batches behind the web app, which
# broke the Coupon tab: Batch 14 renamed the slate's date field on both sides at
# once, only the web half shipped, and the page threw on `new Date(undefined)`.
# Nothing surfaced it because the web kept working.
#
# Three tiers, strongest first:
#
#   1. commit    — /health reports RAILWAY_GIT_COMMIT_SHA. Exact, but Railway
#                  injects it only for GitHub-connected services, so a CLI
#                  shipment leaves it unset unless /ship-prod stamps it.
#   2. migration — /health reports the Alembic head bundled in the image. Weaker
#                  (it only moves when a migration is added) but intrinsic: it
#                  needs nothing injected at deploy time, so it is right even
#                  when tier 1 is blank. This is the tier that would have caught
#                  2026-08-06, where the breaking change *was* a migration.
#   3. probe     — ask for a route added in a known batch. A 404 dates the image.
#
# The question is "is a /ship-prod owed?", not "are the two SHAs equal", so a
# commit behind that cannot reach the API image does not count as drift. Tier 1
# is commit-exact and would otherwise report every docs push as DRIFTED, which
# trains you to ignore it.
#
# Exit 0 nothing to ship · 1 a /ship-prod is owed · 2 could not tell.
set -uo pipefail

ROOT="/Users/craigrobinson/the-coupon"
API="${API_ORIGIN:-https://api-production-109b1.up.railway.app}"

# Paths that end up in the API image. `railway up` uploads the whole working
# directory, but only these change what the service runs: apps/api is the
# source (requirements*.txt included), migrations is the schema, and the two
# TOML files drive the build and start command.
API_PATHS=(apps/api migrations nixpacks.toml railway.toml)

# Routes that only exist from a given batch onward. A 404 here means the API
# predates that batch; anything else (403 behind auth, 200) means it is present.
# Keep this pointed at the newest batch that added a route, or the fallback
# answers a staler question than it needs to.
PROBE_PATH="/api/v1/football/tables"
PROBE_SINCE="Batch 51"

git -C "$ROOT" fetch origin --quiet 2>/dev/null
EXPECTED="$(git -C "$ROOT" rev-parse origin/main 2>/dev/null)"
if [[ -z "$EXPECTED" ]]; then
  echo "Could not resolve origin/main." >&2
  exit 2
fi

# The migration head at origin/main. alembic.ini sets file_template to
# %(rev)s_%(slug)s, so the filename prefix is the revision id by construction.
EXPECTED_MIGRATION="$(git -C "$ROOT" ls-tree --name-only origin/main migrations/versions/ 2>/dev/null \
  | sed -nE 's#.*/([0-9]+)_.*\.py$#\1#p' | sort | tail -1)"

HEALTH="$(curl -fsS --max-time 15 "$API/api/v1/health" 2>/dev/null)"
if [[ -z "$HEALTH" ]]; then
  echo "API unreachable at $API" >&2
  exit 2
fi

field() { printf '%s' "$HEALTH" | sed -nE "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/p"; }
DEPLOYED="$(field sha)"
DEPLOYED_MIGRATION="$(field migration)"

echo "origin/main   ${EXPECTED:0:8}  $(git -C "$ROOT" log -1 --format=%s origin/main | cut -c1-56)"
echo "              migration ${EXPECTED_MIGRATION:-unknown}"

# Tier 1 — exact commit.
if [[ -n "$DEPLOYED" && "$DEPLOYED" != "unknown" ]]; then
  echo "deployed API  ${DEPLOYED:0:8}"
  echo "              migration ${DEPLOYED_MIGRATION:-unknown}"
  if [[ "$DEPLOYED" == "$EXPECTED" ]]; then
    echo "in sync"
    exit 0
  fi
  if ! git -C "$ROOT" cat-file -e "$DEPLOYED^{commit}" 2>/dev/null; then
    echo "DRIFTED — deployed commit is not in this checkout (fetch, or it was never pushed)"
    echo
    echo "Ship it with /ship-prod, which also refreshes RAILWAY_GIT_COMMIT_SHA."
    exit 1
  fi

  BEHIND="$(git -C "$ROOT" rev-list --count "$DEPLOYED..origin/main" 2>/dev/null)"
  # Same revision walk as the count, so history simplification treats both alike.
  TOUCHING_SHAS="$(git -C "$ROOT" rev-list "$DEPLOYED..origin/main" -- "${API_PATHS[@]}" 2>/dev/null)"
  TOUCHING="$(printf '%s' "$TOUCHING_SHAS" | grep -c . || true)"

  # `*` marks a commit that reaches the API image.
  while read -r sha subject; do
    [[ -z "$sha" ]] && continue
    if printf '%s\n' "$TOUCHING_SHAS" | grep -q "^$sha$"; then mark="*"; else mark=" "; fi
    printf '    %s %s %s\n' "$mark" "${sha:0:8}" "$subject"
  done < <(git -C "$ROOT" log --format='%H %s' "$DEPLOYED..origin/main" 2>/dev/null | head -15)
  echo

  if [[ "$TOUCHING" -eq 0 ]]; then
    echo "behind by $BEHIND commit(s), none of which reach the API image"
    echo "Nothing to ship — redeploying would rebuild the same service."
    exit 0
  fi
  echo "DRIFTED — $TOUCHING of $BEHIND commit(s) behind origin/main reach the API image"
  echo "Ship it with /ship-prod, which also refreshes RAILWAY_GIT_COMMIT_SHA."
  exit 1
fi

echo "deployed API  unknown (RAILWAY_GIT_COMMIT_SHA not set on this deployment)"
echo "              migration ${DEPLOYED_MIGRATION:-unknown}"

# Tier 2 — migration head. Cannot pin the commit, but settles the dangerous case.
if [[ -n "$DEPLOYED_MIGRATION" && "$DEPLOYED_MIGRATION" != "unknown" && -n "$EXPECTED_MIGRATION" ]]; then
  if [[ "$DEPLOYED_MIGRATION" != "$EXPECTED_MIGRATION" ]]; then
    echo "DRIFTED — the API carries migration $DEPLOYED_MIGRATION, origin/main is at $EXPECTED_MIGRATION"
    echo "This is the schema-bearing kind: the web app may already read fields this API"
    echo "does not serve. Ship it with /ship-prod."
    exit 1
  fi
  echo "no schema drift — the deployed image carries the same migration head as origin/main"
  echo "INCONCLUSIVE — a matching head does not pin the commit, because a batch that"
  echo "adds no migration does not move it. Re-run after the next /ship-prod, which"
  echo "stamps RAILWAY_GIT_COMMIT_SHA and makes this exact."
  exit 2
fi

# Tier 3 — the image predates migration reporting. Probe for a dated route.
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$API$PROBE_PATH" 2>/dev/null)"
if [[ "$CODE" == "404" ]]; then
  echo "DRIFTED — $PROBE_PATH is missing, so the API predates $PROBE_SINCE"
  exit 1
fi
echo "probe         $PROBE_PATH -> $CODE (present, so the API is at least $PROBE_SINCE)"
echo "INCONCLUSIVE — cannot confirm the exact commit until the next deploy seals"
echo "RAILWAY_GIT_COMMIT_SHA. Re-run after the next /ship-prod."
exit 2
