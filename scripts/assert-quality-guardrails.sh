#!/usr/bin/env bash
# Refuse a batch that changes the machinery used to judge that same batch.
#
# ci-local.sh executes this file from local main, not from the working tree. Keep
# every trust decision here: a branch may propose the next version of the guard,
# but it cannot use that proposal to approve itself.
set -uo pipefail

ROOT="${COUPON_GUARD_ROOT:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}"
BASE_REF="main"
COUNTS_FILE="scripts/ci-test-counts.env"

if ! git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BASE_REF"; then
  echo "quality guardrails: cannot compare this batch because local main is missing" >&2
  exit 2
fi

changed="$({
  git -C "$ROOT" diff --name-only "$BASE_REF" --
  git -C "$ROOT" ls-files --others --exclude-standard
} | sort -u)"

branch="$(git -C "$ROOT" symbolic-ref --short HEAD 2>/dev/null || true)"
bootstrap=false
if [[ "$branch" == feat/batch-152-* ]] \
   && git -C "$ROOT" show "$BASE_REF:docs/BUILD_PLAN.md" \
      | grep -qE '^- \[ \] \*\*Batch 152 '; then
  bootstrap=true
fi

# Owner-approved gate maintenance. This table is trusted only because ci-local
# runs main's copy of this script. The matching BUILD_PLAN row must also be open
# on main and quote every approved path, so neither the table nor the evidence
# can be supplied by the branch they approve.
approved_gate_maintenance() {
  case "$1" in
    153) echo "docs/agent-commands/phase-closeout.md scripts/assert-quality-guardrails.sh" ;;
    127) echo ".github/workflows/ci.yml scripts/ci-local.sh apps/web/package.json" ;;
    178) echo "apps/web/vite.config.ts" ;;
    198) echo "scripts/assert-quality-guardrails.sh scripts/ci-local.sh scripts/check-closeout-safety.sh docs/agent-commands/phase-closeout.md" ;;
    199) echo "docs/agent-commands/phase-closeout.md .github/workflows/ci.yml" ;;
    200) echo "scripts/ci-local.sh .github/workflows/ci.yml" ;;
    201) echo "scripts/check-closeout-safety.sh docs/agent-commands/phase-closeout.md" ;;
    202) echo "apps/web/package.json apps/web/vite.config.ts apps/web/.eslintrc.cjs apps/web/tsconfig.json apps/web/tsconfig.node.json apps/web/playwright.prod-bundle.config.ts" ;;
    203) echo "docs/agent-commands/phase-closeout.md apps/api/pyproject.toml scripts/check-deploy-drift.sh" ;;
    204) echo "scripts/check-closeout-safety.sh docs/agent-commands/phase-closeout.md" ;;
  esac
}

# An expected-value change is still a weakening until the owner has approved the
# exact old oracle that may be replaced. Keep these fingerprints in trusted main,
# bind them to an open BUILD_PLAN row and an exact file list, and ignore only the
# named removed lines. Every other removed test, assertion or expectation remains
# a hard failure, including another removal from the same file.
approved_removed_oracles() {
  case "$1" in
    173) cat <<'EOF'
apps/web/src/test/CouponSection.test.tsx|expect(screen.getByText(/all legs won/i)).toBeTruthy();
apps/web/src/test/CouponSection.test.tsx|expect(screen.getByText(/not all legs landed/i)).toBeTruthy();
apps/web/src/test/CouponSection.test.tsx|it('shows what each leg scored', () => {
apps/web/src/test/CouponSection.test.tsx|expect(screen.getByText('20 pts')).toBeTruthy();
apps/web/src/test/CouponSection.test.tsx|expect(screen.getByText('0 pts')).toBeTruthy();
apps/web/src/test/PickRow.test.tsx|expect(within(row).getByText('Won')).toBeTruthy();
apps/web/src/test/PickRow.test.tsx|expect(within(row).getByText('20 pts')).toBeTruthy();
EOF
      ;;
    179) cat <<'EOF'
apps/api/tests/test_admin_console.py|async def test_the_league_admin_reset_obeys_the_same_rule(client: AsyncClient) -> None:
apps/api/tests/test_admin_console.py|assert response.status_code == 200, response.text
apps/api/tests/test_admin_console.py|assert body["temp_pin"] is None, "no minted secret, and the field kept null for the deploy gap"
apps/api/tests/test_admin_console.py|assert body["pin_cleared"] is True
apps/api/tests/test_admin_console.py|assert body["sessions_revoked"] == 1
apps/api/tests/test_admin_console.py|assert await _live_session_count(member.id) == 0
apps/api/tests/test_admin_console.py|assert (await _reload(member.id)).pin_hash is None
apps/api/tests/test_admin_console.py|assert refused.status_code == 403, refused.text
apps/api/tests/test_admin_console.py|assert refused.json()["detail"] == "SITE_ADMIN_RESET_REQUIRED"
EOF
      ;;
    181) cat <<'EOF'
