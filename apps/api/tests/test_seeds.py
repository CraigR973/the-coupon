import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from src.auth import verify_pin
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.seeds import (
    ADMIN_DISPLAY_NAME,
    ADMIN_TIMEZONE,
    BootstrapPlayer,
    bootstrap_league,
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
    roster_path.write_text(
        """
        {
          "players": [
            {
              "display_name": "Alice",
              "pin": "12a4",
              "role": "admin",
              "league_role": "admin"
            }
          ]
        }
        """
    )

    with pytest.raises(ValueError, match="ADMIN_PIN"):
        load_roster(roster_path)


def test_load_roster_requires_exactly_one_admin(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        '{"players": [{"display_name": "Alice", "pin": "1234"}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one"):
        load_roster(roster_path)


def test_load_roster_rejects_duplicate_display_names(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        """
        {
          "players": [
            {
              "display_name": "Craig",
              "pin": "1234",
              "role": "admin",
              "league_role": "admin"
            },
            {"display_name": "craig", "pin": "5678"}
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unique"):
        load_roster(roster_path)


def test_load_roster_rejects_split_admin_roles(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        """
        {
          "players": [
            {
              "display_name": "Craig",
              "pin": "1234",
              "role": "admin"
            },
            {
              "display_name": "Alice",
              "pin": "5678",
              "league_role": "admin"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one"):
        load_roster(roster_path)


@pytest.mark.asyncio
async def test_bootstrap_league_uses_roster_admin_and_is_idempotent(
    db_conn: AsyncConnection,
) -> None:
    roster = [
        BootstrapPlayer(
            display_name="Craig",
            pin="1111",
            role=UserRole.admin,
            timezone="Europe/London",
            league_role=LeagueMemberRole.admin,
        ),
        BootstrapPlayer(display_name="Alice", pin="2222"),
    ]
    async with AsyncSession(
        bind=db_conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        first = await bootstrap_league(
            db,
            admin_pin="2468",
            roster=roster,
            league_slug="bootstrap-test",
            league_name="Bootstrap Test",
        )
        second = await bootstrap_league(
            db,
            admin_pin="2468",
            roster=roster,
            league_slug="bootstrap-test",
            league_name="Bootstrap Test",
        )

        profiles = (
            (
                await db.execute(
                    select(Profile)
                    .where(Profile.display_name.in_(["Craig", "Alice", ADMIN_DISPLAY_NAME]))
                    .where(Profile.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        league = (
            await db.execute(select(League).where(League.slug == "bootstrap-test"))
        ).scalar_one()
        membership_count = await db.scalar(
            select(func.count())
            .select_from(LeagueMembership)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.deleted_at.is_(None),
            )
        )

    assert first.profiles_created == 2
    assert first.memberships_created == 2
    assert second.profiles_created == 0
    assert second.profiles_updated == 2
    assert second.memberships_created == 0
    assert {profile.display_name for profile in profiles} == {"Craig", "Alice"}
    assert membership_count == 2
    craig = next(profile for profile in profiles if profile.display_name == "Craig")
    assert craig.role == UserRole.admin
    assert craig.timezone == "Europe/London"
    assert verify_pin("2468", craig.pin_hash)
