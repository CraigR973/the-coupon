"""The all-picked transition — recorded once, delivered at least once. Batch 107.

Two functions, and the split between them is the point. :func:`record_completion` decides
*whether this submission completed the round*, and lets the database decide it, because two
members can claim the last two selections seconds apart and both then read a full coupon.
:func:`claim_pending_completion` decides *whether this request should announce it*, and does
that with a row lock, because the announcement is worth exactly one push per round.

The delivery itself lives in ``notification_triggers`` with the other triggers; this module
owns the row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.gameweek_completion import GameweekCompletion

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def record_completion(
    session: AsyncSession,
    gameweek: Gameweek,
    *,
    picker_id: uuid.UUID,
    picker_name: str,
    selection: str,
    odds: Decimal,
    member_count: int,
) -> bool:
    """Write the round's completion event if it does not exist yet.

    Returns whether *this* call created it — that is, whether this submission was the
    completing transition and should therefore replace its ordinary pick alert rather
    than accompany it.

    **The insert is the arbiter, not the count.** The caller reaches here having read a
    full coupon, and so may several other requests at the same instant: the last two
    members claiming seconds apart both commit, and both then read ``12/12``. Asking
    each of them "were you the one who completed it?" has no answer, because for both of
    them the count says yes. ``ON CONFLICT DO NOTHING`` against
    ``uq_gameweek_completions_gameweek`` gives it one: whoever's insert lands completed
    the round, everyone else made an ordinary pick into a coupon that was already full.

    That also makes the retry path free. A submission arriving on an already-complete
    round conflicts, returns ``False``, and sends its ordinary alert — there is no second
    completion event to be had for that round, ever.
    """
    result = await session.execute(
        insert(GameweekCompletion)
        .values(
            id=uuid.uuid4(),
            gameweek_id=gameweek.id,
            final_picker_id=picker_id,
            final_picker_name=picker_name,
            selection=selection,
            odds=odds,
            member_count=member_count,
        )
        .on_conflict_do_nothing(constraint="uq_gameweek_completions_gameweek")
    )
    return bool(result.rowcount)


async def claim_pending_completion(
    session: AsyncSession, gameweek: Gameweek
) -> GameweekCompletion | None:
    """Take exclusive hold of this round's undelivered completion event, if there is one.

    ``None`` is the ordinary answer and means one of three things, all of them fine: the
    round has not completed, its event has already been announced, or another request is
    announcing it right now.

    ``SKIP LOCKED`` rather than a plain ``FOR UPDATE`` because the third case is a
    request the member is waiting on. Delivery is a fan-out of blocking webpush calls, so
    a concurrent submitter that queued behind the lock would be made to wait out somebody
    else's push round-trips before its own pick response returned — to then find the work
    already done and skip it. Skipping immediately reaches the same state sooner.

    The caller stamps :func:`mark_delivered` only once the fan-out has finished, so a
    delivery that raises leaves ``delivered_at`` null and the row is claimed again by the
    next submission on the round.
    """
    return (
        await session.execute(
            select(GameweekCompletion)
            .where(
                GameweekCompletion.gameweek_id == gameweek.id,
                GameweekCompletion.delivered_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()


def mark_delivered(completion: GameweekCompletion) -> None:
    """Stamp a completion event as announced. The caller's commit makes it stick."""
    completion.delivered_at = datetime.now(UTC).replace(tzinfo=None)
