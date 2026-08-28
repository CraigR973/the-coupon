"""Pick submission — the weekly land-grab.

``POST /api/v1/leagues/{slug}/picks`` submits (or, before lock, changes) the caller's one
pick for the gameweek. The endpoint snapshots the odds itself, so the frozen price is
authoritative rather than client-supplied, and it enforces both game rules:

* the claim period — after the league's announced opening (``PICKS_NOT_OPEN``) and
  before the deadline (``PICKS_LOCKED``);
* one pick per member per round (a re-pick updates in place, freeing the old selection);
* no two members holding the same claim (first-come; a taken claim → 409).

How much a claim covers is the league's ``pick_scope``: one ``(fixture, market,
outcome)`` under the original ``selection`` rule, or the entire game under ``fixture``.
The refusal is ``SELECTION_TAKEN`` or ``FIXTURE_TAKEN`` accordingly.

The unique constraints on ``picks`` are the race backstop — a concurrent grab that slips
past the pre-check trips ``IntegrityError`` and is reported as a conflict.

Submitting also spends the odds provider's rate-limited quota, once per submission, so
the endpoint carries two limits rather than one: ``PICK_SUBMIT_LIMIT`` per member and
``PICK_SUBMIT_SHARED_LIMIT`` per league. A league that has spent its share is refused
with ``PICKS_BUSY`` (429) rather than served a price it could not confirm.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.config import settings
from src.database import get_db
from src.deps import LeagueMemberDep, OddsProviderDep
from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture
from src.models.league import League, PickScope
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome
from src.models.profile import Profile
from src.rate_limit import consume_shared_limit, limiter, per_user_key
from src.services.gameweek import PICKABLE_STATES, pick_refusal
from src.services.notification_triggers import notify_pick_made
from src.services.odds_provider import OddsProviderError, Selection

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["picks"])

Db = Annotated[AsyncSession, Depends(get_db)]

#: How often one member may submit or change a pick.
#:
#: This is a **provider budget**, not an abuse control, and it was set as though it were
#: the latter. Each submission freezes a price at `odds_cache_pick_ttl_seconds` (60s), so
#: re-picking the *same* fixture inside a minute is free but moving between fixtures costs
#: one upstream request each time — and deciding between fixtures is exactly what the hour
#: before lock is for.
#:
#: At the previous `60/hour` a single member could spend sixty requests against a plan
#: that, once `test_request_budget.py`'s peak browsing hour and the ad-hoc round allowance
#: are subtracted, has about twelve to spare. One member could exhaust the whole
#: allowance and the failure is silent: everyone else's prices stop refreshing.
#:
#: Ten is what one member can spend without being able to do that alone, and it is far
#: more than the journey needs — a member takes one pick and changes their mind a handful
#: of times. `test_request_budget.py` asserts it against the measured spare rather than
#: against this comment.
#:
#: What it cannot do on its own is bound the *total*, because a per-actor limit never
#: does: fifteen members at ten each is over the plan, and at `max_members`'s real
#: ceiling of fifty it is `500/hour` against a hundred. `PICK_SUBMIT_SHARED_LIMIT` below
#: is the other half — this one keeps a single member from taking the league's whole
#: share, that one keeps the league inside the provider's.
PICK_SUBMIT_LIMIT = "10/hour"

#: How much of the provider's hour and day one league's pick submissions may spend.
#:
#: The aggregate bound the per-member limit above cannot provide (Batch 89, closing
#: OPS-10 / CORR-03). Denominated in **submissions, not upstream requests**: freezing a
#: price costs at most one provider request — one event is one request — so bounding
#: submissions bounds the spend without having to know, at the moment of charging,
#: whether this particular fetch will be served from the 60-second cache. That direction
#: is the safe one; it can over-count a re-pick of the same fixture inside a minute, never
#: under-count what actually goes upstream.
#:
#: `50/hour` is what the hour leaves once the measured peak browsing hour is subtracted
#: (`test_request_budget.py`: 28 requests, and it does not grow with membership because
#: the slate cache collapses every reader into one sweep). It is also the number that
#: makes the finding's worst case survivable: a full fifty-member league gets one pick
#: each per hour instead of the `500/hour` the unbounded path allowed.
#:
#: `100/day` because an hourly cap alone permits twenty-four times its own number a day,
#: and the day is the tighter plan — the same lesson `PROVIDER_SLATE_FETCH_LIMIT` learned.
#: Two hours of full-tilt picking is more rounds than a league locks in a day.
#:
#: **Keyed per league**, which bounds a league and not the installation: with several
#: leagues picking in the same hour the global plan is the binding constraint again, and
#: the answer to that is the plan rather than a tighter bucket that would refuse members
#: of a league spending nothing. `test_request_budget.py` states that residual rather than
#: leaving it to be rediscovered.
PICK_SUBMIT_SHARED_LIMIT = "50/hour;100/day"

#: The bucket every pick submission in one league is charged to, whichever member asked.
PICK_SUBMIT_SHARED_SCOPE = "pick-submit-provider-budget"

#: What a member is told when the league's share of the provider budget is gone.
#:
#: A refusal, deliberately — not a queue and not a cached price. `_snapshot_selection`
#: says why a pick can never freeze a price it could not confirm: the frozen number is
#: what a winner is scored on, so a stale one is not a degraded pick but a wrong score.
#: And in a first-come land-grab the member has to be left in no doubt their claim did
#: not land, which a silent queue would not do (owner decision, 2026-08-27).
PICKS_BUSY = "PICKS_BUSY"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── Schemas ─────────────────────────────────────────────────────────────────────


class SubmitPickRequest(BaseModel):
    fixture_id: str
    market: PickMarket
    outcome: PickOutcome


class PickResponse(BaseModel):
    id: str
    league_id: str
    gameweek_id: str
    fixture_id: str
    home: str
    away: str
    competition: str
    market: str
    outcome: str
    runner_name: str
    odds: float
    status: str
    points_awarded: int | None


def _to_response(pick: Pick, fixture: Fixture) -> PickResponse:
    return PickResponse(
        id=str(pick.id),
        league_id=str(pick.league_id),
        gameweek_id=str(pick.gameweek_id),
        fixture_id=str(fixture.id),
        home=fixture.home,
        away=fixture.away,
        competition=fixture.competition,
        market=pick.market.value,
        outcome=pick.outcome.value,
        runner_name=pick.runner_name,
        odds=float(pick.odds_at_pick),
        status=pick.status.value,
        points_awarded=pick.points_awarded,
    )


# ── Submit / change a pick ────────────────────────────────────────────────────


@router.post("/{slug}/picks", response_model=PickResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(PICK_SUBMIT_LIMIT, key_func=per_user_key)
async def submit_pick(
    request: Request,
    slug: str,
    body: SubmitPickRequest,
    player: CurrentUser,
    league: LeagueMemberDep,
    provider: OddsProviderDep,
    db: Db,
) -> PickResponse:
    fixture = await _resolve_fixture(body.fixture_id, db)
    gameweek = await _round_playing(db, league, fixture)
    # Both ends of the claim period: ``PICKS_NOT_OPEN`` before the league's announced
    # opening (Batch 27), ``PICKS_LOCKED`` after the deadline.
    refusal = pick_refusal(gameweek, _now())
    if refusal is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)

    # The league may offer only a subset of the two markets. A market it does not offer
    # is refused here as well as hidden from the slate, so the rule holds even if a
    # client posts a fixture id and market straight past the pick screen.
    if body.market not in league.offered_markets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="MARKET_NOT_OFFERED"
        )

    # Charged here and not earlier: everything above is free, and a submission refused
    # for being locked or for a market the league does not offer has spent nothing, so
    # charging it would price the budget against members who never reached the provider.
    # Everything below *has* spent it — the claim pre-check and the commit come after the
    # fetch, so a submission that goes on to lose the race still cost its request. Batch
    # 57's lock-then-fetch ordering is untouched.
    if not consume_shared_limit(
        _league_budget_key(league), PICK_SUBMIT_SHARED_LIMIT, PICK_SUBMIT_SHARED_SCOPE
    ):
        log.warning(
            "pick refused: the league's share of the provider budget is spent",
            league_id=str(league.id),
            gameweek_id=str(gameweek.id),
            player_id=str(player.id),
        )
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=PICKS_BUSY)

    selection = await _snapshot_selection(provider, fixture, body.market, body.outcome)

    # And again, because the line above left the process. `_snapshot_selection` is an
    # outbound HTTP call to a third party on the request path, and the deadline it was
    # cleared against is the one the whole product turns on — a pick that lands at
    # 14:30:03 scores like any other. `pick_refusal` is authoritative on time rather than
    # on `status` (see its docstring), so asking it twice is cheap and needs no lock: the
    # second answer is simply the true one at the moment of writing.
    refusal = pick_refusal(gameweek, _now())
    if refusal is not None:
        log.info(
            "pick refused: lock passed while the price was being fetched",
            league_id=str(league.id),
            gameweek_id=str(gameweek.id),
            player_id=str(player.id),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)

    # Pre-check: has another member already claimed this? How much of the fixture a
    # claim covers is the league's choice — one selection, or the whole game.
    conflict_detail = await _claim_conflict(db, league, gameweek, fixture, body, player.id)
    if conflict_detail is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_detail)

    # One pick per member per gameweek: update in place if they already have one.
    existing = await db.execute(
        select(Pick).where(
            Pick.league_id == league.id,
            Pick.gameweek_id == gameweek.id,
            Pick.player_id == player.id,
        )
    )
    pick = existing.scalar_one_or_none()
    # Captured *before* `_apply_selection` overwrites the row. `submit_pick` updates in
    # place, so after that call there is nothing left to say whether this was a claim or a
    # move — and they are different events to everyone else in the league (Batch 76). A
    # move frees the old selection back into the grab, which is the more useful half.
    moved = pick is not None
    if pick is None:
        pick = Pick(league_id=league.id, gameweek_id=gameweek.id, player_id=player.id)
        db.add(pick)
    _apply_selection(pick, fixture, body, selection, league.pick_scope)

    try:
        await db.commit()
    except IntegrityError:
        # A concurrent grab won the claim (or the member's pick) between pre-check
        # and commit — the unique constraints are the source of truth.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_taken_detail(league))
    await db.refresh(pick)

    log.info(
        "pick submitted",
        league_id=str(league.id),
        gameweek_id=str(gameweek.id),
        player_id=str(player.id),
        selection=f"{body.market.value}:{body.outcome.value}",
    )

    # Serialised before the alert, not after. The block below rolls back on failure, and a
    # rollback expires every object in the session — so building the response afterwards
    # would re-read a committed row through an implicit lazy load, outside the transaction
    # that was just discarded. The response is the endpoint's contract; nothing about
    # announcing the pick may put it at risk.
    response = _to_response(pick, fixture)

    # Batch 76 — announce the grab. After the commit, deliberately: the pick is the thing
    # that must land, and a push that fails must not roll one back. Failures are swallowed
    # for the same reason, so a dead subscription cannot turn a successful claim into a
    # 500 the member reads as "it did not save".
    #
    # Sends are inline, matching `notify_member_joined`. Eleven webpush calls on the
    # submit path is a real latency cost and it is accepted rather than unnoticed —
    # moving delivery off the request is the delivery-layer change this batch is scoped
    # out of, and reach is 5 active subscriptions across 13 profiles today.
    try:
        await notify_pick_made(
            db,
            gameweek,
            picker_id=player.id,
            picker_name=await _league_display_name(db, league.id, player),
            league_name=league.name,
            selection=pick.runner_name,
            odds=pick.odds_at_pick,
            moved=moved,
        )
        await db.commit()
    except Exception:
        log.exception(
            "pick alert failed",
            league_id=str(league.id),
            gameweek_id=str(gameweek.id),
        )
        await db.rollback()

    return response


async def _league_display_name(db: AsyncSession, league_id: uuid.UUID, player: Profile) -> str:
    """What this league calls the picker — the override when set, else their profile name.

    The alert has to read the way the leaderboard does; a member who set an override in
    one league is that name to everybody in it.
    """
    override = (
        await db.execute(
            select(LeagueMembership.display_name_override).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.player_id == player.id,
                LeagueMembership.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return override or player.display_name


# ── Read: my pick for a gameweek ──────────────────────────────────────────────


@router.get("/{slug}/gameweeks/{gameweek_id}/pick", response_model=PickResponse | None)
async def my_pick(
    slug: str,
    gameweek_id: uuid.UUID,
    player: CurrentUser,
    league: LeagueMemberDep,
    db: Db,
) -> PickResponse | None:
    """The caller's pick for one round, or ``null``.

    ``gameweek_id`` is typed as a real ``UUID`` so FastAPI answers 422 for a malformed
    one. It used to be ``str``, which reached the query and raised inside the driver as an
    unhandled 500 — every other router in this codebase already types its ids this way.
    """
    result = await db.execute(
        select(Pick, Fixture)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.league_id == league.id,
            Pick.gameweek_id == gameweek_id,
            Pick.player_id == player.id,
        )
    )
    row = result.first()
    if row is None:
        return None
    pick, fixture = row
    return _to_response(pick, fixture)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _league_budget_key(league: League) -> str:
    """The bucket identity: the league, not the member and not the caller's address.

    The league is what the limit is *about* — fifty members submitting one pick each is
    the shape the provider plan cannot absorb, and every one of those requests carries a
    different user id and may carry a different IP. Keying on either of those is the gap
    this closes rather than the fix for it.
    """
    return f"league:{league.id}"


async def _resolve_fixture(fixture_id: str, db: AsyncSession) -> Fixture:
    """The fixture, or a 404 — never a 500.

    ``fixture_id`` arrives as a string on the request body and the column is a real
    ``UUID``, so handing it straight to ``db.get`` let a malformed value raise inside the
    driver and surface as an unhandled 500. A stale link or a client bug is a client
    error; spending a 500 on it trains you to ignore the alert that means something.

    The same shape as ``routers/players.py:83`` deliberately — that is where this
    codebase already decided what a malformed id means here.
    """
    try:
        target = uuid.UUID(fixture_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found"
        ) from None
    fixture = await db.get(Fixture, target)
    if fixture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")
    return fixture


async def _round_playing(db: AsyncSession, league: League, fixture: Fixture) -> Gameweek:
    """The round of *this league* that has this fixture on its card.

    Fixtures are pooled since Batch 14, so a fixture no longer names the round it
    belongs to — it can be on several leagues' cards at once. The round has to be
    found from the league and the fixture together.

    A fixture the league is not playing is a 404 rather than a lock error: as far as
    this league is concerned that match is not on the card at all. The pick uniqueness
    rules are keyed on the round, so picking through a fixture the league never
    selected would otherwise write a pick nothing could settle.

    A league can carry the same fixture on two rounds — a match that moves between
    windows stays on the round it was first discovered for, because ``sync_slate``
    unlinks only on an explicit void status and never on a fixture's mere absence.
    **Rounds that are not over win**, newest first: a pick can only ever land on
    one whose deadline is still ahead, so resolving to a locked one would refuse a
    submission the member could legitimately make. ``scheduled`` counts, so a member
    whose league announces an opening is told to come back rather than told the game
    they are looking at is finished.
    """
    result = await db.execute(
        select(Gameweek)
        .join(GameweekFixture, GameweekFixture.gameweek_id == Gameweek.id)
        .where(GameweekFixture.fixture_id == fixture.id, Gameweek.league_id == league.id)
        .order_by(
            Gameweek.status.in_(PICKABLE_STATES).desc(),
            Gameweek.starts_on.desc(),
        )
        .limit(1)
    )
    gameweek = result.scalar_one_or_none()
    if gameweek is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fixture is not on this league's slate"
        )
    return gameweek


async def _snapshot_selection(
    provider: OddsProviderDep,
    fixture: Fixture,
    market: PickMarket,
    outcome: PickOutcome,
) -> Selection:
    """Fetch the fixture's odds and return the chosen priced selection.

    Enforces the *only offer what the provider prices* rule: an outcome that isn't
    currently offered (unpriced or missing) is rejected rather than stored at a stale
    price. The price may come from the provider's short-lived cache — bounded by
    ``ODDS_CACHE_TTL_SECONDS`` — which is the trade the provider's rate limit forces.

    **This is the path that must not degrade.** Browsing the card falls back to the last
    known prices when the provider fails (Batch 48), because a stale price beats a broken
    screen. Here the price is frozen at this instant and a winner scores
    ``round(odds × 10)`` from it, so a stale or missing one is not a degraded pick, it is
    a wrong score. An unreachable provider refuses the submission — loudly, and as a
    ``503`` rather than an unhandled crash, so the client can say what happened.
    """
    # The one price that gets frozen onto a scored pick, so it buys freshness the
    # browse path cannot afford — but for a single fixture, which is one request.
    try:
        odds = await provider.fetch_odds(
            [fixture.provider_event_id], max_age_seconds=settings.odds_cache_pick_ttl_seconds
        )
    except OddsProviderError as exc:
        log.warning(
            "pick refused: odds unavailable",
            fixture=fixture.provider_event_id,
            error=repr(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ODDS_UNAVAILABLE"
        ) from exc
    for fixture_odds in odds:
        for selection in fixture_odds.selections:
            if selection.market.value == market.value and selection.outcome.value == outcome.value:
                return selection
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="SELECTION_NOT_AVAILABLE"
    )


def _taken_detail(league: League) -> str:
    """The conflict code for a claim this league's rule refuses."""
    return "FIXTURE_TAKEN" if league.pick_scope is PickScope.fixture else "SELECTION_TAKEN"


