"""Scheduler domain functions on real Postgres (canned odds via ``FakeBetfair``).

Covers the pieces the pure/unit tests can't — the DB-driven halves of the four jobs:

* ``refresh_slate``            — a provider slate becomes gameweek + fixtures (and an empty
  slate creates nothing), asking only for the competitions the league plays (Batch 35);
* ``latest_gameweek``          — which round a league is *currently on* when it holds a
  one-off outside its cadence (Batch 35), when its own round is being played (Batch 65),
  and when that round never settles; asserted against ``routers/me.py``'s window function
  on the same fixture data, because the rule is spelled twice and they must agree;
* ``rederive_claim_periods``   — a window edit restamps unlocked rounds and only those
  (Batch 65);
* ``lock_due_gameweeks``       — an open gameweek past 14:30 flips to ``locked``;
* ``open_due_gameweeks``       — a scheduled gameweek past its announced pick-open time
  flips to ``open`` (Batch 27), and one that never opened still locks;
* ``settle_gameweek_via_provider`` + ``standings`` — the **lock → settle → leaderboard**
  end-to-end: canned results settle the picks and the season table updates (the Batch 4
  slice of the acceptance e2e);
* ``settle_gameweeks_via_provider`` — a settle run reads a fixture two leagues both hold
  once rather than once per league (Batch 31);
* ``sync_slate``               — a fixture the provider reports called off comes off an
  open round with the pick on it, and comes off nothing else (Batch 49);
* ``members_missing_picks``    — only members without a pick are reminder candidates;
* gameweek selection helpers   — ``current_open_gameweeks`` / ``settleable_gameweeks``.

Skipped unless ``DATABASE_URL`` points at a migrated database (the repo runs it via the
pgserver harness). Each test does all its work inside one session and never commits, so the
suite stays hermetic regardless of order.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.routers.me import _latest_rounds
from src.services.betfair import (
    SAMPLE_ARSENAL_SEL,
    SAMPLE_EPL_EVENT_ID,
    SAMPLE_EPL_ID,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_EVENT_ID,
    SAMPLE_SL2_ID,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.gameweek import (
    IN_PLAY_GRACE_MINUTES,
    current_open_gameweeks,
    discover_fixtures,
    fixtures_for,
    latest_gameweek,
    lock_due_gameweeks,
    members_missing_picks,
    open_due_gameweeks,
    picks_open_at,
    rederive_claim_periods,
    refresh_slate,
    settleable_gameweeks,
    sync_slate,
    uk_today,
    window_for,
)
from src.services.odds_provider import SATURDAY_THREE_PM, EventSettlement, Slate, SlateFixture
from src.services.scoring import (
    settle_gameweek_via_provider,
    settle_gameweeks_via_provider,
    standings,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session that is always rolled back — nothing these tests write persists."""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _seed_league(db: AsyncSession, names: list[str]) -> tuple[dict[str, Profile], League]:
    """Create players + a league they all belong to (flush only — no commit)."""
    tag = uuid.uuid4().hex[:8]
    players = {
        name: Profile(display_name=f"{name}-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
        for name in names
    }
    db.add_all(list(players.values()))
    await db.flush()
    league = League(
        slug=f"cpn-{tag}", name=f"Coupon {tag}", created_by=next(iter(players.values())).id
    )
    db.add(league)
    await db.flush()
    for player in players.values():
        db.add(LeagueMembership(league_id=league.id, player_id=player.id))
    await db.flush()
    return players, league


async def _open_gameweek(
    db: AsyncSession, league: League, starts_on: date
) -> tuple[Gameweek, Fixture, Fixture]:
    """An open round for ``league`` playing the two sample fixtures (EPL, SL2).

    Fixtures go into the shared pool and are linked to the round, which is how a
    second league can be given the same card without a second row.
    """
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=GameweekStatus.open,
        locks_at_utc=window_for(league).locks_at(starts_on),
    )
    db.add(gameweek)
    await db.flush()
    kickoff = datetime(starts_on.year, starts_on.month, starts_on.day, 14, 0)

    fixtures = []
    for event_id, home, away, competition, competition_id in (
        (SAMPLE_EPL_EVENT_ID, "Arsenal", "Chelsea", "English Premier League", "10932509"),
        (
            SAMPLE_SL2_EVENT_ID,
            "Forfar Athletic",
            "Brechin City",
            "Scottish League Two",
            "10932510",
        ),
    ):
        existing = await db.execute(select(Fixture).where(Fixture.provider_event_id == event_id))
        fixture = existing.scalar_one_or_none()
        if fixture is None:
            fixture = Fixture(
                provider_event_id=event_id,
                home=home,
                away=away,
                kickoff_utc=kickoff,
                competition=competition,
                competition_id=competition_id,
            )
            db.add(fixture)
            await db.flush()
        db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
        fixtures.append(fixture)
    await db.flush()
    return gameweek, fixtures[0], fixtures[1]


def _pick(
    league: League,
    gameweek: Gameweek,
    fixture: Fixture,
    player: Profile,
    outcome: PickOutcome,
    runner_name: str,
    odds: str,
) -> Pick:
    return Pick(
        league_id=league.id,
        gameweek_id=gameweek.id,
        fixture_id=fixture.id,
        player_id=player.id,
        market=PickMarket.MATCH_ODDS,
        outcome=outcome,
        runner_name=runner_name,
        odds_at_pick=Decimal(odds),
    )


# ── refresh_slate ───────────────────────────────────────────────────────────────


async def test_refresh_slate_syncs_fixtures_and_skips_empty(session: AsyncSession) -> None:
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    gameweek = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert gameweek is not None
    assert gameweek.starts_on == SAMPLE_SATURDAY
    assert gameweek.league_id == league.id
    fixtures = await fixtures_for(session, gameweek.id)
    assert {"Arsenal", "Forfar Athletic"} <= {f.home for f in fixtures}

    # A date the provider prices nothing for → no round is created.
    assert await refresh_slate(session, fake, league, date(2030, 1, 5)) is None


async def test_discovery_walks_the_horizon_and_skips_barren_dates(
    session: AsyncSession,
) -> None:
    """The daily job pre-fetches fixtures ahead of time, without pricing them."""
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    # A horizon starting the week before the sample Saturday: the first date carries
    # the canned card, the rest carry nothing.
    discovered = await discover_fixtures(
        session, fake, [league], SAMPLE_SATURDAY - timedelta(days=2), 3
    )

    assert [g.starts_on for g in discovered] == [SAMPLE_SATURDAY]
    assert len(await fixtures_for(session, discovered[0].id)) >= 2


async def test_discovery_is_idempotent_across_days(session: AsyncSession) -> None:
    """It runs daily against the same round, so a re-run must not duplicate rows."""
    _, league = await _seed_league(session, ["solo"])
    fake = FakeBetfair.with_sample_data()

    first = await discover_fixtures(session, fake, [league], SAMPLE_SATURDAY, 1)
    before = await fixtures_for(session, first[0].id)

    second = await discover_fixtures(session, fake, [league], SAMPLE_SATURDAY, 1)
    after = await fixtures_for(session, second[0].id)

    assert second[0].id == first[0].id
    assert len(after) == len(before)


