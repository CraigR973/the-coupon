"""Tests for auth endpoints, activation, and FastAPI auth dependencies."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from limits import parse_many
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import (
    create_access_token,
    create_refresh_token,
    hash_pin,
    hash_token,
    require_admin,
    verify_pin,
)
from src.config import settings
from src.database import get_db
from src.main import app
from src.models.profile import OddsFormat, Profile, UserRole
from src.models.refresh_token import RefreshToken
from src.routers.auth import REGISTER_LIMIT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_user(
    role: UserRole = UserRole.player,
    failed: int = 0,
    locked_until: datetime | None = None,
    is_active: bool = True,
) -> Profile:
    p = MagicMock(spec=Profile)
    p.id = uuid.uuid4()
    p.display_name = "Test User"
    p.pin_hash = hash_pin("1234")
    p.role = role
    p.timezone = "UTC"
    p.odds_format = OddsFormat.decimal
    p.is_active = is_active
    p.failed_login_count = failed
    p.locked_until = locked_until
    p.deleted_at = None
    # Batch 42. A `MagicMock(spec=Profile)` yields a mock for any unset attribute, and
    # pydantic rejects that against `str | None` — so every response carrying PlayerInfo
    # fails unless this is a real value. `None` is the state of nearly every profile.
    p.avatar_url = None
    return p


def _make_refresh_record(user_id: uuid.UUID, refresh_jwt: str) -> MagicMock:
    r = MagicMock(spec=RefreshToken)
    r.id = uuid.uuid4()
    r.user_id = user_id
    r.token_hash = hash_token(refresh_jwt)
    r.device_hint = "TestAgent"
    r.expires_at = _now() + timedelta(days=30)
    r.revoked_at = None
    return r


def _stub_db(execute_results: list) -> AsyncMock:
    """Build a mock AsyncSession with sequential execute() return values."""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()
    return mock_db


def _scalar(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


@asynccontextmanager
async def _override_db(mock_db: AsyncMock) -> AsyncGenerator[None, None]:
    """Temporarily override the get_db dependency."""

    async def _fake_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _fake_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Unit tests — bcrypt / JWT helpers
# ---------------------------------------------------------------------------


def test_hash_and_verify_pin() -> None:
    h = hash_pin("9876")
    assert verify_pin("9876", h)
    assert not verify_pin("0000", h)


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, UserRole.admin)
    payload = pyjwt.decode(token, settings.jwt_access_secret, algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"


def test_refresh_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    record_id = uuid.uuid4()
    token = create_refresh_token(user_id, record_id)
    payload = pyjwt.decode(token, settings.jwt_refresh_secret, algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["jti"] == str(record_id)


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------


async def test_login_success(client: AsyncClient) -> None:
    user = _make_user(role=UserRole.admin)
    mock_db = _stub_db([_scalar(user), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["player"]["role"] == "admin"
    assert data["player"]["display_name"] == "Test User"
    assert "email" not in data["player"]
    # `avatar_url` was asserted *absent* until Batch 42, when the field arrived. It is
    # present and null for a member who has set no picture, which is nearly all of them.
    assert data["player"]["avatar_url"] is None


async def test_login_wrong_pin(client: AsyncClient) -> None:
    user = _make_user()
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "0000"},
        )

    assert resp.status_code == 401


async def test_login_user_not_found(client: AsyncClient) -> None:
    mock_db = _stub_db([_scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "nobody", "pin": "1234"},
        )

    assert resp.status_code == 401


async def test_login_wrong_pin_returns_401(client: AsyncClient) -> None:
    """Wrong PIN always returns 401."""
    user = _make_user(failed=99)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_wrong_pin_updates_durable_counter(client: AsyncClient) -> None:
    user = _make_user(failed=1)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert user.failed_login_count == 2
    mock_db.commit.assert_awaited_once()


async def test_login_locks_profile_after_threshold(client: AsyncClient) -> None:
    user = _make_user(failed=4)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    assert user.failed_login_count == 5
    assert user.locked_until is not None


async def test_login_rejects_locked_profile(client: AsyncClient) -> None:
    user = _make_user(locked_until=_now() + timedelta(minutes=5))
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 423
    assert resp.json()["detail"] == "Too many failed attempts. Try again later."


async def test_login_rejects_inactive_profile(client: AsyncClient) -> None:
    user = _make_user(is_active=False)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 401


async def test_login_success_resets_durable_lockout(client: AsyncClient) -> None:
    user = _make_user(failed=2, locked_until=_now() - timedelta(minutes=1))
    mock_db = _stub_db([_scalar(user), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 200
    assert user.failed_login_count == 0
    assert user.locked_until is None


# ---------------------------------------------------------------------------
# Refresh endpoint
# ---------------------------------------------------------------------------


async def test_refresh_success(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)
    token_record = _make_refresh_record(user.id, refresh_jwt)
    token_record.id = record_id

    mock_db = _stub_db([_scalar(token_record), _scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] != refresh_jwt  # rotation happened
    assert token_record.revoked_at is not None


async def test_refresh_invalid_token(client: AsyncClient) -> None:
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.jwt"},
        )

    assert resp.status_code == 401


async def test_refresh_revoked_token(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)

    # Two lookups since Batch 58: no live row, then "was this one of ours, already
    # rotated away?" — which distinguishes an unknown token from a replay.
    mock_db = _stub_db([_scalar(None), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout endpoint
# ---------------------------------------------------------------------------


async def test_logout_success(client: AsyncClient) -> None:
    user = _make_user()
    record_id = uuid.uuid4()
    refresh_jwt = create_refresh_token(user.id, record_id)
    token_record = _make_refresh_record(user.id, refresh_jwt)

    mock_db = _stub_db([_scalar(token_record)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_jwt},
        )

    assert resp.status_code == 204
    assert token_record.revoked_at is not None


async def test_logout_bad_token_still_204(client: AsyncClient) -> None:
    """Logout must always return 204 — even with a garbage token."""
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "garbage"},
        )

    assert resp.status_code == 204


async def test_activate_route_removed(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/activate", json={"code": "unknown-code"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Registration endpoint (public self-serve signup, owner's 2026-08-22 decision)
# ---------------------------------------------------------------------------


def _register_db(existing_name: object = None) -> AsyncMock:
    """A session whose one SELECT answers the display-name uniqueness probe."""
    db = _stub_db([_scalar(existing_name)])
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _added_profiles(db: AsyncMock) -> list[Profile]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Profile)]


async def test_register_creates_an_account_and_signs_it_in(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "New Member", "pin": "3719"}
        )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["player"]["display_name"] == "New Member"
    # A stranger signing themselves up must never land as a site admin — that role reaches
    # every league and can take down any member's avatar or be paged for a PIN reset.
    assert payload["player"]["role"] == "player"


async def test_register_stores_the_pin_hashed(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        await client.post("/api/v1/auth/register", json={"display_name": "Hashed", "pin": "3719"})

    (profile,) = _added_profiles(db)
    assert profile.pin_hash != "3719"
    assert verify_pin("3719", profile.pin_hash)


async def test_register_stores_the_name_with_whitespace_collapsed(client: AsyncClient) -> None:
    """What is checked for uniqueness has to be what is stored, or the check means nothing."""
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "  Sam   Smith  ", "pin": "3719"}
        )

    assert resp.status_code == 201
    assert resp.json()["player"]["display_name"] == "Sam Smith"
    assert [p.display_name for p in _added_profiles(db)] == ["Sam Smith"]


async def test_register_refuses_a_taken_name(client: AsyncClient) -> None:
    db = _register_db(existing_name=uuid.uuid4())
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Taken", "pin": "3719"}
        )

    assert resp.status_code == 409
    assert "taken" in resp.json()["detail"].lower()
    db.flush.assert_not_awaited()


async def test_register_compares_names_case_insensitively(client: AsyncClient) -> None:
    """`uq_profiles_display_name` is case-sensitive; a leaderboard reader is not.

    "Dave" and "dave" would both be valid logins and one person twice in the standings,
    which is exactly the impersonation an open signup invites. The endpoint compares
    lowered, so the query it issues must be the lowered one.
    """
    db = _register_db(existing_name=uuid.uuid4())
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "DAVE", "pin": "3719"}
        )

    assert resp.status_code == 409
    rendered = str(db.execute.call_args_list[0].args[0]).lower()
    assert "lower(" in rendered


async def test_register_does_not_filter_out_soft_deleted_names(client: AsyncClient) -> None:
    """`deleted_at` does not release a name.

    Login filters deleted profiles out, so the row cannot be signed into — but the unique
    constraint still holds the string, and letting a stranger register the display name of
    a departed member would hand them that person's identity in every league's history.
    """
    db = _register_db(existing_name=uuid.uuid4())
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Departed", "pin": "3719"}
        )

    assert resp.status_code == 409
    assert "deleted_at" not in str(db.execute.call_args_list[0].args[0])


async def test_register_survives_losing_the_uniqueness_race(client: AsyncClient) -> None:
    """Two registrations for one name in the same instant: the loser gets 409, not 500."""
    db = _register_db()
    db.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("duplicate key")))
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Racer", "pin": "3719"}
        )

    assert resp.status_code == 409
    db.rollback.assert_awaited()


async def test_register_refuses_a_weak_pin(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Weak PIN", "pin": "1234"}
        )

    assert resp.status_code == 422
    assert "too common" in resp.json()["detail"]
    db.flush.assert_not_awaited()


@pytest.mark.parametrize("pin", ["123", "12345", "abcd", "", "12a4"])
async def test_register_refuses_a_pin_that_is_not_four_digits(
    client: AsyncClient, pin: str
) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Someone", "pin": pin}
        )

    assert resp.status_code == 422


@pytest.mark.parametrize("name", ["A", "x" * 33, "   ", ""])
async def test_register_refuses_a_name_outside_the_length_bounds(
    client: AsyncClient, name: str
) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": name, "pin": "3719"}
        )

    assert resp.status_code == 422
    db.flush.assert_not_awaited()


async def test_register_measures_length_after_collapsing(client: AsyncClient) -> None:
    """The control for the bounds above: padding is trimmed, not counted against you."""
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "  Jo  ", "pin": "3719"}
        )

    assert resp.status_code == 201
    assert resp.json()["player"]["display_name"] == "Jo"


@pytest.mark.parametrize(
    "name",
    [
        "Alice \U0001f389",  # emoji — unreproducible at the sign-in form on most keyboards
        "-Dave",  # opens with punctuation
        "_admin",  # opens with punctuation, and reads as UI chrome
        ".hidden",  # ditto
        "Bob\x07",  # control character
        "Rob<script>",  # angle brackets
        "Zoe​Anna",  # zero-width space — two visually identical names otherwise
    ],
)
async def test_register_refuses_a_name_the_login_form_cannot_reproduce(
    client: AsyncClient, name: str
) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": name, "pin": "3719"}
        )

    assert resp.status_code == 422


async def test_register_folds_exotic_whitespace_into_plain_spaces(client: AsyncClient) -> None:
    """A tab is whitespace to `str.split()`, so it normalises rather than being refused.

    Worth pinning because the neighbouring rejection list makes the opposite look likely:
    the character class refuses anything it cannot render, but normalisation runs *first*,
    and a name pasted out of a spreadsheet should register as the name it looks like. The
    zero-width space in that list is the contrast — `str.split()` does not treat U+200B as
    whitespace, so it survives normalisation and is then correctly refused, which is what
    stops two visually identical names existing.
    """
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Sarah\tJones", "pin": "3719"}
        )

    assert resp.status_code == 201
    assert resp.json()["player"]["display_name"] == "Sarah Jones"


async def test_register_accepts_the_punctuation_real_names_contain(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "O'Neill-Smith Jr.", "pin": "3719"}
        )

    assert resp.status_code == 201


async def test_register_keeps_the_browsers_timezone(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"display_name": "Zoned", "pin": "3719", "timezone": "Europe/London"},
        )

    assert resp.status_code == 201
    assert resp.json()["player"]["timezone"] == "Europe/London"


async def test_register_refuses_an_unknown_timezone(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"display_name": "Nowhere", "pin": "3719", "timezone": "Mars/Olympus"},
        )

    assert resp.status_code == 422


async def test_register_defaults_to_utc_without_a_timezone(client: AsyncClient) -> None:
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Unzoned", "pin": "3719"}
        )

    assert resp.status_code == 201
    assert resp.json()["player"]["timezone"] == "UTC"


async def test_register_is_refused_when_public_signup_is_disabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kill switch. Closing signup must not need a deploy, and must not touch the DB."""
    monkeypatch.setattr(settings, "public_signup_enabled", False)
    db = _register_db()
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/register", json={"display_name": "Too Late", "pin": "3719"}
        )

    assert resp.status_code == 403
    assert "closed" in resp.json()["detail"].lower()
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()


