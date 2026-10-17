"""Batch 205 — pay to pick: weekly dues, the ledger and the paid-up check (ADR 0009).

Every active member of a league that charges a fee owes one fee for every round, recorded
when the round opens, and must be paid up — arrears and the round in front of them — to
pick. These are the row's verification cases plus the edges its design leans on:

* refused while owing, allowed once paid up, with a 402 and never a 401;
* a missed week rolls over, and prepaying carries credit forward;
* dues are charged once per member per round however often the opening runs;
* a member joining while a round is open owes it, and nothing before it;
* picking, changing a pick and re-picking after a postponement cost nothing extra;
* a voided round, a withdrawn round and leaving before the lock all reverse the due;
* only a site admin sets the fee and the link, and a league with a fee stays private;
* the season pot across a season boundary.

Postgres-backed. The HTTP cases commit, because the app reads through its own sessions,
and every row they write is removed again by the ``world`` fixture; the service cases run
in a session that is always rolled back. Rounds are dated in seasons nothing else in the
suite labels (2063 onwards) and lock two hours out, clear of the reminder window.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.auth import create_access_token, hash_pin
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League, LeaguePrivacy
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.models.notification import ActionType, AuditLog
from src.models.pick import Pick
from src.models.profile import Profile, UserRole
from src.models.season_calendar import SeasonCalendar
from src.services.betfair import (
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_ID,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_ID,
    FakeBetfair,
)
from src.services.dues import (
    NOTE_LEFT_BEFORE_LOCK,
    NOTE_REJOINED,
    NOTE_ROUND_VOIDED,
    NOTE_ROUND_WITHDRAWN,
    PAYMENT_REQUIRED,
    RoundDue,
    _rounds_ahead,
    allocate,
    fee_standings,
    format_pence,
    league_money,
    normalise_payer_name,
    record_round_dues,
    reverse_round_dues,
    season_pot,
)
from src.services.gameweek import (
    _drop_voided_fixtures,
    open_due_gameweeks,
    retire_stranded_rounds,
    sync_slate,
    window_for,
)
from src.services.notification_triggers import send_pick_reminders
from src.services.odds_provider import SlateFixture

FEE = 100
PIN = "1234"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


def _saturday(year: int, month: int, day: int) -> date:
    """The first Saturday on or after the given day."""
    start = date(year, month, day)
    return start + timedelta(days=(5 - start.weekday()) % 7)


# ── Committed worlds, cleaned up afterwards ────────────────────────────────────


@dataclass
class World:
    """Every league and profile a test commits, so the fixture can remove them all."""

    leagues: list[uuid.UUID] = field(default_factory=list)
    profiles: list[uuid.UUID] = field(default_factory=list)


async def _clean(world: World) -> None:
    async with AsyncSessionLocal() as session:
        if world.leagues:
            await session.execute(
                delete(LedgerEntry).where(LedgerEntry.league_id.in_(world.leagues))
            )
            await session.execute(
                delete(PayerMapping).where(PayerMapping.league_id.in_(world.leagues))
            )
            await session.execute(delete(Gameweek).where(Gameweek.league_id.in_(world.leagues)))
            await session.execute(
                delete(LeagueMembership).where(LeagueMembership.league_id.in_(world.leagues))
            )
            await session.execute(delete(AuditLog).where(AuditLog.target_id.in_(world.leagues)))
            await session.execute(delete(League).where(League.id.in_(world.leagues)))
        if world.profiles:
            await session.execute(
                delete(LeagueMembership).where(LeagueMembership.player_id.in_(world.profiles))
            )
            await session.execute(delete(Profile).where(Profile.id.in_(world.profiles)))
        await session.commit()


@pytest_asyncio.fixture
async def world(db_engine: AsyncEngine) -> AsyncIterator[World]:
    created = World()
    try:
        yield created
    finally:
        await _clean(created)


@pytest_asyncio.fixture
async def client_and_fake(world: World) -> AsyncIterator[tuple[AsyncClient, FakeBetfair]]:
    fake = FakeBetfair.with_sample_data()
    app.dependency_overrides[get_odds_provider] = lambda: fake
    app.dependency_overrides[get_optional_odds_provider] = lambda: fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, fake
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


@pytest_asyncio.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session that is always rolled back — nothing the service cases write persists."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _profile(
    db: AsyncSession, world: World | None, name: str, role: UserRole = UserRole.player
) -> Profile:
    profile = Profile(
        display_name=f"{name}-{uuid.uuid4().hex[:8]}", pin_hash=hash_pin(PIN), role=role
    )
    db.add(profile)
    await db.flush()
    if world is not None:
        world.profiles.append(profile.id)
    return profile


async def _league(
    db: AsyncSession,
    world: World | None,
    members: list[Profile],
    *,
    fee: int | None = FEE,
    link: str | None = "https://pay.example/weekly-coupon",
    privacy: LeaguePrivacy = LeaguePrivacy.private,
) -> League:
    """A league the first member runs and every member plays in."""
    tag = uuid.uuid4().hex[:8]
    league = League(
        slug=f"pay-{tag}",
        name=f"Pay {tag}",
        created_by=members[0].id,
        privacy=privacy,
        entry_fee_pence=fee,
        payment_link_url=link,
    )
    db.add(league)
    await db.flush()
    if world is not None:
        world.leagues.append(league.id)
    for index, member in enumerate(members):
        db.add(
            LeagueMembership(
                league_id=league.id,
                player_id=member.id,
                role=LeagueMemberRole.admin if index == 0 else LeagueMemberRole.player,
            )
        )
    await db.flush()
    return league


async def _pooled(db: AsyncSession, event_id: str) -> Fixture:
    """One of the two canned fixtures the fake prices, shared through the pool."""
    found = (
        await db.execute(select(Fixture).where(Fixture.provider_event_id == event_id))
    ).scalar_one_or_none()
    if found is not None:
        return found
    epl = event_id == SAMPLE_EPL_EVENT_ID
    fixture = Fixture(
        provider_event_id=event_id,
        home="Arsenal" if epl else "Forfar Athletic",
        away="Chelsea" if epl else "Brechin City",
        kickoff_utc=_now() + timedelta(hours=3),
        competition="English Premier League" if epl else "Scottish League Two",
        competition_id=SAMPLE_EPL_ID if epl else SAMPLE_SL2_ID,
    )
    db.add(fixture)
    await db.flush()
    return fixture


async def _round(
    db: AsyncSession,
    league: League,
    starts_on: date,
    *,
    status: GameweekStatus = GameweekStatus.open,
    locks_in: timedelta = timedelta(hours=2),
    opens_ago: timedelta | None = None,
    event_id: str = SAMPLE_EPL_EVENT_ID,
    number: int | None = None,
) -> Gameweek:
    """A round of ``league`` playing one canned fixture. Negative ``locks_in`` is the past."""
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=status,
        locks_at_utc=_now() + locks_in,
        picks_open_at_utc=None if opens_ago is None else _now() - opens_ago,
        number=number,
    )
    db.add(gameweek)
    await db.flush()
    fixture = await _pooled(db, event_id)
    db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
    await db.flush()
    return gameweek


def _cash(league: League, member: Profile, pence: int) -> LedgerEntry:
    return LedgerEntry(
        league_id=league.id, player_id=member.id, kind=LedgerKind.payment, amount_pence=pence
    )


async def _submit(
    client: AsyncClient, league: League, member: Profile, outcome: str = "HOME"
) -> Response:
    async with AsyncSessionLocal() as db:
        fixture = await _pooled(db, SAMPLE_EPL_EVENT_ID)
        await db.commit()
    return await _submit_on(client, league, member, fixture.id, outcome)


async def _submit_on(
    client: AsyncClient,
    league: League,
    member: Profile,
    fixture_id: uuid.UUID,
    outcome: str = "HOME",
    market: str = "MATCH_ODDS",
) -> Response:
    return await client.post(
        f"/api/v1/leagues/{league.slug}/picks",
        json={"fixture_id": str(fixture_id), "market": market, "outcome": outcome},
        headers=_auth(member),
    )


async def _entries(league_id: uuid.UUID, player_id: uuid.UUID | None = None) -> list[LedgerEntry]:
    async with AsyncSessionLocal() as db:
        query = select(LedgerEntry).where(LedgerEntry.league_id == league_id)
        if player_id is not None:
            query = query.where(LedgerEntry.player_id == player_id)
        return list((await db.execute(query.order_by(LedgerEntry.created_at))).scalars().all())


def _owed_for(entries: list[LedgerEntry], gameweek_id: uuid.UUID) -> int:
    """What the entries say is still owed for one round."""
    return -sum(
        entry.amount_pence
        for entry in entries
        if entry.gameweek_id == gameweek_id
        and entry.kind in (LedgerKind.round_due, LedgerKind.due_reversal)
    )


async def _record(league: League, *entries: LedgerEntry) -> None:
    async with AsyncSessionLocal() as db:
        db.add_all(entries)
        await db.commit()


async def _open_with_dues(db: AsyncSession, league: League, gameweek: Gameweek) -> None:
    """Record the round's dues the way its opening would."""
    await record_round_dues(db, league, gameweek)


