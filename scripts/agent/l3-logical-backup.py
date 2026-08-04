#!/usr/bin/env python3
"""Portable application-data backup used by the L3 staging restore rehearsal.

The staging export is allowed only with the canned odds provider. Restore is allowed only to
a loopback database that already has the repository migrations at head. The
backup contains sensitive hashes and is therefore written mode 0600; callers
must delete it after recording the checksum and redacted row-count evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select, text
from src import models as _models  # noqa: F401 - populate Base.metadata
from src.config import Environment, OddsProviderName, settings
from src.database import AsyncSessionLocal, Base

_FORMAT_VERSION = 1


def _application_tables():
    return [
        table
        for table in Base.metadata.sorted_tables
        if table.schema in (None, "public")
    ]


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return {"$type": "enum", "value": value.value}
    if isinstance(value, uuid.UUID):
        return {"$type": "uuid", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"$type": "time", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    raise TypeError(f"Unsupported backup value type: {type(value).__name__}")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    value_type = value.get("$type")
    if value_type == "enum":
        return value["value"]
    if value_type == "uuid":
        return uuid.UUID(value["value"])
    if value_type == "datetime":
        return datetime.fromisoformat(value["value"])
    if value_type == "date":
        return date.fromisoformat(value["value"])
    if value_type == "time":
        return time.fromisoformat(value["value"])
    if value_type == "decimal":
        return Decimal(value["value"])
    if value_type == "bytes":
        return base64.b64decode(value["value"])
    return {key: _decode(item) for key, item in value.items()}


def _require_staging_export() -> None:
    if settings.environment != Environment.staging or (
        settings.odds_provider != OddsProviderName.fake
    ):
        raise SystemExit("Export requires staging with ODDS_PROVIDER=fake")


def _require_loopback_restore() -> None:
    parts = urlsplit(settings.database_url)
    host = parts.hostname
    socket_host = parse_qs(parts.query).get("host", [""])[0]
    local_socket = host is None and socket_host.startswith("/")
    if host not in {"127.0.0.1", "localhost", "::1"} and not local_socket:
        raise SystemExit("Restore target must be a loopback PostgreSQL database")
    if settings.environment != Environment.development:
        raise SystemExit("Restore target requires ENVIRONMENT=development")


async def export_backup(output: Path) -> None:
    _require_staging_export()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing backup: {output}")

    payload: dict[str, Any] = {
        "format_version": _FORMAT_VERSION,
        "migration_revision": None,
        "tables": {},
    }
    counts: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        payload["migration_revision"] = await db.scalar(
            text("select version_num from public.alembic_version")
        )
        for table in _application_tables():
            rows = [
                {key: _encode(value) for key, value in row.items()}
                for row in (await db.execute(select(table))).mappings()
            ]
            payload["tables"][table.name] = rows
            counts[table.name] = len(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)

    print(
        json.dumps(
            {
                "migration_revision": payload["migration_revision"],
                "tables": counts,
            },
            sort_keys=True,
        )
    )


async def restore_backup(input_path: Path) -> None:
    _require_loopback_restore()
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if raw.get("format_version") != _FORMAT_VERSION:
        raise SystemExit("Unsupported logical backup format")

    expected_revision = raw.get("migration_revision")
    expected_tables = raw.get("tables")
    if not isinstance(expected_revision, str) or not isinstance(expected_tables, dict):
        raise SystemExit("Malformed logical backup")

    restored: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        current_revision = await db.scalar(
            text("select version_num from public.alembic_version")
        )
        if current_revision != expected_revision:
            raise SystemExit(
                f"Migration mismatch: backup={expected_revision} target={current_revision}"
            )

        for table in _application_tables():
            existing = await db.scalar(select(func.count()).select_from(table))
            if existing:
                raise SystemExit(f"Restore target table is not empty: {table.name}")
            raw_rows = expected_tables.get(table.name)
            if not isinstance(raw_rows, list):
                raise SystemExit(f"Backup is missing table: {table.name}")
            rows = [
                {key: _decode(value) for key, value in raw_row.items()}
                for raw_row in raw_rows
            ]
            if rows:
                await db.execute(table.insert(), rows)
            restored[table.name] = len(rows)
        await db.commit()

        verified = {
            table.name: await db.scalar(select(func.count()).select_from(table))
            for table in _application_tables()
        }
        if verified != restored:
            raise SystemExit("Restored row counts do not match the backup")

    print(
        json.dumps(
            {
                "migration_revision": expected_revision,
                "tables": verified,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--output", type=Path, required=True)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "export":
        asyncio.run(export_backup(args.output))
    else:
        asyncio.run(restore_backup(args.input))


if __name__ == "__main__":
    main()
