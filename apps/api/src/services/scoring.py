"""Scoring — settle picks against the provider's results and rank the leaderboard.

The rule: a winning pick scores ``round(odds_at_pick × 10)`` (long shots pay more), a
losing or void pick scores nothing. Season standing is the cumulative sum per member.

``resolve_pick`` and ``points_for`` are pure (no DB) so the maths and the
:class:`~src.services.odds_provider.EventSettlement` mapping are unit-tested directly;
``settle_gameweek`` and ``standings`` apply them over the database.

A pick resolves on ``(market, outcome)`` against its *fixture's* settlement. Until ADR
0002 it resolved on a Betfair market and selection id stored on the pick itself; those
columns are gone (revision ``005``) because ``(fixture, market, outcome)`` is already the
league's uniqueness key and is the same in every provider's vocabulary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekStatus
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick, PickMarket, PickOutcome, PickStatus
from src.models.profile import Profile
from src.services.coupon import combined_odds
from src.services.football_provider import current_season
from src.services.gameweek import season_bounds
from src.services.odds_provider import (
    EventSettlement,
    Market,
    OddsProvider,
    Outcome,
)

_POINTS_MULTIPLIER = 10


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def points_for(odds: Decimal) -> int:
    """Points a winning pick at ``odds`` scores: ``round(odds × 10)``.

    Rounds half **up** (``2.05`` → ``21``, not Python's banker's-rounding ``20``) so the
    reward is predictable for players.
    """
    return int((odds * _POINTS_MULTIPLIER).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class PickResolution(BaseModel):
    """The outcome of scoring one pick against its market's settlement."""

    status: PickStatus
    points: int


def resolve_pick(
    market: PickMarket,
    outcome: PickOutcome,
    odds: Decimal,
    settlement: EventSettlement,
) -> PickResolution | None:
    """Score a single pick against its fixture's settlement.

    Returns ``None`` — leave the pick pending — when the fixture has no result yet, or
    when it has one but *this* market does not. That distinction is what stops a
    half-settled fixture from voiding picks that are merely still waiting.

    Once the market has settled: ``won`` when the outcome won, ``lost`` when it did not,
    and ``void`` when the fixture was postponed or abandoned, or the outcome has vanished
    from a settled market (a withdrawn selection). A void pick scores nothing but is not
    counted as a loss.
    """
    if not settlement.settled:
        return None
    if settlement.void:
        return PickResolution(status=PickStatus.void, points=0)
    if Market(market.value) not in settlement.settled_markets:
        return None
    result = next(
        (
            o
            for o in settlement.outcomes
            if o.market == Market(market.value) and o.outcome == Outcome(outcome.value)
        ),
        None,
    )
    if result is None:
        return PickResolution(status=PickStatus.void, points=0)
    if result.won:
        return PickResolution(status=PickStatus.won, points=points_for(odds))
    return PickResolution(status=PickStatus.lost, points=0)


async def settle_gameweek(
    db: AsyncSession, gameweek: Gameweek, settlements: list[EventSettlement]
) -> int:
    """Apply event settlements to a round's pending picks; returns the count resolved.

    Idempotent and incremental: only pending picks whose fixture has a result are scored,
    so the scheduler can call this repeatedly as results land. Once no pending picks
    remain, the round flips to ``settled``. Does not commit — the caller owns the
    transaction.

    Since Batch 14 a round belongs to one league, so "no pending picks remain" means
    that league's picks. It used to mean *every* league's, which held one league's
    round open until an unrelated league had also finished settling.
    """
    by_event = {s.provider_event_id: s for s in settlements if s.settled}

    result = await db.execute(
        select(Pick, Fixture.provider_event_id)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.gameweek_id == gameweek.id,
            Pick.status == PickStatus.pending,
        )
    )
    resolved = 0
    for pick, provider_event_id in result.all():
        settlement = by_event.get(provider_event_id)
        if settlement is None:
            continue
        resolution = resolve_pick(pick.market, pick.outcome, pick.odds_at_pick, settlement)
        if resolution is None:
            continue
        pick.status = resolution.status
        pick.points_awarded = resolution.points
        resolved += 1

    remaining = await db.execute(
        select(func.count())
        .select_from(Pick)
        .where(Pick.gameweek_id == gameweek.id, Pick.status == PickStatus.pending)
    )
    if remaining.scalar_one() == 0 and gameweek.status != GameweekStatus.settled:
        gameweek.status = GameweekStatus.settled
        gameweek.settled_at = _now()

    await db.flush()
    return resolved


