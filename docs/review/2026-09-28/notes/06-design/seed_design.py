"""Lens 06 seed: lens 03's seed_states.py (copied, paths changed) plus five extra members.

The extra members (Hana, Ivan, Jo, Kai, Lee — PIN 1234) join the-coupon so the league
looks like a real one on standings, and so the per-league pick budget (50/hour) can be
exhausted for real by five members x ten submissions (PICK_SUBMIT_LIMIT 10/hour each).

Original docstring follows.

Seed every state lens 03 needs on top of the e2e server's base seed.

Run with the gate's venv while `stack_design.py --name design` is up:

    ~/.cache/the-coupon/ci-local-venv/bin/python \
        docs/review/2026-09-28/notes/06-design/seed_design.py [--reset] [--login]

--reset  POST /__e2e/seed first (truncates profiles, leagues, fixtures) — the base
         seed is Alice, Bob, Carol (PIN 1234), league `the-coupon`, one open round.
--login  log each persona in once over HTTP and write <scratchpad>/design-sessions.json
         (access, refresh, player) for Playwright to inject into localStorage.
         The durable login limit is 5 / 15 min per name+IP, so this clears the
         scratch rate-limit table first (scratch database only).

What it adds (all in process, with the app's own models, against the scratch DB):
  * Alice -> site admin (role=admin); still league admin of the-coupon.
  * Dave  -> a member with no league (first-run home).
  * Erin  -> a pending join request to the-coupon (league becomes public_request).
  * the-coupon's open round -> locks in 3 days (so captures never race the lock).
  * an invite token REVIEWINVITE1 on the-coupon (for /join/:token).
  * league `sunday-club` (fixture scope, match odds only, Bob admin, Alice member)
    with a LOCKED round holding Alice's and Bob's pending picks.
  * season 2025 archive for the-coupon: rounds 37 and 38, settled, with won / lost /
    void picks for Alice, Bob and Carol, and a 2025 season calendar row.
Nothing here can reach production or a live provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
STATE = json.loads((SCRATCH / "stack-design.json").read_text())
API = STATE["api"]
os.environ.update(
    DATABASE_URL=STATE["database_url"],
    JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters",
    JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters",
    SCHEDULER_ENABLED="false",
    ODDS_PROVIDER="fake",
)
os.environ.pop("ENVIRONMENT", None)
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

from sqlalchemy import select, text  # noqa: E402

from src.auth import hash_pin  # noqa: E402
from src.database import AsyncSessionLocal  # noqa: E402
from src.models.fixture import Fixture  # noqa: E402
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus  # noqa: E402
from src.models.invite import Invite  # noqa: E402
from src.models.league import League, LeaguePrivacy, PickMarket, PickScope  # noqa: E402
from src.models.league_join_request import JoinRequestStatus, LeagueJoinRequest  # noqa: E402
from src.models.league_membership import LeagueMemberRole, LeagueMembership  # noqa: E402
from src.models.pick import Pick, PickOutcome, PickStatus  # noqa: E402
from src.models.profile import Profile, UserRole  # noqa: E402
from src.models.season_calendar import SeasonCalendar  # noqa: E402

PIN = "1234"
EXTRA = ["Hana", "Ivan", "Jo", "Kai", "Lee"]


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def post(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        f"{API}{path}", method="POST", data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode() or "{}")


async def seed() -> dict:
    async with AsyncSessionLocal() as db:
        people = {
            p.display_name: p
            for p in (await db.execute(select(Profile))).scalars().all()
        }
        alice, bob, carol = people["Alice"], people["Bob"], people["Carol"]
        alice.role = UserRole.admin

        dave = Profile(display_name="Dave", pin_hash=hash_pin(PIN), role=UserRole.player,
                       timezone="Europe/London")
        erin = Profile(display_name="Erin", pin_hash=hash_pin(PIN), role=UserRole.player,
                       timezone="Europe/London")
        db.add_all([dave, erin])
        extra = [Profile(display_name=n, pin_hash=hash_pin(PIN), role=UserRole.player,
                         timezone="Europe/London") for n in EXTRA]
        db.add_all(extra)
        await db.flush()

        coupon = (await db.execute(select(League).where(League.slug == "the-coupon"))).scalar_one()
        coupon.privacy = LeaguePrivacy.public_request
        coupon.description = "The original Saturday coupon."
        open_round = (
            await db.execute(select(Gameweek).where(Gameweek.league_id == coupon.id))
        ).scalar_one()
        open_round.locks_at_utc = now() + timedelta(days=3)

        db.add_all([LeagueMembership(league_id=coupon.id, player_id=x.id) for x in extra])
        db.add(LeagueJoinRequest(league_id=coupon.id, player_id=erin.id,
                                 status=JoinRequestStatus.pending))
        db.add(Invite(token="REVIEWINVITE1", display_name_hint="Frank", league_id=coupon.id,
                      created_by=alice.id, expires_at=now() + timedelta(days=7)))

        fixtures = (await db.execute(select(Fixture).order_by(Fixture.kickoff_utc))).scalars().all()
        arsenal = next(f for f in fixtures if f.home == "Arsenal")
        forfar = next(f for f in fixtures if f.home == "Forfar Athletic")

        # League two: a different claim scope and market set, and a LOCKED round.
        sunday = League(
            slug="sunday-club", name="Sunday Club", created_by=bob.id,
            pick_scope=PickScope.fixture, offered_markets=[PickMarket.MATCH_ODDS],
            description="One game each, match result only.",
        )
        db.add(sunday)
        await db.flush()
        db.add_all([
            LeagueMembership(league_id=sunday.id, player_id=bob.id, role=LeagueMemberRole.admin),
            LeagueMembership(league_id=sunday.id, player_id=alice.id),
        ])
        locked = Gameweek(league_id=sunday.id, starts_on=open_round.starts_on, number=1,
                          status=GameweekStatus.locked,
                          locks_at_utc=now() - timedelta(hours=1))
        db.add(locked)
        await db.flush()
        db.add_all([GameweekFixture(gameweek_id=locked.id, fixture_id=f.id) for f in fixtures])
        db.add_all([
            Pick(league_id=sunday.id, gameweek_id=locked.id, fixture_id=arsenal.id,
                 player_id=alice.id, market=PickMarket.MATCH_ODDS, outcome=PickOutcome.HOME,
                 runner_name="Arsenal", odds_at_pick=Decimal("2.10"),
                 pick_scope=PickScope.fixture),
            Pick(league_id=sunday.id, gameweek_id=locked.id, fixture_id=forfar.id,
                 player_id=bob.id, market=PickMarket.MATCH_ODDS, outcome=PickOutcome.AWAY,
                 runner_name="Brechin City", odds_at_pick=Decimal("3.40"),
                 pick_scope=PickScope.fixture),
        ])

        # Season 2025 archive for the-coupon: two settled rounds.
        cal = await db.get(SeasonCalendar, 2025)
        if cal is None:
            db.add(SeasonCalendar(season=2025, week_one_anchor=date(2025, 8, 16), extra_weeks=[]))
        archive = [
            (date(2026, 4, 25), 37, [("Liverpool", "Everton"), ("Leeds United", "Burnley")],
             [(alice, 0, PickMarket.MATCH_ODDS, PickOutcome.HOME, "Liverpool", "1.62", PickStatus.won),
              (bob, 1, PickMarket.MATCH_ODDS, PickOutcome.DRAW, "The Draw", "3.60", PickStatus.lost),
              (carol, 1, PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES, "Yes", "1.90", PickStatus.void)]),
            (date(2026, 5, 2), 38, [("Chelsea", "Arsenal"), ("Aston Villa", "Newcastle United")],
             [(alice, 0, PickMarket.MATCH_ODDS, PickOutcome.AWAY, "Arsenal", "2.45", PickStatus.lost),
              (bob, 1, PickMarket.MATCH_ODDS, PickOutcome.HOME, "Aston Villa", "2.20", PickStatus.won),
              (carol, 0, PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES, "Yes", "1.72", PickStatus.won)]),
        ]
        for n, (day, number, games, picks) in enumerate(archive):
            kick = datetime.combine(day, datetime.min.time()) + timedelta(hours=14)
            rows = [
                Fixture(provider_event_id=f"review-2025-{number}-{i}", home=h, away=a,
                        kickoff_utc=kick, competition="English Premier League",
                        competition_id="10932509")
                for i, (h, a) in enumerate(games)
            ]
            db.add_all(rows)
            gw = Gameweek(league_id=coupon.id, starts_on=day, number=number,
                          status=GameweekStatus.settled,
                          locks_at_utc=kick - timedelta(minutes=30),
                          settled_at=kick + timedelta(hours=3))
            db.add(gw)
            await db.flush()
            db.add_all([GameweekFixture(gameweek_id=gw.id, fixture_id=r.id) for r in rows])
            for who, idx, market, outcome, runner, odds, status in picks:
                o = Decimal(odds)
                pts = int((o * 10).quantize(Decimal("1"))) if status == PickStatus.won else 0
                db.add(Pick(league_id=coupon.id, gameweek_id=gw.id, fixture_id=rows[idx].id,
                            player_id=who.id, market=market, outcome=outcome,
                            runner_name=runner, odds_at_pick=o, points_awarded=pts,
                            status=status, pick_scope=PickScope.selection))
        await db.commit()
        return {
            "coupon_round": str(open_round.id),
            "sunday_round": str(locked.id),
            "people": {p: str(v.id) for p, v in {**people, "Dave": dave, "Erin": erin, **{x.display_name: x for x in extra}}.items()},
        }


async def clear_rate_limits() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM rate_limit_counters"))
        await db.commit()


def login_all(names: list[str]) -> dict:
    out = {}
    for name in names:
        out[name] = post("/api/v1/auth/login", {"display_name": name, "pin": PIN})
    return out


async def run(a: argparse.Namespace) -> dict:
    # One event loop for the whole run: the app's engine pool is bound to the loop
    # that first used it, so two asyncio.run() calls break the second.
    result: dict = {}
    if a.reset:
        result["base"] = post("/__e2e/seed")
        result["extra"] = await seed()
    if a.login:
        await clear_rate_limits()
        sessions = login_all(["Alice", "Bob", "Carol", "Dave", *EXTRA])
        (SCRATCH / "design-sessions.json").write_text(json.dumps(sessions, indent=2))
        result["sessions"] = {k: {"player": v.get("player")} for k, v in sessions.items()}
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true")
    p.add_argument("--login", action="store_true")
    a = p.parse_args()
    print(json.dumps(asyncio.run(run(a)), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
