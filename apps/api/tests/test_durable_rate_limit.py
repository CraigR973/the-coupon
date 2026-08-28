"""Batch 99 — the limits that guard credentials survive a redeploy, and the rest do not.

Every rate-limit counter in the app lived in process memory, so a Railway restart handed
each one a fresh bucket. On a project that redeploys several times a week that is not a
theoretical reset: it is five login attempts, wait for a deploy, five more.

Only the counters where a reset is a **security event** moved to Postgres —
``/auth/login`` and ``/auth/pin/reset-request``. The provider budgets stayed in memory,
because there a reset costs provider requests rather than protection. Both halves of that
split are asserted here, in both directions, so it stays a decision somebody made rather
than something the code happens to do.

Postgres-backed: the durable half has no meaning without the table it lives in.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from limits import parse_many
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.rate_limit as rate_limit
from src.auth import hash_pin
from src.database import AsyncSessionLocal
from src.main import app
from src.models.profile import Profile, UserRole
from src.models.rate_limit import BUCKET_KEY_MAX_LENGTH, RateLimitCounter
from src.rate_limit import (
    LOGIN_LIMIT,
    consume_durable_limit,
    consume_shared_limit,
    durable_bucket_key,
    limiter,
)
from src.routers.leagues import PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE
from src.routers.picks import PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE
from src.scheduler import run_prune_rate_limit_counters

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as s:
        yield s


def _restart_the_process() -> None:
    """Everything a redeploy does to the rate limiter, and nothing else.

    ``slowapi``'s counters are a dictionary hanging off the ``Limiter``; a new process
    builds an empty one. Emptying the live storage is that same observable event without
    the fifty seconds of Railway in the middle — and it is exactly what every counter in
    the app could not survive before this batch.
    """
    limiter._storage.reset()


async def _counter(key: str, limit_value: str) -> RateLimitCounter | None:
    item = parse_many(limit_value)[0]
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(RateLimitCounter).where(
                    RateLimitCounter.bucket_key == durable_bucket_key(key),
                    RateLimitCounter.limit_item == item.key_for(),
                )
            )
        ).scalar_one_or_none()


async def _profile(pin: str = "8351") -> Profile:
    async with AsyncSessionLocal() as s:
        profile = Profile(
            display_name=f"rl-{uuid.uuid4().hex[:8]}",
            pin_hash=hash_pin(pin),
            role=UserRole.player,
        )
        s.add(profile)
        await s.commit()
        await s.refresh(profile)
        return profile


# ── The batch, in one test each way ────────────────────────────────────────────


async def test_the_login_bucket_survives_a_process_restart(session: AsyncSession) -> None:
    """The finding, inverted. Five attempts, a redeploy, and the sixth is still refused.

    Before this batch the restart in the middle handed the caller a fresh ``5/15
    minutes`` and the sixth attempt was the first of a new five.
    """
    key = f"login:test-{uuid.uuid4().hex[:8]}:203.0.113.9"

    for attempt in range(5):
        assert await consume_durable_limit(session, key, LOGIN_LIMIT) is True, attempt

    _restart_the_process()

    assert await consume_durable_limit(session, key, LOGIN_LIMIT) is False
    row = await _counter(key, LOGIN_LIMIT)
    assert row is not None and row.hits == 6


async def test_the_pick_budget_deliberately_does_not_survive_a_restart() -> None:
    """The other half of the split, asserted rather than assumed.

    Batch 89 put a shared ``50/hour;100/day`` bucket in front of pick submission. It
    protects a *spend* — the odds provider's 100 requests an hour — so a restart costs
    requests, not protection, and paying a database round trip on the pick path to keep
    it would be the wrong trade. If somebody later moves this to Postgres too, this test
    is what tells them it was a decision they are reversing.
    """
    key = f"league-budget:{uuid.uuid4()}"

    spent = 0
    while consume_shared_limit(key, PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE):
        spent += 1
        assert spent < 200, "the shared pick budget never refused anything"
    assert spent == 50, f"expected the hourly window to be the binding one, spent {spent}"

    _restart_the_process()

    assert consume_shared_limit(key, PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE) is True
    assert (
        await _counter(key, PICK_SUBMIT_SHARED_LIMIT) is None
    ), "the pick budget must not have written a durable row"


async def test_the_slate_fetch_budget_deliberately_does_not_survive_a_restart() -> None:
    """Same again for the other provider budget, ``2/hour;3/day``."""
    key = f"user:{uuid.uuid4()}"

    assert consume_shared_limit(key, PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE)
    assert consume_shared_limit(key, PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE)
    assert not consume_shared_limit(key, PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE)

    _restart_the_process()

    assert consume_shared_limit(key, PROVIDER_SLATE_FETCH_LIMIT, PROVIDER_SLATE_FETCH_SCOPE)
    assert await _counter(key, PROVIDER_SLATE_FETCH_LIMIT) is None


# ── The durable counter's own behaviour ────────────────────────────────────────


async def test_the_window_rolls_the_counter_over_in_place(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closed window starts again at one, and does so without a second row."""
    key = f"login:roll-{uuid.uuid4().hex[:8]}:198.51.100.4"

    for _ in range(5):
        assert await consume_durable_limit(session, key, LOGIN_LIMIT) is True
    assert await consume_durable_limit(session, key, LOGIN_LIMIT) is False

    # Sixteen minutes on, which is a different fifteen-minute window whenever "now" fell
    # inside the old one. Patching the name `src.rate_limit` holds rather than the `time`
    # module itself, so nothing outside the limiter sees a moved clock.
    later = rate_limit.time.time() + 16 * 60

    class _SixteenMinutesLater:
        @staticmethod
        def time() -> float:
            return later

    monkeypatch.setattr(rate_limit, "time", _SixteenMinutesLater)

    assert await consume_durable_limit(session, key, LOGIN_LIMIT) is True
    row = await _counter(key, LOGIN_LIMIT)
    assert row is not None and row.hits == 1

    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(RateLimitCounter).where(RateLimitCounter.bucket_key == durable_bucket_key(key))
        )
        rows = list(result.scalars())
    assert len(rows) == 1, "the bucket must roll forward in place, not accumulate windows"