async def _claim_conflict(
    db: AsyncSession,
    league: League,
    gameweek: Gameweek,
    fixture: Fixture,
    body: SubmitPickRequest,
    player_id: uuid.UUID,
) -> str | None:
    """The conflict code if another member already holds this claim, else ``None``.

    Under ``selection`` scope only the exact ``(fixture, market, outcome)`` is
    contested. Under ``fixture`` scope any pick on the game blocks, which is the
    whole point of the rule. The caller's own pick never conflicts with itself —
    a re-pick to the same claim is a no-op update, not a grab.
    """
    conditions = [
        Pick.league_id == league.id,
        Pick.gameweek_id == gameweek.id,
        Pick.fixture_id == fixture.id,
    ]
    if league.pick_scope is PickScope.selection:
        conditions += [Pick.market == body.market, Pick.outcome == body.outcome]

    result = await db.execute(select(Pick.player_id).where(*conditions))
    holders = set(result.scalars().all())
    if holders - {player_id}:
        return _taken_detail(league)
    return None


def _apply_selection(
    pick: Pick,
    fixture: Fixture,
    body: SubmitPickRequest,
    selection: Selection,
    scope: PickScope,
) -> None:
    """Write the frozen snapshot onto a new or re-picked row.

    ``(fixture, market, outcome)`` is the whole identity of a pick — the same key the
    league's uniqueness constraint uses and the one settlement resolves against — so no
    provider identifier is stored alongside it.

    ``scope`` is copied from the league because the fixture-level unique index is
    partial on this column: a PostgreSQL index predicate cannot join to ``leagues``.
    """
    pick.fixture_id = fixture.id
    pick.market = body.market
    pick.outcome = body.outcome
    pick.runner_name = selection.runner_name
    pick.odds_at_pick = selection.price
    pick.pick_scope = scope
