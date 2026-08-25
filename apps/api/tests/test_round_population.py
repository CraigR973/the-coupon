"""Batch 47 — a league gets its rounds when it is created, not at 06:00 tomorrow.

Fixture discovery runs once a day, so a league created at any other hour had no round,
no card and no coupon until the following morning, and the only remedy was a Railway
shell. The fix exploits what ``discover_fixtures``' own docstring already claimed: each
``(window, date)`` is fetched once and shared, so when the pool already holds a window's
fixtures a new league's rounds can be built from rows that exist — no provider request at
all.

What these tests hold to:

* creating a league on an already-pooled window issues **zero** upstream requests and
  still gets its rounds with fixtures linked;
* an empty pool falls back to a real fetch, and that fetch is charged to the same
  per-admin bucket the ad-hoc round endpoint spends, so neither can outspend it;
* a neighbour's one-off date produces no round for the new league — a creation-time
  populate walks the *cadence* only;
* "refresh rounds" may add fixtures to an unlocked round and may never move an instant
  of its own, and it does not touch a locked round at all;
* the settings edit itself *does* restamp both ends of the claim period, on unlocked
  rounds only — Batch 65, and the reverse of the rule the refresh still obeys.

Postgres-backed and **non-hermetic**: these drive the HTTP endpoints, which commit
through their own sessions. Every league here is given a window of its own — a distinct
weekday and minute — so the fixtures one test pools can never decide another's outcome.
Nothing hard-codes the horizon or the limit: both are read from the shipped settings, so
a change to either moves these tests with it rather than breaking them.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Collection
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from limits import parse_many
from sqlalchemy import select

from src.auth import create_access_token, hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.deps import get_odds_provider, get_optional_odds_provider
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMemberRole, LeagueMembership
from src.models.profile import Profile, UserRole
from src.routers.leagues import PROVIDER_SLATE_FETCH_LIMIT
from src.services.betfair import FakeBetfair
from src.services.gameweek import fixtures_for, pooled_slate, uk_today, upcoming_slate_dates
from src.services.odds_provider import UK_TZ, Slate, SlateWindow

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

MONDAY, TUESDAY, WEDNESDAY, THURSDAY = 0, 1, 2, 3


def _hourly_sweeps() -> int:
    """How many provider sweeps an admin may spend in an hour, read from the shipped limit."""
    return next(
        item.amount
        for item in parse_many(PROVIDER_SLATE_FETCH_LIMIT)
        if item.GRANULARITY.name == "hour"
    )


class CountingBetfair(FakeBetfair):
    """The canned provider with its slate fetches counted, and carrying nothing.

    One ``fetch_slate`` is one walk of the provider — an ``/events`` call per competition
    the league plays — so the call log is the thing under test rather than an
    implementation detail. Batch 47's whole claim is that the common case never reaches
    this class at all.

    Returning an empty slate is deliberate: a fetch that produced fixtures would blur
    "did it go upstream" with "did it get a round", and every test here asks the first
    question. The rounds these tests do get are built from fixtures they pool themselves.
    """

    def __init__(self) -> None:
        super().__init__()
        self.slate_calls: list[date] = []

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
        competition_names: Collection[str] | None = None,
        countries: Collection[str] = (),
    ) -> Slate:
        self.slate_calls.append(starts_on)
        return Slate(starts_on=starts_on, fixtures=[])


@pytest_asyncio.fixture
async def client_and_counter() -> AsyncIterator[tuple[AsyncClient, CountingBetfair]]:
    """An HTTP client whose odds provider counts every slate fetch."""
    counter = CountingBetfair()
    app.dependency_overrides[get_odds_provider] = lambda: counter
    app.dependency_overrides[get_optional_odds_provider] = lambda: counter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, counter
    app.dependency_overrides.pop(get_odds_provider, None)
    app.dependency_overrides.pop(get_optional_odds_provider, None)


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _player() -> Profile:
    """A player with an account, committed so the HTTP endpoints can authenticate them."""
    async with AsyncSessionLocal() as session:
        player = Profile(
            display_name=f"gaffer-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("1234"),
            role=UserRole.player,
        )
        session.add(player)
        await session.commit()
        await session.refresh(player)
        return player


def _window(weekday: int, minute: int) -> SlateWindow:
    """A point window on one weekday — the shape almost every league plays."""
    return SlateWindow(
        start_weekday=weekday, start_minute=minute, end_weekday=weekday, end_minute=minute
    )


def _cadence(window: SlateWindow) -> list[date]:
    """The dates a league on this window would populate — its whole horizon."""
    return upcoming_slate_dates(uk_today(), window, settings.slate_horizon_weeks)


async def _pool_fixture(starts_on: date, window: SlateWindow, *, competition_id: str) -> Fixture:
    """Put one kick-off inside ``window`` into the shared pool, as discovery would.

    Committed, because the endpoints under test read it through their own session.
    """
    kickoff = window.opens_at(starts_on).astimezone(UTC).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        fixture = Fixture(
            provider_event_id=f"ev-{uuid.uuid4().hex[:10]}",
            home=f"Home {uuid.uuid4().hex[:4]}",
            away=f"Away {uuid.uuid4().hex[:4]}",
            kickoff_utc=kickoff,
            competition="Test Division",
            competition_id=competition_id,
        )
        session.add(fixture)
        await session.commit()
        await session.refresh(fixture)
        return fixture


async def _pool_cadence(window: SlateWindow, *, competition_id: str) -> list[Fixture]:
    """One pooled fixture on every cadence date — the window another league already fetched."""
    return [
        await _pool_fixture(starts_on, window, competition_id=competition_id)
        for starts_on in _cadence(window)
    ]


async def _seed_league(admin: Profile, window: SlateWindow) -> League:
    """A league with this window, inserted directly — no populate, no budget spent."""
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(
            slug=f"cpn-{tag}",
            name=f"Coupon {tag}",
            created_by=admin.id,
            slate_start_weekday=window.start_weekday,
            slate_start_minute=window.start_minute,
            slate_end_weekday=window.end_weekday,
            slate_end_minute=window.end_minute,
            lock_offset_minutes=window.lock_offset_minutes,
        )
        session.add(league)
        await session.flush()
        session.add(
            LeagueMembership(league_id=league.id, player_id=admin.id, role=LeagueMemberRole.admin)
        )
        await session.commit()
        await session.refresh(league)
        return league


async def _create_league(
    client: AsyncClient, admin: Profile, window: SlateWindow, **extra: object
) -> str:
    """Create a league over HTTP — the path that populates rounds — and return its slug."""
    body: dict[str, object] = {
        "name": f"Coupon {uuid.uuid4().hex[:8]}",
        "slate_start_weekday": window.start_weekday,
        "slate_start_minute": window.start_minute,
        "slate_end_weekday": window.end_weekday,
        "slate_end_minute": window.end_minute,
        "lock_offset_minutes": window.lock_offset_minutes,
        **extra,
    }
    response = await client.post("/api/v1/leagues", json=body, headers=_auth(admin))
    assert response.status_code == 201, response.text
    return str(response.json()["slug"])


async def _rounds(slug: str) -> list[Gameweek]:
    """This league's rounds, oldest first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Gameweek)
            .join(League, League.id == Gameweek.league_id)
            .where(League.slug == slug)
            .order_by(Gameweek.starts_on)
        )
        return list(result.scalars().all())


