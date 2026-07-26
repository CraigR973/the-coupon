"""Unit tests for the pick-reminder trigger (collaborators mocked — no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.gameweek import MissingPickMember
from src.services.notification_triggers import send_pick_reminders


def _member(name: str, timezone: str) -> MissingPickMember:
    return MissingPickMember(
        player_id=str(uuid.uuid4()),
        display_name=name,
        timezone=timezone,
        league_id=str(uuid.uuid4()),
        league_name=f"{name}'s league",
    )


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
        count = await send_pick_reminders(session, MagicMock())

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
        assert await send_pick_reminders(session, MagicMock()) == 0
    send.assert_not_awaited()
