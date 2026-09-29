#!/usr/bin/env bash
# Classify every non-docs commit since 2ce6f42 the way scripts/check-closeout-safety.sh
# classifies a batch diff (API / web / tooling), and flag protected-file edits.
R=/Users/craigrobinson/the-coupon
PROTECTED='^(\.github/workflows/ci\.yml|apps/api/pyproject\.toml|apps/api/requirements-dev\.txt|apps/web/\.eslintrc\.cjs|apps/web/package\.json|apps/web/playwright\.prod-bundle\.config\.ts|apps/web/tsconfig\.json|apps/web/tsconfig\.node\.json|apps/web/vite\.config\.ts|scripts/assert-quality-guardrails\.sh|scripts/check-closeout-safety\.sh|scripts/check-deploy-drift\.sh|scripts/ci-local\.sh|scripts/run-prod-bundle-smoke\.sh|docs/agent-commands/phase-closeout\.md)$'
for c in $(git -C $R log --reverse --format=%h 2ce6f42..main); do
  subj=$(git -C $R log -1 --format=%s $c)
  case "$subj" in docs:*) continue;; esac
  api=false; web=false; prot=""
  while IFS= read -r p; do
    case "$p" in apps/api/*|migrations/*|nixpacks.toml|.railway/railway.ts) api=true;; esac
    case "$p" in
      apps/web/e2e/*|apps/web/src/test/*|apps/web/src/*/__tests__/*|apps/web/playwright*.config.ts) ;;
      apps/web/*|vercel.json|pnpm-lock.yaml) web=true;;
    esac
    if [[ "$p" =~ $PROTECTED ]]; then prot+="$p "; fi
  done < <(git -C $R diff-tree --no-commit-id --name-only -r $c)
  cls=tooling
  $api && $web && cls=API+WEB
  $api && ! $web && cls=api
  ! $api && $web && cls=web
  printf '%s %-8s %s%s\n' "$c" "$cls" "$subj" "${prot:+  [PROTECTED: $prot]}"
done
