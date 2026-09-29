#!/usr/bin/env bash
# Guardrail-only probes: apply one weakening at a time in the throwaway worktree, run
# scripts/assert-quality-guardrails.sh (working-tree copy, exactly as ci-local.sh does),
# record the exit code, revert. Usage: bash gate_probes.sh <worktree>
set -u
W="$1"
revert() { git -C "$W" checkout -q -- . ; git -C "$W" clean -fdq -- apps scripts docs; }
probe() {
  local name="$1"; shift
  revert
  ( eval "$*" ) >/dev/null 2>&1
  out=$(bash "$W/scripts/assert-quality-guardrails.sh" 2>&1); rc=$?
  printf '%-4s rc=%s  %-62s | %s\n' "$name" "$rc" "$(git -C "$W" status --porcelain | tr '\n' ' ' | cut -c1-62)" "$(echo "$out" | head -1 | cut -c1-90)"
}
A=$W/apps/api; WEB=$W/apps/web
probe G01 "sed -i '' 's/^async def test_a_second_league_is_bounded_by_what_the_deployment_has_left(/@pytest.mark.skip(reason=\"probe\")\n&/' $A/tests/test_picks_flow.py"
probe G02 "sed -i '' 's/^async def test_a_second_league_is_bounded_by_what_the_deployment_has_left(/@pytest.mark.xfail(reason=\"probe\")\n&/' $A/tests/test_picks_flow.py"
probe G03 "sed -i '' 's/^BACKEND_TEST_COUNT=1350/BACKEND_TEST_COUNT=1349/' $W/scripts/ci-test-counts.env"
probe G04 "sed -i '' 's/assert quiet_pick.status_code == 429, quiet_pick.text/assert quiet_pick.status_code in (201, 429), quiet_pick.text/' $A/tests/test_picks_flow.py"
probe G05 "printf '\n_PROBE: int = \"x\"  # type: ignore[assignment]\n' >> $A/src/display_name.py"
probe G06 "printf '\n// eslint-disable-next-line @typescript-eslint/no-explicit-any\nexport const probe: any = 1;\n' >> $WEB/src/lib/utils.ts"
probe G07 "sed -i '' 's/select = \[\"E\", \"F\", \"I\", \"UP\"\]/select = [\"E\"]/' $A/pyproject.toml"
probe G08 "sed -i '' 's/^strict = true/strict = false/' $A/pyproject.toml"
probe G09 "sed -i '' \"s/'plugin:react-hooks\/recommended',//\" $WEB/.eslintrc.cjs"
probe G10 "sed -i '' 's/\"strict\": true/\"strict\": false/' $WEB/tsconfig.json"
probe G11 "printf '\n# probe\n' >> $W/scripts/ci-local.sh"
probe G12 "sed -i '' '2i\\
exit 0
' $W/scripts/assert-quality-guardrails.sh"
probe G13 "printf '\nprobe\n' >> $W/docs/agent-commands/phase-closeout.md"
probe G14 "sed -i '' 's/^BACKEND_TEST_COUNT=1350/BACKEND_TEST_COUNT=1360/' $W/scripts/ci-test-counts.env"
probe G15 "printf '[lint]\nselect = [\"E\"]\n' > $A/ruff.toml"
probe G16 "printf '[mypy]\nignore_errors = True\n' > $A/mypy.ini"
probe G17 "printf '{\"rules\": {\"@typescript-eslint/no-explicit-any\": \"off\"}}\n' > $WEB/src/.eslintrc.json"
probe G18 "printf 'export default { test: { include: [\"src/test/contrast.test.ts\"] } }\n' > $WEB/vitest.config.ts"
probe G19 "printf '[pytest]\naddopts = -p no:cacheprovider\n' > $A/pytest.ini"
probe G20 "printf '\ndef pytest_pyfunc_call(pyfuncitem):\n    return True\n' >> $A/tests/conftest.py"
probe G21 "printf '\n# probe\n' >> $W/scripts/check-closeout-safety.sh"
probe G22 "printf 'src/lib/utils.ts\n' > $WEB/.eslintignore"
probe G23 "printf '\n# probe\n' >> $W/scripts/check-migration-recovery.sh"
probe G24 "printf '\n# probe\n' >> $W/docs/agent-commands/batch-start.md; printf '\nprobe\n' >> $W/AGENTS.md"
revert
