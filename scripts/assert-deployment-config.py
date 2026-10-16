"""Assert the evaluated Railway IaC graph and the build/deploy couplings."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tomllib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render-railway-config.mjs"

TARGETS = {
    "the-coupon-staging": (
        "cc2fc994-87c3-4e2e-8d9b-5bcafa496350",
        "333ffc77-ad0d-43af-8436-4865fb9c2946",
    ),
    "the-coupon-production": (
        "e030ebe3-e7fc-43c9-9478-4e80cafaa126",
        "8f18cb49-5137-4557-900a-031bcab4ac38",
    ),
}

EXPECTED_BUILD = {
    "builder": "NIXPACKS",
    "buildEnvironment": "V3",
    "nixpacksConfigPath": "nixpacks.toml",
}
EXPECTED_DEPLOY = {
    "healthcheckPath": "/api/v1/health/ready",
    "healthcheckTimeout": 300,
    "numReplicas": 1,
    "sleepApplication": False,
    "ipv6EgressEnabled": True,
    "multiRegionConfig": {"europe-west4-drams3a": {"numReplicas": 1}},
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3,
    "runtime": "V2",
    "useLegacyStacker": False,
    "limitOverride": {"containers": {"cpu": 0.25, "memoryBytes": 500_000_000}},
}
EXPECTED_VARIABLES = {
    "AVATAR_STORAGE",
    "BF_APP_KEY",
    "BF_CERT_FILE",
    "BF_CERT_PEM_B64",
    "BF_FAKE_MODE",
    "BF_KEY_FILE",
    "BF_KEY_PEM_B64",
    "BF_PASS",
    "BF_USER",
    "DATABASE_URL",
    "ENVIRONMENT",
    "FOOTBALL_API_KEY",
    "FOOTBALL_DATA_PROVIDER",
    "FRONTEND_ORIGIN",
    "JWT_ACCESS_SECRET",
    "JWT_REFRESH_SECRET",
    "LOG_LEVEL",
    "ODDS_API_BOOKMAKER",
    "ODDS_API_KEY",
    "ODDS_PROVIDER",
    "RAILWAY_GIT_COMMIT_SHA",
    "SCHEDULER_ENABLED",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_URL",
    "VAPID_CONTACT_EMAIL",
    "VAPID_PRIVATE_KEY",
    "VAPID_PUBLIC_KEY",
}

# Batch 207 — the payments service (ADR 0009 option B). It shares the image's build but not
# its start: no Alembic, and a boot that refuses an unexpected revision.
EXPECTED_PAYMENTS_DEPLOY = {
    **EXPECTED_DEPLOY,
    "startCommand": "python -m src.payments_service",
    "healthcheckPath": "/health/ready",
}
EXPECTED_PAYMENTS_VARIABLES = {
    "DATABASE_URL",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "MONZO_CLIENT_ID",
    "MONZO_CLIENT_SECRET",
    "MONZO_TOKEN_ENCRYPTION_KEY",
    "MONZO_WEBHOOK_PATH_SECRET",
    "RAILWAY_GIT_COMMIT_SHA",
}
# Owner decision, 2026-10-14: switched off in both projects until the owner creates the
# service. Switching one on is a reviewed commit that changes this expectation too.
# Production switched on by owner decision, 2026-10-15.
EXPECTED_PAYMENTS_ENABLED = {
    "the-coupon-staging": False,
    "the-coupon-production": True,
}


def render(project_id: str, environment_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(RENDERER), project_id, environment_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise AssertionError("Railway IaC did not evaluate")
    return json.loads(result.stdout)


def render_payments() -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(RENDERER), "--payments-service"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise AssertionError("Railway IaC did not render the payments service")
    return json.loads(result.stdout)


def assert_api(api: dict[str, Any]) -> None:
    assert api["address"] == "service.api"
    assert api["name"] == "api"
    assert api["build"] == EXPECTED_BUILD
    assert api["deploy"] == EXPECTED_DEPLOY
    assert set(api["variables"]) == EXPECTED_VARIABLES
    assert all(value == {"type": "preserve"} for value in api["variables"].values())


def assert_payments(payments: dict[str, Any]) -> None:
    assert payments["address"] == "service.payments"
    assert payments["name"] == "payments"
    assert payments["build"] == EXPECTED_BUILD
    assert payments["deploy"] == EXPECTED_PAYMENTS_DEPLOY
    start = payments["deploy"]["startCommand"]
    assert "alembic" not in start, "the payments service must never migrate"
    assert "uvicorn" not in start, "the boot check binds the port itself, after it passes"
    assert set(payments["variables"]) == EXPECTED_PAYMENTS_VARIABLES
    assert all(value == {"type": "preserve"} for value in payments["variables"].values())
    # The two services hold disjoint credentials, which is the point of option B: the API
    # never sees a Monzo secret, and the payments service never sees the API's.
    shared = {"DATABASE_URL", "ENVIRONMENT", "LOG_LEVEL", "RAILWAY_GIT_COMMIT_SHA"}
    api_only = EXPECTED_VARIABLES - shared
    assert not (set(payments["variables"]) & api_only)
    assert not any(name.startswith("MONZO_") for name in EXPECTED_VARIABLES)


def assert_railway() -> None:
    subprocess.run(
        [
            "pnpm",
            "exec",
            "tsc",
            "--noEmit",
            "--module",
            "NodeNext",
            "--moduleResolution",
            "NodeNext",
            "--target",
            "ES2022",
            "--skipLibCheck",
            ".railway/railway.ts",
        ],
        cwd=ROOT,
        check=True,
    )

    payments_render = render_payments()
    assert payments_render["enabled"] == EXPECTED_PAYMENTS_ENABLED
    assert set(payments_render["origins"]) == set(TARGETS)
    for project_name, origin in payments_render["origins"].items():
        # A switched-on service with no origin is one the drift check cannot see.
        if EXPECTED_PAYMENTS_ENABLED[project_name]:
            assert origin.startswith("https://"), f"{project_name} needs its payments origin"
        else:
            assert origin == "" or origin.startswith("https://")
    assert_payments(payments_render["service"])

    for project_name, (project_id, environment_id) in TARGETS.items():
        rendered = render(project_id, environment_id)
        assert rendered["partial"] == "api"
        graph = rendered["graph"]
        assert graph["name"] == project_name
        names = [resource["name"] for resource in graph["resources"]]
        enabled = EXPECTED_PAYMENTS_ENABLED[project_name]
        expected_names = ["api", "payments"] if enabled else ["api"]
        assert names == expected_names, f"{project_name} renders {names}"
        assert_api(graph["resources"][0])
        if enabled:
            assert graph["resources"][1] == payments_render["service"]
        state = "switched on" if enabled else "declared, switched off"
        print(f"{project_name}: renders {', '.join(names)}; payments {state}")

    rejected = subprocess.run(
        ["node", str(RENDERER), "unrecorded-project", "unrecorded-environment"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0, "Railway IaC must reject unrecorded targets"
    assert not (ROOT / "railway.toml").exists()


def assert_nixpacks_and_vercel() -> None:
    nixpacks = tomllib.loads((ROOT / "nixpacks.toml").read_text())
    vercel = json.loads((ROOT / "apps/web/vercel.json").read_text())

    assert "postgresql_17" in nixpacks["phases"]["setup"]["nixPkgs"]
    install_cmd = " ".join(nixpacks["phases"]["install"]["cmds"])
    assert "python -m venv --copies /opt/venv" in install_cmd
    assert "apps/api/requirements.txt" in install_cmd
    assert nixpacks["phases"]["install"]["paths"] == ["/opt/venv/bin"]
    assert int(nixpacks["variables"]["DEPLOY_REPLICA_COUNT"]) == 1

    start = nixpacks["start"]["cmd"]
    assert "python -m src.runtime_secrets" in start
    assert "alembic -c apps/api/alembic.ini upgrade head" in start
    assert "uvicorn src.main:app" in start
    assert start.index("python -m src.runtime_secrets") < start.index(
        "alembic -c apps/api/alembic.ini upgrade head"
    )
    assert start.index("alembic -c apps/api/alembic.ini upgrade head") < start.index(
        "uvicorn src.main:app"
    )

    assert not (ROOT / "vercel.json").exists()
    assert vercel["installCommand"] == "pnpm install --frozen-lockfile"
    assert vercel["buildCommand"] == "pnpm build"
    assert vercel["outputDirectory"] == "dist"
    assert vercel["rewrites"][0]["destination"] == "/index.html"
    assert any(header["source"] == "/sw.js" for header in vercel["headers"])


if __name__ == "__main__":
    assert_railway()
    assert_nixpacks_and_vercel()
