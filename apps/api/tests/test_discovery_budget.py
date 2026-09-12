"""What the daily discovery run costs, and what it keeps when it cannot finish. Batch 119.

Between 2026-09-04 and 2026-09-11 the scheduled run produced **nothing, every day**, and
the two halves of why are both tested here:

* it asked for 67 competitions across two windows and two dates — 268 requests against a
  100/hour plan — so it took a ``429`` partway through; and
* it committed once at the end, so the exception rolled back every ``(window, date)`` that
  had already succeeded. A run that got a hundred requests in had nothing to show for them,
  and the next morning's run started from the same place and failed the same way.

Postgres-backed. The partial-run tests genuinely commit, so they run on a session bound to
the rolled-back connection with ``join_transaction_mode="create_savepoint"`` — a real
commit as far as the code under test is concerned, and nothing left behind afterwards.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from src.auth import hash_pin
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.profile import Profile, UserRole
from src.services.gameweek import (
    discover_fixtures,
    fixtures_for,
    pooled_competition_ids,
    warmable_gameweeks,
    window_for,
)
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_provider import (
    Competition,
    EventSettlement,
    FixtureOdds,
    Market,
    OddsProvider,
    OddsProviderRateLimited,
    Outcome,
    Selection,
    Slate,
    SlateFixture,
    SlateWindow,
)
from src.services.odds_warm import warm_round

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
    ),
]

#: Three consecutive Saturdays. The default window is a single 15:00 London instant, so a
#: fixture has to kick off on it exactly to land on the card.
SATURDAYS = (date(2026, 10, 3), date(2026, 10, 10), date(2026, 10, 17))

#: A catalogue in miniature with the shape that matters: some competitions carry fixtures
#: and some never have, which is the whole of the daily run's narrowing.
CARRIES = ("scotland-premiership", "england-championship")
BARREN = ("wales-welsh-cup", "scotland-challenge-cup", "england-efl-cup")


def _kickoff(starts_on: date) -> datetime:
    """15:00 Europe/London on that Saturday, as naive UTC — BST in October, so 14:00."""
    return datetime(starts_on.year, starts_on.month, starts_on.day, 14, 0)


class _CatalogueProvider(OddsProvider):
    """Records every slate walk and what it was narrowed to; can run out of quota."""

    def __init__(self, *, rate_limit_after: int | None = None) -> None:
        self.slate_calls: list[tuple[date, tuple[str, ...] | None]] = []
        self.rate_limit_after = rate_limit_after
        self.odds_calls: list[list[str]] = []
        self.priced: set[str] | None = None

    async def login(self) -> str:
        return "token"

    async def keep_alive(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch_slate(
        self,
        window: SlateWindow,
        starts_on: date,
        *,
        competition_ids: Collection[str] | None = None,
    ) -> Slate:
        narrowed = None if competition_ids is None else tuple(sorted(competition_ids))
        self.slate_calls.append((starts_on, narrowed))
        if self.rate_limit_after is not None and len(self.slate_calls) > self.rate_limit_after:
            raise OddsProviderRateLimited("odds-api.io /events rate-limited (429), not retried")
        offered = CARRIES if narrowed is None else tuple(c for c in CARRIES if c in narrowed)
        return Slate(
            starts_on=starts_on,
            fixtures=[
                SlateFixture(
                    provider_event_id=f"{competition}-{starts_on:%Y%m%d}-{index}",
                    home=f"Home {index}",
                    away=f"Away {index}",
                    kickoff_utc=_kickoff(starts_on),
                    competition=competition.replace("-", " ").title(),
                    competition_id=competition,
                )
                for competition in offered
                for index in range(2)
            ],
        )

    async def fetch_competitions(self) -> list[Competition]:
        return [Competition(competition_id=c, competition=c) for c in (*CARRIES, *BARREN)]

    async def settle(self, event_ids: Sequence[str]) -> list[EventSettlement]:
        return []

    async def fetch_odds(
        self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
    ) -> list[FixtureOdds]:
        self.odds_calls.append(list(event_ids))
        return [
            FixtureOdds(
                provider_event_id=event_id,
                home="Home",
                away="Away",
                selections=[
                    Selection(
                        market=Market.MATCH_ODDS,
                        outcome=Outcome.HOME,
                        runner_name="Home",
                        price=Decimal("2.00"),
                    )
                ],
            )
            for event_id in event_ids
            if self.priced is None or event_id in self.priced
        ]


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A rolled-back session for the tests that never commit."""
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


