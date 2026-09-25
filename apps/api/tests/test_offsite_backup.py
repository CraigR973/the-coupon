"""Batch 95 — the scored history of the game gets a second copy, off the platform.

The row's verification, in its own words: a restore rehearsal proving the dump is
*recoverable*, not merely written; and a test that the destination is configured and
reachable *before* the dump starts, so a misconfigured target fails loudly rather than
silently producing nothing. Both are here, along with the request signing the upload
depends on, pinned to AWS's own test vectors.

The store is a stand-in — ``httpx.MockTransport`` answering as R2 would — because the
owner has not provisioned the bucket yet, and the job ships switched off until they do.
Everything on this side of the network is real: ``pg_dump``, the archive, ``pg_restore``.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pgserver  # type: ignore[import-untyped,unused-ignore]
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from src.auth import hash_pin
from src.config import settings
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.notification import ActionType, AuditLog
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile, UserRole
from src.scheduler import create_scheduler, run_offsite_backup
from src.services.backup import _pg_dsn, _pg_password, archive_key, create_archive
from src.services.backup_storage import (
    BackupTargetError,
    S3BackupStore,
    authorization_header,
    backup_target_from_settings,
    canonical_query,
)
from src.services.notification_triggers import notify_backup_failed

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

#: The PostgreSQL client tools pgserver ships (16.2) — a dev dependency, so present in the
#: gate and in CI alike, and a client no older than either's server.
_PG_BIN = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin"

_needs_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

_CONFIGURED: dict[str, Any] = {
    "backup_storage": "s3",
    "backup_s3_endpoint": "https://account.eu.r2.cloudflarestorage.com",
    "backup_s3_bucket": "coupon-backups",
    "backup_s3_region": "auto",
    "backup_s3_access_key_id": "test-access-key-id-000000000000",
    "backup_s3_secret_access_key": "test-secret-access-key-0000000000000000",
    "backup_s3_prefix": "production/",
}


def _configured(**overrides: Any) -> Any:
    return settings.model_copy(update={**_CONFIGURED, **overrides})


# ── Request signing, against AWS's own test suite ───────────────────────────────

#: The credentials every vector in AWS's Signature Version 4 test suite is computed with.
_SUITE_ACCESS_KEY = "AKIDEXAMPLE"
_SUITE_SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _suite_signature(query: str) -> str:
    return authorization_header(
        method="GET",
        path="/",
        query=query,
        headers={"Host": "example.amazonaws.com", "X-Amz-Date": "20150830T123600Z"},
        payload_sha256=_EMPTY_SHA256,
        access_key_id=_SUITE_ACCESS_KEY,
        secret_access_key=_SUITE_SECRET,
        region="us-east-1",
        service="service",
        amz_date="20150830T123600Z",
    )


def test_signing_matches_the_get_vanilla_vector() -> None:
    """``aws4_testsuite/get-vanilla``: the simplest request, and the whole algorithm."""
    assert _suite_signature("") == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
        "SignedHeaders=host;x-amz-date, "
        "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"
    )


def test_signing_sorts_the_query_as_the_suite_requires() -> None:
    """``get-vanilla-query-order-key-case``: parameters are signed sorted, and the listing
    this job sends is exactly the string it signs."""
    query = canonical_query([("Param2", "value2"), ("Param1", "value1")])
    assert query == "Param1=value1&Param2=value2"
    assert _suite_signature(query).endswith(
        "Signature=b97d918cfa904a5beff61c982a1b6f458b799221646efd99d3219ec94cdf2500"
    )


# ── The target is resolved before anything else ─────────────────────────────────


def test_an_unconfigured_target_names_every_missing_variable() -> None:
    with pytest.raises(BackupTargetError) as refused:
        backup_target_from_settings(
            _configured(backup_s3_endpoint="", backup_s3_secret_access_key="  ")
        )
    assert "BACKUP_S3_ENDPOINT" in str(refused.value)
    assert "BACKUP_S3_SECRET_ACCESS_KEY" in str(refused.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://account.eu.r2.cloudflarestorage.com",  # plaintext
        "https://account.eu.r2.cloudflarestorage.com/coupon-backups",  # bucket in the path
        "account.eu.r2.cloudflarestorage.com",  # no scheme at all
    ],
)
def test_the_endpoint_must_be_a_bare_https_origin(endpoint: str) -> None:
    with pytest.raises(BackupTargetError, match="bare https"):
        backup_target_from_settings(_configured(backup_s3_endpoint=endpoint))


def test_switched_off_is_not_a_target() -> None:
    with pytest.raises(BackupTargetError, match="'s3'"):
        backup_target_from_settings(_configured(backup_storage="none"))


# ── The job ─────────────────────────────────────────────────────────────────────


class _Ctx:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


def _failure_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _store_answering(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[..., Any]:
    return lambda target: S3BackupStore(target, transport=httpx.MockTransport(handler))


def _audit_reason(session: AsyncMock) -> str:
    rows = [call.args[0] for call in session.add.call_args_list]
    audits = [row for row in rows if isinstance(row, AuditLog)]
    assert len(audits) == 1, rows
    assert audits[0].action_type == ActionType.backup_failed
    return str(audits[0].changes["error"])


async def test_a_misconfigured_target_fails_before_the_database_is_read() -> None:
    """The row's second test: configured is checked first, and loudly."""
    session = _failure_session()
    with (
        patch("src.scheduler.settings", _configured(backup_s3_bucket="")),
        patch("src.scheduler.create_archive", new_callable=AsyncMock) as dump,
        patch("src.scheduler.notify_backup_failed", new_callable=AsyncMock) as alert,
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
    ):
        assert await run_offsite_backup() is False

    dump.assert_not_awaited()
    assert "BACKUP_S3_BUCKET" in _audit_reason(session)
    alert.assert_awaited_once()
    session.commit.assert_awaited_once()


