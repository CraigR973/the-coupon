"""Persist a provider's slate as a league's round, drawing on the shared fixture pool.

Turns a :class:`~src.services.odds_provider.Slate` DTO into ``gameweeks`` / ``fixtures`` /
``gameweek_fixtures`` rows. Idempotent: syncing the same round twice updates the existing
rows rather than duplicating them, so the scheduler can refresh before lock.

**Per-league since Batch 14.** A round belongs to one league, and the window it covers —
which days, which kick-off times, how long before it opens picks lock — is that league's
configuration rather than a constant. Fixtures live in a pool shared by every league, so
two leagues playing the same match cost one row and one provider request.

All ``*_utc`` values are stored naive-UTC to match the rest of the schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture, GameweekStatus
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile
from src.services.football_provider import season_for
from src.services.odds_provider import (
    UK_TZ,
    OddsProvider,
    Slate,
    SlateFixture,
    SlateWindow,
    is_void_status,
)
from src.services.push_notification_service import send_notification

# Tier boundaries for how stale a browsed price may be (see slate_odds_max_age).
_NEAR_LOCK_SECONDS = 6 * 3600
_MID_LOCK_SECONDS = 24 * 3600


def _naive_utc(value: datetime) -> datetime:
    """Strip to naive UTC (the storage convention for every ``*_utc`` column)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_now() -> datetime:
    """Naive-UTC now, matching the ``*_utc`` storage convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def season_bounds(season: int) -> tuple[date, date]:
    """The first and last dates of a season, named by its starting year.

    The inverse of :func:`season_for`, and the reason it exists: numbering is per
    league *per season*, and the query that finds a league's highest number so far has
    to express "same season" as a date range the database can filter on.
    """
    return date(season, 7, 1), date(season + 1, 6, 30)


async def next_gameweek_number(db: AsyncSession, league_id: Any, starts_on: date) -> int:
    """The number a new round takes: one past this league's highest for that season.

    One past the **maximum** rather than one past the count, so a number is never
    reused. Deleting a round leaves a gap, which is correct — members were told about
    "Gameweek 7", and the next round must not become a second one.

    A round inserted mid-sequence therefore takes the next number rather than the
    position its date implies. That is deliberate and is the whole reason the number is
    stored: Batch 35 made a one-off round (Boxing Day, say) legitimate, and an ordinal
    derived from ``starts_on`` order would renumber every round after it the moment one
    appeared. A one-off is simply the next round the league plays, so it gets the next
    number, and history stays fixed.

    Rounds with no number — possible in a database restored from before Batch 41's
    backfill — are ignored by ``max``, so the sequence resumes from whatever *is*
    numbered rather than restarting at 1.
    """
    first_day, last_day = season_bounds(season_for(starts_on))
    result = await db.execute(
        select(func.max(Gameweek.number)).where(
            Gameweek.league_id == league_id,
            Gameweek.starts_on >= first_day,
            Gameweek.starts_on <= last_day,
        )
    )
    highest = result.scalar_one_or_none()
    return (highest or 0) + 1


def uk_today() -> date:
    """Today's date in UK local time.

    A round's ``starts_on`` is a UK calendar date, so "at or before today" has to be
    asked in the same timezone the date was written in — not in UTC, which is a day
    behind for the first hour of a BST morning.
    """
    return datetime.now(UK_TZ).date()


#: Rounds a member may still be able to claim on — the two states before the deadline.
PICKABLE_STATES = (GameweekStatus.scheduled, GameweekStatus.open)


def pick_refusal(gameweek: Gameweek, now: datetime) -> str | None:
    """Why this round refuses a pick right now, or ``None`` when it accepts one.

    ``now`` must be naive-UTC (as stored). Time is the authority in both directions and
    ``status`` is the label the scheduler keeps up with, exactly as it has been since
    Batch 4: an ``open`` round past its deadline is refused before the lock job runs,
    and a ``scheduled`` round whose opening has passed is accepted before the open job
    runs. Only ``locked`` and ``settled`` are decided by status alone, because those are
    reached by settlement rather than by a clock.

    ``PICKS_NOT_OPEN`` is a distinct code from ``PICKS_LOCKED`` because the two ask
    opposite things of a member: come back later, versus it is over.
    """
    if gameweek.status not in PICKABLE_STATES:
        return "PICKS_LOCKED"
    if gameweek.picks_open_at_utc is not None and now < gameweek.picks_open_at_utc:
        return "PICKS_NOT_OPEN"
    if now >= gameweek.locks_at_utc:
        return "PICKS_LOCKED"
    return None


def is_open_for_picks(gameweek: Gameweek, now: datetime) -> bool:
    """True when picks are accepted: inside the claim period and not yet locked."""
    return pick_refusal(gameweek, now) is None


def window_for(league: League) -> SlateWindow:
    """The slate window this league plays.

    The single place league columns become the value object the rest of the code
    reasons with, so nothing outside this function needs to know the window is
    stored as five integers.
    """
    return SlateWindow(
        start_weekday=league.slate_start_weekday,
        start_minute=league.slate_start_minute,
        end_weekday=league.slate_end_weekday,
        end_minute=league.slate_end_minute,
        lock_offset_minutes=league.lock_offset_minutes,
    )


def picks_open_at(league: League, starts_on: date) -> datetime | None:
    """Naive-UTC instant picks open for this league's round, or ``None`` for no gate.

    A *third* instant, and the reason it needed its own name: the window's own
    ``opens_at`` is when the fixtures kick off, ``locks_at`` is when claiming stops, and
    this is when claiming starts. All three are measured back from the same anchor, so a
    league playing Saturday 15:00 with a seven-day pick-open offset opens claims the
    previous Saturday at 15:00 and closes them at 14:30 on the day.

    ``None`` (``pick_open_offset_minutes`` unset) is the pre-Batch-27 rule: a round is
    claimable from the moment discovery writes it.
    """
    if league.pick_open_offset_minutes is None:
        return None
    return window_for(league).utc_before_open(starts_on, league.pick_open_offset_minutes)


def initial_status(picks_open_at_utc: datetime | None, now: datetime) -> GameweekStatus:
    """The state a freshly discovered round starts in.

    ``scheduled`` only while its opening is genuinely ahead. A round discovered after
    its own pick-open instant — an ad-hoc Boxing Day round, or a league that turned the
    setting on late — starts ``open``, so it is never labelled "not open yet" while
    :func:`pick_refusal` is already accepting picks on it.
    """
    if picks_open_at_utc is not None and now < picks_open_at_utc:
        return GameweekStatus.scheduled
    return GameweekStatus.open


def selected_competition_slugs(league: League) -> frozenset[str] | None:
    """The competition slugs this league plays, or ``None`` for *all UK leagues*.

    ``None`` (``leagues.competitions`` unset) is the group the slate has always used —
    every UK competition the provider carries. A configured list narrows the round to
    those slugs, matched against ``fixtures.competition_id``.

    Applied at link time in *discovery* (:func:`sync_slate`) rather than by asking the
    provider for fewer competitions, so the shared per-window fetch — and the request
    budget that depends on it — is untouched: narrowing changes what a league *plays*,
    not what discovery *costs*. On the unshared ad-hoc path it is pushed into the fetch
    instead, where the same reasoning inverts; see :func:`refresh_slate`.
    """
    if league.competitions is None:
        return None
    return frozenset(
        entry["slug"]
        for entry in league.competitions
        if isinstance(entry, dict) and entry.get("slug")
    )


def accepting_picks(now: datetime) -> ColumnElement[bool]:
    """SQL for :func:`pick_refusal` returning ``None`` — this round takes a pick *now*.

    The same three conditions in the same order, so the two cannot drift: a pickable
    status, an opening that has arrived (or was never announced), and a lock still
    ahead. ``now`` is naive-UTC, as stored.
    """
    return and_(
        Gameweek.status.in_(PICKABLE_STATES),
        or_(Gameweek.picks_open_at_utc.is_(None), Gameweek.picks_open_at_utc <= now),
        Gameweek.locks_at_utc > now,
    )


def current_round_order(
    now: datetime | None = None, today: date | None = None
) -> tuple[ColumnElement[Any], ...]:
    """Order rounds by the question a member is actually asking: which one am I on?

    Not "the newest ``starts_on``", which is what this was until Batch 35 and which a
    one-off round breaks: add Boxing Day in August and every screen in that league
    jumps to a round whose picks open in December, while the member's *other* leagues
    still show Saturday. Home renders those cards side by side, so the disagreement is
    visible in one glance.

    Three tiers, in the order a member would name them:

    1. rounds accepting picks right now, **the one locking soonest first** — once a
       Boxing Day round and the 20 December Saturday are both open, the one to act on
       is the one that shuts first;
    2. failing that, the most recent ``starts_on`` at or before today — the round just
       played, which is what a settled league should be showing;
    3. failing that, the earliest ahead — a league whose season has not started yet.

    Returned as ORDER BY clauses rather than applied here because the rule has two call
    sites — :func:`latest_gameweek` per league, and a window function over many leagues
    in ``routers/me.py`` — and they have to move together or the Coupon tab and the home
    card disagree about which round is current. Within any one tier every row shares the
    same nullness, so the tiers below it simply do not discriminate.

    Both instants default to the real clock; they are arguments so a test can put a
    league's Boxing Day round on either side of "now" without waiting for December.
    """
    accepting = accepting_picks(_utc_now() if now is None else now)
    already_started = Gameweek.starts_on <= (uk_today() if today is None else today)
    return (
        case((accepting, 0), (already_started, 1), else_=2).asc(),
        case((accepting, Gameweek.locks_at_utc), else_=None).asc(),
        case((already_started, Gameweek.starts_on), else_=None).desc(),
        Gameweek.starts_on.asc(),
    )


async def latest_gameweek(db: AsyncSession, league_id: uuid.UUID) -> Gameweek | None:
    """The round this league is currently on — what the coupon and pick screen default to.

    "Currently on" is :func:`current_round_order`, not the newest ``starts_on``. Kept
    under its original name because it is still *the* round for a league that only ever
    plays its own cadence; only a one-off round outside that cadence tells the two rules
    apart.
    """
    result = await db.execute(
        select(Gameweek)
        .where(Gameweek.league_id == league_id)
        .order_by(*current_round_order())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def gameweek_by_id(
    db: AsyncSession, league_id: uuid.UUID, gameweek_id: str
) -> Gameweek | None:
    """One of *this league's* rounds by id, or ``None``.

    Scoped to the league deliberately: before Batch 14 this was a bare primary-key
    lookup, so a member of one league could read another league's round just by
    knowing its id. A round belonging to someone else is now indistinguishable from
    one that does not exist.

    A malformed id is a miss rather than a 500 — callers pass a raw query-string
    value, and asking for a round that cannot exist is the same as asking for one
    that doesn't.
    """
    try:
        key = uuid.UUID(gameweek_id)
    except (ValueError, AttributeError, TypeError):
        return None
    result = await db.execute(
        select(Gameweek).where(Gameweek.id == key, Gameweek.league_id == league_id)
    )
    return result.scalar_one_or_none()


async def resolve_gameweek(
    db: AsyncSession, league_id: uuid.UUID, gameweek_id: str | None
) -> Gameweek:
    """The requested round of this league, or the one it is currently on when none is named.

    Shared by the slate and coupon reads so browsing back through the season means
    the same thing on both, and so the league scoping is enforced in one place.
    Raises 404 either way — for an empty season and for an id that does not resolve
    within this league — because to a client both are "there is nothing to show for
    what you asked".
    """
    gameweek = (
        await latest_gameweek(db, league_id)
        if gameweek_id is None
        else await gameweek_by_id(db, league_id, gameweek_id)
    )
    if gameweek is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No gameweek yet" if gameweek_id is None else "Gameweek not found",
        )
    return gameweek


async def all_gameweeks(db: AsyncSession, league_id: uuid.UUID) -> list[Gameweek]:
    """This league's rounds, newest first — its browsable season history.

    Nothing is pruned or archived, so this is the whole record. A season is about
    forty rows, which is small enough not to need paging.
    """
    result = await db.execute(
        select(Gameweek).where(Gameweek.league_id == league_id).order_by(Gameweek.starts_on.desc())
    )
    return list(result.scalars().all())


async def sync_slate(db: AsyncSession, league: League, slate: Slate) -> Gameweek | None:
    """Upsert this league's round for ``slate.starts_on`` and the fixtures it plays.

    Fixtures go into the **shared pool**, keyed on ``provider_event_id``: a match another
    league already discovered is updated rather than duplicated, and this league's round
    simply links to it. That is what keeps a second league on the same window free —
    no extra rows, and no extra provider request.

    The slate is first filtered to the league's competition selection
    (:func:`selected_competition_slugs`; ``None`` = all UK). A league that plays none of
    this window's competitions gets **no** new round — ``None`` is returned — but an
    existing round is left exactly as it is, because a member may already hold a pick on
    it. This is the only place the selection is applied, so two leagues sharing a window
    but not a selection still cost one fetch and simply link different subsets of it.

    Both ends of the claim period — ``locks_at_utc`` and ``picks_open_at_utc`` — are
    fixed when the round is created and never re-derived on a refresh, so an admin
    editing the window cannot move a deadline members have already been told.

    Links are added, and removed only on the provider's say-so. A fixture that simply
    *drops off* a later refresh stays on the round: a partial or failed fetch looks
    exactly like a quiet one, so unlinking on absence would let a single provider hiccup
    strip a round of live picks. A fixture the provider explicitly reports void —
    postponed, cancelled, abandoned — is taken off, picks and all, by
    :func:`_drop_voided_fixtures` (Batch 49).

    Flushes so the returned gameweek and fixtures have ids, but does **not** commit —
    the caller owns the transaction boundary.
    """
    wanted = selected_competition_slugs(league)
    selected = (
        slate.fixtures
        if wanted is None
        else [sf for sf in slate.fixtures if sf.competition_id in wanted]
    )
    playable = [sf for sf in selected if not is_void_status(sf.status)]

    window = window_for(league)
    result = await db.execute(
        select(Gameweek).where(
            Gameweek.league_id == league.id, Gameweek.starts_on == slate.starts_on
        )
    )
    gameweek = result.scalar_one_or_none()
    if gameweek is None:
        # Nothing this league plays on this date, and no round to preserve — create none.
        # Keyed on the *playable* fixtures rather than every selected one: a date whose
        # whole card is called off is a date with no round, not a round with no fixtures.
        if not playable:
            return None
        opens_at = picks_open_at(league, slate.starts_on)
        gameweek = Gameweek(
            league_id=league.id,
            starts_on=slate.starts_on,
            locks_at_utc=window.locks_at(slate.starts_on),
            picks_open_at_utc=opens_at,
            status=initial_status(opens_at, _utc_now()),
            number=await next_gameweek_number(db, league.id, slate.starts_on),
        )
        db.add(gameweek)
        await db.flush()

    if not selected:
        return gameweek

    events = [sf.provider_event_id for sf in selected]
    pooled = await db.execute(select(Fixture).where(Fixture.provider_event_id.in_(events)))
    by_event = {f.provider_event_id: f for f in pooled.scalars().all()}

    for sf in selected:
        fixture = by_event.get(sf.provider_event_id)
        if fixture is None:
            fixture = Fixture(provider_event_id=sf.provider_event_id)
            db.add(fixture)
            by_event[sf.provider_event_id] = fixture
        # Names/kick-off can shift as the provider firms up the card before lock.
        fixture.home = sf.home
        fixture.away = sf.away
        fixture.kickoff_utc = _naive_utc(sf.kickoff_utc)
        fixture.competition = sf.competition
        fixture.competition_id = sf.competition_id
    await db.flush()

    linked = await db.execute(
        select(GameweekFixture.fixture_id).where(GameweekFixture.gameweek_id == gameweek.id)
    )
    already = set(linked.scalars().all())
    for sf in playable:
        fixture = by_event[sf.provider_event_id]
        if fixture.id not in already:
            db.add(GameweekFixture(gameweek_id=gameweek.id, fixture_id=fixture.id))

    await _drop_voided_fixtures(
        db,
        league,
        gameweek,
        {
            by_event[sf.provider_event_id].id: sf
            for sf in selected
            if is_void_status(sf.status) and by_event[sf.provider_event_id].id in already
        },
    )

    await db.flush()
    return gameweek


async def _drop_voided_fixtures(
    db: AsyncSession,
    league: League,
    gameweek: Gameweek,
    voided: Mapping[uuid.UUID, SlateFixture],
) -> None:
    """Take called-off fixtures off a still-open round, and the picks held on them.

    The state a member is left in is *no pick*, which is the one state the game already
    understands: the coupon reopens the selection to the land-grab, the 11:00 reminder
    job nudges them if they do not use it, and nothing in scoring has to learn a new
    shape.

    **Only before the lock.** A member who picked before the deadline did everything
    right and has no way to respond after it, so deleting their pick then would leave
    them indistinguishable in the standings from someone who never picked at all. Past
    the lock this does nothing and the evening settle sweep writes ``void`` instead,
    which already means "scores nothing rather than counting as a loss". Refresh runs
    09:00 and 13:00 against a 14:30 lock, so a Saturday-morning postponement is caught
    here and an afternoon one is caught there.

    **Two deletes, not one.** ``Pick.fixture_id`` and ``Pick.gameweek_id`` cascade from
    ``fixtures`` and ``gameweeks``, but ``gameweek_fixtures`` is a composite-key join
    with no cascade to picks, so dropping the link alone would leave the pick alive and
    pointing at a fixture no longer on its round — off the screen, still found by
    settlement. Both rows go, in one transaction. Picks go first because that is the
    ordering whose half-done state is harmless: a link with no pick is a fixture the
    member can simply pick again, where a pick with no link is the orphan itself.

    The copy is written here against ``send_notification`` directly rather than as a
    wrapper in ``notification_triggers``, where the other triggers live: that module
    imports this one (``members_missing_picks``), so the dependency has to run one way.
    ``data.type`` is free-form, so ``"fixture_postponed"`` needs no enum value and no
    migration — deliberately not an ``ActionType``, which is a Postgres enum and would.
    """
    if not voided or gameweek.locks_at_utc <= _utc_now():
        return

    stranded = (
        await db.execute(
            select(Pick, Profile)
            .join(Profile, Profile.id == Pick.player_id)
            .where(Pick.gameweek_id == gameweek.id, Pick.fixture_id.in_(voided.keys()))
        )
    ).all()
    # Read off what the copy needs *before* the rows go: a deleted instance is not
    # something to be reading attributes off afterwards.
    told = [(player, voided[pick.fixture_id]) for pick, player in stranded]

    for pick, _player in stranded:
        await db.delete(pick)
    await db.execute(
        delete(GameweekFixture).where(
            GameweekFixture.gameweek_id == gameweek.id,
            GameweekFixture.fixture_id.in_(voided.keys()),
        )
    )
    await db.flush()

    for player, fixture in told:
        await send_notification(
            db,
            player.id,
            "Fixture postponed",
            f"{fixture.home} v {fixture.away} is off, so your pick in {league.name} "
            f"has been returned. Pick again before the deadline.",
            data={
                "type": "fixture_postponed",
                "league_id": str(league.id),
                "url": f"/leagues/{league.slug}/predictions",
            },
            tag=f"fixture-postponed-{gameweek.id}",
            timezone_name=player.timezone,
        )


async def fixtures_for(db: AsyncSession, gameweek_id: uuid.UUID) -> list[Fixture]:
    """The fixtures a round plays, in kick-off order."""
    result = await db.execute(
        select(Fixture)
        .join(GameweekFixture, GameweekFixture.fixture_id == Fixture.id)
        .where(GameweekFixture.gameweek_id == gameweek_id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )
    return list(result.scalars().all())


# ── Scheduler-driven lifecycle (Batch 4) ────────────────────────────────────────


def upcoming_slate_dates(today: date, window: SlateWindow, count: int) -> list[date]:
    """The next ``count`` dates this window opens on, today included.

    Fixture *discovery* runs on this horizon so a round's card exists days before
    anyone can pick on it. Pricing is deliberately not on this horizon — odds are
    fetched on demand, because a price is only meaningful at the moment a member
    freezes it onto a pick.

    This is the league's **cadence** only — a weekly step from its window's next
    opening. A round on any other date exists solely because an admin asked for one,
    so it cannot be derived and has to be read back
    (:func:`unlocked_round_dates`); see :func:`discover_fixtures`.
    """
    first = window.first_start_on_or_after(today)
    return [first + timedelta(weeks=offset) for offset in range(max(count, 1))]


async def unlocked_round_dates(
    db: AsyncSession, league_ids: Sequence[uuid.UUID], today: date, until: date
) -> dict[uuid.UUID, set[date]]:
    """Dates each of these leagues holds a still-claimable round on, within the horizon.

    The off-cadence half of what discovery has to cover. Bounded at both ends on
    purpose: a round already locked cannot change in any way a refresh could record —
    its card is fixed and its picks are frozen — and a round beyond the horizon has not
    firmed up yet, so fetching either spends the request budget on nothing.
    """
    if not league_ids:
        return {}
    rows = await db.execute(
        select(Gameweek.league_id, Gameweek.starts_on).where(
            Gameweek.league_id.in_(league_ids),
            Gameweek.status.in_(PICKABLE_STATES),
            Gameweek.starts_on >= today,
            Gameweek.starts_on <= until,
        )
    )
    dates: dict[uuid.UUID, set[date]] = {}
    for league_id, starts_on in rows.all():
        dates.setdefault(league_id, set()).add(starts_on)
    return dates


def slate_odds_max_age(gameweek: Gameweek, now: datetime, near_ttl: float, far_ttl: float) -> float:
    """How stale a browsed price may be, tightening as the lock approaches.

    Three tiers rather than a curve, because the cost is a step function of the TTL
    and a legible budget matters more here than a smooth one. Every state but ``open``
    gets the loosest tier: nothing can move a price that is already frozen, and nobody
    can freeze one on a round whose picks have not opened, so re-fetching either buys
    nothing.
    """
    if gameweek.status != GameweekStatus.open:
        return far_ttl
    until_lock = (gameweek.locks_at_utc - now).total_seconds()
    if until_lock <= _NEAR_LOCK_SECONDS:
        return near_ttl
    if until_lock <= _MID_LOCK_SECONDS:
        return far_ttl / 2
    return far_ttl


async def active_leagues(db: AsyncSession) -> list[League]:
    """Every league still playing — the leagues discovery has to cover."""
    result = await db.execute(select(League).where(League.deleted_at.is_(None)))
    return list(result.scalars().all())


async def discover_fixtures(
    db: AsyncSession, provider: OddsProvider, leagues: Sequence[League], today: date, horizon: int
) -> list[Gameweek]:
    """Walk every league's coming cards into the pool and link them to its rounds.

    The pre-fetch half of Batch 11's split: discovery is scheduled and cheap, pricing
    is on demand and rate-limited.

    Leagues are grouped **by window** and each ``(window, date)`` is fetched exactly
    once, then shared by every league playing it. This is what stops per-league
    windows multiplying the provider bill: the cost is the number of *distinct*
    windows, not the number of leagues, so a second league on the default Saturday
    is free. Only leagues that genuinely play a different window cost anything more.

    The dates walked are each window's cadence (:func:`upcoming_slate_dates`) **union**
    the dates those leagues already hold unlocked rounds on inside the same horizon
    (:func:`unlocked_round_dates`). Without the union a one-off round — Boxing Day, say
    — is never revisited after the admin creates it, so a postponement, a late addition
    or a corrected kick-off never lands on it, and since :func:`sync_slate` only ever
    adds links it cannot self-correct either. Grouping still happens by window, so two
    leagues that both added Boxing Day are refreshed on one fetch.

    An off-cadence date is synced **only** to the leagues that already hold a round on
    it. A league sharing the window but not the one-off must not have a Boxing Day round
    invented for it because its neighbour asked for one.

    Dates the provider carries nothing for are skipped rather than left as empty
    rounds. Flushes but does not commit — the caller owns the transaction.
    """
    by_window: dict[SlateWindow, list[League]] = {}
    for league in leagues:
        by_window.setdefault(window_for(league), []).append(league)

    cadence = {window: upcoming_slate_dates(today, window, horizon) for window in by_window}
    horizon_end = max((dates[-1] for dates in cadence.values()), default=today)
    off_cadence = await unlocked_round_dates(
        db, [league.id for league in leagues], today, horizon_end
    )

    discovered: list[Gameweek] = []
    for window, sharing in by_window.items():
        scheduled = set(cadence[window])
        dates = scheduled.union(*(off_cadence.get(league.id, set()) for league in sharing))
        for starts_on in sorted(dates):
            playing = (
                sharing
                if starts_on in scheduled
                else [lg for lg in sharing if starts_on in off_cadence.get(lg.id, set())]
            )
            slate = await provider.fetch_slate(window, starts_on)
            if not slate.fixtures:
                continue
            for league in playing:
                # ``None`` when the league's competition selection excludes the whole
                # window — no round to record, but the shared fetch is unaffected.
                gameweek = await sync_slate(db, league, slate)
                if gameweek is not None:
                    discovered.append(gameweek)
    return discovered


async def refresh_slate(
    db: AsyncSession, provider: OddsProvider, league: League, starts_on: date
) -> Gameweek | None:
    """Fetch one league's card for ``starts_on`` and upsert it as a round.

    The league's competition selection is pushed **into the fetch** here, which is the
    opposite of what :func:`sync_slate` does and deliberately so. Discovery filters at
    link time because its fetch is shared between every league on the window, so asking
    for fewer competitions would save one league's money by spending another's. This
    function has exactly one production caller — the ad-hoc round endpoint — and there
    the fetch is one league's alone: nobody shares it, so filtering afterwards is simply
    paying for ~30 UK competitions to keep as few as one. A league playing two divisions
    now costs two requests instead of thirty.

    The trade that buys it: a narrowed ad-hoc fetch no longer warms the pool for a wider
    league on the same date. That is correct rather than a regression — nothing shared
    this fetch to begin with.

    Returns the synced round, or ``None`` when there is nothing to record — either the
    provider carries no qualifying fixtures (e.g. out of season) or the league's
    competition selection excludes every one it does. Either way no empty round is left
    behind. Flushes but does not commit — the scheduler job owns the transaction.
    """
    slate = await provider.fetch_slate(
        window_for(league), starts_on, competition_ids=selected_competition_slugs(league)
    )
    if not slate.fixtures:
        return None
    return await sync_slate(db, league, slate)


# ── Populating a league's rounds on demand (Batch 47) ───────────────────────────
#
# Discovery runs once a day at 06:00, so a league created at any other hour had no
# round, no card and no coupon until the next morning. These two functions are the
# cheap second entry point into the machinery above: same ``sync_slate``, same
# cadence, but reading the fixtures back out of the pool instead of buying them.


async def pooled_slate(db: AsyncSession, window: SlateWindow, starts_on: date) -> Slate:
    """This window's card for ``starts_on``, read back out of the shared fixture pool.

    The corollary of what makes a second league on the default Saturday free. Discovery
    fetches each ``(window, date)`` once and writes every kick-off into ``fixtures``, so
    once *any* league has pulled a window's card for a date, the rows another league on
    that window needs are already there — and turning them back into a
    :class:`~src.services.odds_provider.Slate` costs one query rather than one request
    per competition.

    Selected exactly the way a provider fetch is: the window's whole-day
    :meth:`~src.services.odds_provider.SlateWindow.query_bounds` in SQL, then
    :meth:`~src.services.odds_provider.SlateWindow.contains` deciding which kick-offs
    actually qualify. So a pooled slate and a fetched one carry the same fixtures, and
    :func:`sync_slate` cannot tell them apart.

    The pool is not a guarantee of completeness: a date whose only fetch was an ad-hoc
    one holds just that league's competitions (:func:`refresh_slate` narrows its fetch),
    so a league reading it back gets that subset rather than the full window. Partial is
    still better than empty — the next discovery run fetches the window unfiltered and
    :func:`sync_slate` adds the missing links to the same round.
    """
    start, end = window.query_bounds(starts_on)
    rows = await db.execute(
        select(Fixture).where(
            Fixture.kickoff_utc >= _naive_utc(start), Fixture.kickoff_utc < _naive_utc(end)
        )
    )
    return Slate(
        starts_on=starts_on,
        fixtures=[
            SlateFixture(
                provider_event_id=fixture.provider_event_id,
                home=fixture.home,
                away=fixture.away,
                kickoff_utc=fixture.kickoff_utc,
                competition=fixture.competition,
                competition_id=fixture.competition_id,
            )
            for fixture in rows.scalars().all()
            if window.contains(fixture.kickoff_utc, starts_on)
        ],
    )


@dataclass(frozen=True)
class PopulatedRounds:
    """What one populate run produced, and what it spent getting there.

    Every list holds cadence dates, and each date the run considered lands in exactly
    one of four places: it produced a round (``gameweeks``, and ``created_dates`` when
    the round did not exist before), it was left alone (``skipped_dates``), it was left
    for the daily job (``deferred_dates``), or it produced nothing at all — a date the
    league's competition selection excludes entirely, which is a league with no round
    rather than an error. ``fetched_dates`` cuts across ``gameweeks``: the dates the
    pool could not serve, and therefore the only ones that cost a provider request.
    """

    gameweeks: list[Gameweek]
    created_dates: list[date]
    fetched_dates: list[date]
    deferred_dates: list[date]
    skipped_dates: list[date]


async def populate_cadence_rounds(
    db: AsyncSession,
    provider: OddsProvider | None,
    league: League,
    today: date,
    horizon: int,
    *,
    may_fetch: Callable[[], bool] | None = None,
) -> PopulatedRounds:
    """Create or top up this league's cadence rounds now, without waiting for 06:00.

    The common case costs **nothing**. Almost every league plays the default Saturday,
    which some league has already had discovery fetch, so the fixtures are in the pool
    and this is :func:`sync_slate` against rows that already exist — no provider request,
    and the round is on screen the moment the league is created.

    A league genuinely inventing a window — a Wednesday 19:45, say — has an empty pool
    for its dates and has to buy them. That path goes through :func:`refresh_slate`,
    which narrows the fetch to the league's own competitions, and it is gated by
    ``may_fetch``: one call per date, charged against the same budget the ad-hoc round
    endpoint spends, so the two cannot be combined to exceed it. The first refusal ends
    the fetching for this run — the bucket is empty, and asking again would only burn
    the shorter of its two windows — but the free, pooled dates are still populated.
    ``provider`` of ``None`` (no odds source configured or reachable) is the same case
    without the budget question: pool only.

    **Cadence only.** The dates walked are :func:`upcoming_slate_dates` and nothing else,
    where :func:`discover_fixtures` also covers the off-cadence rounds those leagues
    already hold. That difference is the point: an off-cadence date belongs to the league
    that asked for it, so a neighbour's Boxing Day must not be invented here for a league
    that never requested one.

    A date whose round is already ``locked`` or ``settled`` is skipped. Its card is fixed
    and its picks are frozen, which is the same boundary :func:`unlocked_round_dates`
    draws for the daily job. Rounds that *are* rebuilt keep both ends of their claim
    period: :func:`sync_slate` derives ``picks_open_at_utc`` and ``locks_at_utc`` only
    when it creates a round, so refreshing one can add fixtures but can never move a
    deadline members have already been told.

    Flushes but does not commit — the caller owns the transaction.
    """
    window = window_for(league)
    dates = upcoming_slate_dates(today, window, horizon)
    existing = await _rounds_by_date(db, league.id, dates)

    gameweeks: list[Gameweek] = []
    created: list[date] = []
    fetched: list[date] = []
    deferred: list[date] = []
    skipped: list[date] = []
    out_of_budget = False

    for starts_on in dates:
        status = existing.get(starts_on)
        if status is not None and status not in PICKABLE_STATES:
            skipped.append(starts_on)
            continue

        slate = await pooled_slate(db, window, starts_on)
        if slate.fixtures:
            gameweek = await sync_slate(db, league, slate)
        else:
            if provider is None or out_of_budget or (may_fetch is not None and not may_fetch()):
                out_of_budget = provider is not None
                deferred.append(starts_on)
                continue
            gameweek = await refresh_slate(db, provider, league, starts_on)
            fetched.append(starts_on)

        if gameweek is None:
            continue
        gameweeks.append(gameweek)
        if status is None:
            created.append(starts_on)

    return PopulatedRounds(
        gameweeks=gameweeks,
        created_dates=created,
        fetched_dates=fetched,
        deferred_dates=deferred,
        skipped_dates=skipped,
    )


async def _rounds_by_date(
    db: AsyncSession, league_id: uuid.UUID, dates: Sequence[date]
) -> dict[date, GameweekStatus]:
    """The rounds this league already holds on these dates, by date.

    Read once for the whole run rather than per date, and carrying the status because
    it decides two different things: whether the round may be rebuilt at all, and
    whether producing one counts as creating it or refreshing it.
    """
    if not dates:
        return {}
    rows = await db.execute(
        select(Gameweek.starts_on, Gameweek.status).where(
            Gameweek.league_id == league_id, Gameweek.starts_on.in_(dates)
        )
    )
    return {starts_on: status for starts_on, status in rows.all()}


async def open_due_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Flip every scheduled round whose announced opening has passed to ``open``.

    The mirror of :func:`lock_due_gameweeks`, and like it only a label-keeper:
    :func:`pick_refusal` already accepts a pick the moment the instant passes, so a
    missed run delays the badge on the screen and never the game. ``now`` is naive-UTC.
    Flushes but does not commit.
    """
    result = await db.execute(
        select(Gameweek).where(
            Gameweek.status == GameweekStatus.scheduled,
            Gameweek.picks_open_at_utc.is_not(None),
            Gameweek.picks_open_at_utc <= now,
        )
    )
    opened = list(result.scalars().all())
    for gameweek in opened:
        gameweek.status = GameweekStatus.open
    await db.flush()
    return opened


