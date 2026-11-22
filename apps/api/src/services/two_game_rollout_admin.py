"""Owner-approved activation and suspension of the two-game format, one league at a time.

Batch 231. Until this module nothing could write a ``two_game_rollouts`` row or set its
``suspended`` flag except SQL by hand, so the activation checkpoint had no audited action
to approve. Three operations, each a single transaction the caller commits — or rolls back,
which is how a preview runs the exact same checks and writes nothing:

* :func:`activate_rollout` writes the league's one rollout row for an untouched future
  Saturday. **Untouched** is checked, not assumed: no two-game state for the league, and
  every legacy round from the cut-over onwards still scheduled, unopened and with no pick,
  ledger entry, completion or notice. Discovery writes a legacy round two weeks ahead, so an
  otherwise untouched Saturday usually already holds one; with
  ``retire_untouched_legacy`` those rounds are deleted in the same transaction, which is the
  same rule :func:`~src.services.gameweek.retire_stranded_rounds` applies to rounds a league
  no longer plays. Anything touched refuses the whole action and changes nothing.
* :func:`suspend_rollout` stops new entries and future openings. Billing, settlement,
  corrections and history continue: the weekly £1 is owed regardless (owner, 11 Nov).
* :func:`resume_rollout` lifts it, but only with an explicit confirmation of the
  reconciliation it reports first: which games open now, which locked while suspended (a
  locked game is never reopened) and whether weekly billing has a gap.

**The first week's opening.** The rule opens a first week at the previous Saturday noon,
like every consecutive week, and activation must normally come before it. Owner decision,
22 Nov 2026: when that instant has already passed — 28 Nov's was 21 Nov — the first week
may open at activation instead, provided no member was ever shown anything about that
two-game week (the league must hold no two-game state at all). ``open_at_activation``
records that decision; the rollout's ``effective_opening`` and the audit row carry the
activation instant. The games themselves keep the rule's stored opening: migration 032's
fence accepts only a preceding Saturday noon there, and nothing can enter a game that does
not exist yet, so entry starts when the calendar builds the week straight after activation.
No member-facing screen shows an opening that has already passed. Every other rule stands.

Audit rows reuse ``league_updated`` against ``two_game_rollouts`` (as hand settlement does
against ``gameweeks``) so this needs no migration; ``target_id`` is the league, so the row
appears in that league's own log.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.gameweek_completion import GameweekCompletion
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry
from src.models.notification import (
    ActionType,
    ActorType,
    AuditLog,
    MemberNotification,
    NotificationSend,
)
from src.models.pick import Pick
from src.models.profile import Profile, UserRole
from src.models.two_game import (
    ConfirmedBreak,
    MembershipInterval,
    TwoGame,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.services.two_game_schedule import fantasy_opening, game_schedule
from src.services.two_game_storage import london_utc
from src.services.weekly_fees import billing_bounds, billing_label

AUDIT_TABLE = "two_game_rollouts"
#: The owner decision that lets a first week open at activation once its rule opening passed.
OPEN_AT_ACTIVATION_DECISION = "owner 2026-11-22: first week opens at activation"
#: How far before the first Saturday a legacy round still belongs to the cut-over. The same
#: reach as the database fence (``first_week - 5``) and ``legacy_date_blocked``.
CUTOVER_REACH = timedelta(days=5)


class RolloutRefused(Exception):
    """A refused operation. Nothing was written; ``details`` says exactly why."""

    def __init__(self, status: int, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


@dataclass(frozen=True)
class LegacyRound:
    """One legacy round inside the cut-over reach, with everything that would touch it."""

    gameweek_id: uuid.UUID
    number: int | None
    starts_on: date
    status: str
    picks_open_at_utc: datetime | None
    locks_at_utc: datetime
    fixtures: int
    picks: int
    ledger_entries: int
    completions: int
    notices: int
    sends: int

    def touched(self, now: datetime) -> list[str]:
        reasons = []
        if self.status != GameweekStatus.scheduled.value:
            reasons.append(f"status {self.status}")
        if self.picks_open_at_utc is None:
            reasons.append("claimable since discovery (no announced opening)")
        elif self.picks_open_at_utc <= now:
            reasons.append("its opening has passed")
        for count, label in (
            (self.picks, "picks"),
            (self.ledger_entries, "ledger entries"),
            (self.completions, "completions"),
            (self.notices, "notices"),
            (self.sends, "push sends"),
        ):
            if count:
                reasons.append(f"{count} {label}")
        return reasons

    def as_json(self) -> dict[str, Any]:
        return {
            "gameweek_id": str(self.gameweek_id),
            "number": self.number,
            "starts_on": self.starts_on.isoformat(),
            "status": self.status,
            "picks_open_at_utc": _iso(self.picks_open_at_utc),
            "locks_at_utc": self.locks_at_utc.isoformat(),
            "fixtures": self.fixtures,
        }


@dataclass(frozen=True)
class Activation:
    league_id: uuid.UUID
    league_slug: str
    first_week: date
    rule_opening: datetime
    effective_opening: datetime
    opened_at_activation: bool
    retired: tuple[LegacyRound, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "league_id": str(self.league_id),
            "league_slug": self.league_slug,
            "first_week": self.first_week.isoformat(),
            "rule_opening": self.rule_opening.isoformat(),
            "effective_opening": self.effective_opening.isoformat(),
            "opened_at_activation": self.opened_at_activation,
            "retired_rounds": [round_.as_json() for round_ in self.retired],
        }


@dataclass(frozen=True)
class GameState:
    game_id: uuid.UUID
    week_label: date
    kind: str
    status: str
    opens_at: datetime
    locks_at: datetime

    def as_json(self) -> dict[str, Any]:
        return {
            "game_id": str(self.game_id),
            "week_label": self.week_label.isoformat(),
            "kind": self.kind,
            "status": self.status,
            "opens_at": self.opens_at.isoformat(),
            "locks_at": self.locks_at.isoformat(),
        }


@dataclass(frozen=True)
class Reconciliation:
    """What resuming would do, computed before anything changes."""

    league_id: uuid.UUID
    league_slug: str
    suspended: bool
    opens_on_resume: tuple[GameState, ...]
    locked_while_suspended: tuple[GameState, ...]
    billing_gaps: dict[str, list[str]] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "league_id": str(self.league_id),
            "league_slug": self.league_slug,
            "suspended": self.suspended,
            "opens_on_resume": [game.as_json() for game in self.opens_on_resume],
            "locked_while_suspended": [game.as_json() for game in self.locked_while_suspended],
            "billing_gaps": self.billing_gaps,
        }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _audit(actor: Profile, league: League, changes: dict[str, Any]) -> AuditLog:
    return AuditLog(
        actor_id=actor.id,
        actor_type=ActorType.admin,
        action_type=ActionType.league_updated,
        target_table=AUDIT_TABLE,
        target_id=league.id,
        changes={"league_slug": league.slug, "scope": "site", **changes},
    )


async def _site_admin(db: AsyncSession, actor_id: uuid.UUID) -> Profile:
    actor = await db.get(Profile, actor_id)
    if (
        actor is None
        or actor.deleted_at is not None
        or not actor.is_active
        or actor.role != UserRole.admin
    ):
        raise RolloutRefused(403, "NOT_SITE_ADMIN", "Only an active site admin can do this")
    return actor


async def _league(db: AsyncSession, league_id: uuid.UUID) -> League:
    # The same advisory key as parent creation, entries, billing and roster changes, so
    # none of them interleaves with a rollout write for this league.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 220))"),
        {"key": str(league_id)},
    )
    league = await db.get(League, league_id, with_for_update=True, populate_existing=True)
    if league is None or league.deleted_at is not None:
        raise RolloutRefused(404, "NOT_FOUND", "No such league")
    return league


async def _rollout(db: AsyncSession, league_id: uuid.UUID) -> TwoGameRollout:
    rollout = await db.get(TwoGameRollout, league_id, with_for_update=True, populate_existing=True)
    if rollout is None or not rollout.enabled:
        raise RolloutRefused(409, "NOT_ACTIVATED", "This league has no active two-game rollout")
    return rollout


def _require_switch() -> None:
    from src.config import settings

    if not settings.two_games_enabled:
        raise RolloutRefused(
            409, "FORMAT_DISABLED", "TWO_GAMES_ENABLED is off on this service; nothing can start"
        )


async def _count(db: AsyncSession, *clauses: Any) -> int:
    return int(await db.scalar(select(func.count()).where(*clauses)) or 0)


async def legacy_rounds_from(
    db: AsyncSession, league_id: uuid.UUID, first_week: date, *, lock: bool = False
) -> list[LegacyRound]:
    """Every legacy round of this league the cut-over to ``first_week`` would reach."""
    statement = (
        select(Gameweek)
        .where(
            Gameweek.league_id == league_id,
            Gameweek.format == "legacy",
            Gameweek.starts_on >= first_week - CUTOVER_REACH,
        )
        .order_by(Gameweek.starts_on, Gameweek.id)
    )
    if lock:
        statement = statement.with_for_update()
    weeks = list(await db.scalars(statement))
    rounds = []
    for week in weeks:
        key = str(week.id)

        async def count(*clauses: Any) -> int:
            return await _count(db, *clauses)

        rounds.append(
            LegacyRound(
                gameweek_id=week.id,
                number=week.number,
                starts_on=week.starts_on,
                status=GameweekStatus(week.status).value,
                picks_open_at_utc=week.picks_open_at_utc,
                locks_at_utc=week.locks_at_utc,
                fixtures=await count(GameweekFixture.gameweek_id == week.id),
                picks=await count(Pick.gameweek_id == week.id),
                ledger_entries=await count(LedgerEntry.gameweek_id == week.id),
                completions=await count(GameweekCompletion.gameweek_id == week.id),
                notices=await count(
                    MemberNotification.league_id == league_id,
                    MemberNotification.url.contains(key),
                ),
                sends=await count(NotificationSend.subject == key),
            )
        )
    return rounds


async def _two_game_state(db: AsyncSession, league_id: uuid.UUID) -> dict[str, int]:
    return {
        "two_game_weeks": await _count(
            db, Gameweek.league_id == league_id, Gameweek.format == "two_game"
        ),
        "games": await _count(db, TwoGame.league_id == league_id),
        "weekly_obligations": await _count(db, WeeklyFeeObligation.league_id == league_id),
        "breaks": await _count(db, ConfirmedBreak.league_id == league_id),
    }


async def activate_rollout(
    db: AsyncSession,
    *,
    league_id: uuid.UUID,
    first_week: date,
    actor_id: uuid.UUID,
    now: datetime,
    retire_untouched_legacy: bool = False,
    open_at_activation: bool = False,
) -> Activation:
    """Write the league's rollout row for an untouched future Saturday. Caller commits.

    Refuses — and writes nothing — when the switch is off, the league already has a
    rollout or any two-game state, the Saturday's fantasy lock has passed, a legacy round
    in reach is touched, an untouched one is present without ``retire_untouched_legacy``,
    or the first week's rule opening has passed without ``open_at_activation``.
    """
    _require_switch()
    actor = await _site_admin(db, actor_id)
    if first_week.weekday() != 5:
        raise RolloutRefused(422, "NOT_A_SATURDAY", "The first week must be a Saturday label")
    league = await _league(db, league_id)
    if await db.get(TwoGameRollout, league_id, with_for_update=True) is not None:
        raise RolloutRefused(
            409,
            "ALREADY_ACTIVATED",
            "This league already has a rollout row; a second activation is a separate decision",
        )
    state = await _two_game_state(db, league_id)
    if any(state.values()):
        raise RolloutRefused(
            409, "TWO_GAME_STATE_PRESENT", "This league already holds two-game state", **state
        )
    fantasy_lock = london_utc(first_week, 12)
    if now >= fantasy_lock:
        raise RolloutRefused(
            409,
            "TOO_LATE",
            "The first week's fantasy lock has passed",
            fantasy_lock=fantasy_lock.isoformat(),
        )

    rounds = await legacy_rounds_from(db, league_id, first_week, lock=True)
    touched = {str(round_.gameweek_id): round_.touched(now) for round_ in rounds}
    touched = {key: reasons for key, reasons in touched.items() if reasons}
    if touched:
        raise RolloutRefused(
            409,
            "LEGACY_WEEK_TOUCHED",
            "A legacy round in the cut-over has opened or been used; choose a later Saturday",
            rounds=[round_.as_json() for round_ in rounds],
            touched=touched,
        )
    if rounds and not retire_untouched_legacy:
        raise RolloutRefused(
            409,
            "LEGACY_WEEK_PRESENT",
            "Untouched legacy rounds are on the board from the cut-over; retiring them must be"
            " requested explicitly",
            rounds=[round_.as_json() for round_ in rounds],
        )

    rule_opening = fantasy_opening(first_week, set())
    if rule_opening > now:
        effective_opening, opened_at_activation = rule_opening, False
    elif open_at_activation:
        effective_opening, opened_at_activation = now, True
    else:
        raise RolloutRefused(
            409,
            "OPENING_PASSED",
            "The first week's rule opening has passed; opening at activation needs the owner's"
            " decision",
            rule_opening=rule_opening.isoformat(),
        )

    for round_ in rounds:
        # Zero picks, completions and ledger rows were checked under the row lock above, so
        # the cascade can only take this round's fixture links with it.
        await db.execute(
            delete(GameweekFixture).where(GameweekFixture.gameweek_id == round_.gameweek_id)
        )
        await db.execute(delete(Gameweek).where(Gameweek.id == round_.gameweek_id))
    db.add(
        TwoGameRollout(
            league_id=league_id,
            first_week=first_week,
            effective_opening=effective_opening,
            enabled=True,
            suspended=False,
        )
    )
    activation = Activation(
        league_id=league_id,
        league_slug=league.slug,
        first_week=first_week,
        rule_opening=rule_opening,
        effective_opening=effective_opening,
        opened_at_activation=opened_at_activation,
        retired=tuple(rounds),
    )
    db.add(
        _audit(
            actor,
            league,
            {
                "operation": "two_game_activated",
                **{
                    key: value
                    for key, value in activation.as_json().items()
                    if key != "league_slug"
                },
                **({"owner_decision": OPEN_AT_ACTIVATION_DECISION} if opened_at_activation else {}),
            },
        )
    )
    await db.flush()
    return activation


async def suspend_rollout(
    db: AsyncSession, *, league_id: uuid.UUID, actor_id: uuid.UUID, now: datetime, reason: str
) -> TwoGameRollout:
    """Stop new entries and openings for one league. Billing and settlement continue."""
    reason = reason.strip()
    if not reason:
        raise RolloutRefused(422, "REASON_REQUIRED", "Say why the league is being suspended")
    actor = await _site_admin(db, actor_id)
    league = await _league(db, league_id)
    rollout = await _rollout(db, league_id)
    if rollout.suspended:
        raise RolloutRefused(409, "ALREADY_SUSPENDED", "This league is already suspended")
    rollout.suspended = True
    db.add(
        _audit(
            actor,
            league,
            {
                "operation": "two_game_suspended",
                "reason": reason[:500],
                "at": now.isoformat(),
                "first_week": rollout.first_week.isoformat(),
            },
        )
    )
    await db.flush()
    return rollout


async def _games(db: AsyncSession, league_id: uuid.UUID) -> list[tuple[TwoGame, date]]:
    rows = await db.execute(
        select(TwoGame, Gameweek.starts_on)
        .join(Gameweek, Gameweek.id == TwoGame.week_id)
        .where(TwoGame.league_id == league_id)
        .order_by(Gameweek.starts_on, TwoGame.kind)
    )
    return [(game, label) for game, label in rows.tuples()]


def _state(game: TwoGame, label: date) -> GameState:
    return GameState(game.id, label, game.kind, game.status, game.opens_at, game.locks_at)


async def _billing_gaps(
    db: AsyncSession, league: League, rollout: TwoGameRollout, now: datetime
) -> dict[str, list[str]]:
    """Weeks an active member should already owe but has no obligation for.

    Duplicates cannot exist (one row per member and week label is a database constraint),
    so a gap is the only billing fault to reconcile. Each recorded membership interval owes
    every week it intersects from the first week through the current one.
    """
    through = billing_label(now)
    owed: dict[uuid.UUID, set[date]] = defaultdict(set)
    intervals = await db.scalars(
        select(MembershipInterval)
        .join(
            LeagueMembership,
            (LeagueMembership.league_id == MembershipInterval.league_id)
            & (LeagueMembership.player_id == MembershipInterval.player_id),
        )
        .where(MembershipInterval.league_id == league.id, LeagueMembership.deleted_at.is_(None))
    )
    for interval in intervals:
        label = max(rollout.first_week, billing_label(interval.joined_at))
        while label <= through:
            start, end = billing_bounds(label)
            if interval.joined_at < end and (interval.left_at is None or interval.left_at > start):
                owed[interval.player_id].add(label)
            label += timedelta(days=7)
    recorded: dict[uuid.UUID, set[date]] = defaultdict(set)
    for player_id, label in (
        await db.execute(
            select(WeeklyFeeObligation.player_id, WeeklyFeeObligation.week_label).where(
                WeeklyFeeObligation.league_id == league.id
            )
        )
    ).tuples():
        recorded[player_id].add(label)
    gaps = {
        str(player): sorted(day.isoformat() for day in labels - recorded[player])
        for player, labels in owed.items()
        if labels - recorded[player]
    }
    return gaps


async def reconciliation(db: AsyncSession, league_id: uuid.UUID, now: datetime) -> Reconciliation:
    """What :func:`resume_rollout` would do. Read-only."""
    league = await db.get(League, league_id)
    rollout = await db.get(TwoGameRollout, league_id)
    if league is None or league.deleted_at is not None or rollout is None or not rollout.enabled:
        raise RolloutRefused(409, "NOT_ACTIVATED", "This league has no active two-game rollout")
    games = await _games(db, league_id)
    opens = tuple(
        _state(game, label)
        for game, label in games
        if game.status not in ("settled", "cancelled") and game.opens_at <= now < game.locks_at
    )
    locked = tuple(
        _state(game, label)
        for game, label in games
        if game.status != "cancelled" and game.locks_at <= now and game.status != "settled"
    )
    return Reconciliation(
        league_id=league.id,
        league_slug=league.slug,
        suspended=rollout.suspended,
        opens_on_resume=opens,
        locked_while_suspended=locked,
        billing_gaps=await _billing_gaps(db, league, rollout, now),
    )


async def resume_rollout(
    db: AsyncSession,
    *,
    league_id: uuid.UUID,
    actor_id: uuid.UUID,
    now: datetime,
    confirm_reconciliation: bool,
) -> Reconciliation:
    """Lift a suspension after the owner has seen and confirmed its reconciliation.

    A game whose lock passed while suspended stays locked: the lifecycle never reopens one,
    and nothing here changes a stored instant. A billing gap refuses the resume outright —
    the weekly fee kept accruing while suspended, so a gap is a fault to fix first.
    """
    actor = await _site_admin(db, actor_id)
    league = await _league(db, league_id)
    rollout = await _rollout(db, league_id)
    if not rollout.suspended:
        raise RolloutRefused(409, "NOT_SUSPENDED", "This league is not suspended")
    report = await reconciliation(db, league_id, now)
    if report.billing_gaps:
        raise RolloutRefused(
            409,
            "BILLING_GAPS",
            "Weekly billing has gaps; reconcile them before resuming",
            reconciliation=report.as_json(),
        )
    if not confirm_reconciliation:
        raise RolloutRefused(
            409,
            "CONFIRMATION_REQUIRED",
            "Review the reconciliation, then resume with confirmation",
            reconciliation=report.as_json(),
        )
    rollout.suspended = False
    db.add(
        _audit(
            actor,
            league,
            {
                "operation": "two_game_resumed",
                "at": now.isoformat(),
                "reconciliation": report.as_json(),
            },
        )
    )
    await db.flush()
    return report


async def rollout_status(db: AsyncSession, league_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    """A read-only summary for operators: the row, its games and its obligations."""
    league = await db.get(League, league_id)
    if league is None:
        raise RolloutRefused(404, "NOT_FOUND", "No such league")
    rollout = await db.get(TwoGameRollout, league_id)
    games = await _games(db, league_id)
    obligations = (
        await db.execute(
            select(WeeklyFeeObligation.week_label, func.count())
            .where(WeeklyFeeObligation.league_id == league_id)
            .group_by(WeeklyFeeObligation.week_label)
            .order_by(WeeklyFeeObligation.week_label)
        )
    ).tuples()
    return {
        "league_id": str(league.id),
        "league_slug": league.slug,
        "rollout": None
        if rollout is None
        else {
            "first_week": rollout.first_week.isoformat(),
            "effective_opening": rollout.effective_opening.isoformat(),
            "enabled": rollout.enabled,
            "suspended": rollout.suspended,
        },
        "games": [_state(game, label).as_json() for game, label in games],
        "obligations": {label.isoformat(): count for label, count in obligations},
        "legacy_in_reach": None
        if rollout is None
        else [
            round_.as_json()
            for round_ in await legacy_rounds_from(db, league_id, rollout.first_week)
        ],
        "first_week_schedule": None
        if rollout is None
        else {
            kind: [
                value.isoformat()
                for value in game_schedule(kind, rollout.first_week, league, set(), now)
            ]
            for kind in ("group", "fantasy")
        },
    }
