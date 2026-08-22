import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.config import Environment, settings


def _incoming_correlation_id(request: Request) -> str | None:
    """A caller-supplied ``X-Correlation-ID``, but only if it is really one.

    The value used to be taken as sent. It is bound into structlog for the whole request,
    so every log line that request emits carries it, and it is echoed back on the
    response — which made an unbounded, attacker-chosen string a cheap way to multiply
    log volume against a plan whose retention is already thin. The JSON renderer escapes
    the content, so this is about size, not injection.

    Accepting only a well-formed UUID keeps the useful case — a client correlating its
    own request with the server's logs — and costs a forger nothing they can spend.
    Anything else is discarded and a fresh id is minted, so a request is never
    untraceable.
    """
    raw = request.headers.get("X-Correlation-ID")
    if not raw or len(raw) > 36:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request, propagate it in the response header,
    and bind it to structlog context so every log line emitted during the request carries it."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = _incoming_correlation_id(request) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        if settings.environment != Environment.development:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Mitigate XSS-based exfiltration of the long-lived localStorage refresh
        # token. The frontend is a single-page app served from Vercel; this API
        # only serves JSON so there is no script/style/img surface here.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Every route here answers with one member's data behind a bearer token. Shared
        # caches should not store an Authorization-bearing response by default, so this
        # is defence in depth rather than a fix — but it is one header, and the default
        # is silence rather than "no".
        response.headers["Cache-Control"] = "no-store"
        return response
