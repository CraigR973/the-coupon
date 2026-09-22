#!/usr/bin/env bash
# Start the production bundle on the one URL Playwright targets, prove that this
# process owns the port, then exercise it. A pre-existing server must be a hard
# failure rather than an invitation for Vite to choose another port.
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
PORT=4173
URL="http://127.0.0.1:$PORT"
READINESS_TIMEOUT_SECONDS=60
READINESS_POLLS_PER_SECOND=4
LOG="$(mktemp -t coupon-vite-preview-XXXXXX)"
preview=""

cleanup() {
  if [[ -n "$preview" ]]; then
    kill "$preview" 2>/dev/null || true
    wait "$preview" 2>/dev/null || true
  fi
  rm -f "$LOG"
}
trap cleanup EXIT INT TERM

# Run Vite directly. GitHub's pnpm wrapper buffers the background process's output until
# it exits, so the readiness line only reached this log when cleanup killed the preview;
# the server was listening, but the ownership proof could never observe that fact.
node "$ROOT/apps/web/node_modules/vite/bin/vite.js" preview "$ROOT/apps/web" \
  --host 127.0.0.1 --port "$PORT" --strictPort >"$LOG" 2>&1 &
preview=$!

ready=false
for ((attempt = 0; attempt < READINESS_TIMEOUT_SECONDS * READINESS_POLLS_PER_SECOND; attempt++)); do
  if ! kill -0 "$preview" 2>/dev/null; then
    wait "$preview" 2>/dev/null || status=$?
    sed 's/^/  /' "$LOG" >&2
    echo "prod-bundle smoke: preview failed before readiness (exit ${status:-1})" >&2
    exit "${status:-1}"
  fi
  # Vite writes its Local address only after it has successfully bound the
  # strict port. Requiring that line prevents a pre-existing server satisfying
  # the HTTP probe during the short interval before Vite reports EADDRINUSE.
  if grep -qE 'Local:.*4173' "$LOG" && curl -fsS --max-time 2 "$URL" >/dev/null; then
    ready=true
    break
  fi
  sleep 0.25
done

if [[ "$ready" != true ]]; then
  sed 's/^/  /' "$LOG" >&2
  echo "prod-bundle smoke: preview did not become ready at $URL within ${READINESS_TIMEOUT_SECONDS} seconds" >&2
  exit 1
fi

if ! kill -0 "$preview" 2>/dev/null; then
  sed 's/^/  /' "$LOG" >&2
  echo "prod-bundle smoke: preview exited after readiness" >&2
  exit 1
fi

pnpm --dir "$ROOT/apps/web" exec playwright test -c playwright.prod-bundle.config.ts