def _first_unlocked(rounds: list[Gameweek]) -> tuple[int, Gameweek]:
    """The earliest round whose deadline is still ahead, with its position in the cadence.

    ``upcoming_slate_dates`` includes **today** by date alone, never by time of day, so a
    league created after its own window has already locked is born holding a round that
    can never move again — :func:`rederive_claim_periods` bounds itself on
    ``locks_at_utc > now``, deliberately. Taking ``rounds[0]`` therefore asserts on a
    round whose mutability depends on the wall clock: it is the round the members can see
    for most of the week, and a dead one for the hours after the window passes on the
    league's own weekday.

    Every league in this module plays a weekday of its own, so this fired on exactly one
    test on exactly one weekday — Tuesday, after 18:45 London — and passed the other
    167 hours.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    for index, gameweek in enumerate(rounds):
        if gameweek.locks_at_utc > now:
            return index, gameweek
    raise AssertionError(
        "the whole horizon has locked — a league cannot be created into a dead cadence"
    )


async def _linked(gameweek_id: uuid.UUID) -> set[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        return {fixture.id for fixture in await fixtures_for(session, gameweek_id)}


# ── Creation populates from the pool, for nothing ───────────────────────────────


async def test_a_league_created_on_a_pooled_window_costs_no_provider_requests(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """The common case, and the whole point of the batch.

    Almost every league plays a window some other league has already had discovery fetch,
    so its fixtures are sitting in the pool and its rounds are ``sync_slate`` against rows
    that exist. The league appears with a card instantly and the provider never hears
    about it.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(TUESDAY, 19 * 60)
    pooled = await _pool_cadence(window, competition_id="test-div-a")

    slug = await _create_league(client, admin, window)

    assert counter.slate_calls == [], "a pooled window must not reach the provider"
    rounds = await _rounds(slug)
    assert [r.starts_on for r in rounds] == _cadence(window), "the whole horizon, at once"
    for gameweek, fixture in zip(rounds, pooled, strict=True):
        assert await _linked(gameweek.id) == {fixture.id}


