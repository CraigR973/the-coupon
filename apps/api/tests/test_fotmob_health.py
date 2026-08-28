"""Batch 101 — what counts as "FotMob has bitten", and what deliberately does not.

FotMob's terms prohibit automated access. The owner took that knowingly and it stays
revisitable; what was missing was the signal to revisit *on*. Three shipped features rest
on it — Football Stats, the void-fixture cross-check before lock, live in-play scores —
and TheSportsDB is named as the fallback with nothing tracking when to reach for it.

The hard half is not firing. A trigger that goes off on the timeout every HTTP client
sees weekly is a trigger the owner learns to ignore, and then the real one arrives on a
Saturday and reads like all the others. So roughly half of what follows asserts silence.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.notification import ActionType, ActorType, AuditLog
from src.scheduler import (
    report_football_provider_health,
    run_discover_fixtures,
    run_live_scores,
)
from src.services.football_provider import CompetitionKey, FootballDataAPIError
from src.services.fotmob import FotMobProvider
from src.services.fotmob_health import (
    BLOCK_STATUSES,
    CONSECUTIVE_FAILURES_BEFORE_ALERT,
    FotMobHealth,
    FotMobTrouble,
    fotmob_health,
)
from src.services.notification_triggers import (
    FOOTBALL_PROVIDER_ALERT_COOLDOWN,
    notify_football_provider_trouble,
)
from src.services.odds_provider import Slate
from src.services.slate_verification import verify_slate
from tests.test_scheduler import _Ctx
from tests.test_slate_verification import (
    PREMIERSHIP,
    SATURDAY,
    StubFootball,
    slate_fixture,
    state,
)

#: Overridden in ``_COMPETITION_OVERRIDES``, so resolving it costs no catalogue call —
#: which keeps these tests counting the failures they mean to count.
NL_NORTH = CompetitionKey(
    slug="england-amateur-national-league-north",
    name="England Amateur - National League North",
)


def _health() -> FotMobHealth:
    return FotMobHealth()


# ── Staying quiet, which is the half that makes the other half worth having ────


def test_one_transient_failure_says_nothing() -> None:
    """A timeout is what every HTTP call to anyone does sometimes."""
    health = _health()
    health.request_failed(status=None, reason="read timeout")

    assert health.take_alert() is None


def test_one_short_of_the_threshold_still_says_nothing() -> None:
    health = _health()
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT - 1):
        health.request_failed(status=500, reason="upstream 500")

    assert health.take_alert() is None


def test_a_success_clears_the_run() -> None:
    """Consecutive, not cumulative.

    A source that drops one competition in thirty every day is not degrading, and a
    cumulative counter would eventually fire on it no matter how healthy things were.
    """
    health = _health()
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT - 1):
        health.request_failed(status=500, reason="upstream 500")
    health.request_succeeded()
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT - 1):
        health.request_failed(status=500, reason="upstream 500")

    assert health.take_alert() is None
    assert health.consecutive_failures == CONSECUTIVE_FAILURES_BEFORE_ALERT - 1


def test_a_single_429_is_a_hiccup_and_not_a_block() -> None:
    """Rate limiting is the one refusal that genuinely does un-refuse."""
    health = _health()
    health.request_failed(status=429, reason="too many requests")

    assert health.take_alert() is None


# ── Firing ─────────────────────────────────────────────────────────────────────


def test_sustained_failure_fires_once_the_run_is_long_enough() -> None:
    health = _health()
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT):
        health.request_failed(status=500, reason="upstream 500")

    alert = health.take_alert()
    assert alert is not None
    assert alert.trouble is FotMobTrouble.unreachable
    assert str(CONSECUTIVE_FAILURES_BEFORE_ALERT) in alert.detail
    assert alert.loud is False, "an outage is real but does not need somebody's Saturday"


def test_sustained_429s_do_eventually_fire() -> None:
    """Not a block, but a wall we keep walking into is still the source refusing us."""
    health = _health()
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT):
        health.request_failed(status=429, reason="too many requests")

    alert = health.take_alert()
    assert alert is not None and alert.trouble is FotMobTrouble.unreachable


@pytest.mark.parametrize("status", sorted(BLOCK_STATUSES))
def test_a_block_fires_on_the_very_first_one(status: int) -> None:
    """These are the terms being applied, and they do not un-apply.

    Waiting for a second would be waiting to be told twice — and this is precisely the
    signal FEAT-A07 said was missing, so it is the one that must not be batched.
    """
    health = _health()
    health.request_failed(status=status, reason=f"/api/data/leagues returned {status}.")

    alert = health.take_alert()
    assert alert is not None
    assert alert.trouble is FotMobTrouble.blocked
    assert str(status) in alert.detail
    assert alert.loud is True


def test_a_blind_cross_check_fires_and_is_loud() -> None:
    """The pick-validity path, which is why it carries the loudest signal."""
    health = _health()
    health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=9)

    alert = health.take_alert()
    assert alert is not None
    assert alert.trouble is FotMobTrouble.blind_cross_check
    assert alert.loud is True
    assert "9 fixtures" in alert.detail and str(SATURDAY) in alert.detail


def test_a_block_is_not_buried_by_the_ordinary_failures_that_follow_it() -> None:
    """A collector may be ten minutes away; the more serious thing has to survive.

    A block is followed by more blocks — but a moved path is followed by 404s, and a
    dying source by timeouts. Overwriting the diagnosis with the symptom would send the
    owner looking at the network instead of at the terms.
    """
    health = _health()
    health.request_failed(status=403, reason="/api/data/leagues returned 403.")
    for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT):
        health.request_failed(status=500, reason="upstream 500")

    alert = health.take_alert()
    assert alert is not None and alert.trouble is FotMobTrouble.blocked


def test_taking_the_alert_clears_it() -> None:
    """One alert per episode. Three jobs collect; the first to finish reports."""
    health = _health()
    health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=3)

    assert health.take_alert() is not None
    assert health.take_alert() is None


# ── Through the adapter, which is the funnel every request goes through ────────


def _provider(handle: object) -> FotMobProvider:
    client = httpx.AsyncClient(
        base_url="https://www.fotmob.com",
        transport=httpx.MockTransport(handle),  # type: ignore[arg-type]
    )
    return FotMobProvider(client=client)


async def test_the_adapter_reports_a_403_to_the_tracker() -> None:
    """Instrumented at the transport, because that is where every FotMob request funnels.

    A signal taken inside any one feature would miss the outage whenever that feature
    happened not to be the one running — and only one of the three runs every ten minutes.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    provider = _provider(handle)
    try:
        with pytest.raises(FootballDataAPIError):
            await provider.fetch_table(NL_NORTH, 2026)
    finally:
        await provider.close()

    alert = fotmob_health.take_alert()
    assert alert is not None and alert.trouble is FotMobTrouble.blocked


