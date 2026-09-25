"""Database backup service using pg_dump."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass
class BackupInfo:
    filename: str
    size_bytes: int
    created_at: datetime


def _pg_dsn(database_url: str) -> str:
    """SQLAlchemy asyncpg URL -> libpq postgresql:// DSN, with the password removed.

    The password is supplied out-of-band via PGPASSWORD (see ``_pg_password``) so
    it never appears in the pg_dump argv, which is visible to ``ps``. (P3-6.)

    asyncpg calls its TLS query parameter ``ssl`` while libpq calls the same
    setting ``sslmode``. Normalise it here so the exact Railway DATABASE_URL can
    be reused safely by pg_dump.
    """
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", database_url)
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{parts.username}@{host}" if parts.username else host

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    has_sslmode = any(key == "sslmode" for key, _ in query_items)
    normalised_query = [
        ("sslmode" if key == "ssl" and not has_sslmode else key, value)
        for key, value in query_items
        if not (key == "ssl" and has_sslmode)
    ]
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            urlencode(normalised_query),
            parts.fragment,
        )
    )


def _pg_password(database_url: str) -> str | None:
    """Extract the URL-decoded password from a SQLAlchemy/libpq URL, if present."""
    password = urlsplit(database_url).password
    return unquote(password) if password else None


def _safe_filename(filename: str) -> bool:
    """Accept only filenames that look like our own backup files."""
    return bool(re.fullmatch(r"backup_\d{8}_\d{6}\.sql", filename))


async def create_backup(backup_dir: str, database_url: str) -> BackupInfo:
    path = Path(backup_dir)
    path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    filename = f"backup_{now.strftime('%Y%m%d_%H%M%S')}.sql"
    filepath = path / filename

    env = os.environ.copy()
    password = _pg_password(database_url)
    if password is not None:
        env["PGPASSWORD"] = password

    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--no-password",
        "--format=plain",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(filepath),
        _pg_dsn(database_url),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        if filepath.exists():
            filepath.unlink()
        raise RuntimeError(f"pg_dump failed: {stderr.decode().strip()}")

    size = filepath.stat().st_size
    log.info("backup created", filename=filename, size_bytes=size)
    return BackupInfo(filename=filename, size_bytes=size, created_at=now)


#: The weekly archive's object key: ``<prefix>the-coupon-20260928T030000Z.dump``. A UTC
#: timestamp to the second, so no run can overwrite another — which matters, because the
#: owner's bucket lock refuses overwrites anyway and a collision would fail the upload.
def archive_key(prefix: str, created_at: datetime) -> str:
    return f"{prefix}the-coupon-{created_at.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}.dump"


async def create_archive(database_url: str, destination: Path) -> int:
    """``pg_dump`` the application schema into ``destination``; return its size. Batch 95.

    **Custom format, the ``public`` schema, ownership stripped.** Custom (``-Fc``) is
    compressed and is what ``pg_restore`` reads, including ``--list``, which inspects an
    archive without a database. ``public`` is where every table, sequence and enum this
    application owns lives; the rest of a Supabase database is Supabase's own and would
    collide with the schemas a fresh project already has. Owners differ between projects,
    so they are left out, but grants and row-level-security policies are kept: restoring
    into Supabase has to bring the Data API lockdown back with the data.

    The password travels in ``PGPASSWORD``, never on the command line, as
    :func:`create_backup` does.
    """
    env = os.environ.copy()
    password = _pg_password(database_url)
    if password is not None:
        env["PGPASSWORD"] = password

    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--no-password",
        "--format=custom",
        "--schema=public",
        "--no-owner",
        "--file",
        str(destination),
        _pg_dsn(database_url),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed: {stderr.decode().strip()}")
    size = destination.stat().st_size
    log.info("backup archive created", size_bytes=size)
    return size


def list_backups(backup_dir: str) -> list[BackupInfo]:
    path = Path(backup_dir)
    if not path.exists():
        return []
    files = sorted(
        (f for f in path.glob("backup_*.sql") if _safe_filename(f.name)),
        reverse=True,
    )
    return [
        BackupInfo(
            filename=f.name,
            size_bytes=f.stat().st_size,
            created_at=datetime.fromtimestamp(f.stat().st_mtime, tz=UTC),
        )
        for f in files
    ]


def resolve_backup_path(backup_dir: str, filename: str) -> Path:
    if not _safe_filename(filename):
        raise ValueError("Invalid backup filename")
    base = Path(backup_dir).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Invalid backup filename")
    return target
