"""Shared slowapi rate limiter, per-request key helpers, and the durable half.

Two stores, on purpose (Batch 99). ``limiter`` below keeps its counters in process
memory, which is right for the limits that protect a **spend** — a restart there costs
provider requests, not protection. The limits that protect a **credential** live in
Postgres instead, through :func:`consume_durable_limit`, because a restart there is a
security event and this project redeploys often enough for that to be a strategy rather
than an accident.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Annotated

import jwt
import structlog
from fastapi import Depends, Request
from limits import RateLimitItem, parse_many
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.wrappers import Limit
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_limiter_db
from src.models.rate_limit import BUCKET_KEY_MAX_LENGTH, RateLimitCounter

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def client_address(request: Request) -> str:
    """The client IP, counted from the end of ``X-Forwarded-For`` rather than the start.

    ``X-Forwarded-For`` is ``client, proxy1, proxy2 ...``: each proxy **appends** the
    address it received the connection from, so the entries on the left are whatever the
    caller chose to send and only the rightmost ones were written by infrastructure we
    control.

    Reading the leftmost entry — which this did — meant every IP-keyed limit in the app
    could be defeated by sending a different ``X-Forwarded-For`` on each request: login's
    ``5/15 minutes``, ``pin/reset-request``'s ``3/hour``, and every shared provider
    budget. The durable per-profile lockout still bounded PIN guessing, which is the only
    reason this was not worse.

    ``settings.trusted_proxy_count`` is how many hops in front of the app are ours —
    exactly one on Railway, which is the default. Counting that many from the right lands
    on the address the closest trusted proxy observed, which is the furthest left an
    attacker cannot forge. A header with fewer hops than configured falls back to its
    leftmost entry rather than indexing past the end.
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
        if hops:
            depth = min(max(settings.trusted_proxy_count, 1), len(hops))
            return hops[-depth]
    return get_remote_address(request)


# Counters are in-process and reset on restart. Batch 99 moved the two limits where
# that reset is a security event — ``/auth/login`` and ``/auth/pin/reset-request`` — to
# Postgres (see :func:`consume_durable_limit`). What is left on this storage is the
# provider budgets, where a reset costs requests rather than protection, and the
# ordinary per-user ceilings that sit behind an access token. They stay here because a
# database round trip on the pick path would be the wrong price for a quota that refills
# hourly anyway.
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


# ── The durable half (Batch 99) ───────────────────────────────────────────────
#
# Limits whose counter must survive a redeploy. Kept imperative rather than decorated
# because the store is Postgres and the write is `await`ed — `slowapi`'s `Limiter.hit`
# is synchronous, and a synchronous database call on the login path would block the
# event loop for every other request in flight.

#: ``/auth/login``. Keyed by ``login:<name>:<ip>`` so one member's attempts do not spend
#: another's, and one IP cannot work a name list from a single bucket.
LOGIN_LIMIT = "5/15 minutes"

#: ``/auth/pin/reset-request``. Keyed by client address, because the caller is by
#: definition unauthenticated and the display name is the only other thing they send —
#: keying on it would let anyone page every admin once per name they can guess.
PIN_RESET_REQUEST_LIMIT = "3/hour"


def durable_bucket_key(key: str) -> str:
    """Fold a limiter key into something a ``String(200)`` column and a btree can hold.

    ``login_key`` reads ``display_name`` out of the raw request body, which pydantic has
    not seen yet — so the key is as long as the caller wants it to be. In memory that was
    merely wasteful; against a column it is a ``DataError`` and a 500 on the endpoint an
    attacker is already probing.

    Long keys keep their readable prefix and end in a digest of the whole key, so two
    different long keys stay two different buckets rather than being merged by
    truncation.
    """
    if len(key) <= BUCKET_KEY_MAX_LENGTH:
        return key
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"{key[: BUCKET_KEY_MAX_LENGTH - len(digest) - 1]}:{digest}"


def _window_bounds(item: RateLimitItem) -> tuple[datetime, datetime]:
    """The fixed window ``now`` falls in, as naive UTC to match every other timestamp here.

    Fixed windows aligned to the epoch, which is what ``slowapi``'s default strategy uses
    and therefore what the routes behaved as before this moved stores.
    """
    span = item.get_expiry()
    now = int(time.time())
    start = now - (now % span)
    return (
        datetime.fromtimestamp(start, UTC).replace(tzinfo=None),
        datetime.fromtimestamp(start + span, UTC).replace(tzinfo=None),
    )


