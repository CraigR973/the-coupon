"""Batch 69 — the operational half of the admin console.

Dashboard, sync and results. The value is measurable in work already done by hand: Batch
64 opened with a Motherwell pick returned manually and twelve fixtures removed manually,
and Batch 68 is a backfill run straight against the database.

What these hold to:

* **a hand-entered result writes the same ``picks`` rows as the scheduled path** — the
  same round settled both ways is compared field by field, because a second scoring rule
  would be a second answer to "what did this pick score";
* the dashboard's stuck-round count is checked against a round deliberately left pending,
  which is the state Batch 64's phantom Premiership round sat in for a whole afternoon;
* a manual trigger runs the coroutine the scheduler runs, taken from the same registry;
* a job that spends the odds provider's budget is refused once the shared bucket is
  empty, and one that spends nothing is never refused.

The rate-limit arithmetic itself lives in ``tests/test_request_budget.py`` beside the rest
of the budget, following Batch 57.

Postgres-backed and non-hermetic — these drive the HTTP endpoints, which commit.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth import create_access_token, hash_pin
from src.config import settings
from src.database import AsyncSessionLocal
from src.main import app
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.rate_limit import limiter
from src.services.admin_ops import (
    REQUESTS_PER_SLATE_WALK,
    job_by_key,
    manual_jobs,
    settlement_from_score,
    voided_settlement,
)
from src.services.scoring import settle_gameweek

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _auth(profile: Profile) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(profile.id, profile.role)}"}


async def _profile(role: UserRole = UserRole.player) -> Profile:
    async with AsyncSessionLocal() as session:
        profile = Profile(
            display_name=f"{role.value}-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin("8351"),
            role=role,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _locked_round_with_pick(
    member: Profile, *, home_goals: int = 2, away_goals: int = 1
) -> tuple[League, Gameweek, Fixture, Pick]:
    """A league whose round has locked with one pending pick on one fixture.

    The exact shape the results screen exists for: past its deadline, nothing settled,
    and nothing about to settle it because the provider never answered.
    """
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(slug=f"ops-{tag}", name=f"Ops {tag}", created_by=member.id)
        session.add(league)
        await session.flush()
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=date(2027, 3, 6),
            status=GameweekStatus.locked,
            locks_at_utc=_now() - timedelta(hours=2),
        )
        fixture = Fixture(
            provider_event_id=f"ev-{tag}",
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=_now() - timedelta(hours=1),
            competition="Scottish League Two",
            competition_id=f"sl2-{tag}",
        )
        session.add_all([gameweek, fixture])
        await session.flush()
        session.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))
        pick = Pick(
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=member.id,
            fixture_id=fixture.id,
            market=PickMarket.MATCH_ODDS,
            outcome=PickOutcome.HOME,
            runner_name="Forfar Athletic",
            odds_at_pick=Decimal("2.50"),
            status=PickStatus.pending,
        )
        session.add(pick)
        await session.commit()
        await session.refresh(league)
        await session.refresh(gameweek)
        await session.refresh(fixture)
        await session.refresh(pick)
        return league, gameweek, fixture, pick
    # unreachable, but keeps the return type honest for mypy


def _pick_state(pick: Pick) -> tuple[str, int | None]:
    return pick.status.value, pick.points_awarded


# ── The rule the whole screen rests on ─────────────────────────────────────────


async def test_a_hand_entered_result_writes_what_the_scheduled_path_writes(
    client: AsyncClient,
) -> None:
    """One scoring rule, two ways in. The rows have to be indistinguishable.

    Two identical rounds, the same 2-1 to the home side: one settled by an admin typing
    the score, one by ``settle_gameweek`` on the settlement a provider would have sent.
    A second scoring path would be a second answer to "what did this pick score", and the
    failure mode is a leaderboard that disagrees with itself.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    _, by_hand, by_hand_fixture, by_hand_pick = await _locked_round_with_pick(member)
    _, scheduled, scheduled_fixture, scheduled_pick = await _locked_round_with_pick(member)

    response = await client.post(
        f"/api/v1/admin/results/{by_hand.id}/settle",
        json={
            "results": [{"fixture_id": str(by_hand_fixture.id), "home_goals": 2, "away_goals": 1}]
        },
        headers=_auth(admin),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "gameweek_id": str(by_hand.id),
        "picks_resolved": 1,
        "settled": True,
    }

    async with AsyncSessionLocal() as session:
        stored = (
            await session.execute(select(Gameweek).where(Gameweek.id == scheduled.id))
        ).scalar_one()
        await settle_gameweek(
            session,
            stored,
            [settlement_from_score(scheduled_fixture.provider_event_id, 2, 1)],
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        left = (await session.execute(select(Pick).where(Pick.id == by_hand_pick.id))).scalar_one()
        right = (
            await session.execute(select(Pick).where(Pick.id == scheduled_pick.id))
        ).scalar_one()
        assert _pick_state(left) == _pick_state(right) == ("won", 25)  # round(2.5 × 10)

        left_round = (
            await session.execute(select(Gameweek).where(Gameweek.id == by_hand.id))
        ).scalar_one()
        right_round = (
            await session.execute(select(Gameweek).where(Gameweek.id == scheduled.id))
        ).scalar_one()
        assert left_round.status is right_round.status is GameweekStatus.settled
        assert left_round.settled_at is not None and right_round.settled_at is not None


async def test_a_hand_voided_fixture_scores_nothing_and_loses_nothing(
    client: AsyncClient,
) -> None:
    """The Batch 64 case: a fixture that was never played, entered as such.

    Void is not a loss. A member whose game was called off keeps their record intact,
    which is the same thing ``resolve_pick`` already does for a provider-voided event.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    _, gameweek, fixture, pick = await _locked_round_with_pick(member)

    response = await client.post(
        f"/api/v1/admin/results/{gameweek.id}/settle",
        json={"results": [{"fixture_id": str(fixture.id), "void": True}]},
        headers=_auth(admin),
    )

    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(Pick).where(Pick.id == pick.id))).scalar_one()
        assert _pick_state(stored) == ("void", 0)


async def test_a_settled_round_refuses_a_second_settlement(client: AsyncClient) -> None:
    """This corrects a round that is stuck, not one that is finished.

    Rewriting a settled week would move points members have already seen on a
    leaderboard. A genuine correction means editing the pick, which is a different act.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    _, gameweek, fixture, _ = await _locked_round_with_pick(member)
    payload = {"results": [{"fixture_id": str(fixture.id), "home_goals": 2, "away_goals": 1}]}

    assert (
        await client.post(
            f"/api/v1/admin/results/{gameweek.id}/settle", json=payload, headers=_auth(admin)
        )
    ).status_code == 200

    again = await client.post(
        f"/api/v1/admin/results/{gameweek.id}/settle", json=payload, headers=_auth(admin)
    )

    assert again.status_code == 409


async def test_a_result_needs_both_scores_or_void(client: AsyncClient) -> None:
    """Half a scoreline is not a result, and guessing the other half would invent one."""
    admin = await _profile(UserRole.admin)
    member = await _profile()
    _, gameweek, fixture, pick = await _locked_round_with_pick(member)

    response = await client.post(
        f"/api/v1/admin/results/{gameweek.id}/settle",
        json={"results": [{"fixture_id": str(fixture.id), "home_goals": 2}]},
        headers=_auth(admin),
    )

    assert response.status_code == 422
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(Pick).where(Pick.id == pick.id))).scalar_one()
        assert stored.status is PickStatus.pending, "a refused request settles nothing"


