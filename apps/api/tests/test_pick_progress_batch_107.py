"""Batch 107 — how close the coupon is, and the one moment it fills up.

Two things are being proved here, and they fail in different ways.

The **progress** half is arithmetic that reaches members: ``3/12`` is printed on a phone
and returned to the screen, so a denominator that quietly drops muted members would not
look like a bug, it would look like a smaller league. Its tests are mostly about who is
counted.

The **completion** half is a delivery guarantee. It happens once a round and it is the
moment the coupon becomes worth copying, so it must not be sent twice and must not be
lost. Its tests drive two real sessions against real row locks, because that is the only
place the guarantee actually lives.

Postgres-backed throughout. The service-level tests roll back; the ones that need two
concurrent transactions, and the HTTP flow at the end, commit as ``test_picks_flow`` does.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.gameweek_completion import GameweekCompletion
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile, UserRole
from src.services.betfair import SAMPLE_EPL_EVENT_ID, SAMPLE_SATURDAY, FakeBetfair
from src.services.gameweek import (
    fixtures_for,
    notification_targets,
    round_progress,
    sync_slate,
    window_for,
)
from src.services.notification_triggers import (
    COUPON_SECTION_HASH,
    announce_all_picked,
    coupon_section_url,
    notify_pick_made,
)
from src.services.round_completion import claim_pending_completion, record_completion

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


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(db: AsyncSession, name: str, *, active: bool = True) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}",
        pin_hash=hash_pin("8351"),
        role=UserRole.player,
        is_active=active,
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, owner: Profile, name: str = "2-1 Hibs") -> League:
    league = League(slug=f"b107-{uuid.uuid4().hex[:8]}", name=name, created_by=owner.id)
    db.add(league)
    await db.flush()
    return league


async def _join(
    db: AsyncSession,
    league: League,
    person: Profile,
    *,
    muted: bool = False,
    left: bool = False,
) -> LeagueMembership:
    membership = LeagueMembership(
        league_id=league.id,
        player_id=person.id,
        notification_muted=muted,
        deleted_at=_now() if left else None,
    )
    db.add(membership)
    await db.flush()
    return membership


async def _round(db: AsyncSession, league: League) -> Gameweek:
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=(_now() + timedelta(hours=4)).date(),
        status=GameweekStatus.open,
        locks_at_utc=_now() + timedelta(hours=4),
        picks_open_at_utc=None,
    )
    db.add(gameweek)
    await db.flush()
    return gameweek


async def _pick(db: AsyncSession, gameweek: Gameweek, person: Profile, runner: str) -> Pick:
    """One member's pick, on a fixture of its own.

    A fixture each rather than distinct outcomes on one: the counting never joins
    ``fixtures``, so the only thing the shared fixture would contribute is the land-grab's
    unique key, and a test about arithmetic should not have to route around it.
    """
    fixture = Fixture(
        provider_event_id=f"b107-{uuid.uuid4().hex[:12]}",
        home=runner,
        away="Opposition",
        kickoff_utc=_now() + timedelta(hours=6),
        competition="Test League",
        competition_id="test",
    )
    db.add(fixture)
    await db.flush()
    pick = Pick(
        league_id=gameweek.league_id,
        gameweek_id=gameweek.id,
        player_id=person.id,
        fixture_id=fixture.id,
        market=PickMarket.MATCH_ODDS,
        outcome=PickOutcome.HOME,
        runner_name=runner,
        odds_at_pick=Decimal("1.80"),
    )
    db.add(pick)
    await db.flush()
    return pick


# ── Who is counted ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_denominator_counts_members_not_recipients(session: AsyncSession) -> None:
    """A league of four is ``n/4`` even when two of them will never see the push.

    The row is explicit about this and it is the easiest thing in the batch to get wrong,
    because the query that finds *recipients* already existed and returning its length
    would have looked right. It is not right: a mute is a statement about a phone, and a
    member who has muted the league still owes a pick. Counting recipients would announce
    ``1/2`` to a league of four and — worse — call that round complete with two members
    yet to play.
    """
    owner = await _profile(session, "owner")
    muted = await _profile(session, "muted")
    unsubscribed = await _profile(session, "unsubscribed")
    picker = await _profile(session, "picker")
    league = await _league(session, owner)
    for person, is_muted in ((owner, False), (muted, True), (unsubscribed, False), (picker, False)):
        await _join(session, league, person, muted=is_muted)
    gameweek = await _round(session, league)
    await _pick(session, gameweek, picker, "Arsenal")

    progress = await round_progress(session, gameweek)
    assert (progress.picked_count, progress.member_count) == (1, 4)
    assert progress.all_picked is False

    # Nobody here has a push subscription, so every one of these four is "absent
    # subscription" — and the count is unmoved by that too. Delivery is a different
    # question, asked by a different query.
    assert len(await notification_targets(session, gameweek)) == 3


@pytest.mark.asyncio
async def test_members_who_left_or_were_deactivated_leave_the_count_entirely(
    session: AsyncSession,
) -> None:
    """And take their pick out of the numerator with them.

    Both directions matter. Leaving them in the denominator means a round that can never
    complete; leaving their *pick* in the numerator while they are out of the denominator
    means ``4/3``, and a round announced complete while somebody still owes a pick.
    """
    owner = await _profile(session, "owner")
    gone = await _profile(session, "gone")
    deactivated = await _profile(session, "deactivated", active=False)
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, gone, left=True)
    await _join(session, league, deactivated)
    gameweek = await _round(session, league)
    # Both of them picked before they went, and those rows are still there.
    await _pick(session, gameweek, gone, "Celtic")
    await _pick(session, gameweek, deactivated, "Hibs")

    progress = await round_progress(session, gameweek)
    assert (progress.picked_count, progress.member_count) == (0, 1)
    assert progress.all_picked is False


@pytest.mark.asyncio
async def test_an_empty_league_has_not_completed_its_round(session: AsyncSession) -> None:
    """``0 >= 0`` is true and would have been the wrong answer.

    A league whose last member left has not filled its coupon; it has nothing to fill.
    Announcing "all picks are in" to nobody is harmless, but the same flag is what the
    client draws a completion state from, and what stops the ordinary alert being sent.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner)
    gameweek = await _round(session, league)

    progress = await round_progress(session, gameweek)
    assert (progress.picked_count, progress.member_count) == (0, 0)
    assert progress.all_picked is False