async def pending_event_ids(
    db: AsyncSession, gameweeks: Sequence[Gameweek]
) -> dict[uuid.UUID, list[str]]:
    """Distinct provider event ids per round, across each round's still-pending picks.

    These are the fixtures the settle job asks the provider to resolve; a fixture with no
    pending pick (already resolved, or never picked) is skipped, which keeps the request
    count proportional to what is actually outstanding. A round with nothing pending has
    no key.

    Answered for the whole run in one query rather than one per round, because the job
    settles every settleable round together — and because a fixture is one pooled row, two
    leagues holding the same match report the same ``provider_event_id`` here, which is
    what lets the caller ask for it once.
    """
    if not gameweeks:
        return {}
    result = await db.execute(
        select(Pick.gameweek_id, Fixture.provider_event_id)
        .join(Fixture, Fixture.id == Pick.fixture_id)
        .where(
            Pick.gameweek_id.in_([gameweek.id for gameweek in gameweeks]),
            Pick.status == PickStatus.pending,
        )
        .distinct()
    )
    by_gameweek: dict[uuid.UUID, list[str]] = {}
    for gameweek_id, provider_event_id in result.all():
        by_gameweek.setdefault(gameweek_id, []).append(provider_event_id)
    return by_gameweek


async def settle_gameweeks_via_provider(
    db: AsyncSession, provider: OddsProvider, gameweeks: Sequence[Gameweek]
) -> dict[uuid.UUID, int]:
    """Settle several rounds against a **single** shared read of the provider.

    Gather every round's outstanding fixtures, de-duplicate them across the whole run, ask
    the provider once, then fan the results back out per round via :func:`settle_gameweek`
    — which picks out the settlements its own picks reference and ignores the rest.

    The de-duplication is the point. Settlement costs one provider request per fixture, and
    it used to be driven a round at a time, so two leagues playing the same Saturday paid
    separately for every match they both held — against a plan allowing 100 requests an
    hour. Five leagues on one window could approach 75 requests in a run, mostly
    duplicates, and the symptom of running out is not an error but picks staying
    ``pending`` for good. The bill is now the number of *distinct* fixtures outstanding
    rather than the number of leagues holding them, which is the rule
    :func:`~src.services.gameweek.discover_fixtures` already applies to slate windows.

    Returns the count resolved per gameweek id; a round with nothing pending is absent.
    Flushes but does not commit — the job owns the transaction.
    """
    by_gameweek = await pending_event_ids(db, gameweeks)
    event_ids = list(dict.fromkeys(eid for ids in by_gameweek.values() for eid in ids))
    if not event_ids:
        return {}
    settlements = await provider.settle(event_ids)
    return {
        gameweek.id: await settle_gameweek(db, gameweek, settlements)
        for gameweek in gameweeks
        if gameweek.id in by_gameweek
    }


async def settle_gameweek_via_provider(
    db: AsyncSession, provider: OddsProvider, gameweek: Gameweek
) -> int:
    """Read one round's results from the provider and settle its pending picks.

    :func:`settle_gameweeks_via_provider` over a single round, for the callers that
    genuinely hold one — the scheduler passes its whole run at once so the shared fixtures
    are only paid for once. Returns the count resolved (0 when nothing is pending).
    """
    return (await settle_gameweeks_via_provider(db, provider, [gameweek])).get(gameweek.id, 0)


#: Where a pick stops being the obvious one, in decimal odds.
#:
#: A line has to be somewhere, and 3.00 is chosen against the scoring rule rather than by
#: taste: a winner scores ``round(odds × 10)``, so one hit at 3.00 outscores two at evens.
#: It also sits clear of the 1.50-2.50 band most match-odds favourites occupy, so the split
#: separates members rather than putting almost everyone on one side of it.
LONGSHOT_ODDS = Decimal("3.00")


#: How many settled rounds a form run covers. Five is the football convention every
#: other form line in this product already uses, so the two read the same way.
RECENT_FORM_ROUNDS = 5


def resolve_season(season: int | None) -> int:
    """The season a standings read covers: the one asked for, or the one being played.

    ``None`` means "now" rather than "all time", and that is the whole of Batch 96: every
    caller that had no opinion about seasons — the leaderboard, the profile, the
    cross-league summary, the scheduler's log line — was reading a table unbounded by
    date, which is what made a league that has run for three years read as one
    never-ending season.
    """
    return current_season() if season is None else season


