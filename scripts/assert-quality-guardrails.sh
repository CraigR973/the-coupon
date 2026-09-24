#!/usr/bin/env bash
# Refuse a batch that changes the machinery used to judge that same batch.
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BASE_REF="main"
COUNTS_FILE="scripts/ci-test-counts.env"
PROTECTED=(
  .github/workflows/ci.yml
  apps/api/pyproject.toml
  apps/api/requirements-dev.txt
  apps/web/.eslintrc.cjs
  apps/web/package.json
  apps/web/playwright.prod-bundle.config.ts
  apps/web/tsconfig.json
  apps/web/tsconfig.node.json
  apps/web/vite.config.ts
  scripts/assert-quality-guardrails.sh
  scripts/check-closeout-safety.sh
  scripts/check-deploy-drift.sh
  scripts/ci-local.sh
  scripts/run-prod-bundle-smoke.sh
  docs/agent-commands/phase-closeout.md
)

if ! git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BASE_REF"; then
  echo "quality guardrails: cannot compare this batch because local main is missing" >&2
  exit 2
fi

changed_protected="$({
  git -C "$ROOT" diff --name-only "$BASE_REF" -- "${PROTECTED[@]}"
  git -C "$ROOT" ls-files --others --exclude-standard -- "${PROTECTED[@]}"
} | sort -u)"

branch="$(git -C "$ROOT" symbolic-ref --short HEAD 2>/dev/null || true)"
bootstrap=false
if [[ "$branch" == feat/batch-152-* ]] \
   && grep -qE '^- \[ \] \*\*Batch 152 ' "$ROOT/docs/BUILD_PLAN.md"; then
  bootstrap=true
fi

# Owner-approved gate maintenance. A batch named here may change the protected files
# listed against it, and no others, while it runs on its own batch branch and its row is
# still open — so each entry goes inert when the row is ticked, as the Batch 152 bootstrap
# does. An entry is itself a change to this protected file: add one only with the owner's
# approval recorded in that batch's row, never on an agent's own judgement.
#   153, 127 — approved by the owner on 2026-09-24 (see both rows).
approved_gate_maintenance() {
  case "$1" in
    153) echo "docs/agent-commands/phase-closeout.md scripts/assert-quality-guardrails.sh" ;;
    127) echo ".github/workflows/ci.yml scripts/ci-local.sh apps/web/package.json" ;;
  esac
}

branch_batch="$(printf '%s' "$branch" | sed -nE 's#^(feat|fix|chore)/batch-([0-9]+)-.*#\2#p')"
approved=""
if [[ -n "$branch_batch" ]] \
   && grep -qE "^- \[ \] \*\*Batch $branch_batch " "$ROOT/docs/BUILD_PLAN.md"; then
  approved="$(approved_gate_maintenance "$branch_batch")"
fi

unapproved=""
for path in $changed_protected; do
  case " $approved " in
    *" $path "*) ;;
    *) unapproved+="$path"$'\n' ;;
  esac
done

if [[ -n "$unapproved" && "$bootstrap" != true ]]; then
  echo "quality guardrails: FAIL — this batch changes its own gate or lint/type configuration:" >&2
  printf '  %s\n' $unapproved >&2
  echo "Move that work to an explicitly approved gate-maintenance batch." >&2
  exit 1
fi

read_count() {
  local file="$1" key="$2"
  sed -nE "s/^${key}=([0-9]+)$/\\1/p" "$file"
}

if [[ -e "$ROOT/$COUNTS_FILE" ]]; then
  current_backend="$(read_count "$ROOT/$COUNTS_FILE" BACKEND_TEST_COUNT)"
  current_frontend="$(read_count "$ROOT/$COUNTS_FILE" FRONTEND_TEST_COUNT)"
  if [[ -z "$current_backend" || -z "$current_frontend" ]]; then
    echo "quality guardrails: FAIL — $COUNTS_FILE must contain numeric backend and frontend counts" >&2
    exit 1
  fi
else
  echo "quality guardrails: FAIL — $COUNTS_FILE is missing" >&2
  exit 1
fi

if git -C "$ROOT" cat-file -e "$BASE_REF:$COUNTS_FILE" 2>/dev/null; then
  baseline="$(mktemp -t coupon-test-counts-XXXXXX)"
  trap 'rm -f "$baseline"' EXIT
  git -C "$ROOT" show "$BASE_REF:$COUNTS_FILE" >"$baseline"
  base_backend="$(read_count "$baseline" BACKEND_TEST_COUNT)"
  base_frontend="$(read_count "$baseline" FRONTEND_TEST_COUNT)"
  if [[ -z "$base_backend" || -z "$base_frontend" ]]; then
    echo "quality guardrails: FAIL — main has an invalid $COUNTS_FILE" >&2
    exit 1
  fi
  if (( current_backend < base_backend || current_frontend < base_frontend )); then
    echo "quality guardrails: FAIL — test-count baselines may rise, never fall" >&2
    echo "  backend: $base_backend -> $current_backend" >&2
    echo "  frontend: $base_frontend -> $current_frontend" >&2
    exit 1
  fi
elif [[ "$bootstrap" != true ]]; then
  echo "quality guardrails: FAIL — only Batch 152 may introduce $COUNTS_FILE" >&2
  exit 1
fi

if [[ "$bootstrap" == true && -n "$changed_protected" ]]; then
  echo "quality guardrails: PASS — Batch 152 bootstrap changes are explicitly in scope"
elif [[ -n "$changed_protected" ]]; then
  echo "quality guardrails: PASS — Batch $branch_batch's owner-approved gate maintenance changes:"
  printf '  %s\n' $changed_protected
else
  echo "quality guardrails: PASS — gate and lint/type configuration unchanged"
fi
echo "quality guardrails: expected tests — backend $current_backend · frontend $current_frontend"
