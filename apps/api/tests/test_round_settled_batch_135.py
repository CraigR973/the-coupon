"""Batch 135 — a member is told when their round settles, and what their pick did.

None of the existing triggers fired when a round settled, so the weekly loop's payoff was
the one moment the product never mentioned: a member found out by opening the app.

What these hold to, from the row:

* settling a round tells each eligible member once, naming *their own* result;
* a muted league tells nobody — the gate every league trigger already sits on;
* settling again tells nobody again.

Both ways a round settles announce it — the scheduled sweep and an admin's hand-entered
results — because a round an admin settled is no less settled. And an announcement that
fails leaves the settlement standing: the points have already committed by then.

Postgres-backed. The sweep tests lend the job their own session with ``commit`` reduced to
a flush, so they roll back; the hand-entry tests drive the HTTP endpoint, which commits,
like ``test_admin_operations``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import scheduler
from src.auth import create_access_token, hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import PushSubscription
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.services.admin_ops import settlement_from_score, voided_settlement
from src.services.notification_triggers import round_name
from src.services.odds_provider import EventSettlement

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

SEND = "src.services.notification_triggers.send_notification"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _profile(db: AsyncSession, name: str, *, role: UserRole = UserRole.player) -> Profile:
    person = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}", pin_hash=hash_pin("8351"), role=role
    )
    db.add(person)
    await db.flush()
    return person


async def _league(db: AsyncSession, owner: Profile, name: str) -> League:
    league = League(slug=f"b135-{uuid.uuid4().hex[:8]}", name=name, created_by=owner.id)
    db.add(league)
    await db.flush()
    return league


async def _join(db: AsyncSession, league: League, person: Profile, *, muted: bool = False) -> None:
    db.add(LeagueMembership(league_id=league.id, player_id=person.id, notification_muted=muted))
    await db.flush()


async def _fixture(db: AsyncSession, home: str, away: str) -> Fixture:
    fixture = Fixture(
        provider_event_id=f"b135-{uuid.uuid4().hex[:12]}",
        home=home,
        away=away,
        kickoff_utc=_now() - timedelta(hours=3),
        competition="Scottish League Two",
        competition_id="b135",
    )
    db.add(fixture)
    await db.flush()
    return fixture


async def _locked_round(db: AsyncSession, league: League, fixtures: Sequence[Fixture]) -> Gameweek:
    """A round past its deadline with nothing settled — what every sweep starts from."""
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=date(2027, 3, 6),
        number=7,
        status=GameweekStatus.locked,
        locks_at_utc=_now() - timedelta(hours=4),
    )
    db.add(gameweek)
    await db.flush()
    db.add_all(GameweekFixture(gameweek_id=gameweek.id, fixture_id=f.id) for f in fixtures)
    await db.flush()
    return gameweek


async def _pick(
    db: AsyncSession,
    gameweek: Gameweek,
    fixture: Fixture,
    person: Profile,
    outcome: PickOutcome,
    odds: str,
) -> None:
    db.add(
        Pick(
            league_id=gameweek.league_id,
            gameweek_id=gameweek.id,
            fixture_id=fixture.id,
            player_id=person.id,
            market=PickMarket.MATCH_ODDS,
            outcome=outcome,
            runner_name=fixture.home if outcome is PickOutcome.HOME else fixture.away,
            odds_at_pick=Decimal(odds),
        )
    )
    await db.flush()


class _Lent:
    """The test's session, lent to a job that expects to open and commit its own."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Results:
    """A provider that knows the results it is handed, and nothing else yet."""

    def __init__(self, *settlements: EventSettlement) -> None:
        self._by_event = {s.provider_event_id: s for s in settlements}

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return [self._by_event[e] for e in event_ids if e in self._by_event]


async def _sweep(session: AsyncSession, leagues: Sequence[League], provider: _Results) -> bool:
    """Run the real settle sweep over this test's rounds only, on this test's session.

    Other tests commit rounds of their own, and the real selection would hand those to
    the job as well. Filtering the real ``settleable_gameweeks`` rather than replacing it
    keeps its rule — a settled round is never selected again — inside the test.
    """
    ours = {league.id for league in leagues}
    select_due = scheduler.settleable_gameweeks

    async def due(db: AsyncSession, now: datetime) -> list[Gameweek]:
        return [g for g in await select_due(db, now) if g.league_id in ours]

    with (
        patch.object(session, "commit", session.flush),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Lent(session)),
        patch("src.scheduler.odds_session.acquire", new=AsyncMock(return_value=provider)),
        patch("src.scheduler.settleable_gameweeks", new=due),
    ):
        return await scheduler.run_settle_gameweeks()


