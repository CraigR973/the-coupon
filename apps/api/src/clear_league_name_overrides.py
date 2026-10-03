"""Clear every per-league display name, and say how many there were. Batch 181.

``league_memberships.display_name_override`` let a member read under a different name in
one league. Its only writer was ``PUT /leagues/{slug}/members/me/display-name``, which no
screen ever called, and Batch 126 checked a new name only against the league's *current*
members — so it could copy someone outside the league, who then joined under the same name
(review 2026-09-28, SEC-29). The owner's decision on 2026-09-30 removed the route rather
than harden it, and since Batch 181 the roster, the standings, the coupon and the pick
alerts all render the member's global name, which registration keeps unique.

What is left is the names already stored: unread by anything, but still somebody's chosen
name, sitting in a column nothing will ever show again. This clears them. It writes
``NULL`` and nothing else — no membership, profile or audit row is touched — and the
account export, which reports the column as ``your_name_in_this_league``, then reports
nothing, which is the truth.

Soft-deleted memberships are cleared too: the column means nothing on any row now, and a
member who leaves and rejoins restores their old row (``_upsert_membership``).

Run it once after the batch has shipped, dry run first::

    python -m src.clear_league_name_overrides --dry-run
    python -m src.clear_league_name_overrides --apply

Idempotent: with nothing writing the column any more, a second ``--apply`` clears 0.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.league_membership import LeagueMembership


async def count_overrides(db: AsyncSession) -> int:
    """How many memberships, live or left, still carry a per-league name."""
    return (
        await db.execute(
            select(func.count())
            .select_from(LeagueMembership)
            .where(LeagueMembership.display_name_override.is_not(None))
        )
    ).scalar_one()


async def clear_overrides(db: AsyncSession) -> int:
    """Set every stored per-league name to ``NULL``. Returns how many rows changed.

    Commits nothing; the caller owns the transaction, so a dry run can never write.
    """
    result = await db.execute(
        update(LeagueMembership)
        .where(LeagueMembership.display_name_override.is_not(None))
        .values(display_name_override=None)
    )
    return result.rowcount or 0


async def _run(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not apply_changes:
            print(f"per-league names stored: {await count_overrides(db)}")
            print("\nDRY RUN — nothing written.")
            return
        cleared = await clear_overrides(db)
        await db.commit()
        print(f"per-league names cleared: {cleared}")
        print(f"\nAPPLIED at {datetime.now(UTC).isoformat()}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="count them; write nothing")
    group.add_argument("--apply", action="store_true", help="clear them and report the count")
    args = parser.parse_args()
    asyncio.run(_run(apply_changes=bool(args.apply)))


if __name__ == "__main__":
    main()
