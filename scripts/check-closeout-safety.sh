#!/usr/bin/env bash
# Pre-push close-out guard: report existing API drift and refuse an API+web
# batch until the owner has explicitly scheduled the matching /ship-prod.
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BATCH="${1:-}"
SCHEDULED="${2:-}"

if [[ ! "$BATCH" =~ ^[0-9]+$ ]] \
   || [[ -n "$SCHEDULED" && "$SCHEDULED" != "--shipment-scheduled" ]]; then
  echo "usage: $0 <numeric-batch> [--shipment-scheduled]" >&2
  exit 2
fi

if ! git -C "$ROOT" show-ref --verify --quiet refs/heads/main; then
  echo "close-out safety: local main is missing" >&2
  exit 2
fi

changed="$({
  git -C "$ROOT" diff --name-only main --
  git -C "$ROOT" ls-files --others --exclude-standard
} | sort -u)"
if [[ -z "$changed" ]]; then
  echo "close-out safety: no batch diff against local main" >&2
  exit 1
fi

echo "pre-push deployment drift"
drift_status=0
"$ROOT/scripts/check-deploy-drift.sh" || drift_status=$?
if (( drift_status < 0 || drift_status > 2 )); then
  echo "close-out safety: drift check returned unexpected status $drift_status" >&2
  exit 2
fi

api_changed=false
web_changed=false
while IFS= read -r path; do
  case "$path" in
    apps/api/*|migrations/*|nixpacks.toml|.railway/railway.ts) api_changed=true ;;
  esac
  case "$path" in
    apps/web/e2e/*|apps/web/src/test/*|apps/web/src/*/__tests__/*|apps/web/playwright*.config.ts)
      ;;
    apps/web/*|vercel.json|pnpm-lock.yaml) web_changed=true ;;
  esac
done <<<"$changed"

if [[ "$api_changed" == true && "$web_changed" == true ]]; then
  if [[ "$SCHEDULED" != "--shipment-scheduled" ]]; then
    echo >&2
    echo "close-out safety: REFUSED — Batch $BATCH changes both API and web." >&2
    echo "The push would deploy the web half before the API half." >&2
    echo "Stop until the owner explicitly schedules the matching /ship-prod, then rerun:" >&2
    echo "  scripts/check-closeout-safety.sh $BATCH --shipment-scheduled" >&2
    exit 1
  fi
  echo "close-out safety: PASS — split-half shipment explicitly scheduled; /ship-prod is owed immediately after push"
elif [[ "$api_changed" == true ]]; then
  echo "close-out safety: PASS — API-only batch; /ship-prod will be owed after push"
elif [[ "$web_changed" == true ]]; then
  echo "close-out safety: PASS — web-only batch; no API shipment added"
else
  echo "close-out safety: PASS — tooling/docs batch; no application half changed"
fi

case "$drift_status" in
  0) echo "close-out safety: existing deployed-API drift check passed" ;;
  1) echo "close-out safety: existing /ship-prod debt remains; report it in close-out" ;;
  2) echo "close-out safety: existing deployed-API state was inconclusive; report it in close-out" ;;
esac