# ── Dashboard ──────────────────────────────────────────────────────────────────


async def test_the_dashboard_counts_a_round_left_deliberately_pending(
    client: AsyncClient,
) -> None:
    """The state Batch 64's phantom Premiership round sat in, and nobody could see.

    The settle sweep runs at 18:00, 20:00 and 22:00 and simply finds nothing to do, so a
    round the provider will never resolve is invisible until a member asks why their
    points have not landed.
    """
    admin = await _profile(UserRole.admin)
    member = await _profile()
    _, gameweek, fixture, _ = await _locked_round_with_pick(member)

    dashboard = (await client.get("/api/v1/admin/dashboard", headers=_auth(admin))).json()

    stuck = {row["gameweek_id"]: row for row in dashboard["stuck_rounds"]}
    assert str(gameweek.id) in stuck
    assert stuck[str(gameweek.id)]["pending_picks"] == 1
    assert dashboard["active_members"] >= 2

    # Settling it takes it off the list — the count is a live read, not a stored one.
    await client.post(
        f"/api/v1/admin/results/{gameweek.id}/settle",
        json={"results": [{"fixture_id": str(fixture.id), "home_goals": 2, "away_goals": 1}]},
        headers=_auth(admin),
    )
    after = (await client.get("/api/v1/admin/dashboard", headers=_auth(admin))).json()
    assert str(gameweek.id) not in {row["gameweek_id"] for row in after["stuck_rounds"]}


