#!/usr/bin/env bash
# PIPE-03 rehearsal on port 4291 (4173 belongs to the lead's gate). Copies the real smoke
# script into the throwaway worktree with only the port changed (PORT= and the readiness
# pattern, which hard-codes 4173), holds the port with another server, and runs it.
# Usage: bash pipe03_rehearsal.sh <worktree>   (needs apps/web/dist built there)
set -u
W="$1"; P=4291
sed -e "s/^PORT=4173/PORT=$P/" -e "s/Local\.\*4173/Local.*$P/" "$W/scripts/run-prod-bundle-smoke.sh" > "$W/scripts/smoke-$P.sh"
diff "$W/scripts/run-prod-bundle-smoke.sh" "$W/scripts/smoke-$P.sh"
. "$HOME/.nvm/nvm.sh" >/dev/null && nvm use 24 --silent
/usr/bin/python3 -m http.server $P --bind 127.0.0.1 >/dev/null 2>&1 & holder=$!
sleep 1
echo "holder on $P: pid $holder"
start=$(date +%s)
bash "$W/scripts/smoke-$P.sh"; rc=$?
echo "smoke rc=$rc after $(( $(date +%s) - start ))s"
kill $holder; wait $holder 2>/dev/null
rm -f "$W/scripts/smoke-$P.sh"
