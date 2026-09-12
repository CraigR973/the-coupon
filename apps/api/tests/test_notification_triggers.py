"""Unit tests for the pick-reminder trigger (collaborators mocked — no DB)."""

from __future__ import annotations

import pathlib
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.models.gameweek import Gameweek
from src.services.gameweek import MissingPickMember, NotificationTarget, RoundProgress
from src.services.notification_triggers import notify_pick_made, send_pick_reminders

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


# ── Batch 116 item 2: the product's name in the tray ──────────────────────────
#
# The owner reported a pick alert reading as being *from Coupon* when it did not need to,
# and the row refused to guess between two causes without seeing one. The screenshot
# arrived on 2026-09-12 and settled it: every alert was titled with the **league** name
# ("2-1 Hibs"), under an OS line reading "from Coupon". That second line is the platform's
# own attribution for an installed PWA — it cannot be suppressed, only renamed — so there
# was never a second occurrence of the product's name to remove, and **the owner decided
# the same day to leave `short_name` exactly as it is**.
#
# What the screenshot could not show is the row's other candidate, because no live league
# can currently produce it: a league whose own *name* is the product's name would be titled
# "The Coupon" beneath a header reading "Coupon". The league that was named that
# (`the-coupon`) is soft-deleted; the two live leagues are 2-1 Hibs and McCann's Defenders.
#
# These tests pin both halves — the behaviour that is right, and the gap that is known —
# in the style Batch 89 used for the unbounded pick path: assert the gap so it stays
# visible until somebody decides to close it, rather than closing it by guess. Changing the
# title rule alters copy that reaches a phone unprompted, which is precisely what the row
# said not to do without being asked.

#: `short_name` in `apps/web/vite.config.ts` — what the platform stamps above every
#: notification. Pinned from Python because the duplication is a property of the *pair*:
#: the title is composed here and the attribution is composed there, and neither file can
#: see the other. `test_the_tray_attribution_is_the_name_this_module_assumes` is the join.
PRODUCT_SHORT_NAME = "Coupon"

#: `name` in the same manifest, and `seeds.DEFAULT_LEAGUE_NAME`. The collision candidate.
PRODUCT_NAME = "The Coupon"


def _target(league_name: str) -> NotificationTarget:
    return NotificationTarget(
        player_id=str(uuid.uuid4()),
        display_name="Bob",
        timezone="Europe/London",
        league_id=str(uuid.uuid4()),
        league_slug="a-league",
        league_name=league_name,
    )


async def _titles_for(league_name: str) -> list[str]:
    """The notification titles a pick alert produces for a league of that name."""
    with (
        patch(
            "src.services.notification_triggers.notification_targets",
            new=AsyncMock(return_value=[_target(league_name)]),
        ),
        patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send,
    ):
        await notify_pick_made(
            AsyncMock(),
            _gameweek(),
            uuid.uuid4(),
            "Dave",
            "Arsenal",
            Decimal("1.80"),
            moved=False,
            progress=RoundProgress(picked_count=3, member_count=12, all_picked=False),
        )
    return [call.args[2] for call in send.await_args_list]


@pytest.mark.asyncio
async def test_a_pick_alert_is_titled_with_the_league_and_not_the_product() -> None:
    """The behaviour the screenshot confirmed is correct, so it cannot regress quietly.

    The tray is league-scoped — Batch 107 put the league in the title for that reason — and
    the platform's attribution supplies the product name on its own line. Titling with the
    product as well would say nothing the header does not.
    """
    assert await _titles_for("2-1 Hibs") == ["2-1 Hibs"]
    assert PRODUCT_SHORT_NAME not in "2-1 Hibs"


@pytest.mark.asyncio
async def test_a_league_named_after_the_product_prints_it_twice_and_this_is_known() -> None:
    """The residual, asserted rather than fixed (owner decision, 2026-09-12).

    A league called "The Coupon" is titled "The Coupon" under a header reading "Coupon", so
    the tray names the product twice and the league never — which is exactly the complaint
    item 2 was raised about, reached by the one route the screenshot could not show.

    It is left alone on purpose. No live league is named this, the fix is a rule about copy
    rather than a string (what *should* such a league's alert say?), and that copy reaches a
    phone unprompted. When somebody decides the rule, this test is what they delete.
    """
    titles = await _titles_for(PRODUCT_NAME)

    assert titles == [PRODUCT_NAME]
    assert (
        PRODUCT_SHORT_NAME in titles[0]
    ), "the premise of the gap: the title contains the name the platform already stamped"


def test_the_tray_attribution_is_the_name_this_module_assumes() -> None:
    """Pin the manifest, because the duplication lives across the two files.

    The owner chose on 2026-09-12 to leave `short_name` as "Coupon". If it is ever renamed,
    the reasoning above stops describing the product and the test beside this one stops
    describing a collision — so the rename has to come back through here.
    """
    manifest = (
        pathlib.Path(__file__).resolve().parents[3] / "apps" / "web" / "vite.config.ts"
    ).read_text()

    assert f"short_name: '{PRODUCT_SHORT_NAME}'" in manifest
    assert f"name: '{PRODUCT_NAME}'" in manifest
