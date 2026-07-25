import pytest

from src.auth import verify_pin
from src.models.profile import UserRole
from src.seeds import (
    ADMIN_DISPLAY_NAME,
    ADMIN_TIMEZONE,
    build_admin_profile,
)


def test_build_admin_profile_hashes_pin_and_sets_admin_metadata() -> None:
    profile = build_admin_profile("2468")

    assert profile.display_name == ADMIN_DISPLAY_NAME
    assert profile.pin_hash != "2468"
    assert verify_pin("2468", profile.pin_hash)
    assert profile.role == UserRole.admin
    assert profile.timezone == ADMIN_TIMEZONE
    assert profile.is_active is True


@pytest.mark.parametrize("pin", ["", "123", "12345", "12a4"])
def test_build_admin_profile_rejects_invalid_pin(pin: str) -> None:
    with pytest.raises(ValueError, match="ADMIN_PIN"):
        build_admin_profile(pin)
