"""Give every profile one fake push subscription (endpoint push.invalid/<name>), so the
captured `_send_push_sync` shows exactly who a trigger reached after the mute gates."""
import asyncio

import lib  # noqa: F401
from sqlalchemy import delete, select

from src.database import AsyncSessionLocal
from src.models.notification import PushSubscription
from src.models.profile import Profile


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PushSubscription))
        for p in (await db.execute(select(Profile))).scalars():
            db.add(PushSubscription(user_id=p.id, subscription={
                "endpoint": f"https://push.invalid/{p.display_name}",
                "keys": {"p256dh": "x", "auth": "y"}}, device_hint="review"))
        await db.commit()
        print("subscriptions:", len((await db.execute(select(PushSubscription))).all()))


asyncio.run(main())