async def test_two_windows_charge_in_order_and_stop_at_the_first_refusal(
    session: AsyncSession,
) -> None:
    """The same contract ``consume_shared_limit`` documents, kept by the durable twin."""
    key = f"pair-{uuid.uuid4().hex[:8]}"

    assert await consume_durable_limit(session, key, "1/hour;5/day") is True
    assert await consume_durable_limit(session, key, "1/hour;5/day") is False

    hourly = await _counter(key, "1/hour")
    daily = await _counter(key, "5/day")
    assert hourly is not None and hourly.hits == 2
    assert (
        daily is not None and daily.hits == 1
    ), "the daily window must not be charged by a request the hourly one refused"


async def test_an_overlong_key_is_folded_rather_than_rejected(session: AsyncSession) -> None:
    """``login_key`` reads the display name before pydantic has seen it.

    A caller can send ten kilobytes of name. Against a ``String(200)`` column that is a
    ``DataError`` and a 500 on the endpoint they are already probing, so long keys keep a
    readable prefix and end in a digest of the whole key.
    """
    first = f"login:{'a' * 10_000}:203.0.113.9"
    second = f"login:{'a' * 9_999}b:203.0.113.9"

    assert len(durable_bucket_key(first)) <= BUCKET_KEY_MAX_LENGTH
    assert durable_bucket_key(first) != durable_bucket_key(
        second
    ), "folding must not merge two different callers into one bucket"

    assert await consume_durable_limit(session, first, LOGIN_LIMIT) is True
    assert await consume_durable_limit(session, second, LOGIN_LIMIT) is True
    row = await _counter(first, LOGIN_LIMIT)
    assert row is not None and row.hits == 1


