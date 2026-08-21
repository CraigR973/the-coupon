"""Shared slowapi rate limiter and per-request key helpers."""

import hashlib
import json

import jwt
import structlog
from fastapi import Request
from limits import parse_many
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config import settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def client_address(request: Request) -> str:
    """Return the user-facing client IP, honoring Railway's proxy header."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return get_remote_address(request)


# Counters are in-process and reset on restart. This is acceptable for a
# single-instance Railway deployment — the DB lockout (max_attempts) is the
# durable brute-force guard; these counters add a short-term rate layer.
limiter = Limiter(key_func=client_address)


def per_user_key(request: Request) -> str:
    """Rate-limit key derived from the bearer token's user id.

    Falls back to remote address when no valid token is present so
    unauthenticated requests are still bounded (by IP).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(
                token,
                settings.jwt_access_secret,
                algorithms=["HS256"],
                # Allow expired tokens so the user is still rate-limited
                # by ID rather than falling through to the shared IP bucket.
                options={"verify_exp": False},
            )
            return f"user:{payload['sub']}"
        except Exception:
            pass
    return client_address(request)


def login_key(request: Request) -> str:
    """Key for login: display_name + IP to limit per-credential brute-force.

    FastAPI reads and caches the request body in request._body before calling
    the route handler, so accessing it synchronously here is safe.
    """
    try:
        body_bytes: bytes = getattr(request, "_body", b"") or b""
        data = json.loads(body_bytes)
        name = str(data.get("display_name", "")).lower()
    except Exception:
        name = ""
    return f"login:{name}:{client_address(request)}"


def refresh_token_key(request: Request) -> str:
    """Key for token refresh: SHA-256 of the refresh token so each token has its own bucket.

    FastAPI reads and caches the request body in request._body before calling
    the route handler, so accessing it synchronously here is safe.
    """
    try:
        body_bytes: bytes = getattr(request, "_body", b"") or b""
        data = json.loads(body_bytes)
        raw_token = str(data.get("refresh_token", ""))
        return f"refresh:{hashlib.sha256(raw_token.encode()).hexdigest()}"
    except Exception:
        return client_address(request)


def consume_shared_limit(key: str, limit_value: str, scope: str) -> bool:
    """Charge one hit against the bucket ``@limiter.shared_limit(limit_value, scope)`` uses.

    The imperative half of a shared limit, for a cost that only *sometimes* arises. A
    decorator charges every request that reaches the route, which is right when the route
    always spends what the limit protects; Batch 47's populate path spends a provider
    request only when the fixture pool cannot serve the date, and charging the free case
    would price the common one out of existence.

    Same storage, same key, same scope as the decorator — ``slowapi`` evaluates a limit as
    ``limiter.hit(item, key, scope)`` — so a route decorated with
    ``shared_limit(value, scope)`` and a caller passing the same ``scope`` here draw down
    one bucket and cannot be combined to exceed it.

    Multiple windows (``"2/hour;3/day"``) are charged in order and stop at the first
    refusal, exactly as ``slowapi`` charges them: a request refused by the daily window
    has still spent its hourly one.

    Returns ``False`` when the bucket is empty. Raising is the caller's decision, because
    the answer differs by caller — an admin asking for a refresh deserves a 429, while a
    league being created deserves the rounds the pool *can* give it and no error at all.
    """
    return all(limiter.limiter.hit(item, key, scope) for item in parse_many(limit_value))