def _recorder(sent: list[dict[str, Any]]) -> Callable[..., Coroutine[Any, Any, int]]:
    """Stands in for ``send_notification`` and writes down what it was asked to deliver."""

    async def send(
        db: AsyncSession,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        tag: str | None = None,
        timezone_name: str = "UTC",
        now_utc: datetime | None = None,
        league_id: uuid.UUID | None = None,
    ) -> int:
        sent.append(
            {
                "user_id": user_id,
                "title": title,
                "body": body,
                "data": data or {},
                "tag": tag,
                "league_id": league_id,
            }
        )
        return 1

    return send


# ── The scheduled sweep ────────────────────────────────────────────────────────


async def test_settling_a_round_tells_each_member_their_own_result(session: AsyncSession) -> None:
    """One message per active, unmuted member, each naming what *their* pick did.

    Four members, four different answers: a winner, a loser, a pick on a match that was
    called off, and a member who never picked. The last is told too — the table they sit
    in has moved — and is told plainly that they had nothing on it.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner, "Friday League")
    winner = await _profile(session, "winner")
    loser = await _profile(session, "loser")
    called_off = await _profile(session, "calledoff")
    idle = await _profile(session, "idle")
    for person in (winner, loser, called_off, idle):
        await _join(session, league, person)
    forfar = await _fixture(session, "Forfar Athletic", "Brechin City")
    arbroath = await _fixture(session, "Arbroath", "Montrose")
    gameweek = await _locked_round(session, league, [forfar, arbroath])
    await _pick(session, gameweek, forfar, winner, PickOutcome.HOME, "2.50")
    await _pick(session, gameweek, forfar, loser, PickOutcome.AWAY, "3.10")
    await _pick(session, gameweek, arbroath, called_off, PickOutcome.HOME, "1.95")

    sent: list[dict[str, Any]] = []
    with patch(SEND, new=_recorder(sent)):
        ok = await _sweep(
            session,
            [league],
            _Results(
                settlement_from_score(forfar.provider_event_id, 2, 1),
                voided_settlement(arbroath.provider_event_id),
            ),
        )

    assert ok is True
    assert gameweek.status is GameweekStatus.settled
    by_member = {message["user_id"]: message for message in sent}
    assert len(sent) == len(by_member) == 4, f"{len(sent)} messages for 4 members"

    assert by_member[winner.id]["body"].endswith(
        "Your pick, Forfar Athletic (v Brechin City) @ 2.50, won 25 points."
    )
    assert by_member[loser.id]["body"].endswith(
        "Your pick, Brechin City (at Forfar Athletic) @ 3.10, lost."
    )
    assert by_member[called_off.id]["body"].endswith(
        "Your pick, Arbroath (v Montrose), was void — no points."
    )
    assert by_member[idle.id]["body"].endswith("You had no pick this round.")

    for message in sent:
        assert message["body"].startswith("Gameweek ")
        assert " has settled. " in message["body"]
        assert message["title"] == league.name
        # The gate only reaches a trigger that names its league — asserted, not trusted,
        # because a missing keyword fails silently: the message still goes, unmuted.
        assert message["league_id"] == league.id
        assert message["tag"] == f"round-settled-{league.id}-{gameweek.id}"
        assert message["data"] == {
            "type": "round_settled",
            "league_id": str(league.id),
            "url": f"/leagues/{league.slug}/predictions?gw={gameweek.id}#coupon",
        }


async def test_a_muted_league_is_told_nothing(session: AsyncSession) -> None:
    """Through the real ``send_notification``, with only the blocking push patched.

    Two leagues settle in the same sweep off the same match. Every member of the muted one
    has a device and a pick and hears nothing; the member of the other one hears, which is
    what shows the silence is the mute and not a trigger that never fires.
    """
    owner = await _profile(session, "owner")
    muted_league = await _league(session, owner, "Muted")
    loud_league = await _league(session, owner, "Loud")
    quiet_home = await _profile(session, "quiethome")
    quiet_away = await _profile(session, "quietaway")
    loud = await _profile(session, "loud")
    await _join(session, muted_league, quiet_home, muted=True)
    await _join(session, muted_league, quiet_away, muted=True)
    await _join(session, loud_league, loud)
    for person in (quiet_home, quiet_away, loud):
        session.add(
            PushSubscription(
                user_id=person.id,
                subscription={"endpoint": f"https://push.example.test/{person.id}", "keys": {}},
                is_active=True,
            )
        )
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City")
    muted_round = await _locked_round(session, muted_league, [fixture])
    loud_round = await _locked_round(session, loud_league, [fixture])
    await _pick(session, muted_round, fixture, quiet_home, PickOutcome.HOME, "2.00")
    await _pick(session, muted_round, fixture, quiet_away, PickOutcome.AWAY, "3.40")
    await _pick(session, loud_round, fixture, loud, PickOutcome.HOME, "2.00")

    with (
        patch.object(settings, "vapid_private_key", "priv"),
        patch.object(settings, "vapid_public_key", "pub"),
        patch("src.services.push_notification_service._send_push_sync") as push,
    ):
        ok = await _sweep(
            session,
            [muted_league, loud_league],
            _Results(settlement_from_score(fixture.provider_event_id, 1, 0)),
        )

    assert ok is True
    assert (muted_round.status, loud_round.status) == (
        GameweekStatus.settled,
        GameweekStatus.settled,
    )
    delivered_to = [call.args[0]["endpoint"] for call in push.call_args_list]
    assert delivered_to == [f"https://push.example.test/{loud.id}"]


async def test_settling_again_tells_nobody_again(session: AsyncSession) -> None:
    """Announced once, when the round finishes — never per sweep.

    The sweep runs at 18:00, 20:00 and 22:00 and a round often finishes over two of them:
    one result lands, the round waits on another. Telling members at the first would be
    telling them before their points exist; telling them at every sweep would be three
    identical messages a Saturday.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner, "Evening League")
    early = await _profile(session, "early")
    late = await _profile(session, "late")
    await _join(session, league, early)
    await _join(session, league, late)
    first = await _fixture(session, "Forfar Athletic", "Brechin City")
    second = await _fixture(session, "Arbroath", "Montrose")
    gameweek = await _locked_round(session, league, [first, second])
    await _pick(session, gameweek, first, early, PickOutcome.HOME, "2.20")
    await _pick(session, gameweek, second, late, PickOutcome.AWAY, "1.80")
    both = _Results(
        settlement_from_score(first.provider_event_id, 3, 0),
        settlement_from_score(second.provider_event_id, 0, 2),
    )

    sent: list[dict[str, Any]] = []
    with patch(SEND, new=_recorder(sent)):
        # 18:00 — one result in; the round is still waiting on the other.
        only_first = _Results(settlement_from_score(first.provider_event_id, 3, 0))
        assert await _sweep(session, [league], only_first) is True
        assert gameweek.status is GameweekStatus.locked
        assert sent == []

        # 20:00 — the last result lands and the round settles: told now, once each.
        assert await _sweep(session, [league], both) is True
        assert gameweek.status is GameweekStatus.settled
        assert sorted(message["user_id"] for message in sent) == sorted([early.id, late.id])

        # 22:00 — nothing left to settle, and nothing said.
        assert await _sweep(session, [league], both) is True

    assert len(sent) == 2


