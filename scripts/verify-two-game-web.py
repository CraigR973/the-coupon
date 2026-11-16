#!/usr/bin/env python3
"""Build and exercise real loopback web/API/PG flows without live credentials or services."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

import pgserver

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"
WEB = ROOT / "apps/web"
ARTIFACTS = ROOT / ".local/overnight-two-games/227-browser"
VITE = WEB / "node_modules/vite/bin/vite.js"
SERVERS = []
HANDLES = []


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run(name, args, cwd, env):
    with (ARTIFACTS / f"{name}.log").open("w") as output:
        result = subprocess.run(
            args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT
        )
    if result.returncode:
        raise RuntimeError(
            f"{name} failed ({result.returncode}); see {ARTIFACTS/name}.log"
        )


def serve(name, args, cwd, env, pattern, url):
    log = ARTIFACTS / f"{name}.log"
    handle = log.open("w")
    HANDLES.append(handle)
    process = subprocess.Popen(
        args, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT
    )
    SERVERS.append(process)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited; see {log}")
        if re.search(pattern, log.read_text(errors="replace")):
            try:
                with urlopen(url, timeout=1) as response:
                    if response.status == 200 and process.poll() is None:
                        return
            except (URLError, TimeoutError):
                pass
        time.sleep(0.2)
    raise RuntimeError(f"{name} readiness timeout; see {log}")


def main():
    os.environ["LANG"] = "en_US.UTF-8"
    os.environ["LC_ALL"] = "en_US.UTF-8"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="coupon-two-game-browser-"))
    server = None
    try:
        server = pgserver.get_server(str(work / "pg"), cleanup_mode="delete")
        api_port, web_port = port(), port()
        api_url, web_url = (
            f"http://127.0.0.1:{api_port}",
            f"http://127.0.0.1:{web_port}",
        )
        # Whitelist process essentials, then supply every application setting synthetically.
        base = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "HOME",
                "USER",
                "TMPDIR",
                "LANG",
                "LC_ALL",
                "PLAYWRIGHT_BROWSERS_PATH",
            }
        }
        base.update(LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
        api_env = dict(
            base,
            DATABASE_URL=server.get_uri().replace(
                "postgresql://", "postgresql+asyncpg://", 1
            ),
            JWT_ACCESS_SECRET="local-browser-access-secret-with-at-least32chars",
            JWT_REFRESH_SECRET="local-browser-refresh-secret-with-at-least32chars",
            SCHEDULER_ENABLED="false",
            ODDS_PROVIDER="fake",
            TWO_GAMES_ENABLED="true",
            FRONTEND_ORIGIN=web_url,
            PYTHONPATH=str(API),
            COUPON_TWO_GAME_E2E="local-scratch-only",
        )
        run(
            "migrate",
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            API,
            api_env,
        )
        bundle = work / "dist"
        run(
            "build",
            ["node", str(VITE), "build", "--outDir", str(bundle), "--emptyOutDir"],
            WEB,
            dict(base, VITE_API_URL=api_url),
        )
        serve(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.two_game_e2e_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            API,
            api_env,
            rf"Uvicorn running on {re.escape(api_url)}\b",
            api_url + "/api/v1/health/ready",
        )
        serve(
            "web",
            [
                "node",
                str(VITE),
                "preview",
                "--outDir",
                str(bundle),
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
                "--strictPort",
            ],
            WEB,
            base,
            rf"Local.*{web_port}",
            web_url,
        )
        report = ARTIFACTS / "report.json"
        env = dict(
            base,
            COUPON_TWO_GAME_API_URL=api_url,
            COUPON_TWO_GAME_WEB_URL=web_url,
            COUPON_TWO_GAME_ARTIFACT_DIR=str(ARTIFACTS),
            PLAYWRIGHT_JSON_OUTPUT_FILE=str(report),
        )
        result = subprocess.run(
            [
                "pnpm",
                "--dir",
                str(WEB),
                "exec",
                "playwright",
                "test",
                "--config",
                "playwright.two-games.config.ts",
                "--retries",
                "0",
                "--forbid-only",
                "--max-failures=1",
                "--reporter",
                "line,json",
                "--output",
                str(ARTIFACTS / "playwright"),
            ],
            env=env,
        )
        if result.returncode:
            raise RuntimeError(f"browser checks failed; see {report}")
        stats = json.loads(report.read_text())["stats"]
        if stats["expected"] != 16 or any(
            stats[key] for key in ("unexpected", "flaky", "skipped")
        ):
            raise RuntimeError(f"Incomplete browser acceptance: {stats}")
        print(
            "two-game browser: PASS16, zero failures/flaky/skipped; real loopback API + migrated scratch PG"
        )
    finally:
        for process in reversed(SERVERS):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for handle in HANDLES:
            handle.close()
        if server is not None:
            server.cleanup()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
