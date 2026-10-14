"""Pay to pick: the organiser's ledger routes, and the member's 18+ confirmation. Batch 205.

ADR 0009. The money moves outside the app — members pay through the league's payment
link, or hand over cash — and these routes are how the organiser writes down what
arrived. Every write is a new, permanent ledger entry recorded with who made it; nothing
here edits or deletes one. A wrong entry is put right with an adjustment.

**Site admins only.** The fee and the link are already theirs alone (a league admin is
refused both), and so is the money: a league admin who could record cash could record
some for themselves. The routes take :data:`~src.auth.AdminUser`, like the console, rather
than a league-membership dependency, so oversight does not depend on having joined.

The one member route is the confirmation that they are 18 or over, which the round
payload waits for before it shows the payment link.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AdminUser, CurrentUser
from src.database import get_db
from src.deps import LeagueMemberWriteDep, get_league_or_404
from src.display_name import public_name
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind, PayerMapping
from src.models.profile import Profile
from src.rate_limit import limiter, per_user_key
from src.schemas import UtcDatetime
from src.services.dues import (
    league_balances,
    member_balance,
    normalise_payer_name,
    season_pot,
)
from src.services.football_provider import current_season
from src.services.season_calendar import season_label

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["payments"])

Db = Annotated[AsyncSession, Depends(get_db)]

#: The most one entry may move: £1,000. A guard against a mistyped amount, and what keeps
#: an entry inside the column's integer.
MAX_ENTRY_PENCE = 100_000

#: Refusal codes, so the admin screen can say what happened.
PAYMENT_ALREADY_ASSIGNED = "PAYMENT_ALREADY_ASSIGNED"
CASH_OUT_EXCEEDS_CREDIT = "CASH_OUT_EXCEEDS_CREDIT"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── Schemas ─────────────────────────────────────────────────────────────────────


class LedgerEntryOut(BaseModel):
    id: str
    kind: str
    amount_pence: int
    player_id: str | None
    gameweek_id: str | None
    note: str | None
    occurred_at: UtcDatetime
    created_at: UtcDatetime
    created_by: str | None


class MemberBalance(BaseModel):
    """One member's position: positive is credit, negative is owed."""

    player_id: str
    display_name: str
    #: Still an active member. A former member keeps their balance and stays listed.
    active: bool
    balance_pence: int
    owed_pence: int
    credit_pence: int
    adult_confirmed: bool


class QueuedPayment(BaseModel):
    """Money that arrived through the link from a payer nobody has matched yet."""

    id: str
    amount_pence: int
    payer_name: str | None
    occurred_at: UtcDatetime


class SeasonPot(BaseModel):
    season: int
    label: str
    #: The dues of the season's rounds that have been paid.
    pot_pence: int


class PaymentsOverview(BaseModel):
    entry_fee_pence: int | None
    payment_link_url: str | None
    balances: list[MemberBalance]
    queued_payments: list[QueuedPayment]
    season_pot: SeasonPot


class RecordCash(BaseModel):
    player_id: uuid.UUID
    amount_pence: int = Field(ge=1, le=MAX_ENTRY_PENCE)
    note: str | None = Field(default=None, max_length=500)


class RecordCashOut(BaseModel):
    """Credit repaid outside the app. The amount is what was repaid, as a positive number."""

    player_id: uuid.UUID
    amount_pence: int = Field(ge=1, le=MAX_ENTRY_PENCE)
    note: str | None = Field(default=None, max_length=500)


class RecordAdjustment(BaseModel):
    """A correction or an opening balance: positive credits the member, negative charges."""

    player_id: uuid.UUID
    amount_pence: int = Field(ge=-MAX_ENTRY_PENCE, le=MAX_ENTRY_PENCE)
    note: str = Field(min_length=3, max_length=500)

    @field_validator("amount_pence")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("an adjustment moves money; zero is not one")
        return value


class AssignPayment(BaseModel):
    player_id: uuid.UUID


class AssignedPayment(LedgerEntryOut):
    #: What the payer map now remembers this payer by: ``"monzo_user"``, ``"name"``, or
    #: ``None`` when the payment carried neither.
    remembered_by: str | None


class AdultConfirmation(BaseModel):
    adult_confirmed_at: UtcDatetime


def _entry_out(entry: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=str(entry.id),
        kind=LedgerKind(entry.kind).value,
        amount_pence=entry.amount_pence,
        player_id=str(entry.player_id) if entry.player_id else None,
        gameweek_id=str(entry.gameweek_id) if entry.gameweek_id else None,
        note=entry.note,
        occurred_at=entry.occurred_at,
        created_at=entry.created_at,
        created_by=str(entry.created_by) if entry.created_by else None,
    )


