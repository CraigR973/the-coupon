"""``python -m src.payments_service`` — the payments service's whole start command.

One Python entry point rather than a shell chain, so Railway's start command needs no shell
to expand ``$PORT`` or sequence ``&&``. It checks before it binds: a refused boot exits
non-zero without ever listening, so Railway's healthcheck fails the deployment and the
previous one keeps serving.

Batch 208: logging goes through the API's redacting JSON renderer, told every Monzo secret
this process holds, and uvicorn's own loggers are routed through it too
(``log_config=None``). The webhook's address carries its path secret, and an access-log line
is exactly where that would otherwise be printed.
"""

from __future__ import annotations

import asyncio
import os
import sys

import uvicorn

from src.logging_config import configure_logging
from src.payments_service.boot import PaymentsBootRefused, verify
from src.payments_service.settings import monzo_settings


def configure_payments_logging(environ: dict[str, str] | None = None) -> None:
    values = dict(os.environ) if environ is None else environ
    settings = monzo_settings(values)
    configure_logging(
        values.get("LOG_LEVEL", "INFO"),
        secrets=settings.secrets() if settings is not None else (),
    )


def main() -> int:
    try:
        revision = asyncio.run(verify())
    except PaymentsBootRefused as refused:
        print(f"payments boot refused: {refused}", file=sys.stderr, flush=True)
        return 1
    print(f"payments boot: the database is at {revision}, as this image expects", flush=True)
    configure_payments_logging()
    uvicorn.run(
        "src.payments_service.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
