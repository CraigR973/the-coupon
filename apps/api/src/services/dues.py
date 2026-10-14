"""Weekly dues and the paid-up check: pay to pick. Batch 205, ADR 0009.

A league may charge an entry fee (``leagues.entry_fee_pence``). Every active member of
such a league owes one fee for every round, whether they pick or not, and must be paid
up — anything left over from earlier rounds, and the round in front of them — before the
API takes their pick. So a missed week rolls over: skip week 3 and week 4 costs two fees.
The money moves outside the app, through the league's payment link; the app keeps the
ledger (:class:`~src.models.ledger.LedgerEntry`) and reads it.

**When a due is recorded.** When the round opens, inside the step that already opens it,
so there is no new scheduled job: :func:`~src.services.gameweek.open_due_gameweeks` for a
round that announced its opening, and :func:`~src.services.gameweek.sync_slate` for one
discovered already open. A member who joins while a round is open owes it on joining
(:func:`charge_open_rounds_on_join`); rounds before they joined are never owed.

**Which rounds carry a due.** Dues start with the first round that opens after the fee is
set, and nothing stores when that was — nothing needs to. A due is only ever recorded at
an opening, so an open round carries a due exactly when its opening recorded some, and a
round still waiting to open will carry one if the league has a fee when it does. That is
:func:`round_fee`, and it is the one place the rule lives.

**The balance** is payments and adjustments, minus dues and cash-outs. Payments clear the
oldest dues first; whatever is left over is credit carried forward. The paid-up check
counts dues up to and including the round being picked, and no later: a league that
announces no opening has next week's round open beside this one, and a member picking
this week owes this week, not next.

A league without a fee never gets past the first line of any of this.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import DUE_KINDS, LedgerEntry, LedgerKind
from src.models.profile import Profile
from src.services.season_calendar import labels_for_gameweeks, season_bounds

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: The refusal ``submit_pick`` answers with when a member is not paid up. Its own code,
#: and a 402 — never a 401, which the web app treats as "signed out".
PAYMENT_REQUIRED = "PAYMENT_REQUIRED"

#: What a reversal says it was for, so the ledger reads as a story.
NOTE_ROUND_VOIDED = "round voided"
NOTE_ROUND_WITHDRAWN = "round withdrawn"
NOTE_LEFT_BEFORE_LOCK = "membership ended before the round locked"
NOTE_REJOINED = "rejoined while the round was open"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def format_pence(pence: int) -> str:
    """An amount as copy reads it: ``£1``, ``£2.50``."""
    pounds, remainder = divmod(abs(pence), 100)
    sign = "-" if pence < 0 else ""
    return f"{sign}£{pounds}" if remainder == 0 else f"{sign}£{pounds}.{remainder:02d}"


def normalise_payer_name(name: str) -> str:
    """A card payer's name as the payer map keys it.

    Card payers arrive with a fresh anonymous id on every payment, so their name is the
    only thing that recurs — and it arrives however the card issuer spelled it. Accents
    are folded, case is folded, punctuation becomes a space and runs of space collapse,
    so ``J. Smith`` and ``j smith`` are one payer.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", plain.casefold()).split())


# ── Recording dues ─────────────────────────────────────────────────────────────


async def active_member_ids(db: AsyncSession, league_id: uuid.UUID) -> list[uuid.UUID]:
    """Who owes a round when it opens: the league's active members.

    The same population ``round_progress`` counts — an undeleted membership of an active,
    undeleted profile — so the members who owe a round are the members it waits on.
    Ordered, so two writers lock dues in the same order.
    """
    rows = await db.execute(
        select(LeagueMembership.player_id)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
        )
        .order_by(LeagueMembership.player_id)
    )
    return list(rows.scalars().all())


async def _recorded_round_fee(db: AsyncSession, gameweek_id: uuid.UUID) -> int | None:
    """The fee this round's opening charged, or ``None`` when it charged nothing."""
    recorded = await db.scalar(
        select(func.max(-LedgerEntry.amount_pence)).where(
            LedgerEntry.gameweek_id == gameweek_id,
            LedgerEntry.kind == LedgerKind.round_due,
        )
    )
    return int(recorded) if recorded else None