async def lock_due_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Flip every not-yet-locked round whose lock has passed to ``locked``.

    Covers ``scheduled`` as well as ``open``: a round whose lock arrived while it was
    still waiting to open — a misconfigured offset, or an open job that never ran — is
    over either way, and leaving it ``scheduled`` would advertise a claim period that
    has already closed.

    ``now`` is naive-UTC (as stored). Predicate-based rather than "the latest one" so a
    missed run self-heals on the next. Flushes but does not commit.
    """
    result = await db.execute(
        select(Gameweek).where(
            Gameweek.status.in_(PICKABLE_STATES),
            Gameweek.locks_at_utc <= now,
        )
    )
    locked = list(result.scalars().all())
    for gameweek in locked:
        gameweek.status = GameweekStatus.locked
    await db.flush()
    return locked


async def settleable_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Gameweeks past their lock that aren't settled yet — the settle job's candidates.

    Includes any still ``open`` past its lock (a defensive catch if the lock job missed a
    run) as well as ``locked`` ones. Ordered oldest-first.
    """
    result = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.status != GameweekStatus.settled,
            Gameweek.locks_at_utc <= now,
        )
        .order_by(Gameweek.starts_on)
    )
    return list(result.scalars().all())


async def current_open_gameweeks(db: AsyncSession, now: datetime) -> list[Gameweek]:
    """Every still-open round whose lock is in the future — the ones to remind for.

    A list, not one row. Before Batch 14 there was a single global round so "the
    current one" was well defined; now every league has its own, and returning one
    would silently deny reminders to every league but that one.

    ``scheduled`` is deliberately excluded: nagging a member for a pick they are not
    yet allowed to make is worse than not reminding them at all.
    """
    result = await db.execute(
        select(Gameweek)
        .where(
            Gameweek.status == GameweekStatus.open,
            Gameweek.locks_at_utc > now,
        )
        .order_by(Gameweek.starts_on.desc())
    )
    return list(result.scalars().all())