async def _fee_of(client: AsyncClient, league: League, member: Profile, gameweek: Gameweek) -> Any:
    response = await client.get(
        f"/api/v1/leagues/{league.slug}/gameweek/current",
        params={"gameweek_id": str(gameweek.id)},
        headers=_auth(member),
    )
    assert response.status_code == 200, response.text
    return response.json()["fee"]


# ── The pure arithmetic ─────────────────────────────────────────────────────────


def test_payments_clear_the_oldest_dues_first() -> None:
    week = [RoundDue(uuid.uuid4(), date(2063, 3, 3) + timedelta(weeks=n), FEE) for n in range(4)]
    paid = allocate(250, list(reversed(week)))
    assert [due for due, _ in paid] == week, "oldest first, whatever order they arrive in"
    assert [covered for _, covered in paid] == [100, 100, 50, 0]
    assert [covered for _, covered in allocate(-300, week)] == [0, 0, 0, 0]


def test_money_reads_as_pounds_and_payer_names_fold_together() -> None:
    assert [format_pence(p) for p in (100, 250, 5, 0, -200)] == [
        "£1",
        "£2.50",
        "£0.05",
        "£0",
        "-£2",
    ]
    assert normalise_payer_name("J. Smith") == normalise_payer_name("  j   SMITH ") == "j smith"
    assert normalise_payer_name("Zoë O'Brien-Lée") == "zoe o brien lee"


# ── Refused while owing, allowed once paid up ──────────────────────────────────


async def test_a_member_who_owes_is_refused_with_its_own_code_until_paid_up(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "owing")
        league = await _league(db, world, [member])
        gameweek = await _round(db, league, _saturday(2063, 3, 1))
        await _open_with_dues(db, league, gameweek)
        await db.commit()

    with patch.object(fake, "fetch_odds_for_pick", wraps=fake.fetch_odds_for_pick) as priced:
        refused = await _submit(client, league, member)
        assert refused.status_code == 402, refused.text
        assert refused.json()["detail"] == PAYMENT_REQUIRED
        assert priced.call_count == 0, "a refused pick must spend no provider request"

        await _record(league, _cash(league, member, FEE))
        allowed = await _submit(client, league, member)
        assert allowed.status_code == 201, allowed.text
        assert priced.call_count == 1

    entries = await _entries(league.id, member.id)
    assert [entry.kind for entry in entries].count(LedgerKind.round_due) == 1


async def test_a_league_without_a_fee_records_nothing_and_asks_for_nothing(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "free")
        league = await _league(db, world, [member], fee=None, link=None)
        gameweek = await _round(db, league, _saturday(2063, 3, 8))
        await _open_with_dues(db, league, gameweek)
        await db.commit()

    assert (await _submit(client, league, member)).status_code == 201
    assert await _fee_of(client, league, member, gameweek) is None
    assert await _entries(league.id) == []


# ── Rollover, credit and the two-rounds-open case ──────────────────────────────


async def test_a_missed_week_rolls_over_so_week_four_needs_two_fees(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    """Paid weeks one and two, nothing in week three: week four costs £2 to play."""
    client, _fake = client_and_fake
    first = _saturday(2063, 4, 1)
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "skipper")
        league = await _league(db, world, [member])
        weeks = [
            await _round(
                db,
                league,
                first + timedelta(weeks=n),
                status=GameweekStatus.settled,
                locks_in=-timedelta(days=7 * (3 - n)),
                number=n + 1,
            )
            for n in range(3)
        ]
        weeks.append(await _round(db, league, first + timedelta(weeks=3), number=4))
        for gameweek in weeks:
            await _open_with_dues(db, league, gameweek)
        db.add_all([_cash(league, member, FEE), _cash(league, member, FEE)])
        await db.commit()

    fee = await _fee_of(client, league, member, weeks[3])
    assert fee["owed_pence"] == 2 * FEE
    assert [(r["number"], r["amount_pence"]) for r in fee["owed_rounds"]] == [(3, FEE), (4, FEE)]
    assert fee["credit_pence"] == 0

    assert (await _submit(client, league, member)).status_code == 402
    await _record(league, _cash(league, member, FEE))
    assert (await _submit(client, league, member)).status_code == 402, "£1 of £2 is not paid up"
    await _record(league, _cash(league, member, FEE))
    assert (await _submit(client, league, member)).status_code == 201


