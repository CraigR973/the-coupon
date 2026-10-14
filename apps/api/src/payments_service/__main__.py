"""``python -m src.payments_service`` — the payments service's whole start command.

One Python entry point rather than a shell chain, so Railway's start command needs no shell
to expand ``$PORT`` or sequence ``&&``. It checks before it binds: a refused boot exits
non-zero without ever listening, so Railway's healthcheck fails the deployment and the
previous one keeps serving.
"""

from __future__ import annotations

import asyncio
import os
import sys

import uvicorn

from src.payments_service.boot import PaymentsBootRefused, verify


def main() -> int:
    try:
        revision = asyncio.run(verify())
    except PaymentsBootRefused as refused:
        print(f"payments boot refused: {refused}", file=sys.stderr, flush=True)
        return 1
    print(f"payments boot: the database is at {revision}, as this image expects", flush=True)
    uvicorn.run(
        "src.payments_service.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
