"""Activate, suspend or resume the two-game format for one league. Batch 231.

The operator's way to run the site-admin actions in
:mod:`src.services.two_game_rollout_admin` without a browser session: the same functions,
the same checks, one transaction each, and the same audit row naming the site admin given
by ``--actor``. Every command previews unless ``--apply`` is passed — the transaction is
rolled back, so a preview can never write::

    python -m src.two_game_rollout status   --league 2-1-hibs
    python -m src.two_game_rollout activate --league 2-1-hibs --first-week 2026-11-28 \\
        --actor <site-admin profile id> [--retire-untouched-legacy] [--open-at-activation] [--apply]
    python -m src.two_game_rollout suspend  --league 2-1-hibs --actor <id> --reason "..." [--apply]
    python -m src.two_game_rollout resume   --league 2-1-hibs --actor <id> \\
        [--confirm-reconciliation] [--apply]

It prints one JSON document. Exit status 0 is done (or previewed), 2 is refused — nothing
was written and the document says why — and 1 is any other failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

from src import database
from src.models.league import League
from src.services.two_game_rollout_admin import (
    RolloutRefused,
    activate_rollout,
    reconciliation,
    resume_rollout,
    rollout_status,
    suspend_rollout,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def run(
    args: argparse.Namespace, *, now: datetime | None = None
) -> tuple[int, dict[str, Any]]:
    moment = now or _now()
    async with database.AsyncSessionLocal() as db:
        league_id = await db.scalar(select(League.id).where(League.slug == args.league))
        if league_id is None:
            return 2, {"refused": {"code": "NOT_FOUND", "message": f"No league {args.league!r}"}}
        try:
            if args.command == "status":
                return 0, {"applied": False, "result": await rollout_status(db, league_id, moment)}
            actor = uuid.UUID(args.actor)
            result: dict[str, Any]
            if args.command == "activate":
                activation = await activate_rollout(
                    db,
                    league_id=league_id,
                    first_week=date.fromisoformat(args.first_week),
                    actor_id=actor,
                    now=moment,
                    retire_untouched_legacy=args.retire_untouched_legacy,
                    open_at_activation=args.open_at_activation,
                )
                result = activation.as_json()
            elif args.command == "suspend":
                rollout = await suspend_rollout(
                    db, league_id=league_id, actor_id=actor, now=moment, reason=args.reason
                )
                result = {"first_week": rollout.first_week.isoformat(), "suspended": True}
            elif args.apply:
                report = await resume_rollout(
                    db,
                    league_id=league_id,
                    actor_id=actor,
                    now=moment,
                    confirm_reconciliation=args.confirm_reconciliation,
                )
                result = report.as_json()
            else:
                result = (await reconciliation(db, league_id, moment)).as_json()
        except RolloutRefused as exc:
            await db.rollback()
            return 2, {"refused": exc.body()}
        if args.apply:
            await db.commit()
        else:
            await db.rollback()
        return 0, {"applied": bool(args.apply), "result": result}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="show the rollout, games and obligations")
    status.add_argument("--league", required=True, help="league slug")
    for name, text in (
        ("activate", "write the rollout row for an untouched future Saturday"),
        ("suspend", "stop new entries and openings; billing and settlement continue"),
        ("resume", "lift a suspension after reviewing its reconciliation"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--league", required=True, help="league slug")
        command.add_argument("--actor", required=True, help="the site admin's profile id")
        command.add_argument("--apply", action="store_true", help="commit; without it, preview")
        if name == "activate":
            command.add_argument("--first-week", required=True, help="Saturday, YYYY-MM-DD")
            command.add_argument("--retire-untouched-legacy", action="store_true")
            command.add_argument("--open-at-activation", action="store_true")
        if name == "suspend":
            command.add_argument("--reason", required=True)
        if name == "resume":
            command.add_argument("--confirm-reconciliation", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    code, document = asyncio.run(run(args))
    print(json.dumps(document, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
