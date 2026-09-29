#!/usr/bin/env bash
# Replay the two pre-push guards against historical commits in a push-less scratch clone.
# For each non-docs commit C since 2ce6f42: local main := C^, branch := the branch name the
# reflog recorded (or a stand-in), worktree := C. Then run the guard scripts *as they
# existed at C*: assert-quality-guardrails.sh (exists from 5cefff3) and
# check-closeout-safety.sh with check-deploy-drift.sh stubbed to "in sync" (the real one
# calls production and git fetch; never run here).
# Usage: bash replay_guards.sh <clone-path>
set -u
C_ROOT="$1"
known_branch() {
  case "$1" in
    d1b9ee9) echo fix/deterministic-delivery-gates ;; 7ef953d) echo fix/preview-readiness-signal ;;
    89217f8) echo fix/preview-readiness-ansi ;; 2f7d742) echo fix/round-population-window-clock ;;
    83facaf) echo fix/e2e-coupon-flow ;; 99b5fc9) echo fix/remeasure-production-walk ;;
    828f42d) echo feat/batch-115-certify-from-stored-rounds ;;
  esac
}
for c in $(git -C /Users/craigrobinson/the-coupon log --reverse --format=%h 5cefff3..main); do
  subj=$(git -C "$C_ROOT" log -1 --format=%s "$c")
  case "$subj" in docs:*) continue;; esac
  b="$(known_branch "$c")"
  if [[ -z "$b" ]]; then
    n=$(printf '%s' "$subj" | sed -nE 's/.*\(Batch ([0-9]+)\).*/\1/p')
    if [[ -z "$n" ]]; then
      # batch number from the following close-out commit
      n=$(git -C /Users/craigrobinson/the-coupon log --reverse --format=%s "$c"..main | head -3 \
          | sed -nE 's/^docs: close out Batch ([0-9]+) .*/\1/p' | head -1)
    fi
    b="feat/batch-${n:-000}-replay"
  fi
  git -C "$C_ROOT" checkout -q -f -B "$b" "$c" 2>/dev/null
  git -C "$C_ROOT" branch -f main "$c^" >/dev/null
  g_out=$(bash "$C_ROOT/scripts/assert-quality-guardrails.sh" 2>&1); g=$?
  printf '#!/usr/bin/env bash\necho "drift: stubbed in sync"\nexit 0\n' > "$C_ROOT/scripts/check-deploy-drift.sh"
  s_out=$(bash "$C_ROOT/scripts/check-closeout-safety.sh" 000 2>&1); s=$?
  git -C "$C_ROOT" checkout -q -- scripts/check-deploy-drift.sh
  printf '%s %-44s guardrail=%s safety=%s | %s\n' "$c" "$b" "$g" "$s" "$subj"
  if [[ $g -ne 0 ]]; then printf '    guardrail: %s\n' "$(echo "$g_out" | tr '\n' ' ' | cut -c1-300)"; fi
  if [[ $s -ne 0 ]]; then printf '    safety: %s\n' "$(echo "$s_out" | grep -E 'REFUSED|usage|missing|no batch' | tr '\n' ' ' | cut -c1-200)"; fi
done