# ── Through the endpoints, which is where it has to hold ───────────────────────


async def test_the_sixth_login_is_refused_in_the_shape_the_client_reads(
    client: AsyncClient,
) -> None:
    """The 429 body must not change with the store behind it.

    ``AuthContext.tsx`` branches on ``{"error": ...}`` specifically; a 429 carrying
    ``detail`` would fall through to "your details are wrong" and invite the retry the
    limit just refused.
    """
    member = await _profile()

    for attempt in range(5):
        response = await client.post(
            "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "0000"}
        )
        assert response.status_code == 401, (attempt, response.text)

    refused = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "8351"}
    )
    assert refused.status_code == 429, refused.text
    assert refused.json() == {"error": "Rate limit exceeded: 5 per 15 minute"}


async def test_a_redeploy_mid_attack_does_not_hand_back_the_login_bucket(
    client: AsyncClient,
) -> None:
    """The finding end to end: spend the window, restart, and the next attempt is still refused."""
    member = await _profile()

    for _ in range(5):
        await client.post(
            "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "0000"}
        )

    _restart_the_process()

    refused = await client.post(
        "/api/v1/auth/login", json={"display_name": member.display_name, "pin": "0000"}
    )
    assert refused.status_code == 429, refused.text


async def test_an_unknown_name_is_charged_even_though_the_handler_commits_nothing(
    client: AsyncClient,
) -> None:
    """Why the counter has a session of its own.

    A login for a name that does not exist returns 401 without writing anything — there
    is no profile to update and no transaction to commit. Counted on the request's own
    session the attempt would vanish with it, and name enumeration would be free.
    """
    unknown = f"nobody-{uuid.uuid4().hex[:8]}"

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login", json={"display_name": unknown, "pin": "0000"}
        )
        assert response.status_code == 401, response.text

    refused = await client.post("/api/v1/auth/login", json={"display_name": unknown, "pin": "0000"})
    assert refused.status_code == 429, refused.text


async def test_the_pin_reset_request_is_bounded_by_address_across_a_restart(
    client: AsyncClient,
) -> None:
    """Three an hour per caller, and the fourth stays refused through a redeploy.

    This endpoint pushes to every site admin, so its counter resetting is an unbounded
    stream of notifications rather than merely a wasted request.
    """
    for attempt in range(3):
        response = await client.post(
            "/api/v1/auth/pin/reset-request", json={"display_name": f"nobody-{attempt}"}
        )
        assert response.status_code == 200, response.text

    _restart_the_process()

    refused = await client.post("/api/v1/auth/pin/reset-request", json={"display_name": "nobody-3"})
    assert refused.status_code == 429, refused.text
    assert refused.json() == {"error": "Rate limit exceeded: 3 per 1 hour"}


# ── Housekeeping ───────────────────────────────────────────────────────────────


async def test_the_prune_removes_closed_windows_and_leaves_live_ones() -> None:
    """A live bucket must survive the sweep — deleting one hands back the fresh counter."""
    live_key = f"live-{uuid.uuid4().hex[:8]}"
    dead_key = f"dead-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as s:
        s.add(
            RateLimitCounter(
                bucket_key=live_key,
                limit_item="LIMITER/5/15/minute",
                window_start=_now(),
                hits=5,
                expires_at=_now() + timedelta(minutes=10),
            )
        )
        s.add(
            RateLimitCounter(
                bucket_key=dead_key,
                limit_item="LIMITER/5/15/minute",
                window_start=_now() - timedelta(hours=2),
                hits=5,
                expires_at=_now() - timedelta(hours=1),
            )
        )
        await s.commit()

    assert await run_prune_rate_limit_counters() is True

    async with AsyncSessionLocal() as s:
        remaining = {
            row.bucket_key
            for row in (
                await s.execute(
                    select(RateLimitCounter).where(
                        RateLimitCounter.bucket_key.in_([live_key, dead_key])
                    )
                )
            ).scalars()
        }
    assert remaining == {live_key}
