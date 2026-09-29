"""OPS-17: a real scheduled job, due while the event loop is busy for 1.5 s, is dropped.

Uses create_scheduler() unchanged except that lock_gameweeks' function is wrapped to
record that it ran and its next run is moved 2 s ahead. The loop is then blocked for
1.5 s at the due moment (a stand-in for a CPU-heavy request on the one worker).
Writes misfire-demo.txt.
"""
import asyncio, logging, sys, time
from datetime import UTC, datetime, timedelta
from pathlib import Path
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
import src.scheduler as sched

ran, missed = [], []
class Catch(logging.Handler):
    def emit(self, record):
        if "missed by" in record.getMessage():
            missed.append(record.getMessage())
logging.getLogger("apscheduler").addHandler(Catch()); logging.getLogger("apscheduler").setLevel(logging.INFO)

async def main():
    lines = []
    for block in (0.5, 1.5):
        ran.clear(); missed.clear()
        s = sched.create_scheduler()
        async def fake_lock():
            ran.append(time.time())
        s.start()
        job = s.get_job("lock_gameweeks")
        due = datetime.now(UTC) + timedelta(seconds=2)
        job.modify(func=fake_lock)
        job.modify(next_run_time=due)
        await asyncio.sleep(1.9)
        time.sleep(block)  # the one worker's event loop is busy past the due time
        await asyncio.sleep(1.5)
        s.shutdown(wait=False)
        lines.append(f"loop busy {block}s over the due time: ran={len(ran)} missed={missed[:1]}")
    Path(__file__).with_name("misfire-demo.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
asyncio.run(main())