async def test_an_unreachable_target_fails_before_the_database_is_read() -> None:
    """…and reachable is checked next: a refused listing stops the run before pg_dump."""

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="<Error><Code>AccessDenied</Code></Error>")

    session = _failure_session()
    with (
        patch("src.scheduler.settings", _configured()),
        patch("src.scheduler.S3BackupStore", _store_answering(refuse)),
        patch("src.scheduler.create_archive", new_callable=AsyncMock) as dump,
        patch("src.scheduler.notify_backup_failed", new_callable=AsyncMock) as alert,
        patch("src.scheduler.AsyncSessionLocal", return_value=_Ctx(session)),
    ):
        assert await run_offsite_backup() is False

    dump.assert_not_awaited()
    assert "HTTP 403 (AccessDenied)" in _audit_reason(session)
    alert.assert_awaited_once()


@_needs_database
async def test_a_run_lists_then_dumps_then_uploads_a_signed_archive() -> None:
    """The whole job against the gate's own database, in the order the row requires."""
    events: list[str] = []
    uploads: list[httpx.Request] = []

    def store(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            events.append("list")
            return httpx.Response(200, text="<ListBucketResult/>")
        events.append("put")
        uploads.append(request)
        return httpx.Response(200)

    async def dump(database_url: str, destination: Path) -> int:
        events.append("dump")
        return await create_archive(database_url, destination)

    path = f"{_PG_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
    with (
        patch("src.scheduler.settings", _configured(database_url=settings.database_url)),
        patch("src.scheduler.S3BackupStore", _store_answering(store)),
        patch("src.scheduler.create_archive", side_effect=dump),
        patch.dict(os.environ, {"PATH": path}),
    ):
        assert await run_offsite_backup() is True

    assert events == ["list", "dump", "put"]
    (upload,) = uploads
    assert re.fullmatch(
        r"/coupon-backups/production/the-coupon-\d{8}T\d{6}Z\.dump", upload.url.path
    )
    body = upload.content
    assert body.startswith(b"PGDMP"), "not a pg_dump custom-format archive"
    assert upload.headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert upload.headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=test-access-key-id-000000000000/"
    )
    assert "/auto/s3/aws4_request" in upload.headers["authorization"]