@pytest_asyncio.fixture
async def committing_session(db_conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """A session whose ``commit()`` is real to the code under test and undone afterwards.

    ``create_savepoint`` is what makes that possible: the session commits a savepoint on a
    connection whose outer transaction the ``db_conn`` fixture rolls back. The code under
    test cannot tell the difference, which is the point — ``commit_each`` is exactly the
    behaviour being asserted, so faking the commit would assert nothing.
    """
    async with AsyncSession(
        bind=db_conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as db:
        yield db


async def _league(db: AsyncSession, *, window_owner: bool = False) -> League:
    tag = uuid.uuid4().hex[:8]
    owner = Profile(display_name=f"own-{tag}", pin_hash=hash_pin("1234"), role=UserRole.player)
    db.add(owner)
    await db.flush()
    league = League(slug=f"disc-{tag}", name=f"Disc {tag}", created_by=owner.id)
    if window_owner:
        # A genuinely different window: Friday 19:00. Two windows is the production shape.
        league.slate_start_weekday = 4
        league.slate_start_minute = 19 * 60
        league.slate_end_weekday = 4
        league.slate_end_minute = 19 * 60
    db.add(league)
    await db.flush()
    db.add(LeagueMembership(league_id=league.id, player_id=owner.id))
    await db.flush()
    return league


# ── the narrowing ───────────────────────────────────────────────────────────────


async def test_the_daily_run_walks_only_the_competitions_that_have_carried_a_fixture(
    session: AsyncSession,
) -> None:
    """The cost half, end to end: the walk asks for the pool, not for the catalogue.

    Invisible to members by construction — a competition with no fixtures returns nothing
    whether it is asked about or not — and it is the difference between 67 requests per
    ``(window, date)`` and twenty.
    """
    league = await _league(session)
    provider = _CatalogueProvider()

    # Cold: nothing pooled yet, so there is nothing to narrow by and it walks everything.
    await discover_fixtures(session, provider, [league], SATURDAYS[0], 1, competition_ids=None)
    assert provider.slate_calls[0][1] is None

    pooled = await pooled_competition_ids(session)
    assert set(CARRIES) <= pooled
    assert not set(BARREN) & pooled, "a competition with no fixture cannot be in the pool"

    provider.slate_calls.clear()
    await discover_fixtures(session, provider, [league], SATURDAYS[1], 1, competition_ids=pooled)
    _, narrowed = provider.slate_calls[0]
    assert narrowed is not None
    assert set(CARRIES) <= set(narrowed)
    assert not set(BARREN) & set(narrowed)


async def test_the_full_catalogue_walk_reaches_what_the_daily_run_skips(
    session: AsyncSession,
) -> None:
    """The release on the ratchet, stated as the difference between the two calls.

    A competition that is never walked can never be discovered, so skipping the never-used
    ones has to be paired with something that asks about them anyway.
    """
    league = await _league(session)
    provider = _CatalogueProvider()
    pooled = {"scotland-premiership"}

    await discover_fixtures(session, provider, [league], SATURDAYS[0], 1, competition_ids=pooled)
    await discover_fixtures(session, provider, [league], SATURDAYS[1], 1, competition_ids=None)

    daily, full = provider.slate_calls
    assert daily[1] == ("scotland-premiership",)
    assert full[1] is None, "the weekly pass asks for everything, which is its entire point"


# ── what a run that cannot finish leaves behind ─────────────────────────────────


async def test_a_run_that_runs_out_of_quota_keeps_every_date_it_bought(
    committing_session: AsyncSession,
) -> None:
    """The defect that made a week of failed runs cost more than they should have.

    The run is allowed two slate walks and asked for three dates. Before Batch 119 the
    ``429`` on the third raised past a single commit at the end and the session rolled back
    the first two — bought, paid for, and thrown away. Now each ``(window, date)`` is
    committed as it lands.
    """
    league = await _league(committing_session, window_owner=False)
    await committing_session.commit()
    provider = _CatalogueProvider(rate_limit_after=2)

    with pytest.raises(OddsProviderRateLimited):
        await discover_fixtures(
            committing_session,
            provider,
            [league],
            SATURDAYS[0],
            3,
            commit_each=True,
        )

    # Discard whatever the failed date left pending. What survives is only what was
    # committed as it landed — which is the whole assertion.
    await committing_session.rollback()
    kept = (
        (
            await committing_session.execute(
                select(Gameweek.starts_on)
                .where(Gameweek.league_id == league.id)
                .order_by(Gameweek.starts_on)
            )
        )
        .scalars()
        .all()
    )

    assert list(kept) == [
        SATURDAYS[0],
        SATURDAYS[1],
    ], "a run that exhausted the plan partway must leave the dates it completed behind"
    linked = (
        await committing_session.execute(
            select(func.count())
            .select_from(GameweekFixture)
            .join(Gameweek, Gameweek.id == GameweekFixture.gameweek_id)
            .where(Gameweek.league_id == league.id)
        )
    ).scalar_one()
    assert linked == 2 * len(CARRIES) * 2, "the fixtures it bought survived with the rounds"


async def test_a_run_that_completes_leaves_exactly_the_rounds_it_always_did(
    committing_session: AsyncSession,
) -> None:
    """``commit_each`` changes when the rows land, never which rows land."""
    league = await _league(committing_session)
    await committing_session.commit()
    provider = _CatalogueProvider()

    discovered = await discover_fixtures(
        committing_session, provider, [league], SATURDAYS[0], 3, commit_each=True
    )

    assert [g.starts_on for g in discovered] == list(SATURDAYS)
    for gameweek in discovered:
        assert len(await fixtures_for(committing_session, gameweek.id)) == len(CARRIES) * 2


async def test_without_commit_each_the_caller_still_owns_the_transaction(
    session: AsyncSession,
) -> None:
    """The old contract is the default, because tests and composed callers rely on it."""
    league = await _league(session)
    provider = _CatalogueProvider()

    await discover_fixtures(session, provider, [league], SATURDAYS[0], 1)

    assert session.in_transaction(), "discovery must not have committed on its own"


# ── the marker-warming pass ─────────────────────────────────────────────────────


async def test_the_warm_pass_writes_the_marker_with_no_member_involved(
    session: AsyncSession,
) -> None:
    """Batch 115's item, and the reason ``odds_checked_at_utc`` read ``never`` for a week.

    ``record_observations`` ran only from the pick screen, so nothing was learned until an
    authenticated member opened a card — which meant the first member on a match morning
    paid for the whole cold sweep in the hour everyone else was trying to pick.
    """
    league = await _league(session)
    provider = _CatalogueProvider()
    discovered = await discover_fixtures(session, provider, [league], SATURDAYS[0], 1)
    gameweek = discovered[0]
    fixtures = await fixtures_for(session, gameweek.id)
    assert all(f.odds_checked_at_utc is None for f in fixtures), "cold, as production was"

    # The bookmaker prices half of this card and nothing on the other half.
    provider.priced = {f.provider_event_id for f in fixtures[:2]}
    cache = CachingOddsProvider(provider, ttl_seconds=300.0)

    changed = await warm_round(
        session, cache, gameweek, datetime(2026, 10, 1, 6, 0), recheck_seconds=21600
    )

    fixtures = await fixtures_for(session, gameweek.id)
    assert changed == len(fixtures) - 2, "only the unpriced ones are a change to record"
    marked = {f.provider_event_id for f in fixtures if f.odds_unpriced_since_utc is not None}
    assert marked == {f.provider_event_id for f in fixtures} - provider.priced
    assert all(
        f.odds_checked_at_utc is not None
        for f in fixtures
        if f.provider_event_id not in provider.priced
    )

    # And the ambiguity this batch accepted rather than fixed: a fixture that was priced
    # and still is writes **nothing**, so a swept-and-fully-priced card is indistinguishable
    # in the data from one that has never been swept. Resolving it wants a sweep timestamp
    # per round, which wants a column, and Batch 119 carries no migration by design — see
    # `src/services/odds_warm.py`. Asserted so the trade is visible rather than assumed.
    assert all(
        f.odds_checked_at_utc is None for f in fixtures if f.provider_event_id in provider.priced
    )


async def test_a_round_already_learned_inside_its_recheck_window_costs_nothing(
    session: AsyncSession,
) -> None:
    """A no-op, not a second sweep. The marker persists; re-paying for it is the waste."""
    league = await _league(session)
    provider = _CatalogueProvider()
    gameweek = (await discover_fixtures(session, provider, [league], SATURDAYS[0], 1))[0]
    cache = CachingOddsProvider(provider, ttl_seconds=300.0)
    now = datetime(2026, 10, 1, 6, 0)

    provider.priced = set()
    await warm_round(session, cache, gameweek, now, recheck_seconds=21600)
    after_first = len(provider.odds_calls)

    await warm_round(session, cache, gameweek, now + timedelta(hours=1), recheck_seconds=21600)
    assert len(provider.odds_calls) == after_first, "everything is marked and none is due"


async def test_a_rate_limited_warm_pass_writes_nothing(session: AsyncSession) -> None:
    """The same evidence rule the card uses, and the rule that kept the marker honest.

    Every sweep production ran for a week was degraded, ``observed`` was empty, and
    ``record_observations`` correctly wrote nothing. A warm pass that marked fixtures on a
    failed sweep would take pickable rows off the card on exactly the days the provider was
    unreachable.
    """
    league = await _league(session)
    provider = _CatalogueProvider()
    gameweek = (await discover_fixtures(session, provider, [league], SATURDAYS[0], 1))[0]

    class _Refusing(_CatalogueProvider):
        async def fetch_odds(
            self, event_ids: Sequence[str], *, max_age_seconds: float | None = None
        ) -> list[FixtureOdds]:
            raise OddsProviderRateLimited("odds-api.io /odds/multi rate-limited (429)")

    cache = CachingOddsProvider(_Refusing(), ttl_seconds=300.0)
    changed = await warm_round(
        session, cache, gameweek, datetime(2026, 10, 1, 6, 0), recheck_seconds=21600
    )

    assert changed == 0
    fixtures = await fixtures_for(session, gameweek.id)
    assert all(f.odds_checked_at_utc is None for f in fixtures)
    assert all(f.odds_unpriced_since_utc is None for f in fixtures)


async def test_the_warm_pass_leaves_the_hour_before_a_lock_alone(
    session: AsyncSession,
) -> None:
    """Batch 114 moved the late slate pass off 13:00 for this reason; warming keeps clear.

    A scheduled sweep in the ninety minutes before a deadline competes with the members
    trying to beat it, and warming is the one job whose whole purpose is to have already
    happened.
    """
    league = await _league(session)
    provider = _CatalogueProvider()
    gameweek = (await discover_fixtures(session, provider, [league], SATURDAYS[0], 1))[0]
    gameweek.status = GameweekStatus.open
    await session.flush()

    lock = gameweek.locks_at_utc
    early = await warmable_gameweeks(session, lock - timedelta(hours=6), horizon_weeks=1)
    late = await warmable_gameweeks(session, lock - timedelta(minutes=30), horizon_weeks=1)

    assert gameweek.id in {g.id for g in early}
    assert gameweek.id not in {g.id for g in late}


async def test_two_windows_cost_two_walks_a_date_and_not_two_per_league(
    session: AsyncSession,
) -> None:
    """The third factor in ``windows x dates x competitions``, which the budget suite models.

    Asserted here on requests actually issued, because the production shape that could not
    complete was two windows and the old arithmetic counted one.
    """
    saturday_a = await _league(session)
    saturday_b = await _league(session)
    friday = await _league(session, window_owner=True)
    assert window_for(saturday_a) == window_for(saturday_b)
    assert window_for(friday) != window_for(saturday_a)

    provider = _CatalogueProvider()
    await discover_fixtures(session, provider, [saturday_a, saturday_b, friday], SATURDAYS[0], 1)

    assert len(provider.slate_calls) == 2, "two windows, one walk each — not one per league"


async def test_the_pool_is_shared_so_one_window_teaches_the_whole_deployment(
    session: AsyncSession,
) -> None:
    """Why the weekly full walk can afford to cover a single window.

    ``pooled_competition_ids`` is deployment-wide, so a competition discovered through any
    window is one the daily run walks for every window from the next morning on.
    """
    friday = await _league(session, window_owner=True)
    provider = _CatalogueProvider()

    before = await pooled_competition_ids(session)
    await discover_fixtures(session, provider, [friday], SATURDAYS[0], 1, competition_ids=None)
    after = await pooled_competition_ids(session)

    assert set(CARRIES) <= after
    assert not set(CARRIES) & (before - after)
