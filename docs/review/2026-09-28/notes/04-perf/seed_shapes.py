"""Seed the two data shapes the 2026-09-13 performance pass measured, rebuilt from its prose.

Run with the gate's venv against the scratch cluster the harness holds open
(`stack.py --name perf --no-api`), never against anything else:

    DATABASE_URL=$(jq -r .database_url <scratch>/stack-perf.json) PYTHONPATH=apps/api \
        ~/.cache/the-coupon/ci-local-venv/bin/python seed_shapes.py production
    ... seed_shapes.py stress      # adds the stress league on top of production

**production** — 5 leagues, largest 12 members, 6-7 rounds each (6 settled + 1 open),
a shared pool of ~1,000 fixtures. The open round on Sat 3 Oct 2026 holds 264 fixtures
across 23 competitions (production's largest measured round, 2026-09-27). League 5
plays a Friday-night window, so the deployment has two distinct windows (the number
`test_request_budget.py` records). Alice is in three leagues, Solo in one.

**stress** — production plus a 50-member league with 40 settled rounds (34 in 2025/26,
6 in 2026/27) at 200 fixtures each and one pick per member per round, plus an open round
on 3 Oct. Season calendars for 2025 and 2026 exist in both shapes (production's table is
empty today, so production pays *less* for labels than measured here).

Everything is bulk SQL for speed; PIN for every profile is 1234.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from src.auth import hash_pin  # noqa: E402

DB = os.environ["DATABASE_URL"]
assert "python_PostgresServer" in DB or "localhost" in DB or "/tmp" in DB, "scratch DB only"

random.seed(20260929)

OPEN_DATE = date(2026, 10, 3)
SETTLED_2026 = [date(2026, 8, 22) + timedelta(weeks=i) for i in range(6)]  # 22 Aug .. 26 Sep
SETTLED_2025 = [date(2025, 8, 16) + timedelta(weeks=i) for i in range(34)]  # 16 Aug .. 4 Apr
COMPETITIONS = [
    "england-premier-league", "england-championship", "england-league-one",
    "england-league-two", "england-amateur-national-league",
    "england-amateur-national-league-north", "england-amateur-national-league-south",
    "scotland-premiership", "scotland-championship", "scotland-league-one",
    "scotland-league-two", "scotland-highland-league", "scotland-challenge-cup",
    "scotland-league-cup", "wales-cymru-premier", "wales-welsh-cup", "england-efl-trophy",
    "england-fa-cup", "england-efl-cup", "scotland-scottish-cup", "wales-cymru-north",
    "wales-cymru-south", "scotland-lowland-league",
]
# Pooled but not played (the trim removes them): production's pool held 36, 23 played.
UNPLAYED = [
    "england-amateur-fa-trophy", "england-amateur-isthmian-premier-division",
    "england-amateur-northern-premier-league", "england-amateur-southern-league-premier-central",
    "england-amateur-southern-league-premier-south", "england-amateur-wsl",
    "england-amateur-premier-league-2", "northern-ireland-premiership",
    "northern-ireland-championship", "england-amateur-fa-vase", "england-amateur-wsl-2",
    "ireland-premier-division", "england-amateur-u21-cup",
]
assert len(COMPETITIONS) == 23 and len(UNPLAYED) == 13

PIN_HASH = hash_pin("1234")


def _utc(day: date, hh: int, mm: int = 0) -> datetime:
    """London is BST (UTC+1) for every date used here except 2025-10-26..2026-03-28."""
    bst = not (date(2025, 10, 26) <= day < date(2026, 3, 29))
    return datetime(day.year, day.month, day.day, hh, mm) - timedelta(hours=1 if bst else 0)


class Seeder:
    def __init__(self, conn) -> None:  # noqa: ANN001
        self.conn = conn
        self.fixtures_by_date: dict[date, list[uuid.UUID]] = {}
        self.fixture_meta: dict[uuid.UUID, tuple[str, str]] = {}

    async def x(self, sql: str, rows: list[dict] | dict | None = None) -> None:
        await self.conn.execute(text(sql), rows or {})

    async def profiles(self, names: list[str]) -> dict[str, uuid.UUID]:
        ids = {name: uuid.uuid4() for name in names}
        await self.x(
            "insert into profiles (id, display_name, pin_hash, role, timezone) "
            "values (:id, :n, :h, 'player', 'Europe/London')",
            [{"id": i, "n": n, "h": PIN_HASH} for n, i in ids.items()],
        )
        return ids

    async def fixtures(self, day: date, count: int, *, extra_unplayed: int = 0, prefix: str = "ev") -> list[uuid.UUID]:
        rows = []
        for k in range(count + extra_unplayed):
            comp = COMPETITIONS[k % 23] if k < count else UNPLAYED[k % 13]
            fid = uuid.uuid4()
            ev = f"{prefix}-{day.isoformat()}-{k}"
            kickoff = _utc(day, 15) if k % 9 else _utc(day, 12, 30)
            rows.append({
                "id": fid, "ev": ev, "h": f"Home {day:%m%d} {k}", "a": f"Away {day:%m%d} {k}",
                "ko": kickoff, "c": comp.replace("-", " ").title(), "ci": comp,
            })
            self.fixture_meta[fid] = (ev, comp)
        await self.x(
            "insert into fixtures (id, provider_event_id, home, away, kickoff_utc, competition, "
            "competition_id) values (:id, :ev, :h, :a, :ko, :c, :ci)",
            rows,
        )
        ids = [r["id"] for r in rows[:count]]
        self.fixtures_by_date.setdefault(day, []).extend(ids)
        return ids

    async def league(
        self, slug: str, name: str, owner: uuid.UUID, members: list[uuid.UUID], *,
        friday: bool = False, max_members: int = 15,
    ) -> uuid.UUID:
        lid = uuid.uuid4()
        start_wd, start_min, end_wd, end_min = (4, 19 * 60 + 45, 4, 19 * 60 + 45) if friday else (5, 900, 5, 900)
        await self.x(
            "insert into leagues (id, slug, name, created_by, max_members, slate_start_weekday, "
            "slate_start_minute, slate_end_weekday, slate_end_minute) values "
            "(:id, :s, :n, :o, :m, :sw, :sm, :ew, :em)",
            {"id": lid, "s": slug, "n": name, "o": owner, "m": max_members,
             "sw": start_wd, "sm": start_min, "ew": end_wd, "em": end_min},
        )
        await self.x(
            "insert into league_memberships (id, league_id, player_id, role) values "
            "(:id, :l, :p, :r)",
            [{"id": uuid.uuid4(), "l": lid, "p": p, "r": "admin" if p == owner else "player"}
             for p in members],
        )
        return lid

    async def round(
        self, league: uuid.UUID, day: date, number: int, fixtures: list[uuid.UUID],
        members: list[uuid.UUID], *, settled: bool, picked: int | None = None,
        friday: bool = False,
    ) -> uuid.UUID:
        gid = uuid.uuid4()
        lock = _utc(day, 19, 15) if friday else _utc(day, 14, 30)
        await self.x(
            "insert into gameweeks (id, league_id, starts_on, number, status, locks_at_utc, "
            "picks_open_at_utc, settled_at) values (:id, :l, :d, :n, :st, :lk, :po, :sa)",
            {"id": gid, "l": league, "d": day, "n": number,
             "st": "settled" if settled else "open", "lk": lock,
             "po": lock - timedelta(days=6), "sa": lock + timedelta(hours=6) if settled else None},
        )
        await self.x(
            "insert into gameweek_fixtures (gameweek_id, fixture_id) values (:g, :f)",
            [{"g": gid, "f": f} for f in fixtures],
        )
        who = members if picked is None else members[:picked]
        chosen = random.sample(fixtures, len(who))
        rows = []
        for player, fixture in zip(who, chosen, strict=True):
            odds = round(random.uniform(1.3, 9.0), 2)
            if settled:
                roll = random.random()
                status = "won" if roll < 0.35 else ("void" if roll > 0.97 else "lost")
                points = round(odds * 10) if status == "won" else 0
            else:
                status, points = "pending", None
            rows.append({
                "id": uuid.uuid4(), "l": league, "g": gid, "f": fixture, "p": player,
                "o": odds, "st": status, "pts": points,
                "ca": lock - timedelta(hours=random.randint(1, 100)),
            })
        if rows:
            await self.x(
                "insert into picks (id, league_id, gameweek_id, fixture_id, player_id, market, "
                "outcome, runner_name, odds_at_pick, points_awarded, status, pick_scope, "
                "created_at, updated_at) values (:id, :l, :g, :f, :p, 'MATCH_ODDS', 'HOME', "
                "'Home', :o, :pts, :st, 'selection', :ca, :ca)",
                rows,
            )
        return gid


async def production(conn) -> None:  # noqa: ANN001
    s = Seeder(conn)
    await s.x("TRUNCATE TABLE profiles, leagues, fixtures, season_calendars CASCADE")
    await s.x(
        "insert into season_calendars (season, week_one_anchor, extra_weeks) values "
        "(2025, '2025-08-09', '{}'), (2026, '2026-08-08', '{}')"
    )
    names = ["Alice", "Solo"] + [f"Member {i:02d}" for i in range(1, 29)]
    p = await s.profiles(names)
    alice, solo = p["Alice"], p["Solo"]
    others = [p[n] for n in names[2:]]
    shapes = [  # slug, members, friday
        ("the-coupon", [alice, solo] + others[0:10], False),   # 12
        ("sunday-club", [alice] + others[10:19], False),        # 10
        ("office", [alice] + others[19:26], False),             # 8
        ("family", others[0:6], False),                         # 6
        ("friday-night", others[22:26], True),                  # 4, second window
    ]
    # Pool: ~130 fixtures per settled Saturday, 264 on the open one, a Friday card of 40.
    for day in SETTLED_2026:
        await s.fixtures(day, 130, extra_unplayed=6)
    await s.fixtures(OPEN_DATE, 264, extra_unplayed=10)
    fridays = [d - timedelta(days=1) for d in SETTLED_2026 + [OPEN_DATE]]
    for day in fridays:
        await s.fixtures(day, 12)
    for slug, members, friday in shapes:
        lid = await s.league(slug, slug.replace("-", " ").title(), members[0], members,
                             friday=friday)
        days = fridays if friday else SETTLED_2026 + [OPEN_DATE]
        for n, day in enumerate(days, start=1):
            is_open = n == len(days)
            await s.round(lid, day, n, s.fixtures_by_date[day], members, settled=not is_open,
                          picked=(len(members) * 2) // 3 if is_open else None, friday=friday)


async def stress(conn) -> None:  # noqa: ANN001
    s = Seeder(conn)
    existing = (await conn.execute(text("select count(*) from leagues where slug='stress-50'"))).scalar()
    assert existing == 0, "stress league already seeded"
    names = [f"Stress {i:02d}" for i in range(1, 51)]
    p = await s.profiles(names)
    members = [p[n] for n in names]
    lid = await s.league("stress-50", "Stress Fifty", members[0], members, max_members=50)
    # Existing pool dates: reuse their fixtures and top each up to 200.
    pool = {}
    for day in SETTLED_2026 + [OPEN_DATE]:
        rows = (await conn.execute(text(
            "select id from fixtures where kickoff_utc::date = :d and competition_id not like "
            "'england-amateur-f%' and competition_id not like '%ireland%' order by provider_event_id"),
            {"d": day})).scalars().all()
        pool[day] = list(rows)
    n = 0
    for day in SETTLED_2025:
        n += 1
        fixtures = await s.fixtures(day, 200, prefix="st")
        await s.round(lid, day, n, fixtures, members, settled=True)
    for day in SETTLED_2026:
        n += 1
        have = pool[day][:200]
        if len(have) < 200:
            have = have + await s.fixtures(day, 200 - len(have), prefix="st")
        # distinct event ids for the top-up: fixtures() keys on k, so offset the names
        await s.round(lid, day, n, have, members, settled=True)
    n += 1
    await s.round(lid, OPEN_DATE, n, pool[OPEN_DATE][:264], members, settled=False, picked=30)


async def main() -> None:
    shape = sys.argv[1]
    engine = create_async_engine(DB)
    async with engine.begin() as conn:
        if shape == "production":
            await production(conn)
        elif shape == "stress":
            await stress(conn)
        else:
            raise SystemExit("shape is production or stress")
    async with engine.connect() as conn:
        for table in ("profiles", "leagues", "league_memberships", "fixtures", "gameweeks",
                      "gameweek_fixtures", "picks", "season_calendars"):
            count = (await conn.execute(text(f"select count(*) from {table}"))).scalar()
            print(f"{table:20s} {count}")
        await conn.execute(text("analyze"))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
