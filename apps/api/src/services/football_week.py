"""One scoring round per league per football week, as one rule (Batch 184).

Batch 121 put the rule at settlement: in a league's Wednesday-to-Tuesday week an
*undeclared* round — off the league's weekday and not a declared calendar extra — is
refused once it has company, and so is the league's own round once an undeclared sibling
has settled. That guard is right about scoring, but nothing that *offers* a round knew it.
Discovery still created a round the sweep would refuse every evening for ever, the pick
path still took picks on it, and those picks sat pending indefinitely (CORR-20).

So the rule lives here, read-only, and is asked in three places:

* :func:`settle_refusal` — the guard's verdict, without its operational log line, so
  ``scoring._same_week_round_may_settle`` logs it and the pick path can ask it on every
  submission without paging anybody;
* :func:`new_round_refusal` — the same question about a round that does not exist yet, so
  ``sync_slate`` declines to create one the guard would strand or refuse;
* the operator's void path in ``routers/admin.py``, which may only void what the guard
  refuses.

It sits beside the season calendar rather than in ``services/scoring.py`` because
``services/gameweek.py`` needs it and ``scoring`` already depends on ``gameweek``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.services.season_calendar import canonical_saturday, extra_weeks_between

#: An undeclared round that shares its football week with another round.
UNDECLARED_SAME_WEEK_ROUND = "undeclared_same_week_round"
#: The league's own round, after an undeclared sibling in its week has already settled.
UNDECLARED_SIBLING_ALREADY_SETTLED = "undeclared_sibling_already_settled"
#: A new round beside a kept stray: the stray would stop being the week's only round and
#: the guard would refuse it, stranding the picks that kept it.
WOULD_STRAND_KEPT_ROUND = "would_strand_kept_round"


def football_week(day: date) -> tuple[date, date]:
    """The Wednesday and the Tuesday that bound ``day``'s football week, inclusive."""
    saturday = canonical_saturday(day)
    return saturday - timedelta(days=3), saturday + timedelta(days=3)


@dataclass(frozen=True)
class SettleRefusal:
    """Why the settle guard refuses a round, and the rows it compared."""

    reason: str
    football_week_start: date
    competing_gameweek_ids: list[uuid.UUID]
    intentional_gameweek_ids: list[uuid.UUID]


async def _rounds_in_week(db: AsyncSession, league_id: uuid.UUID, day: date) -> list[Gameweek]:
    week_start, week_end = football_week(day)
    rows = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.league_id == league_id,
            Gameweek.starts_on >= week_start,
            Gameweek.starts_on <= week_end,
        )
        .order_by(Gameweek.starts_on, Gameweek.id)
    )
    return list(rows.scalars().all())


def _intentional(starts_on: date, league: League, extra_dates: set[date]) -> bool:
    """On the league's own weekday, or a date the calendar declared for every league."""
    return starts_on.weekday() == league.slate_start_weekday or starts_on in extra_dates


async def settle_refusal(db: AsyncSession, gameweek: Gameweek) -> SettleRefusal | None:
    """Why Batch 121's guard refuses to settle this round, or ``None`` when it may settle.

    The rule is unchanged from the guard it was lifted out of. Declared calendar extras
    are intentional second rounds (Batch 113), so a cadence round plus declared extras
    settles; a lone off-cadence round settles too, because a later settings edit cannot
    retrospectively invalidate a week with no replacement. Only an undeclared round with
    company is refused — and the league's own round once an undeclared sibling has
    settled, because correcting awarded points is an explicit admin act, never something a
    routine sweep guesses.
    """
    same_week = await _rounds_in_week(db, gameweek.league_id, gameweek.starts_on)
    if len(same_week) <= 1:
        return None

    week_start, week_end = football_week(gameweek.starts_on)
    league = await db.get(League, gameweek.league_id)
    if league is None:  # pragma: no cover — the foreign key makes this unreachable
        return SettleRefusal("league_missing", week_start, [g.id for g in same_week], [])
    extra_dates = await extra_weeks_between(db, week_start, week_end)
    intentional = {
        candidate.id
        for candidate in same_week
        if _intentional(candidate.starts_on, league, extra_dates)
    }
    undeclared = [candidate for candidate in same_week if candidate.id not in intentional]
    if not undeclared:
        return None

    if gameweek.id not in intentional:
        reason = UNDECLARED_SAME_WEEK_ROUND
    elif any(candidate.status is GameweekStatus.settled for candidate in undeclared):
        reason = UNDECLARED_SIBLING_ALREADY_SETTLED
    else:
        return None
    return SettleRefusal(
        reason=reason,
        football_week_start=week_start,
        competing_gameweek_ids=[candidate.id for candidate in same_week],
        intentional_gameweek_ids=[
            candidate.id for candidate in same_week if candidate.id in intentional
        ],
    )


async def new_round_refusal(db: AsyncSession, league: League, starts_on: date) -> str | None:
    """Why creating this league's round on ``starts_on`` would break the rule, or ``None``.

    The guard's question asked before the row exists. A new round is refused when the
    week already holds a round and either side of the pair would be undeclared: a new
    undeclared round would itself never settle; beside an undeclared round that has
    settled, the new one would be refused as its sibling; and beside a kept stray — an
    undeclared round that survived retirement because it holds picks — the stray would
    lose its standing as the week's lone round and its picks would be stranded.

    A cadence round beside a declared extra, or an extra beside the cadence round, is
    exactly what Batch 113 declares and is never refused here, settled or not.
    """
    same_week = await _rounds_in_week(db, league.id, starts_on)
    if not same_week:
        return None
    week_start, week_end = football_week(starts_on)
    extra_dates = await extra_weeks_between(db, week_start, week_end)
    if not _intentional(starts_on, league, extra_dates):
        return UNDECLARED_SAME_WEEK_ROUND
    undeclared = [
        candidate
        for candidate in same_week
        if not _intentional(candidate.starts_on, league, extra_dates)
    ]
    if any(candidate.status is GameweekStatus.settled for candidate in undeclared):
        return UNDECLARED_SIBLING_ALREADY_SETTLED
    if undeclared:
        return WOULD_STRAND_KEPT_ROUND
    return None