async def test_two_leagues_on_one_window_cost_a_single_provider_fetch(
    session: AsyncSession,
) -> None:
    """The whole point of the shared pool: a second league on the same window is free.

    This is the property the request budget depends on. If discovery ever fetches
    per league instead of per window, the provider bill scales with membership and
    the free plan stops being enough.
    """
    _, first = await _seed_league(session, ["alice"])
    _, second = await _seed_league(session, ["bob"])
    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []

    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date) -> object:
        calls.append(starts_on)
        return await original(window, starts_on)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    discovered = await discover_fixtures(session, fake, [first, second], SAMPLE_SATURDAY, 1)

    assert len(calls) == 1, "one window, one date — one fetch, however many leagues"
    assert len(discovered) == 2, "but both leagues get their own round"
    assert {g.league_id for g in discovered} == {first.id, second.id}

    # …drawing on the same pooled fixture rows, not copies.
    first_fixtures = {f.id for f in await fixtures_for(session, discovered[0].id)}
    second_fixtures = {f.id for f in await fixtures_for(session, discovered[1].id)}
    assert first_fixtures == second_fixtures
    assert first_fixtures, "the round is not empty"


async def test_a_different_window_costs_its_own_fetch(session: AsyncSession) -> None:
    """Only a genuinely different window adds provider cost."""
    _, saturday_league = await _seed_league(session, ["alice"])
    _, friday_league = await _seed_league(session, ["bob"])
    friday_league.slate_start_weekday = 4  # Friday
    friday_league.slate_end_weekday = 0  # through Monday
    await session.flush()

    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []
    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date) -> object:
        calls.append(starts_on)
        return await original(window, starts_on)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    await discover_fixtures(session, fake, [saturday_league, friday_league], SAMPLE_SATURDAY, 1)
    assert len(calls) == 2, "two distinct windows, two fetches"


# ── Batch 15: the per-league competition selection (link-time filter) ────────────


async def test_sync_slate_plays_only_the_leagues_selected_competitions(
    session: AsyncSession,
) -> None:
    """A league that plays only the EPL gets the EPL fixture and not the Scottish one.

    The selection is applied at link time, so the same shared fetch feeds a narrowed
    league a subset of its fixtures without a second provider request.
    """
    _, league = await _seed_league(session, ["epl-only"])
    league.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    await session.flush()
    fake = FakeBetfair.with_sample_data()

    gameweek = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert gameweek is not None
    fixtures = await fixtures_for(session, gameweek.id)
    assert {f.competition_id for f in fixtures} == {SAMPLE_EPL_ID}
    assert [f.home for f in fixtures] == ["Arsenal"], "the Scottish fixture must be excluded"


async def test_sync_slate_records_no_round_when_the_selection_excludes_every_fixture(
    session: AsyncSession,
) -> None:
    """A league playing none of a window's competitions gets no round, not an empty one."""
    _, league = await _seed_league(session, ["none-of-these"])
    league.competitions = [{"slug": "a-competition-not-on-this-slate", "name": "Elsewhere"}]
    await session.flush()
    fake = FakeBetfair.with_sample_data()

    # The provider *does* carry fixtures for this date — they are just not this league's.
    assert await refresh_slate(session, fake, league, SAMPLE_SATURDAY) is None
    # And an all-UK league on the same date still gets its round from the same data.
    _, all_uk = await _seed_league(session, ["all-uk"])
    assert await refresh_slate(session, fake, all_uk, SAMPLE_SATURDAY) is not None


async def test_narrowing_after_a_round_exists_keeps_the_round_but_stops_adding(
    session: AsyncSession,
) -> None:
    """Narrowing the selection does not strip a fixture a member may already hold.

    The only thing that unlinks is the provider reporting a fixture called off (Batch
    49); a competition dropping out of the league's selection is not that.

    The Scottish fixture linked while the league was all-UK stays put; a later refresh
    under an EPL-only selection simply adds nothing new.
    """
    _, league = await _seed_league(session, ["was-broad"])
    fake = FakeBetfair.with_sample_data()

    first = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert first is not None
    assert {SAMPLE_EPL_ID, SAMPLE_SL2_ID} == {
        f.competition_id for f in await fixtures_for(session, first.id)
    }

    league.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    await session.flush()
    again = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)
    assert again is not None and again.id == first.id
    # Both fixtures remain: the existing SL2 link is preserved even though it is no
    # longer selected, because a pick may already stand on it.
    assert {SAMPLE_EPL_ID, SAMPLE_SL2_ID} == {
        f.competition_id for f in await fixtures_for(session, again.id)
    }


# ── Batch 49: a called-off fixture comes off an open round ─────────────────────
#
# `sync_slate` used to say it outright — "Links are added, never removed" — so a fixture
# postponed after discovery stayed on every round that had linked it, stayed pickable, and
# stayed pickable right through the deadline. Nothing between discovery and the evening
# settle sweep read the provider's status at all.
#
# The four tests below fix the shape of the answer, and three of them are about what must
# *not* happen: only an explicit void status removes anything, only before the lock, and
# only from the round that is still open.


def _upcoming_saturday() -> date:
    """A Saturday whose 14:30 lock is still ahead of now.

    The removal gate is the lock *instant*, not the round's status label, so a round
    dated in the past would be refused however it is labelled — which would make these
    tests pass for the wrong reason.
    """
    return SATURDAY_THREE_PM.first_start_on_or_after(uk_today() + timedelta(days=7))


def _naive_now() -> datetime:
    """Naive-UTC now, matching the ``*_utc`` storage convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def _slate_of(
    starts_on: date, fixtures: Sequence[Fixture], *, postponed: Collection[str] = ()
) -> Slate:
    """A provider card for ``starts_on``, echoing back pooled rows.

    ``postponed`` names the ``provider_event_id``s the provider reports called off.
    Everything else comes back ``pending``, which is what odds-api.io says for a fixture
    that is still on — 1,597 of the 1,599 it listed for 2026-08-22, measured the day
    before.
    """
    return Slate(
        starts_on=starts_on,
        fixtures=[
            SlateFixture(
                provider_event_id=fixture.provider_event_id,
                home=fixture.home,
                away=fixture.away,
                kickoff_utc=fixture.kickoff_utc,
                competition=fixture.competition,
                competition_id=fixture.competition_id,
                status="postponed" if fixture.provider_event_id in postponed else "pending",
            )
            for fixture in fixtures
        ],
    )


def _capture_notifications(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record what ``sync_slate`` would push, rather than delivering it."""
    sent: list[dict[str, Any]] = []

    async def _record(
        db: AsyncSession,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        **_: Any,
    ) -> int:
        sent.append({"user_id": user_id, "title": title, "body": body, "data": data or {}})
        return 1

    monkeypatch.setattr("src.services.gameweek.send_notification", _record)
    return sent


class _VoidingFake(FakeBetfair):
    """A provider that reports every fixture asked about as called off.

    The settle-side of a postponement, which is the half that already worked.
    """

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return [
            EventSettlement(provider_event_id=eid, status="postponed", settled=True, void=True)
            for eid in event_ids
        ]