async def test_the_dashboard_reports_the_scheduler_it_can_actually_see(
    client: AsyncClient,
) -> None:
    """``enabled`` is the configured intent; ``running`` is the fact.

    They come apart in the case worth knowing about — a container whose scheduler never
    started — and the tests run with ``SCHEDULER_ENABLED=false``, which is that shape.
    """
    admin = await _profile(UserRole.admin)

    dashboard = (await client.get("/api/v1/admin/dashboard", headers=_auth(admin))).json()

    assert dashboard["scheduler"]["running"] is False
    assert isinstance(dashboard["scheduler"]["jobs"], list)


async def test_the_dashboard_reports_the_odds_budget_without_spending_any_of_it(
    client: AsyncClient,
) -> None:
    """Batch 114. Nothing counted the plan, so an exhausted one looked like a stale card.

    On 2026-09-05 the hourly allowance was gone by 08:06 and the first anyone knew of it
    was a member being refused a pick. The counters are on the screen an admin already
    checks on a Saturday morning — and reading them must not establish a provider session
    or send a request, because a dashboard left open on a second screen would then be
    spending the very budget it reports.
    """
    admin = await _profile(UserRole.admin)

    dashboard = (await client.get("/api/v1/admin/dashboard", headers=_auth(admin))).json()

    budget = dashboard["odds_budget"]
    assert budget["live"] is False, "reading the dashboard must not build a provider session"
    assert budget["hour_limit"] == settings.odds_hourly_request_limit
    assert budget["day_limit"] == settings.odds_daily_request_limit
    assert budget["hour_remaining"] == budget["hour_limit"] - budget["hour_used"]
    assert budget["day_remaining"] == budget["day_limit"] - budget["day_used"]
    assert budget["rate_limited_for"] is None


async def test_the_dashboard_shows_the_next_lock_per_league_not_every_round(
    client: AsyncClient,
) -> None:
    """The horizon holds two or three rounds and only the nearest can still be acted on."""
    admin = await _profile(UserRole.admin)
    member = await _profile()
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        league = League(slug=f"locks-{tag}", name=f"Locks {tag}", created_by=member.id)
        session.add(league)
        await session.flush()
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        for days in (3, 10):
            session.add(
                Gameweek(
                    league_id=league.id,
                    starts_on=date(2027, 4, 3) + timedelta(days=days),
                    status=GameweekStatus.open,
                    locks_at_utc=_now() + timedelta(days=days),
                )
            )
        await session.commit()
        slug = league.slug

    dashboard = (await client.get("/api/v1/admin/dashboard", headers=_auth(admin))).json()

    mine = [row for row in dashboard["upcoming_locks"] if row["league_slug"] == slug]
    assert len(mine) == 1, "one deadline per league, the nearest"
    assert mine[0]["members"] == 1


# ── Sync ───────────────────────────────────────────────────────────────────────


def test_every_offered_job_is_one_the_scheduler_actually_runs() -> None:
    """Taken from ``run_scheduled.JOBS``, so there is no second implementation to drift.

    Resolving ``.run`` is the assertion: a key that is not in the registry raises here
    rather than 500-ing the first time an admin presses it.
    """
    assert manual_jobs()
    for job in manual_jobs():
        assert callable(job.run)


def test_the_destructive_and_useless_jobs_are_not_offered() -> None:
    """``backup`` writes to the container's disk; ``football-backfill`` is a season pull.

    Both stay available to the cron entry point, which is where a one-off belongs.
    """
    offered = {job.key for job in manual_jobs()}
    assert "backup" not in offered
    assert "football-backfill" not in offered


def test_only_the_jobs_that_reach_odds_api_declare_a_cost() -> None:
    """FotMob needs no key and has no rate limit to protect, so its sweep is free.

    Pricing the harmless buttons is how the useful one stops being pressed.
    """
    costs = {job.key: job.provider_requests for job in manual_jobs()}
    assert costs["sync-football"] == 0
    assert costs["open"] == costs["lock"] == costs["remind"] == 0
    assert costs["refresh-slate"] == REQUESTS_PER_SLATE_WALK
    assert costs["discover-fixtures"] >= REQUESTS_PER_SLATE_WALK


