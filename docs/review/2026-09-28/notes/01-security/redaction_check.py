"""Batch 155 check: the redacted members' names must be absent from the working tree.

The names are derived, never written down: from Batch 155's own commit (ca62213), pair each
removed line with its replacement and take the words that became "Member X". The script
then greps the tracked tree and reports counts per anonymous index only — it never prints
a name, so these notes do not reintroduce what the batch removed.

    ~/.cache/the-coupon/ci-local-venv/bin/python redaction_check.py > redaction-check.txt
"""

from __future__ import annotations

import difflib
import re
import subprocess

REPO = "/Users/craigrobinson/the-coupon"
COMMIT = "ca62213"

diff = subprocess.run(["git", "-C", REPO, "show", "--no-color", "-U0", COMMIT],
                      capture_output=True, text=True).stdout
names: set[str] = set()
removed: list[str] = []
added: list[str] = []


def harvest() -> None:
    """For each added line carrying "Member X", turn it into a pattern with the "Member X"
    slots as captures and match it against the removed lines of the same hunk."""
    for new in added:
        if not re.search(r"Member [A-L]\b", new):
            continue
        parts = re.split(r"Member [A-L]\b", new)
        pat = "^" + "(.+?)".join(re.escape(p) for p in parts) + "$"
        for old in removed:
            m = re.match(pat, old)
            if m:
                for g in m.groups():
                    for cand in re.findall(r"[A-Z][a-z'\-]+(?: [A-Z][a-z'\-]+)+", g):
                        names.add(cand)
                break


for line in diff.splitlines():
    if line.startswith("@@") or line.startswith("diff "):
        harvest()
        removed, added = [], []
    elif line.startswith("-") and not line.startswith("---"):
        removed.append(line[1:])
    elif line.startswith("+") and not line.startswith("+++"):
        added.append(line[1:])
harvest()

# Keep full "First Surname" names and bare first names that occur in a full name.
full = sorted(n for n in names if " " in n)
firsts = sorted({n.split()[0] for n in full})
print(f"derived from {COMMIT}: {len(full)} full names ({len(firsts)} distinct first names)")
tracked = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True).stdout.split()
total = 0
for idx, n in enumerate(full, 1):
    r = subprocess.run(["git", "-C", REPO, "grep", "-I", "-l", "-i", "-F", n], capture_output=True, text=True)
    files = [f for f in r.stdout.split() if f]
    total += len(files)
    print(f"  full name #{idx:02d}: {len(files)} tracked files" + (f" -> {files}" if files else ""))
print(f"total tracked files containing a redacted full name: {total}")
# Old sign-in names are single tokens; report any surname that still appears, as a count.
surnames = sorted({n.split()[-1] for n in full})
hits = 0
for idx, s in enumerate(surnames, 1):
    r = subprocess.run(["git", "-C", REPO, "grep", "-I", "-l", "-w", "-F", s], capture_output=True, text=True)
    files = [f for f in r.stdout.split() if f and "node_modules" not in f]
    hits += bool(files)
    print(f"  surname #{idx:02d}: {len(files)} tracked files" + (f" -> {files[:5]}" if files else ""))
print(f"surnames still present somewhere in the tree: {hits} of {len(surnames)}")