async def test_a_postponed_fixture_comes_off_an_open_round_with_the_pick_on_it(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both rows go — the link and the pick — and the member is told.

    Deleting the link alone would leave the pick alive and pointing at a fixture no
    longer on its round: off the screen, still found by settlement. What the member is
    left with is *no pick*, the one state the game already understands, so the selection
    returns to the land-grab and the 11:00 reminder nudges them if they don't use it.
    """
    players, league = await _seed_league(session, ["alice", "bob"])
    starts_on = _upcoming_saturday()
    gameweek, epl, sl2 = await _open_gameweek(session, league, starts_on)
    session.add_all(
        [
            _pick(
                league, gameweek, sl2, players["alice"], PickOutcome.HOME, "Forfar Athletic", "2.50"
            ),
            _pick(league, gameweek, epl, players["bob"], PickOutcome.HOME, "Arsenal", "1.90"),
        ]
    )
    await session.flush()
    sent = _capture_notifications(monkeypatch)

    await sync_slate(
        session, league, _slate_of(starts_on, [epl, sl2], postponed={SAMPLE_SL2_EVENT_ID})
    )

    assert [f.provider_event_id for f in await fixtures_for(session, gameweek.id)] == [
        SAMPLE_EPL_EVENT_ID
    ]
    surviving = (
        (await session.execute(select(Pick).where(Pick.gameweek_id == gameweek.id))).scalars().all()
    )
    assert [p.player_id for p in surviving] == [players["bob"].id], "only the stranded pick goes"

    assert [(s["user_id"], s["data"]["type"]) for s in sent] == [
        (players["alice"].id, "fixture_postponed")
    ]
    assert "Forfar Athletic v Brechin City" in sent[0]["body"]
    assert sent[0]["data"]["url"] == f"/leagues/{league.slug}/predictions"


async def test_a_postponed_fixture_stays_on_a_locked_round_and_settles_void(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the deadline the pick stands, because the member can no longer respond.

    Deleting it then would make them indistinguishable in the standings from someone who
    never picked at all. ``void`` already means "scores nothing rather than counting as a
    loss", and settlement already writes it for exactly this status — so the locked case
    needs no new code, only a refusal here.
    """
    players, league = await _seed_league(session, ["alice"])
    starts_on = _upcoming_saturday()
    gameweek, epl, sl2 = await _open_gameweek(session, league, starts_on)
    gameweek.locks_at_utc = _naive_now() - timedelta(minutes=1)
    gameweek.status = GameweekStatus.locked
    pick = _pick(
        league, gameweek, sl2, players["alice"], PickOutcome.HOME, "Forfar Athletic", "2.50"
    )
    session.add(pick)
    await session.flush()
    sent = _capture_notifications(monkeypatch)

    await sync_slate(
        session, league, _slate_of(starts_on, [epl, sl2], postponed={SAMPLE_SL2_EVENT_ID})
    )

    assert {f.provider_event_id for f in await fixtures_for(session, gameweek.id)} == {
        SAMPLE_EPL_EVENT_ID,
        SAMPLE_SL2_EVENT_ID,
    }
    assert pick.status is PickStatus.pending
    assert sent == [], "nothing was taken away, so there is nothing to tell them"

    assert await settle_gameweek_via_provider(session, _VoidingFake(), gameweek) == 1
    assert pick.status is PickStatus.void
    assert pick.points_awarded == 0


async def test_a_fixture_merely_absent_from_a_refresh_is_never_removed(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absence is not a postponement, and must never be read as one.

    ``discover_fixtures`` skips any date the provider returns nothing for, and a partial
    or failed fetch is indistinguishable from a quiet one. Unlinking on "the fixture
    vanished from this refresh" would let one provider hiccup strip a whole round of live
    picks.
    """
    players, league = await _seed_league(session, ["alice"])
    starts_on = _upcoming_saturday()
    gameweek, epl, sl2 = await _open_gameweek(session, league, starts_on)
    session.add(
        _pick(league, gameweek, sl2, players["alice"], PickOutcome.HOME, "Forfar Athletic", "2.50")
    )
    await session.flush()
    sent = _capture_notifications(monkeypatch)

    # A partial card — the Scottish fixture simply is not in it.
    await sync_slate(session, league, _slate_of(starts_on, [epl]))
    # And then a card with nothing in it at all.
    await sync_slate(session, league, Slate(starts_on=starts_on, fixtures=[]))

    assert {f.provider_event_id for f in await fixtures_for(session, gameweek.id)} == {
        SAMPLE_EPL_EVENT_ID,
        SAMPLE_SL2_EVENT_ID,
    }
    picks = (
        (await session.execute(select(Pick).where(Pick.gameweek_id == gameweek.id))).scalars().all()
    )
    assert [p.player_id for p in picks] == [players["alice"].id]
    assert sent == []


async def test_only_the_open_round_loses_a_fixture_two_rounds_share(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One pooled match, two leagues' cards, one deadline passed — one removal.

    Removal is per round because the lock is per round. The pooled ``fixtures`` row
    itself is never touched: the locked round still plays it and settlement still has to
    resolve the pick standing on it, which is why the status is carried on the slate DTO
    rather than stored.
    """
    open_players, open_league = await _seed_league(session, ["alice"])
    locked_players, locked_league = await _seed_league(session, ["bob"])
    starts_on = _upcoming_saturday()
    open_gw, epl, sl2 = await _open_gameweek(session, open_league, starts_on)
    locked_gw, epl_again, sl2_again = await _open_gameweek(session, locked_league, starts_on)
    assert (epl_again.id, sl2_again.id) == (epl.id, sl2.id), "one pooled row, two cards"
    locked_gw.locks_at_utc = _naive_now() - timedelta(minutes=1)
    locked_gw.status = GameweekStatus.locked
    session.add_all(
        [
            _pick(
                open_league,
                open_gw,
                sl2,
                open_players["alice"],
                PickOutcome.HOME,
                "Forfar Athletic",
                "2.50",
            ),
            _pick(
                locked_league,
                locked_gw,
                sl2,
                locked_players["bob"],
                PickOutcome.HOME,
                "Forfar Athletic",
                "2.50",
            ),
        ]
    )
    await session.flush()
    sent = _capture_notifications(monkeypatch)

    slate = _slate_of(starts_on, [epl, sl2], postponed={SAMPLE_SL2_EVENT_ID})
    await sync_slate(session, open_league, slate)
    await sync_slate(session, locked_league, slate)

    assert {f.provider_event_id for f in await fixtures_for(session, open_gw.id)} == {
        SAMPLE_EPL_EVENT_ID
    }
    assert {f.provider_event_id for f in await fixtures_for(session, locked_gw.id)} == {
        SAMPLE_EPL_EVENT_ID,
        SAMPLE_SL2_EVENT_ID,
    }
    assert await session.get(Fixture, sl2.id) is not None, "the pooled row stays in the pool"
    assert [s["user_id"] for s in sent] == [open_players["alice"].id]


# ── Batch 35: the ad-hoc fetch buys only what the league plays ──────────────────
#
# Asserted on the *requests issued* rather than the rows written, because the rows were
# already right — `sync_slate` filtered them at link time. What was wrong was paying for
# ~30 UK competitions to keep as few as one, and only a request count can see that.
# `BetfairAdapter.fetch_slate` calls `list_events` once per competition, which is the
# same one-request-per-competition fan-out the live odds-api.io client pays.


def _count_competition_requests(fake: FakeBetfair, asked: list[list[str]]) -> None:
    """Record the competitions each ``list_events`` request covers, in order."""
    original = fake.list_events

    async def counting_list_events(
        *, competition_ids: Sequence[str], from_utc: datetime, to_utc: datetime
    ) -> list[Any]:
        asked.append(list(competition_ids))
        return await original(competition_ids=competition_ids, from_utc=from_utc, to_utc=to_utc)

    fake.list_events = counting_list_events  # type: ignore[method-assign]


async def test_an_ad_hoc_fetch_asks_only_for_the_competitions_the_league_plays(
    session: AsyncSession,
) -> None:
    """One league, one date, a fetch nobody shares — so there is no sharing to protect."""
    _, league = await _seed_league(session, ["epl-only"])
    league.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    await session.flush()

    fake = FakeBetfair.with_sample_data()
    asked: list[list[str]] = []
    _count_competition_requests(fake, asked)

    gameweek = await refresh_slate(session, fake, league, SAMPLE_SATURDAY)

    assert gameweek is not None
    assert asked == [[SAMPLE_EPL_ID]], "one request, for the one competition this league plays"
    assert [f.competition_id for f in await fixtures_for(session, gameweek.id)] == [SAMPLE_EPL_ID]


async def test_an_unconfigured_league_still_pays_for_every_competition(
    session: AsyncSession,
) -> None:
    """All-UK is a genuine selection, not a missing one — narrowing must not invent it."""
    _, league = await _seed_league(session, ["all-uk"])
    fake = FakeBetfair.with_sample_data()
    asked: list[list[str]] = []
    _count_competition_requests(fake, asked)

    assert await refresh_slate(session, fake, league, SAMPLE_SATURDAY) is not None
    assert len(asked) == 3, "every canned competition, one request each"


async def test_shared_discovery_does_not_narrow_its_fetch(session: AsyncSession) -> None:
    """The inverse of the rule above, and the reason it is a per-call argument.

    Discovery's fetch is shared by every league on the window, so narrowing it to one
    league's selection would save that league's requests by denying the next league its
    fixtures. The EPL-only league here must not shrink the Scottish league's card.
    """
    _, narrowed = await _seed_league(session, ["epl-only"])
    narrowed.competitions = [{"slug": SAMPLE_EPL_ID, "name": "English Premier League"}]
    _, all_uk = await _seed_league(session, ["all-uk"])
    await session.flush()

    fake = FakeBetfair.with_sample_data()
    asked: list[list[str]] = []
    _count_competition_requests(fake, asked)

    discovered = await discover_fixtures(session, fake, [narrowed, all_uk], SAMPLE_SATURDAY, 1)

    assert len(asked) == 3, "the shared fetch still walks every competition"
    by_league = {g.league_id: g for g in discovered}
    assert {SAMPLE_EPL_ID} == {
        f.competition_id for f in await fixtures_for(session, by_league[narrowed.id].id)
    }
    assert {SAMPLE_EPL_ID, SAMPLE_SL2_ID} == {
        f.competition_id for f in await fixtures_for(session, by_league[all_uk.id].id)
    }


# ── Batch 35: discovery reaches a round off the league's cadence ────────────────
#
# `upcoming_slate_dates` only ever yields the weekly cadence, so before this an ad-hoc
# round was frozen at whatever the provider held when the admin created it — a
# postponement, a late addition or a corrected kick-off never landed, and since
# `sync_slate` only adds links the round could not self-correct either.
#
# The canned card sits on a Saturday, so these leagues play a *Sunday* window: that makes
# 2026-08-01 off their cadence while still being a date the fake carries fixtures for.

SUNDAY = 6


async def _sunday_league(session: AsyncSession, name: str) -> League:
    """A league whose cadence is Sundays — so the canned Saturday is off it."""
    _, league = await _seed_league(session, [name])
    league.slate_start_weekday = SUNDAY
    league.slate_end_weekday = SUNDAY
    await session.flush()
    return league


async def _bare_round(session: AsyncSession, league: League, starts_on: date) -> Gameweek:
    """An open round with no fixtures linked yet — an ad-hoc one before its refresh."""
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=GameweekStatus.open,
        locks_at_utc=window_for(league).locks_at(starts_on),
    )
    session.add(gameweek)
    await session.flush()
    return gameweek


async def test_discovery_refreshes_an_unlocked_round_off_the_cadence(
    session: AsyncSession,
) -> None:
    """The Boxing Day case: nothing else would ever revisit this round."""
    league = await _sunday_league(session, "one-off")
    one_off = await _bare_round(session, league, SAMPLE_SATURDAY)
    assert await fixtures_for(session, one_off.id) == []

    await discover_fixtures(session, FakeBetfair.with_sample_data(), [league], SAMPLE_SATURDAY, 1)

    assert len(await fixtures_for(session, one_off.id)) == 2, "the card finally landed"


async def test_an_off_cadence_date_is_not_synced_to_the_leagues_that_did_not_ask(
    session: AsyncSession,
) -> None:
    """A neighbour on the same window must not have a Boxing Day round invented for it."""
    asked_for_it = await _sunday_league(session, "one-off")
    neighbour = await _sunday_league(session, "cadence-only")
    await _bare_round(session, asked_for_it, SAMPLE_SATURDAY)

    await discover_fixtures(
        session, FakeBetfair.with_sample_data(), [asked_for_it, neighbour], SAMPLE_SATURDAY, 1
    )

    rounds = await session.execute(
        select(Gameweek.starts_on).where(Gameweek.league_id == neighbour.id)
    )
    assert SAMPLE_SATURDAY not in set(rounds.scalars().all())


async def test_two_leagues_sharing_an_off_cadence_date_share_one_fetch(
    session: AsyncSession,
) -> None:
    """Grouping is still by window, so a date two leagues both added costs one request."""
    first = await _sunday_league(session, "boxing-day-a")
    second = await _sunday_league(session, "boxing-day-b")
    await _bare_round(session, first, SAMPLE_SATURDAY)
    await _bare_round(session, second, SAMPLE_SATURDAY)

    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []
    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date, **kwargs: object) -> object:
        calls.append(starts_on)
        return await original(window, starts_on, **kwargs)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    await discover_fixtures(session, fake, [first, second], SAMPLE_SATURDAY, 1)

    assert calls.count(SAMPLE_SATURDAY) == 1, "one window, one date — one fetch"
    for league in (first, second):
        round_on_the_date = await session.execute(
            select(Gameweek).where(
                Gameweek.league_id == league.id, Gameweek.starts_on == SAMPLE_SATURDAY
            )
        )
        assert len(await fixtures_for(session, round_on_the_date.scalar_one().id)) == 2