async def _require_member_row(db: AsyncSession, league: League, player_id: uuid.UUID) -> None:
    """Entries are for people who are, or were, members of this league — nobody else."""
    found = await db.scalar(
        select(LeagueMembership.id).where(
            LeagueMembership.league_id == league.id,
            LeagueMembership.player_id == player_id,
        )
    )
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")


async def _write(db: AsyncSession, entry: LedgerEntry) -> LedgerEntryOut:
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    log.info(
        "ledger entry recorded",
        league_id=str(entry.league_id),
        player_id=str(entry.player_id),
        kind=LedgerKind(entry.kind).value,
        amount_pence=entry.amount_pence,
        by=str(entry.created_by),
    )
    return _entry_out(entry)


# ── The organiser's routes ──────────────────────────────────────────────────────


@router.get("/{slug}/payments", response_model=PaymentsOverview)
@limiter.limit("60/minute", key_func=per_user_key)
async def payments_overview(
    request: Request,
    slug: str,
    admin: AdminUser,
    db: Db,
    season: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> PaymentsOverview:
    """Every member's balance, the payments waiting to be matched, and the season pot."""
    league = await get_league_or_404(slug, db)
    balances = await league_balances(db, league.id)

    members = (
        await db.execute(
            select(LeagueMembership, Profile)
            .join(Profile, Profile.id == LeagueMembership.player_id)
            .where(LeagueMembership.league_id == league.id)
        )
    ).all()
    listed: list[MemberBalance] = []
    for membership, profile in members:
        active = membership.deleted_at is None and profile.deleted_at is None and profile.is_active
        balance = balances.get(profile.id, 0)
        # A former member is listed only while something is still owed or held.
        if not active and balance == 0:
            continue
        listed.append(
            MemberBalance(
                player_id=str(profile.id),
                display_name=public_name(profile.display_name),
                active=active,
                balance_pence=balance,
                owed_pence=max(0, -balance),
                credit_pence=max(0, balance),
                adult_confirmed=membership.adult_confirmed_at is not None,
            )
        )
    listed.sort(key=lambda row: (not row.active, row.display_name.casefold()))

    queued = (
        (
            await db.execute(
                select(LedgerEntry)
                .where(
                    LedgerEntry.league_id == league.id,
                    LedgerEntry.player_id.is_(None),
                    LedgerEntry.kind == LedgerKind.payment,
                )
                .order_by(LedgerEntry.occurred_at)
            )
        )
        .scalars()
        .all()
    )
    wanted = current_season() if season is None else season
    return PaymentsOverview(
        entry_fee_pence=league.entry_fee_pence,
        payment_link_url=league.payment_link_url,
        balances=listed,
        queued_payments=[
            QueuedPayment(
                id=str(entry.id),
                amount_pence=entry.amount_pence,
                payer_name=entry.payer_name,
                occurred_at=entry.occurred_at,
            )
            for entry in queued
        ],
        season_pot=SeasonPot(
            season=wanted,
            label=season_label(wanted),
            pot_pence=await season_pot(db, league.id, wanted),
        ),
    )


@router.post(
    "/{slug}/payments/cash", response_model=LedgerEntryOut, status_code=status.HTTP_201_CREATED
)
@limiter.limit("120/hour", key_func=per_user_key)
async def record_cash(
    request: Request, slug: str, body: RecordCash, admin: AdminUser, db: Db
) -> LedgerEntryOut:
    """Cash handed to the organiser: a payment, recorded against the member who paid."""
    league = await get_league_or_404(slug, db)
    await _require_member_row(db, league, body.player_id)
    return await _write(
        db,
        LedgerEntry(
            league_id=league.id,
            player_id=body.player_id,
            kind=LedgerKind.payment,
            amount_pence=body.amount_pence,
            note=body.note,
            occurred_at=_now(),
            created_by=admin.id,
        ),
    )


@router.post(
    "/{slug}/payments/cash-outs",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("120/hour", key_func=per_user_key)
async def record_cash_out(
    request: Request, slug: str, body: RecordCashOut, admin: AdminUser, db: Db
) -> LedgerEntryOut:
    """Credit repaid outside the app. Never more than the member is owed back."""
    league = await get_league_or_404(slug, db)
    await _require_member_row(db, league, body.player_id)
    if body.amount_pence > max(0, await member_balance(db, league.id, body.player_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CASH_OUT_EXCEEDS_CREDIT)
    return await _write(
        db,
        LedgerEntry(
            league_id=league.id,
            player_id=body.player_id,
            kind=LedgerKind.cash_out,
            amount_pence=-body.amount_pence,
            note=body.note,
            occurred_at=_now(),
            created_by=admin.id,
        ),
    )


@router.post(
    "/{slug}/payments/adjustments",
    response_model=LedgerEntryOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("120/hour", key_func=per_user_key)
async def record_adjustment(
    request: Request, slug: str, body: RecordAdjustment, admin: AdminUser, db: Db
) -> LedgerEntryOut:
    """A correction or an opening balance, always with the reason written down."""
    league = await get_league_or_404(slug, db)
    await _require_member_row(db, league, body.player_id)
    return await _write(
        db,
        LedgerEntry(
            league_id=league.id,
            player_id=body.player_id,
            kind=LedgerKind.adjustment,
            amount_pence=body.amount_pence,
            note=body.note,
            occurred_at=_now(),
            created_by=admin.id,
        ),
    )


@router.post("/{slug}/payments/{entry_id}/assign", response_model=AssignedPayment)
@limiter.limit("120/hour", key_func=per_user_key)
async def assign_payment(
    request: Request,
    slug: str,
    entry_id: uuid.UUID,
    body: AssignPayment,
    admin: AdminUser,
    db: Db,
) -> AssignedPayment:
    """Say whose a queued payment was, and remember the payer for next time.

    The payer map keys an app payer by their stable user id and a card payer by their
    normalised name. Assigning again re-points the key, which is how a wrong match is
    corrected for the future; the payment already assigned is corrected with adjustments,
    because its member, once set, is never changed.
    """
    league = await get_league_or_404(slug, db)
    entry = (
        await db.execute(
            select(LedgerEntry)
            .where(
                LedgerEntry.id == entry_id,
                LedgerEntry.league_id == league.id,
                LedgerEntry.kind == LedgerKind.payment,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if entry.player_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PAYMENT_ALREADY_ASSIGNED)
    await _require_member_row(db, league, body.player_id)

    now = _now()
    entry.player_id = body.player_id
    entry.assigned_by = admin.id
    entry.assigned_at = now

    remembered_by: str | None = None
    key: dict[str, str] = {}
    if entry.payer_monzo_user_id:
        remembered_by, key = "monzo_user", {"monzo_user_id": entry.payer_monzo_user_id}
    elif entry.payer_name and normalise_payer_name(entry.payer_name):
        remembered_by = "name"
        key = {"normalised_name": normalise_payer_name(entry.payer_name)}
    if key:
        column = next(iter(key))
        await db.execute(
            insert(PayerMapping)
            .values(
                id=uuid.uuid4(),
                league_id=league.id,
                player_id=body.player_id,
                created_by=admin.id,
                **key,
            )
            .on_conflict_do_update(
                index_elements=["league_id", column],
                index_where=PayerMapping.__table__.c[column].is_not(None),
                set_={"player_id": body.player_id, "updated_at": now},
            )
        )
    await db.commit()
    await db.refresh(entry)
    log.info(
        "queued payment assigned",
        league_id=str(league.id),
        entry_id=str(entry.id),
        player_id=str(body.player_id),
        remembered_by=remembered_by,
        by=str(admin.id),
    )
    return AssignedPayment(**_entry_out(entry).model_dump(), remembered_by=remembered_by)


# ── The member's route ──────────────────────────────────────────────────────────


@router.post("/{slug}/adult-confirmation", response_model=AdultConfirmation)
@limiter.limit("30/hour", key_func=per_user_key)
async def confirm_adult(
    request: Request,
    slug: str,
    player: CurrentUser,
    league: LeagueMemberWriteDep,
    db: Db,
) -> AdultConfirmation:
    """The member confirms, once, that they are 18 or over.

    Unused since Batch 209: ADR 0009's amended fourth rule leaves members' ages to the
    owner, and the link no longer waits for this. Kept, with its column, so nothing is
    migrated away.

    Idempotent: confirming again keeps the first time. The write variant of the
    membership dependency, so only a member — not a site admin looking in — can confirm.
    """
    membership = (
        await db.execute(
            select(LeagueMembership)
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.player_id == player.id,
                LeagueMembership.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one()
    confirmed_at = membership.adult_confirmed_at
    if confirmed_at is None:
        confirmed_at = membership.adult_confirmed_at = _now()
        await db.commit()
        log.info("member confirmed they are an adult", league_id=str(league.id))
    return AdultConfirmation(adult_confirmed_at=confirmed_at)
