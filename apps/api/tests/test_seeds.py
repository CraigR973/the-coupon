import pytest

from src.auth import verify_pin
from src.models.league_membership import LeagueMemberRole
from src.models.profile import UserRole
from src.seeds import (
    ADMIN_DISPLAY_NAME,
    ADMIN_TIMEZONE,
    BootstrapPlayer,
    build_admin_profile,
    load_roster,
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


def test_load_roster_parses_players(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        """
        {
          "players": [
            {
              "display_name": "Alice",
              "pin": "1234",
              "role": "admin",
              "league_role": "admin",
              "timezone": "Europe/London"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    assert load_roster(roster_path) == [
        BootstrapPlayer(
            display_name="Alice",
            pin="1234",
            role=UserRole.admin,
            timezone="Europe/London",
            league_role=LeagueMemberRole.admin,
        )
    ]


def test_load_roster_rejects_invalid_pin(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text('{"players": [{"display_name": "Alice", "pin": "12a4"}]}')

    with pytest.raises(ValueError, match="ADMIN_PIN"):
        load_roster(roster_path)
