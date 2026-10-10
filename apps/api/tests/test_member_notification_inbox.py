"""Member notification history survives missing push and keeps each member isolated."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.auth import get_current_user
from src.config import settings
from src.database import AsyncSessionLocal, get_db
from src.main import app
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import MemberNotification, NotificationPreferences, PushSubscription
from src.models.profile import Profile
from src.scheduler import MEMBER_NOTIFICATION_RETENTION, run_prune_rate_limit_counters
from src.services.push_notification_service import (
    collect_notification_intents,
    prepare_collected_notifications,
    send_notification,
)


@pytest_asyncio.fixture
async def members() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    async with AsyncSessionLocal() as session:
        first = Profile(display_name=f"inbox-a-{uuid.uuid4().hex[:8]}", pin_hash=None)
        second = Profile(display_name=f"inbox-b-{uuid.uuid4().hex[:8]}", pin_hash=None)
        session.add_all([first, second])
        await session.flush()
        league = League(
            slug=f"inbox-{uuid.uuid4().hex[:8]}", name="Inbox League", created_by=first.id
        )
        session.add(league)
        await session.flush()
        session.add_all(
            [
                LeagueMembership(league_id=league.id, player_id=first.id),
                LeagueMembership(league_id=league.id, player_id=second.id),
            ]
        )
        await session.commit()
        ids = first.id, second.id, league.id
    try:
        yield ids
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MemberNotification).where(MemberNotification.league_id == ids[2])
            )
            await session.execute(
                delete(NotificationPreferences).where(NotificationPreferences.user_id.in_(ids[:2]))
            )
            await session.execute(
                delete(PushSubscription).where(PushSubscription.user_id.in_(ids[:2]))
            )
            await session.execute(
                delete(LeagueMembership).where(LeagueMembership.league_id == ids[2])
            )
            await session.execute(delete(League).where(League.id == ids[2]))
            await session.execute(delete(Profile).where(Profile.id.in_(ids[:2])))
            await session.commit()
        app.dependency_overrides.clear()


async def _db() -> AsyncIterator[object]:
    async with AsyncSessionLocal() as session:
        yield session


def _event(league_id: uuid.UUID, kind: str = "picks_open") -> dict[str, str]:
    return {"type": kind, "url": "/leagues/inbox/predictions", "league_id": str(league_id)}


@pytest.mark.asyncio
async def test_unsubscribed_members_get_private_history_and_read_state(
    members: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    first, second, league_id = members
    member_kinds = (
        "pick_made",
        "pick_changed",
        "all_picked",
        "picks_open",
        "pick_reminder",
        "fixture_postponed",
        "round_settled",
        "result_corrected",
    )
    with (
        patch.object(settings, "vapid_private_key", ""),
        patch.object(settings, "vapid_public_key", ""),
    ):
        async with AsyncSessionLocal() as session:
            for kind in member_kinds:
                assert (
                    await send_notification(
                        session,
                        first,
                        "League",
                        kind,
                        data=_event(league_id, kind),
                        league_id=league_id,
                    )
                    == 0
                )
            assert (
                await send_notification(
                    session,
                    second,
                    "League",
                    "Second only",
                    data=_event(league_id),
                    league_id=league_id,
                )
                == 0
            )
            await session.commit()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=first)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_inbox = await client.get("/api/v1/notifications/inbox")
        assert first_inbox.status_code == 200
        assert first_inbox.json()["unread_count"] == len(member_kinds)
        assert {item["body"] for item in first_inbox.json()["items"]} == set(member_kinds)
        assert all(item["created_at"].endswith("Z") for item in first_inbox.json()["items"])
        marked = await client.post("/api/v1/notifications/inbox/read")
        assert marked.status_code == 200
        assert marked.json()["read_count"] == len(member_kinds)
        assert (await client.get("/api/v1/notifications/inbox")).json()["unread_count"] == 0

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=second)
        second_inbox = await client.get("/api/v1/notifications/inbox")
        assert second_inbox.json()["unread_count"] == 1
        assert [item["body"] for item in second_inbox.json()["items"]] == ["Second only"]


@pytest.mark.asyncio
async def test_mutes_hide_both_channels_but_quiet_hours_keep_history(
    members: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    first, _, league_id = members
    now = datetime(2026, 10, 10, 12)
    with (
        patch.object(settings, "vapid_private_key", "private"),
        patch.object(settings, "vapid_public_key", "public"),
        patch("src.services.push_notification_service._send_push_sync") as push,
    ):
        async with AsyncSessionLocal() as session:
            prefs = NotificationPreferences(user_id=first, mute_pick_activity=True)
            session.add(prefs)
            session.add(
                PushSubscription(
                    user_id=first,
                    subscription={
                        "endpoint": "https://fcm.googleapis.com/push",
                        "keys": {"auth": "x", "p256dh": "y"},
                    },
                )
            )
            await session.flush()
            assert (
                await send_notification(
                    session,
                    first,
                    "League",
                    "Muted pick",
                    data=_event(league_id, "pick_made"),
                    league_id=league_id,
                    now_utc=now,
                )
                == 0
            )

            prefs.mute_pick_activity = False
            prefs.quiet_hours_start = datetime(2000, 1, 1, 0)
            prefs.quiet_hours_end = datetime(2000, 1, 1, 23, 59)
            assert (
                await send_notification(
                    session,
                    first,
                    "League",
                    "Quiet pick",
                    data=_event(league_id, "pick_made"),
                    league_id=league_id,
                    now_utc=now,
                )
                == 0
            )

            prefs.global_mute = True
            assert (
                await send_notification(
                    session,
                    first,
                    "League",
                    "Globally muted",
                    data=_event(league_id, "round_settled"),
                    league_id=league_id,
                    now_utc=now,
                )
                == 0
            )
            prefs.global_mute = False
            membership = (
                await session.execute(
                    select(LeagueMembership).where(
                        LeagueMembership.league_id == league_id, LeagueMembership.player_id == first
                    )
                )
            ).scalar_one()
            membership.notification_muted = True
            assert (
                await send_notification(
                    session,
                    first,
                    "League",
                    "League muted",
                    data=_event(league_id, "round_settled"),
                    league_id=league_id,
                    now_utc=now,
                )
                == 0
            )
            await session.commit()
            bodies = (
                (
                    await session.execute(
                        select(MemberNotification.body).where(MemberNotification.user_id == first)
                    )
                )
                .scalars()
                .all()
            )
            assert bodies == ["Quiet pick"]
            membership.notification_muted = False
            prefs.mute_pick_activity = True
            await session.commit()
        push.assert_not_called()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=first)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hidden = await client.get("/api/v1/notifications/inbox")
        assert hidden.status_code == 200
        assert hidden.json() == {"items": [], "unread_count": 0}


@pytest.mark.asyncio
async def test_collected_fanout_persists_without_vapid_or_subscription(
    members: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    first, _, league_id = members
    with (
        patch.object(settings, "vapid_private_key", ""),
        patch.object(settings, "vapid_public_key", ""),
    ):
        async with AsyncSessionLocal() as session:
            with collect_notification_intents() as intents:
                assert (
                    await send_notification(
                        session,
                        first,
                        "League",
                        "A pick moved",
                        data=_event(league_id, "pick_changed"),
                        league_id=league_id,
                    )
                    == 0
                )
            assert await prepare_collected_notifications(session, intents) == ()
            await session.commit()
            row = (
                await session.execute(
                    select(MemberNotification).where(MemberNotification.user_id == first)
                )
            ).scalar_one()
            assert row.kind == "pick_changed"
            assert row.body == "A pick moved"


@pytest.mark.asyncio
async def test_retention_prunes_expired_rows_and_keeps_recent_ones(
    members: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    first, _, league_id = members
    now = datetime.now(UTC).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                MemberNotification(
                    user_id=first,
                    league_id=league_id,
                    kind="picks_open",
                    title="Old",
                    body="Expired",
                    url="/",
                    created_at=now - MEMBER_NOTIFICATION_RETENTION - timedelta(days=1),
                ),
                MemberNotification(
                    user_id=first,
                    league_id=league_id,
                    kind="picks_open",
                    title="New",
                    body="Retained",
                    url="/",
                    created_at=now - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    assert await run_prune_rate_limit_counters() is True
    async with AsyncSessionLocal() as session:
        remaining = (
            (
                await session.execute(
                    select(MemberNotification.body).where(MemberNotification.user_id == first)
                )
            )
            .scalars()
            .all()
        )
        assert remaining == ["Retained"]
