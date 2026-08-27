"""Batch 76 — the three triggers, and the per-league mute they all sit on.

The mute is the load-bearing part. ``league_memberships.notification_muted`` has existed
since Batch 32 and until now exactly one query honoured it, so a member who muted a league
still got its postponement alerts. Batch 76 stacks two high-volume triggers on top of
``send_notification`` — twelve members each notifying eleven others is 132 sends a round —
and the owner has declined a separate opt-out, which makes this column a member's only
recourse. If it does not work, nothing else here is safe to ship.

Postgres-backed; each test rolls back.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import PushSubscription
from src.models.profile import Profile, UserRole
from src.services.gameweek import gameweeks_due_a_reminder, notification_targets
from src.services.notification_triggers import (
    notify_member_joined,
    notify_pick_made,
    notify_picks_open,
)
from src.services.push_notification_service import send_notification

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


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _profile(db: AsyncSession, name: str, *, role: UserRole = UserRole.player) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=role,
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, owner: Profile, name: str) -> League:
    league = League(slug=f"{name}-{uuid.uuid4().hex[:8]}", name=name, created_by=owner.id)
    db.add(league)
    await db.flush()
    return league


async def _join(db: AsyncSession, league: League, person: Profile, *, muted: bool = False) -> None:
    db.add(
        LeagueMembership(
            league_id=league.id,
            player_id=person.id,
            notification_muted=muted,
        )
    )
    await db.flush()


async def _round(db: AsyncSession, league: League, *, locks_in: timedelta) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=(_now() + locks_in).date(),
        status=GameweekStatus.open,
        locks_at_utc=_now() + locks_in,
        picks_open_at_utc=None,
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


# ── The mute gate itself ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_muted_league_is_not_delivered_and_another_league_still_is(
    session: AsyncSession,
) -> None:
    """The row's first requirement, and the one the rest depends on.

    Both halves matter. Suppressing the muted league proves the gate fires; delivering the
    other one proves it is scoped to a league rather than to the member — muting one league
    must not silence every league they play.

    Driven through the real ``send_notification`` with VAPID configured and only the
    blocking push patched, because the gate lives *inside* that function. Asserting a 0
    return with VAPID unset would pass on the early bail-out and prove nothing.
    """
    owner = await _profile(session, "owner")
    member = await _profile(session, "member")
    muted_league = await _league(session, owner, "Muted")
    loud_league = await _league(session, owner, "Loud")
    await _join(session, muted_league, member, muted=True)
    await _join(session, loud_league, member, muted=False)
    session.add(
        PushSubscription(
            user_id=member.id,
            subscription={"endpoint": "https://example.test/x", "keys": {}},
            is_active=True,
        )
    )
    await session.flush()

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync") as push,
    ):
        suppressed = await send_notification(
            session, member.id, "T", "B", league_id=muted_league.id
        )
        assert suppressed == 0
        assert push.call_count == 0

        delivered = await send_notification(session, member.id, "T", "B", league_id=loud_league.id)
        assert delivered == 1
        assert push.call_count == 1


@pytest.mark.asyncio
async def test_a_missing_membership_does_not_suppress(session: AsyncSession) -> None:
    """The gate fires on an explicit mute, never on an absent row.

    Deliberate: this keeps Batch 76 purely additive. A member who left a league mid-round
    should still be told their pick was returned, and no message that goes out today stops
    going out because a membership could not be found.
    """
    owner = await _profile(session, "owner")
    stranger = await _profile(session, "stranger")
    league = await _league(session, owner, "Elsewhere")
    session.add(
        PushSubscription(
            user_id=stranger.id,
            subscription={"endpoint": "https://example.test/y", "keys": {}},
            is_active=True,
        )
    )
    await session.flush()

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync"),
    ):
        assert await send_notification(session, stranger.id, "T", "B", league_id=league.id) == 1


@pytest.mark.asyncio
async def test_a_muted_member_is_never_targeted(session: AsyncSession) -> None:
    """The cheaper half: muted members are filtered out in SQL before any send.

    Both layers are wanted. This one keeps the triggers' return counts honest about who
    was targeted; the gate above is the authority that catches anything this misses.
    """
    owner = await _profile(session, "owner")
    quiet = await _profile(session, "quiet")
    loud = await _profile(session, "loud")
    league = await _league(session, owner, "League")
    await _join(session, league, quiet, muted=True)
    await _join(session, league, loud, muted=False)
    gameweek = await _round(session, league, locks_in=timedelta(hours=5))

    targets = await notification_targets(session, gameweek)
    assert {t.player_id for t in targets} == {str(loud.id)}


# ── Picks open ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opening_a_round_notifies_that_league_and_nobody_else(
    session: AsyncSession,
) -> None:
    owner = await _profile(session, "owner")
    ours = await _profile(session, "ours")
    theirs = await _profile(session, "theirs")
    league = await _league(session, owner, "Ours")
    other = await _league(session, owner, "Theirs")
    await _join(session, league, ours)
    await _join(session, other, theirs)
    gameweek = await _round(session, league, locks_in=timedelta(hours=6))

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        told = await notify_picks_open(session, gameweek)

    assert told == 1
    recipients = {call.args[1] for call in send.await_args_list}
    assert recipients == {ours.id}
    # The gate only reaches this trigger if the trigger names its league. Asserted here
    # rather than trusted, because a missing kwarg fails silently — the message still
    # sends, just without the mute ever being consulted.
    assert send.await_args_list[0].kwargs["league_id"] == league.id


# ── The reminder's window ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_reminder_selects_three_hours_out_and_skips_three_days(
    session: AsyncSession,
) -> None:
    """One reminder, three hours before the lock — not one a day until it locks.

    The three-day round is the case that produced the complaint: open from discovery, so
    the old "every open round with a future lock" predicate nudged for it every day.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner, "League")
    soon = await _round(session, league, locks_in=timedelta(hours=3))
    await _round(session, league, locks_in=timedelta(days=3))

    due = await gameweeks_due_a_reminder(session, _now())
    assert [g.id for g in due] == [soon.id]


