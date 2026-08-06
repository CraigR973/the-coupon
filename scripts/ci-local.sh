#!/usr/bin/env bash
# Run the checks .github/workflows/ci.yml runs, locally.
#
# GitHub Actions is not always available — during the 2026-08-06 Actions outage
# two pushes to main landed with no run scheduled at all, so nothing gated them.
# This is the same gate, independent of GitHub.
#
# Needs a Python with apps/api/requirements-dev.txt installed. This repo keeps no
# venv of its own, so point PYTHON at one:
#   PYTHON=/path/to/venv/bin/python scripts/ci-local.sh
#
# Skip the slowest job with:  SKIP_PROD_BUNDLE=1 scripts/ci-local.sh
set -uo pipefail

ROOT="/Users/craigrobinson/the-coupon"
PYTHON="${PYTHON:-python3}"
LOG="$(mktemp -t coupon-ci-XXXXXX)"
FAILED=()
PASSED=0

cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

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

# CI pins ruff in requirements-dev.txt, and the pinned version disagrees with
# newer ones on formatting, so derive it rather than naming it here.
RUFF_PIN="$(sed -nE 's/^ruff==([0-9.]+).*/\1/p' "$ROOT/apps/api/requirements-dev.txt")"
if [[ -z "$RUFF_PIN" ]]; then
  echo "Could not read the ruff pin from apps/api/requirements-dev.txt" >&2
  exit 2
fi

if ! "$PYTHON" -c 'import alembic, pytest, pgserver, mypy' >/dev/null 2>&1; then
  echo "PYTHON=$PYTHON is missing alembic/pytest/pgserver/mypy." >&2
  echo "Point PYTHON at an interpreter with apps/api/requirements-dev.txt installed." >&2
  exit 2
fi

echo "ruff $RUFF_PIN · python $("$PYTHON" -c 'import sys; print(sys.version.split()[0])')"

echo
echo "backend"
step "ruff check"          "$ROOT/apps/api" uvx "ruff@$RUFF_PIN" check .
step "ruff format --check" "$ROOT/apps/api" uvx "ruff@$RUFF_PIN" format --check .
step "mypy src"            "$ROOT/apps/api" env PYTHONPATH="$ROOT/apps/api" "$PYTHON" -m mypy src

# alembic + pytest need a database. Start from a clean schema: the HTTP pick-flow
# test commits real rows, so a reused cluster accumulates them across runs.
step "alembic upgrade head + pytest" "$ROOT" "$PYTHON" - <<'PY'
import os, shutil, subprocess, sys, tempfile
import pgserver

API = "/Users/craigrobinson/the-coupon/apps/api"
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
echo "deployment-config"
step "railway/nixpacks/vercel assertions" "$ROOT" "$PYTHON" - <<'PY'
import json, pathlib, tomllib
root = pathlib.Path("/Users/craigrobinson/the-coupon")
railway = tomllib.loads((root / "railway.toml").read_text())
nixpacks = tomllib.loads((root / "nixpacks.toml").read_text())
vercel = json.loads((root / "apps/web/vercel.json").read_text())
assert railway["build"]["builder"] == "nixpacks"
assert railway["build"]["nixpacksConfigPath"] == "nixpacks.toml"
assert railway["deploy"]["healthcheckPath"] == "/api/v1/health/ready"
assert railway["deploy"]["numReplicas"] == 1
assert railway["deploy"]["sleepApplication"] is False
assert railway["deploy"]["ipv6EgressEnabled"] is True
assert railway["deploy"]["multiRegionConfig"] == {"europe-west4-drams3a": {"numReplicas": 1}}
assert "postgresql_17" in nixpacks["phases"]["setup"]["nixPkgs"]
install_cmd = " ".join(nixpacks["phases"]["install"]["cmds"])
assert "python -m venv --copies /opt/venv" in install_cmd
assert "apps/api/requirements.txt" in install_cmd
assert nixpacks["phases"]["install"]["paths"] == ["/opt/venv/bin"]
start = nixpacks["start"]["cmd"]
assert "python -m src.runtime_secrets" in start
assert "alembic -c apps/api/alembic.ini upgrade head" in start
assert "uvicorn src.main:app" in start
assert start.index("python -m src.runtime_secrets") < start.index("alembic -c apps/api/alembic.ini upgrade head")
assert start.index("alembic -c apps/api/alembic.ini upgrade head") < start.index("uvicorn src.main:app")
assert not (root / "vercel.json").exists()
assert vercel["installCommand"] == "pnpm install --frozen-lockfile"
assert vercel["buildCommand"] == "pnpm build"
assert vercel["outputDirectory"] == "dist"
assert vercel["rewrites"][0]["destination"] == "/index.html"
assert any(header["source"] == "/sw.js" for header in vercel["headers"])
PY

echo
echo "frontend"
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  . "$HOME/.nvm/nvm.sh" && nvm use 20 --silent
fi
step "pnpm install --frozen-lockfile" "$ROOT" pnpm install --frozen-lockfile
step "lint"      "$ROOT" pnpm --dir apps/web lint
step "typecheck" "$ROOT" pnpm --dir apps/web typecheck
step "test"      "$ROOT" pnpm --dir apps/web test
step "build"     "$ROOT" env VITE_API_URL=https://api.example.invalid pnpm --dir apps/web build

if [[ -z "${SKIP_PROD_BUNDLE:-}" ]]; then
  echo
  echo "prod-bundle"
  step "playwright deep-link smoke" "$ROOT" bash -c '
    pnpm --dir apps/web exec vite preview --host 127.0.0.1 >/tmp/the-coupon-vite.log 2>&1 &
    preview=$!
    trap "kill $preview 2>/dev/null" EXIT
    sleep 5
    pnpm --dir apps/web exec playwright test -c playwright.prod-bundle.config.ts
  '
fi

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  echo "ci-local: PASS ($PASSED checks)"
  exit 0
fi
echo "ci-local: FAIL — ${FAILED[*]}"
exit 1