async def test_a_pooled_round_is_claimable_the_moment_the_league_exists(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """ "Instantly" has to mean pickable, not merely present.

    The round is built through the same ``sync_slate`` discovery uses, so it lands in the
    state ``initial_status`` gives it and its lock is derived from the league's own
    window — nothing about it says "created out of hours".
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(WEDNESDAY, 19 * 60 + 45)
    await _pool_cadence(window, competition_id="test-div-b")

    slug = await _create_league(client, admin, window)

    first = (await _rounds(slug))[0]
    assert first.status == GameweekStatus.open
    assert first.locks_at_utc == window.locks_at(first.starts_on)
    assert first.picks_open_at_utc is None  # no announced opening was configured
    assert first.number == 1
    assert counter.slate_calls == []


async def test_a_neighbours_one_off_date_produces_no_round_for_a_new_league(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """An off-cadence date belongs to the league that asked for it.

    ``discover_fixtures`` deliberately syncs one only to leagues already holding a round
    on it. A creation-time populate walks the cadence and nothing else, so a neighbour's
    Boxing Day is not invented for a league that never requested one — even though the
    fixtures for it are sitting in the same pool, which is exactly what would make the
    mistake invisible.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(THURSDAY, 20 * 60)
    cadence = _cadence(window)
    one_off = cadence[0] + timedelta(days=3)  # a Sunday this window never opens on

    await _pool_cadence(window, competition_id="test-div-c")
    # The neighbour's one-off: fixtures in the pool *and* a round already on the date.
    neighbour = await _seed_league(admin, window)
    off_cadence = await _pool_fixture(one_off, window, competition_id="test-div-c")
    async with AsyncSessionLocal() as session:
        gameweek = Gameweek(
            league_id=neighbour.id,
            starts_on=one_off,
            status=GameweekStatus.open,
            locks_at_utc=window.locks_at(one_off),
        )
        session.add(gameweek)
        await session.flush()
        session.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=off_cadence.id))
        await session.commit()

    slug = await _create_league(client, admin, window)

    assert [r.starts_on for r in await _rounds(slug)] == cadence
    assert counter.slate_calls == []