@pytest.mark.asyncio
async def test_the_last_pick_fills_the_coupon(session: AsyncSession) -> None:
    owner = await _profile(session, "owner")
    other = await _profile(session, "other")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, other)
    gameweek = await _round(session, league)

    await _pick(session, gameweek, owner, "Arsenal")
    assert (await round_progress(session, gameweek)).all_picked is False
    await _pick(session, gameweek, other, "Chelsea")
    assert (await round_progress(session, gameweek)).all_picked is True


# ── What the two alerts say, and where they land ───────────────────────────────


@pytest.mark.asyncio
async def test_the_ordinary_alert_lands_on_the_round_itself(session: AsyncSession) -> None:
    """The exact url, which is the half of the copy nobody reads in review.

    Unchanged by this batch and asserted here anyway: an ordinary pick continues to the
    league's current-round position, and only the completion deep-links the copy section.
    A pick alert that opened the coupon fold would be the batch's easiest accidental
    regression, and it would take a member somewhere they cannot act.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, picker)
    gameweek = await _round(session, league)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await notify_pick_made(
            session,
            gameweek,
            picker_id=picker.id,
            picker_name="Dave",
            selection="Arsenal",
            odds=Decimal("1.80"),
            moved=False,
            progress=await round_progress(session, gameweek),
        )

    call = send.await_args_list[0]
    assert call.kwargs["data"]["url"] == f"/leagues/{league.slug}/predictions"
    assert COUPON_SECTION_HASH not in call.kwargs["data"]["url"]
    assert call.kwargs["data"]["type"] == "pick_made"


@pytest.mark.asyncio
async def test_the_completion_alert_names_the_final_picker_and_opens_the_copy_section(
    session: AsyncSession,
) -> None:
    """The whole point of the event, in one assertion each.

    The body is the ordinary pick line with a clause on the end rather than a bare "all
    picks are in", because the last member's name is the one piece of the round nobody
    else could see coming — a message that dropped it would be less informative than the
    alert it replaces.

    The url names the round explicitly. "All picks are in" is worth reading an hour later,
    by which time the league's *current* round may be a different one, and a link that
    resolved to whatever is current would open the wrong coupon.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, picker)
    gameweek = await _round(session, league)
    await record_completion(
        session,
        gameweek,
        picker_id=picker.id,
        picker_name="Dave",
        selection="Arsenal",
        odds=Decimal("1.80"),
        member_count=12,
    )

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        told = await announce_all_picked(session, gameweek)

    assert told == 2
    call = send.await_args_list[0]
    assert call.args[2] == league.name
    assert call.args[3] == "Dave picked Arsenal @ 1.80 · 12/12 picked — all picks are in"
    assert call.kwargs["data"]["url"] == (
        f"/leagues/{league.slug}/predictions?gw={gameweek.id}#coupon"
    )
    assert call.kwargs["data"]["url"] == coupon_section_url(league.slug, gameweek.id)
    assert call.kwargs["data"]["type"] == "all_picked"
    # A tag of its own, so the completion cannot replace an ordinary pick alert in the
    # tray or be replaced by one — they collapse against their own kind only.
    assert call.kwargs["tag"] == f"all-picked-{league.id}-{gameweek.id}"


