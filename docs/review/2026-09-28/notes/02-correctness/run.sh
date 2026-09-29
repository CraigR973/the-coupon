#!/usr/bin/env bash
# Run one lens-02 driver script with the gate venv, from the scratchpad (no .env there).
#   bash run.sh <script.py> [args]
set -euo pipefail
NOTES=/Users/craigrobinson/the-coupon/docs/review/2026-09-28/notes/02-correctness
SCRATCH=/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad
builtin cd "$SCRATCH"
exec "$HOME/.cache/the-coupon/ci-local-venv/bin/python" "$NOTES/$1" "${@:2}"