def _season_round_ids(season: int) -> Select[tuple[uuid.UUID]]:
    """The rounds belonging to ``season``, as a subquery to filter picks against.

    A subquery rather than a join to ``gameweeks``, because the boundary has to sit in
    the **join** to ``picks`` beside ``exclude_gameweek_ids`` and not in a ``WHERE``. The
    reason is the same one written out under that parameter: a member whose only pick is
    outside this season is still a member of this season's league, on nought. Expressed as
    a ``WHERE`` the boundary would not zero them, it would delete them from the table.

    The range comes from :func:`~src.services.gameweek.season_bounds` — the definition
    round numbering already uses — so a round cannot be in one season for its number and
    another for the leaderboard.
    """
    first_day, last_day = season_bounds(season)
    return select(Gameweek.id).where(
        Gameweek.starts_on >= first_day,
        Gameweek.starts_on <= last_day,
    )


class FormRound(BaseModel):
    """One settled round in a member's recent run (Batch 80).

    ``status`` is the pick's, so it is ``won``, ``lost`` or **``void``** — never ``draw``.
    A coupon pick has no drawn state: a void fixture never ran, which is a different
    thing from a bet that ran and lost, and it is the same distinction ``picks_played``
    and ``picks_priced`` exist to keep further up this file.

    ``points`` is what the round scored, zero for anything that did not win. It is
    carried per round rather than left to the pips because points here are
    ``round(odds × 10)``: one win at 5.00 outscores two at 2.00, so a run of letters
    understates a member who takes long prices and overstates one who does not.
    """

    gameweek_id: str
    starts_on: date
    status: str
    points: int


class Standing(BaseModel):
    """One row of a leaderboard's season table.

    **The single ranking rule in the codebase.** :func:`standings_by_league` is read by
    the leaderboard, by ``routers/players.py``'s profile and by ``routers/me.py``'s
    cross-league summary, deliberately, so the three can never disagree — which is why
    Batch 70 added its figures here once rather than to each surface.

    Everything below ``rank`` is Batch 70 and **every one of them is optional with a
    default**. Vercel deploys the web app from ``main`` on merge while the API waits for
    ``/ship-prod``, so a required field would break the leaderboard for everyone in the
    gap: the trap Batches 38, 41 and 48 each recorded.

    **Two denominators, and the difference is real.** ``picks_played`` counts won, lost
    *and* void, because a member who claimed a fixture that was then postponed did take
    part in that round. The odds figures count only ``picks_priced`` — won and lost — for
    the opposite reason: a void pick never ran, so folding its price into a cumulative
    total credits a member for a bet that was never struck. A leaderboard showing both
    denominators without saying so is lying quietly, so the UI says so.
    """

    player_id: str
    display_name: str
    total_points: int
    #: Won, lost **and** void — every round this member took part in.
    picks_played: int
    picks_won: int
    rank: int
    #: Won and lost only: the picks that actually ran, and the denominator for every odds
    #: figure below. Zero for a member whose only picks were voided.
    picks_priced: int = 0
    #: The sum of the prices this member took, over ``picks_priced``. A *sum*, not a
    #: product: an accumulator's product over a season is a number nobody can read.
    cumulative_odds: float = 0.0
    #: ``cumulative_odds / picks_priced``, or ``None`` before anything has run.
    average_odds: float | None = None
    #: Total points over ``picks_played``. The figure that separates two members on the
    #: same total: the same points from fewer rounds is the better record.
    points_per_pick: float | None = None
    #: The best single return, in points. ``None`` until something has settled.
    best_return: int | None = None
    #: Wins over ``picks_played``, as a whole percentage. Computed here rather than by
    #: each surface, which is how the profile and the summary used to disagree by a
    #: rounding step.
    win_rate_pct: int | None = None
    #: How the priced picks split around :data:`LONGSHOT_ODDS`. The number that actually
    #: answers "what kind of picks is this person making".
    longshot_picks: int = 0
    favourite_picks: int = 0
    #: The line the split is drawn at, carried on the row so the screen labels it from
    #: the value it was computed with rather than from a constant of its own.
    longshot_odds: float = float(LONGSHOT_ODDS)
    #: The last :data:`RECENT_FORM_ROUNDS` settled rounds, **most recent first** — the
    #: order every form payload in this product is sent in, reversed by the screen that
    #: draws it. Empty unless the caller asked for it; see ``with_form``.
    recent_form: list[FormRound] = []