def test_archive_keys_are_utc_and_never_collide_within_a_second() -> None:
    at = datetime(2026, 9, 28, 4, 0, 1, tzinfo=UTC)
    assert archive_key("production/", at) == "production/the-coupon-20260928T040001Z.dump"
    assert archive_key("production/", at + timedelta(seconds=1)) != archive_key("production/", at)


# ── The restore rehearsal ───────────────────────────────────────────────────────


def _url_for(database: str) -> str:
    return (
        make_url(os.environ["DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )


@pytest_asyncio.fixture
async def two_scratch_databases() -> AsyncIterator[tuple[str, str]]:
    """A source and an empty restore target of this test's own, dropped afterwards."""
    original = os.environ["DATABASE_URL"]
    names = [f"coupon_backup_{role}_{uuid.uuid4().hex[:10]}" for role in ("src", "dst")]
    admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        for name in names:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()
    try:
        yield _url_for(names[0]), _url_for(names[1])
    finally:
        os.environ["DATABASE_URL"] = original
        admin = create_async_engine(original, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            for name in names:
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": name},
                )
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin.dispose()


async def _migrate_to_head(database_url: str) -> None:
    original = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = database_url
    try:
        await asyncio.to_thread(command.upgrade, Config(str(_ALEMBIC_INI)), "head")
    finally:
        os.environ["DATABASE_URL"] = original


async def _a_settled_week(engine: AsyncEngine) -> uuid.UUID:
    """The history this batch exists to protect: a member, a league, a settled round, and
    one winning pick with the price it was frozen at and the points it scored."""
    async with AsyncSession(engine) as session:
        member = Profile(display_name="Member", pin_hash=hash_pin("8351"), role=UserRole.player)
        session.add(member)
        await session.flush()
        league = League(slug="backup-rehearsal", name="Backup rehearsal", created_by=member.id)
        session.add(league)
        await session.flush()
        session.add(LeagueMembership(league_id=league.id, player_id=member.id))
        kickoff = datetime(2026, 9, 19, 14, 0)
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=date(2026, 9, 19),
            status=GameweekStatus.settled,
            locks_at_utc=kickoff - timedelta(minutes=30),
        )
        fixture = Fixture(
            provider_event_id="ev-backup-rehearsal",
            home="Forfar Athletic",
            away="Brechin City",
            kickoff_utc=kickoff,
            competition="Scottish League Two",
            competition_id="sl2-backup-rehearsal",
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
            status=PickStatus.won,
            points_awarded=25,
        )
        session.add(pick)
        await session.flush()
        pick_id = pick.id  # read before the commit expires it
        await session.commit()
        return pick_id


async def _row_counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
            )
        ).scalars()
        counts = {}
        for table in list(tables):
            counts[table] = (
                await conn.execute(text(f'SELECT count(*) FROM public."{table}"'))
            ).scalar_one()
        return counts


