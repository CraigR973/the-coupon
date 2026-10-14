"""The payments service's routes. Until Batch 208 that is only its health pair.

``/health`` mirrors the API's, so ``scripts/check-deploy-drift.sh`` reads both services the
same way: the commit ``/ship-prod`` stamped and the migration head bundled in the image.
``/health/ready`` is Railway's healthcheck, and stays red unless the database is at exactly
that head, which is the same rule the boot enforces.
"""

from __future__ import annotations

import os
from functools import cache

from fastapi import FastAPI, Response

from src.payments_service.boot import (
    DATABASE_URL_ENV,
    PaymentsBootRefused,
    applied_revision,
    bundled_head,
)

app = FastAPI(title="The Coupon payments", docs_url=None, redoc_url=None, openapi_url=None)


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