def _rank_rows(
    rows: Sequence[Any], form: dict[uuid.UUID, list[FormRound]] | None = None
) -> list[Standing]:
    """Order one league's aggregated rows and assign competition ranks."""
    ranked = sorted(
        rows,
        key=lambda r: (-int(r.total_points), -int(r.picks_won), r.display_name.lower()),
    )
    standings_out: list[Standing] = []
    for row in ranked:
        total = int(row.total_points)
        played = int(row.picks_played)
        priced = int(row.picks_priced)
        cumulative = float(row.cumulative_odds or 0)
        longshots = int(row.longshot_picks)
        # Competition ranking: everyone with a strictly higher total is above you.
        rank = sum(1 for r in ranked if int(r.total_points) > total) + 1
        standings_out.append(
            Standing(
                player_id=str(row.player_id),
                display_name=row.display_name,
                total_points=total,
                picks_played=played,
                picks_won=int(row.picks_won),
                rank=rank,
                picks_priced=priced,
                cumulative_odds=round(cumulative, 2),
                average_odds=round(cumulative / priced, 2) if priced else None,
                points_per_pick=round(total / played, 2) if played else None,
                best_return=int(row.best_return) if row.best_return is not None else None,
                win_rate_pct=round(100 * int(row.picks_won) / played) if played else None,
                longshot_picks=longshots,
                favourite_picks=priced - longshots,
                recent_form=(form or {}).get(row.player_id, []),
            )
        )
    return standings_out


async def recent_form_by_league(
    db: AsyncSession,
    league_ids: Sequence[uuid.UUID],
    limit: int = RECENT_FORM_ROUNDS,
    *,
    season: int | None = None,
) -> dict[tuple[uuid.UUID, uuid.UUID], list[FormRound]]:
    """Each member's last ``limit`` settled rounds in ``season``, keyed by ``(league, player)``.

    One query for every league and every member in them. The slice is a window function
    rather than a Python truncation of the whole season: a leaderboard's cost must not
    grow with how long the league has been running, and it is the same shape the current
    round and the last result are already selected with.

    Ordered most recent first, which is how every form payload in this product is sent
    and the opposite of how a form line is drawn — the screen reverses it, so that the
    nth pip is the nth row of any panel opened underneath.

    **The run stops at the season boundary** (Batch 96). Form sits on a row of a season
    table, so a run that reached back past the boundary would be describing rounds the
    total beside it does not count — and on the second weekend of a season it would fill
    four of its five pips from last year, which is the opposite of what a form line is
    for. Unlike the aggregate, the boundary is a plain ``WHERE`` here and that asymmetry
    is deliberate: this returns runs, not rows, so a member with nothing inside the season
    is simply absent and :func:`_rank_rows` gives them the empty run it gives anyone.
    """
    if not league_ids:
        return {}

    first_day, last_day = season_bounds(resolve_season(season))

    ranked = (
        select(
            Pick.league_id,
            Pick.player_id,
            Gameweek.id.label("gameweek_id"),
            Gameweek.starts_on,
            Pick.status,
            Pick.points_awarded,
            func.row_number()
            .over(
                partition_by=(Pick.league_id, Pick.player_id),
                order_by=(Gameweek.starts_on.desc(), Gameweek.id.desc()),
            )
            .label("rn"),
        )
        .join(Gameweek, Gameweek.id == Pick.gameweek_id)
        .where(
            Pick.league_id.in_(league_ids),
            Gameweek.status == GameweekStatus.settled,
            Gameweek.starts_on >= first_day,
            Gameweek.starts_on <= last_day,
            Pick.status.in_((PickStatus.won, PickStatus.lost, PickStatus.void)),
        )
        .subquery()
    )
    rows = (await db.execute(select(ranked).where(ranked.c.rn <= limit))).all()

    form: dict[tuple[uuid.UUID, uuid.UUID], list[FormRound]] = {}
    for row in sorted(rows, key=lambda r: r.rn):
        form.setdefault((row.league_id, row.player_id), []).append(
            FormRound(
                gameweek_id=str(row.gameweek_id),
                starts_on=row.starts_on,
                status=row.status.value,
                # A void round scored nothing because it never ran, and a lost one because
                # it lost. Both are zero here; the status is what tells them apart.
                points=int(row.points_awarded or 0),
            )
        )
    return form


