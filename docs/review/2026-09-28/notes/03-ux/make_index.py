"""Build lens 03's rows of screenshots/INDEX.md from the sweep JSON, plus duplicate hashes.

    ~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/03-ux/make_index.py

Reads notes/03-ux/axe/*/<base>.json (written by sweep.mjs at capture time), hashes every
PNG lens 03 wrote, and rewrites ONLY the block between the lens-03 markers in INDEX.md,
leaving other lenses' rows untouched. Writes notes/03-ux/duplicates.txt.
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/craigrobinson/the-coupon")
SHOTS = REPO / "docs/review/2026-09-28/screenshots"
NOTES = REPO / "docs/review/2026-09-28/notes/03-ux"
INDEX = SHOTS / "INDEX.md"
BEGIN, END = "<!-- lens-03 begin -->", "<!-- lens-03 end -->"


def confirm(state: str, p: dict) -> str:
    """What the DOM said at capture time, for the state the file is named for."""
    h1 = (p.get("h1") or [""])[0]
    if state == "loading":
        return f"{p['skeletons']} `aria-busy` skeletons in DOM, request held open"
    if state == "error":
        return f"`query-error-state` present ({p['errorState']}), API fulfilled 500" if p["errorState"] else "**no error state rendered** (500 fulfilled)"
    if state == "offline":
        return "network dropped after load; 'offline' text present" if p["offlineText"] else "network dropped after load; **no offline text**"
    if state in ("locked", "locked-own"):
        return "round status locked (API); 'lock' text present" if p["lockedText"] else "round locked (API)"
    if state == "settled":
        return "won/lost/settled text present after `/__e2e/settle`" if p["settledText"] else "settled via API"
    if state in ("empty", "forced-empty", "firstrun", "no-settled-rounds"):
        return f"empty copy present: “{p['snippet'][:70]}…”"
    return f"h1 “{h1}”"


rows = []
by_hash = defaultdict(list)
for js in sorted(p for p in NOTES.glob("axe/*/*.json") if not p.parent.name.endswith("-rerun")):
    if "-summary" in js.name:
        continue
    j = json.loads(js.read_text())
    base = js.stem
    name, state, width, theme = base.split("--")[:4]
    ax = j.get("axe")
    v = "—"
    if ax:
        v = " ".join(f"{x['id']}:{x['nodes']}" for x in ax["violations"]) or "0"
    for suffix in ("", "--full"):
        png = SHOTS / f"{base}{suffix}.png"
        if not png.exists():
            continue
        h = hashlib.sha256(png.read_bytes()).hexdigest()
        by_hash[h].append(png.name)
        who = j["job"].get("persona") or "signed out"
        rows.append(
            f"| `{png.name}` | `{j['proof']['url']}` | {state}{' (full page)' if suffix else ''} | {width} | {theme} "
            f"| `{h[:12]}` | {who}: {confirm(state, j['proof'])} | {v} |"
        )

# Toast / pick-feedback captures (toasts.mjs): confirmed by the toast text and live region read at capture.
MOCKED = {"pick-pricemoved": "POST fulfilled 409 PRICE_MOVED:9.99 (API shape, mocked)",
          "pick-busy": "POST fulfilled 429 PICKS_BUSY (mocked)",
          "toast-error": "POST fulfilled 500 (mocked)",
          "pick-conflict": "POST fulfilled 409 SELECTION_TAKEN (API shape, mocked; see notes)",
          "pick-confirm": "real POST by Carol"}
toast_rows = {}
for txt in ("toasts.txt", "toasts-conflict.txt"):  # later file wins (the conflict re-capture)
    f = NOTES / txt
    if not f.exists():
        continue
    for line in f.read_text().splitlines():
        m = re.match(r"(current-round--[^:]+\.png): toast=(\S.*?) type=(\S+) gapToTabBar=(\S+) bottomGap=(\S+) alert=\"(.*?)\" status=\"(.*?)\"", line)
        if not m:
            continue
        name, toast, typ, gap, bottom, alert, status = m.groups()
        png = SHOTS / name
        if not png.exists():
            continue
        h = hashlib.sha256(png.read_bytes()).hexdigest()
        _, state, width, theme = name[:-4].split("--")
        region = "role=alert" if alert else ("role=status" if status else "none")
        who = "Carol" if state == "pick-confirm" else "Alice"
        toast_rows[name] = (h, f"| `{name}` | `/leagues/the-coupon/predictions` | {state} | {width} | {theme} | `{h[:12]}` "
                    f"| {who}, {MOCKED.get(state.replace('-safearea34',''), '')}: {typ} toast {toast[:60]}…; {region}; gap to tab bar {gap}px, to viewport bottom {bottom}px | — |")
for name, (h, row) in toast_rows.items():
    by_hash[h].append(name)
    rows.append(row)

# Offline pick queue (offline.mjs): sunday-club round reopened, Alice taps a free selection offline.
for png in sorted(SHOTS.glob("current-round--offline-queued--*.png")):
    h = hashlib.sha256(png.read_bytes()).hexdigest()
    by_hash[h].append(png.name)
    _, state, width, theme = png.stem.split("--")
    rows.append(f"| `{png.name}` | `/leagues/sunday-club/predictions` | offline-queued | {width} | {theme} | `{h[:12]}` "
                "| Alice, Chromium offline emulation after load, one selection tapped: spinner on it, every selection disabled, "
                "no toast, no 'waiting to send' marker, 0 POSTs (offline-verify.txt); pick landed after reconnect (offline.txt) | — |")

dups = {h: fs for h, fs in by_hash.items() if len(fs) > 1}
(NOTES / "duplicates.txt").write_text(
    "\n".join(f"{h[:12]}  {'  '.join(fs)}" for h, fs in dups.items()) + ("\n" if dups else "none\n")
)

block = "\n".join([
    BEGIN,
    "## Lens 03 — UX / accessibility corpus",
    "",
    "Production bundle built with `notes/03-ux/build_web.py` (cwd=apps/web, CSS 45.8 KB — the harness",
    "`web.sh` build was unstyled) against the seeded scratch API on :8130 (`ODDS_PROVIDER=fake`,",
    "scheduler off, `notes/03-ux/seed_states.py`). Playwright 1.60 Chromium, deviceScaleFactor 1,",
    "`reducedMotion: reduce`, service workers blocked, theme and session put in localStorage before",
    "first paint. 390 captures use a desktop UA at 390×844 (the layout an installed PWA gets; the",
    "install gate is UA-triggered and is captured separately as `install-gate--mobile-browser`).",
    "Personas: Alice = site admin + league admin of the-coupon; Bob = member; Dave = no league.",
    "Last column: axe-core 4.10.2 violations at capture (`rule:nodes`), `—` = not run.",
    f"Duplicate hashes: {len(dups)} groups (see `notes/03-ux/duplicates.txt`).",
    "",
    "| file | url at capture | state | width | theme | sha256 | state confirmed by | axe |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
    *rows,
    END,
])

text = INDEX.read_text() if INDEX.exists() else "# Screenshot corpus index — 2026-09-28\n"
if BEGIN in text:
    text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block, text, flags=re.S)
else:
    text = text.rstrip() + "\n\n" + block + "\n"
INDEX.write_text(text)
print(len(rows), "rows;", len(dups), "duplicate groups")
