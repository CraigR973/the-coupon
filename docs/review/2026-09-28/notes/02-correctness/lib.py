"""Shared helpers for the lens-02 driver scripts.

Import this FIRST: it points the app's settings at the scratch database written by
harness/stack.py (stack name `corr`) and forces ODDS_PROVIDER=fake before `src` loads.
Run scripts with the gate venv and cwd = the scratchpad (never a directory with a .env):

    ~/.cache/the-coupon/ci-local-venv/bin/python <script>.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-craigrobinson-the-coupon/"
    "3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad"
)
NOTES = Path(__file__).resolve().parent
API_DIR = "/Users/craigrobinson/the-coupon/apps/api"
STATE = json.loads((SCRATCH / "stack-corr.json").read_text())
API = "http://127.0.0.1:8120"
WEB_ORIGIN = "http://127.0.0.1:4320"

os.environ.update(
    DATABASE_URL=STATE["database_url"],
    JWT_ACCESS_SECRET="review-access-secret-with-at-least-32-characters",
    JWT_REFRESH_SECRET="review-refresh-secret-with-at-least-32-characters",
    SCHEDULER_ENABLED="false",
    ODDS_PROVIDER="fake",
    FRONTEND_ORIGIN=WEB_ORIGIN,
    FOOTBALL_DATA_PROVIDER="none",
    VAPID_PUBLIC_KEY="review-dummy-public",
    VAPID_PRIVATE_KEY="review-dummy-private",
)
os.environ.pop("ENVIRONMENT", None)
for p in (API_DIR, str(NOTES)):
    if p not in sys.path:
        sys.path.insert(0, p)

import richfake  # noqa: E402
from src.auth import create_access_token  # noqa: E402
from src.database import AsyncSessionLocal  # noqa: E402
from src.models.profile import Profile  # noqa: E402
from src.services import odds_session as _odds_session_mod  # noqa: E402

FAKE = richfake.build()


def use_rich_fake(fake=None) -> richfake.CountingFake:
    """Make the scheduler's own provider session hand out the rich fake (in this process)."""
    global FAKE
    if fake is not None:
        FAKE = fake
    _odds_session_mod.build_provider = lambda: FAKE  # type: ignore[assignment]
    _odds_session_mod.odds_session._client = None  # force a fresh CachingOddsProvider
    return FAKE


async def tokens() -> dict[str, str]:
    """Access tokens for every profile, minted with the stack's secret (skips the login limit)."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Profile))).scalars().all()
        return {p.display_name: create_access_token(p.id, p.role) for p in rows}


def out(name: str, text: str) -> Path:
    """Append evidence to notes/02-correctness/out/<name>.txt and echo it."""
    d = NOTES / "out"
    d.mkdir(exist_ok=True)
    path = d / f"{name}.txt"
    with path.open("a") as fh:
        fh.write(text.rstrip() + "\n")
    print(text)
    return path


PUSHES: list[dict] = []


def capture_pushes() -> list[dict]:
    """Record pushes in this process instead of sending them (subscriptions are fake)."""
    import json as _json

    from src.services import push_notification_service as _push

    def _capture(subscription_data: dict, payload: str) -> None:
        PUSHES.append({"endpoint": subscription_data.get("endpoint"), **_json.loads(payload)})

    _push._send_push_sync = _capture  # type: ignore[assignment]
    return PUSHES
