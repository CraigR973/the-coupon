"""Four rounds and three members in 2-1 Hibs are called the wrong thing.

Batch 74, the owner's first and fourth points (2026-08-25). Two unrelated corrections
that share a shape — both rewrite a name people have already used, both are production
data, and neither has a screen in the product that could do it.

**The renumbering reverses a decision Batch 68 made deliberately.**
``backfill_august_2026.py:459`` left 8 and 15 August unnumbered rather than renumber
22 August, reasoning that members had been told 22 August was "Gameweek 1". The owner's
call on 2026-08-25 is that the season should read 1-4 from 8 August, so 22 August becomes
Gameweek 3 and that name is rewritten. Four rows, and no code follows them:
:func:`~src.services.gameweek.next_gameweek_number` is one past the season *maximum*, so
once these read 1-4 the next discovered round takes 5 with nothing else changed.

**The rename changes how three people sign in.** ``profiles.display_name`` is globally
unique and *is* the login identifier (``routers/auth.py:228``), which is why this is not
cosmetic and why it is not ``league_memberships.display_name_override`` — that one is
per-league and changes nothing about signing in. Consequences, carried here rather than
discovered afterwards:

* Nobody is signed out. The JWT subject is the player id, so live sessions are unaffected.
* The **next** sign-in needs the new name, as does any ``pin/reset-request``. Both match
  ``display_name`` exactly (``auth.py:228``, ``auth.py:695``). **The three must be told.**
* The freed names become registrable by anyone. Note this is *worse* than deleting a
  member: ``auth.py:436``'s case-insensitive reservation deliberately includes
  soft-deleted rows, so a departed member keeps their name — but a renamed one releases
  it, because no row holds it at all afterwards.
* ``invites.display_name_hint`` and the audit payloads keep the old strings, correctly.
  Both are records of what was true when they were written, not pointers to a profile.

**It fails closed, like Batch 68.** Every round and every profile must resolve to exactly
one row or the run raises before writing anything. In particular a target name already
held by somebody else aborts the whole run, including the renumbering.

Idempotent: a round already carrying its number is left alone, and a profile already
carrying its new name resolves *through* that name, so a second run is a no-op rather
than a failure.

Run it with::

    python -m src.backfill_names_and_numbers --dry-run
    python -m src.backfill_names_and_numbers --apply

Scope: one league's four rounds and three profiles. No admin rename screen — nothing in
the product can change a display name after registration, which is a real gap and the
obvious follow-up, but it is not this batch.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.profile import Profile

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: The one league this batch touches.
LEAGUE_SLUG = "2-1-hibs"

#: What each round's ``number`` must read afterwards, keyed by ``starts_on``.
#:
#: Written as the whole intended sequence rather than as a diff, so the file states the
#: outcome and the run is idempotent by construction: applying it twice is applying the
#: same four numbers twice.
ROUND_NUMBERS: dict[date, int] = {
    date(2026, 8, 8): 1,
    date(2026, 8, 15): 2,
    date(2026, 8, 22): 3,  # was "Gameweek 1" — the name Batch 68 declined to rewrite
    date(2026, 8, 29): 4,
}

#: Old display name to new. Both sides are matched case-insensitively.
RENAMES: dict[str, str] = {
    "Craig": "Craig Robinson",
    "Birch": "Marc Birch",
    "Lewis": "Lewis Steele",
}


class BackfillError(RuntimeError):
    """Something did not resolve to exactly one row. Nothing is written."""


@dataclass
class RoundChange:
    """One round's number, as it is and as it must be."""

    starts_on: date
    gameweek_id: uuid.UUID
    was: int | None
    now: int

    @property
    def changing(self) -> bool:
        return self.was != self.now


@dataclass
class NameChange:
    """One member's display name, as it is and as it must be."""

    player_id: uuid.UUID
    was: str
    now: str

    @property
    def changing(self) -> bool:
        return self.was != self.now


async def _league(db: AsyncSession) -> League:
    league = (
        await db.execute(select(League).where(League.slug == LEAGUE_SLUG))
    ).scalar_one_or_none()
    if league is None:
        raise BackfillError(f"league {LEAGUE_SLUG!r} not found")
    return league


async def _plan_rounds(db: AsyncSession, league: League) -> list[RoundChange]:
    """The four rounds, resolved and paired with the number each must carry.

    ``uq_gameweeks_league_starts_on`` makes at most one row possible per date, so the only
    failure this can find is a date with *no* round — which is worth stopping on rather
    than numbering around: a season that reads 1, 2, 4 is a worse outcome than a run that
    refuses and says which Saturday is missing.
    """
    changes: list[RoundChange] = []
    missing: list[str] = []
    for starts_on, number in sorted(ROUND_NUMBERS.items()):
        gameweek = (
            await db.execute(
                select(Gameweek).where(
                    Gameweek.league_id == league.id,
                    Gameweek.starts_on == starts_on,
                )
            )
        ).scalar_one_or_none()
        if gameweek is None:
            missing.append(starts_on.isoformat())
            continue
        changes.append(
            RoundChange(
                starts_on=starts_on,
                gameweek_id=gameweek.id,
                was=gameweek.number,
                now=number,
            )
        )
    if missing:
        raise BackfillError(f"{LEAGUE_SLUG} has no round on: {', '.join(missing)}")
    return changes