async def test_a_failed_announcement_does_not_fail_the_sweep(session: AsyncSession) -> None:
    """By the time anything is sent the points have committed, so a failure is only logged.

    The sweep reports success: a dead push service is not a settlement that did not
    happen, and a job reporting it as one would send somebody looking in the wrong place.
    """
    owner = await _profile(session, "owner")
    league = await _league(session, owner, "Unlucky League")
    member = await _profile(session, "member")
    await _join(session, league, member)
    fixture = await _fixture(session, "Forfar Athletic", "Brechin City")
    gameweek = await _locked_round(session, league, [fixture])
    await _pick(session, gameweek, fixture, member, PickOutcome.HOME, "2.50")

    boom = AsyncMock(side_effect=RuntimeError("push service down"))
    with (
        patch(SEND, new=boom),
        patch("src.services.notification_triggers.log") as trigger_log,
    ):
        ok = await _sweep(
            session, [league], _Results(settlement_from_score(fixture.provider_event_id, 2, 1))
        )

    assert ok is True
    boom.assert_awaited()
    trigger_log.exception.assert_called_once()


# ── Results entered by hand ────────────────────────────────────────────────────


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _committed_round(
    members: int,
) -> tuple[Profile, League, Gameweek, Fixture, list[Profile]]:
    """An admin, and a league whose locked round has one pending pick — committed.

    The first member holds the home side at 2.50; the rest hold nothing.
    """
    async with AsyncSessionLocal() as db:
        admin = await _profile(db, "admin", role=UserRole.admin)
        league = await _league(db, admin, "Hand League")
        people = [await _profile(db, f"member{i}") for i in range(members)]
        for person in people:
            await _join(db, league, person)
        fixture = await _fixture(db, "Forfar Athletic", "Brechin City")
        gameweek = await _locked_round(db, league, [fixture])
        await _pick(db, gameweek, fixture, people[0], PickOutcome.HOME, "2.50")
        await db.commit()
        return admin, league, gameweek, fixture, people


