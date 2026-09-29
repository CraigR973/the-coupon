#!/usr/bin/env bash
# In the push-less scratch clone: can a batch branch approve its own gate edits by adding a
# line to the guardrail's approval table? Usage: bash self_approval_probe.sh <clone>
set -u
C="$1"
git -C "$C" checkout -q -f -B feat/batch-999-probe eb18bcb
git -C "$C" branch -f main eb18bcb
run() { out=$(bash "$C/scripts/assert-quality-guardrails.sh" 2>&1); echo "rc=$? :: $(echo "$out" | tr '\n' ' ' | cut -c1-230)"; }
# an open row, as every batch in flight has
printf '\n- [ ] **Batch 999 — probe** — throwaway row for the review probe.\n' >> "$C/docs/BUILD_PLAN.md"
printf '\n# weakened by probe\n' >> "$C/scripts/ci-local.sh"
echo "S1 edit ci-local.sh, no approval line:"; run
sed -i '' 's#^    127) echo#    999) echo "scripts/ci-local.sh scripts/assert-quality-guardrails.sh" ;;\
    127) echo#' "$C/scripts/assert-quality-guardrails.sh"
echo "S2 plus a self-added approval line for 999:"; run
sed -i '' 's/^- \[ \] \*\*Batch 999 /- [x] **Batch 999 /' "$C/docs/BUILD_PLAN.md"
echo "S3 control: same, but the 999 row ticked:"; run
git -C "$C" checkout -q -f -- . ; git -C "$C" checkout -q -f -B chore/review-2026-09-28 eb18bcb