async def test_prepaying_several_weeks_carries_credit_forward(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    first = _saturday(2063, 5, 1)
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "prepaid")
        league = await _league(db, world, [member])
        this_week = await _round(db, league, first)
        await _open_with_dues(db, league, this_week)
        db.add(_cash(league, member, 3 * FEE))
        await db.commit()

    fee = await _fee_of(client, league, member, this_week)
    assert (fee["owed_pence"], fee["credit_pence"]) == (0, 2 * FEE)
    assert (await _submit(client, league, member)).status_code == 201

    # The week settles and the next opens: the credit pays for it with nothing new paid.
    async with AsyncSessionLocal() as db:
        settled = await db.get(Gameweek, this_week.id)
        assert settled is not None
        settled.status = GameweekStatus.settled
        settled.locks_at_utc = _now() - timedelta(days=1)
        next_week = await _round(db, league, first + timedelta(weeks=1))
        await _open_with_dues(db, league, next_week)
        await db.commit()

    fee = await _fee_of(client, league, member, next_week)
    assert (fee["owed_pence"], fee["credit_pence"]) == (0, FEE)
    assert (await _submit(client, league, member, "AWAY")).status_code == 201


async def test_with_two_rounds_open_this_week_needs_only_this_weeks_fee(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    """A league announcing no opening has next week open beside this one."""
    client, _fake = client_and_fake
    first = _saturday(2063, 6, 1)
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "early")
        league = await _league(db, world, [member])
        this_week = await _round(db, league, first)
        next_week = await _round(
            db,
            league,
            first + timedelta(weeks=1),
            locks_in=timedelta(days=7, hours=2),
            event_id=SAMPLE_SL2_EVENT_ID,
        )
        for gameweek in (this_week, next_week):
            await _open_with_dues(db, league, gameweek)
        db.add(_cash(league, member, FEE))
        sl2 = await _pooled(db, SAMPLE_SL2_EVENT_ID)
        await db.commit()

    assert (await _fee_of(client, league, member, this_week))["owed_pence"] == 0
    assert (await _fee_of(client, league, member, next_week))["owed_pence"] == FEE
    assert (await _submit(client, league, member)).status_code == 201
    assert (await _submit_on(client, league, member, sl2.id)).status_code == 402


# ── Charged once, however often the opening runs ───────────────────────────────


async def test_an_opening_charges_every_active_member_once_however_often_it_runs(
    session: AsyncSession,
) -> None:
    active = [await _profile(session, None, f"active{n}") for n in range(3)]
    gone = await _profile(session, None, "gone")
    inactive = await _profile(session, None, "inactive")
    league = await _league(session, None, [*active, gone, inactive])
    gone_row = (
        await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id, LeagueMembership.player_id == gone.id
            )
        )
    ).scalar_one()
    gone_row.deleted_at = _now()
    inactive.is_active = False
    gameweek = await _round(
        session,
        league,
        _saturday(2063, 7, 1),
        status=GameweekStatus.scheduled,
        opens_ago=timedelta(minutes=5),
    )

    opened = await open_due_gameweeks(session, _now())
    assert gameweek.id in {round_.id for round_ in opened}
    assert gameweek.id not in {round_.id for round_ in await open_due_gameweeks(session, _now())}
    # A round put back to "scheduled" by a settings edit opens again; still charged once.
    gameweek.status = GameweekStatus.scheduled
    await session.flush()
    assert gameweek.id in {round_.id for round_ in await open_due_gameweeks(session, _now())}
    for _ in range(2):
        assert await record_round_dues(session, league, gameweek) == 0

    dues = (
        await session.execute(
            select(LedgerEntry.player_id, func.count())
            .where(LedgerEntry.gameweek_id == gameweek.id, LedgerEntry.kind == LedgerKind.round_due)
            .group_by(LedgerEntry.player_id)
        )
    ).all()
    assert dict(dues) == {member.id: 1 for member in active}

    with pytest.raises(IntegrityError):
        session.add(
            LedgerEntry(
                league_id=league.id,
                player_id=active[0].id,
                kind=LedgerKind.round_due,
                amount_pence=-FEE,
                gameweek_id=gameweek.id,
            )
        )
        await session.flush()


async def test_a_round_discovered_already_open_is_charged_at_discovery(
    session: AsyncSession,
) -> None:
    fake = FakeBetfair.with_sample_data()
    member = await _profile(session, None, "discovered")
    charging = await _league(session, None, [member])
    free = await _league(session, None, [member], fee=None, link=None)
    slate = await fake.fetch_slate(window_for(charging), SAMPLE_SATURDAY)

    charged_round = await sync_slate(session, charging, slate)
    free_round = await sync_slate(session, free, slate)
    assert charged_round is not None and free_round is not None
    assert charged_round.status is GameweekStatus.open

    by_round = (
        await session.execute(
            select(LedgerEntry.gameweek_id, func.count())
            .where(LedgerEntry.gameweek_id.in_([charged_round.id, free_round.id]))
            .group_by(LedgerEntry.gameweek_id)
        )
    ).all()
    assert dict(by_round) == {charged_round.id: 1}


async def test_dues_start_with_the_first_round_that_opens_after_the_fee_is_set(
    session: AsyncSession,
) -> None:
    member = await _profile(session, None, "late-fee")
    league = await _league(session, None, [member], fee=None, link=None)
    already_open = await _round(session, league, _saturday(2063, 8, 1))
    upcoming = await _round(
        session,
        league,
        _saturday(2063, 8, 1) + timedelta(weeks=1),
        status=GameweekStatus.scheduled,
        locks_in=timedelta(days=7, hours=2),
        opens_ago=timedelta(minutes=1),
    )
    league.entry_fee_pence = FEE
    await session.flush()

    standing = (await fee_standings(session, league, already_open, [member.id]))[member.id]
    assert (standing.round_due_pence, standing.owed_pence) == (0, 0)

    await open_due_gameweeks(session, _now())
    standing = (await fee_standings(session, league, upcoming, [member.id]))[member.id]
    assert (standing.round_due_pence, standing.owed_pence) == (FEE, FEE)