async def test_league_creation_survives_an_odds_provider_that_is_not_there(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """No provider is "pool only", never a failed creation.

    The populate is the only reason league creation touches the odds source at all, and
    it is a convenience. Wiring the ability to create a league to a third party being up
    would be a worse fault than the one this batch fixes.
    """
    client, _ = client_and_counter
    admin = await _player()
    app.dependency_overrides[get_optional_odds_provider] = lambda: None
    try:
        slug = await _create_league(client, admin, _window(MONDAY, 19 * 60 + 30))
    finally:
        app.dependency_overrides.pop(get_optional_odds_provider, None)

    assert await _rounds(slug) == [], "nothing to build from, and no error either"


# ── The fallback fetch, and the budget it shares ────────────────────────────────


async def test_an_empty_pool_falls_back_to_a_fetch_and_is_refused_past_the_shared_limit(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """A league inventing a window pays for it, visibly and boundedly.

    Nothing in the pool for either cadence date, so the first refresh spends the hourly
    allowance walking the provider. The second is refused *before* reaching it — which is
    the point: the response to being over a provider's budget cannot be more requests.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(TUESDAY, 20 * 60 + 15)
    league = await _seed_league(admin, window)
    allowance = min(_hourly_sweeps(), settings.slate_horizon_weeks)

    first = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks/refresh", headers=_auth(admin)
    )
    assert first.status_code == 200, first.text
    assert len(counter.slate_calls) == allowance, "one sweep per unpooled cadence date"
    assert first.json()["fetched_dates"] == [d.isoformat() for d in counter.slate_calls]
    assert first.json()["rounds"] == [], "the counting provider carries nothing for them"

    refused = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks/refresh", headers=_auth(admin)
    )
    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"] == "PROVIDER_BUDGET_EXHAUSTED"
    assert len(counter.slate_calls) == allowance, "a refusal must not reach the provider"


async def test_the_populate_path_and_the_ad_hoc_endpoint_share_one_budget(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """Two routes onto one provider, so two separate limits would simply be twice the limit.

    The arithmetic behind ``PROVIDER_SLATE_FETCH_LIMIT`` measures what odds-api.io's plan
    leaves spare for admin-triggered sweeps. It only holds if every route that can cause
    one draws down the same bucket.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(WEDNESDAY, 20 * 60 + 45)
    league = await _seed_league(admin, window)

    spend = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks/refresh", headers=_auth(admin)
    )
    assert spend.status_code == 200, spend.text
    spent = len(counter.slate_calls)
    assert spent == min(_hourly_sweeps(), settings.slate_horizon_weeks)

    ad_hoc = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks",
        json={"starts_on": _cadence(window)[0].isoformat()},
        headers=_auth(admin),
    )
    assert ad_hoc.status_code == 429, "the ad-hoc endpoint sees the bucket the refresh emptied"
    assert len(counter.slate_calls) == spent