def _pg_restore(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    password = _pg_password(database_url)
    if password is not None:
        env["PGPASSWORD"] = password
    return subprocess.run(
        [str(_PG_BIN / "pg_restore"), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@_needs_database
async def test_the_archive_restores_into_an_empty_database(
    two_scratch_databases: tuple[str, str], tmp_path: Path
) -> None:
    """The row's first test: recoverable, not merely written.

    A database at migration head holding one settled week is archived by the job's own
    function, then restored with ``pg_restore`` into an empty database, and the two are
    compared table by table — then on the one row the batch exists for.
    """
    source_url, target_url = two_scratch_databases
    await _migrate_to_head(source_url)
    source = create_async_engine(source_url)
    target = create_async_engine(target_url)
    try:
        pick_id = await _a_settled_week(source)

        archive = tmp_path / "the-coupon.dump"
        with patch.dict(os.environ, {"PATH": f"{_PG_BIN}{os.pathsep}{os.environ['PATH']}"}):
            size = await create_archive(source_url, archive)
        assert size == archive.stat().st_size > 0

        listing = _pg_restore(target_url, "--list", str(archive))
        assert listing.returncode == 0, listing.stderr
        assert "TABLE DATA public picks" in listing.stdout

        # The runbook's own command. `--clean --if-exists` because a dump of the `public`
        # schema carries `CREATE SCHEMA public`, which every new database already has — so
        # this is for an empty target only, never one holding data.
        restored = _pg_restore(
            target_url,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--exit-on-error",
            "--dbname",
            _pg_dsn(target_url),
            str(archive),
        )
        assert restored.returncode == 0, restored.stderr

        before, after = await _row_counts(source), await _row_counts(target)
        assert after == before
        assert before["picks"] == 1 and before["alembic_version"] == 1

        async with target.connect() as conn:
            head = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
            row = (
                await conn.execute(
                    text("SELECT odds_at_pick, points_awarded, status FROM picks WHERE id = :id"),
                    {"id": pick_id},
                )
            ).one()
        async with source.connect() as conn:
            source_head = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar()
        assert head == source_head
        assert (row.odds_at_pick, row.points_awarded, str(row.status)) == (
            Decimal("2.50"),
            25,
            "won",
        )
    finally:
        await source.dispose()
        await target.dispose()


# ── Scheduling, and the alert ───────────────────────────────────────────────────


def test_switched_off_schedules_nothing() -> None:
    with patch("src.scheduler.settings", _configured(backup_storage="none")):
        scheduler = create_scheduler()
    assert scheduler.get_job("offsite_backup") is None


def test_switched_on_runs_mondays_at_four_london_time() -> None:
    with patch("src.scheduler.settings", _configured()):
        scheduler = create_scheduler()
    job = scheduler.get_job("offsite_backup")
    assert job is not None
    fields = {field.name: str(field) for field in job.trigger.fields}
    assert (fields["day_of_week"], fields["hour"], fields["minute"]) == ("mon", "4", "0")
    assert str(job.trigger.timezone) == "Europe/London"
    assert job.misfire_grace_time == 3600
    assert job.coalesce is True and job.max_instances == 1


def test_a_misconfigured_switch_is_reported_at_boot() -> None:
    """Said on the deploy that introduced the typo, not six days later."""
    with (
        patch("src.scheduler.settings", _configured(backup_s3_access_key_id="")),
        patch("src.scheduler.log") as log,
    ):
        scheduler = create_scheduler()
    assert scheduler.get_job("offsite_backup") is not None
    events = [call.args[0] for call in log.error.call_args_list]
    assert "offsite backup is switched on but misconfigured" in events


async def test_a_failure_pages_the_site_admins_once_a_day() -> None:
    admin = MagicMock(id=uuid.uuid4(), timezone="Europe/London")
    session = AsyncMock()
    with (
        patch(
            "src.services.notification_triggers.consume_durable_limit",
            new_callable=AsyncMock,
            side_effect=[True, False],
        ),
        patch(
            "src.services.notification_triggers._admin_players",
            new_callable=AsyncMock,
            return_value=[admin],
        ),
        patch(
            "src.services.notification_triggers.send_notification", new_callable=AsyncMock
        ) as push,
    ):
        assert await notify_backup_failed(session, "backup target refused a listing") is True
        assert await notify_backup_failed(session, "backup target refused a listing") is False

    push.assert_awaited_once()
    assert push.await_args.args[1] == admin.id
    assert push.await_args.args[2] == "The weekly backup failed"
