"""Bounded member/week form and legacy fee arithmetic over shared loaded inputs."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.services.dues import (
    MemberLedger,
    OwedRound,
    RoundFeeStatus,
    _dues_of,
    allocate,
)
from src.services.member_week_form import member_weeks, recent_member_weeks
from src.services.two_game_read_models import WeeklyForm


def legacy_fee(
    league: League,
    parent: Gameweek,
    member: LeagueMembership,
    ledger: MemberLedger,
    rounds: dict[uuid.UUID, Gameweek],
    recorded: dict[uuid.UUID, int],
    labels: dict[uuid.UUID, str],
) -> RoundFeeStatus | None:
    """Match the existing recorded legacy fee/FIFO policy without querying per card."""
    if league.entry_fee_pence is None or member.deleted_at is not None:
        return None
    owed = dict(ledger.owed_by_round)
    if parent.status in (GameweekStatus.scheduled, GameweekStatus.open):
        owed[parent.id] = recorded.get(
            parent.id, league.entry_fee_pence if parent.status == GameweekStatus.scheduled else 0
        )
    dues = _dues_of(MemberLedger(ledger.credit_pence, owed), rounds)
    through = [due for due in dues if due.starts_on is None or due.starts_on <= parent.starts_on]
    total = max(0, sum(due.amount_pence for due in through) - ledger.credit_pence)
    unpaid = [
        OwedRound(
            gameweek_id=str(due.gameweek_id),
            starts_on=rounds[due.gameweek_id].starts_on,
            number=rounds[due.gameweek_id].number,
            season_week=labels.get(due.gameweek_id),
            amount_pence=due.amount_pence - paid,
        )
        for due, paid in allocate(ledger.credit_pence, through)
        if due.amount_pence > paid and due.gameweek_id in rounds
    ]
    return RoundFeeStatus(
        entry_fee_pence=league.entry_fee_pence,
        round_due_pence=max(owed.get(parent.id, 0), 0),
        owed_pence=total,
        owed_rounds=unpaid,
        earlier_balance_pence=max(0, total - sum(due.amount_pence for due in unpaid)),
        credit_pence=max(0, ledger.credit_pence - sum(due.amount_pence for due in dues)),
        adult_confirmed=member.adult_confirmed_at is not None,
        has_payment_link=league.payment_link_url is not None,
        payment_link_url=league.payment_link_url,
    )


async def weekly_forms(
    db: AsyncSession,
    player_id: uuid.UUID,
    leagues: dict[uuid.UUID, League],
    season: int,
    *,
    two_game_leagues: Collection[uuid.UUID],
    limit: int = 5,
) -> dict[uuid.UUID, list[WeeklyForm]]:
    """Aggregate one row per member/week BEFORE the bounded recent-form window."""
    weeks = member_weeks(
        list(leagues), season, two_game_leagues=two_game_leagues, player_id=player_id
    )
    rows = (await db.execute(select(recent_member_weeks(weeks, limit)))).mappings()
    output: dict[uuid.UUID, list[WeeklyForm]] = {}
    for row in rows:
        league = leagues[row["league_id"]]
        legacy_row = row["format"] == "legacy"
        output.setdefault(league.id, []).append(
            WeeklyForm(
                week_id=row["week_id"],
                week_label=row["week_label"],
                format=row["format"],
                game_kind="legacy" if legacy_row else "fantasy",
                destination=(
                    f"/leagues/{league.slug}/predictions?gw={row['week_id']}#coupon"
                    if legacy_row
                    else f"/leagues/{league.id}/weeks/{row['week_id']}/fantasy"
                ),
                status=row["status"],
                weekly_points=row["weekly_points"],
                slots_filled=row["slots_filled"],
            )
        )
    for forms in output.values():
        forms.sort(key=lambda row: (row.week_label, str(row.week_id)), reverse=True)
    return output