def test_a_job_that_walks_the_card_twice_is_charged_twice() -> None:
    """The bucket is denominated in slate walks, so cost has to be expressed in them.

    Charging discovery one hit for two walks would let an admin spend twice what the
    limit permits — the same arithmetic error Batch 57 found on the pick path.
    """
    discovery = job_by_key("discover-fixtures")
    refresh = job_by_key("refresh-slate")
    assert discovery is not None and refresh is not None
    assert refresh.budget_units == 1
    assert discovery.budget_units == discovery.provider_requests // REQUESTS_PER_SLATE_WALK


async def test_the_sync_screen_says_what_a_run_costs_before_it_is_pressed(
    client: AsyncClient,
) -> None:
    """ "30 requests" says nothing; "30 of 100 an hour, shared with the scheduler" does."""
    admin = await _profile(UserRole.admin)

    body = (await client.get("/api/v1/admin/jobs", headers=_auth(admin))).json()

    assert body["hourly_budget"] == 100
    assert body["budget_limit"] == "2/hour;3/day"
    by_key = {job["key"]: job for job in body["jobs"]}
    assert by_key["refresh-slate"]["spends_budget"] is True
    assert by_key["refresh-slate"]["provider_requests"] == REQUESTS_PER_SLATE_WALK
    assert by_key["sync-football"]["spends_budget"] is False


async def test_a_free_job_runs_and_is_never_refused_for_budget(client: AsyncClient) -> None:
    """Locking due rounds touches only the database, so no bucket is charged.

    Pressed repeatedly past the provider limit's whole allowance and still answering.
    """
    admin = await _profile(UserRole.admin)
    limiter._storage.reset()

    for _ in range(5):
        response = await client.post("/api/v1/admin/jobs/lock/run", headers=_auth(admin))
        assert response.status_code == 200, response.text
        assert response.json() == {"key": "lock", "ok": True}


async def test_a_budget_spending_job_is_refused_once_the_shared_bucket_is_empty(
    client: AsyncClient,
) -> None:
    """The scheduler's own runs come first.

    An admin refreshing a slate by hand at 14:00 on a Saturday can 429 the refresh that
    matters, and exhaustion is silent — picks simply stay pending and the week never
    finishes. The bucket is the one the ad-hoc slate fetch already uses, not a second one
    beside it, because two ``2/hour`` limits against a plan with room for two is
    ``4/hour``.
    """
    admin = await _profile(UserRole.admin)
    limiter._storage.reset()

    seen = []
    for _ in range(4):
        response = await client.post("/api/v1/admin/jobs/refresh-slate/run", headers=_auth(admin))
        seen.append(response.status_code)

    assert 429 in seen, f"the shared budget never refused anything: {seen}"
    assert seen[0] == 200, "the first press must be allowed"


async def test_an_unknown_job_is_a_404_not_a_500(client: AsyncClient) -> None:
    admin = await _profile(UserRole.admin)

    response = await client.post("/api/v1/admin/jobs/drop-database/run", headers=_auth(admin))

    assert response.status_code == 404


# ── The score → settlement conversion, on its own ──────────────────────────────


@pytest.mark.parametrize(
    ("home", "away", "winner", "both_scored"),
    [
        (2, 1, "HOME", True),
        (0, 3, "AWAY", False),
        (1, 1, "DRAW", True),
        (0, 0, "DRAW", False),
    ],
)
def test_a_scoreline_decides_both_markets(
    home: int, away: int, winner: str, both_scored: bool
) -> None:
    """An admin types a score; the markets follow from it rather than being asked about.

    Asking separately whether both teams scored is asking for arithmetic the code can do,
    and for a mistake nothing would catch.
    """
    settlement = settlement_from_score("ev-1", home, away)

    won = {(o.market.value, o.outcome.value) for o in settlement.outcomes if o.won}
    assert ("MATCH_ODDS", winner) in won
    assert ("BOTH_TEAMS_TO_SCORE", "YES" if both_scored else "NO") in won
    assert len([o for o in settlement.outcomes if o.won]) == 2, "one winner per market"


def test_a_void_settlement_settles_without_deciding_anything() -> None:
    """`settled` and `void` together is what ``resolve_pick`` reads as "never played"."""
    settlement = voided_settlement("ev-1")

    assert settlement.settled is True
    assert settlement.void is True
    assert settlement.outcomes == []