@pytest.mark.asyncio
async def test_the_completion_reaches_the_final_picker_and_skips_the_muted(
    session: AsyncSession,
) -> None:
    """The one alert that does tell somebody what they just did.

    Every other pick trigger excludes the picker, because telling a member their own news
    is noise. This is the exception, and it is the reason the event exists: the member who
    fills the coupon is the one person for whom something changed — the round is now worth
    copying, and they are holding it.

    The mute still applies. Being counted in ``12/12`` and being sent a push are separate
    decisions, and this proves the second one still honours the opt-out.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    quiet = await _profile(session, "quiet")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, picker)
    await _join(session, league, quiet, muted=True)
    gameweek = await _round(session, league)
    await record_completion(
        session,
        gameweek,
        picker_id=picker.id,
        picker_name="Dave",
        selection="Arsenal",
        odds=Decimal("1.80"),
        member_count=3,
    )

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await announce_all_picked(session, gameweek)

    recipients = {call.args[1] for call in send.await_args_list}
    assert picker.id in recipients
    assert recipients == {owner.id, picker.id}


# ── Exactly one event, and it is not lost ──────────────────────────────────────


@pytest.mark.asyncio
async def test_a_round_already_announced_is_never_announced_again(
    session: AsyncSession,
) -> None:
    """Two guards, and the test needs both to pass to mean anything.

    ``record_completion`` refusing the second insert is what stops a *second event*; the
    claim finding nothing undelivered is what stops a *second push* for the one event.
    A change of pick after the coupon fills goes down both paths on every submission.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, picker)
    gameweek = await _round(session, league)

    first = await record_completion(
        session,
        gameweek,
        picker_id=picker.id,
        picker_name="Dave",
        selection="Arsenal",
        odds=Decimal("1.80"),
        member_count=2,
    )
    second = await record_completion(
        session,
        gameweek,
        picker_id=owner.id,
        picker_name="Someone else",
        selection="Chelsea",
        odds=Decimal("3.40"),
        member_count=2,
    )
    assert (first, second) == (True, False)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ):
        assert await announce_all_picked(session, gameweek) == 2
    # Delivered — so a later submission on the same round finds nothing to claim.
    assert await announce_all_picked(session, gameweek) is None

    rows = (
        (
            await session.execute(
                select(GameweekCompletion).where(GameweekCompletion.gameweek_id == gameweek.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    # The first transition's details, not the second attempt's.
    assert rows[0].final_picker_name == "Dave"


@pytest.mark.asyncio
async def test_a_fan_out_that_fails_leaves_the_event_to_be_retried(
    session: AsyncSession,
) -> None:
    """The reason this event has a row at all.

    Delivery is blocking webpush calls on somebody's request path and can fail for reasons
    that have nothing to do with this league. A pick alert lost that way costs nothing —
    the screen already says it and another pick is along in a minute. The completion
    happens once a round, so a failure has to leave something behind that the next
    submission picks up.
    """
    owner = await _profile(session, "owner")
    picker = await _profile(session, "picker")
    league = await _league(session, owner)
    await _join(session, league, owner)
    await _join(session, league, picker)
    gameweek = await _round(session, league)
    await record_completion(
        session,
        gameweek,
        picker_id=picker.id,
        picker_name="Dave",
        selection="Arsenal",
        odds=Decimal("1.80"),
        member_count=2,
    )

    with patch(
        "src.services.notification_triggers.send_notification",
        new=AsyncMock(side_effect=RuntimeError("push gateway down")),
    ):
        with pytest.raises(RuntimeError):
            await announce_all_picked(session, gameweek)

    stored = (
        await session.execute(
            select(GameweekCompletion).where(GameweekCompletion.gameweek_id == gameweek.id)
        )
    ).scalar_one()
    assert stored.delivered_at is None

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ):
        assert await announce_all_picked(session, gameweek) == 2

    # Flushed rather than refreshed: the service stamps the row and leaves the commit to
    # its caller, which is what lets a failed fan-out discard the claim. Reading it back
    # through the open transaction proves the stamp reaches the database all the same.
    await session.flush()
    assert (
        await session.execute(
            select(GameweekCompletion.delivered_at).where(GameweekCompletion.id == stored.id)
        )
    ).scalar_one() is not None


# ── The two-transaction cases ──────────────────────────────────────────────────
#
# These commit, because a row lock between two sessions is the only thing being tested and
# an uncommitted seed is invisible to the second one. They follow `test_picks_flow` in
# leaving their rows behind; every league and profile here is uniquely named.


async def _committed_round(members: int) -> tuple[League, Gameweek, list[Profile]]:
    async with AsyncSessionLocal() as db:
        people = [await _profile(db, f"p{i}") for i in range(members)]
        league = await _league(db, people[0])
        for person in people:
            await _join(db, league, person)
        gameweek = await _round(db, league)
        await db.commit()
        return league, gameweek, people


@pytest.mark.asyncio
async def test_two_simultaneous_final_picks_record_one_completion() -> None:
    """The race the batch was written around, run for real against the unique key.

    The last two members claim seconds apart. Both commits land, and both requests then
    read a full coupon — so "did I complete it?" cannot be answered from that read: for
    both of them the honest answer is yes. Deciding it in the application would fan the
    completion out twice.

    ``ON CONFLICT DO NOTHING`` moves the decision to the database. One insert lands and
    one does not, whatever order the two interleave in, and the loser's submission goes on
    to send its ordinary alert instead.
    """
    _, gameweek, people = await _committed_round(2)

    async def _attempt(person: Profile) -> bool:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Gameweek, gameweek.id)
            assert fresh is not None
            recorded = await record_completion(
                db,
                fresh,
                picker_id=person.id,
                picker_name=person.display_name,
                selection="Arsenal",
                odds=Decimal("1.80"),
                member_count=2,
            )
            await db.commit()
            return recorded

    outcomes = await asyncio.gather(_attempt(people[0]), _attempt(people[1]))
    assert sorted(outcomes) == [False, True]

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(func.count())
            .select_from(GameweekCompletion)
            .where(GameweekCompletion.gameweek_id == gameweek.id)
        )
        assert rows.scalar_one() == 1


@pytest.mark.asyncio
async def test_a_second_request_does_not_queue_behind_a_fan_out_in_flight() -> None:
    """``SKIP LOCKED``, and why it is not ``FOR UPDATE``.

    While one request is delivering, another submission on the same round arrives. A plain
    ``FOR UPDATE`` would make that member wait out somebody else's webpush round-trips
    before their own pick response returned — to then find the work already done and skip
    it anyway. Skipping immediately reaches the same state sooner, and the only thing that
    must not happen either way is a second fan-out.
    """
    _, gameweek, people = await _committed_round(2)
    async with AsyncSessionLocal() as db:
        fresh = await db.get(Gameweek, gameweek.id)
        assert fresh is not None
        await record_completion(
            db,
            fresh,
            picker_id=people[0].id,
            picker_name="Dave",
            selection="Arsenal",
            odds=Decimal("1.80"),
            member_count=2,
        )
        await db.commit()

    async with AsyncSessionLocal() as holder, AsyncSessionLocal() as other:
        held = await claim_pending_completion(holder, gameweek)
        assert held is not None
        assert await claim_pending_completion(other, gameweek) is None
        await holder.rollback()

    # Rolled back rather than delivered, so it is still there for the next submission.
    async with AsyncSessionLocal() as db:
        assert await claim_pending_completion(db, gameweek) is not None


# ── Through the real endpoint ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client_and_fake() -> AsyncIterator[tuple[AsyncClient, FakeBetfair]]:
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    app.dependency_overrides[get_optional_odds_provider] = lambda: fake
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


async def _seeded_round(fake: FakeBetfair, members: int) -> tuple[League, Gameweek, list[Profile]]:
    """A committed league of ``members`` playing the canned card, open for picks."""
    async with AsyncSessionLocal() as db:
        people = [await _profile(db, f"m{i}") for i in range(members)]
        league = await _league(db, people[0])
        for person in people:
            await _join(db, league, person)
        await db.commit()
        slate = await fake.fetch_slate(window_for(league), SAMPLE_SATURDAY)
        gameweek = await sync_slate(db, league, slate)
        assert gameweek is not None
        gameweek.status = GameweekStatus.open
        gameweek.locks_at_utc = _now() + timedelta(hours=2)
        await db.commit()
        await db.refresh(gameweek)
        for person in people:
            await db.refresh(person)
        await db.refresh(league)
        return league, gameweek, people


async def _epl_fixture_id(gameweek: Gameweek) -> str:
    async with AsyncSessionLocal() as db:
        fixtures = await fixtures_for(db, gameweek.id)
        return next(str(f.id) for f in fixtures if f.provider_event_id == SAMPLE_EPL_EVENT_ID)


async def _submit(
    client: AsyncClient, league: League, person: Profile, fixture_id: str, outcome: str
) -> Response:
    return await client.post(
        f"/api/v1/leagues/{league.slug}/picks",
        json={"fixture_id": fixture_id, "market": "MATCH_ODDS", "outcome": outcome},
        headers=_auth(person),
    )


@pytest.mark.asyncio
async def test_the_pick_response_carries_the_rounds_progress(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """So the client can draw the completion state on the same paint as the pick.

    Without these three the only way to know the round just filled is to refetch — a
    request racing the write that caused it, made by the one member the push cannot be
    relied on to reach in time, because they are holding the phone.
    """
    client, fake = client_and_fake
    league, gameweek, (alice, bob, carol) = await _seeded_round(fake, 3)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ):
        first = await _submit(client, league, alice, fixture_id, "HOME")
        second = await _submit(client, league, bob, fixture_id, "AWAY")
        third = await _submit(client, league, carol, fixture_id, "DRAW")

    assert first.status_code == 201, first.text
    assert (first.json()["picked_count"], first.json()["member_count"]) == (1, 3)
    assert first.json()["all_picked"] is False
    assert (second.json()["picked_count"], second.json()["member_count"]) == (2, 3)
    assert second.json()["all_picked"] is False
    assert (third.json()["picked_count"], third.json()["member_count"]) == (3, 3)
    assert third.json()["all_picked"] is True


@pytest.mark.asyncio
async def test_completing_the_round_replaces_the_ordinary_alert(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """One event reaches the tray, not two.

    The row is explicit that the completion *replaces* the ordinary pick alert. Sending
    both would put two notifications about one action on every member's phone, and the
    ordinary one would be the less useful of the pair.
    """
    client, fake = client_and_fake
    league, gameweek, (alice, bob) = await _seeded_round(fake, 2)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await _submit(client, league, alice, fixture_id, "HOME")
        send.reset_mock()
        final = await _submit(client, league, bob, fixture_id, "AWAY")

    assert final.status_code == 201, final.text
    kinds = {call.kwargs["data"]["type"] for call in send.await_args_list}
    assert kinds == {"all_picked"}
    # Everyone, the final picker included.
    assert {call.args[1] for call in send.await_args_list} == {alice.id, bob.id}
    assert send.await_args_list[0].args[3].endswith("· 2/2 picked — all picks are in")
    assert send.await_args_list[0].kwargs["data"]["url"] == (
        f"/leagues/{league.slug}/predictions?gw={gameweek.id}#coupon"
    )


@pytest.mark.asyncio
async def test_a_pick_changed_after_the_coupon_filled_is_an_ordinary_alert(
    client_and_fake: tuple[AsyncClient, FakeBetfair],
) -> None:
    """A full coupon is a state, not a transition, and only the transition is the event.

    The member moving their pick is making an ordinary pick into a round that happens to
    be complete, so the league gets the ordinary alert — at ``2/2``, which is true. What
    it must not get is the completion a second time, and the round must not gain a second
    completion row.
    """
    client, fake = client_and_fake
    league, gameweek, (alice, bob) = await _seeded_round(fake, 2)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await _submit(client, league, alice, fixture_id, "HOME")
        await _submit(client, league, bob, fixture_id, "AWAY")
        send.reset_mock()
        moved = await _submit(client, league, bob, fixture_id, "DRAW")

    assert moved.status_code == 201, moved.text
    assert moved.json()["all_picked"] is True
    assert [call.kwargs["data"]["type"] for call in send.await_args_list] == ["pick_changed"]
    assert {call.args[1] for call in send.await_args_list} == {alice.id}
    assert "moved to" in send.await_args_list[0].args[3]
    assert send.await_args_list[0].args[3].endswith("· 2/2 picked")

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(GameweekCompletion).where(GameweekCompletion.gameweek_id == gameweek.id)
        )
        completions = rows.scalars().all()
    assert len(completions) == 1
    assert completions[0].final_picker_id == bob.id
    assert completions[0].delivered_at is not None
