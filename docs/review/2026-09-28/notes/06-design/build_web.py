"""Build + serve the production web bundle for lens 06 (copied from lens 03, ports changed), with the right working directory.

Why this exists instead of `harness/web.sh`: `tailwind.config.ts` declares
`content: ['./index.html', './src/**/*.{ts,tsx}']`, which Tailwind resolves against the
*process* working directory. web.sh runs `vite build <root>` from wherever it is invoked,
so Tailwind scans nothing, emits no utilities, and the bundle's CSS is 9.1 KB (the gate's
own `apps/web/dist` CSS is 45.8 KB). Every page then renders unstyled. Running the same
build with cwd=apps/web (Python `cwd=`, never a shell `cd`) fixes it.

    ~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/06-design/build_web.py

Builds into <scratchpad>/web-design (VITE_API_URL=http://127.0.0.1:8160 in the process env,
which Vite prefers over apps/web/.env.local), refuses to serve unless the bundle names the
local API and the CSS is > 30 KB, then serves it on 127.0.0.1:4360 --strictPort.
"""

import os
import subprocess
import sys
from pathlib import Path

WEB = Path("/Users/craigrobinson/the-coupon/apps/web")
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
OUT = SCRATCH / "web-design"
API = "http://127.0.0.1:8160"
NODE = subprocess.run(
    ["bash", "-c", '. "$HOME/.nvm/nvm.sh" >/dev/null && nvm which 24'],
    capture_output=True, text=True, check=True,
).stdout.strip()
VITE = str(WEB / "node_modules/vite/bin/vite.js")

env = dict(os.environ, VITE_API_URL=API)
with open(SCRATCH / "web-design.build.txt", "w") as log:
    subprocess.run([NODE, VITE, "build", "--outDir", str(OUT), "--emptyOutDir"],
                   cwd=WEB, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
assets = list((OUT / "assets").iterdir())
if not any(API in p.read_text(errors="ignore") for p in assets if p.suffix == ".js"):
    sys.exit(f"bundle does not reference {API}")
css = [p.stat().st_size for p in assets if p.suffix == ".css"]
print("css bytes", css, flush=True)
if max(css) < 30_000:
    sys.exit("CSS too small — Tailwind utilities missing")
subprocess.run([NODE, VITE, "preview", "--outDir", str(OUT), "--host", "127.0.0.1",
                "--port", "4360", "--strictPort"], cwd=WEB, env=env)