apps/api/tests/test_league_display_name.py|assert accepted.status_code == 204, accepted.text
apps/api/tests/test_league_display_name.py|assert again.status_code == 204, again.text
apps/api/tests/test_league_display_name.py|assert allowed.status_code == 204, allowed.text
apps/api/tests/test_league_display_name.py|assert await _override_of(league.id, impersonator.id) is None
apps/api/tests/test_league_display_name.py|assert await _override_of(league.id, member.id) == "Gaffer"
apps/api/tests/test_league_display_name.py|assert await _override_of(league.id, member.id) == "The Gaffer"
apps/api/tests/test_league_display_name.py|assert await _override_of(league.id, member.id) is None
apps/api/tests/test_league_display_name.py|assert claimed.status_code == 204, claimed.text
apps/api/tests/test_league_display_name.py|assert cleared.status_code == 204, cleared.text
apps/api/tests/test_league_display_name.py|assert first.status_code == 204
apps/api/tests/test_league_display_name.py|assert refused.json()["detail"] == NAME_TAKEN_IN_LEAGUE
apps/api/tests/test_league_display_name.py|assert refused.status_code == 409
apps/api/tests/test_league_display_name.py|assert refused.status_code == 409, refused.text
apps/api/tests/test_league_display_name.py|assert refused.status_code == 422, (repr(bad), refused.status_code, refused.text)
apps/api/tests/test_league_display_name.py|async def test_a_free_name_is_accepted_and_stored_normalised(client: AsyncClient) -> None:
apps/api/tests/test_league_display_name.py|async def test_an_override_colliding_with_another_members_name_is_refused(
apps/api/tests/test_league_display_name.py|async def test_an_override_colliding_with_another_members_override_is_refused(
apps/api/tests/test_league_display_name.py|async def test_clearing_the_override_still_works(client: AsyncClient) -> None:
apps/api/tests/test_league_display_name.py|async def test_keeping_your_own_override_is_not_a_collision_with_yourself(
apps/api/tests/test_league_display_name.py|async def test_the_charset_rules_are_the_registration_ones(client: AsyncClient) -> None:
apps/api/tests/test_league_display_name.py|async def test_the_collision_check_ignores_case_and_padding(client: AsyncClient) -> None:
apps/api/tests/test_league_display_name.py|async def test_the_same_name_is_free_in_a_different_league(client: AsyncClient) -> None:
apps/api/tests/test_league_write_access.py|assert accepted.status_code == 204, accepted.text
apps/api/tests/test_league_write_access.py|assert refused.status_code == 403, refused.text
apps/api/tests/test_league_write_access.py|async def test_a_non_member_site_admin_is_refused_on_the_per_league_display_name(
apps/api/tests/test_league_write_access.py|async def test_a_real_member_still_reaches_the_write_paths(client: AsyncClient) -> None:
EOF
      ;;
    182) cat <<'EOF'
apps/web/src/test/csp.test.ts|expect(connect).toContain('https://api-production-0641.up.railway.app');
EOF
      ;;
    188) cat <<'EOF'
apps/api/tests/test_cross_league_summary_cost.py|assert flat.count("GAMEWEEKS.") == 3, f"one projected column and two bounds: {flat}"
EOF
      ;;
    190) cat <<'EOF'
apps/api/tests/test_request_budget.py|assert _pick_installation_limits()["day"] <= spare
apps/api/tests/test_request_budget.py|assert _pick_installation_limits() == _pick_shared_limits()
EOF
      ;;
  esac
}