async def test_a_scheduled_round_past_its_opening_is_charged_by_the_pick_and_not_again(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    """The hour before the opening job runs: the pick asks for the fee and records it."""
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        early, other = (await _profile(db, world, "early"), await _profile(db, world, "other"))
        league = await _league(db, world, [early, other])
        gameweek = await _round(
            db,
            league,
            _saturday(2063, 9, 1),
            status=GameweekStatus.scheduled,
            opens_ago=timedelta(minutes=10),
        )
        await db.commit()

    assert (await _submit(client, league, early)).status_code == 402
    await _record(league, _cash(league, early, FEE))
    assert (await _submit(client, league, early)).status_code == 201
    assert _owed_for(await _entries(league.id, early.id), gameweek.id) == FEE

    async with AsyncSessionLocal() as db:
        try:
            await open_due_gameweeks(db, _now())
            dues = (
                await db.execute(
                    select(LedgerEntry.player_id, func.count())
                    .where(
                        LedgerEntry.gameweek_id == gameweek.id,
                        LedgerEntry.kind == LedgerKind.round_due,
                    )
                    .group_by(LedgerEntry.player_id)
                )
            ).all()
            assert dict(dues) == {early.id: 1, other.id: 1}
        finally:
            await db.rollback()


# ── Joining, leaving and rejoining ─────────────────────────────────────────────


async def test_a_member_joining_while_a_round_is_open_owes_it_and_nothing_earlier(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    first = _saturday(2063, 10, 1)
    async with AsyncSessionLocal() as db:
        founder = await _profile(db, world, "founder")
        joiner = await _profile(db, world, "joiner")
        league = await _league(db, world, [founder])
        played = await _round(
            db, league, first, status=GameweekStatus.settled, locks_in=-timedelta(days=7)
        )
        current = await _round(db, league, first + timedelta(weeks=1))
        for gameweek in (played, current):
            await _open_with_dues(db, league, gameweek)
        await db.commit()

    joined = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": league.join_code}, headers=_auth(joiner)
    )
    assert joined.status_code == 200, joined.text

    entries = await _entries(league.id, joiner.id)
    assert _owed_for(entries, current.id) == FEE
    assert _owed_for(entries, played.id) == 0
    fee = await _fee_of(client, league, joiner, current)
    assert fee["owed_pence"] == FEE
    assert [r["gameweek_id"] for r in fee["owed_rounds"]] == [str(current.id)]


async def test_a_joiner_owes_an_open_round_whose_opening_was_moved_back(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    """A settings edit can push an opening back into the future; a round holding picks
    keeps its ``open`` label and is never opened again, so the newcomer owes it on joining.
    """
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        founder = await _profile(db, world, "founder")
        joiner = await _profile(db, world, "joiner")
        league = await _league(db, world, [founder])
        held_open = await _round(db, league, _saturday(2063, 12, 1))
        await _open_with_dues(db, league, held_open)
        held_open.picks_open_at_utc = _now() + timedelta(hours=1)
        await db.commit()

    joined = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": league.join_code}, headers=_auth(joiner)
    )
    assert joined.status_code == 200, joined.text
    assert _owed_for(await _entries(league.id, joiner.id), held_open.id) == FEE


async def test_leaving_before_the_lock_reverses_the_due_and_rejoining_restores_it(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    first = _saturday(2063, 11, 1)
    async with AsyncSessionLocal() as db:
        founder = await _profile(db, world, "founder")
        leaver = await _profile(db, world, "leaver")
        league = await _league(db, world, [founder, leaver])
        locked = await _round(
            db, league, first, status=GameweekStatus.locked, locks_in=-timedelta(hours=1)
        )
        current = await _round(db, league, first + timedelta(weeks=1))
        for gameweek in (locked, current):
            await _open_with_dues(db, league, gameweek)
        await db.commit()

    left = await client.delete(f"/api/v1/leagues/{league.slug}/membership", headers=_auth(leaver))
    assert left.status_code == 204, left.text
    entries = await _entries(league.id, leaver.id)
    assert _owed_for(entries, current.id) == 0, "the open round is no longer owed"
    assert _owed_for(entries, locked.id) == FEE, "a locked round stays owed"
    (reversal,) = (e for e in entries if e.kind is LedgerKind.due_reversal)
    assert (reversal.note, reversal.created_by) == (NOTE_LEFT_BEFORE_LOCK, leaver.id)

    rejoined = await client.post(
        "/api/v1/leagues/join-by-code", json={"code": league.join_code}, headers=_auth(leaver)
    )
    assert rejoined.status_code == 200, rejoined.text
    entries = await _entries(league.id, leaver.id)
    assert _owed_for(entries, current.id) == FEE
    assert [e.kind for e in entries if e.gameweek_id == current.id].count(
        LedgerKind.round_due
    ) == 1, "one due per member per round — rejoining undoes the reversal instead"
    assert [e.note for e in entries if e.kind is LedgerKind.due_reversal][-1] == NOTE_REJOINED


# ── Picking costs nothing extra ────────────────────────────────────────────────


async def test_picking_changing_and_repicking_after_a_postponement_cost_nothing_extra(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "repicker")
        league = await _league(db, world, [member])
        gameweek = await _round(db, league, _saturday(2064, 1, 1))
        sl2 = await _pooled(db, SAMPLE_SL2_EVENT_ID)
        db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=sl2.id))
        await _open_with_dues(db, league, gameweek)
        db.add(_cash(league, member, FEE))
        await db.commit()

    assert (await _submit(client, league, member, "HOME")).status_code == 201
    assert (await _submit(client, league, member, "AWAY")).status_code == 201
    assert (await _submit_on(client, league, member, sl2.id)).status_code == 201

    # The Scottish game is called off before the lock: the pick goes, and the member
    # picks again — the way discovery's postponement handling leaves them.
    async with AsyncSessionLocal() as db:
        held = await db.get(Gameweek, gameweek.id)
        refreshed_league = await db.get(League, league.id)
        assert held is not None and refreshed_league is not None
        postponed = SlateFixture(
            provider_event_id=SAMPLE_SL2_EVENT_ID,
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=_now() + timedelta(hours=3),
            competition="Scottish League Two",
            competition_id=SAMPLE_SL2_ID,
            status="postponed",
        )
        await _drop_voided_fixtures(db, refreshed_league, held, {sl2.id: postponed})
        await db.commit()
        assert (
            await db.scalar(
                select(func.count()).select_from(Pick).where(Pick.gameweek_id == held.id)
            )
        ) == 0

    assert (await _submit(client, league, member, "DRAW")).status_code == 201

    entries = await _entries(league.id, member.id)
    assert sum(entry.amount_pence for entry in entries) == 0, "one fee paid, one fee owed"
    assert [entry.kind for entry in entries].count(LedgerKind.round_due) == 1


# ── Reversals: a voided round and a withdrawn one ──────────────────────────────


