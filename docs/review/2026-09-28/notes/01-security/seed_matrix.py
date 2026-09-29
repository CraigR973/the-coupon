"""Seed the extra actors the security matrix needs, on top of POST /__e2e/seed.

Run AFTER the harness stack has seeded (it truncates profiles/leagues on seed):

    ~/.cache/the-coupon/ci-local-venv/bin/python seed_matrix.py

Reads <scratchpad>/stack-sec.json for the scratch DATABASE_URL. Writes
<scratchpad>/matrix-actors.json (ids + minted access tokens, scratch secret only) and
prints the ids. Tokens are minted with the harness's JWT secret instead of logging in,
so the durable login limit is never spent by the matrix; the auth lifecycle is probed
separately over real /auth/login.

Actors
  anon            no token
  alice           league A (the-coupon) admin            (from e2e seed)
  bob, carol      league A members                        (from e2e seed)
  hank            league A second admin (co-admin, for the demote->reset chain)
  sadie           SITE ADMIN, plain member of league A (SEC-15 target)
  gary            league B admin AND plain member of league A (SEC-15 "any league's admin")
  dave            league B admin, league C admin
  erin            league B member
  frank           outsider (no league)
  sam             SITE ADMIN, member of nothing (SEC-17)
  v1..v5          lockout victims, league A members
League B `league-b` private, own round from the canned slate (open, locks in 2h).
League C `league-c` public_request, Dave admin; Frank has a pending join request.
League D `league-d` soft-deleted, with an active unclaimed invite (SEC-26).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
state = json.loads((SCRATCH / "stack-sec.json").read_text())
os.environ["DATABASE_URL"] = state["database_url"]
os.environ["JWT_ACCESS_SECRET"] = "review-access-secret-with-at-least-32-characters"
os.environ["JWT_REFRESH_SECRET"] = "review-refresh-secret-with-at-least-32-characters"
os.environ["ODDS_PROVIDER"] = "fake"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ.pop("ENVIRONMENT", None)
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

from sqlalchemy import select  # noqa: E402

from src.auth import create_access_token, generate_join_code, generate_opaque_token, hash_pin  # noqa: E402
from src.database import AsyncSessionLocal  # noqa: E402
from src.models.gameweek import GameweekStatus  # noqa: E402
from src.models.invite import Invite  # noqa: E402
from src.models.league import League, LeaguePrivacy  # noqa: E402
from src.models.league_join_request import JoinRequestStatus, LeagueJoinRequest  # noqa: E402
from src.models.league_membership import LeagueMemberRole, LeagueMembership  # noqa: E402
from src.models.profile import Profile, UserRole  # noqa: E402
from src.services.betfair import SAMPLE_SATURDAY, FakeBetfair  # noqa: E402
from src.services.gameweek import latest_gameweek, sync_slate, window_for  # noqa: E402

PIN = "1234"  # the e2e seed's PIN; weak-PIN rule applies only at register/change


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def main() -> None:
    out: dict[str, object] = {}
    async with AsyncSessionLocal() as db:
        league_a = (await db.execute(select(League).where(League.slug == "the-coupon"))).scalar_one()
        profiles = {
            p.display_name.lower(): p
            for p in (await db.execute(select(Profile))).scalars().all()
        }

        def mk(name: str, role: UserRole = UserRole.player) -> Profile:
            p = Profile(display_name=name, pin_hash=hash_pin(PIN), role=role, timezone="Europe/London")
            db.add(p)
            profiles[name.lower()] = p
            return p

        for name in ("Hank", "Gary", "Dave", "Erin", "Frank", "V1", "V2", "V3", "V4", "V5"):
            mk(name)
        mk("Sadie", UserRole.admin)
        mk("Sam", UserRole.admin)
        await db.flush()

        def member(league: League, p: Profile, admin: bool = False) -> None:
            db.add(
                LeagueMembership(
                    league_id=league.id,
                    player_id=p.id,
                    role=LeagueMemberRole.admin if admin else LeagueMemberRole.player,
                )
            )

        member(league_a, profiles["hank"], admin=True)
        member(league_a, profiles["sadie"])
        member(league_a, profiles["gary"])
        for v in ("v1", "v2", "v3", "v4", "v5"):
            member(league_a, profiles[v])
        league_a.max_members = 50

        league_b = League(
            slug="league-b", name="League B", created_by=profiles["dave"].id,
            privacy=LeaguePrivacy.private, join_code=generate_join_code(), max_members=50,
        )
        league_c = League(
            slug="league-c", name="League C", created_by=profiles["dave"].id,
            privacy=LeaguePrivacy.public_request, join_code=generate_join_code(), max_members=50,
        )
        league_d = League(
            slug="league-d", name="League D (deleted)", created_by=profiles["dave"].id,
            privacy=LeaguePrivacy.private, join_code=generate_join_code(), max_members=50,
        )
        db.add_all([league_b, league_c, league_d])
        await db.flush()
        member(league_b, profiles["dave"], admin=True)
        member(league_b, profiles["gary"], admin=True)
        member(league_b, profiles["erin"])
        member(league_c, profiles["dave"], admin=True)
        member(league_d, profiles["dave"], admin=True)

        slate = await FakeBetfair.with_sample_data().fetch_slate(window_for(league_b), SAMPLE_SATURDAY)
        gw_b = await sync_slate(db, league_b, slate)
        assert gw_b is not None
        gw_b.status = GameweekStatus.open
        gw_b.locks_at_utc = _now() + timedelta(hours=2)

        jr = LeagueJoinRequest(
            league_id=league_c.id, player_id=profiles["frank"].id,
            status=JoinRequestStatus.pending, requested_at=_now(), created_at=_now(),
        )
        db.add(jr)
        inv_b = Invite(
            token=generate_opaque_token(), league_id=league_b.id, created_by=profiles["dave"].id,
            expires_at=_now() + timedelta(days=7), is_active=True, created_at=_now(),
        )
        inv_d = Invite(
            token=generate_opaque_token(), league_id=league_d.id, created_by=profiles["dave"].id,
            expires_at=_now() + timedelta(days=7), is_active=True, created_at=_now(),
        )
        db.add_all([inv_b, inv_d])
        await db.flush()
        league_d.deleted_at = _now()

        gw_a = await latest_gameweek(db, league_a.id)
        await db.commit()

        out["leagues"] = {
            "a": {"slug": league_a.slug, "id": str(league_a.id), "gameweek_id": str(gw_a.id)},
            "b": {"slug": league_b.slug, "id": str(league_b.id), "gameweek_id": str(gw_b.id),
                  "join_code": league_b.join_code},
            "c": {"slug": league_c.slug, "id": str(league_c.id), "join_code": league_c.join_code},
            "d": {"slug": league_d.slug, "id": str(league_d.id)},
        }
        out["join_request_c"] = str(jr.id)
        out["invite_b"] = {"id": str(inv_b.id), "token": inv_b.token}
        out["invite_d"] = {"id": str(inv_d.id), "token": inv_d.token}
        out["actors"] = {
            name: {
                "id": str(p.id),
                "display_name": p.display_name,
                "role": p.role.value,
                "token": create_access_token(p.id, p.role),
            }
            for name, p in profiles.items()
        }

    (SCRATCH / "matrix-actors.json").write_text(json.dumps(out, indent=2))
    printable = {k: v for k, v in out.items() if k != "actors"}
    printable["actors"] = {k: {"id": v["id"], "role": v["role"]} for k, v in out["actors"].items()}
    print(json.dumps(printable, indent=2))


asyncio.run(main())