approved_oracle_paths() {
  case "$1" in
    173) echo "apps/web/src/test/CouponSection.test.tsx apps/web/src/test/PickRow.test.tsx" ;;
    179) echo "apps/api/tests/test_admin_console.py" ;;
    181) echo "apps/api/tests/test_league_display_name.py apps/api/tests/test_league_write_access.py" ;;
    182) echo "apps/web/src/test/csp.test.ts" ;;
    188) echo "apps/api/tests/test_cross_league_summary_cost.py" ;;
    190) echo "apps/api/tests/test_request_budget.py" ;;
  esac
}

main_batch_row() {
  local batch="$1"
  git -C "$ROOT" show "$BASE_REF:docs/BUILD_PLAN.md" | awk -v batch="$batch" '
    $0 ~ "^- \\[[ x]\\] \\*\\*Batch " batch " " { found=1 }
    found && seen && $0 ~ "^- \\[[ x]\\] \\*\\*Batch [0-9]+ " { exit }
    found { print; seen=1 }
  '
}

branch_batch="$(printf '%s' "$branch" | sed -nE 's#^(feat|fix|chore)/batch-([0-9]+)-.*#\2#p')"
approved=""
if [[ -n "$branch_batch" ]]; then
  row="$(main_batch_row "$branch_batch")"
  candidate="$(approved_gate_maintenance "$branch_batch")"
  if printf '%s\n' "$row" | grep -qE "^- \[ \] \*\*Batch $branch_batch " \
     && printf '%s\n' "$row" | grep -qF '**Gate maintenance approved' \
     && [[ -n "$candidate" ]]; then
    approval_complete=true
    for path in $candidate; do
      if ! printf '%s\n' "$row" | grep -qF "\`$path\`"; then
        approval_complete=false
      fi
    done
    if [[ "$approval_complete" == true ]]; then
      approved="$candidate"
    fi
  fi
fi

approved_oracles=""
if [[ -n "$branch_batch" ]]; then
  row="$(main_batch_row "$branch_batch")"
  oracle_candidate="$(approved_removed_oracles "$branch_batch")"
  oracle_paths="$(approved_oracle_paths "$branch_batch")"
  if printf '%s\n' "$row" | grep -qE "^- \[ \] \*\*Batch $branch_batch " \
     && printf '%s\n' "$row" | grep -qF '**Oracle changes approved' \
     && [[ -n "$oracle_candidate" && -n "$oracle_paths" ]]; then
    approval_complete=true
    for path in $oracle_paths; do
      if ! printf '%s\n' "$row" | grep -qF "\`$path\`"; then
        approval_complete=false
      fi
    done
    if [[ "$approval_complete" == true ]]; then
      approved_oracles="$oracle_candidate"
    fi
  fi
fi

is_protected() {
  case "$1" in
    .github/workflows/ci.yml|apps/api/pyproject.toml|apps/api/requirements-dev.txt|\
    apps/web/package.json|apps/web/playwright.prod-bundle.config.ts|apps/web/vite.config.ts|\
    scripts/assert-quality-guardrails.sh|scripts/check-closeout-safety.sh|\
    scripts/check-deploy-drift.sh|scripts/check-migration-recovery.sh|scripts/ci-local.sh|\
    scripts/run-prod-bundle-smoke.sh|docs/agent-commands/phase-closeout.md|AGENTS.md|*/AGENTS.md|\
    conftest.py|*/conftest.py|pytest.ini|*/pytest.ini|mypy.ini|*/mypy.ini|\
    .mypy.ini|*/.mypy.ini|ruff.toml|*/ruff.toml|.ruff.toml|*/.ruff.toml|\
    setup.cfg|*/setup.cfg|.eslintrc*|*/.eslintrc*|.eslintignore|*/.eslintignore|\
    vitest.config.*|*/vitest.config.*|tsconfig*.json|*/tsconfig*.json)
      return 0
      ;;
  esac
  return 1
}

protected_changed=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  if is_protected "$path"; then
    protected_changed+="$path"$'\n'
  fi
done <<<"$changed"

unapproved=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case " $approved " in
    *" $path "*) ;;
    *) unapproved+="$path"$'\n' ;;
  esac
