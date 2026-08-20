"""Where a profile picture is kept — the port, the re-encoder, and the backends.

Batch 42 landed the *shape* of avatars deliberately without a backend, and recorded three
things that had to be true before one could be enabled. Batch 44 made them true:

* **Bytes are re-encoded, never passed through.** :func:`sniff_image_type` checks magic
  bytes, which proves the *header* is an image and nothing more — a valid PNG header can
  precede a payload that is not one. :func:`reencode_avatar` decodes the image with
  Pillow and writes a new file from the decoded pixels, so whatever was behind the header
  does not survive. Content-type and magic-byte checks remain a filter, not a defence;
  they are kept because they refuse the obvious cases before a decoder is handed
  anything.
* **The bucket's access rules are written explicitly.** See
  ``docs/runbooks/avatar-storage.md`` and ADR 0006. The bucket is public-read with an
  unguessable object key: a member's picture cannot be found from their player id, and
  ``avatar_url`` stays a plain stable URL that costs nothing to read. Migrations 003 and
  004 locked the Supabase *public schema* and Data API down; a bucket is a separate
  surface and this one is provisioned separately, by hand, from checked-in SQL.
* **Removal exists on both sides.** A member clears their own picture; a site admin takes
  another's down. Both shipped in Batch 42.

**Nothing here is on until it is configured.** ``AVATAR_STORAGE`` defaults to ``none``,
which selects :class:`UnconfiguredAvatarStorage` and answers 503, exactly as before. The
API advertises which of the two it is at ``GET /api/v1/config`` so the web app can mount
the upload control only where it works.
"""

from __future__ import annotations

import io
import secrets
from abc import ABC, abstractmethod

import httpx
import structlog
from PIL import Image, ImageOps, UnidentifiedImageError

from src.config import settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: What an avatar may be *sent* as. Kept narrow on purpose — every format here is one a
#: browser renders natively and Pillow re-encodes without surprises.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

#: What an avatar is *stored* as, whatever arrived. One output format means one decoder
#: path to reason about, and WebP is a fraction of the bytes of an equivalent PNG on a
#: surface phones re-fetch constantly.
STORED_MEDIA_TYPE = "image/webp"
STORED_EXTENSION = "webp"

#: Longest edge of a stored avatar. It is rendered at 40-96 CSS pixels; 512 leaves room
#: for a retina display and a future larger surface without storing a photograph.
MAX_DIMENSION = 512

#: Refuse before decoding above this many pixels. A 2 MB upload is bounded, but *decoded*
#: size is not — highly-compressed formats reach hundreds of megapixels from a few
#: kilobytes, and the memory is spent inside the decoder before any of our code runs
#: again. 50 MP is far above any real photograph a phone produces.
MAX_PIXELS = 50_000_000

#: Leading bytes that identify each allowed format. Checked because a client's declared
#: ``Content-Type`` is a claim, not evidence.
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

#: Formats the decoder will open. Pillow will happily identify a TIFF or an ICO from its
#: own header even when the caller declared a PNG; naming the three we accept keeps the
#: decoder on the paths the allowlist actually covers.
_DECODABLE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


class AvatarStorageError(RuntimeError):
    """Base for every way storing an avatar can fail."""


class AvatarStorageUnavailable(AvatarStorageError):
    """No object store is configured, so an avatar cannot be stored at all."""


class AvatarRejected(AvatarStorageError):
    """The bytes are not an image this application will re-encode and serve."""


