#!/usr/bin/env python3
"""Apply six simultaneous weakenings to the throwaway worktree that keep every test count
exact and every skip count zero, so the full gate can be run over them.
Usage: python3 combined_weakening.py <worktree>"""
import re, sys, pathlib
W = pathlib.Path(sys.argv[1]); A = W / "apps/api"; WEB = W / "apps/web"
def edit(path, old, new, count=1):
    s = path.read_text(); assert s.count(old) >= 1, (path, old[:60]); path.write_text(s.replace(old, new, count))
# 1. loosen a core assertion in place (the installation pick budget, Batch 161)
edit(A / "tests/test_picks_flow.py",
     "assert quiet_pick.status_code == 429, quiet_pick.text",
     "assert quiet_pick.status_code in (201, 429), quiet_pick.text")
# 2. delete a backend test and add a trivial one (count held)
p = A / "tests/test_competitions.py"; s = p.read_text()
s = re.sub(r"\ndef test_the_trim_removes_thirteen_of_the_thirty_six_the_pool_holds\(.*?(?=\n\n\n)", "", s, flags=re.S)
s += "\n\ndef test_probe_trivial_a() -> None:\n    assert True\n"
p.write_text(s)
# 3. drop a test at collection through the unprotected conftest.py, add a trivial one
with (A / "tests/conftest.py").open("a") as f:
    f.write("\n\ndef pytest_collection_modifyitems(config, items):  # review probe\n"
            "    items[:] = [i for i in items if i.name != "
            "'test_the_measurements_describe_the_catalogue_they_were_taken_from']\n")
with (A / "tests/test_competitions.py").open("a") as f:
    f.write("\n\ndef test_probe_trivial_b() -> None:\n    assert True\n")
# 4. silence a real type error in product code
with (A / "src/display_name.py").open("a") as f:
    f.write('\n_PROBE: int = "not an int"  # type: ignore[assignment]\n')
# 5. silence a real lint error in product code
with (WEB / "src/lib/utils.ts").open("a") as f:
    f.write("\n// eslint-disable-next-line @typescript-eslint/no-explicit-any\nexport const probe: any = 1;\n")
# 6. swap a frontend test for a trivial one, and add a todo
edit(WEB / "src/test/usePickEditor.test.tsx",
     "  it('carries the moved price so the button can name it', () => {\n"
     "    expect(pickRefusal('PRICE_MOVED:3.50').price).toBe('3.50');\n  });",
     "  it('probe trivial', () => {\n    expect(true).toBe(true);\n  });\n  it.todo('probe todo');")
print("applied")

# After applying, the probe ran the pinned `ruff format` over the three edited Python files
# (what an agent does before the gate), so formatting is not what the gate judges.
