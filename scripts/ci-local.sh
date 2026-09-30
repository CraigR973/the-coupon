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
# Skip both production-bundle browser checks: SKIP_PROD_BUNDLE=1 scripts/ci-local.sh
# Rebuild the venv from scratch:              CI_LOCAL_REBUILD=1 scripts/ci-local.sh
# Run only the seeded coupon journey:         scripts/ci-local.sh --journey-only
set -uo pipefail

# Only the full profile is the gate, and only it can stamp a tree for close-out.
# GitHub's coupon-journey job runs --journey-only so that it drives this file's
# journey runner rather than a second copy of it; that profile skips the
# guardrail because a CI checkout has no local main to judge against.
PROFILE=full
case "$#:${1:-}" in
  0:) ;;
  1:--journey-only) PROFILE=journey ;;
  *)
    echo "usage: scripts/ci-local.sh [--journey-only]" >&2
    exit 2
    ;;
esac

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REQ="$ROOT/apps/api/requirements-dev.txt"
VENV="${CI_LOCAL_VENV:-$HOME/.cache/the-coupon/ci-local-venv}"
# Matches actions/setup-python in .github/workflows/ci.yml.
PY_VERSION="3.12"
LOG="$(mktemp -t coupon-ci-XXXXXX)"
GATE_STAMP="$(git -C "$ROOT" rev-parse --absolute-git-dir)/coupon-ci-local.pass"
FAILED=()
PASSED=0

cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

# A failed or interrupted run must not leave an older pass reusable.
rm -f "$GATE_STAMP"

# The branch may propose changes to the gate, but main's guard and approval
# table judge them. Running from ROOT keeps the pre-Batch-198 guard compatible
# while this change itself is being verified.
if [[ "$PROFILE" == full ]]; then
  if ! (cd "$ROOT" && git show main:scripts/assert-quality-guardrails.sh \
    | COUPON_GUARD_ROOT="$ROOT" bash); then
    exit 1
  fi
fi

read_count() {
  local key="$1"
  sed -nE "s/^${key}=([0-9]+)$/\\1/p" "$ROOT/scripts/ci-test-counts.env"
}
BACKEND_TEST_COUNT="$(read_count BACKEND_TEST_COUNT)"
FRONTEND_TEST_COUNT="$(read_count FRONTEND_TEST_COUNT)"
JOURNEY_TEST_COUNT="$(read_count JOURNEY_TEST_COUNT)"

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
  # An empty or non-numeric baseline would make every comparison below false and
  # fall through to PASS, so it is a failure before anything runs.
  if [[ ! "$expected" =~ ^[0-9]+$ ]]; then
    echo "FAIL"
    echo "      scripts/ci-test-counts.env records no $suite test count."
    FAILED+=("$name (count unrecorded)")
    return
  fi
  if ! ( cd "$dir" && "$@" ) >"$LOG" 2>&1; then
    echo "FAIL"
    sed 's/^/      /' "$LOG" | tail -30
    FAILED+=("$name")
    return
  fi

  if [[ "$suite" == backend ]]; then
    summary="$(grep -E '[0-9]+ passed' "$LOG" | tail -1)"
  elif [[ "$suite" == journey ]]; then
    summary="$(grep -E '^coupon journey: [0-9]+ passed' "$LOG" | tail -1)"
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

if [[ "$PROFILE" == full ]]; then
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
fi

echo
echo "node dependencies"
# GitHub's setup-node has already selected Node 24, so nvm is only for this Mac,
# whose ambient node is far older.
if [[ "$(node --version 2>/dev/null)" != v24.* && -s "$HOME/.nvm/nvm.sh" ]]; then
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

if [[ "$PROFILE" == full ]]; then
  echo
  echo "deployment-config"
  step "railway/nixpacks/vercel assertions" "$ROOT" "$PYTHON" scripts/assert-deployment-config.py

  echo
  echo "frontend"
  step "lint"      "$ROOT" pnpm --dir apps/web lint
  step "typecheck" "$ROOT" pnpm --dir apps/web typecheck
  test_step "test" "$ROOT" frontend "$FRONTEND_TEST_COUNT" pnpm --dir apps/web test
  step "build"     "$ROOT" env VITE_API_URL=https://api.example.invalid pnpm --dir apps/web build