async def test_disabling_public_signup_does_not_disturb_login(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch closes the door for new members only — it must never lock out existing ones."""
    monkeypatch.setattr(settings, "public_signup_enabled", False)
    user = _make_user()
    db = _stub_db([_scalar(user), _scalar(None)])
    async with _override_db(db):
        resp = await client.post(
            "/api/v1/auth/login", json={"display_name": "Test User", "pin": "1234"}
        )

    assert resp.status_code == 200


def test_register_rate_limit_is_tight_enough_to_bound_name_squatting() -> None:
    """Asserted rather than left in a decorator string, as `PICK_SUBMIT_LIMIT` was (Batch 57).

    This is the only control between a public write endpoint with no email verification
    and a script minting accounts to squat display names — which are globally unique and
    are the login identifier. Five an hour per address still lets a household sign up
    together; loosening it is a decision, not a tidy-up.
    """
    limit = parse_many(REGISTER_LIMIT)[0]
    assert limit.amount <= 5
    assert limit.GRANULARITY.seconds >= 3600


# ---------------------------------------------------------------------------
# Auth dependency — require_admin
# ---------------------------------------------------------------------------


async def test_require_admin_rejects_player_role() -> None:
    """require_admin raises 403 for a player-role token."""
    user = _make_user(role=UserRole.player)

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403


async def test_require_admin_passes_admin_role() -> None:
    """require_admin returns the user when role is admin."""
    user = _make_user(role=UserRole.admin)
    result = await require_admin(user)
    assert result is user


async def test_me_profile_rejects_device_token(client: AsyncClient) -> None:
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.get(
            "/api/v1/me/profile",
            headers={"Authorization": "Bearer raw-device-token"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


async def test_me_profile_rejects_expired_jwt_without_device_fallback(client: AsyncClient) -> None:
    user = _make_user(role=UserRole.admin)
    expired_jwt = pyjwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "exp": _now() - timedelta(minutes=1),
            "iat": _now() - timedelta(hours=1),
        },
        settings.jwt_access_secret,
        algorithm="HS256",
    )
    mock_db = _stub_db([])

    async with _override_db(mock_db):
        resp = await client.get(
            "/api/v1/me/profile",
            headers={"Authorization": f"Bearer {expired_jwt}"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token expired"


# ---------------------------------------------------------------------------
# Batch 9 — the odds display preference on PATCH /auth/me
# ---------------------------------------------------------------------------


async def test_patch_me_sets_odds_format_without_a_timezone(client: AsyncClient) -> None:
    """``timezone`` became optional in Batch 9 so one field can change alone."""
    user = _make_user()
    mock_db = _stub_db([_scalar(user), MagicMock()])
    token = create_access_token(user.id, user.role)

    async with _override_db(mock_db):
        resp = await client.patch(
            "/api/v1/auth/me",
            json={"odds_format": "fractional"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["odds_format"] == "fractional"
    # The untouched field comes back as it was, not as null.
    assert resp.json()["timezone"] == "UTC"


async def test_patch_me_still_accepts_a_timezone_alone(client: AsyncClient) -> None:
    user = _make_user()
    mock_db = _stub_db([_scalar(user), MagicMock()])
    token = create_access_token(user.id, user.role)

    async with _override_db(mock_db):
        resp = await client.patch(
            "/api/v1/auth/me",
            json={"timezone": "Europe/London"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["timezone"] == "Europe/London"
    assert resp.json()["odds_format"] == "decimal"


async def test_patch_me_rejects_an_unknown_odds_format(client: AsyncClient) -> None:
    user = _make_user()
    mock_db = _stub_db([_scalar(user)])
    token = create_access_token(user.id, user.role)

    async with _override_db(mock_db):
        resp = await client.patch(
            "/api/v1/auth/me",
            json={"odds_format": "american"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Batch 56 — a PIN change ends the sessions opened with the old PIN
# ---------------------------------------------------------------------------


def _rowcount(n: int) -> MagicMock:
    """An `execute()` result for an UPDATE, which reports rows rather than scalars."""
    r = MagicMock()
    r.rowcount = n
    return r


async def test_changing_a_pin_revokes_every_refresh_token(client: AsyncClient) -> None:
    """The whole point: a stolen session must not outlive the credential it was opened with."""
    user = _make_user()
    token = create_access_token(user.id, user.role)
    # get_current_user resolves the profile, then revoke_all_refresh_tokens updates.
    mock_db = _stub_db([_scalar(user), _rowcount(3)])

    async with _override_db(mock_db):
        resp = await client.put(
            "/api/v1/auth/me/pin",
            json={"current_pin": "1234", "new_pin": "8317"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 204
    # The second statement is the revocation, and it targets this member's live tokens.
    revoke = mock_db.execute.await_args_list[1].args[0]
    compiled = str(revoke).lower()
    assert compiled.startswith("update refresh_tokens")
    assert "revoked_at" in compiled
    assert verify_pin("8317", user.pin_hash)


async def test_changing_a_pin_clears_a_lockout(client: AsyncClient) -> None:
    """Someone who proved they know the current PIN should not stay locked out."""
    user = _make_user(failed=5, locked_until=_now() + timedelta(minutes=10))
    token = create_access_token(user.id, user.role)
    mock_db = _stub_db([_scalar(user), _rowcount(0)])

    async with _override_db(mock_db):
        resp = await client.put(
            "/api/v1/auth/me/pin",
            json={"current_pin": "1234", "new_pin": "8317"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 204
    assert user.failed_login_count == 0
    assert user.locked_until is None


async def test_a_wrong_current_pin_revokes_nothing(client: AsyncClient) -> None:
    """A failed change must not log the member out of their own sessions."""
    user = _make_user()
    token = create_access_token(user.id, user.role)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.put(
            "/api/v1/auth/me/pin",
            json={"current_pin": "9999", "new_pin": "8317"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 401
    # One statement only — the profile lookup. No revocation was attempted.
    assert mock_db.execute.await_count == 1


# ---------------------------------------------------------------------------
# Batch 56 — an expired lockout returns the whole counter, not one attempt
# ---------------------------------------------------------------------------


async def test_an_expired_lockout_gives_back_all_five_attempts(client: AsyncClient) -> None:
    """The ratchet: a sixth wrong guess used to re-lock immediately, forever.

    `failed_login_count` reset only on success, so after the first lockout expired a
    single wrong answer took the count from 5 to 6 — still >= MAX_FAILED_ATTEMPTS — and
    locked the profile again. A member who had genuinely forgotten their PIN could never
    get more than one guess per window.
    """
    user = _make_user(failed=5, locked_until=_now() - timedelta(minutes=1))
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "9999"},
        )

    assert resp.status_code == 401
    # Counter restarted at 0 and took this one failure — not 6, and not re-locked.
    assert user.failed_login_count == 1
    assert user.locked_until is None


async def test_an_unexpired_lockout_still_refuses(client: AsyncClient) -> None:
    """Decay must not weaken the window itself."""
    user = _make_user(failed=5, locked_until=_now() + timedelta(minutes=5))
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"display_name": "Test User", "pin": "1234"},
        )

    assert resp.status_code == 423
    assert user.failed_login_count == 5


# ---------------------------------------------------------------------------
# Batch 56 — the reset request reaches somebody
# ---------------------------------------------------------------------------


async def test_a_pin_reset_request_records_and_notifies(client: AsyncClient) -> None:
    """It used to write one log line and claim an admin had been told."""
    user = _make_user()
    admin = _make_user(role=UserRole.admin)
    admins = MagicMock()
    admins.scalars.return_value.all.return_value = [admin]
    mock_db = _stub_db([_scalar(user), admins])

    sent: list[tuple[uuid.UUID, str]] = []

    async def _fake_send(session, user_id, title, body, **kwargs):  # noqa: ANN001, ANN202
        sent.append((user_id, title))
        return 1

    import src.routers.auth as auth_router

    original = auth_router.send_notification
    auth_router.send_notification = _fake_send  # type: ignore[assignment]
    try:
        async with _override_db(mock_db):
            resp = await client.post(
                "/api/v1/auth/pin/reset-request",
                json={"display_name": "Test User"},
            )
    finally:
        auth_router.send_notification = original  # type: ignore[assignment]

    assert resp.status_code == 200
    # A durable record was written...
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(type(row).__name__ == "AuditLog" for row in added)
    audit = next(row for row in added if type(row).__name__ == "AuditLog")
    assert audit.changes["stage"] == "requested"
    assert audit.target_id == user.id
    # ...and a live admin was actually told.
    assert sent == [(admin.id, "PIN reset requested")]


async def test_an_unknown_display_name_records_nothing(client: AsyncClient) -> None:
    """Same answer either way, so the endpoint cannot be used to enumerate members."""
    mock_db = _stub_db([_scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post(
            "/api/v1/auth/pin/reset-request",
            json={"display_name": "Nobody At All"},
        )

    assert resp.status_code == 200
    assert "an admin will be notified" in resp.json()["message"]
    assert mock_db.add.call_count == 0


# ---------------------------------------------------------------------------
# Batch 58 — reusing a rotated refresh token revokes the family
# ---------------------------------------------------------------------------


async def test_replaying_a_rotated_refresh_token_revokes_every_session(
    client: AsyncClient,
) -> None:
    """Reuse of a one-time token is the signature of theft (OAuth 2 BCP 4.13.2).

    Rotation means a refresh token is used exactly once, so a second use is either the
    victim or the thief and there is no way to tell which. Both are logged out; only the
    one who knows the PIN gets back in. Before this the two simply raced and the loser was
    signed out with nothing recorded.
    """
    user = _make_user()
    refresh_jwt = create_refresh_token(user.id, uuid.uuid4())
    revoked_record = _make_refresh_record(user.id, refresh_jwt)
    revoked_record.revoked_at = _now() - timedelta(minutes=1)

    # 1) no live row for this token, 2) but a revoked one exists, 3) the family revoke.
    mock_db = _stub_db([_scalar(None), _scalar(revoked_record), _rowcount(4)])

    async with _override_db(mock_db):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_jwt})

    assert resp.status_code == 401
    family_revoke = mock_db.execute.await_args_list[2].args[0]
    assert str(family_revoke).lower().startswith("update refresh_tokens")


async def test_an_unknown_refresh_token_revokes_nothing(client: AsyncClient) -> None:
    """Only a token this app issued and rotated away counts as reuse."""
    user = _make_user()
    refresh_jwt = create_refresh_token(user.id, uuid.uuid4())
    # No live row and no revoked row either — it was never ours.
    mock_db = _stub_db([_scalar(None), _scalar(None)])

    async with _override_db(mock_db):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_jwt})

    assert resp.status_code == 401
    # Two lookups, no third statement: nothing was revoked.
    assert mock_db.execute.await_count == 2


# ---------------------------------------------------------------------------
# Batch 58 — a PIN that is not really a PIN
# ---------------------------------------------------------------------------


async def test_a_common_pin_is_refused(client: AsyncClient) -> None:
    user = _make_user()
    token = create_access_token(user.id, user.role)
    mock_db = _stub_db([_scalar(user)])

    async with _override_db(mock_db):
        resp = await client.put(
            "/api/v1/auth/me/pin",
            json={"current_pin": "1234", "new_pin": "0000"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422
    assert "too common" in resp.json()["detail"]
    # The old PIN still works — nothing was written.
    assert verify_pin("1234", user.pin_hash)


async def test_an_ordinary_pin_is_accepted(client: AsyncClient) -> None:
    """The blocklist is the head of the distribution, not a general policy."""
    user = _make_user()
    token = create_access_token(user.id, user.role)
    mock_db = _stub_db([_scalar(user), _rowcount(1)])

    async with _override_db(mock_db):
        resp = await client.put(
            "/api/v1/auth/me/pin",
            json={"current_pin": "1234", "new_pin": "8317"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 204
    assert verify_pin("8317", user.pin_hash)


def test_the_weak_pin_list_covers_the_obvious_shapes() -> None:
    from src.auth import is_weak_pin

    for weak in ("0000", "1111", "1234", "4321", "1212", "6969"):
        assert is_weak_pin(weak), weak
    for fine in ("8317", "2749", "5081", "9042"):
        assert not is_weak_pin(fine), fine
