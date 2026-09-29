"""The lens-02 API: tests.e2e_server's app, but with the production provider path.

tests.e2e_server overrides get_odds_provider with a bare FakeBetfair carrying two
fixtures on 1 Aug. Here the overrides are removed, so requests go through the real
odds_session -> CachingOddsProvider (pick TTL, budget counter, reserve) exactly as in
production, and odds_session.build_provider hands out the deterministic rich fake.

    PYTHONPATH=apps/api:notes/02-correctness uvicorn corr_server:app --port 8120
(run by corr_api.sh with the scratch DATABASE_URL). ODDS_PROVIDER=fake, scheduler off.
"""

from __future__ import annotations

import richfake
from src.deps import get_odds_provider, get_optional_odds_provider
from src.services import odds_session as _odds_session_mod

import tests.e2e_server as e2e

FAKE = richfake.build()
_odds_session_mod.build_provider = lambda: FAKE  # type: ignore[assignment]
e2e.app.dependency_overrides.pop(get_odds_provider, None)
e2e.app.dependency_overrides.pop(get_optional_odds_provider, None)


@e2e.app.get("/__corr/calls")
async def calls() -> dict[str, int]:
    """How many provider primitives this process has called (counting fake)."""
    return dict(FAKE.calls)


@e2e.app.post("/__corr/reprice")
async def reprice(body: dict) -> dict[str, str]:
    FAKE.reprice(body["event_id"], int(body["selection_id"]), float(body["price"]), body.get("market", "mo"))
    return {"ok": "repriced"}


# Push capture: every push that would have gone to a phone is recorded here instead of
# sent (the subscriptions are fake). Mute and quiet-hours gates still run upstream of this.
from src.services import push_notification_service as _push  # noqa: E402

PUSHES: list[dict] = []


def _capture(subscription_data: dict, payload: str) -> None:
    import json as _json

    PUSHES.append({"endpoint": subscription_data.get("endpoint"), **_json.loads(payload)})


_push._send_push_sync = _capture  # type: ignore[assignment]


@e2e.app.get("/__corr/pushes")
async def pushes() -> list[dict]:
    return PUSHES


@e2e.app.delete("/__corr/pushes")
async def clear_pushes() -> dict[str, int]:
    n = len(PUSHES)
    PUSHES.clear()
    return {"cleared": n}


app = e2e.app