def sniff_image_type(data: bytes) -> str | None:
    """The image type these bytes actually start with, or ``None``.

    A weak check by design, and documented as such at the module level: it proves the
    header, not the payload. WebP needs both halves of its container signature — ``RIFF``
    then ``WEBP`` — because ``RIFF`` alone is also WAV and AVI.
    """
    for prefix, media_type in _MAGIC_PREFIXES:
        if data.startswith(prefix):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def reencode_avatar(data: bytes) -> bytes:
    """Decode ``data`` and write a fresh WebP from its pixels.

    This is the step that makes serving a stranger's file defensible. The output is built
    from the decoded image, so anything riding *behind* a valid header — a script in a
    trailing chunk, a polyglot file that is also valid HTML — is simply not carried over.
    EXIF goes with it, which also drops the location a phone camera writes into a photo.

    Three refusals happen before the pixels are read, in order of what they cost:

    1. A format outside :data:`_DECODABLE_FORMATS`, taken from the file's own header
       rather than from what the caller declared.
    2. A pixel count above :data:`MAX_PIXELS`. ``Image.open`` parses the header only, so
       the dimensions are known while decoding is still cheap to refuse — which is the
       whole defence against a decompression bomb, since the *encoded* size cap says
       nothing about the decoded one.
    3. Anything Pillow cannot decode, which is the ordinary case of a truncated or
       fabricated file.

    Raises :class:`AvatarRejected` for all of them; the caller turns that into a 400.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in _DECODABLE_FORMATS:
                raise AvatarRejected(f"unsupported image format: {image.format}")

            width, height = image.size
            if width * height > MAX_PIXELS:
                raise AvatarRejected(f"image is too large to decode: {width}x{height}")

            # Rotate to how it was taken before the orientation tag is discarded, or a
            # phone photo is stored on its side.
            oriented = ImageOps.exif_transpose(image) or image
            # RGB, not RGBA: WebP carries alpha, but flattening here means one stored
            # shape and no transparent-background surprises against a dark theme.
            converted = oriented.convert("RGB")
            converted.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

            out = io.BytesIO()
            converted.save(out, format="WEBP", quality=82, method=4)
            return out.getvalue()
    except AvatarRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        # OSError covers Pillow's truncated-file errors; ValueError covers a decoder
        # rejecting its own header mid-parse.
        raise AvatarRejected("could not decode that image") from exc


class AvatarStorage(ABC):
    """Somewhere a profile picture can be put, fetched from, and removed."""

    #: Whether ``put`` can actually store anything. ``GET /api/v1/config`` reports this,
    #: and the web app mounts its upload control on it — a visible control that always
    #: fails is worse for a member than no control at all.
    enabled: bool = False

    @abstractmethod
    async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
        """Store ``data`` for one member and return the URL it is readable at.

        ``data`` is the re-encoded WebP, not what arrived: the router calls
        :func:`reencode_avatar` first, so an implementation is never handed bytes a
        stranger chose. ``media_type`` is what they *sent*, kept for the log line.
        """

    @abstractmethod
    async def delete(self, *, player_id: str) -> None:
        """Remove a member's stored picture. Must not fail when there is none."""


class UnconfiguredAvatarStorage(AvatarStorage):
    """The backend every environment gets until one is provisioned, and it refuses.

    Uploading returns a clear "not enabled" rather than a half-working path, and deleting
    succeeds so that clearing an avatar — which only has to null a column — keeps working
    whether or not a bucket is ever wired.
    """

    enabled = False

    async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
        raise AvatarStorageUnavailable("no avatar storage backend is configured")

    async def delete(self, *, player_id: str) -> None:
        return None