fi

if [[ "$PROFILE" == full && -z "${SKIP_PROD_BUNDLE:-}" ]]; then
  echo
  echo "prod-bundle"
  step "playwright deep-link smoke" "$ROOT" "$ROOT/scripts/run-prod-bundle-smoke.sh"
fi

# The one test in which members claim unique picks, the round locks and settles
# and standings are read, through a production bundle and the real API on scratch
# PostgreSQL. It sat outside the gate until Batch 200 and rotted for five days.
# Both servers get ports of their own (the deep-link smoke holds 4173; 5173 and
# 8000 are the development servers) and must prove they bound them. Playwright
# runs without retries, and the count check refuses a skipped journey.
if [[ "$PROFILE" == journey || -z "${SKIP_PROD_BUNDLE:-}" ]]; then
  echo
  echo "coupon journey"
  test_step "playwright coupon journey" "$ROOT" journey "$JOURNEY_TEST_COUNT" \
    env COUPON_CI_ROOT="$ROOT" "$PYTHON" - <<'PY'
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
import pgserver

ROOT = os.environ["COUPON_CI_ROOT"]
API_DIR = os.path.join(ROOT, "apps", "api")
WEB_DIR = os.path.join(ROOT, "apps", "web")
VITE = os.path.join(WEB_DIR, "node_modules", "vite", "bin", "vite.js")
API_PORT, WEB_PORT = 8174, 4174
API_URL = f"http://127.0.0.1:{API_PORT}"
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"
# Kept after the run for inspection (git ignores it, CI uploads it on failure):
# Playwright's traces, the journey's screenshots and every server's log.
RESULTS = os.path.join(WEB_DIR, "test-results", "coupon-journey")
LOGS = os.path.join(RESULTS, "logs")
READY_SECONDS = 60
# No proxy may answer for 127.0.0.1: the probes are about the processes started here.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
servers = []


def fail(message, log=None):
    if log:
        with open(log, errors="replace") as handle:
            tail = "".join(handle.readlines()[-25:]).rstrip("\n")
        if tail:
            print(tail, flush=True)
    print(f"coupon journey: {message}", flush=True)
    sys.exit(1)


def run(name, argv, cwd, env):
    log = os.path.join(LOGS, f"{name}.log")
    with open(log, "w") as out:
        code = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT).returncode
    if code != 0:
        fail(f"{name} failed (exit {code})", log)