class MissingPickMember(BaseModel):
    """A member who still owes a pick for a gameweek — one pick-reminder recipient."""

    player_id: str
    display_name: str
    timezone: str
    league_id: str
    #: The league's address, so a reminder can link to *that* league's pick screen.
    league_slug: str
    league_name: str


async def members_missing_picks(db: AsyncSession, gameweek: Gameweek) -> list[MissingPickMember]:
    """Members of *this round's league* with no pick for it — the reminder recipients.

    Filtered to ``gameweek.league_id``. Before Batch 14 a round was global, and this
    query had no league filter at all, so a reminder for one round was sent to every
    member of every league in the database. Excludes deleted memberships/leagues and
    inactive/deleted profiles, and memberships with ``notification_muted`` — a muted
    league is never targeted, rather than targeted and suppressed, which also keeps
    ``send_pick_reminders``' return count honest about who was actually nudged.
    """
    display_name = func.coalesce(LeagueMembership.display_name_override, Profile.display_name)
    rows = await db.execute(
        select(
            LeagueMembership.player_id,
            display_name.label("display_name"),
            Profile.timezone,
            League.id.label("league_id"),
            League.slug.label("league_slug"),
            League.name.label("league_name"),
        )
        .select_from(LeagueMembership)
        .join(League, League.id == LeagueMembership.league_id)
        .join(Profile, Profile.id == LeagueMembership.player_id)
        .outerjoin(
            Pick,
            (Pick.league_id == LeagueMembership.league_id)
            & (Pick.player_id == LeagueMembership.player_id)
            & (Pick.gameweek_id == gameweek.id),
        )
        .where(
            LeagueMembership.league_id == gameweek.league_id,
            LeagueMembership.deleted_at.is_(None),
            LeagueMembership.notification_muted.is_(False),
            League.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
            Profile.is_active.is_(True),
            Pick.id.is_(None),
        )
    )
    return [
        MissingPickMember(
            player_id=str(row.player_id),
            display_name=row.display_name,
            timezone=row.timezone,
            league_id=str(row.league_id),
            league_slug=row.league_slug,
            league_name=row.league_name,
        )
        for row in rows.all()
    ]