async def test_a_locked_round_is_not_refetched(session: AsyncSession) -> None:
    """Its card is fixed and its picks are frozen, so a refresh could not record anything."""
    league = await _sunday_league(session, "already-locked")
    one_off = await _bare_round(session, league, SAMPLE_SATURDAY)
    one_off.status = GameweekStatus.locked
    await session.flush()

    fake = FakeBetfair.with_sample_data()
    calls: list[date] = []
    original = fake.fetch_slate

    async def counting_fetch_slate(window: object, starts_on: date, **kwargs: object) -> object:
        calls.append(starts_on)
        return await original(window, starts_on, **kwargs)  # type: ignore[arg-type]

    fake.fetch_slate = counting_fetch_slate  # type: ignore[method-assign]

    await discover_fixtures(session, fake, [league], SAMPLE_SATURDAY, 1)

    assert SAMPLE_SATURDAY not in calls
    assert await fixtures_for(session, one_off.id) == []


# ── Batch 35: which round a league is currently on ─────────────────────────────
#
# Until now `latest_gameweek` ordered `starts_on DESC LIMIT 1`, so a one-off round added
# outside the cadence hijacked "this week" for that league alone — and home renders every
# league's card side by side, which is where it reads as broken rather than as a setting.
# Dates here are relative to today so the rule is exercised against the real clock.