class SupabaseAvatarStorage(AvatarStorage):
    """Supabase Storage, reached over its REST API with the service-role key.

    The object key is ``{player_id}/{random}.webp``. The random half is the access
    control: the bucket is public-read, so anyone holding a URL can fetch it, but nobody
    can *derive* one from a player id — which they otherwise could, since player ids are
    on every league page. Replacing a picture writes a new random key and deletes the old
    objects, so a URL that leaked stops resolving the moment the member changes it.

    Uses ``httpx``, already a dependency for the odds and football providers, rather than
    the ``supabase`` SDK: three calls do not justify a client library, and the SDK brings
    its own transport with its own logging behaviour into a process that has been burned
    by exactly that (Batch 36).
    """

    enabled = True

    def __init__(
        self,
        *,
        base_url: str,
        service_key: str,
        bucket: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = service_key
        self._bucket = bucket
        self._client = client

    # ── HTTP plumbing ──────────────────────────────────────────────────────────

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Auth on every call, as headers.

        Never as a query parameter, however convenient: odds-api.io takes its key that
        way and httpx logged the full request URL at INFO for months (Batch 36). A
        header cannot end up in a request line.
        """
        return {
            "Authorization": f"Bearer {self._key}",
            "apikey": self._key,
            **(extra or {}),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: object,
    ) -> httpx.Response:
        url = f"{self._base}/storage/v1{path}"
        merged = self._headers(headers)
        if self._client is not None:
            return await self._client.request(method, url, headers=merged, **kwargs)  # type: ignore[arg-type]
        async with httpx.AsyncClient(timeout=15.0) as client:
            return await client.request(method, url, headers=merged, **kwargs)  # type: ignore[arg-type]

    # ── The port ───────────────────────────────────────────────────────────────

    async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
        # Old objects go first. If the upload then fails the member is left with no
        # picture rather than a stale one still reachable at a URL they meant to replace.
        await self.delete(player_id=player_id)

        key = f"{player_id}/{secrets.token_urlsafe(16)}.{STORED_EXTENSION}"
        response = await self._request(
            "POST",
            f"/object/{self._bucket}/{key}",
            content=data,
            headers={
                "Content-Type": STORED_MEDIA_TYPE,
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )
        if response.status_code >= 400:
            log.warning(
                "avatar upload failed",
                status=response.status_code,
                bucket=self._bucket,
                player_id=player_id,
            )
            raise AvatarStorageError(f"storage refused the upload ({response.status_code})")

        # Immutable and long-cached is safe precisely because the key is random: a new
        # picture is a new URL, so nothing has to be invalidated.
        return f"{self._base}/storage/v1/object/public/{self._bucket}/{key}"

    async def delete(self, *, player_id: str) -> None:
        keys = await self._existing_keys(player_id)
        if not keys:
            return
        response = await self._request("DELETE", f"/object/{self._bucket}", json={"prefixes": keys})
        if response.status_code >= 400:
            # Deliberately not raised. Clearing an avatar must succeed for the member —
            # the column is nulled either way — and an object left behind is unreachable
            # once nothing points at it. It is logged so it is not silent.
            log.warning(
                "avatar delete failed",
                status=response.status_code,
                bucket=self._bucket,
                player_id=player_id,
            )

    async def _existing_keys(self, player_id: str) -> list[str]:
        """Object keys already stored for this member. Empty on any failure."""
        response = await self._request(
            "POST",
            f"/object/list/{self._bucket}",
            json={"prefix": f"{player_id}/", "limit": 100},
        )
        if response.status_code >= 400:
            log.warning("avatar list failed", status=response.status_code, player_id=player_id)
            return []
        try:
            entries = response.json()
        except ValueError:
            return []
        return [
            f"{player_id}/{entry['name']}"
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        ]


def avatar_storage() -> AvatarStorage:
    """The configured backend. FastAPI dependency, so a test can override it.

    Fails closed twice over: an unknown ``AVATAR_STORAGE`` value and a ``supabase``
    selection with a missing URL or key both fall back to the refusing backend rather
    than raising at request time. A misconfigured deployment answers "not enabled yet",
    which is true, instead of 500ing on every upload.
    """
    if settings.avatar_storage != "supabase":
        return UnconfiguredAvatarStorage()
    if not settings.supabase_url or not settings.supabase_service_key:
        log.warning("AVATAR_STORAGE=supabase but SUPABASE_URL/SUPABASE_SERVICE_KEY is unset")
        return UnconfiguredAvatarStorage()
    return SupabaseAvatarStorage(
        base_url=settings.supabase_url,
        service_key=settings.supabase_service_key,
        bucket=settings.avatar_bucket,
    )
