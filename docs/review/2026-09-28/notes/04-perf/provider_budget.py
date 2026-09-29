"""odds-api.io requests per job and per member action, counted at the HTTP layer.

The real `OddsApiProvider` is given an `httpx.MockTransport` that serves a synthetic
catalogue and counts every request it receives (the ground truth). It is wrapped in the
real `CachingOddsProvider` (whose plan counter Batch 160 made charge every entry point)
and installed as the process-wide `odds_session` client, so the real scheduler jobs
(`run_discover_fixtures`, `run_warm_odds_marker`, `run_refresh_slate`,
`run_settle_gameweeks`, lock/open) and the pick screen's own odds path
(`askable` -> `fetch_odds_best_effort` -> `record_observations`) all spend through it.

A virtual clock drives Thu 1 Oct 05:00 -> Sun 4 Oct 00:00 London; the Saturday is the
measured day. **Destroys the scratch database contents** (it re-seeds its own minimal
state per scenario); re-run seed_shapes.py afterwards.

    bash run.sh provider_budget.py <windows: 1|3|5> [--quiet-members]

Writes budget-<N>w.json and appends a line to budget-summary.txt.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
import sys
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
import httpx  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

import src.scheduler as sched  # noqa: E402
import src.services.gameweek as gw_service  # noqa: E402
import src.services.season_calendar as cal_service  # noqa: E402
from src.config import settings  # noqa: E402
from src.database import AsyncSessionLocal, engine  # noqa: E402
from src.models.gameweek import Gameweek, GameweekStatus  # noqa: E402
from src.models.league import League  # noqa: E402
from src.services.football_session import football_session  # noqa: E402
from src.services.odds_api import OddsApiProvider  # noqa: E402
from src.services.odds_cache import CachingOddsProvider  # noqa: E402
from src.services.odds_pricing import askable, record_observations  # noqa: E402
from src.services.odds_session import odds_session  # noqa: E402

HERE = Path(__file__).resolve().parent
LON = ZoneInfo("Europe/London")
POOLED_PLAYED = [
    "england-premier-league", "england-championship", "england-league-one",
    "england-league-two", "england-amateur-national-league",
    "england-amateur-national-league-north", "england-amateur-national-league-south",
    "scotland-premiership", "scotland-championship", "scotland-league-one",
    "scotland-league-two", "scotland-highland-league", "scotland-challenge-cup",
    "scotland-league-cup", "wales-cymru-premier", "wales-welsh-cup", "england-efl-trophy",
    "england-fa-cup", "england-efl-cup", "scotland-scottish-cup", "wales-cymru-north",
    "wales-cymru-south", "scotland-lowland-league",
]
POOLED_UNPLAYED = [f"england-amateur-division-{i}" for i in range(9)] + [
    "northern-ireland-premiership", "northern-ireland-championship",
    "northern-ireland-cup", "northern-ireland-league-cup"]
NEVER_POOLED_PLAYED = [f"scotland-extra-{i}" for i in range(18)]  # 23 + 18 = 41 played
NEVER_POOLED_UNPLAYED = [f"england-amateur-other-{i}" for i in range(13)]  # 67 UK total
assert len(POOLED_UNPLAYED) == 13

# Windows: (start_weekday, start_minute, end_weekday, end_minute), kick-off instants.
WINDOWS = [
    (5, 900, 5, 900),    # Sat 15:00 — default
    (4, 1185, 4, 1185),  # Fri 19:45
    (6, 840, 6, 840),    # Sun 14:00
    (5, 750, 5, 750),    # Sat 12:30
    (1, 1185, 1, 1185),  # Tue 19:45
]
EVENTS_PER_SLOT = {900: 264, 1185: 24, 840: 20, 750: 20}


class Catalogue:
    """The mock odds-api.io. Counts every request by kind and by virtual London hour."""

    def __init__(self, clock: "Clock") -> None:
        self.clock = clock
        self.total = 0
        self.by_kind: Counter[str] = Counter()
        self.by_hour: Counter[str] = Counter()
        leagues = [{"slug": s, "name": f"{'Scotland' if s.startswith('scotland') else 'Wales' if s.startswith('wales') else 'Northern Ireland' if s.startswith('northern') else 'England'} - {s}"}
                   for s in POOLED_PLAYED + POOLED_UNPLAYED + NEVER_POOLED_PLAYED + NEVER_POOLED_UNPLAYED]
        leagues += [{"slug": f"spain-la-liga-{i}", "name": f"Spain - La Liga {i}"} for i in range(20)]
        self.leagues = leagues

    def events_for(self, slug: str, frm: datetime, to: datetime) -> list[dict]:
        if slug not in POOLED_PLAYED:
            return []
        i = POOLED_PLAYED.index(slug)
        out = []
        day = frm.astimezone(LON).date()
        while datetime(day.year, day.month, day.day, tzinfo=LON) < to:
            for sw, sm, _ew, _em in WINDOWS:
                if day.weekday() != sw:
                    continue
                n = EVENTS_PER_SLOT[sm]
                ko = datetime(day.year, day.month, day.day, sm // 60, sm % 60, tzinfo=LON).astimezone(UTC)
                for k in range(i, n, 23):
                    ev = f"{day:%m%d}{sm:04d}{k:03d}"
                    out.append({"id": int(ev), "home": f"H{ev}", "away": f"A{ev}",
                                "date": ko.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "pending",
                                "league": {"name": slug, "slug": slug}})
            day += timedelta(days=1)
        return out

    @staticmethod
    def priced(ev: str) -> bool:
        return int(ev[-3:]) % 3 != 0  # about a third unpriced (production: 89 of 264)

    def odds_payload(self, ev: str) -> dict:
        body = {"id": int(ev), "home": f"H{ev}", "away": f"A{ev}", "status": "pending", "bookmakers": {}}
        if self.priced(ev):
            body["bookmakers"] = {"Bet365": [
                {"name": "ML", "odds": [{"home": "2.10", "draw": "3.40", "away": "3.25"}]},
                {"name": "Both Teams To Score", "odds": [{"yes": "1.83", "no": "1.95"}]}]}
        return body

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.total += 1
        path = request.url.path.removeprefix("/v3")
        q = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        hour = self.clock.london().strftime("%a %H:00")
        if path == "/leagues":
            kind, body = "leagues", self.leagues
        elif path == "/events":
            kind = "events (slate walk)"
            body = self.events_for(q["league"], datetime.fromisoformat(q["from"].replace("Z", "+00:00")),
                                   datetime.fromisoformat(q["to"].replace("Z", "+00:00")))
        elif path == "/odds/multi":
            kind, body = "odds/multi", [self.odds_payload(e) for e in q["eventIds"].split(",")]
        elif path == "/odds":
            kind, body = "odds (single)", [self.odds_payload(q["eventId"])]
        elif path.startswith("/events/"):
            kind = "events/{id} (settle)"
            ev = path.rsplit("/", 1)[1]
            body = {"id": int(ev), "home": f"H{ev}", "away": f"A{ev}", "status": "settled",
                    "scores": {"home": 1, "away": 0}}
        else:
            return httpx.Response(404, json={"error": "unknown"})
        self.by_kind[kind] += 1
        self.by_hour[hour] += 1
        return httpx.Response(200, json=body)


class Clock:
    def __init__(self, start_london: datetime) -> None:
        self.now_utc = start_london.astimezone(UTC)
        self.origin = self.now_utc

    def london(self) -> datetime:
        return self.now_utc.astimezone(LON)

    def naive_utc(self) -> datetime:
        return self.now_utc.replace(tzinfo=None)

    def monotonic(self) -> float:
        return (self.now_utc - self.origin).total_seconds()


def install_clock(clock: Clock) -> None:
    real = datetime

    class FakeDT(real):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            value = clock.now_utc
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    for module in (sched, gw_service, cal_service):
        module.datetime = FakeDT  # type: ignore[attr-defined]
    sched._uk_today = lambda: clock.london().date()  # type: ignore[attr-defined]
    sched._utc_now = clock.naive_utc  # type: ignore[attr-defined]
    gw_service._utc_now = clock.naive_utc  # type: ignore[attr-defined]
    gw_service.uk_today = lambda: clock.london().date()  # type: ignore[attr-defined]

    async def no_football():  # noqa: ANN202
        return None

    football_session.acquire = no_football  # type: ignore[method-assign]


async def seed(windows: int) -> list[uuid.UUID]:
    """Minimal state: a pool history of 36 competitions, N leagues (one per window)."""
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE profiles, leagues, fixtures, season_calendars CASCADE"))
        await conn.execute(text(
            "insert into season_calendars (season, week_one_anchor, extra_weeks) values (2026, '2026-08-08', '{}')"))
        for n, slug in enumerate(POOLED_PLAYED + POOLED_UNPLAYED):
            await conn.execute(text(
                "insert into fixtures (id, provider_event_id, home, away, kickoff_utc, competition, competition_id) "
                "values (gen_random_uuid(), :ev, 'H', 'A', '2026-09-12 14:00', :c, :c)"),
                {"ev": f"old-{n}", "c": slug})
        members = []
        for i in range(12 + 4 * (windows - 1)):
            pid = uuid.uuid4()
            members.append(pid)
            await conn.execute(text(
                "insert into profiles (id, display_name, pin_hash, role) values (:id, :n, 'x', 'player')"),
                {"id": pid, "n": f"Budget {i:02d}"})
        leagues = []
        for w in range(windows):
            sw, sm, ew, em = WINDOWS[w]
            lid = uuid.uuid4()
            leagues.append(lid)
            await conn.execute(text(
                "insert into leagues (id, slug, name, created_by, slate_start_weekday, slate_start_minute, "
                "slate_end_weekday, slate_end_minute) values (:id, :s, :s, :o, :sw, :sm, :ew, :em)"),
                {"id": lid, "s": f"window-{w}", "o": members[0], "sw": sw, "sm": sm, "ew": ew, "em": em})
            who = members[:12] if w == 0 else members[12 + 4 * (w - 1): 16 + 4 * (w - 1)]
            for p in who:
                await conn.execute(text(
                    "insert into league_memberships (id, league_id, player_id) values (gen_random_uuid(), :l, :p)"),
                    {"l": lid, "p": p})
    return leagues


async def card_load(cache: CachingOddsProvider, now: datetime) -> int:
    """Every league's current round, through the pick screen's own odds path."""
    loads = 0
    async with AsyncSessionLocal() as db:
        rounds = (await db.execute(
            select(Gameweek).where(Gameweek.status.in_([GameweekStatus.open]), Gameweek.locks_at_utc > now)
            .order_by(Gameweek.league_id, Gameweek.locks_at_utc))).scalars().all()
        seen: set[uuid.UUID] = set()
        for gw in rounds:
            if gw.league_id in seen:
                continue
            seen.add(gw.league_id)
            fixtures = await gw_service.fixtures_for(db, gw.id)
            asked = askable(fixtures, now, recheck_seconds=settings.odds_unpriced_recheck_seconds)
            max_age = gw_service.slate_odds_max_age(gw, now, near_ttl=settings.odds_cache_near_ttl_seconds,
                                                    far_ttl=settings.odds_cache_ttl_seconds)
            snap = await cache.fetch_odds_best_effort([f.provider_event_id for f in asked], max_age_seconds=max_age)
            if record_observations(asked, snap.observed, {o.provider_event_id for o in snap.odds}, now):
                await db.commit()
            loads += 1
    return loads


async def picks_for_saturday(cache: CachingOddsProvider, now: datetime, member_pick: int) -> None:
    """One member freezing a price (60 s tier) and the pick row the settle job needs."""
    async with AsyncSessionLocal() as db:
        gw = (await db.execute(select(Gameweek).join(League, League.id == Gameweek.league_id)
              .where(League.slug == "window-0", Gameweek.status == GameweekStatus.open,
                     Gameweek.locks_at_utc > now).order_by(Gameweek.locks_at_utc).limit(1))).scalars().first()
        if gw is None:
            return
        fixtures = [f for f in await gw_service.fixtures_for(db, gw.id) if Catalogue.priced(f.provider_event_id)]
        fixture = fixtures[member_pick * 7 % len(fixtures)]
        await cache.fetch_odds([fixture.provider_event_id], max_age_seconds=settings.odds_cache_pick_ttl_seconds)
        member = (await db.execute(text(
            "select player_id from league_memberships where league_id = :l order by player_id offset :o limit 1"),
            {"l": gw.league_id, "o": member_pick % 12})).scalar()
        await db.execute(text(
            "insert into picks (id, league_id, gameweek_id, fixture_id, player_id, market, outcome, runner_name, "
            "odds_at_pick, status, pick_scope) values (gen_random_uuid(), :l, :g, :f, :p, 'MATCH_ODDS', 'HOME', 'H', 2.1, "
            "'pending', 'selection') on conflict do nothing"),
            {"l": gw.league_id, "g": gw.id, "f": fixture.id, "p": member})
        await db.commit()


async def main() -> None:
    windows = int(sys.argv[1])
    clock = Clock(datetime(2026, 10, 1, 5, 0, tzinfo=LON))
    install_clock(clock)
    await seed(windows)
    cat = Catalogue(clock)
    inner = OddsApiProvider("review-fake-key", client=httpx.AsyncClient(
        transport=httpx.MockTransport(cat.handler), base_url="https://mock.odds-api.invalid/v3"))
    cache = CachingOddsProvider(
        inner, ttl_seconds=settings.odds_cache_ttl_seconds,
        unpriced_ttl_seconds=settings.odds_cache_unpriced_ttl_seconds,
        rate_limited_cooldown_seconds=settings.odds_rate_limited_cooldown_seconds,
        hourly_request_limit=settings.odds_hourly_request_limit,
        daily_request_limit=settings.odds_daily_request_limit,
        pick_reserve_requests=settings.odds_pick_reserve_requests,
        isolation_requests=settings.odds_isolation_requests, clock=clock.monotonic)
    odds_session._client = cache  # type: ignore[attr-defined]
    odds_session._validated_at = datetime.now(UTC)  # type: ignore[attr-defined]

    refresh_hours = {int(h) for h in settings.odds_refresh_slate_hours.split(",")}
    per_job: dict[str, list[int]] = defaultdict(list)
    hourly_counter_vs_truth: list[tuple[str, int, int]] = []
    withheld = 0
    end = datetime(2026, 10, 4, 0, 0, tzinfo=LON).astimezone(UTC)
    picks_done = 0
    hour_start_truth = 0
    while clock.now_utc < end:
        lon = clock.london()
        if lon.minute == 0:
            hour_start_truth = cat.total
        jobs = []
        if lon.minute == 0:
            if lon.hour == 6:
                jobs.append(("discover_fixtures", sched.run_discover_fixtures))
            if lon.hour == 7:
                jobs.append(("warm_odds_marker", sched.run_warm_odds_marker))
            if lon.hour in refresh_hours:
                jobs.append(("refresh_slate", sched.run_refresh_slate))
            if lon.hour in (18, 20, 22):
                jobs.append(("settle_gameweeks", sched.run_settle_gameweeks))
            jobs.append(("lock_gameweeks", sched.run_lock_gameweeks))
        if lon.minute == 1:
            jobs.append(("open_gameweeks", sched.run_open_gameweeks))
        for name, job in jobs:
            before = cat.total
            await job()
            if cat.total - before or name in ("refresh_slate", "discover_fixtures", "warm_odds_marker", "settle_gameweeks"):
                per_job[f"{lon:%a} {name}"].append(cat.total - before)
        # Members: a card load every minute 08:00-23:00 (saturated), picks on Saturday.
        if 8 <= lon.hour < 23:
            before_budget = cache.budget().hour_used
            await card_load(cache, clock.naive_utc())
            _ = before_budget
        if lon.weekday() == 5 and lon.hour in (9, 10, 11, 12, 13) and lon.minute in (5, 25, 45) and picks_done < 15:
            await picks_for_saturday(cache, clock.naive_utc(), picks_done)
            picks_done += 1
        if lon.minute == 59:
            b = cache.budget()
            hourly_counter_vs_truth.append((lon.strftime("%a %H:00"), b.hour_used, cat.total - hour_start_truth))
        clock.now_utc += timedelta(minutes=1)
    by_day = Counter()
    for hour, n in cat.by_hour.items():
        by_day[hour[:3]] += n
    sat = {h: n for h, n in cat.by_hour.items() if h.startswith("Sat")}
    mismatches = [(h, c, t) for h, c, t in hourly_counter_vs_truth if c != t]
    result = {
        "windows": windows,
        "uptime": subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip(),
        "truth_total": cat.total,
        "provider_requests_made": inner.requests_made,
        "plan_counter_day_used_at_end": cache.budget().day_used,
        "by_day": dict(by_day),
        "saturday_peak_hour": max(sat.items(), key=lambda kv: kv[1]) if sat else None,
        "saturday_by_hour": dict(sorted(sat.items())),
        "by_kind": dict(cat.by_kind),
        "per_job_run": {k: v for k, v in per_job.items()},
        "hourly_counter_vs_truth_mismatches": mismatches,
        "pick_freezes": picks_done,
    }
    (HERE / f"budget-{windows}w.json").write_text(json.dumps(result, indent=1, default=str))
    line = (f"{windows} window(s): Sat total {by_day.get('Sat', 0)}, peak {result['saturday_peak_hour']}, "
            f"Fri {by_day.get('Fri', 0)}, Thu(from 05:00) {by_day.get('Thu', 0)}; truth {cat.total} = "
            f"requests_made {inner.requests_made}; counter mismatches {len(mismatches)}; "
            f"refresh runs {[v for k, v in per_job.items() if 'Sat refresh' in k]}; "
            f"discover {[v for k, v in per_job.items() if 'Sat discover' in k]}; "
            f"warm {[v for k, v in per_job.items() if 'Sat warm' in k]}; "
            f"settle {[v for k, v in per_job.items() if 'Sat settle' in k]} | {result['uptime']}")
    with open(HERE / "budget-summary.txt", "a") as fh:
        fh.write(line + "\n")
    print(line)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
