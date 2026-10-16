"""The only Monzo calls the payments service can make. Batch 208.

ADR 0009: the service reads. It never moves money, never writes to the owner's feed, never
annotates a transaction. That is enforced here rather than trusted to every caller: each
request is checked against :data:`ALLOWED_CALLS` before it is built, and anything else
raises :class:`MonzoCallRefused` without a byte leaving the process.

The two POSTs on the list are not writes to the owner's account. ``/oauth2/token`` is how a
connect finishes and how the token is refreshed; ``/webhooks`` asks Monzo to nudge this
service when a transaction appears (owner decision, 2026-10-16).

Errors carry a short ``code`` for the organiser's link-health line and nothing from the
response body, which can echo account data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

MONZO_API = "https://api.monzo.com"
MONZO_AUTH = "https://auth.monzo.com/"

#: Every (method, path) this service may call. Nothing else is reachable.
ALLOWED_CALLS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"/oauth2/token")),
    ("GET", re.compile(r"/accounts")),
    ("GET", re.compile(r"/transactions")),
    ("GET", re.compile(r"/transactions/tx_[A-Za-z0-9]+")),
    ("GET", re.compile(r"/webhooks")),
    ("POST", re.compile(r"/webhooks")),
)

#: Monzo pages transactions at most 100 at a time. A page cap stops a misbehaving cursor
#: from looping; 50 pages is 5,000 transactions, far beyond one five-minute window.
PAGE_LIMIT = 100
MAX_PAGES = 50

TIMEOUT_SECONDS = 15.0


class MonzoError(RuntimeError):
    code = "monzo_error"


class MonzoCallRefused(MonzoError):
    """A call outside :data:`ALLOWED_CALLS`. Never sent."""

    code = "call_refused"


class MonzoUnavailable(MonzoError):
    """Monzo could not be reached, timed out, rate-limited us or failed (5xx)."""

    code = "monzo_unavailable"


class MonzoUnauthorised(MonzoError):
    """401: the access token is no longer accepted."""

    code = "unauthorised"


class MonzoForbidden(MonzoError):
    """403: until the owner approves in the Monzo app, account data is withheld."""

    code = "forbidden"


class MonzoRefused(MonzoError):
    """Any other 4xx — for the token endpoint, a code or refresh token Monzo will not take."""

    code = "refused"


class MonzoMalformed(MonzoError):
    """A 2xx whose body is not the shape Monzo documents."""

    code = "malformed_response"


@dataclass(frozen=True)
class TokenGrant:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str


def is_allowed(method: str, path: str) -> bool:
    return any(method == allowed and pattern.fullmatch(path) for allowed, pattern in ALLOWED_CALLS)


def authorise_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Where the owner's browser is sent to start a connect."""
    query = httpx.QueryParams(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{MONZO_AUTH}?{query}"


class MonzoClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _call(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not is_allowed(method, path):
            raise MonzoCallRefused(f"{method} {path} is not a call this service makes")
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        try:
            async with httpx.AsyncClient(
                base_url=MONZO_API, timeout=TIMEOUT_SECONDS, transport=self._transport
            ) as http:
                response = await http.request(
                    method, path, params=params, data=data, headers=headers
                )
        except httpx.HTTPError as failure:
            raise MonzoUnavailable(type(failure).__name__) from None
        if response.status_code == 401:
            raise MonzoUnauthorised(f"{method} {path}: 401")
        if response.status_code == 403:
            raise MonzoForbidden(f"{method} {path}: 403")
        if response.status_code == 429 or response.status_code >= 500:
            raise MonzoUnavailable(f"{method} {path}: {response.status_code}")
        if response.status_code >= 400:
            raise MonzoRefused(f"{method} {path}: {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise MonzoMalformed(f"{method} {path}: not JSON") from None
        if not isinstance(body, dict):
            raise MonzoMalformed(f"{method} {path}: not an object")
        return body

    async def _grant(self, data: dict[str, str]) -> TokenGrant:
        body = await self._call("POST", "/oauth2/token", data=data)
        access = body.get("access_token")
        refresh = body.get("refresh_token")
        expires_in = body.get("expires_in")
        user_id = body.get("user_id")
        if not (isinstance(access, str) and access and isinstance(user_id, str) and user_id):
            raise MonzoMalformed("token response without an access token or user")
        if not (isinstance(refresh, str) and refresh):
            # Only a confidential client is given a refresh token, and without one the
            # service would stop reading within a day of every connect.
            raise MonzoMalformed("token response without a refresh token")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise MonzoMalformed("token response without a lifetime")
        return TokenGrant(access, refresh, expires_in, user_id)

    async def exchange_code(
        self, *, client_id: str, client_secret: str, redirect_uri: str, code: str
    ) -> TokenGrant:
        return await self._grant(
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            }
        )

    async def refresh(
        self, *, client_id: str, client_secret: str, refresh_token: str
    ) -> TokenGrant:
        """A new access token *and* a new refresh token; the old refresh token is spent."""
        return await self._grant(
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            }
        )

    async def accounts(self, access_token: str) -> list[dict[str, Any]]:
        body = await self._call("GET", "/accounts", access_token=access_token)
        accounts = body.get("accounts")
        if not isinstance(accounts, list):
            raise MonzoMalformed("accounts response without accounts")
        return [account for account in accounts if isinstance(account, dict)]

    async def transactions(
        self, access_token: str, account_id: str, since: str
    ) -> list[dict[str, Any]]:
        """Every transaction on one account from ``since`` (RFC 3339), oldest first."""
        found: list[dict[str, Any]] = []
        cursor = since
        for _page in range(MAX_PAGES):
            body = await self._call(
                "GET",
                "/transactions",
                access_token=access_token,
                params={"account_id": account_id, "since": cursor, "limit": PAGE_LIMIT},
            )
            page = body.get("transactions")
            if not isinstance(page, list):
                raise MonzoMalformed("transactions response without transactions")
            page = [transaction for transaction in page if isinstance(transaction, dict)]
            found.extend(page)
            last_id = page[-1].get("id") if page else None
            if len(page) < PAGE_LIMIT or not isinstance(last_id, str):
                return found
            # Monzo's ``since`` also takes a transaction id, which pages without overlap.
            cursor = last_id
        return found

    async def transaction(self, access_token: str, transaction_id: str) -> dict[str, Any]:
        body = await self._call("GET", f"/transactions/{transaction_id}", access_token=access_token)
        transaction = body.get("transaction")
        if not isinstance(transaction, dict):
            raise MonzoMalformed("transaction response without a transaction")
        return transaction

    async def webhooks(self, access_token: str, account_id: str) -> list[dict[str, Any]]:
        body = await self._call(
            "GET", "/webhooks", access_token=access_token, params={"account_id": account_id}
        )
        hooks = body.get("webhooks")
        if not isinstance(hooks, list):
            raise MonzoMalformed("webhooks response without webhooks")
        return [hook for hook in hooks if isinstance(hook, dict)]

    async def register_webhook(self, access_token: str, account_id: str, url: str) -> None:
        await self._call(
            "POST",
            "/webhooks",
            access_token=access_token,
            data={"account_id": account_id, "url": url},
        )
