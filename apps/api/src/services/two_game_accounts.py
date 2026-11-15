"""Requester-only records; never export another member or provider/payment payload."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    MembershipInterval,
    WeeklyFeeObligation,
)


async def export_two_game_records(db: AsyncSession, player_id: uuid.UUID) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for model, key in ((GroupPick, "group_picks"), (FantasyPick, "fantasy_picks")):
        rows = (
            await db.execute(
                select(model, Fixture)
                .join(Fixture, Fixture.id == model.fixture_id)
                .where(model.player_id == player_id)
                .order_by(model.week_id, model.id)
            )
        ).all()
        picks = []
        for pick, fixture in rows:
            value: dict[str, Any] = dict(
                id=str(pick.id),
                league_id=str(pick.league_id),
                week_id=str(pick.week_id),
                game_id=str(pick.game_id),
                game_kind=pick.game_kind,
                fixture_id=str(pick.fixture_id),
                fixture=f"{fixture.home} v {fixture.away}",
                kickoff_utc=fixture.kickoff_utc.isoformat(),
                market=pick.market,
                outcome=pick.outcome,
                selection=pick.runner_name,
                status=pick.status,
                revision=pick.revision,
                operation_id=str(pick.operation_id),
            )
            if isinstance(pick, FantasyPick):
                value.update(
                    slot=pick.slot,
                    frozen_odds=str(pick.frozen_odds),
                    quoted_at=pick.quoted_at.isoformat(),
                    provider=pick.provider,
                    bookmaker=pick.bookmaker,
                    points=pick.points_awarded,
                )
            picks.append(value)
        output[key] = picks
    output["game_operations"] = [
        dict(
            league_id=str(row.league_id),
            week_id=str(row.week_id),
            game_id=str(row.game_id),
            game_kind=row.game_kind,
            slot=row.slot,
            operation_id=str(row.operation_id),
        )
        for row in await db.scalars(
            select(GameOperation)
            .where(GameOperation.player_id == player_id)
            .order_by(GameOperation.id)
        )
    ]
    output["membership_intervals"] = [
        dict(
            league_id=str(row.league_id),
            joined_at=row.joined_at.isoformat(),
            left_at=row.left_at.isoformat() if row.left_at else None,
            provenance=row.provenance,
        )
        for row in await db.scalars(
            select(MembershipInterval)
            .where(MembershipInterval.player_id == player_id)
            .order_by(MembershipInterval.joined_at)
        )
    ]
    output["weekly_fees"] = [
        dict(
            league_id=str(row.league_id),
            week_id=str(row.week_id),
            week_label=row.week_label.isoformat(),
            billing_start=row.billing_start.isoformat(),
            billing_end=row.billing_end.isoformat(),
            amount_pence=row.amount_pence,
            owed_at=row.owed_at.isoformat(),
        )
        for row in await db.scalars(
            select(WeeklyFeeObligation)
            .where(WeeklyFeeObligation.player_id == player_id)
            .order_by(WeeklyFeeObligation.week_label)
        )
    ]
    return output