async def test_a_hand_entered_settlement_tells_the_league_once(client: AsyncClient) -> None:
    """An admin settling a stuck round announces it exactly as the sweep would.

    The second attempt is refused — the round has settled — and says nothing either.
    """
    admin, league, gameweek, fixture, (picker, idle) = await _committed_round(2)
    payload = {"results": [{"fixture_id": str(fixture.id), "home_goals": 2, "away_goals": 1}]}

    sent: list[dict[str, Any]] = []
    with patch(SEND, new=_recorder(sent)):
        first = await client.post(
            f"/api/v1/admin/results/{gameweek.id}/settle", json=payload, headers=_auth(admin)
        )
        again = await client.post(
            f"/api/v1/admin/results/{gameweek.id}/settle", json=payload, headers=_auth(admin)
        )

    assert first.status_code == 200, first.text
    assert first.json()["settled"] is True
    assert again.status_code == 409
    assert sorted(message["user_id"] for message in sent) == sorted([picker.id, idle.id])
    by_member = {message["user_id"]: message for message in sent}
    assert by_member[picker.id]["body"].endswith(
        "Your pick, Forfar Athletic (v Brechin City) @ 2.50, won 25 points."
    )
    assert by_member[idle.id]["body"].endswith("You had no pick this round.")
    assert {message["league_id"] for message in sent} == {league.id}


async def test_a_failed_announcement_leaves_a_hand_entered_settlement_standing(
    client: AsyncClient,
) -> None:
    """The admin gets their answer and the points stay, whatever the push service does."""
    admin, _league_row, gameweek, fixture, _people = await _committed_round(1)
    payload = {"results": [{"fixture_id": str(fixture.id), "home_goals": 2, "away_goals": 1}]}

    boom = AsyncMock(side_effect=RuntimeError("push service down"))
    with (
        patch(SEND, new=boom),
        patch("src.services.notification_triggers.log") as trigger_log,
    ):
        response = await client.post(
            f"/api/v1/admin/results/{gameweek.id}/settle", json=payload, headers=_auth(admin)
        )

    assert response.status_code == 200, response.text
    assert response.json()["settled"] is True
    boom.assert_awaited()
    trigger_log.exception.assert_called_once()
    async with AsyncSessionLocal() as db:
        stored = await db.get(Gameweek, gameweek.id)
        assert stored is not None and stored.status is GameweekStatus.settled
        pick = (await db.execute(select(Pick).where(Pick.gameweek_id == gameweek.id))).scalar_one()
        assert (pick.status, pick.points_awarded) == (PickStatus.won, 25)


# ── What the round is called ───────────────────────────────────────────────────


def test_a_round_is_named_the_way_its_screen_names_it() -> None:
    """``roundName`` in ``lib/coupon.ts``, line for line: season week, number, then date."""
    saturday = date(2027, 3, 6)
    assert round_name("12b", 7, saturday) == "Gameweek 12b"
    assert round_name(None, 7, saturday) == "Gameweek 7"
    assert round_name("", 7, saturday) == "Gameweek 7"
    assert round_name(None, None, saturday) == "The round of Sat 6 Mar 2027"
