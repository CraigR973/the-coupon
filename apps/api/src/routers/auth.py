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
    is_weak_pin,
    verify_pin,
)
from src.config import settings
from src.database import get_db
from src.models.notification import ActionType, ActorType, AuditLog
from src.models.profile import OddsFormat, Profile, UserRole
from src.models.refresh_token import RefreshToken
from src.rate_limit import limiter, login_key, per_user_key, refresh_token_key
from src.services.avatar_storage import (
    ALLOWED_IMAGE_TYPES,
    AvatarRejected,
    AvatarStorage,
    AvatarStorageError,
    AvatarStorageUnavailable,
    avatar_storage,
    reencode_avatar,
    sniff_image_type,
)
from src.services.push_notification_service import send_notification

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


async def _revoke_all_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every live refresh token for one member. Returns how many were revoked.

    The caller's own session goes with the rest. There is no way to spare it — a member
    authenticates here with an *access* token, so the API never sees which refresh token
    belongs to this device, and guessing by ``device_hint`` would spare an attacker who
    copied the User-Agent. Losing the current session is the right trade anyway: the
    client clears its tokens on the next failed refresh and asks for the new PIN
    (``lib/api.ts`` already redirects to /login when a refresh 401s), which is exactly
    what should happen after a credential changes.
    """
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    return result.rowcount or 0


async def _notify_site_admins(
    db: AsyncSession,
    title: str,
    body: str,
    data: dict[str, str],
    tag: str,
) -> int:
    """Push one message to every active site admin. Returns how many were reached.

    Best-effort by design: a member's request must be recorded whether or not a push
    goes anywhere, so a failure here is logged and swallowed rather than raised. Push
    needs VAPID keys and an active subscription, and neither is guaranteed —
    ``send_notification`` already answers 0 when they are missing.
    """
    admins = (
        (
            await db.execute(
                select(Profile).where(
                    Profile.role == UserRole.admin,
                    Profile.deleted_at.is_(None),
                    Profile.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    reached = 0
    for admin in admins:
        try:
            reached += await send_notification(
                db,
                admin.id,
                title,
                body,
                data=dict(data),
                tag=tag,
                timezone_name=admin.timezone,
            )
        except Exception:  # noqa: BLE001 — one bad subscription must not lose the record
            log.warning("admin notification failed", admin_id=str(admin.id))
    return reached


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

    # A lockout that has expired gives the counter back, not one attempt.
    #
    # `failed_login_count` used to reset only on a *successful* login, so once it
    # reached MAX_FAILED_ATTEMPTS the expiry of `locked_until` bought exactly one guess:
    # a wrong answer took the count to six, which is still >= the maximum, and re-locked
    # for another window. Forever, at one attempt per fifteen minutes. That is punishing
    # to an attacker and fatal to a member who has simply forgotten four digits — and
    # until this batch the "forgot PIN" path notified nobody, so there was no way back.
    #
    # The window is what bounds brute force, and it is unchanged: five attempts per
    # fifteen minutes is 20/hour whatever this line does.
    if user.locked_until is not None:
        user.failed_login_count = 0
        user.locked_until = None

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
    if token_record is None:
        # Nothing live matched. Distinguish "never existed / already expired" from a
        # *replay* of a token this app issued and has since rotated away, because the
        # second is the signature of theft: rotation means a refresh token is used once,
        # so a second use is either the victim or the thief, and there is no way to tell
        # which. OAuth 2 Security BCP §4.13.2 says revoke the family; without lineage on
        # the rows, the family is every token this member holds.
        #
        # Both parties are logged out and have to sign in with the PIN — which the thief
        # does not have. Before this, the two simply raced and whoever refreshed second
        # was quietly signed out with nothing recorded anywhere.
        replayed = (
            await db.execute(
                select(RefreshToken).where(
                    RefreshToken.id == jti,
                    RefreshToken.user_id == user_id,
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.is_not(None),
                )
            )
        ).scalar_one_or_none()
        if replayed is not None:
            revoked = await _revoke_all_refresh_tokens(db, user_id)
            await db.commit()
            log.warning(
                "refresh token reuse detected — revoking every session for this member",
                user_id=str(user_id),
                jti=str(jti),
                sessions_revoked=revoked,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    if token_record.expires_at < _now():
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
    """Change the caller's PIN and end every session opened with the old one.

    A member changes their PIN when they think somebody else knows it. Writing the new
    hash and stopping there left every already-issued refresh token live for its full
    thirty days, renewing itself, so the session the member was trying to shut out
    outlived the credential it was opened with. Rotation that does not revoke is theatre.

    The caller's own session ends too — see :func:`_revoke_all_refresh_tokens`. The
    24-hour access token cannot be recalled (it is stateless by design), so the practical
    effect is that the old session keeps working until that token expires and is then
    refused at refresh. Shortening the access TTL is a separate decision; revoking what
    *can* be revoked is not.

    Lockout state is cleared with it. A member who mistyped their way into a lockout and
    then changed their PIN has proved they know the current one; leaving them locked out
    afterwards would be perverse.
    """
    if not verify_pin(body.current_pin, user.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current PIN is incorrect"
        )
    # Checked after the current PIN, so the endpoint cannot be used to probe the
    # blocklist without already holding the account.
    if is_weak_pin(body.new_pin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That PIN is too common — choose one that is not a run or a repeat.",
        )
    user.pin_hash = hash_pin(body.new_pin)
    revoked = await _revoke_all_refresh_tokens(db, user.id)
    user.failed_login_count = 0
    user.locked_until = None
    await db.commit()
    log.info("pin changed", user_id=str(user.id), sessions_revoked=revoked)


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

    # Until this batch the endpoint wrote one `log.info` and returned "an admin will be
    # notified" — which was not true. No row, no message, nothing an admin could act on;
    # the only trace was a Railway log line, and `railway logs` caps at 500. Since this
    # is the *only* account-recovery path a member has, the message being false meant a
    # forgotten PIN was a lost account.
    #
    # Two things now happen, because they answer different questions. The audit row is
    # the durable record — it survives, it is queryable, and it is where "who asked, and
    # when" lives. The push is what actually reaches a person; `audit_log` has no reader
    # anywhere in the app, so writing only there would have reproduced the same silence
    # in a new table.
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_type=ActorType.player,
            action_type=ActionType.player_pin_reset,
            target_table="profiles",
            target_id=user.id,
            # `player_pin_reset` covers both halves of the journey and this names which
            # half. A dedicated `pin_reset_requested` value would read better, and it is
            # deliberately not added: `ALTER TYPE ... ADD VALUE` cannot be undone, and
            # production has no restore point (owner's 2026-07-30 deferral). Not worth an
            # irreversible schema change for a nicer enum label.
            changes={"stage": "requested", "display_name": user.display_name},
        )
    )
    await db.commit()

    reached = await _notify_site_admins(
        db,
        title="PIN reset requested",
        body=f"{user.display_name} cannot sign in and has asked for a PIN reset.",
        data={"url": "/settings", "player_id": str(user.id)},
        tag=f"pin-reset-{user.id}",
    )

    log.info(
        "pin reset requested — admins notified",
        user_id=str(user.id),
        admins_reached=reached,
    )
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

    Answers 503 wherever ``AVATAR_STORAGE`` is unset, which is every environment until a
    bucket is provisioned (``docs/runbooks/avatar-storage.md``). Failing closed there is
    the point rather than an omission, and ``GET /api/v1/config`` says which it is so the
    web app does not offer a control that cannot work.

    The image is the **raw request body**, typed by ``Content-Type`` — not a multipart
    form. One file needs no envelope, multipart would add ``python-multipart`` as a
    dependency for nothing, and this way the declared type arrives on the header the
    validation already has to read. ``fetch(url, {method: 'POST', body: file})`` sends
    exactly this shape.

    Four gates, cheapest first: a content-type allowlist, a size cap enforced as the body
    arrives, a magic-byte check that the bytes begin as the type they claim, and then
    :func:`reencode_avatar`, which is the only one of the four that inspects the payload
    rather than the header. What reaches storage is a WebP this process wrote from
    decoded pixels — never the bytes that were uploaded.
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
        stored = reencode_avatar(data)
    except AvatarRejected:
        # The header said one thing and the payload was another, or was not decodable at
        # all. Same 400 as a magic-byte mismatch: from a member's side it is one message
        # about one file, and the difference is only interesting in the log.
        log.info("avatar rejected by the re-encoder", user_id=str(user.id), declared=declared)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file could not be read as an image",
        ) from None

    try:
        url = await storage.put(player_id=str(user.id), data=stored, media_type=declared)
    except AvatarStorageUnavailable:
        log.info("avatar upload refused — no storage backend", user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile pictures are not enabled yet",
        ) from None
    except AvatarStorageError:
        # A configured backend that would not take it — the member can try again, and
        # `storage.put` has already logged what the store said.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not store that picture — try again",
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