async def test_a_two_hundred_that_is_not_json_counts_as_a_failure() -> None:
    """The interface is undocumented and has moved before — a changed shape is a signal.

    ``/api/leagues?id=47`` began answering 404 while ``/api/data/leagues`` answered 200,
    with no version and no changelog. A maintenance page served as 200 is the same class
    of event and must not read as a healthy request.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    provider = _provider(handle)
    try:
        for _ in range(CONSECUTIVE_FAILURES_BEFORE_ALERT):
            with pytest.raises(FootballDataAPIError):
                await provider.fetch_table(NL_NORTH, 2026)
    finally:
        await provider.close()

    alert = fotmob_health.take_alert()
    assert alert is not None and alert.trouble is FotMobTrouble.unreachable


# ── Through the cross-check, the one that decides whether a pick is valid ──────


async def test_a_slate_nothing_could_be_checked_against_reports_itself() -> None:
    """``verify_slate`` fails open by design, which is correct and also silent.

    A card where nothing could be verified looks exactly like a card that was fine. This
    is what makes the difference audible.
    """
    slate = Slate(starts_on=SATURDAY, fixtures=[slate_fixture("Rangers", "St Mirren")])

    verified, voided = await verify_slate(slate, StubFootball(raises=RuntimeError("boom")))

    assert voided == 0, "failing open is the safety property and must not change"
    assert verified is slate
    alert = fotmob_health.take_alert()
    assert alert is not None and alert.trouble is FotMobTrouble.blind_cross_check


async def test_a_slate_with_one_checkable_fixture_stays_quiet() -> None:
    """Partial coverage is the normal Saturday — FotMob carries most of the card, not all.

    Eight of one Saturday's fixtures were unverifiable by any available source. Alerting
    on that would fire every week and mean nothing.
    """
    checkable = slate_fixture("Rangers", "St Mirren", event_id="1")
    unknown = slate_fixture("Ballymena", "Glenavon", event_id="2", competition=("ni-1", "NI - 1"))
    slate = Slate(starts_on=SATURDAY, fixtures=[checkable, unknown])

    await verify_slate(slate, StubFootball({PREMIERSHIP[0]: [state("Rangers", "St Mirren")]}))

    assert fotmob_health.take_alert() is None


async def test_an_empty_slate_is_not_a_blind_cross_check() -> None:
    """Nothing to verify is not the same as verifying nothing."""
    slate = Slate(starts_on=SATURDAY, fixtures=[])

    await verify_slate(slate, StubFootball())

    assert fotmob_health.take_alert() is None


# ── The alert itself, which has to be durable and has to shut up ───────────────

_needs_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as s:
        yield s


async def _degraded_rows(session: AsyncSession) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).where(AuditLog.action_type == ActionType.football_provider_degraded)
    )
    return list(result.scalars())


async def _clear_degraded(session: AsyncSession) -> None:
    """These two commit, so they tidy up after themselves rather than trusting a rollback."""
    await session.execute(
        delete(AuditLog).where(AuditLog.action_type == ActionType.football_provider_degraded)
    )
    await session.commit()


@_needs_db
async def test_the_alert_leaves_a_row_somebody_can_read_on_monday(
    session: AsyncSession,
) -> None:
    """The push is what reaches a person on the day; the row is what is still there."""
    await _clear_degraded(session)
    health = _health()
    health.request_failed(status=403, reason="/api/data/leagues returned 403.")
    alert = health.take_alert()
    assert alert is not None

    assert await notify_football_provider_trouble(session, alert) is True
    await session.commit()

    rows = await _degraded_rows(session)
    assert len(rows) == 1
    assert rows[0].actor_type is ActorType.system
    assert rows[0].changes is not None
    assert rows[0].changes["trouble"] == "blocked"
    assert "403" in rows[0].changes["detail"]

    await _clear_degraded(session)


@_needs_db
async def test_a_ten_minute_job_does_not_alert_every_ten_minutes(
    session: AsyncSession,
) -> None:
    """A blocked source answers every request the same way, all afternoon.

    Without the cooldown the first bad Saturday is a hundred identical pushes, which is
    how an alert stops being read at all.
    """
    await _clear_degraded(session)
    health = _health()
    health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=9)
    first = health.take_alert()
    health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=9)
    second = health.take_alert()
    assert first is not None and second is not None

    assert await notify_football_provider_trouble(session, first) is True
    await session.commit()
    assert await notify_football_provider_trouble(session, second) is False
    await session.commit()

    rows = await _degraded_rows(session)
    assert len(rows) == 1, "the second alert must not have written a second row"

    # ...and the silence ends when the cooldown does.
    rows[0].timestamp = (
        datetime.now(UTC).replace(tzinfo=None)
        - FOOTBALL_PROVIDER_ALERT_COOLDOWN
        - timedelta(minutes=1)
    )
    await session.commit()
    assert await notify_football_provider_trouble(session, second) is True
    await session.commit()

    assert len(await _degraded_rows(session)) == 2

    await _clear_degraded(session)


# ── The wiring, which is the half that is inert if it is wrong ─────────────────


async def test_nothing_pending_costs_nothing() -> None:
    """Three jobs call this and two of them run on a schedule. The quiet path is the path.

    ``AsyncSessionLocal`` is rigged to explode: if the helper opened a session just to
    discover there was nothing to say, every ten-minute live-scores run would pay for it.
    """
    with patch("src.scheduler.AsyncSessionLocal", side_effect=AssertionError("opened a session")):
        assert await report_football_provider_health() is False


async def test_the_first_job_to_finish_reports_and_the_rest_find_nothing() -> None:
    """One alert per episode, not one per job that noticed it."""
    fotmob_health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=9)
    session = AsyncMock()
    with (
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch(
            "src.scheduler.notify_football_provider_trouble", new=AsyncMock(return_value=True)
        ) as notify,
    ):
        assert await report_football_provider_health() is True
        assert await report_football_provider_health() is False

    assert notify.await_count == 1
    assert notify.await_args is not None
    assert notify.await_args.args[1].trouble is FotMobTrouble.blind_cross_check


async def test_a_job_that_threw_still_reports_what_the_source_did() -> None:
    """Reported from ``finally``, and this is why.

    A sweep that raised is precisely when the source is in trouble. Hanging the report off
    the success path would lose the alert in exactly the case it exists for.
    """
    fotmob_health.request_failed(status=403, reason="/api/data/leagues returned 403.")
    session = AsyncMock()
    with (
        patch(
            "src.scheduler.odds_session.acquire",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch(
            "src.scheduler.notify_football_provider_trouble", new=AsyncMock(return_value=True)
        ) as notify,
    ):
        assert await run_discover_fixtures() is False

    assert notify.await_count == 1
    assert notify.await_args is not None
    assert notify.await_args.args[1].trouble is FotMobTrouble.blocked


async def test_a_live_scores_run_with_no_provider_still_reports() -> None:
    """The ten-minute job returns early when nothing is configured — and still collects.

    Whichever of the three jobs happens to run first should be the one that reports, so
    none of them may skip the collection on its own early-return.
    """
    fotmob_health.cross_check_saw_nothing(starts_on=SATURDAY, fixtures=4)
    session = AsyncMock()
    with (
        patch("src.scheduler.football_session.acquire", new=AsyncMock(return_value=None)),
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
        patch(
            "src.scheduler.notify_football_provider_trouble", new=AsyncMock(return_value=True)
        ) as notify,
    ):
        assert await run_live_scores() is True

    assert notify.await_count == 1
