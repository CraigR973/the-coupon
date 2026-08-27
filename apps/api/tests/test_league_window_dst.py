"""A league window may not land on the hour British clocks change.

Batch 84. ``SlateWindow`` builds every local instant as
``datetime(y, m, d, tzinfo=UK_TZ) + timedelta(minutes=...)``, which is wall-clock
arithmetic: on the last Sunday of March the hour 01:00-02:00 does not exist, on the
last Sunday of October it happens twice, and Python resolves both silently via
``fold=0`` instead of raising. Any authenticated member can configure such a window
since Batch 63, so it is refused at the door.

The predicate tests below need no database. The two HTTP tests do, and skip without
``DATABASE_URL`` like the rest of the suite's endpoint coverage.
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.routers.leagues import (
    _check_dst_safe_window,
    _recurs_into_a_transition,
    _uk_transition_days,
)

MONDAY, SATURDAY, SUNDAY = 0, 5, 6
THREE_PM = 15 * 60


# ── What the tz database actually says ────────────────────────────────────────


def test_transitions_are_read_from_zoneinfo_not_assumed() -> None:
    """Two a year, both Sundays — asserted rather than trusted.

    Every rejection below rests on this. If the tz database ever moves the rule, this
    is the test that should fail first and explain why the others did.
    """
    for year in (2026, 2027, 2028):
        days = _uk_transition_days(year)
        assert len(days) == 2, f"{year} should change the clocks twice, got {days}"
        assert all(day.weekday() == SUNDAY for day in days), days
        assert days[0].month == 3 and days[1].month == 10


# ── The predicate ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("weekday", "minute", "why"),
    [
        (SUNDAY, 60, "01:00 — the first instant that vanishes"),
        (SUNDAY, 90, "01:30 — squarely inside"),
        (SUNDAY, 119, "01:59 — the last instant that vanishes"),
    ],
)
def test_transition_hour_is_refused(weekday: int, minute: int, why: str) -> None:
    assert _recurs_into_a_transition(weekday, minute) is True, why


@pytest.mark.parametrize(
    ("weekday", "minute", "why"),
    [
        (SUNDAY, 59, "00:59 — one minute before the clocks move"),
        (SUNDAY, 120, "02:00 — one minute after the hour closes"),
        (SUNDAY, 0, "midnight Sunday"),
        (SATURDAY, THREE_PM, "the default window every league ships with"),
        (SATURDAY, 90, "01:30, but on a Saturday — the clocks never change then"),
        (MONDAY, 90, "01:30 on a Monday, likewise"),
    ],
)
def test_every_other_window_is_accepted(weekday: int, minute: int, why: str) -> None:
    assert _recurs_into_a_transition(weekday, minute) is False, why


def test_an_instant_measured_backwards_lands_on_its_real_weekday() -> None:
    """A lock is subtracted from the opening, so it can cross midnight into another day.

    This is the reason the predicate normalises before testing: a Sunday 03:00 window
    with a 90-minute lock is a *safe* window with an *unsafe* lock, and a Monday 00:30
    window with a 60-minute lock resolves back to Sunday 23:30, which is fine.
    """
    assert _recurs_into_a_transition(SUNDAY, 180 - 90) is True  # Sunday 01:30
    assert _recurs_into_a_transition(MONDAY, 30 - 60) is False  # Sunday 23:30


# ── Which of the four instants is at fault ────────────────────────────────────


def _window(**overrides: int | None) -> dict[str, int | None]:
    base: dict[str, int | None] = {
        "start_weekday": SATURDAY,
        "start_minute": THREE_PM,
        "end_weekday": SATURDAY,
        "end_minute": THREE_PM,
        "lock_offset_minutes": 30,
        "pick_open_offset_minutes": None,
    }
    return base | overrides


@pytest.mark.parametrize(
    ("overrides", "named"),
    [
        ({"start_weekday": SUNDAY, "start_minute": 90}, "the window opening"),
        ({"end_weekday": SUNDAY, "end_minute": 90}, "the window close"),
        (
            {"start_weekday": SUNDAY, "start_minute": 180, "lock_offset_minutes": 90},
            "the pick lock",
        ),
        (
            {
                "start_weekday": SUNDAY,
                "start_minute": 180,
                "lock_offset_minutes": 30,
                "pick_open_offset_minutes": 90,
            },
            "the announced pick opening",
        ),
    ],
)
def test_the_refusal_names_the_offending_instant(overrides: dict[str, int], named: str) -> None:
    """All four instants are checked, and the 422 says which one is wrong.

    An admin who set a lock offset three screens ago cannot be expected to work out
    that *that* is what a bare "invalid window" refers to.
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        _check_dst_safe_window(**_window(**overrides))  # type: ignore[arg-type]
    assert raised.value.status_code == 422
    assert named in str(raised.value.detail)


