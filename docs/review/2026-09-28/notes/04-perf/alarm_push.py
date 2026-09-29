"""OPS-14 re-drive: the discovery-silence alarm pushes once to site admins, not every run,
and a healthy deployment sends none. Real report_discovery_silence(); webpush recorded.
Scratch DB: temporarily makes Alice a site admin and ages every round's created_at.
Writes alarm-push.txt.
"""
import asyncio, os, sys
from pathlib import Path
os.environ["VAPID_PUBLIC_KEY"] = "review-dummy-public"; os.environ["VAPID_PRIVATE_KEY"] = "review-dummy-private"
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import text
import src.services.push_notification_service as push
import src.scheduler as sched
from src.database import engine

sent = []
push._send_push_sync = lambda sub, payload: sent.append((sub["endpoint"], payload[:80]))

async def x(sql):
    async with engine.begin() as c:
        await c.execute(text(sql))

async def main():
    lines = []
    await x("update gameweeks set status='open' where starts_on in ('2026-10-02','2026-10-03')")
    await x("delete from rate_limit_counters")
    await x("update profiles set role='admin' where display_name='Alice'")
    await x("update gameweeks set created_at = now() - interval '10 days'")
    for run in range(1, 4):
        before = len(sent)
        fired = await sched.report_discovery_silence()
        lines.append(f"stale run {run}: alarm={fired} pushes={len(sent) - before}")
    await x("update gameweeks set created_at = now()")
    await x("delete from rate_limit_counters")
    before = len(sent)
    fired = await sched.report_discovery_silence()
    lines.append(f"healthy run: alarm={fired} pushes={len(sent) - before}")
    lines.append(f"recipients: {sorted(set(e for e, _ in sent))}")
    lines.append(f"payload: {sent[0][1] if sent else None}")
    await x("update profiles set role='player' where display_name='Alice'")
    Path(__file__).with_name("alarm-push.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    await engine.dispose()
asyncio.run(main())
