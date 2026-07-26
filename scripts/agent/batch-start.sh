#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/craigrobinson/the-coupon"
BATCH="${1:-}"

if [[ ! "$BATCH" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <numeric-batch>" >&2
  exit 2
fi

ROW="$(grep -E "^- \\[ \\] \\*\\*Batch $BATCH " "$ROOT/docs/BUILD_PLAN.md" || true)"
if [[ -z "$ROW" ]]; then
  echo "Batch $BATCH is missing or already closed." >&2
  exit 1
fi

BRANCH="$(git -C "$ROOT" symbolic-ref --short HEAD)"
if [[ "$BRANCH" != "main" ]]; then
  echo "Refusing to start from '$BRANCH'; check out main first." >&2
  exit 1
fi

if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "Working tree is not clean." >&2
  exit 1
fi

TITLE="$(printf '%s' "$ROW" | sed -E "s/^- \\[ \\] \\*\\*Batch $BATCH — ([^*]+)\\*\\*.*/\\1/")"
SLUG="$(printf '%s' "$TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-40)"
BRANCH_NAME="feat/batch-$BATCH-$SLUG"
git -C "$ROOT" checkout -b "$BRANCH_NAME"
echo "Started $BRANCH_NAME"
echo "After verification, wait for /phase-closeout $BATCH"
