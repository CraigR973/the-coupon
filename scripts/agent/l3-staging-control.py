#!/usr/bin/env python3
"""Guarded operator controls for the L3 canned-odds staging verification.

Run this script only through Railway's exact staging variables. It deliberately
refuses production and any live odds provider. Output is limited to counts and state;
credentials, tokens, profile names, and database URLs are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import timedelta

from sqlalchemy import delete, func, select
from src.auth import hash_pin
from src.config import Environment, OddsProviderName, settings
from src.database import AsyncSessionLocal
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickStatus
from src.models.profile import Profile
from src.models.refresh_token import RefreshToken
from src.scheduler import _utc_now, run_lock_gameweeks, run_settle_gameweeks
from src.services.betfair import (
    SAMPLE_ARSENAL_SEL,
    SAMPLE_EPL_MATCH_ODDS_MKT,
    SAMPLE_FORFAR_SEL,
    SAMPLE_SATURDAY,
    SAMPLE_SL2_MATCH_ODDS_MKT,
    FakeBetfair,
)
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_session import odds_session

_SYNTHETIC_NAMES = (
    "Admin",
    "Staging Player 01",
    "Staging Player 02",
    "Staging Player 03",
)


def _require_safe_staging() -> None:
    if settings.environment != Environment.staging:
        raise SystemExit("L3 controls require ENVIRONMENT=staging")
    if settings.odds_provider != OddsProviderName.fake:
        raise SystemExit(
            "L3 controls require ODDS_PROVIDER=fake (or the deprecated BF_FAKE_MODE)"
        )


async def _sample_gameweek(db) -> Gameweek:
    gameweek = (
        await db.execute(
            select(Gameweek).where(Gameweek.saturday_date == SAMPLE_SATURDAY)
        )
    ).scalar_one_or_none()
    if gameweek is None:
        raise SystemExit("Run the refresh-slate job before using L3 controls")
    return gameweek


async def reset_credentials() -> None:
    pin = os.environ.get("L3_SYNTHETIC_PIN", "")
    if len(pin) != 4 or not pin.isdecimal():
        raise SystemExit("L3_SYNTHETIC_PIN must be exactly four digits")

    async with AsyncSessionLocal() as db:
        profiles = list(
            (
                await db.execute(
                    select(Profile).where(
                        Profile.display_name.in_(_SYNTHETIC_NAMES),
                        Profile.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(profiles) != len(_SYNTHETIC_NAMES):
            raise SystemExit(
                f"Expected {len(_SYNTHETIC_NAMES)} synthetic profiles; found {len(profiles)}"
            )

        profile_ids = [profile.id for profile in profiles]
        for profile in profiles:
            profile.pin_hash = hash_pin(pin)
            profile.failed_login_count = 0
            profile.locked_until = None
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id.in_(profile_ids))
        )
        await db.commit()

    print(json.dumps({"synthetic_credentials_reset": len(profiles)}))


async def force_lock() -> None:
    async with AsyncSessionLocal() as db:
        gameweek = await _sample_gameweek(db)
        gameweek.status = GameweekStatus.open
        gameweek.locks_at_utc = _utc_now() - timedelta(minutes=1)
        await db.commit()

    if not await run_lock_gameweeks():
        raise SystemExit("lock job failed")
    print(json.dumps({"lock_job_executions": 1}))


async def settle(*, close_markets: bool) -> None:
    if close_markets:
        provider = await odds_session.acquire()
        # The session hands out a cache wrapper; the canned client is inside it.
        if isinstance(provider, CachingOddsProvider):
            provider = provider.inner
        if not isinstance(provider, FakeBetfair):
            raise SystemExit("Canned settlement requires FakeBetfair")
        provider.close_markets(
            {
                SAMPLE_EPL_MATCH_ODDS_MKT: SAMPLE_ARSENAL_SEL,
                SAMPLE_SL2_MATCH_ODDS_MKT: SAMPLE_FORFAR_SEL,
            }
        )

    if not await run_settle_gameweeks():
        raise SystemExit("settlement job failed")
    print(
        json.dumps(
            {
                "settlement_job_executions": 1,
                "canned_markets_closed": close_markets,
            }
        )
    )


async def summary() -> None:
    async with AsyncSessionLocal() as db:
        gameweek = await _sample_gameweek(db)
        counts = {
            "profiles": await db.scalar(
                select(func.count())
                .select_from(Profile)
                .where(Profile.deleted_at.is_(None))
            ),
            "leagues": await db.scalar(
                select(func.count())
                .select_from(League)
                .where(League.deleted_at.is_(None))
            ),
            "memberships": await db.scalar(
                select(func.count())
                .select_from(LeagueMembership)
                .where(LeagueMembership.deleted_at.is_(None))
            ),
            "fixtures": await db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.gameweek_id == gameweek.id)
            ),
            "picks": await db.scalar(
                select(func.count())
                .select_from(Pick)
                .where(Pick.gameweek_id == gameweek.id)
            ),
            "pending_picks": await db.scalar(
                select(func.count())
                .select_from(Pick)
                .where(
                    Pick.gameweek_id == gameweek.id, Pick.status == PickStatus.pending
                )
            ),
            "won_picks": await db.scalar(
                select(func.count())
                .select_from(Pick)
                .where(Pick.gameweek_id == gameweek.id, Pick.status == PickStatus.won)
            ),
        }
        revision = await db.scalar(select(func.max(Gameweek.saturday_date)))

    print(
        json.dumps(
            {
                "latest_saturday": revision.isoformat()
                if revision is not None
                else None,
                "gameweek_status": gameweek.status.value,
                **counts,
            },
            sort_keys=True,
        )
    )


async def _run(args: argparse.Namespace) -> None:
    _require_safe_staging()
    if args.command == "reset-credentials":
        await reset_credentials()
    elif args.command == "force-lock":
        await force_lock()
    elif args.command == "settle-open":
        await settle(close_markets=False)
    elif args.command == "settle-closed":
        await settle(close_markets=True)
    elif args.command == "summary":
        await summary()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "reset-credentials",
            "force-lock",
            "settle-open",
            "settle-closed",
            "summary",
        ),
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