def _next_saturday_ahead() -> date:
    """The first Saturday strictly after today, so its 14:30 lock is always in the future."""
    return SATURDAY_THREE_PM.first_start_on_or_after(uk_today() + timedelta(days=1))


async def test_a_far_future_one_off_does_not_hijack_this_week(session: AsyncSession) -> None:
    """Boxing Day added in August must not become the round the league is on."""
    _, league = await _seed_league(session, ["boxing-day"])
    saturday = _next_saturday_ahead()
    await _bare_round(session, league, saturday)
    await _bare_round(session, league, saturday + timedelta(weeks=20))

    current = await latest_gameweek(session, league.id)

    assert current is not None and current.starts_on == saturday


async def test_two_open_rounds_are_tie_broken_by_which_shuts_first(
    session: AsyncSession,
) -> None:
    """The load-bearing half of the rule: act on the round that closes first.

    The midweek one-off starts *earlier* than the Saturday, so the old "newest
    ``starts_on``" rule picks the Saturday and this one picks the round a member has
    hours rather than days to act on.
    """
    _, league = await _seed_league(session, ["both-open"])
    saturday = _next_saturday_ahead() + timedelta(weeks=1)
    midweek = saturday - timedelta(days=3)
    await _bare_round(session, league, saturday)
    await _bare_round(session, league, midweek)

    current = await latest_gameweek(session, league.id)

    assert current is not None and current.starts_on == midweek


async def test_with_nothing_open_the_round_just_played_wins(session: AsyncSession) -> None:
    """A settled league shows its last round, not the first of next season."""
    _, league = await _seed_league(session, ["between-rounds"])
    today = uk_today()
    for starts_on in (today - timedelta(days=14), today - timedelta(days=7)):
        gameweek = await _bare_round(session, league, starts_on)
        gameweek.status = GameweekStatus.settled
    await session.flush()

    current = await latest_gameweek(session, league.id)

    assert current is not None and current.starts_on == today - timedelta(days=7)


async def test_a_season_not_yet_started_shows_the_earliest_round_ahead(
    session: AsyncSession,
) -> None:
    """The last fallback — and the one "newest ``starts_on``" got exactly backwards."""
    _, league = await _seed_league(session, ["not-started"])
    today = uk_today()
    for starts_on in (today + timedelta(days=30), today + timedelta(days=60)):
        gameweek = await _bare_round(session, league, starts_on)
        gameweek.status = GameweekStatus.scheduled
        gameweek.picks_open_at_utc = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=20)
    await session.flush()

    current = await latest_gameweek(session, league.id)

    assert current is not None and current.starts_on == today + timedelta(days=30)


# ── Batch 65: the week ends at the results, not at the lock ────────────────────
#
# Two rounds are all it takes. Discovery runs a `slate_horizon_weeks` horizon ahead, and
# for a league announcing no opening it writes next week's round with
# `picks_open_at_utc` NULL — which `accepting_picks` admits the instant the row exists.
# From Sunday onwards both rounds sat in the top tier and only the soonest-lock tiebreak
# kept this week in front; at 14:30 on Saturday that tiebreak stopped applying and the
# league jumped a week, mid-afternoon, with its own games still being played.
#
# Instants are placed relative to the real clock rather than injected, because
# `latest_gameweek` takes no clock argument and these have to exercise the call the
# routers actually make.

FRIDAY, MONDAY = 4, 0

#: How long after its lock the default Saturday-15:00 window closes: the 30-minute lock
#: offset, no days spanned, and no difference between the window's end and start minute.
DEFAULT_MINUTES_LOCK_TO_CLOSE = 30


def _naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _round_in_state(
    session: AsyncSession,
    league: League,
    starts_on: date,
    *,
    status: GameweekStatus,
    locks_in: timedelta,
    opens_in: timedelta | None,
) -> Gameweek:
    """A round whose claim period is placed relative to now, not to its own window.

    The window's derivation is exercised elsewhere; what these tests need is a round
    parked at a chosen point of its life, which means writing the instants directly.
    """
    now = _naive_now()
    gameweek = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=status,
        locks_at_utc=now + locks_in,
        picks_open_at_utc=None if opens_in is None else now + opens_in,
    )
    session.add(gameweek)
    await session.flush()
    return gameweek


async def test_a_league_walks_a_full_round_cycle_without_jumping_the_week(
    session: AsyncSession,
) -> None:
    """One league, one round, every state it passes through — and which one is current.

    The member-reported defect is the fourth step. Everything before it already held, and
    is asserted here so the new top tier cannot buy it at the cost of the old rule.
    """
    _, league = await _seed_league(session, ["full-cycle"])
    today = uk_today()
    playing = await _round_in_state(
        session,
        league,
        today,
        status=GameweekStatus.scheduled,
        locks_in=timedelta(hours=3),
        opens_in=timedelta(hours=1),
    )
    upcoming = await _round_in_state(
        session,
        league,
        today + timedelta(days=7),
        status=GameweekStatus.scheduled,
        locks_in=timedelta(days=7, hours=3),
        opens_in=timedelta(days=7, hours=1),
    )

    async def current() -> Gameweek:
        found = await latest_gameweek(session, league.id)
        assert found is not None
        return found

    assert (await current()).id == playing.id, "scheduled: the round about to be played"

    # It opens. Nothing else has.
    playing.status = GameweekStatus.open
    playing.picks_open_at_utc = _naive_now() - timedelta(hours=1)
    await session.flush()
    assert (await current()).id == playing.id, "open: the one round taking picks"

    # Discovery writes next week's round with no announced opening — claimable at once.
    upcoming.status = GameweekStatus.open
    upcoming.picks_open_at_utc = None
    await session.flush()
    assert (await current()).id == playing.id, "two claimable rounds: the one shutting first"

    # 14:30 Saturday. This is where the league used to jump a week.
    playing.status = GameweekStatus.locked
    playing.locks_at_utc = _naive_now() - timedelta(hours=1)
    await session.flush()
    assert (await current()).id == playing.id, "locked and being played: still this week"

    # The results land.
    playing.status = GameweekStatus.settled
    playing.settled_at = _naive_now()
    await session.flush()
    assert (await current()).id == upcoming.id, "settled: now, and only now, the week turns"


async def test_a_round_that_never_settles_stops_pinning_the_league(
    session: AsyncSession,
) -> None:
    """The load-bearing bound: settlement can simply never arrive.

    Settlement sweeps at 18:00, 20:00 and 22:00 every day, so `IN_PLAY_GRACE_MINUTES` is
    six consecutive sweeps past the close of the round's own window. A round the provider
    has not resolved by then — Batch 64's phantom Scottish Premiership round is exactly
    that shape — is stuck, not in play, and must hand the league back to the round its
    members can still claim on.
    """
    _, league = await _seed_league(session, ["never-settles"])
    today = uk_today()
    stuck = await _round_in_state(
        session,
        league,
        today,
        status=GameweekStatus.locked,
        locks_in=-timedelta(minutes=DEFAULT_MINUTES_LOCK_TO_CLOSE + IN_PLAY_GRACE_MINUTES - 5),
        opens_in=None,
    )
    claimable = await _round_in_state(
        session,
        league,
        today + timedelta(days=7),
        status=GameweekStatus.open,
        locks_in=timedelta(days=7),
        opens_in=None,
    )

    current = await latest_gameweek(session, league.id)
    assert current is not None and current.id == stuck.id, "inside the bound it is still in play"

    stuck.locks_at_utc = _naive_now() - timedelta(
        minutes=DEFAULT_MINUTES_LOCK_TO_CLOSE + IN_PLAY_GRACE_MINUTES + 5
    )
    await session.flush()

    current = await latest_gameweek(session, league.id)
    assert current is not None and current.id == claimable.id, "past it, the claimable round wins"


