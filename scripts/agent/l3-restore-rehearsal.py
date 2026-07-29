#!/usr/bin/env python3
"""Restore an L3 logical backup into a disposable pip-pgserver database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from pgserver import get_server

_ROOT = Path("/Users/craigrobinson/the-coupon")
_PYTHON = Path("/Users/craigrobinson/app-starter/apps/api/.venv/bin/python")
_ALEMBIC = Path("/Users/craigrobinson/app-starter/apps/api/.venv/bin/alembic")


def _run(command: list[str], env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=_ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).replace(
            env.get("DATABASE_URL", ""),
            "<redacted-database-url>",
        )
        raise SystemExit(
            f"Disposable restore command failed: {Path(command[0]).name}\n{detail[-2000:]}"
        )
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit("Backup file does not exist")
    if args.input.stat().st_mode & 0o077:
        raise SystemExit("Backup file must not be group/world accessible")

    checksum = hashlib.sha256(args.input.read_bytes()).hexdigest()
    os.environ["LANG"] = "C"
    os.environ["LC_ALL"] = "C"
    with tempfile.TemporaryDirectory(prefix="the-coupon-l3-restore-") as temp_dir:
        server = get_server(Path(temp_dir) / "pgdata", cleanup_mode="delete")
        database_url = server.get_uri().replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "development",
            "FRONTEND_ORIGIN": "http://localhost:4173",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "JWT_ACCESS_SECRET": "l3-disposable-access-secret-000000000",
            "JWT_REFRESH_SECRET": "l3-disposable-refresh-secret-00000000",
            "PYTHONPATH": str(_ROOT / "apps/api"),
            "PYTHONUTF8": "1",
            "SCHEDULER_ENABLED": "false",
        }
        _run(
            [
                str(_ALEMBIC),
                "-c",
                str(_ROOT / "apps/api/alembic.ini"),
                "upgrade",
                "head",
            ],
            env,
        )
        restored = _run(
            [
                str(_PYTHON),
                str(_ROOT / "scripts/agent/l3-logical-backup.py"),
                "restore",
                "--input",
                str(args.input),
            ],
            env,
        )
        readiness = _run(
            [
                str(_PYTHON),
                "-c",
                (
                    "from fastapi.testclient import TestClient; "
                    "from src.main import app; "
                    "client=TestClient(app); "
                    "response=client.get('/api/v1/health/ready'); "
                    "assert response.status_code == 200, response.status_code; "
                    "assert response.json() == {'status':'ready','db':'ok'}; "
                    "print('ready')"
                ),
            ],
            env,
        )
        restored_summary = json.loads(restored)
        print(
            json.dumps(
                {
                    "backup_sha256": checksum,
                    "migration_revision": restored_summary["migration_revision"],
                    "readiness": readiness,
                    "tables": restored_summary["tables"],
                },
                sort_keys=True,
            )
        )
        server.cleanup()


if __name__ == "__main__":
    main()
