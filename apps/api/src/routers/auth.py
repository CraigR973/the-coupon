"""Auth endpoints: login, refresh, logout, me, pin change, pin reset."""

import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import bcrypt as _bcrypt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import (
    LOCKOUT_DURATION,
    MAX_FAILED_ATTEMPTS,
    REFRESH_TTL,
    AdminUser,
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_pin,
    hash_token,
    verify_pin,
)
from src.config import settings
from src.database import get_db
from src.models.profile import OddsFormat, Profile
from src.models.refresh_token import RefreshToken
from src.rate_limit import limiter, login_key, per_user_key, refresh_token_key
from src.services.avatar_storage import (
    ALLOWED_IMAGE_TYPES,
    AvatarStorage,
    AvatarStorageUnavailable,
    avatar_storage,
    sniff_image_type,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Pre-computed dummy hash for constant-time login response when user not found.
_DUMMY_HASH: str = _bcrypt.hashpw(b"dummy-timing-guard", _bcrypt.gensalt()).decode()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    display_name: str
    pin: str = Field(pattern=r"^\d{4}$")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    player: "PlayerInfo"


class PlayerInfo(BaseModel):
    id: str
    display_name: str
    role: str
    timezone: str
    odds_format: str
    # Where this member's picture lives, or ``null`` for the initials fallback (Batch 42).
    avatar_url: str | None = None


def _player_info(user: Profile) -> PlayerInfo:
    """One place the shape is built, so the four endpoints returning it cannot drift."""
    return PlayerInfo(
        id=str(user.id),
        display_name=user.display_name,
        role=user.role.value,
        timezone=user.timezone,
        odds_format=user.odds_format.value,
        avatar_url=user.avatar_url,
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePinRequest(BaseModel):
    current_pin: str = Field(pattern=r"^\d{4}$")
    new_pin: str = Field(pattern=r"^\d{4}$")


class PinResetRequestBody(BaseModel):
    display_name: str


_PIN_RESET_GENERIC = {
    "message": "If that display name is registered, an admin will be notified to reset your PIN."
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _issue_token_pair(
    user: Profile,
    db: AsyncSession,
    device_hint: str | None = None,
) -> tuple[str, str]:
    """Create a new refresh token record and return (access_token, refresh_token)."""
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)

    token_record = RefreshToken(
        id=record_id,
        user_id=user.id,
        token_hash=hash_token(refresh_jwt),
        device_hint=device_hint,
        expires_at=_now() + REFRESH_TTL,
    )
    db.add(token_record)
    await db.commit()

    access = create_access_token(user.id, user.role)
    return access, refresh_jwt


# ---------------------------------------------------------------------------
# Endpoints — login / refresh / logout
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/15 minutes", key_func=login_key)
async def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(
        select(Profile).where(
            Profile.display_name == body.display_name,
            Profile.deleted_at.is_(None),
        )
    )

    user = result.scalar_one_or_none()

    if user is None:
        verify_pin(body.pin, _DUMMY_HASH)
        log.info("login failed — user not found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    now = _now()
    if not user.is_active:
        verify_pin(body.pin, user.pin_hash)
        log.info("login failed — inactive profile", user_id=str(user.id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.locked_until is not None and user.locked_until > now:
        verify_pin(body.pin, user.pin_hash)
        log.info("login failed — profile locked", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Too many failed attempts. Try again later.",
        )

    if not verify_pin(body.pin, user.pin_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + LOCKOUT_DURATION
        await db.commit()
        log.info("login failed — wrong pin", user_id=str(user.id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.failed_login_count or user.locked_until is not None:
        user.failed_login_count = 0
        user.locked_until = None
    await db.commit()
    await db.refresh(user)

    device_hint = request.headers.get("User-Agent", "")[:100]
    access, refresh = await _issue_token_pair(user, db, device_hint)

    log.info(
        "login successful",
        user_id=str(user.id),
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        player=_player_info(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("60/hour", key_func=refresh_token_key)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    payload = decode_refresh_token(body.refresh_token)
    jti = uuid.UUID(payload["jti"])
    user_id = uuid.UUID(payload["sub"])

    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.id == jti,
            RefreshToken.user_id == user_id,
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()
    if token_record is None or token_record.expires_at < _now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    token_record.revoked_at = _now()
    await db.commit()

    user_result = await db.execute(
        select(Profile).where(Profile.id == user_id, Profile.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    device_hint = token_record.device_hint
    access, new_refresh = await _issue_token_pair(user, db, device_hint)

    log.info("tokens refreshed", user_id=str(user_id))
    return AccessTokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        payload = decode_refresh_token(body.refresh_token)
        jti = uuid.UUID(payload["jti"])
        token_hash = hash_token(body.refresh_token)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.id == jti,
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        )
        token_record = result.scalar_one_or_none()
        if token_record:
            token_record.revoked_at = _now()
            await db.commit()
            log.info("logout — token revoked", jti=str(jti))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Endpoints — me, pin change, pin reset
# ---------------------------------------------------------------------------


@router.get("/me", response_model=PlayerInfo)
async def me(user: CurrentUser) -> PlayerInfo:
    return _player_info(user)


class ProfileUpdateRequest(BaseModel):
    """Both fields are optional so a client can change one without resending the other.

    ``timezone`` was required until Batch 9 added ``odds_format`` alongside it;
    callers that still send only a timezone are unaffected.
    """

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    odds_format: OddsFormat | None = None


@router.patch("/me", response_model=PlayerInfo)
async def update_profile(
    body: ProfileUpdateRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PlayerInfo:
    """Update the authenticated user's mutable profile fields."""
    values: dict[str, object] = {}
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid IANA timezone identifier",
            )
        values["timezone"] = body.timezone
    if body.odds_format is not None:
        values["odds_format"] = body.odds_format

    if values:
        await db.execute(update(Profile).where(Profile.id == user.id).values(**values))
        await db.commit()

    # Built from `body` rather than through `_player_info`, because the bulk `update()`
    # above does not refresh the in-memory `user` — reading it back would report the
    # pre-update values. `avatar_url` is untouched here, so it comes off `user`.
    return PlayerInfo(
        id=str(user.id),
        display_name=user.display_name,
        role=user.role.value,
        timezone=body.timezone if body.timezone is not None else user.timezone,
        odds_format=(body.odds_format or user.odds_format).value,
        avatar_url=user.avatar_url,
    )


@router.put("/me/pin", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/hour", key_func=per_user_key)
async def change_pin(
    request: Request,
    body: ChangePinRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    if not verify_pin(body.current_pin, user.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current PIN is incorrect"
        )
    user.pin_hash = hash_pin(body.new_pin)
    await db.commit()
    log.info("pin changed", user_id=str(user.id))


@router.post("/pin/reset-request")
@limiter.limit("3/hour")
async def pin_reset_request(
    request: Request,
    body: PinResetRequestBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    result = await db.execute(
        select(Profile).where(
            Profile.display_name == body.display_name,
            Profile.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        return _PIN_RESET_GENERIC

    log.info("pin reset requested — admin handoff required", user_id=str(user.id))
    return _PIN_RESET_GENERIC


# ---------------------------------------------------------------------------
# Endpoints — profile picture (Batch 42)
# ---------------------------------------------------------------------------


async def _read_capped(request: Request, cap: int) -> bytes:
    """The request body, refused as soon as it passes ``cap`` rather than after.

    Streamed rather than ``await request.body()`` so an oversized upload is rejected
    while it arrives instead of being buffered whole first — the cap is there to bound
    what the process holds, and reading everything before checking would defeat it.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            raise HTTPException(
                # `HTTP_413_REQUEST_ENTITY_TOO_LARGE`, not the newer
                # `HTTP_413_CONTENT_TOO_LARGE`: the pinned starlette==0.37.2 has only the
                # old name, and the shared dev venv's newer starlette has both and warns
                # about the old one. Following that warning turns a warning locally into
                # an AttributeError on the pins — which is what CI and production run.
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Avatar must be under {cap // 1024} KB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/me/avatar", response_model=PlayerInfo)
@limiter.limit("6/hour", key_func=per_user_key)
async def upload_avatar(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[AvatarStorage, Depends(avatar_storage)],
) -> PlayerInfo:
    """Replace the caller's profile picture.

    The path the frontend called for a year before anything answered it — see
    ``docs/LAUNCH_PLAN.md``. It answers now, and in every environment it answers 503:
    no object store is configured, so there is nowhere to put the bytes. Failing closed
    is the point rather than an omission; ``src/services/avatar_storage.py`` records what
    has to be true before a backend may be enabled, and re-encoding is the item that is
    not done.

    The image is the **raw request body**, typed by ``Content-Type`` — not a multipart
    form. One file needs no envelope, multipart would add ``python-multipart`` as a
    dependency for nothing, and this way the declared type arrives on the header the
    validation already has to read. ``fetch(url, {method: 'POST', body: file})`` sends
    exactly this shape.

    Validation runs *before* the refusal so it is exercised and tested rather than
    written and forgotten: a size cap, a content-type allowlist, and a magic-byte check
    that the bytes begin as the type they claim.
    """
    declared = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Avatar must be one of: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
        )

    data = await _read_capped(request, settings.avatar_max_bytes)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar is empty")

    sniffed = sniff_image_type(data)
    if sniffed is None or sniffed != declared:
        # A declared content-type is a claim; the leading bytes are evidence, and a
        # mismatch between them is the shape of someone trying it on.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar content does not match its declared type",
        )

    try:
        url = await storage.put(player_id=str(user.id), data=data, media_type=declared)
    except AvatarStorageUnavailable:
        log.info("avatar upload refused — no storage backend", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile pictures are not enabled yet",
        ) from None

    user.avatar_url = url
    await db.commit()
    log.info("avatar set", user_id=str(user.id))
    return _player_info(user)


@router.delete("/me/avatar", response_model=PlayerInfo)
async def clear_avatar(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[AvatarStorage, Depends(avatar_storage)],
) -> PlayerInfo:
    """Remove the caller's own profile picture.

    Works whether or not a backend is configured: clearing is a null on a column, and
    ``UnconfiguredAvatarStorage.delete`` is a no-op. A member must always be able to take
    their own picture down, including in the window where uploading is disabled.
    """
    await storage.delete(player_id=str(user.id))
    user.avatar_url = None
    await db.commit()
    log.info("avatar cleared", user_id=str(user.id))
    return _player_info(user)


@router.delete("/players/{player_id}/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def remove_player_avatar(
    player_id: uuid.UUID,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[AvatarStorage, Depends(avatar_storage)],
) -> None:
    """Take down another member's picture — moderation, not self-service.

    A **site** admin rather than a league admin, deliberately. An avatar is a profile
    field, not a membership one: it follows the member into every league they play in, so
    removing it reaches beyond any one league's admin remit. A league admin who wants a
    picture gone asks a site admin, which is the same escalation the product already uses
    for a PIN reset.

    Idempotent — clearing a member who has no picture is a success, so a moderator acting
    on a stale report is not told they failed.
    """
    result = await db.execute(
        select(Profile).where(Profile.id == player_id, Profile.deleted_at.is_(None))
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")

    await storage.delete(player_id=str(target.id))
    target.avatar_url = None
    await db.commit()
    log.info("avatar removed by admin", user_id=str(target.id), admin_id=str(admin.id))
