"""One-process local stack for the 2026-09-28 review: scratch PostgreSQL + seeded API.

Run with the gate's venv (it has pgserver, alembic, uvicorn and every app dependency):

    ~/.cache/the-coupon/ci-local-venv/bin/python \
        docs/review/2026-09-28/notes/harness/stack.py --name sec --api-port 8110 \
        --origin http://127.0.0.1:4310 [--seed]

Why one process: pgserver's cluster lives only as long as the process that called
get_server(), so the cluster, alembic and uvicorn are all children of this script.
It writes <scratchpad>/stack-<name>.json with the local DATABASE_URL (a unix-socket
scratch cluster, no password) and the API origin, then blocks until killed.

The API is tests.e2e_server:app (FakeBetfair odds, POST /__e2e/seed|lock|settle),
with SCHEDULER_ENABLED=false and ODDS_PROVIDER=fake. Nothing here can reach a live
provider or production.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pgserver

ROOT = Path("/Users/craigrobinson/the-coupon")
API = ROOT / "apps" / "api"
SCRATCH = Path(
    os.environ.get(
        "REVIEW_SCRATCH",
        "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
        "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad",
    )
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--api-port", type=int, required=True)
    p.add_argument("--origin", default="http://127.0.0.1:4173")
    p.add_argument("--seed", action="store_true", help="POST /__e2e/seed once the API is up")
    p.add_argument("--keep-data", action="store_true", help="do not reset the schema on start")
    p.add_argument("--no-api", action="store_true", help="database only (for in-process scripts)")
    args = p.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    pgdata = SCRATCH / f"pg-{args.name}"
    pgdata.mkdir(exist_ok=True)
    server = pgserver.get_server(str(pgdata))
    if not args.keep_data:
        server.psql("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    db_url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    env = dict(os.environ)
    env.update(
        DATABASE_URL=db_url,
        JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters",
        JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters",
        SCHEDULER_ENABLED="false",
        ODDS_PROVIDER="fake",
        FRONTEND_ORIGIN=args.origin,
        PYTHONPATH=str(API),
    )
    env.pop("ENVIRONMENT", None)

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=env, check=True)

    state = {
        "name": args.name,
        "database_url": db_url,
        "pgdata": str(pgdata),
        "api": None if args.no_api else f"http://127.0.0.1:{args.api_port}",
        "frontend_origin": args.origin,
        "pid": os.getpid(),
    }
    uvicorn = None
    if not args.no_api:
        log = open(SCRATCH / f"stack-{args.name}.api.log", "w")
        uvicorn = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "tests.e2e_server:app",
             "--host", "127.0.0.1", "--port", str(args.api_port)],
            cwd=API, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        for _ in range(240):
            try:
                urllib.request.urlopen(f"{state['api']}/api/v1/health", timeout=2).read()
                break
            except Exception:
                if uvicorn.poll() is not None:
                    print("uvicorn exited; see", log.name, file=sys.stderr)
                    return 1
                time.sleep(0.5)
        if args.seed:
            req = urllib.request.Request(f"{state['api']}/__e2e/seed", method="POST", data=b"")
            print(urllib.request.urlopen(req, timeout=60).read().decode())

    (SCRATCH / f"stack-{args.name}.json").write_text(json.dumps(state, indent=2))
    print(json.dumps(state), flush=True)

    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while not stop:
        if uvicorn is not None and uvicorn.poll() is not None:
            print("uvicorn exited", file=sys.stderr)
            break
        time.sleep(1)
    if uvicorn is not None and uvicorn.poll() is None:
        uvicorn.terminate()
        uvicorn.wait(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
