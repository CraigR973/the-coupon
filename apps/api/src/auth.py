"""JWT creation/verification, bcrypt helpers, and FastAPI auth dependencies."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.profile import Profile, UserRole

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=True)

ACCESS_TTL = timedelta(hours=24)
REFRESH_TTL = timedelta(days=30)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

#: Four-digit PINs common enough that permitting them shrinks the keyspace to nothing.
#:
#: Published analyses of leaked four-digit PINs put roughly a quarter of all human choices
#: in about twenty values — `1234` alone is close to a tenth. Against that distribution a
#: nominal 10,000-value space behaves like a few dozen, and the durable five-attempt
#: lockout is doing all the work.
#:
#: Kept deliberately short. A long blocklist starts refusing PINs people chose for real
#: reasons and pushes them toward writing it down, which is a worse outcome than a weak
#: PIN behind a lockout. This is the head of the distribution and nothing else: the
#: obvious repeats, the obvious runs, and the handful of famous ones.
WEAK_PINS = frozenset(
    {
        "0000",
        "1111",
        "2222",
        "3333",
        "4444",
        "5555",
        "6666",
        "7777",
        "8888",
        "9999",
        "1234",
        "2345",
        "3456",
        "4567",
        "5678",
        "6789",
        "0123",
        "4321",
        "5432",
        "6543",
        "7654",
        "8765",
        "9876",
        "3210",
        "1212",
        "2121",
        "1122",
        "1313",
        "1010",
        "2020",
        "6969",
        "1004",
        "2000",
        "2001",
    }
)


def is_weak_pin(pin: str) -> bool:
    """True when a PIN is common enough that it is effectively no PIN at all."""
    return pin in WEAK_PINS


# ---------------------------------------------------------------------------
# Bcrypt helpers
# ---------------------------------------------------------------------------


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    return bcrypt.checkpw(pin.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_access_token(user_id: uuid.UUID, role: UserRole) -> str:
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": _now() + ACCESS_TTL,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.jwt_access_secret, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID, token_record_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "jti": str(token_record_id),
        "exp": _now() + REFRESH_TTL,
        "iat": _now(),
    }
    return jwt.encode(payload, settings.jwt_refresh_secret, algorithm="HS256")


def hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of a raw token string — stored in refresh_tokens.token_hash."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_opaque_token() -> str:
    """32-byte URL-safe random token (used as the raw refresh token)."""
    return secrets.token_urlsafe(32)


_JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1


def generate_join_code() -> str:
    """6-character human-typable league join code (unambiguous alphabet)."""
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(6))


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_access_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_refresh_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Profile:
    token = credentials.credentials

    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_access_secret, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(
        select(Profile).where(
            Profile.id == user_id,
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(
    user: Annotated[Profile, Depends(get_current_user)],
) -> Profile:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


CurrentUser = Annotated[Profile, Depends(get_current_user)]
AdminUser = Annotated[Profile, Depends(require_admin)]
