"""CORR-15 (Batch 133), Batch 159 (refresh narrowing) and Batch 161 (installation bucket).

discover_fixtures is called exactly as run_discover_fixtures / run_refresh_slate call it
(same horizon, competition_ids = the pooled set, commit_each, and the daily run's
request_budget = settings.discovery_request_budget), inside a rolled-back transaction, with
a stub provider that charges what odds-api.io charges: one /events request per competition
walked (the /leagues catalogue is memoised). The pool is 23 competitions, production's
2026-09-27 measurement (MEASURED_DAILY_WALK). 1..6 distinct windows.
"""

import asyncio
from datetime import date, datetime, timedelta

import lib
from sqlalchemy import select

from src.config import settings
from src.database import AsyncSessionLocal
from src.models.league import League
from src.models.profile import Profile
from src.rate_limit import consume_shared_limit, limiter
from src.routers.picks import (
    PICK_SUBMIT_INSTALLATION_KEY,
    PICK_SUBMIT_INSTALLATION_LIMIT,
    PICK_SUBMIT_INSTALLATION_SCOPE,
    PICK_SUBMIT_SHARED_LIMIT,
    PICK_SUBMIT_SHARED_SCOPE,
)
from src.services.gameweek import discover_fixtures, window_for
from src.services.odds_provider import Slate, SlateFixture

OUT = "budget"
# Production's pool shape, 2026-09-27 (competitions.py): 36 competitions have ever carried a
# fixture, 23 of them survive the product trim. `pooled_competition_ids` returns the raw 36;
# odds-api's fetch_slate intersects them with the played (trimmed) catalogue before walking.
PLAYED = [f"england-league-{i:02d}" for i in range(23)]
TRIMMED = [f"england-amateur-isthmian-{i:02d}" for i in range(9)] + [f"ireland-division-{i}" for i in range(4)]
POOL = PLAYED + TRIMMED
WINDOWS = [  # (weekday, start, end)
    (5, 15 * 60, 15 * 60),  # Sat 15:00
    (4, 19 * 60, 22 * 60),  # Fri 19-22
    (6, 13 * 60, 16 * 60),  # Sun 13-16
    (1, 19 * 60 + 45, 19 * 60 + 45),  # Tue 19:45
    (5, 12 * 60 + 30, 12 * 60 + 30),  # Sat 12:30
    (0, 20 * 60, 20 * 60),  # Mon 20:00
]


class OddsApiCostStub:
    def __init__(self) -> None:
        self.requests = 0
        self.walks: list[tuple[str, date]] = []

    async def fetch_slate(self, window, starts_on, *, competition_ids=None):
        from src.services.competitions import is_played
        comps = list(competition_ids) if competition_ids is not None else [f"all-{i}" for i in range(41)]
        # odds_api.fetch_slate: `_uk_leagues()` (played only) intersected with competition_ids,
        # then one /events request per league walked.
        self.requests += len([c for c in comps if is_played(c)])
        self.walks.append((f"{window.start_weekday}@{window.start_minute}", starts_on))
        ko = window.opens_at(starts_on).astimezone(tz=None).replace(tzinfo=None)
        from zoneinfo import ZoneInfo
        ko = window.opens_at(starts_on).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return Slate(starts_on=starts_on, fixtures=[SlateFixture(
            provider_event_id=f"b-{window.start_weekday}-{window.start_minute}-{starts_on}", home="H", away="A",
            kickoff_utc=ko, competition="C", competition_id=POOL[0])])


async def run(n_windows: int, today: date, horizon: int, budget: int | None) -> tuple[int, int, set]:
    async with AsyncSessionLocal() as db:
        owner = (await db.execute(select(Profile).limit(1))).scalar_one()
        leagues = []
        for i, (wd, s, e) in enumerate(WINDOWS[:n_windows]):
            lg = League(slug=f"b-{n_windows}-{i}", name="b", created_by=owner.id,
                        slate_start_weekday=wd, slate_start_minute=s, slate_end_weekday=wd, slate_end_minute=e)
            db.add(lg)
            leagues.append(lg)
        await db.flush()
        stub = OddsApiCostStub()
        await discover_fixtures(db, stub, leagues, today, horizon, competition_ids=POOL, request_budget=budget)
        served = {w for w, _ in stub.walks}
        await db.rollback()
        return stub.requests, len(stub.walks), served


async def main() -> None:
    today = date(2026, 10, 5)  # a Monday: every window's next date is ahead
    lib.out(OUT, "--- pool shape: 36 pooled / 23 played (production 2026-09-27) ---")
    lib.out(OUT, f"settings.discovery_request_budget = {settings.discovery_request_budget}, horizon {settings.slate_horizon_weeks}; pool {len(POOL)} competitions")
    for n in range(1, 7):
        d_req, d_walks, d_served = await run(n, today, settings.slate_horizon_weeks, settings.discovery_request_budget)
        u_req, u_walks, _ = await run(n, today, settings.slate_horizon_weeks, None)
        r_req, r_walks, _ = await run(n, today, 1, None)
        lib.out(OUT, f"{n} window(s): daily run {d_req} req / {d_walks} walks, windows served {len(d_served)}/{n} "
                     f"(unbudgeted would be {u_req}); refresh run (no budget, horizon 1) {r_req} req, x2/day = {2 * r_req}")

    # Batch 161: three leagues each trying 40 submissions in one hour, charged exactly as
    # submit_pick charges them (league bucket first, then the installation bucket).
    limiter._storage.reset()
    passed = {}
    for league in ("A", "B", "C"):
        ok = 0
        for _ in range(40):
            if not consume_shared_limit(f"league:{league}", PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE):
                continue
            if not consume_shared_limit(PICK_SUBMIT_INSTALLATION_KEY, PICK_SUBMIT_INSTALLATION_LIMIT, PICK_SUBMIT_INSTALLATION_SCOPE):
                continue
            ok += 1
        passed[league] = ok
    lib.out(OUT, f"Batch 161: 3 leagues x 40 submissions -> admitted {passed}, total {sum(passed.values())} (installation limit {PICK_SUBMIT_INSTALLATION_LIMIT})")


asyncio.run(main())
