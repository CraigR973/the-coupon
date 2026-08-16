#!/usr/bin/env bash
# Serve the built bundle, rather than the dev server, so a browser check exercises
# what production actually ships — the prod-bundle Playwright smoke in
# scripts/ci-local.sh runs against this same `vite preview`.
#
# Needs `pnpm --dir apps/web build` to have run first; vite preview serves dist/
# and says so plainly if it is missing.
#
# Mirrors dev.sh: nvm is sourced rather than relying on whatever node is on PATH,
# and every path stays relative to the repository root, which is where
# .claude/launch.json invokes this from.
export NVM_DIR="$HOME/.nvm"
# shellcheck source=/dev/null
source "$NVM_DIR/nvm.sh"
nvm use 20 --silent
exec pnpm --dir apps/web preview --host 127.0.0.1 --port 4173
