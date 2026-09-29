#!/usr/bin/env bash
# Do the unprotected config files actually change what the gate's tools enforce?
# Each check: introduce a real violation, run the tool the way ci-local.sh does (FAIL
# expected), add the unprotected precedence file, run again. Usage: bash precedence_probes.sh <worktree>
set -u
W="$1"; A=$W/apps/api; WEB=$W/apps/web
V=$HOME/.cache/the-coupon/ci-local-venv/bin
. "$HOME/.nvm/nvm.sh" >/dev/null && nvm use 24 --silent
revert() { git -C "$W" checkout -q -- . ; git -C "$W" clean -fdq -- apps scripts docs; }
inapi() { "$V/python" -c 'import os,subprocess,sys; sys.exit(subprocess.run(sys.argv[1:], cwd=os.environ["A"], env={**os.environ, "PYTHONPATH": "."}).returncode)' "$@"; }
export A
revert
echo "T1 ruff: unused local variable (F841) in src"
printf '\n\ndef _probe() -> None:\n    unused = 1\n' >> "$A/src/display_name.py"
inapi "$V/ruff" check . >/dev/null 2>&1; echo "  before: rc=$?"
printf 'line-length = 100\n[lint]\nselect = ["E"]\n' > "$A/ruff.toml"
inapi "$V/ruff" check . >/dev/null 2>&1; echo "  with apps/api/ruff.toml: rc=$?"
revert
echo "T2 mypy: real type error in src"
printf '\n_PROBE: int = "x"\n' >> "$A/src/display_name.py"
inapi "$V/python" -m mypy src/display_name.py >/dev/null 2>&1; echo "  before: rc=$?"
printf '[mypy]\nignore_errors = True\n' > "$A/mypy.ini"
inapi "$V/python" -m mypy src/display_name.py >/dev/null 2>&1; echo "  with apps/api/mypy.ini: rc=$?"
revert
echo "T3 eslint: explicit any in src"
printf '\nexport const probe: any = 1;\n' >> "$WEB/src/lib/utils.ts"
pnpm --dir "$WEB" exec eslint src/lib/utils.ts --report-unused-disable-directives >/dev/null 2>&1; echo "  before: rc=$?"
printf '{"rules": {"@typescript-eslint/no-explicit-any": "off"}}\n' > "$WEB/src/.eslintrc.json"
pnpm --dir "$WEB" exec eslint src/lib/utils.ts --report-unused-disable-directives >/dev/null 2>&1; echo "  with apps/web/src/.eslintrc.json: rc=$?"
revert
echo "T4 vitest: which config wins"
printf 'export default { test: { include: ["src/test/contrast.test.ts"] } }\n' > "$WEB/vitest.config.ts"
pnpm --dir "$WEB" exec vitest run 2>&1 | grep -E 'Test Files|Tests ' | sed 's/^/  with apps\/web\/vitest.config.ts: /'
revert
echo "T5 pytest: a failing test, then a conftest hook"
printf '\n\ndef test_probe_that_must_fail() -> None:\n    assert 1 == 2\n' >> "$A/tests/test_competitions.py"
inapi "$V/python" -m pytest -q -p no:cacheprovider tests/test_competitions.py 2>&1 | tail -1 | sed 's/^/  before: /'
printf '\n\ndef pytest_pyfunc_call(pyfuncitem):  # probe\n    return True\n' >> "$A/tests/conftest.py"
inapi "$V/python" -m pytest -q -p no:cacheprovider tests/test_competitions.py 2>&1 | tail -1 | sed 's/^/  with the conftest hook: /'
revert
