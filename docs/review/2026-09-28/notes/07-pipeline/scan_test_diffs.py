#!/usr/bin/env python3
"""Scan every commit since 2ce6f42 for signs of a weakened check.

Reports, per commit: added suppression markers anywhere; removed test functions /
cases that were not re-added under the same name; deleted test files; net change in
assertion lines inside test files; ratchet changes; and "changed expectation" pairs
(a removed and an added assert/expect line in the same hunk).
Run: python3 scan_test_diffs.py > scan-test-diffs.txt
"""
import re, subprocess, collections

R = "/Users/craigrobinson/the-coupon"
def git(*a):
    return subprocess.run(["git", "-C", R, *a], capture_output=True, text=True, check=True).stdout

TEST_PATH = re.compile(r"(^apps/api/tests/|\.test\.tsx?$|\.spec\.tsx?$|/e2e/|/__tests__/|/src/test/)")
MARKERS = [
    (r"pytest\.mark\.skip|pytest\.skip\(|skipif|mark\.xfail|pytest\.xfail", "py-skip/xfail"),
    (r"\b(it|test|describe)\.(skip|only|todo|fails)\b|\bxit\(|\bxdescribe\(|\bfit\(", "js-skip/only/todo"),
    (r"type:\s*ignore", "type-ignore"),
    (r"eslint-disable", "eslint-disable"),
    (r"#\s*noqa", "noqa"),
    (r"@ts-(ignore|expect-error|nocheck)", "ts-ignore"),
    (r"pragma:\s*no cover", "no-cover"),
    (r"\bas any\b|: any\b", "any"),
]
PY_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)")
JS_TEST_DEF = re.compile(r"^\s*(?:it|test)\s*\(\s*(['\"`])(.+?)\1")
ASSERT = re.compile(r"^\s*(assert\b|expect\(|await expect\(|self\.assert)")

commits = git("log", "--reverse", "--format=%h%x09%s", "2ce6f42..main").strip().splitlines()
for line in commits:
    sha, subj = line.split("\t", 1)
    if subj.startswith("docs:"):
        continue
    diff = git("show", "--format=", "-U0", "--no-color", sha)
    status = git("show", "--format=", "--name-status", sha)
    deleted_tests = [l.split("\t")[-1] for l in status.splitlines()
                     if l.startswith("D") and TEST_PATH.search(l.split("\t")[-1])]
    marker_hits = collections.Counter()
    marker_lines = []
    removed_defs, added_defs = collections.Counter(), collections.Counter()
    a_add = a_del = 0
    ratchet = []
    changed_expect = []
    cur = None
    hunk_del, hunk_add = [], []
    def flush():
        if cur and TEST_PATH.search(cur) and hunk_del and hunk_add:
            d = [x for x in hunk_del if ASSERT.search(x)]
            a = [x for x in hunk_add if ASSERT.search(x)]
            if d and a:
                changed_expect.append((cur, d[:3], a[:3]))
    for l in diff.splitlines():
        if l.startswith("diff --git"):
            flush(); hunk_del, hunk_add = [], []
            cur = l.split(" b/", 1)[1]
            continue
        if l.startswith("@@"):
            flush(); hunk_del, hunk_add = [], []
            continue
        if l.startswith("+++") or l.startswith("---"):
            continue
        if cur == "scripts/ci-test-counts.env" and l[:1] in "+-" and "COUNT=" in l:
            ratchet.append(l)
        if l.startswith("+"):
            body = l[1:]
            hunk_add.append(body)
            for pat, name in MARKERS:
                if re.search(pat, body):
                    marker_hits[name] += 1
                    marker_lines.append(f"{name}: {cur}: {body.strip()[:140]}")
            if cur and TEST_PATH.search(cur):
                m = PY_TEST_DEF.match(body) or JS_TEST_DEF.match(body)
                if m: added_defs[(cur, m.group(m.lastindex))] += 1
                if ASSERT.search(body): a_add += 1
        elif l.startswith("-"):
            body = l[1:]
            hunk_del.append(body)
            if cur and TEST_PATH.search(cur):
                m = PY_TEST_DEF.match(body) or JS_TEST_DEF.match(body)
                if m: removed_defs[(cur, m.group(m.lastindex))] += 1
                if ASSERT.search(body): a_del += 1
    flush()
    gone = [k for k in removed_defs if k not in added_defs]
    print(f"=== {sha} {subj}")
    print(f"    asserts +{a_add} -{a_del}; test defs +{sum(added_defs.values())} -{sum(removed_defs.values())}; removed-not-readded {len(gone)}")
    if ratchet: print("    ratchet:", " ".join(r.strip() for r in ratchet))
    for f in deleted_tests: print("    DELETED TEST FILE:", f)
    for k in gone: print("    REMOVED TEST:", k[0], "::", k[1][:100])
    for m in marker_lines: print("    MARKER", m)
    for f, d, a in changed_expect[:12]:
        print(f"    CHANGED-EXPECT {f}")
        for x in d: print("       -", x.strip()[:150])
        for x in a: print("       +", x.strip()[:150])
    if len(changed_expect) > 12: print(f"    ... {len(changed_expect)-12} more changed-expect hunks")