async def round_fee(db: AsyncSession, league: League, gameweek: Gameweek) -> int | None:
    """What one member owes for this round, or ``None`` when it carries no due.

    Read from the ledger rather than from the league, because a round's due is fixed when
    it opens: the fee its opening recorded. A round still waiting to open will carry the
    league's fee when it does. An open round whose opening recorded nothing opened before
    the fee was set, and owes nothing — which is what "dues start with the first round
    that opens after the fee is set" means.
    """
    if league.entry_fee_pence is None:
        return None
    recorded = await _recorded_round_fee(db, gameweek.id)
    if recorded is not None:
        return recorded
    if gameweek.status is GameweekStatus.scheduled:
        return league.entry_fee_pence
    return None


async def _owed_for_round(db: AsyncSession, gameweek_id: uuid.UUID, player_id: uuid.UUID) -> int:
    """What this member still owes for this round: the fee, or nothing."""
    total = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_pence), 0)).where(
            LedgerEntry.gameweek_id == gameweek_id,
            LedgerEntry.player_id == player_id,
            LedgerEntry.kind.in_(DUE_KINDS),
        )
    )
    return -int(total or 0)


async def ensure_round_due(
    db: AsyncSession,
    *,
    league_id: uuid.UUID,
    gameweek_id: uuid.UUID,
    player_id: uuid.UUID,
    amount_pence: int,
) -> bool:
    """Make this member owe this round, once. Returns whether anything was written.

    The first time, that is the due itself, inserted against the partial unique index so
    that two writers — the opening and a member's pick, say — cannot both record it. A
    member whose due was reversed when they left, and who has rejoined while the round is
    still open, has the reversal undone by an opposite one; the due row is locked first,
    so two writers cannot both do that either.
    """
    inserted = await db.scalar(
        insert(LedgerEntry)
        .values(
            id=uuid.uuid4(),
            league_id=league_id,
            player_id=player_id,
            kind=LedgerKind.round_due,
            amount_pence=-amount_pence,
            gameweek_id=gameweek_id,
        )
        .on_conflict_do_nothing(
            index_elements=["gameweek_id", "player_id"],
            index_where=text("kind = 'round_due'"),
        )
        .returning(LedgerEntry.id)
    )
    if inserted is not None:
        return True

    due = (
        await db.execute(
            select(LedgerEntry)
            .where(
                LedgerEntry.gameweek_id == gameweek_id,
                LedgerEntry.player_id == player_id,
                LedgerEntry.kind == LedgerKind.round_due,
            )
            .with_for_update()
        )
    ).scalar_one()
    if await _owed_for_round(db, gameweek_id, player_id) > 0:
        return False
    db.add(
        LedgerEntry(
            league_id=league_id,
            player_id=player_id,
            kind=LedgerKind.due_reversal,
            amount_pence=due.amount_pence,
            gameweek_id=gameweek_id,
            note=NOTE_REJOINED,
        )
    )
    await db.flush()
    return True


async def record_round_dues(db: AsyncSession, league: League, gameweek: Gameweek) -> int:
    """The opening step's half of pay to pick: every active member owes the round.

    Idempotent — run it as often as the opening runs and each member owes the round once.
    The amount is the one already charged for this round if any member has been, so a fee
    edited between two runs cannot split a round in two. Flushes; the caller commits.
    """
    if league.entry_fee_pence is None or league.deleted_at is not None:
        return 0
    amount = await _recorded_round_fee(db, gameweek.id) or league.entry_fee_pence
    charged = 0
    for player_id in await active_member_ids(db, league.id):
        if await ensure_round_due(
            db,
            league_id=league.id,
            gameweek_id=gameweek.id,
            player_id=player_id,
            amount_pence=amount,
        ):
            charged += 1
    if charged:
        log.info(
            "round dues recorded",
            league_id=str(league.id),
            gameweek_id=str(gameweek.id),
            members=charged,
            amount_pence=amount,
        )
    return charged


async def record_dues_for_opened(db: AsyncSession, gameweeks: Sequence[Gameweek]) -> int:
    """:func:`record_round_dues` for every round an opening just moved."""
    if not gameweeks:
        return 0
    leagues = {
        league.id: league
        for league in (
            await db.execute(
                select(League).where(
                    League.id.in_({gameweek.league_id for gameweek in gameweeks}),
                    League.entry_fee_pence.is_not(None),
                    League.deleted_at.is_(None),
                )
            )
        ).scalars()
    }
    charged = 0
    for gameweek in gameweeks:
        league = leagues.get(gameweek.league_id)
        if league is not None:
            charged += await record_round_dues(db, league, gameweek)
    return charged