def test_the_default_window_is_accepted() -> None:
    """Saturday 15:00 with a 30-minute lock — what every league has today."""
    _check_dst_safe_window(**_window())  # type: ignore[arg-type]


# ── Over HTTP ─────────────────────────────────────────────────────────────────

db_required = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _seed_admin(session: AsyncSession) -> tuple[Profile, League]:
    """One member, and a league they administer."""
    tag = uuid.uuid4().hex[:8]
    player = Profile(display_name=f"dst-{tag}", pin_hash=hash_pin("3719"), role=UserRole.player)
    session.add(player)
    await session.flush()
    league = League(slug=f"dst-{tag}", name=f"DST {tag}", created_by=player.id)
    session.add(league)
    await session.flush()
    session.add(
        LeagueMembership(league_id=league.id, player_id=player.id, role=LeagueMemberRole.admin)
    )
    await session.commit()
    await session.refresh(player)
    await session.refresh(league)
    return player, league


@db_required
async def test_create_refuses_a_transition_window_and_accepts_the_next_minute() -> None:
    async with AsyncSessionLocal() as session:
        player, _ = await _seed_admin(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        refused = await client.post(
            "/api/v1/leagues",
            json={
                "name": f"Small Hours {uuid.uuid4().hex[:6]}",
                "slate_start_weekday": SUNDAY,
                "slate_start_minute": 90,
                "slate_end_weekday": SUNDAY,
                "slate_end_minute": 22 * 60,
            },
            headers=_auth(player),
        )
        assert refused.status_code == 422, refused.text
        assert "clocks change" in refused.json()["detail"]

        allowed = await client.post(
            "/api/v1/leagues",
            json={
                "name": f"Two AM {uuid.uuid4().hex[:6]}",
                "slate_start_weekday": SUNDAY,
                "slate_start_minute": 120,
                "slate_end_weekday": SUNDAY,
                "slate_end_minute": 22 * 60,
                "lock_offset_minutes": 0,
            },
            headers=_auth(player),
        )
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["slate_window"]["start_minute"] == 120


@db_required
async def test_patch_naming_only_the_minute_is_still_judged_on_the_stored_weekday() -> None:
    """The case a request-body validator cannot catch, which is why the handler checks.

    The league is moved to Sunday first, then patched with *only* a minute. Nothing in
    that second body says "Sunday" — the weekday it lands on comes from the row.
    """
    async with AsyncSessionLocal() as session:
        player, league = await _seed_admin(session)
        slug = league.slug

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        moved = await client.patch(
            f"/api/v1/leagues/{slug}",
            json={"slate_start_weekday": SUNDAY, "slate_start_minute": 12 * 60},
            headers=_auth(player),
        )
        assert moved.status_code == 200, moved.text

        refused = await client.patch(
            f"/api/v1/leagues/{slug}",
            json={"slate_start_minute": 90},
            headers=_auth(player),
        )
        assert refused.status_code == 422, refused.text
        assert "the window opening" in refused.json()["detail"]

    # And the refusal left the stored window alone.
    async with AsyncSessionLocal() as session:
        after = await session.get(League, league.id)
        assert after is not None
        assert after.slate_start_minute == 12 * 60