@pytest.mark.asyncio
async def test_the_reminder_skips_a_round_whose_opening_has_not_arrived(
    session: AsyncSession,
) -> None:
    """Nagging for a pick nobody may make yet is worse than not reminding at all.

    The eligibility half mirrors ``pick_refusal`` rather than testing ``status``, which is
    Batch 73's lesson applied here: with a window this narrow, a round mislabelled for an
    hour would not have its reminder delayed, it would lose it.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner, "League")
    gated = await _round(session, league, locks_in=timedelta(hours=3))
    gated.picks_open_at_utc = _now() + timedelta(hours=1)
    await session.flush()

    assert await gameweeks_due_a_reminder(session, _now()) == []


# ── Somebody picked ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_pick_notifies_the_others_and_never_the_picker(session: AsyncSession) -> None:
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    watcher = await _profile(session, "watcher")
    league = await _league(session, owner, "2-1 Hibs")
    await _join(session, league, picker)
    await _join(session, league, watcher)
    gameweek = await _round(session, league, locks_in=timedelta(hours=4))

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        told = await notify_pick_made(
            session,
            gameweek,
            picker_id=picker.id,
            picker_name="Dave",
            league_name=league.name,
            selection="Arsenal to win",
            odds=Decimal("1.80"),
            moved=False,
        )

    assert told == 1
    recipients = {call.args[1] for call in send.await_args_list}
    assert recipients == {watcher.id}
    assert picker.id not in recipients
    # As above: without this the highest-volume trigger in the product would ignore the
    # only opt-out a member has against it.
    assert send.await_args_list[0].kwargs["league_id"] == league.id


@pytest.mark.asyncio
async def test_a_claim_and_a_move_read_differently(session: AsyncSession) -> None:
    """A move is the more useful event: it frees the old selection back into the grab.

    ``submit_pick`` updates in place, so the trigger can only tell them apart from a flag
    captured before ``_apply_selection`` overwrites the row.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    watcher = await _profile(session, "watcher")
    league = await _league(session, owner, "2-1 Hibs")
    await _join(session, league, picker)
    await _join(session, league, watcher)
    gameweek = await _round(session, league, locks_in=timedelta(hours=4))

    async def _copy(*, moved: bool) -> tuple[str, str]:
        with patch(
            "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
        ) as send:
            await notify_pick_made(
                session,
                gameweek,
                picker_id=picker.id,
                picker_name="Dave",
                league_name=league.name,
                selection="Celtic",
                odds=Decimal("2.10"),
                moved=moved,
            )
        call = send.await_args_list[0]
        return call.args[2], call.args[3]

    claim_title, claim_body = await _copy(moved=False)
    move_title, move_body = await _copy(moved=True)

    assert "took" in claim_body and "moved to" not in claim_body
    assert "moved to" in move_body and "took" not in move_body
    assert claim_title != move_title