async def test_the_in_play_bound_is_measured_from_the_leagues_own_window(
    session: AsyncSession,
) -> None:
    """A Friday-to-Monday league is still playing on Monday night.

    The bound runs from the close of the window, not from the lock, so a league whose
    round spans three days keeps its in-play tier three days longer than the default
    Saturday one. Measuring from the lock would drop a long-weekend league out of its own
    round while Monday's games were being played — the single-window assumption
    `AGENTS.md` calls a bug.
    """
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"span-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    session.add(owner)
    await session.flush()
    long_weekend = League(
        slug=f"span-{tag}",
        name=f"Span {tag}",
        created_by=owner.id,
        slate_start_weekday=FRIDAY,
        slate_start_minute=19 * 60,
        slate_end_weekday=MONDAY,
        slate_end_minute=22 * 60,
    )
    session.add(long_weekend)
    await session.flush()

    span_minutes = 3 * 24 * 60 + (22 * 60 - 19 * 60)
    today = uk_today()
    # Well past the default window's bound, and well inside this league's.
    stuck = await _round_in_state(
        session,
        long_weekend,
        today,
        status=GameweekStatus.locked,
        locks_in=-timedelta(
            minutes=DEFAULT_MINUTES_LOCK_TO_CLOSE + span_minutes + IN_PLAY_GRACE_MINUTES - 60
        ),
        opens_in=None,
    )
    await _round_in_state(
        session,
        long_weekend,
        today + timedelta(days=7),
        status=GameweekStatus.open,
        locks_in=timedelta(days=7),
        opens_in=None,
    )

    current = await latest_gameweek(session, long_weekend.id)
    assert current is not None and current.id == stuck.id


async def test_home_and_the_coupon_pick_the_same_round_in_every_state(
    session: AsyncSession,
) -> None:
    """The rule is spelled twice and the two spellings are asserted against each other.

    `latest_gameweek` orders one league's rounds; `routers/me.py` runs a window function
    over many leagues at once. Home renders every league's card side by side, so a
    disagreement is visible in one glance — and the new tier is exactly the kind of
    change that reaches one spelling and not the other.
    """
    players, playing_league = await _seed_league(session, ["home-vs-coupon"])
    member = next(iter(players.values()))
    tag = uuid.uuid4().hex[:8]
    stuck_league = League(slug=f"stuck-{tag}", name=f"Stuck {tag}", created_by=member.id)
    settled_league = League(slug=f"done-{tag}", name=f"Done {tag}", created_by=member.id)
    session.add_all([stuck_league, settled_league])
    await session.flush()
    for league in (stuck_league, settled_league):
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
    await session.flush()

    today = uk_today()
    # One league mid-round, one whose round is stuck past the bound, one fully settled —
    # every tier of the order, on one fixture set.
    await _round_in_state(
        session,
        playing_league,
        today,
        status=GameweekStatus.locked,
        locks_in=-timedelta(hours=1),
        opens_in=None,
    )
    await _round_in_state(
        session,
        playing_league,
        today + timedelta(days=7),
        status=GameweekStatus.open,
        locks_in=timedelta(days=7),
        opens_in=None,
    )
    await _round_in_state(
        session,
        stuck_league,
        today - timedelta(days=14),
        status=GameweekStatus.locked,
        locks_in=-timedelta(minutes=DEFAULT_MINUTES_LOCK_TO_CLOSE + IN_PLAY_GRACE_MINUTES + 60),
        opens_in=None,
    )
    await _round_in_state(
        session,
        stuck_league,
        today + timedelta(days=3),
        status=GameweekStatus.open,
        locks_in=timedelta(days=3),
        opens_in=None,
    )
    for offset in (21, 14):
        gameweek = await _round_in_state(
            session,
            settled_league,
            today - timedelta(days=offset),
            status=GameweekStatus.settled,
            locks_in=-timedelta(days=offset),
            opens_in=None,
        )
        gameweek.settled_at = _naive_now()
    await session.flush()

    league_ids = [playing_league.id, stuck_league.id, settled_league.id]
    home = await _latest_rounds(session, league_ids, member.id)

    for league_id in league_ids:
        coupon = await latest_gameweek(session, league_id)
        assert coupon is not None
        assert home[league_id].gameweek_id == str(
            coupon.id
        ), "home's card and the coupon must name the same round"


# ── Batch 65: a window edit reaches the rounds the league already holds ─────────


async def test_a_settings_change_restamps_unlocked_rounds_and_leaves_locked_ones(
    session: AsyncSession,
) -> None:
    """The owner's second sentence: an announced opening applies to each round, not one.

    Discovery writes a `slate_horizon_weeks` horizon ahead, so before this batch every
    round the member could see was already stamped against the old settings and the new
    ones appeared to do nothing for weeks. The half of the old rule that was load-bearing
    is kept: a round that has locked keeps the deadline it was claimed against.
    """
    _, league = await _seed_league(session, ["restamp"])
    today = uk_today()
    unlocked = await _round_in_state(
        session,
        league,
        today + timedelta(days=7),
        status=GameweekStatus.open,
        locks_in=timedelta(days=7),
        opens_in=None,
    )
    also_unlocked = await _round_in_state(
        session,
        league,
        today + timedelta(days=14),
        status=GameweekStatus.scheduled,
        locks_in=timedelta(days=14),
        opens_in=timedelta(days=10),
    )
    locked = await _round_in_state(
        session,
        league,
        today,
        status=GameweekStatus.locked,
        locks_in=-timedelta(hours=1),
        opens_in=None,
    )
    settled = await _round_in_state(
        session,
        league,
        today - timedelta(days=7),
        status=GameweekStatus.settled,
        locks_in=-timedelta(days=7),
        opens_in=None,
    )
    frozen = {gw.id: (gw.locks_at_utc, gw.picks_open_at_utc) for gw in (locked, settled)}

    league.slate_start_minute = 19 * 60 + 45
    league.lock_offset_minutes = 45
    league.pick_open_offset_minutes = 3 * 24 * 60
    await session.flush()

    moved = await rederive_claim_periods(session, league)

    assert {gw.id for gw in moved} == {unlocked.id, also_unlocked.id}
    window = window_for(league)
    for gameweek in (unlocked, also_unlocked):
        assert gameweek.locks_at_utc == window.locks_at(gameweek.starts_on)
        assert gameweek.picks_open_at_utc == picks_open_at(league, gameweek.starts_on)
    for gameweek in (locked, settled):
        assert (gameweek.locks_at_utc, gameweek.picks_open_at_utc) == frozen[gameweek.id]


