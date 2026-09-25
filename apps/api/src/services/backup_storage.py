"""Off-site storage for the database backup (Batch 95).

The scored history of the game — ``picks.odds_at_pick``, ``points_awarded`` and ``status``
— had no second copy. Supabase's Free plan carries no managed backup and no PITR, and
Batch 75 removed a nightly ``pg_dump`` that wrote to ``/tmp`` on a service with no volume,
so every copy died with the next redeploy. This is the destination that survives one: any
S3-compatible object store. The owner chose Cloudflare R2 in the EU jurisdiction on
2026-09-25; nothing here is R2-specific beyond the ``auto`` region it signs with.

**Signed by hand, deliberately.** The job needs two requests — list one key to prove the
target is reachable, and put one object — and ``httpx`` is already how this API talks to
storage (``avatar_storage.py``). AWS Signature Version 4 is a published canonical-string
algorithm over HMAC-SHA256, and ``tests/test_offsite_backup.py`` pins this implementation
to vectors from AWS's own signing test suite, so a slip in the canonical form fails a test
rather than a Monday morning. boto3 was the alternative: five more packages in every
production install, for two requests.

**Nothing secret leaves this module.** The signing key never reaches a log line, and the
errors raised carry the status and the store's own error code, never a header.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from src.config import Settings

#: What the store is given to sign with. R2 accepts only this for its S3 API.
_SERVICE = "s3"

#: One request, generously: the upload is a few megabytes and runs once a week.
_TIMEOUT_SECONDS = 60.0


class BackupTargetError(RuntimeError):
    """The off-site target is missing, misconfigured, unreachable or refused a request."""


@dataclass(frozen=True)
class BackupTarget:
    """Where the weekly archive goes. Built only by :func:`backup_target_from_settings`."""

    endpoint: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    prefix: str


def backup_target_from_settings(settings: Settings) -> BackupTarget:
    """The configured target, or a :class:`BackupTargetError` naming what is missing.

    Resolved before anything else runs, so a half-configured deployment says exactly which
    variable it lacks instead of dumping the database and then failing to put it anywhere.
    """
    if settings.backup_storage != "s3":
        raise BackupTargetError(
            f"BACKUP_STORAGE is {settings.backup_storage!r}; the off-site backup needs 's3'"
        )
    required = {
        "BACKUP_S3_ENDPOINT": settings.backup_s3_endpoint,
        "BACKUP_S3_BUCKET": settings.backup_s3_bucket,
        "BACKUP_S3_REGION": settings.backup_s3_region,
        "BACKUP_S3_ACCESS_KEY_ID": settings.backup_s3_access_key_id,
        "BACKUP_S3_SECRET_ACCESS_KEY": settings.backup_s3_secret_access_key,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise BackupTargetError("off-site backup is switched on but missing " + ", ".join(missing))

    endpoint = settings.backup_s3_endpoint.strip().rstrip("/")
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.path or parts.query:
        raise BackupTargetError(
            "BACKUP_S3_ENDPOINT must be a bare https:// origin, such as "
            "https://<account_id>.eu.r2.cloudflarestorage.com"
        )
    return BackupTarget(
        endpoint=endpoint,
        bucket=settings.backup_s3_bucket.strip(),
        region=settings.backup_s3_region.strip(),
        access_key_id=settings.backup_s3_access_key_id.strip(),
        secret_access_key=settings.backup_s3_secret_access_key.strip(),
        prefix=settings.backup_s3_prefix,
    )


# ── Signature Version 4 ─────────────────────────────────────────────────────────


def _encode(value: str, *, keep_slash: bool) -> str:
    """RFC 3986 encoding, as SigV4 defines it: only ``A-Z a-z 0-9 - _ . ~`` pass through."""
    return quote(value, safe="-_.~/" if keep_slash else "-_.~")


def canonical_query(pairs: list[tuple[str, str]]) -> str:
    """The query string exactly as it is signed — and so exactly as it must be sent."""
    encoded = [
        (_encode(key, keep_slash=False), _encode(value, keep_slash=False)) for key, value in pairs
    ]
    return "&".join(f"{key}={value}" for key, value in sorted(encoded))


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def authorization_header(
    *,
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    payload_sha256: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    service: str,
    amz_date: str,
) -> str:
    """The ``Authorization`` value for one request, per AWS Signature Version 4.

    ``path`` is the already-encoded URI path and ``query`` the output of
    :func:`canonical_query`; ``headers`` are every header being signed, and must include
    ``host`` and ``x-amz-date``. S3 signs the path as sent, without the double encoding
    other AWS services apply.
    """
    signed = {name.lower(): " ".join(value.strip().split()) for name, value in headers.items()}
    names = sorted(signed)
    canonical_headers = "".join(f"{name}:{signed[name]}\n" for name in names)
    signed_headers = ";".join(names)
    canonical_request = "\n".join(
        [method, path or "/", query, canonical_headers, signed_headers, payload_sha256]
    )

    day = amz_date[:8]
    scope = f"{day}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    key = _hmac(("AWS4" + secret_access_key).encode(), day)
    for part in (region, service, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


# ── The store ───────────────────────────────────────────────────────────────────


def _error_code(response: httpx.Response) -> str:
    """The store's own error code (``AccessDenied``, ``NoSuchBucket``…), never the body."""
    match = re.search(r"<Code>([^<]{1,64})</Code>", response.text or "")
    return match.group(1) if match else "no error code"


class S3BackupStore:
    """Two calls against an S3-compatible bucket, path-style, signed with SigV4."""

    def __init__(
        self, target: BackupTarget, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._target = target
        self._transport = transport
        self._host = urlsplit(target.endpoint).netloc

    async def _request(
        self, method: str, key: str = "", *, query: str = "", body: bytes = b""
    ) -> httpx.Response:
        path = "/" + _encode(self._target.bucket, keep_slash=False)
        if key:
            path += "/" + _encode(key, keep_slash=True)
        payload_sha256 = hashlib.sha256(body).hexdigest()
        amz_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        headers = {
            "host": self._host,
            "x-amz-content-sha256": payload_sha256,
            "x-amz-date": amz_date,
        }
        headers["authorization"] = authorization_header(
            method=method,
            path=path,
            query=query,
            headers=headers,
            payload_sha256=payload_sha256,
            access_key_id=self._target.access_key_id,
            secret_access_key=self._target.secret_access_key,
            region=self._target.region,
            service=_SERVICE,
            amz_date=amz_date,
        )
        url = f"{self._target.endpoint}{path}" + (f"?{query}" if query else "")
        async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT_SECONDS) as client:
            return await client.request(method, url, headers=headers, content=body)

    async def check_reachable(self) -> None:
        """List at most one key under the prefix. Proves the endpoint answers, the bucket
        exists, the key is valid and the clock is close enough to sign — all before a byte of
        the database has been read."""
        query = canonical_query(
            [("list-type", "2"), ("max-keys", "1"), ("prefix", self._target.prefix)]
        )
        try:
            response = await self._request("GET", query=query)
        except httpx.HTTPError as exc:
            raise BackupTargetError(f"backup target unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise BackupTargetError(
                f"backup target refused a listing: HTTP {response.status_code} "
                f"({_error_code(response)})"
            )

    async def put(self, key: str, body: bytes) -> None:
        """Store one object. The declared SHA-256 makes the store reject a corrupted body."""
        try:
            response = await self._request("PUT", key, body=body)
        except httpx.HTTPError as exc:
            raise BackupTargetError(f"backup upload failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise BackupTargetError(
                f"backup upload refused: HTTP {response.status_code} ({_error_code(response)})"
            )