async def charge_open_rounds_on_join(
    db: AsyncSession,
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """A member joining while a round is open owes that round on joining.

    Only rounds that carry a due (:func:`round_fee`), are labelled ``open`` and have not
    locked. That includes a round whose opening a settings edit has since moved back
    into the future but which kept its label because it holds picks: it has opened, its
    opening charged its members, and nothing will open it again, so a newcomer owes it
    now like them. A round still labelled ``scheduled`` is left to its opening, which
    charges every active member — this one included — when it runs. Rounds before the
    member joined are never charged: nothing here looks backwards.
    """
    fee = await db.scalar(
        select(League.entry_fee_pence).where(League.id == league_id, League.deleted_at.is_(None))
    )
    if fee is None:
        return 0
    moment = now or _utc_now()
    charged_rounds = (
        await db.execute(
            select(Gameweek.id, func.max(-LedgerEntry.amount_pence))
            .join(LedgerEntry, LedgerEntry.gameweek_id == Gameweek.id)
            .where(
                Gameweek.league_id == league_id,
                Gameweek.status == GameweekStatus.open,
                Gameweek.locks_at_utc > moment,
                LedgerEntry.kind == LedgerKind.round_due,
            )
            .group_by(Gameweek.id)
        )
    ).all()
    charged = 0
    for gameweek_id, amount in charged_rounds:
        if await ensure_round_due(
            db,
            league_id=league_id,
            gameweek_id=gameweek_id,
            player_id=player_id,
            amount_pence=int(amount),
        ):
            charged += 1
    if charged:
        log.info(
            "joining member charged the open round",
            league_id=str(league_id),
            player_id=str(player_id),
            rounds=charged,
        )
    return charged


# ── Reversing dues ─────────────────────────────────────────────────────────────


async def reverse_round_dues(
    db: AsyncSession,
    gameweek_ids: Collection[uuid.UUID],
    *,
    note: str,
    actor_id: uuid.UUID | None = None,
) -> int:
    """Cancel every member's standing due on these rounds — a voided or withdrawn round.

    A reversing entry per member still owing, never a delete: the due stays as the record
    that it was charged. Returns how many were reversed. Flushes; the caller commits.
    """
    if not gameweek_ids:
        return 0
    ids = list(gameweek_ids)
    dues = (
        (
            await db.execute(
                select(LedgerEntry)
                .where(LedgerEntry.gameweek_id.in_(ids), LedgerEntry.kind == LedgerKind.round_due)
                .order_by(LedgerEntry.player_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if not dues:
        return 0
    standing = {
        (gameweek_id, player_id): -int(total)
        for gameweek_id, player_id, total in (
            await db.execute(
                select(
                    LedgerEntry.gameweek_id,
                    LedgerEntry.player_id,
                    func.sum(LedgerEntry.amount_pence),
                )
                .where(LedgerEntry.gameweek_id.in_(ids), LedgerEntry.kind.in_(DUE_KINDS))
                .group_by(LedgerEntry.gameweek_id, LedgerEntry.player_id)
            )
        ).all()
    }
    reversed_count = 0
    for due in dues:
        owed = standing.get((due.gameweek_id, due.player_id), 0)
        if owed <= 0:
            continue
        db.add(
            LedgerEntry(
                league_id=due.league_id,
                player_id=due.player_id,
                kind=LedgerKind.due_reversal,
                amount_pence=owed,
                gameweek_id=due.gameweek_id,
                created_by=actor_id,
                note=note,
            )
        )
        reversed_count += 1
    if reversed_count:
        await db.flush()
        log.info("round dues reversed", gameweeks=[str(i) for i in ids], dues=reversed_count)
    return reversed_count


async def reverse_unlocked_dues(
    db: AsyncSession,
    player_id: uuid.UUID,
    league_ids: Collection[uuid.UUID] | None,
    *,
    now: datetime,
    actor_id: uuid.UUID | None = None,
) -> int:
    """A member leaving before a round locks stops owing it.

    The same rounds :func:`~src.services.gameweek.release_unlocked_picks` frees the
    member's picks on — still pickable, deadline ahead — so the pick and the due go
    together. Locked rounds stay owed. ``league_ids`` narrows to the leagues being left;
    ``None`` is every league, for an account that is going altogether.
    """
    from src.services.gameweek import PICKABLE_STATES

    if league_ids is not None and not league_ids:
        return 0
    query = (
        select(LedgerEntry)
        .join(Gameweek, Gameweek.id == LedgerEntry.gameweek_id)
        .where(
            LedgerEntry.player_id == player_id,
            LedgerEntry.kind == LedgerKind.round_due,
            Gameweek.status.in_(PICKABLE_STATES),
            Gameweek.locks_at_utc > now,
        )
        .order_by(LedgerEntry.gameweek_id)
        .with_for_update(of=LedgerEntry)
    )
    if league_ids is not None:
        query = query.where(LedgerEntry.league_id.in_(list(league_ids)))
    dues = (await db.execute(query)).scalars().all()
    reversed_count = 0
    for due in dues:
        assert due.gameweek_id is not None  # the join above guarantees it
        owed = await _owed_for_round(db, due.gameweek_id, player_id)
        if owed <= 0:
            continue
        db.add(
            LedgerEntry(
                league_id=due.league_id,
                player_id=player_id,
                kind=LedgerKind.due_reversal,
                amount_pence=owed,
                gameweek_id=due.gameweek_id,
                created_by=actor_id,
                note=NOTE_LEFT_BEFORE_LOCK,
            )
        )
        reversed_count += 1
    if reversed_count:
        log.info(
            "departing member's open dues reversed",
            player_id=str(player_id),
            dues=reversed_count,
        )
    return reversed_count


# ── Reading balances ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoundDue:
    """What a member owes for one round, net of reversals. ``starts_on`` orders it."""

    gameweek_id: uuid.UUID | None
    starts_on: date | None
    amount_pence: int


def _due_order(due: RoundDue) -> tuple[int, date, str]:
    # A due whose round was withdrawn has no date; it is the oldest by definition.
    if due.starts_on is None:
        return (0, date.min, "")
    return (1, due.starts_on, str(due.gameweek_id))


def allocate(credit_pence: int, dues: Iterable[RoundDue]) -> list[tuple[RoundDue, int]]:
    """Clear the oldest dues first. Each due, oldest first, with how much of it is paid."""
    remaining = max(credit_pence, 0)
    paid: list[tuple[RoundDue, int]] = []
    for due in sorted(dues, key=_due_order):
        covered = min(remaining, due.amount_pence)
        remaining -= covered
        paid.append((due, covered))
    return paid


@dataclass
class MemberLedger:
    """One member's entries in one league, folded into what the arithmetic needs."""

    #: Payments and adjustments, minus cash-outs.
    credit_pence: int = 0
    #: What each round still owes, net of reversals; ``None`` keys a withdrawn round.
    owed_by_round: dict[uuid.UUID | None, int] = field(default_factory=dict)


async def _member_ledgers(
    db: AsyncSession, league_id: uuid.UUID, player_ids: Collection[uuid.UUID] | None = None
) -> dict[uuid.UUID, MemberLedger]:
    """Every assigned entry in the league, folded per member. One query."""
    query = select(
        LedgerEntry.player_id,
        LedgerEntry.kind,
        LedgerEntry.amount_pence,
        LedgerEntry.gameweek_id,
    ).where(LedgerEntry.league_id == league_id, LedgerEntry.player_id.is_not(None))
    if player_ids is not None:
        query = query.where(LedgerEntry.player_id.in_(list(player_ids)))
    ledgers: dict[uuid.UUID, MemberLedger] = defaultdict(MemberLedger)
    for player_id, kind, amount, gameweek_id in (await db.execute(query)).all():
        ledger = ledgers[player_id]
        if kind in DUE_KINDS:
            ledger.owed_by_round[gameweek_id] = ledger.owed_by_round.get(gameweek_id, 0) - amount
        else:
            ledger.credit_pence += amount
    return dict(ledgers)


async def _round_dates(
    db: AsyncSession, gameweek_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, Gameweek]:
    wanted = {gameweek_id for gameweek_id in gameweek_ids if gameweek_id is not None}
    if not wanted:
        return {}
    rows = await db.execute(select(Gameweek).where(Gameweek.id.in_(wanted)))
    return {gameweek.id: gameweek for gameweek in rows.scalars().all()}


def _dues_of(ledger: MemberLedger, rounds: dict[uuid.UUID, Gameweek]) -> list[RoundDue]:
    return [
        RoundDue(
            gameweek_id=gameweek_id,
            starts_on=rounds[gameweek_id].starts_on if gameweek_id in rounds else None,
            amount_pence=owed,
        )
        for gameweek_id, owed in ledger.owed_by_round.items()
        if owed > 0
    ]


@dataclass(frozen=True)
class FeeStanding:
    """A member's position on one round of a league that charges a fee."""

    #: What this round costs the member: its fee while it can be picked (nothing when it
    #: carries no due), then whatever their entries say — nothing, once it is voided.
    round_due_pence: int
    #: What they must pay to pick this round — anything outstanding from earlier rounds,
    #: plus this one. Zero means paid up.
    owed_pence: int
    #: The rounds behind ``owed_pence``, oldest first, each with its unpaid part.
    owed_rounds: list[RoundDue]
    #: What is left over once every due recorded so far is paid.
    credit_pence: int


async def fee_standings(
    db: AsyncSession, league: League, gameweek: Gameweek, player_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, FeeStanding]:
    """Each member's :class:`FeeStanding` on this round. Empty for a league without a fee.

    While the round can still be picked it counts at its fee whatever a member's own
    entries say, so a member is asked for it even in the hour before the opening job
    records it — the job then records it against them like everyone else. Once it has
    locked, what it costs a member is what their entries say, which for a voided round
    is nothing.
    """
    # Deferred, for the import cycle ``charge_open_rounds_on_join`` describes.
    from src.services.gameweek import PICKABLE_STATES

    if league.entry_fee_pence is None or not player_ids:
        return {}
    pickable = gameweek.status in PICKABLE_STATES
    this_round = await round_fee(db, league, gameweek) or 0
    ledgers = await _member_ledgers(db, league.id, player_ids)
    rounds = await _round_dates(
        db,
        [gameweek.id, *(gid for ledger in ledgers.values() for gid in ledger.owed_by_round)],
    )
    standings: dict[uuid.UUID, FeeStanding] = {}
    for player_id in player_ids:
        ledger = ledgers.get(player_id, MemberLedger())
        if pickable:
            ledger.owed_by_round[gameweek.id] = this_round
        due_here = max(ledger.owed_by_round.get(gameweek.id, 0), 0)
        dues = _dues_of(ledger, rounds)
        through = [
            due for due in dues if due.starts_on is None or due.starts_on <= gameweek.starts_on
        ]
        owed_through = sum(due.amount_pence for due in through)
        owed_rounds = [
            RoundDue(due.gameweek_id, due.starts_on, due.amount_pence - paid)
            for due, paid in allocate(ledger.credit_pence, through)
            if due.amount_pence > paid and due.gameweek_id is not None
        ]
        standings[player_id] = FeeStanding(
            round_due_pence=due_here,
            owed_pence=max(0, owed_through - ledger.credit_pence),
            owed_rounds=owed_rounds,
            credit_pence=max(0, ledger.credit_pence - sum(due.amount_pence for due in dues)),
        )
    return standings


async def payment_required(
    db: AsyncSession, league: League, gameweek: Gameweek, player_id: uuid.UUID
) -> bool:
    """The gate: whether this member must pay before picking on this round.

    False for a league without a fee before any query is made, which is what keeps every
    such league exactly as it was.
    """
    if league.entry_fee_pence is None:
        return False
    standing = (await fee_standings(db, league, gameweek, [player_id]))[player_id]
    return standing.owed_pence > 0


async def record_due_on_pick(
    db: AsyncSession, league: League, gameweek: Gameweek, player_id: uuid.UUID
) -> None:
    """Write down the due a pick was charged for, if the ledger does not have it yet.

    The gate counted this round at its fee. Usually the opening already recorded that;
    when it has not — the hour before the opening job runs, say — the pick records it, so
    nobody plays a round the ledger never charged them for. Picking, changing a pick and
    picking again after a postponement all land here and cost nothing extra.
    """
    if league.entry_fee_pence is None:
        return
    amount = await round_fee(db, league, gameweek)
    if amount is None:
        return
    await ensure_round_due(
        db,
        league_id=league.id,
        gameweek_id=gameweek.id,
        player_id=player_id,
        amount_pence=amount,
    )


async def owed_to_pick(
    db: AsyncSession, gameweek: Gameweek, player_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """What each of these members must pay to pick this round; only those who owe."""
    if not player_ids:
        return {}
    league = await db.get(League, gameweek.league_id)
    if league is None or league.entry_fee_pence is None:
        return {}
    return {
        player_id: standing.owed_pence
        for player_id, standing in (await fee_standings(db, league, gameweek, player_ids)).items()
        if standing.owed_pence > 0
    }


# ── What members and admins read ───────────────────────────────────────────────


class OwedRound(BaseModel):
    """One round a member has not fully paid for."""

    gameweek_id: str
    starts_on: date
    number: int | None
    #: The deployment-wide football week, as ``GameweekListEntry`` carries it.
    season_week: str | None = None
    amount_pence: int


class RoundFeeStatus(BaseModel):
    """The member's fee status, as the round payload carries it. Batch 205.

    Every member gets ``payment_link_url`` straight away: since ADR 0009's 13 Oct
    amendment (Batch 209) the owner, not the app, makes sure members are adults.
    ``adult_confirmed`` is kept for clients built against Batch 205 and decides nothing.
    """

    entry_fee_pence: int
    round_due_pence: int
    owed_pence: int
    owed_rounds: list[OwedRound]
    credit_pence: int
    adult_confirmed: bool
    has_payment_link: bool
    payment_link_url: str | None


async def round_fee_status(
    db: AsyncSession, league: League, gameweek: Gameweek, player_id: uuid.UUID
) -> RoundFeeStatus | None:
    """The caller's fee status on this round, or ``None`` — no fee, or not a member."""
    if league.entry_fee_pence is None:
        return None
    membership = (
        await db.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == player_id,
                LeagueMembership.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        return None
    standing = (await fee_standings(db, league, gameweek, [player_id]))[player_id]
    rounds = await _round_dates(db, [due.gameweek_id for due in standing.owed_rounds])
    labels = await labels_for_gameweeks(db, list(rounds.values()))
    return RoundFeeStatus(
        entry_fee_pence=league.entry_fee_pence,
        round_due_pence=standing.round_due_pence,
        owed_pence=standing.owed_pence,
        owed_rounds=[
            OwedRound(
                gameweek_id=str(due.gameweek_id),
                starts_on=rounds[due.gameweek_id].starts_on,
                number=rounds[due.gameweek_id].number,
                season_week=labels.get(due.gameweek_id),
                amount_pence=due.amount_pence,
            )
            for due in standing.owed_rounds
            if due.gameweek_id in rounds
        ],
        credit_pence=standing.credit_pence,
        adult_confirmed=membership.adult_confirmed_at is not None,
        has_payment_link=league.payment_link_url is not None,
        payment_link_url=league.payment_link_url,
    )


async def league_balances(db: AsyncSession, league_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Every member with an entry, and their balance: credit if positive, owed if not."""
    return {
        player_id: ledger.credit_pence - sum(max(owed, 0) for owed in ledger.owed_by_round.values())
        for player_id, ledger in (await _member_ledgers(db, league_id)).items()
    }


async def member_balance(db: AsyncSession, league_id: uuid.UUID, player_id: uuid.UUID) -> int:
    """One member's balance in one league, as :func:`league_balances` reads it."""
    ledger = (await _member_ledgers(db, league_id, [player_id])).get(player_id, MemberLedger())
    return ledger.credit_pence - sum(max(owed, 0) for owed in ledger.owed_by_round.values())


async def season_pot(db: AsyncSession, league_id: uuid.UUID, season: int) -> int:
    """The season's prize pot: the dues of that season's rounds that have been paid.

    The season is the standings' own (``season_bounds``), so the pot and the table always
    cover the same rounds. Each member's payments clear their oldest dues first, across
    seasons — arrears from last season are paid before this season's dues are — and the
    pot is the paid part of the dues whose round falls inside the season.
    """
    first_day, last_day = season_bounds(season)
    ledgers = await _member_ledgers(db, league_id)
    rounds = await _round_dates(
        db, [gid for ledger in ledgers.values() for gid in ledger.owed_by_round]
    )
    pot = 0
    for ledger in ledgers.values():
        for due, paid in allocate(ledger.credit_pence, _dues_of(ledger, rounds)):
            if due.starts_on is not None and first_day <= due.starts_on <= last_day:
                pot += paid
    return pot
