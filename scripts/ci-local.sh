#!/usr/bin/env bash
# Run the checks .github/workflows/ci.yml runs, locally.
#
# GitHub Actions is not always available — during the 2026-08-06 Actions outage
# two pushes to main landed with no run scheduled at all, so nothing gated them.
# This is the same gate, independent of GitHub.
#
# It installs apps/api/requirements-dev.txt into a managed venv and runs
# everything from that, because "the same gate" has to mean the same versions.
# Pointing PYTHON at whichever interpreter was handy is exactly how
# tests/test_football_router.py passed here and failed in CI for nine days
# straight: `HTTPBearer` answers a missing Authorization header with 403 on the
# pinned fastapi==0.111.0 and 401 on newer ones, and the ambient venv was 28
# minor versions ahead of what ships. A local PASS on a commit CI fails is worse
# than no local gate at all, so the interpreter is no longer configurable.
#
# The venv lives outside the repository deliberately: `railway up` uploads the
# working directory, so a venv inside it would ship to production.
#
# Skip the slowest job with:   SKIP_PROD_BUNDLE=1 scripts/ci-local.sh
# Rebuild the venv from scratch: CI_LOCAL_REBUILD=1 scripts/ci-local.sh
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REQ="$ROOT/apps/api/requirements-dev.txt"
VENV="${CI_LOCAL_VENV:-$HOME/.cache/the-coupon/ci-local-venv}"
# Matches actions/setup-python in .github/workflows/ci.yml.
PY_VERSION="3.12"
LOG="$(mktemp -t coupon-ci-XXXXXX)"
FAILED=()
PASSED=0

cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

if ! "$ROOT/scripts/assert-quality-guardrails.sh"; then
  exit 1
fi

read_count() {
  local key="$1"
  sed -nE "s/^${key}=([0-9]+)$/\\1/p" "$ROOT/scripts/ci-test-counts.env"
}
BACKEND_TEST_COUNT="$(read_count BACKEND_TEST_COUNT)"
FRONTEND_TEST_COUNT="$(read_count FRONTEND_TEST_COUNT)"

# step <name> <working-dir> <command...>
step() {
  local name="$1" dir="$2"; shift 2
  printf '  %-36s' "$name"
  if ( cd "$dir" && "$@" ) >"$LOG" 2>&1; then
    echo "PASS"
    PASSED=$((PASSED + 1))
  else
    echo "FAIL"
    sed 's/^/      /' "$LOG" | tail -30
    FAILED+=("$name")
  fi
}