async def test_a_pooled_refresh_costs_nothing_and_so_charges_nothing(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """The limit protects provider requests, not the endpoint.

    Charging the free case would price the common one out of existence: an admin who
    changed their window three times in an hour would be told to come back tomorrow for a
    rebuild that costs a single query.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(THURSDAY, 19 * 60 + 30)
    await _pool_cadence(window, competition_id="test-div-d")
    league = await _seed_league(admin, window)

    for _ in range(_hourly_sweeps() * 2):
        response = await client.post(
            f"/api/v1/leagues/{league.slug}/gameweeks/refresh", headers=_auth(admin)
        )
        assert response.status_code == 200, response.text
        assert response.json()["fetched_dates"] == []
    assert counter.slate_calls == []
    assert [r.starts_on for r in await _rounds(league.slug)] == _cadence(window)


# ── Refresh rounds: what it may change, and what it may not ─────────────────────


async def test_the_settings_edit_restamps_an_unlocked_round_and_the_refresh_leaves_it(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """Who may move a claim period, and who may not — the two halves in one journey.

    An admin who moves the fixture window has unlocked rounds built against the old one
    and, before Batch 47, waited for 06:00 to see the new card. A refresh rebuilds them
    from the pool at once.

    **The edit itself restamps both ends** on every round that has not locked (Batch 65).
    Until then neither instant was ever re-derived, and discovery writes a
    ``slate_horizon_weeks`` horizon ahead, so an admin who announced an opening changed
    nothing about any round their members could currently see — the setting appeared to
    do nothing for weeks.

    **The refresh must still not touch them.** Topping a round's card up from the pool is
    a different act from changing the settings, and a deadline that moved as a side effect
    of adding a fixture would be a deadline nobody decided to move.
    """
    client, counter = client_and_counter
    admin = await _player()
    before_window = _window(TUESDAY, 19 * 60 + 15)
    after_window = _window(TUESDAY, 18 * 60 + 15)
    old_card = await _pool_cadence(before_window, competition_id="test-div-e")

    slug = await _create_league(client, admin, before_window, pick_open_offset_minutes=2880)
    # Not `[0]`: on the league's own weekday that round may already have locked, and a
    # locked deadline is the one thing the edit must never move.
    cadence_index, before = _first_unlocked(await _rounds(slug))
    assert before.picks_open_at_utc is not None, "the league announced an opening"
    assert before.locks_at_utc == before_window.locks_at(before.starts_on)

    # The admin moves the window an hour earlier; that hour's fixtures are already pooled.
    new_card = await _pool_cadence(after_window, competition_id="test-div-e")
    moved = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={
            "slate_start_minute": after_window.start_minute,
            "slate_end_minute": after_window.end_minute,
        },
        headers=_auth(admin),
    )
    assert moved.status_code == 200, moved.text

    restamped = (await _rounds(slug))[cadence_index]
    assert restamped.locks_at_utc == after_window.locks_at(
        restamped.starts_on
    ), "the round the members can see follows the settings that describe it"
    assert restamped.picks_open_at_utc == after_window.utc_before_open(restamped.starts_on, 2880)
    opens_at, locks_at = restamped.picks_open_at_utc, restamped.locks_at_utc

    response = await client.post(f"/api/v1/leagues/{slug}/gameweeks/refresh", headers=_auth(admin))
    assert response.status_code == 200, response.text
    rebuilt = [
        r for r in response.json()["rounds"] if r["starts_on"] == before.starts_on.isoformat()
    ]
    assert rebuilt and rebuilt[0]["created"] is False, "the existing round, topped up in place"

    after = (await _rounds(slug))[cadence_index]
    assert after.picks_open_at_utc == opens_at, "a rebuild moves no instant of its own"
    assert after.locks_at_utc == locks_at
    # Both cards stay linked: a member may already hold a pick on the old one, and a
    # pooled slate carries no provider status, so nothing here can unlink anything.
    assert await _linked(after.id) == {old_card[cadence_index].id, new_card[cadence_index].id}
    assert counter.slate_calls == []


async def test_the_settings_edit_leaves_a_locked_rounds_deadline_alone(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """The half of the old rule that was load-bearing, kept.

    Members were told a deadline and claimed against it. An admin editing the window
    afterwards may reshape what has not happened yet and nothing else.
    """
    client, _ = client_and_counter
    admin = await _player()
    window = _window(THURSDAY, 20 * 60 + 15)
    await _pool_cadence(window, competition_id="test-div-h")

    slug = await _create_league(client, admin, window, pick_open_offset_minutes=2880)
    existing = (await _rounds(slug))[0]
    async with AsyncSessionLocal() as session:
        stored = await session.get(Gameweek, existing.id)
        assert stored is not None
        stored.status = GameweekStatus.locked
        await session.commit()
    frozen = (existing.picks_open_at_utc, existing.locks_at_utc)

    edited = await client.patch(
        f"/api/v1/leagues/{slug}",
        json={"lock_offset_minutes": 90, "pick_open_offset_minutes": 4320},
        headers=_auth(admin),
    )
    assert edited.status_code == 200, edited.text

    after = (await _rounds(slug))[0]
    assert (after.picks_open_at_utc, after.locks_at_utc) == frozen


async def test_refresh_rounds_leaves_a_locked_round_alone(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """A locked round's card is fixed and its picks are frozen.

    The same boundary ``unlocked_round_dates`` draws for the daily job: there is nothing
    a rebuild could legitimately change, so the date is reported as skipped rather than
    quietly rewritten under members who have already claimed on it.
    """
    client, counter = client_and_counter
    admin = await _player()
    window = _window(WEDNESDAY, 19 * 60 + 15)
    await _pool_cadence(window, competition_id="test-div-f")

    slug = await _create_league(client, admin, window)
    existing = (await _rounds(slug))[0]
    async with AsyncSessionLocal() as session:
        stored = await session.get(Gameweek, existing.id)
        assert stored is not None
        stored.status = GameweekStatus.locked
        await session.commit()

    # A fixture the refresh would otherwise link onto that round.
    await _pool_fixture(existing.starts_on, window, competition_id="test-div-f")

    response = await client.post(f"/api/v1/leagues/{slug}/gameweeks/refresh", headers=_auth(admin))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped_dates"] == [existing.starts_on.isoformat()]
    assert existing.starts_on.isoformat() not in [r["starts_on"] for r in body["rounds"]]

    assert len(await _linked(existing.id)) == 1, "the locked round kept the card it locked with"
    assert counter.slate_calls == []


async def test_refresh_rounds_is_an_admin_action(
    client_and_counter: tuple[AsyncClient, CountingBetfair],
) -> None:
    """It spends the league's provider budget and rebuilds its cards — not a member's call."""
    client, _ = client_and_counter
    admin = await _player()
    member = await _player()
    league = await _seed_league(admin, _window(THURSDAY, 18 * 60))
    async with AsyncSessionLocal() as session:
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        await session.commit()

    response = await client.post(
        f"/api/v1/leagues/{league.slug}/gameweeks/refresh", headers=_auth(member)
    )
    assert response.status_code == 403


# ── The pooled slate itself ─────────────────────────────────────────────────────


async def test_a_pooled_slate_carries_only_the_kick_offs_inside_the_window() -> None:
    """A pooled slate and a fetched one must be indistinguishable to ``sync_slate``.

    The pool holds every league's fixtures, so reading it back has to apply the same
    ``contains`` test a provider fetch is filtered by — whole days in SQL, the window
    itself in Python. A neighbouring league's lunchtime kick-off is in the same rows.
    """
    window = _window(TUESDAY, 15 * 60)
    starts_on = _cadence(window)[0]
    inside = await _pool_fixture(starts_on, window, competition_id="test-div-g")
    lunchtime = await _pool_fixture(
        starts_on, _window(TUESDAY, 12 * 60 + 30), competition_id="test-div-g"
    )

    async with AsyncSessionLocal() as session:
        slate = await pooled_slate(session, window, starts_on)

    events = {sf.provider_event_id for sf in slate.fixtures}
    assert slate.starts_on == starts_on
    assert inside.provider_event_id in events
    assert lunchtime.provider_event_id not in events, "same day, outside the window"


async def test_a_pooled_slate_reads_the_window_in_uk_local_time() -> None:
    """The window is anchored in ``Europe/London``; the pool is stored naive-UTC.

    Under BST those differ by an hour, so a read that compared the stored instant against
    the window's local minutes would drop every fixture in the summer half of the season
    — including the launch Saturday.
    """
    window = _window(TUESDAY, 15 * 60)
    starts_on = _cadence(window)[0]
    fixture = await _pool_fixture(starts_on, window, competition_id="test-div-h")

    local = fixture.kickoff_utc.replace(tzinfo=UTC).astimezone(UK_TZ)
    assert (local.hour, local.minute) == (15, 0), "stored an hour off its own window"

    async with AsyncSessionLocal() as session:
        slate = await pooled_slate(session, window, starts_on)
    assert fixture.provider_event_id in {sf.provider_event_id for sf in slate.fixtures}


async def test_a_pooled_slate_is_empty_when_nothing_has_been_discovered_for_the_date() -> None:
    """The condition that decides whether a populate has to pay: no rows, no slate."""
    window = _window(MONDAY, 11 * 60 + 5)
    async with AsyncSessionLocal() as session:
        slate = await pooled_slate(session, window, _cadence(window)[0])
    assert slate.fixtures == []
