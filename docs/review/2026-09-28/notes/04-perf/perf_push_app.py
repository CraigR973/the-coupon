"""perf_app with push delivery switched on and every webpush replaced by a 179 ms sleep.

179 ms is the per-send time implied by the 13 Sep measurement (49 sends in 8,759 ms).
The sleep runs where the real send runs — in the default thread executor — so the real
`send_notification` path (league mute, preferences, subscriptions, bookkeeping) executes.
Each send appends a line to SENDS_FILE. GET /__perf/pool reports the connection pool.
"""
import os
import sys
import time

os.environ["VAPID_PUBLIC_KEY"] = "review-dummy-public"
os.environ["VAPID_PRIVATE_KEY"] = "review-dummy-private"
sys.path.insert(0, os.path.dirname(__file__))
sys.argv = [sys.argv[0], "serve"]
from measure_api import app  # noqa: E402
import src.services.push_notification_service as push  # noqa: E402
from src.database import engine  # noqa: E402

SENDS_FILE = os.environ["SENDS_FILE"]


def _sleepy_send(subscription_data, payload):  # noqa: ANN001
    time.sleep(0.179)
    with open(SENDS_FILE, "a") as fh:
        fh.write(f"{time.time():.3f} {subscription_data['endpoint']}\n")


push._send_push_sync = _sleepy_send


@app.get("/__perf/pool")
async def pool_state() -> dict:
    pool = engine.pool
    return {"checked_out": pool.checkedout(), "overflow": pool.overflow(), "size": pool.size()}
