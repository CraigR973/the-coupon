"""Undo jobs.py's lock: put the 3 Oct rounds back to open (scratch DB)."""
import asyncio, sys
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from sqlalchemy import text
from src.database import engine
async def main():
    async with engine.begin() as c:
        r = await c.execute(text("update gameweeks set status='open' where starts_on='2026-10-03' and status<>'open'"))
        print("reopened", r.rowcount)
    await engine.dispose()
asyncio.run(main())
