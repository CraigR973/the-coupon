#!/usr/bin/env bash
# Pre-push close-out guard: report existing API drift and refuse an API+web
# batch until the owner has explicitly scheduled the matching /ship-prod.
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BATCH="${1:-}"
MODE="${2:-}"
GATE_STAMP="$(git -C "$ROOT" rev-parse --absolute-git-dir)/coupon-ci-local.pass"

if [[ ! "$BATCH" =~ ^[0-9]+$ ]] \
   || [[ -n "$MODE" && "$MODE" != "--shipment-scheduled" \
        && "$MODE" != "--verify-gate-stamp" ]]; then
  echo "usage: $0 <numeric-batch> [--shipment-scheduled|--verify-gate-stamp]" >&2
  exit 2
fi

if ! git -C "$ROOT" show-ref --verify --quiet refs/heads/main; then
  echo "close-out safety: local main is missing" >&2
  exit 2
fi

worktree_tree_hash() {
  local gate_index gate_tree
  gate_index="$(mktemp -t coupon-closeout-index-XXXXXX)"
  rm -f "$gate_index"
  if ! GIT_INDEX_FILE="$gate_index" git -C "$ROOT" read-tree HEAD \
     || ! GIT_INDEX_FILE="$gate_index" git -C "$ROOT" add -A \
     || ! gate_tree="$(GIT_INDEX_FILE="$gate_index" git -C "$ROOT" write-tree)"; then
    rm -f "$gate_index"
    return 1
  fi
  rm -f "$gate_index"
  printf '%s\n' "$gate_tree"
}

current_tree="$(worktree_tree_hash)" || {
  echo "close-out safety: could not hash the current working tree" >&2
  exit 2
}
stamp_valid=false
stamped_tree=""
if [[ -f "$GATE_STAMP" ]] \
   && [[ "$(wc -l <"$GATE_STAMP" | tr -d ' ')" == 3 ]] \
   && grep -qxF 'version=1' "$GATE_STAMP" \
   && grep -qxF 'profile=full' "$GATE_STAMP"; then
  stamped_tree="$(sed -nE 's/^tree=([0-9a-f]{40})$/\1/p' "$GATE_STAMP")"
  [[ -n "$stamped_tree" ]] && stamp_valid=true
fi
if [[ "$stamp_valid" != true || "$stamped_tree" != "$current_tree" ]]; then
  echo "close-out safety: REFUSED — the exact tree has no matching ci-local PASS stamp" >&2
  echo "Run the complete 11-check scripts/ci-local.sh gate against this tree before continuing." >&2
  exit 1
fi
echo "close-out safety: verified ci-local PASS stamp for tree $current_tree"

if [[ "$MODE" == "--verify-gate-stamp" ]]; then
  exit 0
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
  if [[ "$MODE" != "--shipment-scheduled" ]]; then
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
