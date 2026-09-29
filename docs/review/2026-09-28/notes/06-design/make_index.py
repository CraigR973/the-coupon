"""Write lens 06's rows into screenshots/INDEX.md between its own markers.

Reads notes/06-design/captures.json (a list of {file, url, state, width, theme, confirmed})
and computes each file's sha256 now, so the index always matches the bytes on disk.
Only the text between `<!-- lens-06 begin -->` and `<!-- lens-06 end -->` is rewritten;
other passes' rows are never touched. Also writes notes/06-design/duplicates.txt.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/craigrobinson/the-coupon/docs/review/2026-09-28")
SHOTS = ROOT / "screenshots"
NOTES = ROOT / "notes/06-design"
rows = json.loads((NOTES / "captures.json").read_text())
by_hash = defaultdict(list)
lines = [
    "<!-- lens-06 begin -->",
    "## Lens 06 — premium design corpus additions",
    "",
    "Production bundle built by `notes/06-design/build_web.py` (cwd=apps/web, CSS 45,794 B — the same",
    "file name, `index-Br02Ny1y.css`, that production serves) against the lens 06 stack on :8160",
    "(`notes/06-design/stack_design.py`: the e2e server + a test-only `POST /__review/move-price`;",
    "`ODDS_PROVIDER=fake`, scheduler off). Playwright Chromium, deviceScaleFactor 1, reduced motion,",
    "service workers blocked. Every state below was driven for real — no request was mocked — and the",
    "last column says what proved it. Each PNG was opened after capture; duplicates are listed in",
    "`notes/06-design/duplicates.txt`.",
    "",
    "| file | url at capture | state | width | theme | sha256 | state confirmed by |",
    "| --- | --- | --- | --- | --- | --- | --- |",
]
for r in rows:
    p = SHOTS / r["file"]
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    by_hash[h].append(r["file"])
    lines.append(f"| `{r['file']}` | `{r['url']}` | {r['state']} | {r['width']} | {r['theme']} | `{h[:12]}` | {r['confirmed']} |")
lines.append("<!-- lens-06 end -->")
index = (SHOTS / "INDEX.md").read_text()
block = "\n".join(lines) + "\n"
if "<!-- lens-06 begin -->" in index:
    head, rest = index.split("<!-- lens-06 begin -->", 1)
    _, tail = rest.split("<!-- lens-06 end -->\n", 1)
    index = head + block + tail
else:
    index = index.rstrip("\n") + "\n\n" + block
(SHOTS / "INDEX.md").write_text(index)
dups = [v for v in by_hash.values() if len(v) > 1]
(NOTES / "duplicates.txt").write_text(
    f"{len(rows)} lens-06 captures, {len(by_hash)} distinct hashes, {len(dups)} duplicate groups\n"
    + "".join("  " + " = ".join(v) + "\n" for v in dups)
)
print(f"{len(rows)} rows, {len(dups)} duplicate groups")