done <<<"$protected_changed"

if [[ -n "$unapproved" && "$bootstrap" != true ]]; then
  echo "quality guardrails: FAIL — this batch changes its own gate or lint/type configuration:" >&2
  printf '  %s\n' $unapproved >&2
  echo "Move that work to an explicitly approved gate-maintenance batch." >&2
  exit 1
fi

# Explicit bypass markers and removed oracles can preserve exact test counts
# while making the suite green. New tests and stronger assertions remain free
# to land; weakening an existing oracle requires an owner decision.
added_lines=""
removed_test_lines=""
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    apps/api/src/*|apps/api/tests/*|apps/web/src/*|apps/web/e2e/*) ;;
    *) continue ;;
  esac
  if git -C "$ROOT" ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    added_lines+="$(git -C "$ROOT" diff --unified=0 "$BASE_REF" -- "$path" \
      | sed -nE '/^\+\+\+ /d; /^\+/{s/^\+//;p;}')"$'\n'
    case "$path" in
      apps/api/tests/*|apps/web/src/test/*|apps/web/src/*/__tests__/*|apps/web/e2e/*)
        removed_lines="$(git -C "$ROOT" diff --unified=0 "$BASE_REF" -- "$path" \
          | sed -nE '/^--- /d; /^-/{s/^-//;p;}')"
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          trimmed="$(printf '%s\n' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
          fingerprint="$path|$trimmed"
          if [[ -n "$approved_oracles" ]] \
             && printf '%s\n' "$approved_oracles" | grep -Fxq -- "$fingerprint"; then
            continue
          fi
          removed_test_lines+="$line"$'\n'
        done <<<"$removed_lines"
        ;;
    esac
  elif [[ -f "$ROOT/$path" ]]; then
    added_lines+="$(cat "$ROOT/$path")"$'\n'
  fi
done <<<"$changed"

if printf '%s\n' "$added_lines" | grep -Eq \
  'pytest\.mark\.(skip|xfail)|# *type: *ignore|# *noqa|eslint-disable|(^|[^[:alnum:]_])(it|test|describe)\.(skip|todo|only)\(|expect\(true\)\.toBe\(true\)|status_code +in +\([^)]*,[^)]*\)'; then
  echo "quality guardrails: FAIL — the diff adds a recorded test, type or lint bypass" >&2
  exit 1
fi

if printf '%s\n' "$removed_test_lines" | grep -Eq \
  '^[[:space:]]*((async +)?def +test_|assert +|expect\(|(it|test|describe)(\.(each|only))?\()'; then
  echo "quality guardrails: FAIL — the diff removes a test, assertion or expectation" >&2
  echo "Changing an existing oracle requires an owner decision; add stronger coverage instead." >&2
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
  if (( current_backend > base_backend )) \
     && ! printf '%s\n' "$changed" | grep -qE '^apps/api/tests/'; then
    echo "quality guardrails: FAIL — the backend test ratchet rose without a backend test change" >&2
    exit 1
  fi
  if (( current_frontend > base_frontend )) \
     && ! printf '%s\n' "$changed" | grep -qE '^apps/web/(src/test/|src/.*/__tests__/|e2e/)'; then
    echo "quality guardrails: FAIL — the frontend test ratchet rose without a frontend test change" >&2
    exit 1
  fi
elif [[ "$bootstrap" != true ]]; then
  echo "quality guardrails: FAIL — only Batch 152 may introduce $COUNTS_FILE" >&2
  exit 1
fi

if [[ "$bootstrap" == true && -n "$protected_changed" ]]; then
  echo "quality guardrails: PASS — Batch 152 bootstrap changes are explicitly in scope"
elif [[ -n "$protected_changed" ]]; then
  echo "quality guardrails: PASS — Batch $branch_batch's owner-approved gate maintenance changes:"
  printf '  %s\n' $protected_changed
else
  echo "quality guardrails: PASS — gate and lint/type configuration unchanged"
fi
if [[ -n "$approved_oracles" ]]; then
  echo "quality guardrails: Batch $branch_batch owner-approved exact oracle replacements applied"
fi
echo "quality guardrails: expected tests — backend $current_backend · frontend $current_frontend"