@pytest.mark.asyncio
async def test_the_alert_quotes_the_frozen_price(session: AsyncSession) -> None:
    """``odds_at_pick``, never a live quote.

    A winning pick scores ``round(odds × 10)`` against the stored number, so an alert
    quoting anything else quotes a score nobody gets. The price is passed in rather than
    re-read for exactly that reason, and this pins the formatting too — "1.80", not "1.8".
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    watcher = await _profile(session, "watcher")
    league = await _league(session, owner, "2-1 Hibs")
    await _join(session, league, picker)
    await _join(session, league, watcher)
    gameweek = await _round(session, league, locks_in=timedelta(hours=4))

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await notify_pick_made(
            session,
            gameweek,
            picker_id=picker.id,
            picker_name="Dave",
            league_name="2-1 Hibs",
            selection="Arsenal to win",
            odds=Decimal("1.80"),
            moved=False,
        )

    body = send.await_args_list[0].args[3]
    assert "Dave took Arsenal to win at 1.80 in 2-1 Hibs." == body


@pytest.mark.asyncio
async def test_the_pick_alert_collapses_per_league_and_round(session: AsyncSession) -> None:
    """The tag is load-bearing, not tidiness.

    Twelve members each notifying eleven others is 132 sends a round, and the owner chose
    that over a digest. One live pick alert in the tray is what makes it survivable.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    watcher = await _profile(session, "watcher")
    league = await _league(session, owner, "2-1 Hibs")
    await _join(session, league, picker)
    await _join(session, league, watcher)
    gameweek = await _round(session, league, locks_in=timedelta(hours=4))

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await notify_pick_made(
            session,
            gameweek,
            picker_id=picker.id,
            picker_name="Dave",
            league_name=league.name,
            selection="Arsenal to win",
            odds=Decimal("1.80"),
            moved=False,
        )

    assert send.await_args_list[0].kwargs["tag"] == f"pick-made-{league.id}-{gameweek.id}"


# ── Batch 85: the fourth trigger, which Batch 76 missed ────────────────────────


@pytest.mark.asyncio
async def test_a_muted_league_suppresses_its_member_joined_alert(session: AsyncSession) -> None:
    """The trigger Batch 76 left behind, held to the same rule as the other three.

    ``notify_member_joined`` called ``send_notification`` with no ``league_id``, so the
    gate had nothing to check and a site admin who had muted a league still got its
    "New member" push — while the message names that league in both its title and its
    body. Two admins here, one muted and one not, because suppressing everything would
    pass just as well as suppressing the right one.
    """
    owner = await _profile(session, "owner")
    quiet_admin = await _profile(session, "quiet-admin", role=UserRole.admin)
    loud_admin = await _profile(session, "loud-admin", role=UserRole.admin)
    league = await _league(session, owner, "Hibs")
    await _join(session, league, quiet_admin, muted=True)
    await _join(session, league, loud_admin, muted=False)
    for admin in (quiet_admin, loud_admin):
        session.add(
            PushSubscription(
                user_id=admin.id,
                subscription={"endpoint": "https://example.test/x", "keys": {}},
                is_active=True,
            )
        )
    await session.flush()

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync") as push,
    ):
        await notify_member_joined(session, "Newcomer", league.name, league.id)

    assert push.call_count == 1, "only the admin who has not muted this league is told"


@pytest.mark.asyncio
async def test_member_joined_passes_the_league_through(session: AsyncSession) -> None:
    """The mechanism, so a failure says *why* rather than only that nothing arrived.

    ``league_id`` is a required parameter rather than a defaulted one, so a future call
    site cannot reintroduce the omission by leaving it off — but nothing stops it being
    dropped between here and ``send_notification``, which is what this pins.
    """
    owner = await _profile(session, "owner")
    admin = await _profile(session, "admin", role=UserRole.admin)
    league = await _league(session, owner, "Hibs")
    await _join(session, league, admin)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await notify_member_joined(session, "Newcomer", league.name, league.id)

    assert send.await_args_list[0].kwargs["league_id"] == league.id