async def consume_durable_limit(session: AsyncSession, key: str, limit_value: str) -> bool:
    """Charge one hit against a Postgres-backed bucket. ``False`` when it is spent.

    The boolean face of :func:`charge_durable_limit`, matching
    :func:`consume_shared_limit` so the two read the same at a call site.
    """
    return (await charge_durable_limit(session, key, limit_value)) is None


async def charge_durable_limit(
    session: AsyncSession, key: str, limit_value: str
) -> RateLimitItem | None:
    """Charge one hit and return the window that refused it, or ``None`` if none did.

    The durable twin of :func:`consume_shared_limit`, with the same contract: multiple
    windows (``"2/hour;3/day"``) are charged in order and stop at the first refusal, so a
    request the daily window turns away has still spent its hourly one.

    The count is committed **before** the caller decides what to do with the answer, and
    on a session of its own (:func:`~src.database.get_limiter_db`) rather than the
    request's. That is the point of the whole batch: an attempt has to be counted whether
    or not the work behind it commits, and whether or not the process survives the next
    second.

    One statement per window, and the upsert rolls the window forward in place — so a
    counter that has aged out starts again at 1 without anything having to expire it, and
    the table holds one row per bucket rather than one per window.
    """
    for item in parse_many(limit_value):
        window_start, expires_at = _window_bounds(item)
        insert_stmt = insert(RateLimitCounter).values(
            bucket_key=durable_bucket_key(key),
            limit_item=item.key_for(),
            window_start=window_start,
            hits=1,
            expires_at=expires_at,
        )
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["bucket_key", "limit_item"],
            set_={
                # The whole of the fixed-window reset, expressed inside the upsert so no
                # read-then-write race can open between noticing the window has rolled
                # and acting on it: an aged-out row starts again at 1, a live one counts.
                "hits": case(
                    (RateLimitCounter.window_start < excluded.window_start, 1),
                    else_=RateLimitCounter.hits + 1,
                ),
                "window_start": excluded.window_start,
                "expires_at": excluded.expires_at,
            },
        ).returning(RateLimitCounter.hits)
        hits = (await session.execute(stmt)).scalar_one()
        await session.commit()
        if hits > item.amount:
            return item
    return None


async def enforce_durable_limit(
    request: Request, session: AsyncSession, key: str, limit_value: str
) -> None:
    """Charge the bucket and raise ``slowapi``'s own 429 when it is spent.

    Raising ``RateLimitExceeded`` rather than a hand-built ``HTTPException`` is
    deliberate: the app already installs ``_rate_limit_exceeded_handler``, which answers
    ``{"error": "Rate limit exceeded: 5 per 15 minute"}``, and ``AuthContext.tsx`` reads
    that shape specifically — a 429 carrying ``detail`` instead would fall through to
    "your details are wrong" and invite the retry the limit just refused. Moving the
    store must not change a byte of what the client sees.

    ``request.state.view_rate_limit`` is set for the same reason: the handler reads it
    unconditionally, so a route that raises outside the decorator has to leave behind
    what the decorator would have.
    """
    refused_by = await charge_durable_limit(session, key, limit_value)
    if refused_by is None:
        return
    request.state.view_rate_limit = (refused_by, [key, ""])
    log.warning("durable ratelimit exceeded", limit=str(refused_by), path=request.url.path)
    raise RateLimitExceeded(Limit(refused_by, lambda: key, None, False, None, None, None, 1, False))


async def enforce_login_limit(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_limiter_db)],
) -> None:
    """``/auth/login``'s durable ``5/15 minutes``, as a dependency.

    A dependency and not a decorator because the charge is `await`ed. FastAPI reads and
    caches the request body before it solves dependencies, so :func:`login_key` sees the
    same ``request._body`` here that it saw under ``@limiter.limit``.
    """
    await enforce_durable_limit(request, session, login_key(request), LOGIN_LIMIT)


async def enforce_pin_reset_request_limit(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_limiter_db)],
) -> None:
    """``/auth/pin/reset-request``'s durable ``3/hour``, keyed by client address."""
    await enforce_durable_limit(request, session, client_address(request), PIN_RESET_REQUEST_LIMIT)


DurableLoginLimit = Annotated[None, Depends(enforce_login_limit)]
DurablePinResetRequestLimit = Annotated[None, Depends(enforce_pin_reset_request_limit)]