async def test_a_voided_round_reverses_everyones_due(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    saturday = _saturday(2064, 2, 1)
    async with AsyncSessionLocal() as db:
        admin = await _profile(db, world, "site-admin", UserRole.admin)
        members = [await _profile(db, world, f"voided{n}") for n in range(2)]
        league = await _league(db, world, members)
        await _round(
            db, league, saturday, status=GameweekStatus.settled, locks_in=-timedelta(days=1)
        )
        stray = await _round(
            db,
            league,
            saturday - timedelta(days=1),
            status=GameweekStatus.locked,
            locks_in=-timedelta(hours=1),
        )
        await _open_with_dues(db, league, stray)
        await db.commit()

    voided = await client.post(
        f"/api/v1/admin/results/{stray.id}/void-non-scoring",
        json={"reason": "Friday stray left by a window edit"},
        headers=_auth(admin),
    )
    assert voided.status_code == 200, voided.text
    for member in members:
        entries = await _entries(league.id, member.id)
        assert _owed_for(entries, stray.id) == 0
        (reversal,) = (e for e in entries if e.kind is LedgerKind.due_reversal)
        assert (reversal.note, reversal.created_by) == (NOTE_ROUND_VOIDED, admin.id)
        fee = await _fee_of(client, league, member, stray)
        assert (fee["round_due_pence"], fee["owed_pence"]) == (0, 0), "a voided round costs nothing"


async def test_a_withdrawn_round_reverses_its_dues_and_keeps_them_as_history(
    session: AsyncSession,
) -> None:
    member = await _profile(session, None, "withdrawn")
    league = await _league(session, None, [member])
    friday = _saturday(2064, 3, 1) - timedelta(days=1)
    stranded = await _round(session, league, friday, locks_in=timedelta(days=1))
    await record_round_dues(session, league, stranded)

    retired = await retire_stranded_rounds(session, league, friday, 1)
    assert retired == [friday]
    # Columns, not entities: the identity map still holds the reversal as it was written,
    # before the delete's ``SET NULL`` reached it.
    rows = (
        await session.execute(
            select(
                LedgerEntry.kind,
                LedgerEntry.gameweek_id,
                LedgerEntry.amount_pence,
                LedgerEntry.note,
            ).where(LedgerEntry.player_id == member.id)
        )
    ).all()
    assert sorted((row.kind, row.gameweek_id) for row in rows) == [
        (LedgerKind.due_reversal, None),
        (LedgerKind.round_due, None),
    ], "both stay, with the withdrawn round's id taken off them"
    assert sum(row.amount_pence for row in rows) == 0
    assert NOTE_ROUND_WITHDRAWN in {row.note for row in rows}


# ── The fee and the link: site admins only, private leagues only ───────────────


async def test_a_league_admin_is_refused_on_both_fields_and_a_site_admin_is_audited(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        runner = await _profile(db, world, "runner")
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        league = await _league(db, world, [runner], fee=None, link=None)
        await db.commit()

    for field_name, value in (
        ("entry_fee_pence", FEE),
        ("payment_link_url", "https://pay.example/mine"),
    ):
        refused = await client.patch(
            f"/api/v1/leagues/{league.slug}", json={field_name: value}, headers=_auth(runner)
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"] == "SITE_ADMIN_REQUIRED"

    accepted = await client.patch(
        f"/api/v1/leagues/{league.slug}",
        json={"entry_fee_pence": FEE, "payment_link_url": "https://pay.example/weekly"},
        headers=_auth(site_admin),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["entry_fee_pence"] == FEE
    assert accepted.json()["payment_link_url"] == "https://pay.example/weekly"

    async with AsyncSessionLocal() as db:
        (audit,) = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.target_id == league.id,
                        AuditLog.action_type == ActionType.league_updated,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert audit.changes == {
        "entry_fee_pence": {"from": None, "to": FEE},
        "payment_link_url": {"from": None, "to": "https://pay.example/weekly"},
    }

    # A league admin reads the fee but not the link; the link reaches members through
    # the round payload.
    detail = await client.get(f"/api/v1/leagues/{league.slug}", headers=_auth(runner))
    assert detail.status_code == 200
    assert (detail.json()["entry_fee_pence"], detail.json()["payment_link_url"]) == (FEE, None)
    assert detail.json()["season_pot_pence"] == 0


async def test_a_league_with_a_fee_stays_private_in_both_directions(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        runner = await _profile(db, world, "runner")
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        public = await _league(
            db, world, [runner], fee=None, link=None, privacy=LeaguePrivacy.public_request
        )
        charging = await _league(db, world, [runner])
        await db.commit()

    fee_on_public = await client.patch(
        f"/api/v1/leagues/{public.slug}", json={"entry_fee_pence": FEE}, headers=_auth(site_admin)
    )
    assert fee_on_public.status_code == 409, fee_on_public.text
    assert fee_on_public.json()["detail"] == "FEE_REQUIRES_PRIVATE"

    going_public = await client.patch(
        f"/api/v1/leagues/{charging.slug}",
        json={"privacy": "public_open"},
        headers=_auth(runner),
    )
    assert going_public.status_code == 409, going_public.text
    assert going_public.json()["detail"] == "FEE_REQUIRES_PRIVATE"

    both_at_once = await client.patch(
        f"/api/v1/leagues/{public.slug}",
        json={"privacy": "private", "entry_fee_pence": FEE},
        headers=_auth(site_admin),
    )
    assert both_at_once.status_code == 200, both_at_once.text

    not_https = await client.patch(
        f"/api/v1/leagues/{public.slug}",
        json={"payment_link_url": "http://pay.example/weekly"},
        headers=_auth(site_admin),
    )
    assert not_https.status_code == 422, not_https.text

    async with AsyncSessionLocal() as db:
        stored = await db.get(League, charging.id)
        assert stored is not None
        stored.privacy = LeaguePrivacy.public_open
        with pytest.raises(IntegrityError):
            await db.commit()


# ── What a member sees ─────────────────────────────────────────────────────────


async def test_the_round_payload_carries_the_fee_and_the_link_without_any_confirmation(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "viewer")
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        league = await _league(db, world, [member])
        gameweek = await _round(db, league, _saturday(2064, 4, 1), number=7)
        await _open_with_dues(db, league, gameweek)
        await db.commit()

    fee = await _fee_of(client, league, member, gameweek)
    # The football-week label depends on the deployment calendar, which this test does not
    # own; that it is carried is the point here.
    assert "season_week" in fee["owed_rounds"][0]
    fee["owed_rounds"][0].pop("season_week")
    assert fee == {
        "entry_fee_pence": FEE,
        "round_due_pence": FEE,
        "owed_pence": FEE,
        "owed_rounds": [
            {
                "gameweek_id": str(gameweek.id),
                "starts_on": gameweek.starts_on.isoformat(),
                "number": 7,
                "amount_pence": FEE,
            }
        ],
        "earlier_balance_pence": 0,
        "credit_pence": 0,
        "adult_confirmed": False,
        "has_payment_link": True,
        "payment_link_url": "https://pay.example/weekly-coupon",
    }

    for _ in range(2):
        confirmed = await client.post(
            f"/api/v1/leagues/{league.slug}/adult-confirmation", headers=_auth(member)
        )
        assert confirmed.status_code == 200, confirmed.text
    fee = await _fee_of(client, league, member, gameweek)
    assert fee["adult_confirmed"] is True
    assert fee["payment_link_url"] == "https://pay.example/weekly-coupon"

    # A site admin looking in is not a member: no fee status, and no confirming for one.
    assert await _fee_of(client, league, site_admin, gameweek) is None
    refused = await client.post(
        f"/api/v1/leagues/{league.slug}/adult-confirmation", headers=_auth(site_admin)
    )
    assert refused.status_code == 403


async def test_a_member_who_never_confirms_still_gets_the_link_and_nothing_is_recorded(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    """Batch 209: ADR 0009's amended fourth rule leaves members' ages to the owner.

    The link is on every round a member reads, owing or paid up, and the app records
    nothing about their age along the way. A league with no link still sends none.
    """
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "never-asked")
        league = await _league(db, world, [member])
        bare = await _league(db, world, [member], link=None)
        owing = await _round(db, league, _saturday(2066, 3, 7), number=1)
        await _open_with_dues(db, league, owing)
        unlinked = await _round(db, bare, _saturday(2066, 3, 7), number=1)
        await _open_with_dues(db, bare, unlinked)
        await db.commit()

    owed = await _fee_of(client, league, member, owing)
    assert (owed["owed_pence"], owed["adult_confirmed"]) == (FEE, False)
    assert owed["payment_link_url"] == "https://pay.example/weekly-coupon"

    await _record(league, _cash(league, member, FEE))
    paid = await _fee_of(client, league, member, owing)
    assert (paid["owed_pence"], paid["adult_confirmed"]) == (0, False)
    assert paid["payment_link_url"] == "https://pay.example/weekly-coupon"

    no_link = await _fee_of(client, bare, member, unlinked)
    assert (no_link["has_payment_link"], no_link["payment_link_url"]) == (False, None)

    async with AsyncSessionLocal() as db:
        confirmed = (
            (
                await db.execute(
                    select(LeagueMembership.adult_confirmed_at).where(
                        LeagueMembership.player_id == member.id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert confirmed == [None, None]


async def test_the_reminder_tells_a_member_who_owes_that_they_must_pay_to_pick(
    session: AsyncSession,
) -> None:
    owing = await _profile(session, None, "owing")
    paid = await _profile(session, None, "paid")
    league = await _league(session, None, [owing, paid])
    gameweek = await _round(session, league, _saturday(2064, 5, 1))
    await record_round_dues(session, league, gameweek)
    session.add(_cash(league, paid, FEE))
    session.add(_cash(league, owing, FEE))
    session.add(
        LedgerEntry(
            league_id=league.id,
            player_id=owing.id,
            kind=LedgerKind.adjustment,
            amount_pence=-2 * FEE,
            note="opening balance: two weeks unpaid",
        )
    )
    await session.flush()

    sent: dict[uuid.UUID, str] = {}

    async def record(
        _db: AsyncSession, user_id: uuid.UUID, _title: str, body: str, **_: Any
    ) -> int:
        sent[user_id] = body
        return 1

    with patch("src.services.notification_triggers.send_notification", new=record):
        assert await send_pick_reminders(session, gameweek) == 2

    assert "You owe £2, so pay to pick before picks lock" in sent[owing.id]
    assert sent[paid.id].startswith(f"You haven't made your pick in {league.name} yet — picks lock")


# ── The organiser's routes ─────────────────────────────────────────────────────


async def test_the_organiser_records_cash_cash_outs_and_adjustments(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        runner = await _profile(db, world, "runner")
        member = await _profile(db, world, "member")
        outsider = await _profile(db, world, "outsider")
        league = await _league(db, world, [runner, member])
        gameweek = await _round(db, league, _saturday(2064, 6, 1))
        await _open_with_dues(db, league, gameweek)
        await db.commit()
    base = f"/api/v1/leagues/{league.slug}/payments"

    league_admin_refused = await client.post(
        f"{base}/cash",
        json={"player_id": str(member.id), "amount_pence": FEE},
        headers=_auth(runner),
    )
    assert league_admin_refused.status_code == 403
    assert (await client.get(base, headers=_auth(runner))).status_code == 403

    cash = await client.post(
        f"{base}/cash",
        json={"player_id": str(member.id), "amount_pence": 3 * FEE, "note": "paid at the pub"},
        headers=_auth(site_admin),
    )
    assert cash.status_code == 201, cash.text
    assert (cash.json()["kind"], cash.json()["created_by"]) == ("payment", str(site_admin.id))

    too_much = await client.post(
        f"{base}/cash-outs",
        json={"player_id": str(member.id), "amount_pence": 3 * FEE},
        headers=_auth(site_admin),
    )
    assert too_much.status_code == 409
    assert too_much.json()["detail"] == "CASH_OUT_EXCEEDS_CREDIT"
    cash_out = await client.post(
        f"{base}/cash-outs",
        json={"player_id": str(member.id), "amount_pence": FEE},
        headers=_auth(site_admin),
    )
    assert cash_out.status_code == 201
    assert cash_out.json()["amount_pence"] == -FEE

    no_reason = await client.post(
        f"{base}/adjustments",
        json={"player_id": str(runner.id), "amount_pence": -FEE},
        headers=_auth(site_admin),
    )
    assert no_reason.status_code == 422
    zero = await client.post(
        f"{base}/adjustments",
        json={"player_id": str(runner.id), "amount_pence": 0, "note": "nothing"},
        headers=_auth(site_admin),
    )
    assert zero.status_code == 422
    adjusted = await client.post(
        f"{base}/adjustments",
        json={"player_id": str(runner.id), "amount_pence": -FEE, "note": "week before dues"},
        headers=_auth(site_admin),
    )
    assert adjusted.status_code == 201
    stranger = await client.post(
        f"{base}/cash",
        json={"player_id": str(outsider.id), "amount_pence": FEE},
        headers=_auth(site_admin),
    )
    assert stranger.status_code == 404

    # June 2064 is in season 2063, which runs July to June.
    overview = await client.get(base, params={"season": 2063}, headers=_auth(site_admin))
    assert overview.status_code == 200, overview.text
    balances = {row["player_id"]: row for row in overview.json()["balances"]}
    assert balances[str(member.id)]["balance_pence"] == FEE, "paid 3, owed 1, repaid 1"
    assert balances[str(member.id)]["credit_pence"] == FEE
    assert balances[str(runner.id)]["owed_pence"] == 2 * FEE, "this round and the adjustment"
    assert overview.json()["season_pot"] == {
        "season": 2063,
        "label": "2063/64",
        "pot_pence": FEE,
    }, "the member's due is paid; the runner's is not"


async def test_assigning_a_queued_payment_remembers_the_payer(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        card_payer, app_payer = (
            await _profile(db, world, "card"),
            await _profile(db, world, "app"),
        )
        league = await _league(db, world, [card_payer, app_payer])
        await db.commit()
    tag = uuid.uuid4().hex[:8]
    card = LedgerEntry(
        league_id=league.id,
        kind=LedgerKind.payment,
        amount_pence=FEE,
        monzo_transaction_id=f"tx_card_{tag}",
        payer_name="J. Smith",
    )
    in_app = LedgerEntry(
        league_id=league.id,
        kind=LedgerKind.payment,
        amount_pence=2 * FEE,
        monzo_transaction_id=f"tx_app_{tag}",
        payer_monzo_user_id=f"user_{tag}",
        payer_name="Somebody Else",
    )
    await _record(league, card, in_app)
    base = f"/api/v1/leagues/{league.slug}/payments"

    queued = (await client.get(base, headers=_auth(site_admin))).json()["queued_payments"]
    assert {(row["payer_name"], row["amount_pence"]) for row in queued} == {
        ("J. Smith", FEE),
        ("Somebody Else", 2 * FEE),
    }

    first = await client.post(
        f"{base}/{card.id}/assign",
        json={"player_id": str(card_payer.id)},
        headers=_auth(site_admin),
    )
    assert first.status_code == 200, first.text
    assert (first.json()["player_id"], first.json()["remembered_by"]) == (
        str(card_payer.id),
        "name",
    )
    again = await client.post(
        f"{base}/{card.id}/assign",
        json={"player_id": str(app_payer.id)},
        headers=_auth(site_admin),
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "PAYMENT_ALREADY_ASSIGNED"
    second = await client.post(
        f"{base}/{in_app.id}/assign",
        json={"player_id": str(app_payer.id)},
        headers=_auth(site_admin),
    )
    assert second.json()["remembered_by"] == "monzo_user"

    async with AsyncSessionLocal() as db:
        mappings = {
            (row.monzo_user_id, row.normalised_name): row.player_id
            for row in (
                await db.execute(select(PayerMapping).where(PayerMapping.league_id == league.id))
            ).scalars()
        }
        stored = await db.get(LedgerEntry, card.id)
    assert mappings == {(None, "j smith"): card_payer.id, (f"user_{tag}", None): app_payer.id}
    assert stored is not None and stored.assigned_by == site_admin.id
    assert (await client.get(base, headers=_auth(site_admin))).json()["queued_payments"] == []


# ── The season pot ─────────────────────────────────────────────────────────────


async def test_the_season_pot_counts_each_seasons_paid_dues_across_the_boundary(
    session: AsyncSession,
) -> None:
    """Payments clear the oldest dues first, so arrears from May are paid before August."""
    steady, behind = (
        await _profile(session, None, "steady"),
        await _profile(session, None, "behind"),
    )
    league = await _league(session, None, [steady, behind])
    may = [_saturday(2065, 5, 1) + timedelta(weeks=n) for n in range(2)]
    august = [_saturday(2065, 8, 1) + timedelta(weeks=n) for n in range(2)]
    for starts_on in (*may, *august):
        gameweek = await _round(
            session, league, starts_on, status=GameweekStatus.settled, locks_in=-timedelta(days=1)
        )
        await record_round_dues(session, league, gameweek)
    session.add_all([_cash(league, steady, 4 * FEE), _cash(league, behind, 3 * FEE)])
    await session.flush()

    assert await season_pot(session, league.id, 2064) == 4 * FEE, "both paid both May weeks"
    assert await season_pot(session, league.id, 2065) == 3 * FEE, "one August week unpaid"
    assert await season_pot(session, league.id, 2066) == 0


async def test_erasure_forgets_the_payer_and_keeps_the_amounts(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        runner = await _profile(db, world, "runner")
        leaver = await _profile(db, world, "eraseme")
        league = await _league(db, world, [runner, leaver])
        db.add_all(
            [
                LedgerEntry(
                    league_id=league.id,
                    player_id=leaver.id,
                    kind=LedgerKind.payment,
                    amount_pence=FEE,
                    monzo_transaction_id=f"tx_{uuid.uuid4().hex[:8]}",
                    payer_monzo_user_id="user_erase",
                    payer_name=leaver.display_name,
                ),
                LedgerEntry(
                    league_id=league.id,
                    player_id=leaver.id,
                    kind=LedgerKind.adjustment,
                    amount_pence=-FEE,
                    note=f"owed from before: {leaver.display_name} said they'd pay",
                ),
                PayerMapping(league_id=league.id, player_id=leaver.id, monzo_user_id="user_erase"),
            ]
        )
        await db.commit()

    exported = await client.get("/api/v1/me/export", headers=_auth(leaver))
    assert exported.status_code == 200
    assert sorted(row["amount_pence"] for row in exported.json()["league_payments"]) == [-FEE, FEE]

    erased = await client.post("/api/v1/me/delete", json={"pin": PIN}, headers=_auth(leaver))
    assert erased.status_code == 204, erased.text
    entries = await _entries(league.id, leaver.id)
    assert sorted(entry.amount_pence for entry in entries) == [-FEE, FEE]
    assert {entry.payer_name for entry in entries} == {None}
    assert {entry.payer_monzo_user_id for entry in entries} == {None}
    assert all(leaver.display_name not in (entry.note or "") for entry in entries)
    async with AsyncSessionLocal() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(PayerMapping)
                .where(PayerMapping.player_id == leaver.id)
            )
        ) == 0


# ── The league's money, as every member sees it (Batch 212) ────────────────────


def test_the_full_season_estimate_counts_weekly_rounds_to_the_end_of_may() -> None:
    """One a week after the latest counted round to 31 May, plus declared extra weeks."""
    latest = _saturday(2072, 3, 19)  # Saturday 19 March 2072
    assert _rounds_ahead(2071, latest, latest, ()) == 10, "26 Mar to 28 May"
    extras = [date(2072, 3, 2), latest, date(2072, 4, 13), date(2072, 6, 10)]
    assert _rounds_ahead(2071, latest, latest, extras) == 11, "only 13 April is ahead"
    # Rounds paused six weeks ago: the gap is behind us, so the estimate starts this week.
    paused = latest - timedelta(weeks=6)
    assert _rounds_ahead(2071, latest, paused, ()) == 11
    assert _rounds_ahead(2071, latest, None, ()) == 11
    assert _rounds_ahead(2071, date(2072, 6, 5), latest, ()) == 0, "nothing left to guess"


async def test_the_money_read_sums_the_pot_both_targets_and_every_status(
    session: AsyncSession,
) -> None:
    """Payments, dues, a voided round, a cash-out, a charge, credit and a former member."""
    steady, saver, skint, owed_before, gone = [
        await _profile(session, None, name)
        for name in ("steady", "saver", "skint", "owed-before", "gone")
    ]
    league = await _league(session, None, [steady, saver, skint, owed_before, gone])
    assert await session.get(SeasonCalendar, 2071) is None, "season 2071 is this test's own"
    session.add(
        SeasonCalendar(
            season=2071,
            week_one_anchor=_saturday(2071, 8, 1),
            extra_weeks=[date(2072, 4, 13), date(2072, 6, 10)],
        )
    )
    settled = {"status": GameweekStatus.settled, "locks_in": -timedelta(days=1)}
    # Last season, steady alone owed a round, as if the others joined in the summer.
    last_season = await _round(session, league, _saturday(2071, 5, 1), **settled)
    session.add(
        LedgerEntry(
            league_id=league.id,
            player_id=steady.id,
            kind=LedgerKind.round_due,
            amount_pence=-FEE,
            gameweek_id=last_season.id,
        )
    )
    # Opened before the fee was set: it carries no due, so no target counts it.
    await _round(session, league, _saturday(2072, 2, 27), **settled)
    first = await _round(session, league, _saturday(2072, 3, 5), **settled)
    await record_round_dues(session, league, first)
    voided = await _round(session, league, _saturday(2072, 3, 12), **settled)
    await record_round_dues(session, league, voided)
    await reverse_round_dues(session, [voided.id], note=NOTE_ROUND_VOIDED)
    membership = (
        await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id, LeagueMembership.player_id == gone.id
            )
        )
    ).scalar_one()
    membership.deleted_at = _now()
    current = await _round(session, league, _saturday(2072, 3, 19))
    await record_round_dues(session, league, current)
    session.add_all(
        [
            _cash(league, steady, 3 * FEE),
            _cash(league, saver, 5 * FEE),
            LedgerEntry(
                league_id=league.id,
                player_id=saver.id,
                kind=LedgerKind.cash_out,
                amount_pence=-FEE,
            ),
            _cash(league, owed_before, 2 * FEE),
            LedgerEntry(
                league_id=league.id,
                player_id=owed_before.id,
                kind=LedgerKind.adjustment,
                amount_pence=-5 * FEE,
                note="owed before the app",
            ),
            _cash(league, gone, FEE),
        ]
    )
    await session.flush()

    money = await league_money(session, league, today=current.starts_on)

    assert money.season == 2071
    # The first round, charged to five, and this one, to the four still here.
    assert (money.rounds_to_date, money.per_person_to_date_pence) == (2, 2 * FEE)
    assert money.total_to_date_pence == 9 * FEE
    # Steady's and the saver's two rounds, and the former member's first: last season's
    # due takes steady's oldest pound, and owed-before's payments go to the earlier charge.
    assert money.pot_pence == 5 * FEE
    # Ten Saturdays from 26 March to 28 May, and the extra week of 13 April.
    assert money.rounds_full_season == 2 + 11
    assert money.per_person_full_season_pence == (2 + 11) * FEE
    assert money.total_full_season_pence == 9 * FEE + 11 * FEE * 4
    assert money.estimated_through == date(2072, 5, 31)
    assert money.balances == {
        steady.id: 0,
        saver.id: 2 * FEE,
        skint.id: -2 * FEE,
        owed_before.id: -5 * FEE,
    }, "a former member is not listed"


async def test_members_read_the_money_and_nothing_private_reaches_them(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        site_admin = await _profile(db, world, "owner", UserRole.admin)
        runner = await _profile(db, world, "runner")
        member = await _profile(db, world, "member")
        outsider = await _profile(db, world, "outsider")
        league = await _league(db, world, [runner, member])
        free = await _league(db, world, [runner], fee=None, link=None)
        db.add_all(
            [
                LedgerEntry(
                    league_id=league.id,
                    player_id=member.id,
                    kind=LedgerKind.payment,
                    amount_pence=2 * FEE,
                    monzo_transaction_id=f"tx_{uuid.uuid4().hex}",
                    payer_monzo_user_id="user_privatepayer",
                    payer_name="Private Payer",
                ),
                LedgerEntry(
                    league_id=league.id,
                    player_id=None,
                    kind=LedgerKind.payment,
                    amount_pence=FEE,
                    monzo_transaction_id=f"tx_{uuid.uuid4().hex}",
                    payer_name="Queued Stranger",
                ),
                LedgerEntry(
                    league_id=league.id,
                    player_id=runner.id,
                    kind=LedgerKind.adjustment,
                    amount_pence=-3 * FEE,
                    note="owed before the app",
                ),
            ]
        )
        await db.commit()
    url = f"/api/v1/leagues/{league.slug}/money"

    response = await client.get(url, headers=_auth(member))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "season",
        "label",
        "entry_fee_pence",
        "pot_pence",
        "target_to_date",
        "target_full_season",
        "short_of_target_pence",
        "members",
    }
    assert body["members"] == [
        {
            "player_id": str(runner.id),
            "display_name": runner.display_name,
            "status": "owes",
            "amount_pence": 3 * FEE,
        },
        {
            "player_id": str(member.id),
            "display_name": member.display_name,
            "status": "credit",
            "amount_pence": 2 * FEE,
        },
    ]
    assert body["entry_fee_pence"] == FEE
    full = body["target_full_season"]
    assert set(full) == {
        "rounds",
        "per_person_pence",
        "total_pence",
        "estimated_through",
        "is_estimate",
    }
    assert full["per_person_pence"] == full["rounds"] * FEE
    assert full["total_pence"] == full["per_person_pence"] * 2
    for private in ("Private Payer", "privatepayer", "Queued Stranger", "owed before", "tx_"):
        assert private not in response.text

    admin_read = await client.get(url, headers=_auth(site_admin))
    assert admin_read.status_code == 200, admin_read.text
    assert admin_read.json() == body
    assert (await client.get(url, headers=_auth(outsider))).status_code == 403
    no_fee = await client.get(f"/api/v1/leagues/{free.slug}/money", headers=_auth(runner))
    assert no_fee.status_code == 404


async def test_the_pay_panel_carries_an_earlier_charge_as_one_amount_without_its_note(
    client_and_fake: tuple[AsyncClient, FakeBetfair], world: World
) -> None:
    client, _fake = client_and_fake
    async with AsyncSessionLocal() as db:
        member = await _profile(db, world, "behind")
        league = await _league(db, world, [member])
        gameweek = await _round(db, league, _saturday(2064, 9, 1))
        await _open_with_dues(db, league, gameweek)
        db.add(
            LedgerEntry(
                league_id=league.id,
                player_id=member.id,
                kind=LedgerKind.adjustment,
                amount_pence=-3 * FEE,
                note="owed before the app",
            )
        )
        await db.commit()

    fee = await _fee_of(client, league, member, gameweek)
    assert fee["owed_pence"] == 4 * FEE
    assert [round_["amount_pence"] for round_ in fee["owed_rounds"]] == [FEE]
    assert fee["earlier_balance_pence"] == 3 * FEE, "the lines add up to what is asked"
    assert "owed before" not in str(fee)

    async with AsyncSessionLocal() as db:
        db.add(_cash(league, member, 3 * FEE))
        await db.commit()
    fee = await _fee_of(client, league, member, gameweek)
    assert (fee["owed_pence"], fee["earlier_balance_pence"]) == (FEE, 0)
