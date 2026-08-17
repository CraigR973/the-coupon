"""Unit tests for the pick-reminder trigger (collaborators mocked — no DB)."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.gameweek import Gameweek
from src.services.gameweek import MissingPickMember
from src.services.notification_triggers import send_pick_reminders

#: Naive-UTC, as stored. 13:30 UTC is 14:30 in London during British Summer Time.
LOCKS_AT = datetime(2026, 8, 22, 13, 30)


def _member(name: str, timezone: str) -> MissingPickMember:
    return MissingPickMember(
        player_id=str(uuid.uuid4()),
        display_name=name,
        timezone=timezone,
        league_id=str(uuid.uuid4()),
        league_slug=f"{name}-league",
        league_name=f"{name}'s league",
    )


def _gameweek(locks_at_utc: datetime = LOCKS_AT) -> Gameweek:
    return Gameweek(locks_at_utc=locks_at_utc)


@pytest.mark.asyncio
async def test_send_pick_reminders_nudges_each_missing_member() -> None:
    session = AsyncMock()
    members = [_member("bob", "Europe/London"), _member("carol", "UTC")]
    with (
        patch(
            "src.services.notification_triggers.members_missing_picks",
            new=AsyncMock(return_value=members),
        ),
        patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send,
    ):
        count = await send_pick_reminders(session, _gameweek())

    assert count == 2
    assert send.await_count == 2
    # Each reminder targeted the right member id + their timezone (for quiet-hours).
    targeted = {call.args[1]: call.kwargs["timezone_name"] for call in send.await_args_list}
    assert targeted == {uuid.UUID(m.player_id): m.timezone for m in members}


@pytest.mark.asyncio
async def test_send_pick_reminders_no_one_missing_sends_nothing() -> None:
    session = AsyncMock()
    with (
        patch(
            "src.services.notification_triggers.members_missing_picks",
            new=AsyncMock(return_value=[]),
        ),
        patch("src.services.notification_triggers.send_notification", new=AsyncMock()) as send,
    ):
        assert await send_pick_reminders(session, _gameweek()) == 0
    send.assert_not_awaited()


# ── Batch 30: the reminder points at the league it is about ────────────────────


@pytest.mark.asyncio
async def test_send_pick_reminders_links_to_that_league_s_pick_screen() -> None:
    """Without a ``url`` the service worker falls back to ``/`` — a list of every league."""
    session = AsyncMock()
    member = _member("bob", "Europe/London")
    with (
        patch(
            "src.services.notification_triggers.members_missing_picks",
            new=AsyncMock(return_value=[member]),
        ),
        patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send,
    ):
        await send_pick_reminders(session, _gameweek())

    assert send.await_args.kwargs["data"] == {
        "type": "pick_reminder",
        "league_id": member.league_id,
        "url": "/leagues/bob-league/predictions",
    }


@pytest.mark.asyncio
async def test_send_pick_reminders_names_the_round_s_own_deadline() -> None:
    """Lock time is per-league and admin-configurable, so the copy cannot hardcode 14:30."""
    session = AsyncMock()
    members = [_member("bob", "Europe/London"), _member("carol", "UTC")]
    with (
        patch(
            "src.services.notification_triggers.members_missing_picks",
            new=AsyncMock(return_value=members),
        ),
        patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send,
    ):
        # A league playing Friday to Monday, locking Friday evening rather than Saturday.
        await send_pick_reminders(session, _gameweek(datetime(2026, 8, 21, 18, 45)))

    bodies = [call.args[3] for call in send.await_args_list]
    # Each member reads the same instant on their own clock: 19:45 in London, 18:45 UTC.
    assert bodies[0] == "You haven't made your pick in bob's league yet — picks lock Fri 19:45."
    assert bodies[1] == "You haven't made your pick in carol's league yet — picks lock Fri 18:45."


@pytest.mark.asyncio
async def test_send_pick_reminders_falls_back_to_utc_for_an_unknown_timezone() -> None:
    session = AsyncMock()
    with (
        patch(
            "src.services.notification_triggers.members_missing_picks",
            new=AsyncMock(return_value=[_member("dave", "Mars/Olympus_Mons")]),
        ),
        patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send,
    ):
        await send_pick_reminders(session, _gameweek())

    assert send.await_args.args[3].endswith("picks lock Sat 13:30.")
