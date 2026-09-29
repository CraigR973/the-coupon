"""Static route inventory: every FastAPI route vs every web-client caller.

Run: python3 route_inventory.py  (no imports of the app; pure text scan)
Prints: METHOD PATH  file:line  | callers in apps/web/src (non-test) that hit it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/Users/craigrobinson/the-coupon")
ROUTERS = ROOT / "apps/api/src/routers"
WEB = ROOT / "apps/web/src"

prefix_re = re.compile(r'APIRouter\(\s*prefix="([^"]*)"')
route_re = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*\n?\s*"([^"]*)"', re.M)

routes: list[tuple[str, str, str]] = []
for f in sorted(ROUTERS.glob("*.py")):
    text = f.read_text()
    m = prefix_re.search(text)
    prefix = m.group(1) if m else ""
    for rm in route_re.finditer(text):
        line = text.count("\n", 0, rm.start()) + 1
        routes.append((rm.group(1).upper(), prefix + rm.group(2), f"{f.name}:{line}"))

# Web sources (exclude tests)
web_files = [
    p
    for p in WEB.rglob("*.ts*")
    if ".test." not in p.name and "/test/" not in str(p)
]
web_text = {p: p.read_text() for p in web_files}


def pattern_for(path: str) -> re.Pattern[str]:
    # strip /api/v1 then turn {param} into a wildcard that matches ${...} or literal
    p = path.removeprefix("/api/v1")
    parts = re.split(r"(\{[^}]+\})", p)
    rx = ""
    for part in parts:
        if part.startswith("{"):
            rx += r"(?:\$\{[^}]+\}|[A-Za-z0-9_:.-]+)"
        else:
            rx += re.escape(part)
    return re.compile(rx + r"(?:[`'\"?]|\$\{)")


for method, path, loc in routes:
    rx = pattern_for(path)
    hits = []
    for p, t in web_text.items():
        for m in rx.finditer(t):
            ln = t.count("\n", 0, m.start()) + 1
            hits.append(f"{p.relative_to(WEB)}:{ln}")
    print(f"{method:6} {path:70} {loc:28} | {', '.join(hits[:4]) or '-- NO WEB CALLER --'}")
