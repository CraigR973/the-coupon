"""Where a profile picture is kept — the port, and the refusal that stands in for it.

Batch 42 landed the *shape* of avatars deliberately without a backend. There is no
bucket in any environment, so :class:`UnconfiguredAvatarStorage` is what every caller
gets, and the upload endpoint fails closed rather than half-working. That is the point:
an avatar is a user-supplied image shown to every member of a league, and the decisions
it needs — which store, what access rules, how images are re-encoded, who can remove
one — are worth making deliberately rather than inheriting from whichever backend was
wired first.

**Before enabling any implementation of this port, three things must be true**, and none
of them is done:

* **Bytes are re-encoded, never passed through.** :func:`sniff_image_type` below checks
  magic bytes, which proves the *header* is an image and nothing more — a valid PNG
  header can precede a payload that is not one. Re-encoding through an imaging library
  is what actually neutralises a hostile file, and no imaging library is a dependency of
  this project yet. Content-type and magic-byte checks are a filter, not a defence.
* **The bucket's access rules are written explicitly.** Migrations 003 and 004 locked the
  Supabase public schema and Data API down on purpose. A storage bucket is a separate
  surface with separate policies, and adding one must not quietly reopen what those
  closed.
* **Removal exists on both sides.** A member can clear their own picture; an admin can
  remove one that should not be there. Moderation is not a later feature for an image
  every member of a league can see.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

#: What an avatar may be. Kept narrow on purpose — every format here is one a browser
#: renders natively and an imaging library can re-encode without surprises.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

#: Leading bytes that identify each allowed format. Checked because a client's declared
#: ``Content-Type`` is a claim, not evidence.
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


class AvatarStorageError(RuntimeError):
    """Base for every way storing an avatar can fail."""


class AvatarStorageUnavailable(AvatarStorageError):
    """No object store is configured, so an avatar cannot be stored at all."""


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


class AvatarStorage(ABC):
    """Somewhere a profile picture can be put, fetched from, and removed."""

    @abstractmethod
    async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
        """Store ``data`` for one member and return the URL it is readable at.

        Implementations must re-encode ``data`` rather than writing it through. See the
        module docstring: the caller has checked a magic-byte prefix, which is not the
        same as knowing the file is safe to serve.
        """

    @abstractmethod
    async def delete(self, *, player_id: str) -> None:
        """Remove a member's stored picture. Must not fail when there is none."""


class UnconfiguredAvatarStorage(AvatarStorage):
    """The only implementation that exists, and it refuses.

    Every environment gets this one. Uploading returns a clear "not enabled" rather than
    a half-working path, and deleting succeeds so that clearing an avatar — which only
    has to null a column — keeps working whether or not a bucket is ever wired.
    """

    async def put(self, *, player_id: str, data: bytes, media_type: str) -> str:
        raise AvatarStorageUnavailable("no avatar storage backend is configured")

    async def delete(self, *, player_id: str) -> None:
        return None


def avatar_storage() -> AvatarStorage:
    """The configured backend. FastAPI dependency, so a test can override it."""
    return UnconfiguredAvatarStorage()
