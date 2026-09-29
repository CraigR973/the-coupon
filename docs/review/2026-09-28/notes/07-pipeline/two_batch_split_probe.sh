#!/usr/bin/env bash
# Batch N ships an API route (API-only, /ship-prod owed); Batch N+1 is web-only and calls it.
# Does the close-out guard stop N+1? Drift stubbed to exit 1 ("a /ship-prod is owed").
set -u
C="$1"
git -C "$C" checkout -q -f -B feat/batch-998-probe eb18bcb
git -C "$C" branch -f main eb18bcb
printf '\nexport const probeRoute = "/api/v1/route-only-batch-997-added";\n' >> "$C/apps/web/src/lib/utils.ts"
printf '#!/usr/bin/env bash\necho "drift: stubbed — API behind origin/main, a /ship-prod is owed"\nexit 1\n' > "$C/scripts/check-deploy-drift.sh"
bash "$C/scripts/check-closeout-safety.sh" 998; echo "rc=$?"
git -C "$C" checkout -q -f -- . ; git -C "$C" checkout -q -f -B chore/review-2026-09-28 eb18bcb
