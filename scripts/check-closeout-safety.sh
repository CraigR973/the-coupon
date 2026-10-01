#!/usr/bin/env bash
# Pre-push close-out guard: report existing API drift and refuse a web release
# that depends on unshipped API work until the owner has explicitly scheduled
# the matching /ship-prod. A shipment acknowledgement names who scheduled it
# and when so close-out can preserve that evidence in session-log.md.
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BATCH="${1:-}"
GATE_STAMP="$(git -C "$ROOT" rev-parse --absolute-git-dir)/coupon-ci-local.pass"
VERIFY_GATE_STAMP=false
SHIPMENT_SCHEDULED_BY=""
SHIPMENT_SCHEDULED_AT=""

usage() {
  echo "usage: $0 <numeric-batch> [--verify-gate-stamp | --shipment-scheduled-by <identity> --shipment-scheduled-at <UTC-RFC3339>]" >&2
}

if [[ ! "$BATCH" =~ ^[0-9]+$ ]]; then
  usage
  exit 2
fi
shift

while (( $# > 0 )); do
  case "$1" in
    --verify-gate-stamp)
      VERIFY_GATE_STAMP=true
      shift
      ;;
    --shipment-scheduled-by)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      SHIPMENT_SCHEDULED_BY="$2"
      shift 2
      ;;
    --shipment-scheduled-at)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      SHIPMENT_SCHEDULED_AT="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

ACKNOWLEDGED=false
if [[ -n "$SHIPMENT_SCHEDULED_BY" || -n "$SHIPMENT_SCHEDULED_AT" ]]; then
  if [[ -z "$SHIPMENT_SCHEDULED_BY" || -z "$SHIPMENT_SCHEDULED_AT" ]]; then
    echo "close-out safety: shipment acknowledgement requires both who and when" >&2
    usage
    exit 2
  fi
  if [[ ! "$SHIPMENT_SCHEDULED_BY" =~ ^[[:alnum:]][[:alnum:].@_-]*(\ [[:alnum:].@_-]+)*$ ]] \
     || (( ${#SHIPMENT_SCHEDULED_BY} > 80 )); then
    echo "close-out safety: shipment identity must be 1-80 letters, numbers, spaces or . @ _ -" >&2
    exit 2
  fi
  if [[ ! "$SHIPMENT_SCHEDULED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
    echo "close-out safety: shipment time must be UTC RFC3339 (YYYY-MM-DDTHH:MM:SSZ)" >&2
    exit 2
  fi
  ACKNOWLEDGED=true
fi

if [[ "$VERIFY_GATE_STAMP" == true && "$ACKNOWLEDGED" == true ]]; then
  echo "close-out safety: gate verification and shipment acknowledgement are separate invocations" >&2
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
  echo "Run the complete 12-check scripts/ci-local.sh gate against this tree before continuing." >&2
  exit 1
fi
echo "close-out safety: verified ci-local PASS stamp for tree $current_tree"

if [[ "$VERIFY_GATE_STAMP" == true ]]; then
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

drift_record="pre-push deployed-API state inconclusive"
case "$drift_status" in
  0) drift_record="pre-push deployed-API drift in sync" ;;
  1) drift_record="pre-push /ship-prod debt present" ;;
esac

if [[ "$api_changed" == true && "$web_changed" == true ]]; then
  if [[ "$ACKNOWLEDGED" != true ]]; then
    echo >&2
    echo "close-out safety: REFUSED — Batch $BATCH changes both API and web." >&2
    echo "The push would deploy the web half before the API half." >&2
    echo "Stop until the owner explicitly schedules the matching /ship-prod." >&2
    echo "Record who scheduled it and the current UTC time when rerunning the guard." >&2
    echo "Close-out safety: REFUSED — API+web; shipment acknowledgement missing; $drift_record" >&2
    exit 1
  fi
  echo "close-out safety: PASS — API+web shipment explicitly scheduled"
  echo "Close-out safety: PASS — API+web; shipment scheduled by $SHIPMENT_SCHEDULED_BY at $SHIPMENT_SCHEDULED_AT; $drift_record; /ship-prod owed immediately after push"
elif [[ "$web_changed" == true && "$drift_status" -eq 1 ]]; then
  if [[ "$ACKNOWLEDGED" != true ]]; then
    echo >&2
    echo "close-out safety: REFUSED — Batch $BATCH changes web while an earlier /ship-prod is owed." >&2
    echo "The web change may depend on API work that members cannot reach yet." >&2
    echo "Stop until the owner explicitly schedules the matching /ship-prod." >&2
    echo "Record who scheduled it and the current UTC time when rerunning the guard." >&2
    echo "Close-out safety: REFUSED — web-only over existing API debt; shipment acknowledgement missing; $drift_record" >&2
    exit 1
  fi
  echo "close-out safety: PASS — web change over existing API debt; shipment explicitly scheduled"
  echo "Close-out safety: PASS — web-only over existing API debt; shipment scheduled by $SHIPMENT_SCHEDULED_BY at $SHIPMENT_SCHEDULED_AT; $drift_record; /ship-prod owed immediately after push"
elif [[ "$api_changed" == true ]]; then
  echo "close-out safety: PASS — API-only batch; /ship-prod will be owed after push"
  echo "Close-out safety: PASS — API-only; $drift_record; /ship-prod owed after push"
elif [[ "$web_changed" == true ]]; then
  echo "close-out safety: PASS — web-only batch; no API shipment added"
  echo "Close-out safety: PASS — web-only; $drift_record; no API shipment added"
else
  echo "close-out safety: PASS — tooling/docs batch; no application half changed"
  echo "Close-out safety: PASS — tooling/docs; $drift_record; no application half changed"
fi

case "$drift_status" in
  0) echo "close-out safety: existing deployed-API drift check passed" ;;
  1) echo "close-out safety: existing /ship-prod debt remains; report it in close-out" ;;
  2) echo "close-out safety: existing deployed-API state was inconclusive; report it in close-out" ;;
esac