async def test_dropping_an_announced_opening_clears_it_from_unlocked_rounds(
    session: AsyncSession,
) -> None:
    """`NULL` is a value here, not "unchanged" — the league stops announcing an opening.

    An unlocked round has to follow it back to claimable-on-sight, or a league that turns
    the setting off keeps a gate its settings no longer describe.
    """
    _, league = await _seed_league(session, ["stop-announcing"])
    league.pick_open_offset_minutes = 5 * 24 * 60
    await session.flush()
    ahead = await _round_in_state(
        session,
        league,
        uk_today() + timedelta(days=7),
        status=GameweekStatus.scheduled,
        locks_in=timedelta(days=7),
        opens_in=timedelta(days=2),
    )

    league.pick_open_offset_minutes = None
    await session.flush()
    moved = await rederive_claim_periods(session, league)

    assert [gw.id for gw in moved] == [ahead.id]
    assert ahead.picks_open_at_utc is None


async def test_restamping_an_unchanged_window_moves_nothing(session: AsyncSession) -> None:
    """Idempotent, so an edit to an unrelated setting cannot churn a deadline."""
    _, league = await _seed_league(session, ["no-op"])
    starts_on = uk_today() + timedelta(days=7)
    round_ = Gameweek(
        league_id=league.id,
        starts_on=starts_on,
        status=GameweekStatus.open,
        locks_at_utc=window_for(league).locks_at(starts_on),
        picks_open_at_utc=picks_open_at(league, starts_on),
    )
    session.add(round_)
    await session.flush()

    assert await rederive_claim_periods(session, league) == []


# ── lock → settle → leaderboard (the Batch 4 e2e slice) ─────────────────────────


