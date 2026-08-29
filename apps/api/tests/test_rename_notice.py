"""Batch 93 — the one-time notice to the three members Batch 74 renamed.

The hard part is not sending it. It is sending it *once*, from a task that runs on every
boot, to three accounts identified by name in a database where they may not exist at all —
and not marking someone as told when nothing actually reached them.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.models.notification import ActionType, AuditLog, PushSubscription
from src.models.profile import Profile
from src.services.rename_notice import (
    NOTICE_TITLE,
    RENAMED_MEMBERS,
    notice_body,
    send_rename_notices,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@contextmanager
def push_enabled() -> Iterator[MagicMock]:
    """Patch the delivery call *and* the VAPID keys.

    ``send_notification`` returns 0 when no keys are configured, which would make most of
    the assertions below pass for entirely the wrong reason: an undelivered notice would
    look exactly like a suppressed one, and the "did not mark them as told" tests would
    hold even if the marker logic were broken.
    """
    with (
        patch("src.services.push_notification_service._send_push_sync") as sync,
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
    ):
        yield sync


async def _renamed_profile(db: AsyncSession, new_name: str, *, subscribed: bool = True) -> Profile:
    """One of the three, as production holds them: already carrying the new name."""
    person = Profile(display_name=new_name, pin_hash=hash_pin("8351"))
    db.add(person)
    await db.flush()
    if subscribed:
        db.add(
            PushSubscription(
                user_id=person.id,
                subscription={"endpoint": f"https://example.test/{uuid.uuid4().hex}", "keys": {}},
                is_active=True,
            )
        )
        await db.flush()
    return person


async def _markers(db: AsyncSession) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog).where(AuditLog.action_type == ActionType.display_name_changed)
    )
    return list(result.scalars().all())


class TestReachesTheThree:
    async def test_notifies_every_renamed_member_that_exists(self, session: AsyncSession) -> None:
        for member in RENAMED_MEMBERS:
            await _renamed_profile(session, member.new_name)

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert set(sent) == {m.new_name for m in RENAMED_MEMBERS}
        assert all(count == 1 for count in sent.values())
        assert push.call_count == 3
        assert len(await _markers(session)) == 3

    async def test_body_names_the_old_name_and_the_new_one(self) -> None:
        # The old name is what they will type first, so the copy has to say both.
        body = notice_body(RENAMED_MEMBERS[0])
        assert RENAMED_MEMBERS[0].old_name in body
        assert RENAMED_MEMBERS[0].new_name in body
        # And must not imply their credentials changed — only the identifier did.
        assert "PIN itself has not changed" in body
        assert NOTICE_TITLE == "Your sign-in name changed"

    async def test_leaves_everyone_else_alone(self, session: AsyncSession) -> None:
        await _renamed_profile(session, f"Someone Else {uuid.uuid4().hex[:6]}")

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert sent == {}
        assert push.call_count == 0
        assert await _markers(session) == []

    async def test_is_a_no_op_where_the_three_do_not_exist(self, session: AsyncSession) -> None:
        # Every environment except production. This is what makes the boot hook safe.
        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert sent == {}
        assert push.call_count == 0

    async def test_matches_the_name_case_insensitively(self, session: AsyncSession) -> None:
        # Migration 017 made display names CI-unique, so the row's case is not guaranteed
        # to be the case the backfill note recorded.
        member = RENAMED_MEMBERS[0]
        await _renamed_profile(session, member.new_name.upper())

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert push.call_count == 1
        assert sent == {member.new_name: 1}


class TestOnlyOnce:
    async def test_a_second_run_sends_nothing(self, session: AsyncSession) -> None:
        for member in RENAMED_MEMBERS:
            await _renamed_profile(session, member.new_name)

        with push_enabled() as first:
            await send_rename_notices(session)
        await session.flush()
        with push_enabled() as second:
            again = await send_rename_notices(session)

        assert first.call_count == 3
        assert second.call_count == 0, "a redeploy must not tell them a second time"
        assert again == {}
        assert len(await _markers(session)) == 3

    async def test_the_marker_records_both_names(self, session: AsyncSession) -> None:
        member = RENAMED_MEMBERS[0]
        person = await _renamed_profile(session, member.new_name)

        with push_enabled():
            await send_rename_notices(session)

        marker = next(m for m in await _markers(session) if m.target_id == person.id)
        assert marker.target_table == "profiles"
        assert marker.changes == {"old": member.old_name, "new": member.new_name, "pushes": 1}


class TestUndelivered:
    async def test_an_unreachable_member_is_not_marked_as_told(self, session: AsyncSession) -> None:
        # No push subscription: send_notification delivers nothing, so nothing was said.
        member = RENAMED_MEMBERS[0]
        await _renamed_profile(session, member.new_name, subscribed=False)

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert push.call_count == 0
        assert sent == {member.new_name: 0}
        assert await _markers(session) == [], "marking them told would strand them silently"

    async def test_they_are_reached_once_they_subscribe(self, session: AsyncSession) -> None:
        member = RENAMED_MEMBERS[0]
        person = await _renamed_profile(session, member.new_name, subscribed=False)

        with push_enabled():
            await send_rename_notices(session)

        session.add(
            PushSubscription(
                user_id=person.id,
                subscription={"endpoint": "https://example.test/late", "keys": {}},
                is_active=True,
            )
        )
        await session.flush()

        with push_enabled() as later:
            sent = await send_rename_notices(session)

        assert later.call_count == 1
        assert sent == {member.new_name: 1}
        assert len(await _markers(session)) == 1


class TestTheBootHook:
    async def test_a_failure_does_not_stop_the_api_booting(self) -> None:
        """The notice is a courtesy to three people; the API must outlive its failure."""
        from src.main import _send_pending_rename_notices

        with patch("src.main.send_rename_notices", side_effect=RuntimeError("database is down")):
            await _send_pending_rename_notices()  # must not raise

    async def test_it_runs_from_lifespan(self) -> None:
        """'On this batch's deploy' is what the lifespan hook means in this app."""
        import inspect

        from src import main

        assert "_send_pending_rename_notices" in inspect.getsource(main.lifespan)
