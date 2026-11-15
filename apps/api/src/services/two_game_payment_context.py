"""API-only receipt context over the same stored targets and pooled FIFO as Home."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.league import League
from src.models.two_game import TwoGameRollout
from src.services.dues import format_pence
from src.services.two_game_reads import GameReadRefused, load_read_data, project_read_data


@dataclass(frozen=True)
class PaymentGameContext:
    standing: str
    destination: str
    targets: list[dict[str, Any]]


async def payment_game_context(
    db: AsyncSession,
    league: League,
    player_id: uuid.UUID,
    now: datetime,
    *,
    two_games_enabled: bool,
) -> PaymentGameContext | None:
    """A receipt describes entitlement; it never allocates the payment to a game.

    Use the caller's transaction after its unique receipt claim. Do not open a second
    connection or change transaction mode here. No fee, quote or calendar is created.
    """
    if not two_games_enabled or league.deleted_at is not None:
        return None
    rollout = await db.get(TwoGameRollout, league.id)
    if rollout is None or not rollout.enabled:
        return None
    try:
        data = await load_read_data(
            db, player_id, now, two_games_enabled=two_games_enabled, league_id=league.id
        )
    except GameReadRefused as exc:
        if exc.status == 404:
            return None
        raise
    projected = (await project_read_data(db, data, include_stats=False)).leagues[0]
    targets: list[dict[str, Any]] = []
    open_targets: list[tuple[datetime, dict[str, Any]]] = []
    lines: list[str] = []
    for card in projected.games:
        stored = next(game for game in data.games if game.id == card.game_id)
        if card.archived and stored.finalized_at is not None:
            continue
        label = f"{card.week_label.day} {card.week_label:%b}"
        target = dict(
            league_id=str(card.league_id),
            week_id=str(card.week_id),
            game_id=str(card.game_id),
            game_kind=card.game_kind,
            week_label=card.week_label.isoformat(),
            entry_state=card.entry_state,
            paid_through=card.fee.paid_through,
            owed_pence=card.fee.amount_owed_pence,
            destination=card.destination + "#payment",
        )
        targets.append(target)
        if card.entry_state == "open" and data.members[league.id].deleted_at is None:
            open_targets.append((card.locks_at, target))
            state = (
                "paid"
                if card.fee.paid_through
                else f"{format_pence(card.fee.amount_owed_pence)} owed before entry"
            )
            lines.append(f"{card.game_kind.title()} for {label}: {state}.")
    for legacy in projected.legacy_rounds:
        if not legacy.can_pick:
            continue
        owed = legacy.fee.owed_pence if legacy.fee else 0
        target = dict(
            league_id=str(legacy.league_id),
            week_id=str(legacy.week_id),
            game_kind="legacy",
            week_label=legacy.starts_on.isoformat(),
            entry_state="open",
            paid_through=owed == 0,
            owed_pence=owed,
            destination=legacy.destination,
        )
        targets.append(target)
        open_targets.append((legacy.locks_at, target))
        label = f"{legacy.starts_on.day} {legacy.starts_on:%b}"
        state = "paid" if owed == 0 else f"{format_pence(owed)} owed before entry"
        lines.append(f"Legacy round for {label}: {state}.")
    ordered = sorted(open_targets, key=lambda item: (item[0], item[1]["destination"]))
    fallback = sorted(targets, key=lambda target: (target["week_label"], target["game_kind"]))
    primary: dict[str, Any] | None = None
    for _, target in ordered:
        if not target["paid_through"]:
            primary = target
            break
    if primary is None and ordered:
        primary = ordered[0][1]
    if primary is None:
        primary = next((target for target in fallback if not target["paid_through"]), None)
    if primary is None and fallback:
        primary = fallback[0]
    return PaymentGameContext(
        standing=" ".join(lines) if lines else "No entry is open. Weekly fees still apply.",
        destination=primary["destination"] if primary else f"/leagues/{league.slug}/predictions",
        targets=targets,
    )