async def test_lock_then_settle_updates_leaderboard(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, sl2 = await _open_gameweek(session, league, date(2027, 3, 6))

    # alice → Arsenal (home), bob → Chelsea (away), carol → Forfar (home).
    session.add_all(
        [
            _pick(
                league,
                gameweek,
                epl,
                players["alice"],
                PickOutcome.HOME,
                "Arsenal",
                "1.90",
            ),
            _pick(
                league,
                gameweek,
                epl,
                players["bob"],
                PickOutcome.AWAY,
                "Chelsea",
                "4.30",
            ),
            _pick(
                league,
                gameweek,
                sl2,
                players["carol"],
                PickOutcome.HOME,
                "Forfar Athletic",
                "2.40",
            ),
        ]
    )
    await session.flush()

    # LOCK — after 14:30 the open gameweek flips to locked (and becomes settleable).
    after_lock = gameweek.locks_at_utc + timedelta(minutes=1)
    locked = await lock_due_gameweeks(session, after_lock)
    assert gameweek.id in {g.id for g in locked}
    assert gameweek.status is GameweekStatus.locked
    assert gameweek.id in {g.id for g in await settleable_gameweeks(session, after_lock)}

    # SETTLE — canned results: Arsenal (EPL) and Forfar (SL2) win.
    fake = FakeBetfair.with_sample_data()
    fake.close_markets(
        {
            SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
            SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
        }
    )
    resolved = await settle_gameweek_via_provider(session, fake, gameweek)
    assert resolved == 3
    assert gameweek.status is GameweekStatus.settled
    assert gameweek.settled_at is not None

    picks = {
        p.player_id: p
        for p in (
            await session.execute(select(Pick).where(Pick.gameweek_id == gameweek.id))
        ).scalars()
    }
    assert picks[players["alice"].id].status is PickStatus.won  # 1.90 × 10
    assert picks[players["bob"].id].status is PickStatus.lost
    assert picks[players["carol"].id].status is PickStatus.won  # 2.40 × 10

    # LEADERBOARD — carol 24, alice 19, bob 0.
    table = {s.display_name.split("-")[0]: s for s in await standings(session, league.id)}
    assert (table["carol"].total_points, table["carol"].rank) == (24, 1)
    assert (table["alice"].total_points, table["alice"].rank) == (19, 2)
    assert (table["bob"].total_points, table["bob"].rank) == (0, 3)

    # Idempotent: a second settle pass finds nothing pending.
    assert await settle_gameweek_via_provider(session, fake, gameweek) == 0


class _RecordingFake(FakeBetfair):
    """``FakeBetfair`` that records the event ids of every ``settle`` call.

    Settlement costs one provider request per event id asked for, so what this records is
    the run's bill against a plan allowing 100 requests an hour.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settle_calls: list[list[str]] = []

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        self.settle_calls.append(list(event_ids))
        return await super().settle(event_ids)


async def test_settle_reads_a_shared_fixture_once_across_leagues(
    session: AsyncSession,
) -> None:
    """Two leagues on the same Saturday pay for the fixtures they share exactly once.

    The bill used to be per league: the job settled one round at a time and each round
    bought its own fixtures, so every match two leagues both held was requested twice.
    Nothing failed when the quota went — picks simply stayed ``pending`` and the week
    never finished.
    """
    home, league_home = await _seed_league(session, ["alice", "bob"])
    away, league_away = await _seed_league(session, ["carol"])
    gw_home, epl, sl2 = await _open_gameweek(session, league_home, SAMPLE_SATURDAY)
    gw_away, epl_again, sl2_again = await _open_gameweek(session, league_away, SAMPLE_SATURDAY)

    # One pooled row per real match, on both leagues' cards — the overlap being paid for.
    assert (epl_again.id, sl2_again.id) == (epl.id, sl2.id)

    session.add_all(
        [
            _pick(league_home, gw_home, epl, home["alice"], PickOutcome.HOME, "Arsenal", "1.90"),
            _pick(league_home, gw_home, sl2, home["bob"], PickOutcome.AWAY, "Brechin City", "5.00"),
            _pick(league_away, gw_away, epl, away["carol"], PickOutcome.HOME, "Arsenal", "2.10"),
        ]
    )
    await session.flush()

    after_lock = max(gw_home.locks_at_utc, gw_away.locks_at_utc) + timedelta(minutes=1)
    await lock_due_gameweeks(session, after_lock)
    due = {g.id for g in await settleable_gameweeks(session, after_lock)}
    assert {gw_home.id, gw_away.id} <= due, "both leagues' rounds are settleable in one run"

    fake = _RecordingFake.with_sample_data()
    fake.close_markets(
        {
            SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
            SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
        }
    )
    resolved = await settle_gameweeks_via_provider(session, fake, [gw_home, gw_away])

    # One read for the whole run, asking for each distinct fixture once — three pending
    # picks over two leagues, two requests.
    assert len(fake.settle_calls) == 1
    asked = fake.settle_calls[0]
    assert sorted(asked) == sorted({SAMPLE_EPL_EVENT_ID, SAMPLE_SL2_EVENT_ID})

    # ...and both leagues settle off it, each scoring by its own frozen odds.
    assert (resolved[gw_home.id], resolved[gw_away.id]) == (2, 1)
    assert (gw_home.status, gw_away.status) == (GameweekStatus.settled, GameweekStatus.settled)
    picks = {
        p.player_id: p
        for p in (
            await session.execute(
                select(Pick).where(Pick.gameweek_id.in_([gw_home.id, gw_away.id]))
            )
        ).scalars()
    }
    assert picks[home["alice"].id].points_awarded == 19  # 1.90 × 10
    assert picks[away["carol"].id].points_awarded == 21  # 2.10 × 10, same match
    assert picks[home["bob"].id].status is PickStatus.lost


async def test_settle_skips_the_provider_when_no_round_has_a_pending_pick(
    session: AsyncSession,
) -> None:
    """A run with nothing outstanding costs nothing — no request, no empty settle call."""
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, SAMPLE_SATURDAY)
    await session.flush()

    fake = _RecordingFake.with_sample_data()
    assert await settle_gameweeks_via_provider(session, fake, [gameweek]) == {}
    assert fake.settle_calls == []


# ── gameweek selection helpers ──────────────────────────────────────────────────


async def test_open_and_settleable_selection(session: AsyncSession) -> None:
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 8))
    before = gameweek.locks_at_utc - timedelta(hours=1)
    after = gameweek.locks_at_utc + timedelta(hours=1)

    # Before lock: open, not yet settleable. Not "remindable" — since Batch 76 that is
    # `gameweeks_due_a_reminder`, which wants the lock about three hours out, not merely
    # ahead. This asserts the label, which is all this helper claims.
    assert gameweek.id in {g.id for g in await current_open_gameweeks(session, before)}
    assert gameweek.id not in {g.id for g in await settleable_gameweeks(session, before)}

    # After lock: settleable even while still 'open' (defensive if the lock job missed a run).
    assert gameweek.id in {g.id for g in await settleable_gameweeks(session, after)}


# ── the pick-open flip (Batch 27) ───────────────────────────────────────────────


async def test_a_scheduled_round_opens_when_its_announced_time_arrives(
    session: AsyncSession,
) -> None:
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 15))
    opens_at = gameweek.locks_at_utc - timedelta(days=7)
    gameweek.status = GameweekStatus.scheduled
    gameweek.picks_open_at_utc = opens_at
    await session.flush()

    # A minute early it stays shut and does not read as claimable — nagging a member for
    # a pick they cannot make yet is worse than not reminding them at all, which Batch 76's
    # `gameweeks_due_a_reminder` carries forward in its own predicate.
    # Scoped to this round rather than asserting an empty sweep: the HTTP pick-flow
    # tests commit rounds of their own into the shared scratch database.
    early = opens_at - timedelta(minutes=1)
    assert gameweek.id not in {g.id for g in await open_due_gameweeks(session, early)}
    assert gameweek.status is GameweekStatus.scheduled
    assert gameweek.id not in {g.id for g in await current_open_gameweeks(session, early)}

    # On the instant it opens, and only then does it read as claimable.
    assert gameweek.id in {g.id for g in await open_due_gameweeks(session, opens_at)}
    assert gameweek.status is GameweekStatus.open
    assert gameweek.id in {g.id for g in await current_open_gameweeks(session, opens_at)}


async def test_a_round_that_never_opened_still_locks(session: AsyncSession) -> None:
    """A missed open job must not leave a round advertising a claim period that closed."""
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 22))
    gameweek.status = GameweekStatus.scheduled
    gameweek.picks_open_at_utc = gameweek.locks_at_utc - timedelta(days=7)
    await session.flush()

    after_lock = gameweek.locks_at_utc + timedelta(minutes=1)
    assert gameweek.id in {g.id for g in await lock_due_gameweeks(session, after_lock)}
    assert gameweek.status is GameweekStatus.locked


async def test_a_round_with_no_announced_opening_is_never_flipped(
    session: AsyncSession,
) -> None:
    """The pre-batch rule: no instant, no waiting — the round is already ``open``."""
    _, league = await _seed_league(session, ["solo"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 5, 29))
    assert gameweek.picks_open_at_utc is None

    opened = await open_due_gameweeks(session, gameweek.locks_at_utc)
    assert gameweek.id not in {g.id for g in opened}
    assert gameweek.status is GameweekStatus.open


# ── members_missing_picks ───────────────────────────────────────────────────────


async def test_members_missing_picks_targets_only_non_pickers(session: AsyncSession) -> None:
    players, league = await _seed_league(session, ["alice", "bob", "carol"])
    gameweek, epl, _sl2 = await _open_gameweek(session, league, date(2027, 4, 3))

    # Only alice has picked.
    session.add(
        _pick(
            league,
            gameweek,
            epl,
            players["alice"],
            PickOutcome.HOME,
            "Arsenal",
            "1.90",
        )
    )
    await session.flush()

    missing = await members_missing_picks(session, gameweek)
    mine = [m for m in missing if m.league_id == str(league.id)]
    assert {m.display_name.split("-")[0] for m in mine} == {"bob", "carol"}
    # Each carries the league context + the member's timezone for the reminder.
    bob = next(m for m in mine if m.display_name.startswith("bob"))
    assert bob.league_name == league.name
    assert bob.timezone == "UTC"
    # And the slug, which is what the reminder's url is built from (Batch 30).
    assert bob.league_slug == league.slug


async def test_members_missing_picks_excludes_muted_membership(session: AsyncSession) -> None:
    """A member who muted this league is never targeted (Batch 32)."""
    players, league = await _seed_league(session, ["alice", "bob"])
    gameweek, _epl, _sl2 = await _open_gameweek(session, league, date(2027, 4, 10))

    result = await session.execute(
        select(LeagueMembership).where(
            LeagueMembership.league_id == league.id,
            LeagueMembership.player_id == players["bob"].id,
        )
    )
    bob_membership = result.scalar_one()
    bob_membership.notification_muted = True
    await session.flush()

    missing = await members_missing_picks(session, gameweek)
    mine = {m.display_name.split("-")[0] for m in missing if m.league_id == str(league.id)}
    assert mine == {"alice"}


# ── Batch 58: refresh_tokens stops growing forever ──────────────────────────


async def test_prune_removes_dead_tokens_and_keeps_live_ones() -> None:
    """`refresh_tokens` was append-only — a row per login *and* per rotation, never removed.

    Removable means "can never authenticate again": expired, or revoked. Both wait out
    `REFRESH_TOKEN_RETENTION` first, because a revoked row is the only evidence
    `/auth/refresh` has that a token was *replayed* rather than simply unknown.
    """
    from src.models.refresh_token import RefreshToken
    from src.scheduler import REFRESH_TOKEN_RETENTION, run_prune_refresh_tokens

    now = datetime.now(UTC).replace(tzinfo=None)
    old = now - REFRESH_TOKEN_RETENTION - timedelta(days=1)
    recent = now - timedelta(hours=1)

    async with AsyncSessionLocal() as session:
        player = Profile(
            display_name=f"prune-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("1234"),
            role=UserRole.player,
        )
        session.add(player)
        await session.flush()

        live = RefreshToken(
            user_id=player.id, token_hash="a" * 64, expires_at=now + timedelta(days=30)
        )
        long_expired = RefreshToken(user_id=player.id, token_hash="b" * 64, expires_at=old)
        long_revoked = RefreshToken(
            user_id=player.id,
            token_hash="c" * 64,
            expires_at=now + timedelta(days=30),
            revoked_at=old,
        )
        recently_revoked = RefreshToken(
            user_id=player.id,
            token_hash="d" * 64,
            expires_at=now + timedelta(days=30),
            revoked_at=recent,
        )
        session.add_all([live, long_expired, long_revoked, recently_revoked])
        await session.commit()
        player_id = player.id

    assert await run_prune_refresh_tokens() is True

    async with AsyncSessionLocal() as session:
        remaining = {
            row.token_hash
            for row in (
                await session.execute(select(RefreshToken).where(RefreshToken.user_id == player_id))
            )
            .scalars()
            .all()
        }

    assert "a" * 64 in remaining, "a live token must survive"
    assert "d" * 64 in remaining, "a recently revoked token is still reuse evidence"
    assert "b" * 64 not in remaining, "a long-expired token should be gone"
    assert "c" * 64 not in remaining, "a long-revoked token should be gone"
