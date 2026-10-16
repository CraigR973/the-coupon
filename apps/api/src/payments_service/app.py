"""The payments service's routes: its health pair, and the Monzo connection (Batch 208).

``/health`` mirrors the API's, so ``scripts/check-deploy-drift.sh`` reads both services the
same way: the commit ``/ship-prod`` stamped and the migration head bundled in the image.
``/health/ready`` is Railway's healthcheck, and stays red unless the database is at exactly
that head, which is the same rule the boot enforces.

The Monzo routes:

* ``/monzo/oauth/start`` sends the owner's browser to Monzo to connect, and
  ``/monzo/oauth/callback`` is where Monzo sends it back (the address registered on the
  owner's OAuth client, byte for byte). After that Monzo waits for approval in its app.
* ``/monzo/webhook/<secret>`` is the webhook. Monzo does not sign webhooks, so the path
  secret only keeps strangers from making the service spend Monzo requests; the body is
  never believed. Only its transaction id is used, to re-read the transaction from Monzo.

Without its four ``MONZO_*`` settings the service still serves its health pair, and the
Monzo routes say so rather than half-working.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import os
from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.payments_service.boot import (
    DATABASE_URL_ENV,
    PaymentsBootRefused,
    applied_revision,
    bundled_head,
)
from src.payments_service.crypto import TokenCipherUnavailable
from src.payments_service.db import session_factory
from src.payments_service.ingest import TRANSACTION_ID
from src.payments_service.reader import ConnectOutcome, PaymentsReader, run_catch_up_forever
from src.payments_service.settings import (
    CALLBACK_PATH,
    CONNECT_PATH,
    WEBHOOK_PATH_PREFIX,
    monzo_settings,
    monzo_settings_problems,
)

log = logging.getLogger("payments.app")

#: The Monzo events that mean "a transaction exists or changed". Anything else is ignored.
WEBHOOK_EVENTS = frozenset({"transaction.created", "transaction.updated"})


@cache
def _configured_reader() -> PaymentsReader | None:
    settings = monzo_settings()
    database_url = os.environ.get(DATABASE_URL_ENV, "").strip()
    if settings is None or not database_url:
        problems = monzo_settings_problems()
        if not database_url:
            problems.append(f"{DATABASE_URL_ENV} is not set")
        # Names and rules only: the values are sealed, and a log line must never carry one.
        log.error("monzo reading is off: %s", "; ".join(problems) or "unknown reason")
        return None
    try:
        return PaymentsReader(settings, session_factory(database_url))
    except TokenCipherUnavailable as unusable:
        log.error("monzo reading is off: %s", unusable)
        return None


def get_reader() -> PaymentsReader | None:
    """The reader, or ``None`` when the service is not configured for Monzo."""
    return _configured_reader()


Reader = Annotated[PaymentsReader | None, Depends(get_reader)]


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    reader = get_reader()
    task = asyncio.create_task(run_catch_up_forever(reader)) if reader is not None else None
    if reader is None:
        log.warning("monzo reading is off: the service is not configured")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="The Coupon payments",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@cache
def _bundled_head_or_unknown() -> str:
    try:
        return bundled_head()
    except Exception:
        return "unknown"


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "payments",
        "sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "unknown",
        "migration": _bundled_head_or_unknown(),
    }


@app.get("/health/ready")
async def ready(response: Response) -> dict[str, str]:
    expected = _bundled_head_or_unknown()
    database_url = os.environ.get(DATABASE_URL_ENV, "").strip()
    try:
        applied = await applied_revision(database_url) if database_url else "unknown"
    except PaymentsBootRefused:
        applied = "unknown"
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "db": "unreachable"}
    if applied != expected or expected == "unknown":
        response.status_code = 503
        return {"status": "not_ready", "db": "ok", "migration": applied, "expected": expected}
    return {"status": "ready", "db": "ok", "migration": applied}


# ── Connecting ────────────────────────────────────────────────────────────────


def _page(status_code: int, title: str, body: str) -> HTMLResponse:
    """A plain page for the owner's browser. Nothing from the request is echoed into it."""
    return HTMLResponse(
        status_code=status_code,
        content=(
            "<!doctype html><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            f"<title>{title}</title><h1>{title}</h1><p>{body}</p>"
        ),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


_NOT_CONFIGURED = (
    503,
    "Monzo is not set up",
    "This service is missing its Monzo settings, so it cannot connect.",
)

_CONNECT_PAGES: dict[ConnectOutcome, tuple[int, str, str]] = {
    ConnectOutcome.awaiting_approval: (
        200,
        "Now approve in the Monzo app",
        "The browser half is done. Open the Monzo app and approve access for this "
        "service; until you do, Monzo shares nothing with it. You can close this page.",
    ),
    ConnectOutcome.bad_state: (
        400,
        "This connect link has expired",
        f"It was already used or is more than ten minutes old. Start again at {CONNECT_PATH}.",
    ),
    ConnectOutcome.other_user: (
        409,
        "Already connected to another Monzo account",
        "This service reads one Monzo account and is connected to a different one, so this "
        "connect was not kept.",
    ),
    ConnectOutcome.refused: (
        400,
        "Monzo did not accept this connect",
        f"Nothing was changed. Start again at {CONNECT_PATH}.",
    ),
    ConnectOutcome.unavailable: (
        503,
        "Monzo could not be reached",
        f"Nothing was changed. Start again at {CONNECT_PATH} in a few minutes.",
    ),
}


@app.get(CONNECT_PATH, response_model=None)
async def connect_start(reader: Reader) -> Response:
    if reader is None:
        return _page(*_NOT_CONFIGURED)
    return RedirectResponse(
        await reader.start_connect(),
        status_code=302,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@app.get(CALLBACK_PATH, response_model=None)
async def connect_callback(
    reader: Reader, code: str | None = None, state: str | None = None
) -> Response:
    if reader is None:
        return _page(*_NOT_CONFIGURED)
    if not code or not state or len(code) > 2048 or len(state) > 256:
        return _page(*_CONNECT_PAGES[ConnectOutcome.refused])
    return _page(*_CONNECT_PAGES[await reader.finish_connect(code, state)])


# ── The webhook ───────────────────────────────────────────────────────────────


def _transaction_id(body: Any) -> str | None:
    if not isinstance(body, dict) or body.get("type") not in WEBHOOK_EVENTS:
        return None
    data = body.get("data")
    transaction_id = data.get("id") if isinstance(data, dict) else None
    if isinstance(transaction_id, str) and len(transaction_id) <= 64:
        if TRANSACTION_ID.fullmatch(transaction_id):
            return transaction_id
    return None


@app.post(WEBHOOK_PATH_PREFIX + "{path_secret}", response_model=None)
async def webhook(path_secret: str, request: Request, reader: Reader) -> Response:
    if reader is None or not hmac.compare_digest(
        path_secret.encode(), reader.settings.webhook_path_secret.encode()
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    try:
        body = await request.json()
    except ValueError:
        body = None
    transaction_id = _transaction_id(body)
    if transaction_id is not None:
        # Monzo retries anything but a 2xx five times. The catch-up covers a failed
        # re-read, so a failure here is recorded and answered 200 like a success.
        await reader.nudge(transaction_id)
    return JSONResponse(status_code=200, content={"status": "ok"})