# test_step <name> <working-dir> <suite> <expected-count> <command...>
test_step() {
  local name="$1" dir="$2" suite="$3" expected="$4"; shift 4
  local summary count skipped
  printf '  %-36s' "$name"
  if ! ( cd "$dir" && "$@" ) >"$LOG" 2>&1; then
    echo "FAIL"
    sed 's/^/      /' "$LOG" | tail -30
    FAILED+=("$name")
    return
  fi

  if [[ "$suite" == backend ]]; then
    summary="$(grep -E '[0-9]+ passed' "$LOG" | tail -1)"
  else
    summary="$(grep -E 'Tests[[:space:]]+[0-9]+ passed' "$LOG" | tail -1)"
  fi
  count="$(printf '%s' "$summary" | grep -Eo '[0-9]+ passed' | head -1 | cut -d' ' -f1)"
  skipped="$(printf '%s' "$summary" | grep -Eo '[0-9]+ skipped' | head -1 | cut -d' ' -f1)"
  skipped="${skipped:-0}"

  if [[ -z "$count" || ! "$count" =~ ^[0-9]+$ ]]; then
    echo "FAIL"
    echo "      Could not read the $suite test count from the successful command."
    sed 's/^/      /' "$LOG" | tail -30
    FAILED+=("$name (count missing)")
  elif (( skipped > 0 )); then
    echo "FAIL ($count passed, $skipped skipped; expected no skips)"
    FAILED+=("$name ($skipped skipped)")
  elif (( count < expected )); then
    echo "FAIL ($count tests; expected $expected — tests were removed or skipped)"
    FAILED+=("$name (test count fell)")
  elif (( count > expected )); then
    echo "FAIL ($count tests; baseline is $expected — raise ci-test-counts.env and rerun)"
    FAILED+=("$name (baseline stale)")
  else
    echo "PASS ($count tests, 0 skipped)"
    PASSED=$((PASSED + 1))
  fi
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to build the pinned venv — https://docs.astral.sh/uv/" >&2
  exit 2
fi

# Rebuild whenever either requirements file changes; requirements-dev.txt pulls
# in requirements.txt, so both feed the stamp.
REQ_HASH="$(cat "$REQ" "$ROOT/apps/api/requirements.txt" | shasum -a 256 | cut -d' ' -f1)"
STAMP="$VENV/.requirements-sha256"

if [[ -n "${CI_LOCAL_REBUILD:-}" || ! -x "$VENV/bin/python" \
      || "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]]; then
  echo "building pinned venv at $VENV"
  rm -rf "$VENV"
  # --only-binary=cryptography is kept as a guard, not a workaround. The
  # deviation it used to paper over is gone: apps/api/requirements.txt is now a
  # fully-pinned universal lock generated from requirements.in, and it bounds
  # cryptography at the newest release with wheels for both platforms, so this
  # venv and the production image install the same versions. The flag stays so
  # that a future bump past that bound fails loudly here rather than starting a
  # silent source build that needs a Rust toolchain.
  #
  # Batch 59 raised that bound from 46.0.3 to 48.0.1 and this still holds: 48.0.1
  # publishes a macOS `universal2` wheel, which carries an x86_64 slice and so
  # installs on Intel as well as Apple silicon. 49.0.0 is where macOS wheels stop
  # entirely — that is the bump this flag is now waiting to catch.
  if ! uv venv --python "$PY_VERSION" "$VENV" >/dev/null 2>&1 \
     || ! VIRTUAL_ENV="$VENV" uv pip install --quiet --only-binary=cryptography -r "$REQ"; then
    echo "Could not build the pinned venv from $REQ" >&2
    exit 2
  fi
  printf '%s' "$REQ_HASH" >"$STAMP"
fi

PYTHON="$VENV/bin/python"
RUFF="$VENV/bin/ruff"

if ! "$PYTHON" -c 'import alembic, pytest, pgserver, mypy' >/dev/null 2>&1; then
  echo "The pinned venv at $VENV is incomplete. Retry with CI_LOCAL_REBUILD=1." >&2
  exit 2
fi

# Print the versions the gate is actually running, so a mismatch with the pins
# is visible rather than inferred.
"$PYTHON" - <<'PY'
import fastapi, starlette, sys
print(f"python {sys.version.split()[0]} · fastapi {fastapi.__version__} · starlette {starlette.__version__}", end="")
PY
echo " · $("$RUFF" --version)"

echo
echo "backend"
step "ruff check"          "$ROOT/apps/api" "$RUFF" check .
step "ruff format --check" "$ROOT/apps/api" "$RUFF" format --check .
step "mypy src"            "$ROOT/apps/api" env PYTHONPATH="$ROOT/apps/api" "$PYTHON" -m mypy src

# alembic + pytest need a database. Start from a clean schema: the HTTP pick-flow
# test commits real rows, so a reused cluster accumulates them across runs.
test_step "alembic upgrade head + pytest" "$ROOT" backend "$BACKEND_TEST_COUNT" \
  env COUPON_CI_API="$ROOT/apps/api" "$PYTHON" - <<'PY'
import os, shutil, subprocess, sys, tempfile
import pgserver

API = os.environ["COUPON_CI_API"]
pgdata = tempfile.mkdtemp(prefix="coupon-ci-")
try:
    server = pgserver.get_server(pgdata)
    server.psql("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    env = dict(os.environ)
    env["DATABASE_URL"] = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)
    env["JWT_ACCESS_SECRET"] = "ci-access-secret-with-at-least-32-characters"
    env["JWT_REFRESH_SECRET"] = "ci-refresh-secret-with-at-least-32-characters"
    env["SCHEDULER_ENABLED"] = "false"
    env["PYTHONPATH"] = "."
    env.pop("ENVIRONMENT", None)
    for argv in (["-m", "alembic", "upgrade", "head"], ["-m", "pytest", "-q"]):
        if subprocess.run([sys.executable, *argv], cwd=API, env=env).returncode != 0:
            sys.exit(1)
finally:
    shutil.rmtree(pgdata, ignore_errors=True)
PY

echo
echo "node dependencies"
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  . "$HOME/.nvm/nvm.sh" && nvm use 24 --silent
fi
# CI installs exactly the pnpm that package.json's `packageManager` names (via
# pnpm/action-setup), and a different pnpm can resolve the same lockfile differently.
# So the install step refuses any other version rather than passing on a near miss.
PNPM_PINNED="$(sed -nE 's/.*"packageManager": *"pnpm@([^"]+)".*/\1/p' "$ROOT/package.json")"
pinned_pnpm_install() {
  local have
  have="$(pnpm --version 2>/dev/null)"
  if [[ -z "$PNPM_PINNED" || "$have" != "$PNPM_PINNED" ]]; then
    echo "pnpm is '${have:-missing}' but package.json pins '${PNPM_PINNED:-nothing}'."
    echo "With Node 24 selected, run: corepack enable pnpm"
    return 1
  fi
  pnpm install --frozen-lockfile
}
step "pnpm install --frozen-lockfile" "$ROOT" pinned_pnpm_install

echo
echo "deployment-config"
step "railway/nixpacks/vercel assertions" "$ROOT" "$PYTHON" scripts/assert-deployment-config.py

echo
echo "frontend"
step "lint"      "$ROOT" pnpm --dir apps/web lint
step "typecheck" "$ROOT" pnpm --dir apps/web typecheck
test_step "test" "$ROOT" frontend "$FRONTEND_TEST_COUNT" pnpm --dir apps/web test
step "build"     "$ROOT" env VITE_API_URL=https://api.example.invalid pnpm --dir apps/web build

if [[ -z "${SKIP_PROD_BUNDLE:-}" ]]; then
  echo
  echo "prod-bundle"
  step "playwright deep-link smoke" "$ROOT" "$ROOT/scripts/run-prod-bundle-smoke.sh"
fi

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  echo "ci-local: PASS ($PASSED checks)"
  exit 0
fi
echo "ci-local: FAIL — ${FAILED[*]}"
exit 1