async def standings_by_league(
    db: AsyncSession,
    league_ids: Sequence[uuid.UUID],
    exclude_gameweek_ids: Sequence[uuid.UUID] | None = None,
    *,
    with_form: bool = True,
    season: int | None = None,
) -> dict[uuid.UUID, list[Standing]]:
    """Season tables for several leagues at once, keyed by league id.

    One query for the whole set rather than one per league, so a caller holding a
    member's leagues — the cross-league summary — costs the same number of round trips
    whether they are in one league or six. A league with no active members has no key.

    The per-league table is exactly what :func:`standings` returns, because that is
    now this function over a single id: there is one ranking rule in the codebase and
    the leaderboard, the profile and the summary all read it. That holds *given the same*
    ``with_form`` — the ranking is identical either way and only the run of recent results
    is conditional.

    ``exclude_gameweek_ids`` runs the same aggregate with those rounds left out, which is
    how Batch 79 says "you moved up two": the table as it stood *before* the round being
    reported, differenced against the table now. It is a parameter rather than a second
    function, and rather than a stored snapshot, precisely so that the one ranking rule
    keeps applying — a movement computed by different arithmetic to the rank it is
    attached to is a number that can disagree with the leaderboard the member then opens.

    The exclusion belongs to the **join**, not to a ``WHERE``: a member whose only pick
    is in the excluded round still has a row in the table before it, worth zero.

    ``with_form`` costs one more query and is **on** by default (Batch 81): every table
    this returns is drawn somewhere, with exactly one exception. ``routers/me.py`` calls
    this a second time with ``exclude_gameweek_ids`` to rewind the table and difference the
    two ranks, and that rewound table is never rendered — it passes ``with_form=False``.
    Batch 80 had the default the other way round, which made every screen the exception
    and the one throwaway call the norm.

    ``season`` is the boundary that makes the name on this function true (Batch 96).
    ``None`` is the season being played now, not every season there has ever been, so a
    caller with no opinion gets the live table and a league in its fourth year no longer
    reads as one table four years long. Any other season is the archive: the same ranking
    rule, over the rounds that season contained, which is why a past table is a parameter
    here rather than a stored snapshot or a second query somewhere else.

    Like the exclusion, the boundary belongs to the **join** — see :func:`_season_round_ids`
    for what a ``WHERE`` would have done to a member who did not play this season. The two
    compose: ``routers/me.py`` rewinds the table by passing both, and it must, because a
    movement differenced from a table filtered differently to the one it is drawn beside
    is the exact disagreement this parameter is shaped to prevent.
    """
    if not league_ids:
        return {}

    season = resolve_season(season)

    settled = Pick.status.in_((PickStatus.won, PickStatus.lost, PickStatus.void))
    # The odds figures count only what actually ran. A void pick is a round the member
    # took part in — so it stays in ``picks_played`` — and a bet that was never struck,
    # so its price is not theirs to be credited with.
    priced = Pick.status.in_((PickStatus.won, PickStatus.lost))
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            LeagueMembership.league_id,
            LeagueMembership.player_id,
            display_name.label("display_name"),
            func.coalesce(func.sum(Pick.points_awarded), 0).label("total_points"),
            func.count(Pick.id).label("picks_played"),
            func.coalesce(func.sum(case((Pick.status == PickStatus.won, 1), else_=0)), 0).label(
                "picks_won"
            ),
            func.coalesce(func.sum(case((priced, 1), else_=0)), 0).label("picks_priced"),
            func.coalesce(func.sum(case((priced, Pick.odds_at_pick), else_=0)), 0).label(
                "cumulative_odds"
            ),
            func.max(Pick.points_awarded).label("best_return"),
            func.coalesce(
                func.sum(
                    case(
                        ((priced) & (Pick.odds_at_pick >= LONGSHOT_ODDS), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("longshot_picks"),
        )
        .select_from(LeagueMembership)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .outerjoin(
            Pick,
            (Pick.player_id == LeagueMembership.player_id)
            & (Pick.league_id == LeagueMembership.league_id)
            & settled
            & Pick.gameweek_id.in_(_season_round_ids(season))
            & (Pick.gameweek_id.notin_(exclude_gameweek_ids) if exclude_gameweek_ids else true()),
        )
        .where(
            LeagueMembership.league_id.in_(league_ids),
            LeagueMembership.deleted_at.is_(None),
        )
        .group_by(LeagueMembership.league_id, LeagueMembership.player_id, display_name)
    )

    grouped: dict[uuid.UUID, list[Any]] = {}
    for row in rows.all():
        grouped.setdefault(row.league_id, []).append(row)

    form = await recent_form_by_league(db, league_ids, season=season) if with_form else {}
    return {
        league_id: _rank_rows(
            league_rows,
            {player_id: run for (lid, player_id), run in form.items() if lid == league_id},
        )
        for league_id, league_rows in grouped.items()
    }


async def standings(
    db: AsyncSession, league_id: uuid.UUID, *, season: int | None = None
) -> list[Standing]:
    """Season leaderboard for a league: cumulative points per active member, ranked.

    Every current member gets a row (0 until they score). Members tied on total share a
    rank; display order breaks ties by wins then name. ``season`` defaults to the one
    being played; pass a past one to read it out of the archive.

    Carries ``recent_form`` (Batch 80). This is the single-league read, and both of its
    callers — the leaderboard and the player profile — are screens where a season total
    alone cannot separate a member who has won the last four rounds from one who has
    scored nothing since July.
    """
    return (await standings_by_league(db, [league_id], season=season)).get(league_id, [])


class GameweekResult(BaseModel):
    """One settled round's headline outcome — who won it and how the coupon landed."""

    gameweek_id: str
    starts_on: date
    winner_names: list[str]
    winner_points: int
    leg_count: int
    combined_odds: float
    all_won: bool | None
    #: How many legs actually landed. Batch 79: ``all_won`` could only say *every* leg or
    #: *not every* leg, so five of six and none of six read identically. Optional with a
    #: default because the web app deploys ahead of the API.
    picks_won: int = 0


async def gameweek_results(db: AsyncSession, league_id: uuid.UUID) -> list[GameweekResult]:
    """Every settled round for a league, newest first — the results list.

    The winner is whoever's pick scored the most that round; a tie names every player
    who shares the top score rather than picking one arbitrarily. ``all_won`` and
    ``combined_odds`` mirror :func:`src.services.coupon.build_coupon`'s coupon-outcome
    maths, computed here over every settled round in one query rather than one per row.
    A settled round with no picks in this league (vacuously settled) still gets a row,
    with no winner and an empty coupon.
    """
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            Gameweek.id,
            Gameweek.starts_on,
            display_name.label("display_name"),
            Pick.points_awarded,
            Pick.status,
            Pick.odds_at_pick,
        )
        .select_from(Gameweek)
        .outerjoin(Pick, (Pick.gameweek_id == Gameweek.id) & (Pick.league_id == league_id))
        .outerjoin(
            LeagueMembership,
            (LeagueMembership.player_id == Pick.player_id)
            & (LeagueMembership.league_id == league_id),
        )
        .outerjoin(Profile, Profile.id == Pick.player_id)
        .where(Gameweek.league_id == league_id, Gameweek.status == GameweekStatus.settled)
        .order_by(Gameweek.starts_on.desc())
    )

    by_gameweek: dict[uuid.UUID, tuple[date, list[tuple[str, int, PickStatus, Decimal]]]] = {}
    for gw_id, starts_on, name, points, status_, odds in rows.all():
        _, picks = by_gameweek.setdefault(gw_id, (starts_on, []))
        if points is not None:
            picks.append((name, int(points), status_, odds))

    results: list[GameweekResult] = []
    for gw_id, (starts_on, picks) in by_gameweek.items():
        top_points = max((p for _, p, _, _ in picks), default=0)
        winner_names = sorted({name for name, p, _, _ in picks if p == top_points})
        results.append(
            GameweekResult(
                gameweek_id=str(gw_id),
                starts_on=starts_on,
                winner_names=winner_names,
                winner_points=top_points,
                leg_count=len(picks),
                combined_odds=float(combined_odds([odds for _, _, _, odds in picks])),
                all_won=all(status_ == PickStatus.won for _, _, status_, _ in picks)
                if picks
                else None,
                picks_won=sum(1 for _, _, status_, _ in picks if status_ == PickStatus.won),
            )
        )
    results.sort(key=lambda r: r.starts_on, reverse=True)
    return results