def answers(url):
    try:
        with opener.open(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def serve(name, argv, cwd, env, bound, url):
    # Batch 152's pattern: ready means this server's own log says it bound the
    # port, the URL answers, and the process is still alive. The log line is what
    # stops a server already holding the port from passing the probe in the moment
    # before this one reports the address in use.
    log = os.path.join(LOGS, f"{name}.log")
    out = open(log, "w")
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
    servers.append(process)
    deadline = time.monotonic() + READY_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            fail(f"{name} exited ({process.returncode}) before it was ready", log)
        with open(log, errors="replace") as handle:
            bound_here = re.search(bound, handle.read()) is not None
        if bound_here and answers(url) and process.poll() is None:
            return
        time.sleep(0.25)
    fail(f"{name} was not ready at {url} within {READY_SECONDS} seconds", log)


shutil.rmtree(RESULTS, ignore_errors=True)
os.makedirs(LOGS)
work = tempfile.mkdtemp(prefix="coupon-journey-")
pgdata = tempfile.mkdtemp(prefix="coupon-journey-pg-")
database = None
try:
    database = pgserver.get_server(pgdata, cleanup_mode="delete")
    database.psql("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    api_env = dict(os.environ)
    api_env["DATABASE_URL"] = database.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)
    api_env["JWT_ACCESS_SECRET"] = "ci-access-secret-with-at-least-32-characters"
    api_env["JWT_REFRESH_SECRET"] = "ci-refresh-secret-with-at-least-32-characters"
    api_env["SCHEDULER_ENABLED"] = "false"
    # CORS admits one exact origin; without it every sign-in fails at the preflight.
    api_env["FRONTEND_ORIGIN"] = WEB_URL
    api_env["PYTHONPATH"] = "."
    api_env.pop("ENVIRONMENT", None)
    run("alembic", [sys.executable, "-m", "alembic", "upgrade", "head"], API_DIR, api_env)

    # A production bundle built for this API, outside apps/web/dist so the gate's own
    # build is untouched. It runs from apps/web because Tailwind resolves its content
    # globs from the working directory.
    bundle = os.path.join(work, "dist")
    run(
        "vite-build",
        ["node", VITE, "build", "--outDir", bundle, "--emptyOutDir"],
        WEB_DIR,
        dict(os.environ, VITE_API_URL=API_URL),
    )

    serve(
        "api",
        [sys.executable, "-m", "uvicorn", "tests.e2e_server:app",
         "--host", "127.0.0.1", "--port", str(API_PORT)],
        API_DIR,
        api_env,
        rf"Uvicorn running on {re.escape(API_URL)}\b",
        f"{API_URL}/api/v1/health/ready",
    )
    serve(
        "preview",
        ["node", VITE, "preview", "--outDir", bundle,
         "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"],
        WEB_DIR,
        dict(os.environ),
        rf"Local.*{WEB_PORT}",
        WEB_URL,
    )

    report = os.path.join(work, "report.json")
    code = subprocess.run(
        ["pnpm", "--dir", WEB_DIR, "exec", "playwright", "test", "e2e/coupon-flow.spec.ts",
         "--config", "playwright.config.ts", "--project", "coupon-flow",
         "--retries", "0", "--forbid-only", "--reporter", "line,json",
         "--output", os.path.join(RESULTS, "playwright")],
        env=dict(
            os.environ,
            COUPON_E2E_API_URL=API_URL,
            COUPON_E2E_WEB_URL=WEB_URL,
            COUPON_E2E_ARTIFACT_DIR=os.path.join(RESULTS, "screenshots"),
            PLAYWRIGHT_JSON_OUTPUT_FILE=report,
        ),
    ).returncode
    try:
        with open(report) as handle:
            stats = json.load(handle)["stats"]
    except (OSError, ValueError, KeyError):
        fail(f"playwright exited {code} without writing a result")
    print(
        f"coupon journey: {stats['expected']} passed, {stats['skipped']} skipped, "
        f"{stats['flaky']} flaky, {stats['unexpected']} failed",
        flush=True,
    )
    if code != 0 or stats["unexpected"] or stats["flaky"]:
        fail(f"traces, screenshots and server logs are in {RESULTS}")
finally:
    for process in servers:
        process.terminate()
    for process in servers:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if database is not None:
        database.cleanup()
    shutil.rmtree(pgdata, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
PY
fi

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  if [[ "$PROFILE" == journey ]]; then
    echo "ci-local: PASS ($PASSED checks; journey-only profile — no close-out stamp)"
    exit 0
  fi
  if [[ -n "${SKIP_PROD_BUNDLE:-}" ]]; then
    echo "ci-local: PASS ($PASSED checks; partial profile — no close-out stamp)"
    exit 0
  fi
  gate_index="$(mktemp -t coupon-gate-index-XXXXXX)"
  rm -f "$gate_index"
  if ! GIT_INDEX_FILE="$gate_index" git -C "$ROOT" read-tree HEAD \
     || ! GIT_INDEX_FILE="$gate_index" git -C "$ROOT" add -A \
     || ! gate_tree="$(GIT_INDEX_FILE="$gate_index" git -C "$ROOT" write-tree)"; then
    rm -f "$gate_index"
    echo "ci-local: FAIL — could not hash the verified working tree"
    exit 1
  fi
  rm -f "$gate_index"
  stamp_tmp="${GATE_STAMP}.tmp.$$"
  umask 077
  printf 'version=1\nprofile=full\ntree=%s\n' "$gate_tree" >"$stamp_tmp"
  mv "$stamp_tmp" "$GATE_STAMP"
  echo "ci-local: PASS ($PASSED checks)"
  echo "ci-local: stamped verified tree $gate_tree"
  exit 0
fi
echo "ci-local: FAIL — ${FAILED[*]}"
exit 1