async def _holders(db: AsyncSession, name: str) -> list[Profile]:
    """Every profile holding this name, case-insensitively and including deleted rows.

    Deleted rows are included for the same reason ``auth.py:436`` includes them: a
    soft-deleted profile still holds its name, so renaming *onto* one would create the
    duplicate identity that check exists to prevent.
    """
    rows = await db.execute(select(Profile).where(func.lower(Profile.display_name) == name.lower()))
    return list(rows.scalars().all())


async def _plan_names(db: AsyncSession) -> list[NameChange]:
    """The three renames, resolved through either the old name or the new one.

    Resolving through both is what makes a repeat run a no-op instead of a failure, and
    the four branches below are separated so that "already done" and "somebody else took
    it" cannot be confused — they look identical if you only count rows.
    """
    changes: list[NameChange] = []
    problems: list[str] = []
    for old, new in RENAMES.items():
        old_rows = await _holders(db, old)
        new_rows = await _holders(db, new)
        if len(old_rows) > 1 or len(new_rows) > 1:  # pragma: no cover — uq_ prevents it
            problems.append(f"{old!r}/{new!r}: {len(old_rows)}+{len(new_rows)} rows hold these")
            continue
        if old_rows and new_rows:
            # The abort the batch row asks for. Renaming here would need a name nobody can
            # hold twice, and picking one for the owner is not this script's decision.
            problems.append(
                f"{new!r} is already held by another profile ({new_rows[0].id}) "
                f"while {old!r} still exists ({old_rows[0].id})"
            )
            continue
        if old_rows:
            found = old_rows[0]
            changes.append(NameChange(player_id=found.id, was=found.display_name, now=new))
            continue
        if new_rows:
            # Already renamed by an earlier run. Recorded as a no-op so the dry run still
            # accounts for all three rather than silently listing two.
            changes.append(NameChange(player_id=new_rows[0].id, was=new, now=new))
            continue
        problems.append(f"neither {old!r} nor {new!r} matches any profile")
    if problems:
        raise BackfillError("; ".join(problems))
    return changes


async def plan(db: AsyncSession) -> tuple[list[RoundChange], list[NameChange]]:
    """Resolve everything and decide nothing. The dry run *is* this function.

    Both halves are planned before either is applied, so a name collision stops the
    renumbering too. They are independent corrections, but a run that half-succeeded
    would leave the owner reasoning about which half.
    """
    league = await _league(db)
    return await _plan_rounds(db, league), await _plan_names(db)


async def apply(db: AsyncSession) -> tuple[list[RoundChange], list[NameChange]]:
    """Write both halves, then prove the season reads the way it was asked to."""
    rounds, names = await plan(db)

    for round_change in rounds:
        if not round_change.changing:
            continue
        gameweek = await db.get(Gameweek, round_change.gameweek_id)
        if gameweek is None:  # pragma: no cover — planned id must exist
            raise BackfillError(f"round {round_change.gameweek_id} vanished mid-run")
        gameweek.number = round_change.now

    for name_change in names:
        if not name_change.changing:
            continue
        profile = await db.get(Profile, name_change.player_id)
        if profile is None:  # pragma: no cover — planned id must exist
            raise BackfillError(f"profile {name_change.player_id} vanished mid-run")
        profile.display_name = name_change.now

    await db.flush()
    await _assert_season_reads(db)
    return rounds, names


async def _assert_season_reads(db: AsyncSession) -> None:
    """The four rounds read 1-4 in date order, checked against the database not the plan.

    Re-read rather than trusted because there is no unique constraint on
    ``(league_id, number)`` — ``uq_gameweeks_league_starts_on`` is the only one — so a
    duplicate number is something only an explicit check can catch.
    """
    league = await _league(db)
    rows = (
        await db.execute(
            select(Gameweek.starts_on, Gameweek.number)
            .where(
                Gameweek.league_id == league.id,
                Gameweek.starts_on.in_(list(ROUND_NUMBERS)),
            )
            .order_by(Gameweek.starts_on)
        )
    ).all()
    got = [(starts_on, number) for starts_on, number in rows]
    want = sorted(ROUND_NUMBERS.items())
    if got != want:
        raise BackfillError(f"season does not read as asked: {got} != {want}")


def _describe(rounds: list[RoundChange], names: list[NameChange]) -> str:
    lines = ["rounds:"]
    for round_change in rounds:
        was = "unnumbered" if round_change.was is None else f"Gameweek {round_change.was}"
        verb = "->" if round_change.changing else "== "
        lines.append(f"    {round_change.starts_on}  {was:<12} {verb} Gameweek {round_change.now}")
    lines.append("names:")
    for name_change in names:
        verb = "->" if name_change.changing else "== "
        lines.append(f"    {name_change.was:<16} {verb} {name_change.now}")
        if name_change.changing:
            lines.append(
                f"        frees {name_change.was!r} for anyone to register, and "
                f"{name_change.now!r} is needed at the next sign-in"
            )
    return "\n".join(lines)


async def _run(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not apply_changes:
            rounds, names = await plan(db)
            print(_describe(rounds, names))
            print("\nDRY RUN — nothing written.")
            return
        rounds, names = await apply(db)
        await db.commit()
        print(_describe(rounds, names))
        print(f"\nAPPLIED at {datetime.now(UTC).isoformat()}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="resolve everything, write nothing")
    group.add_argument("--apply", action="store_true", help="renumber and rename")
    args = parser.parse_args()
    asyncio.run(_run(apply_changes=bool(args.apply)))


if __name__ == "__main__":
    main()
