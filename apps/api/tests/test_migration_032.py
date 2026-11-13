"""Populated 031 upgrade, running old payment writer, and synthetic forward restore."""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pgserver
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import PayerMapping
from src.models.profile import Profile, UserRole
from src.payments_service.ingest import Recorded, link_payment, record_link_payment

API = Path(__file__).resolve().parents[1]
NOW = datetime(2060, 1, 10, 15)
HISTORY = (
    "profiles",
    "leagues",
    "league_memberships",
    "gameweeks",
    "fixtures",
    "picks",
    "gameweek_fixtures",
    "ledger_entries",
    "payer_mappings",
    "notification_sends",
    "member_notifications",
    "gameweek_completions",
)


def uri(database: str) -> str:
    return (
        make_url(os.environ["DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )


@pytest_asyncio.fixture
async def scratch(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    # db_engine ensures the canonical PostgreSQL fixture is available; all DDL below
    # targets a separately named disposable database on that same scratch server.
    original = os.environ["DATABASE_URL"]
    name = f"coupon_032_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    target = uri(name)
    engine = create_async_engine(target)
    try:
        os.environ["DATABASE_URL"] = target
        yield engine
    finally:
        await engine.dispose()
        os.environ["DATABASE_URL"] = original
        async with admin.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": name},
            )
            await conn.execute(text(f'DROP DATABASE "{name}"'))
        await admin.dispose()


async def migrate(revision: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, Config(str(API / "alembic.ini")), revision)


def transaction(link: str, suffix: str, *, known: bool = True) -> dict:
    return {
        "id": f"tx_Synthetic{suffix}",
        "created": NOW.isoformat() + "Z",
        "amount": 100,
        "currency": "GBP",
        "metadata": {"universal_payment_link_id": link},
        "counterparty": {
            "name": "Synthetic payer",
            "user_id": "user_Synthetic" if known else "user_Unknown",
        },
    }


async def ingest(db: AsyncSession, link: str, suffix: str, *, known: bool = True) -> Recorded:
    payment = link_payment(transaction(link, suffix, known=known))
    assert payment is not None
    return await record_link_payment(db, payment, counting_since=datetime(2059, 1, 1))


async def seed_031(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, str]:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        player = Profile(
            display_name=f"synthetic-{uuid.uuid4().hex}", pin_hash="synthetic", role=UserRole.player
        )
        db.add(player)
        await db.flush()
        link = f"unipaylink_Synthetic{uuid.uuid4().hex}"
        league = League(
            slug=f"synthetic-{uuid.uuid4().hex}",
            name="Synthetic migration league",
            created_by=player.id,
            entry_fee_pence=100,
            monzo_link_id=link,
        )
        db.add(league)
        unrelated = League(
            slug=f"unrelated-{uuid.uuid4().hex}",
            name="Unrelated free Friday league",
            created_by=player.id,
            entry_fee_pence=None,
            slate_start_weekday=4,
            slate_start_minute=19 * 60,
            slate_end_weekday=6,
            slate_end_minute=22 * 60,
            lock_offset_minutes=45,
        )
        db.add(unrelated)
        await db.flush()
        db.add(LeagueMembership(league_id=league.id, player_id=player.id))
        db.add(LeagueMembership(league_id=unrelated.id, player_id=player.id))
        db.add(
            PayerMapping(league_id=league.id, player_id=player.id, monzo_user_id="user_Synthetic")
        )
        await db.flush()
        assert await ingest(db, link, "Before") == Recorded.matched
        assert await ingest(db, link, "Queued", known=False) == Recorded.queued
        week, fixture = uuid.uuid4(), uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO gameweeks (id,league_id,starts_on,number,status,locks_at_utc,"
                "settled_at) VALUES (:week,:league,'2060-01-03',3,'settled',"
                "'2060-01-03 14:30','2060-01-03 18:00')"
            ),
            {"week": week, "league": league.id},
        )
        await db.execute(
            text(
                "INSERT INTO fixtures (id,provider_event_id,home,away,kickoff_utc,"
                "competition,competition_id) VALUES (:id,'synthetic-event','Home','Away',"
                "'2060-01-03 15:00','League Two','scotland-league-two')"
            ),
            {"id": fixture},
        )
        await db.execute(
            text("INSERT INTO gameweek_fixtures VALUES (:week,:fixture)"),
            {"week": week, "fixture": fixture},
        )
        await db.execute(
            text(
                "INSERT INTO gameweeks (id,league_id,starts_on,number,status,locks_at_utc) "
                "VALUES (:id,:league,'2060-01-02',8,'open','2060-01-02 18:15')"
            ),
            {"id": uuid.uuid4(), "league": unrelated.id},
        )
        await db.execute(
            text(
                "INSERT INTO picks (id,league_id,gameweek_id,fixture_id,player_id,"
                "market,outcome,runner_name,odds_at_pick,status,points_awarded) "
                "VALUES (:id,:league,:week,:fixture,:player,'MATCH_ODDS','HOME',"
                "'Home',2.15,'won',22)"
            ),
            {
                "id": uuid.uuid4(),
                "league": league.id,
                "week": week,
                "fixture": fixture,
                "player": player.id,
            },
        )
        for kind, amount in (("round_due", -100), ("due_reversal", 100)):
            await db.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(id,league_id,player_id,gameweek_id,kind,amount_pence) "
                    "VALUES (:id,:league,:player,:week,:kind,:amount)"
                ),
                {
                    "id": uuid.uuid4(),
                    "league": league.id,
                    "player": player.id,
                    "week": week,
                    "kind": kind,
                    "amount": amount,
                },
            )
        await db.execute(
            text(
                "INSERT INTO notification_sends (id,kind,subject) "
                "VALUES (:id,'round_settled',:subject)"
            ),
            {"id": uuid.uuid4(), "subject": str(week)},
        )
        await db.execute(
            text(
                "INSERT INTO member_notifications "
                "(id,user_id,league_id,kind,title,body,url) "
                "VALUES (:id,:player,:league,'round_settled','Synthetic',"
                "'Synthetic result','/synthetic')"
            ),
            {"id": uuid.uuid4(), "player": player.id, "league": league.id},
        )
        await db.execute(
            text(
                "INSERT INTO gameweek_completions "
                "(id,gameweek_id,final_picker_id,final_picker_name,selection,odds,member_count) "
                "VALUES (:id,:week,:player,'Synthetic','Home',2.15,1)"
            ),
            {"id": uuid.uuid4(), "week": week, "player": player.id},
        )
        await db.commit()
        return league.id, player.id, link


