"""Batch 93 — the one-time notice to the three members Batch 74 renamed.

The hard part is not sending it. It is sending it *once*, from a task that runs on every
boot, to three accounts identified by id in a database where they may not exist at all —
and not marking someone as told when nothing actually reached them.

Batch 148 added the second channel — the app itself, for a member push cannot reach — and
:class:`TestInTheApp` covers it.

Postgres-backed; each test rolls back, except :class:`TestInTheApp`, whose requests run in
their own sessions and so commit, and which deletes what it wrote.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.main import app
from src.models.notification import ActionType, ActorType, AuditLog, PushSubscription
from src.models.profile import Profile
from src.services.rename_notice import (
    NOTICE_TITLE,
    RENAMED_PROFILE_IDS,
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


async def _renamed_profile(
    db: AsyncSession, profile_id: uuid.UUID, *, name: str | None = None, subscribed: bool = True
) -> Profile:
    """One of the three, as production holds them: already carrying the new name."""
    person = Profile(
        id=profile_id,
        display_name=name or f"Renamed {uuid.uuid4().hex[:6]}",
        pin_hash=hash_pin("8351"),
    )
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
        for profile_id in RENAMED_PROFILE_IDS:
            await _renamed_profile(session, profile_id)

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert set(sent) == {str(profile_id) for profile_id in RENAMED_PROFILE_IDS}
        assert all(count == 1 for count in sent.values())
        assert push.call_count == 3
        assert len(await _markers(session)) == 3

    async def test_body_names_the_new_name_and_retires_the_old_one(self) -> None:
        # The old name is what they will type first, so the copy has to say it is gone.
        # It no longer quotes it: the old names are not published anywhere (Batch 155).
        body = notice_body("Member A Fullname")
        assert 'Sign in as "Member A Fullname"' in body
        assert "old sign-in name no longer works" in body
        # And must not imply their credentials changed — only the identifier did.
        assert "PIN itself has not changed" in body
        assert NOTICE_TITLE == "Your sign-in name changed"

    async def test_leaves_everyone_else_alone(self, session: AsyncSession) -> None:
        await _renamed_profile(session, uuid.uuid4(), name=f"Someone Else {uuid.uuid4().hex[:6]}")

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

    async def test_finds_them_by_id_whatever_they_are_called_now(
        self, session: AsyncSession
    ) -> None:
        # The id is the match, so a member renamed again since Batch 74 is still reached —
        # and told the name the row holds now, which is the one that signs them in.
        profile_id = RENAMED_PROFILE_IDS[0]
        await _renamed_profile(session, profile_id, name="Renamed Again")

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert push.call_count == 1
        assert sent == {str(profile_id): 1}
        _, payload = push.call_args.args
        assert json.loads(payload)["body"] == notice_body("Renamed Again")


class TestOnlyOnce:
    async def test_a_second_run_sends_nothing(self, session: AsyncSession) -> None:
        for profile_id in RENAMED_PROFILE_IDS:
            await _renamed_profile(session, profile_id)

        with push_enabled() as first:
            await send_rename_notices(session)
        await session.flush()
        with push_enabled() as second:
            again = await send_rename_notices(session)

        assert first.call_count == 3
        assert second.call_count == 0, "a redeploy must not tell them a second time"
        assert again == {}
        assert len(await _markers(session)) == 3

    async def test_the_marker_records_the_name_they_were_told(self, session: AsyncSession) -> None:
        person = await _renamed_profile(session, RENAMED_PROFILE_IDS[0])

        with push_enabled():
            await send_rename_notices(session)

        marker = next(m for m in await _markers(session) if m.target_id == person.id)
        assert marker.target_table == "profiles"
        assert marker.changes == {"new": person.display_name, "pushes": 1}


class TestUndelivered:
    async def test_an_unreachable_member_is_not_marked_as_told(self, session: AsyncSession) -> None:
        # No push subscription: send_notification delivers nothing, so nothing was said.
        profile_id = RENAMED_PROFILE_IDS[0]
        await _renamed_profile(session, profile_id, subscribed=False)

        with push_enabled() as push:
            sent = await send_rename_notices(session)

        assert push.call_count == 0
        assert sent == {str(profile_id): 0}
        assert await _markers(session) == [], "marking them told would strand them silently"

    async def test_they_are_reached_once_they_subscribe(self, session: AsyncSession) -> None:
        profile_id = RENAMED_PROFILE_IDS[0]
        person = await _renamed_profile(session, profile_id, subscribed=False)

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
        assert sent == {str(profile_id): 1}
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


NOTICE_URL = "/api/v1/me/rename-notice"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def made() -> AsyncIterator[list[Profile]]:
    """The members a test commits, and afterwards everything written about them.

    A request opens its own session, so these rows must be committed to be seen at all —
    and then removed, because :func:`_markers` counts every marker in the database and the
    rolled-back tests above expect to find only their own.
    """
    people: list[Profile] = []
    yield people
    ids = [person.id for person in people]
    if ids:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditLog).where(AuditLog.target_id.in_(ids)))
            await db.execute(delete(Profile).where(Profile.id.in_(ids)))
            await db.commit()


async def _committed_member(made: list[Profile], *, subscribed: bool = False) -> Profile:
    async with AsyncSessionLocal() as db:
        person = await _renamed_profile(db, uuid.uuid4(), subscribed=subscribed)
        await db.commit()
        await db.refresh(person)
    made.append(person)
    return person


@contextmanager
def _renamed(*people: Profile) -> Iterator[None]:
    """Stand these committed members in for the three production ids."""
    with patch(
        "src.services.rename_notice.RENAMED_PROFILE_IDS", tuple(person.id for person in people)
    ):
        yield


def _auth(person: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(person.id, person.role)}"}


async def _markers_for(person: Profile) -> list[AuditLog]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.action_type == ActionType.display_name_changed,
                AuditLog.target_id == person.id,
            )
        )
        return list(result.scalars().all())


async def _run_the_boot_task() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        sent = await send_rename_notices(db)
        await db.commit()
    return sent


class TestInTheApp:
    """Batch 148: the app is the channel for a member push cannot reach."""

    async def test_a_member_push_cannot_reach_is_shown_it_in_the_app(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        person = await _committed_member(made, subscribed=False)

        with _renamed(person), push_enabled() as push:
            sent = await _run_the_boot_task()
            response = await client.get(NOTICE_URL, headers=_auth(person))

        assert push.call_count == 0
        assert sent == {str(person.id): 0}
        assert response.status_code == 200
        assert response.json() == {
            "notice": {"title": NOTICE_TITLE, "body": notice_body(person.display_name)}
        }
        assert await _markers_for(person) == [], "handing it out is not the same as it being seen"

    async def test_it_is_shown_once_and_seeing_it_writes_the_marker(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        person = await _committed_member(made, subscribed=False)

        with _renamed(person):
            shown = await client.get(NOTICE_URL, headers=_auth(person))
            seen = await client.post(f"{NOTICE_URL}/seen", headers=_auth(person))
            next_load = await client.get(NOTICE_URL, headers=_auth(person))

        assert shown.json()["notice"] is not None
        assert seen.status_code == 204
        assert next_load.status_code == 200
        assert next_load.json() == {"notice": None}
        [marker] = await _markers_for(person)
        assert marker.target_table == "profiles"
        assert marker.changes == {"new": person.display_name, "channel": "in_app"}
        assert marker.actor_id == person.id
        assert marker.actor_type == ActorType.player

    async def test_a_member_the_push_reached_is_not_shown_it(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        person = await _committed_member(made, subscribed=True)

        with _renamed(person), push_enabled() as push:
            await _run_the_boot_task()
            response = await client.get(NOTICE_URL, headers=_auth(person))

        assert push.call_count == 1
        assert response.json() == {"notice": None}
        assert len(await _markers_for(person)) == 1

    async def test_once_seen_in_the_app_push_stops_trying(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        # The other direction: a member who read the dialog and subscribes afterwards must
        # not then be pushed what they have already read.
        person = await _committed_member(made, subscribed=False)

        with _renamed(person):
            await client.post(f"{NOTICE_URL}/seen", headers=_auth(person))
            async with AsyncSessionLocal() as db:
                db.add(
                    PushSubscription(
                        user_id=person.id,
                        subscription={"endpoint": "https://example.test/after", "keys": {}},
                        is_active=True,
                    )
                )
                await db.commit()
            with push_enabled() as push:
                sent = await _run_the_boot_task()

        assert push.call_count == 0
        assert sent == {}
        assert len(await _markers_for(person)) == 1

    async def test_dismissing_it_twice_leaves_one_marker(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        # Two tabs, or a double tap before the dialog closes.
        person = await _committed_member(made)

        with _renamed(person):
            first = await client.post(f"{NOTICE_URL}/seen", headers=_auth(person))
            second = await client.post(f"{NOTICE_URL}/seen", headers=_auth(person))

        assert first.status_code == 204
        assert second.status_code == 204
        assert len(await _markers_for(person)) == 1

    async def test_everyone_else_is_shown_nothing_and_marked_nothing(
        self, client: AsyncClient, made: list[Profile]
    ) -> None:
        renamed = await _committed_member(made)
        everyone_else = await _committed_member(made)

        with _renamed(renamed):
            shown = await client.get(NOTICE_URL, headers=_auth(everyone_else))
            seen = await client.post(f"{NOTICE_URL}/seen", headers=_auth(everyone_else))

        assert shown.json() == {"notice": None}
        assert seen.status_code == 204
        assert await _markers_for(everyone_else) == []

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get(NOTICE_URL)).status_code == 401
        assert (await client.post(f"{NOTICE_URL}/seen")).status_code == 401