async def history(engine: AsyncEngine) -> dict:
    async with engine.connect() as conn:
        return {
            table: await conn.scalar(
                text(
                    "SELECT coalesce(jsonb_agg(to_jsonb(t)-'format' "
                    "ORDER BY to_jsonb(t)::text),'[]'::jsonb) "
                    f"FROM {table} t"
                )
            )
            for table in HISTORY
        }


@pytest.mark.asyncio
async def test_populated_031_upgrade_preserves_history_and_running_old_payments(
    scratch: AsyncEngine,
) -> None:
    await migrate("031")
    league, player, link = await seed_031(scratch)
    before = await history(scratch)
    await migrate()
    assert await history(scratch) == before
    async with scratch.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM gameweeks WHERE format<>'legacy'")) == 0
        from src.models.two_game import TABLE_NAMES

        for table in TABLE_NAMES:
            assert await conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    async with AsyncSession(scratch) as db:
        assert await ingest(db, link, "After") == Recorded.matched
        assert await ingest(db, link, "After") == Recorded.duplicate
        assert await ingest(db, link, "AfterUnknown", known=False) == Recorded.queued
        await db.execute(
            text(
                "UPDATE ledger_entries SET player_id=:player "
                "WHERE monzo_transaction_id='tx_SyntheticAfterUnknown'"
            ),
            {"player": player},
        )
        await db.execute(
            text(
                "INSERT INTO gameweeks "
                "(id,league_id,starts_on,locks_at_utc) "
                "VALUES (:id,:league,'2060-01-10','2060-01-10 14:30')"
            ),
            {"id": uuid.uuid4(), "league": league},
        )
        await db.commit()
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM ledger_entries "
                    "WHERE monzo_transaction_id='tx_SyntheticAfter'"
                )
            )
            == 1
        )
        assert (
            await db.scalar(
                text(
                    "SELECT amount_pence FROM ledger_entries "
                    "WHERE monzo_transaction_id='tx_SyntheticBefore'"
                )
            )
            == 100
        )


@pytest.mark.asyncio
async def test_synthetic_dump_restore_and_forward_restart_keep_spend_and_history(
    scratch: AsyncEngine, tmp_path: Path
) -> None:
    await migrate("031")
    await seed_031(scratch)
    before = await history(scratch)
    await migrate()
    async with scratch.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO provider_attempts(id,meter,category,reserved_at) "
                "VALUES (:id,'synthetic','quote','2060-01-10 12:00')"
            ),
            {"id": uuid.uuid4()},
        )
        await conn.execute(
            text(
                "INSERT INTO provider_controls(meter,cooldown_until) "
                "VALUES ('synthetic','2060-01-10 12:15')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO provider_work(key,kind,payload,cursor,next_at) "
                "VALUES ('synthetic','settlement','{\"completed\":[1]}',"
                "'page-2','2060-01-10 12:00')"
            )
        )
    binary = Path(pgserver.__file__).parent / "pginstall" / "bin"
    backup = tmp_path / "synthetic.dump"
    source = (
        make_url(os.environ["DATABASE_URL"])
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    subprocess.run(
        [str(binary / "pg_dump"), "--format=custom", "--file", str(backup), "--dbname", source],
        check=True,
        capture_output=True,
    )
    target_name = f"coupon_032_restore_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(os.environ["DATABASE_URL"], isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{target_name}"'))
    target = uri(target_name)
    restored = create_async_engine(target)
    original = os.environ["DATABASE_URL"]
    try:
        target_pg = (
            make_url(target).set(drivername="postgresql").render_as_string(hide_password=False)
        )
        subprocess.run(
            [
                str(binary / "pg_restore"),
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                target_pg,
                str(backup),
            ],
            check=True,
            capture_output=True,
        )
        os.environ["DATABASE_URL"] = target
        await migrate()  # forward-compatible restart, never a destructive downgrade
        assert await history(restored) == before
        async with restored.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM provider_attempts WHERE meter='synthetic'")
                )
                == 1
            )
            assert (
                await conn.scalar(text("SELECT cursor FROM provider_work WHERE key='synthetic'"))
                == "page-2"
            )
            assert await conn.scalar(
                text("SELECT cooldown_until FROM provider_controls WHERE meter='synthetic'")
            ) == datetime(2060, 1, 10, 12, 15)
    finally:
        os.environ["DATABASE_URL"] = original
        await restored.dispose()
        async with admin.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": target_name},
            )
            await conn.execute(text(f'DROP DATABASE "{target_name}"'))
        await admin.dispose()
