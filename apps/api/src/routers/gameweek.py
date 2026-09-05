"""The weekly pick screen — a gameweek's slate with live odds and taken selections.

``GET /api/v1/leagues/{slug}/gameweeks`` lists the season, newest first.
``GET /api/v1/leagues/{slug}/gameweek/current`` returns a gameweek's fixtures,
each with the currently-priced selections, marking which are already grabbed in this
leaderboard (and which is the caller's own). It's a read view; grabbing happens via
``POST .../picks``.

The odds here come from the provider on every request, which is why the provider handed
out by ``deps.get_odds_provider`` caches: fifteen members refreshing this page must not
turn into fifteen upstream calls against a 100/hour quota.

That same cache is what keeps this screen up when the provider is down. The slate reads
through ``fetch_odds_best_effort``, so a failed refresh serves the last known prices and
sets ``odds_degraded`` rather than answering ``500`` (Batch 48).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, NamedTuple

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.config import settings
from src.database import get_db
from src.deps import LeagueMemberDep, OddsProviderDep
from src.models.fixture import Fixture
from src.models.gameweek import GameweekFixture
from src.models.league import PickMarket, PickScope
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile
from src.schemas import UtcDatetime
from src.services.football_data import FixtureContext, fixture_context, season_or_default
from src.services.gameweek import (
    all_gameweeks,
    fixtures_for,
    resolve_gameweek,
    slate_odds_max_age,
)
from src.services.odds_pricing import askable, pickable, record_observations
from src.services.odds_provider import FixtureOdds

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/leagues", tags=["gameweek"])

Db = Annotated[AsyncSession, Depends(get_db)]


# ── Schemas ─────────────────────────────────────────────────────────────────────


class SelectionOption(BaseModel):
    market: str
    outcome: str
    runner_name: str
    odds: float
    taken_by_player_id: str | None  # who holds it in this league (None = available)
    taken_by_name: str | None
    # When the holder claimed it (`Pick.created_at`). Stored naive UTC and stamped with
    # its offset on the wire, like every other instant here (Batch 43). Added rather than
    # replacing anything, because the web app deploys ahead of this API — a renamed field
    # would break the coupon until `/ship-prod` caught up.
    taken_at: UtcDatetime | None
    mine: bool


class FixtureSlate(BaseModel):
    fixture_id: str
    provider_event_id: str
    home: str
    away: str
    competition_id: str
    competition: str
    kickoff_utc: UtcDatetime
    selections: list[SelectionOption]
    # Fixture-level "already picked" marker, alongside the per-selection one.
    # Several members can hold different selections on one game under the
    # current selection-level rule, so this is a list rather than a flag.
    taken_by_names: list[str]
    mine: bool
    # Both clubs' league position and recent form (Batch 16), or `None` when the
    # football-data source has nothing for them. Read from `standings` / `matches`,
    # never from a provider — see src/services/football_data.py.
    context: FixtureContext | None = None


class GameweekMember(BaseModel):
    """One leaderboard member's standing on this gameweek.

    Everything here is already derivable from the slate's ``taken_by_name``
    fields — this only saves the client from reconstructing it, and adds the
    members who appear nowhere in the slate because they have not picked.
    """

    player_id: str
    display_name: str
    has_picked: bool
    fixture_id: str | None
    home: str | None
    away: str | None
    competition: str | None
    market: str | None
    outcome: str | None
    runner_name: str | None
    odds: float | None


class GameweekListEntry(BaseModel):
    """One row of the season's history — enough to label and choose it."""

    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: UtcDatetime
    # When picks open, or ``null`` when the league announces no opening (Batch 27).
    picks_open_at_utc: UtcDatetime | None
    # What members call this round — "Gameweek 12" (Batch 41). ``null`` for a round that
    # predates the numbering, which reads as "show the date alone".
    number: int | None
    fixture_count: int
    # Picks made in *this* league, so the same gameweek reads differently per league.
    pick_count: int


class GameweekSlateResponse(BaseModel):
    gameweek_id: str
    starts_on: date
    status: str
    locks_at_utc: UtcDatetime
    # When picks open, or ``null`` when the league announces no opening (Batch 27).
    # The pick screen needs it to count *down* to a round it cannot yet claim on,
    # rather than reporting it as locked.
    picks_open_at_utc: UtcDatetime | None
    # What members call this round — "Gameweek 12" (Batch 41), or ``null`` when unnumbered.
    number: int | None
    fixtures: list[FixtureSlate]
    members: list[GameweekMember]
    members_missing_picks: int
    # The league's claim rule, so the client can say why a whole game is gone.
    pick_scope: str
    # True when the prices above came out of a *failed* refresh — last known values, or
    # none at all — so the client can say "prices may be out of date" instead of
    # presenting stale numbers as current (Batch 48). Defaulted rather than required,
    # for the reason Batches 38 and 41 already record: Vercel deploys `main` on merge
    # while this API waits for `/ship-prod`, so a required field breaks the coupon in
    # that gap.
    odds_degraded: bool = False


@router.get("/{slug}/gameweeks", response_model=list[GameweekListEntry])
async def list_gameweeks(
    slug: str,
    league: LeagueMemberDep,
    db: Db,
) -> list[GameweekListEntry]:
    """The season so far, newest first — what makes past weeks browsable.

    Every gameweek ever synced is still in the table, so this is the whole record
    with nothing to backfill. Counts are per league, because the same Saturday has
    a different set of picks in each one.
    """
    gameweeks = await all_gameweeks(db, league.id)
    if not gameweeks:
        return []

    fixture_rows = await db.execute(
        select(GameweekFixture.gameweek_id, func.count())
        .where(GameweekFixture.gameweek_id.in_([g.id for g in gameweeks]))
        .group_by(GameweekFixture.gameweek_id)
    )
    fixture_counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in fixture_rows.all()}

    pick_rows = await db.execute(
        select(Pick.gameweek_id, func.count())
        .where(Pick.league_id == league.id)
        .group_by(Pick.gameweek_id)
    )
    pick_counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in pick_rows.all()}
    return [
        GameweekListEntry(
            gameweek_id=str(gameweek.id),
            starts_on=gameweek.starts_on,
            status=gameweek.status.value,
            locks_at_utc=gameweek.locks_at_utc,
            picks_open_at_utc=gameweek.picks_open_at_utc,
            number=gameweek.number,
            fixture_count=fixture_counts.get(gameweek.id, 0),
            pick_count=pick_counts.get(gameweek.id, 0),
        )
        for gameweek in gameweeks
    ]


@router.get("/{slug}/gameweek/current", response_model=GameweekSlateResponse)
async def current_gameweek(
    slug: str,
    player: CurrentUser,
    league: LeagueMemberDep,
    provider: OddsProviderDep,
    db: Db,
    gameweek_id: str | None = None,
) -> GameweekSlateResponse:
    """A gameweek's slate — the latest by default, or ``gameweek_id`` when browsing back."""
    gameweek = await resolve_gameweek(db, league.id, gameweek_id)

    now = datetime.now(UTC).replace(tzinfo=None)
    #: Every fixture the round plays. The card may show fewer (see `pickable` below), but
    #: the roster still has to name the game behind a pick that is no longer on it.
    all_fixtures = await fixtures_for(db, gameweek.id)
    fixtures = all_fixtures

    taken = await _taken_selections(db, league.id, gameweek.id)
    # Browsing tolerates a stale-ish price; the ceiling tightens as lock nears, and the
    # price a member is actually scored on is refreshed at submit time, not here.
    max_age = slate_odds_max_age(
        gameweek,
        now,
        near_ttl=settings.odds_cache_near_ttl_seconds,
        far_ttl=settings.odds_cache_ttl_seconds,
    )
    # Batch 114. Only ask about fixtures where asking can tell us something: on the round
    # that prompted the batch, 103 of 202 were ties Bet365 prices nothing on, and they
    # cost 11 requests of every 21-request sweep for the answer *no*.
    asked = askable(fixtures, now, recheck_seconds=settings.odds_unpriced_recheck_seconds)
    odds_by_event, odds_degraded, observed = await _live_odds(
        provider, [f.provider_event_id for f in asked], max_age_seconds=max_age
    )
    # Record only what this sweep actually learned. `observed` is empty on every path that
    # did not reach the provider, so a degraded sweep marks nothing — which is what keeps
    # the filter below from blanking a card because the source was briefly unreachable.
    if record_observations(asked, observed, odds_by_event.keys(), now):
        await db.commit()
    fixtures = pickable(fixtures, claimed={fixture_id for fixture_id, _, _ in taken})
    if odds_degraded:
        log.warning(
            "slate served with degraded odds",
            league_id=str(league.id),
            gameweek_id=str(gameweek.id),
            fixtures=len(fixtures),
            priced=len(odds_by_event),
        )

    # Tables and form, from our own tables — three queries for a slate of any size, and
    # no upstream request. An empty map simply means nothing has been ingested yet.
    contexts = await fixture_context(
        db,
        fixtures,
        season=season_or_default(settings.football_season),
        form_matches=settings.football_form_matches,
    )

    holders_by_fixture = _holders_by_fixture(taken)
    # The markets this league offers — the slate must not show a selection the submit
    # endpoint would refuse with MARKET_NOT_OFFERED. Coerced through PickMarket so it
    # holds whether the array column yields enum members or bare strings.
    offered = frozenset(PickMarket(market).value for market in league.offered_markets)
    slate = [
        FixtureSlate(
            fixture_id=str(fixture.id),
            provider_event_id=fixture.provider_event_id,
            home=fixture.home,
            away=fixture.away,
            competition_id=fixture.competition_id,
            competition=fixture.competition,
            kickoff_utc=fixture.kickoff_utc,
            selections=_selection_options(
                fixture,
                odds_by_event.get(fixture.provider_event_id),
                taken,
                player.id,
                league.pick_scope,
                holders_by_fixture.get(str(fixture.id), []),
                offered,
            ),
            taken_by_names=[h.name for h in holders_by_fixture.get(str(fixture.id), [])],
            mine=any(
                h.player_id == str(player.id) for h in holders_by_fixture.get(str(fixture.id), [])
            ),
            context=contexts.get(str(fixture.id)),
        )
        for fixture in fixtures
    ]
    members = await _gameweek_members(db, league.id, gameweek.id, all_fixtures)
    return GameweekSlateResponse(
        gameweek_id=str(gameweek.id),
        starts_on=gameweek.starts_on,
        status=gameweek.status.value,
        locks_at_utc=gameweek.locks_at_utc,
        picks_open_at_utc=gameweek.picks_open_at_utc,
        number=gameweek.number,
        fixtures=slate,
        members=members,
        members_missing_picks=sum(1 for m in members if not m.has_picked),
        pick_scope=league.pick_scope.value,
        odds_degraded=odds_degraded,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


class _Holder(NamedTuple):
    """Who holds a selection, and when they claimed it.

    ``taken_at`` is ``Pick.created_at`` — naive UTC as the column stores it. It has
    always been on the row; nothing carried it out. This is an internal carrier, not a
    response model, so the value stays naive until ``SelectionOption`` serialises it.
    """

    player_id: str
    name: str
    taken_at: datetime


# key: (fixture_id, market_value, outcome_value) -> holder
_TakenMap = dict[tuple[str, str, str], _Holder]


async def _taken_selections(db: AsyncSession, league_id: object, gameweek_id: object) -> _TakenMap:
    result = await db.execute(
        select(Pick, Profile.display_name)
        .join(Profile, Profile.id == Pick.player_id)
        .where(Pick.league_id == league_id, Pick.gameweek_id == gameweek_id)
    )
    taken: _TakenMap = {}
    for pick, display_name in result.all():
        key = (str(pick.fixture_id), pick.market.value, pick.outcome.value)
        taken[key] = _Holder(str(pick.player_id), display_name, pick.created_at)
    return taken


def _holders_by_fixture(taken: _TakenMap) -> dict[str, list[_Holder]]:
    """Collapse the selection-keyed map to ``fixture_id -> [holder]``.

    Distinct **per player**, because one member holding two selections on a fixture would
    otherwise be named twice — which the selection-level rule permits. Deduplicating on
    the whole holder stopped being equivalent once it carried a timestamp: two selections
    claimed a minute apart are different values but the same person. The earliest claim is
    kept, which is when that member picked this game.
    """
    by_fixture: dict[str, list[_Holder]] = {}
    for (fixture_id, _, _), holder in taken.items():
        holders = by_fixture.setdefault(fixture_id, [])
        existing = next((h for h in holders if h.player_id == holder.player_id), None)
        if existing is None:
            holders.append(holder)
        elif holder.taken_at < existing.taken_at:
            holders[holders.index(existing)] = holder
    return by_fixture


async def _gameweek_members(
    db: AsyncSession,
    league_id: object,
    gameweek_id: object,
    fixtures: list[Fixture],
) -> list[GameweekMember]:
    """Every active member of the league and the pick they hold, if any.

    This discloses nothing the slate does not already carry — a taken selection
    is labelled with its holder's name for the land-grab to be legible — but it
    also names the members who have *not* picked, who by definition appear
    nowhere in the slate. Ordered by display name so the roster is stable
    between refreshes.
    """
    fixture_by_id = {str(f.id): f for f in fixtures}

    roster = await db.execute(
        select(Profile.id, Profile.display_name)
        .join(LeagueMembership, LeagueMembership.player_id == Profile.id)
        .where(
            LeagueMembership.league_id == league_id,
            LeagueMembership.deleted_at.is_(None),
            Profile.deleted_at.is_(None),
        )
        .order_by(Profile.display_name)
    )

    picks_result = await db.execute(
        select(Pick).where(Pick.league_id == league_id, Pick.gameweek_id == gameweek_id)
    )
    pick_by_player = {str(p.player_id): p for p in picks_result.scalars().all()}

    members: list[GameweekMember] = []
    for player_id, display_name in roster.all():
        pick = pick_by_player.get(str(player_id))
        if pick is None:
            members.append(
                GameweekMember(
                    player_id=str(player_id),
                    display_name=display_name,
                    has_picked=False,
                    fixture_id=None,
                    home=None,
                    away=None,
                    competition=None,
                    market=None,
                    outcome=None,
                    runner_name=None,
                    odds=None,
                )
            )
            continue
        # A pick can reference a fixture that is no longer on this slate only if
        # the slate was rebuilt around it; fall back to null teams rather than
        # dropping the member from their own roster.
        fixture = fixture_by_id.get(str(pick.fixture_id))
        members.append(
            GameweekMember(
                player_id=str(player_id),
                display_name=display_name,
                has_picked=True,
                fixture_id=str(pick.fixture_id),
                home=fixture.home if fixture else None,
                away=fixture.away if fixture else None,
                competition=fixture.competition if fixture else None,
                market=pick.market.value,
                outcome=pick.outcome.value,
                runner_name=pick.runner_name,
                odds=float(pick.odds_at_pick),
            )
        )
    return members


async def _live_odds(
    provider: OddsProviderDep, event_ids: list[str], *, max_age_seconds: float
) -> tuple[dict[str, FixtureOdds], bool, frozenset[str]]:
    """Prices for the card, plus whether they came from a failed refresh.

    Best-effort on purpose. This used to call ``fetch_odds`` with no fallback, so any
    provider failure propagated and the core screen of the product — the one every
    member opens to make their pick — answered ``500``. Observed in production on
    2026-08-21, the day before launch, when ``/odds/multi`` returned ``429`` and the
    Football tab beside it kept working because it reads only the database.

    A stale price is a far better outcome than a broken screen, and a card with no
    prices at all still shows the fixtures. Freezing a price onto a pick is the
    opposite case and stays on ``fetch_odds`` (``routers/picks.py``).

    The third return is the set of events this call actually got a definite answer about
    (Batch 114). It is the *evidence* half of the response, as distinct from the prices:
    an event served from cache or lost to a failed refresh appears in neither, so nothing
    downstream can mistake "we did not ask" for "the bookmaker prices nothing".
    """
    if not event_ids:
        return {}, False, frozenset()
    snapshot = await provider.fetch_odds_best_effort(event_ids, max_age_seconds=max_age_seconds)
    return {o.provider_event_id: o for o in snapshot.odds}, snapshot.degraded, snapshot.observed


def _selection_options(
    fixture: Fixture,
    fixture_odds: FixtureOdds | None,
    taken: _TakenMap,
    my_id: object,
    scope: PickScope,
    fixture_holders: list[_Holder],
    offered: frozenset[str],
) -> list[SelectionOption]:
    """Price every offered selection and mark who, if anyone, holds it.

    ``offered`` is the league's market set: a selection whose market it does not offer
    is dropped, so the slate never shows a pick the submit endpoint would refuse with
    ``MARKET_NOT_OFFERED``.

    Under ``fixture`` scope a claim takes the whole game, so *every* selection on
    a claimed fixture reports that holder — otherwise the slate would offer
    selections the submit endpoint is bound to refuse with ``FIXTURE_TAKEN``.

    **The caller is not their own blocker.** Only a holder who is somebody *else*
    closes the game, exactly as ``_claim_conflict`` decides it (``holders - {player_id}``):
    a member owns the whole game, so moving between markets inside it is a re-pick, not
    a grab, and the API allows it. Reporting the caller as the holder of all six
    selections would contradict that in two ways — the client greys out anything already
    ``mine``, so the one member permitted to switch could not, and "my pick" is read back
    off the ``mine`` flags, so the banner would name whichever selection happened to be
    priced first rather than the one actually held. A fixture the caller holds therefore
    marks only the selection they really have; the fixture-level ``mine`` flag is what
    still says the game is theirs.

    Legacy rows make this more than a caller-side nicety: a league switched from
    ``selection`` to ``fixture`` scope keeps picks written under the old rule, so a
    fixture can genuinely have several holders. Naming the first — which may be the
    caller — would leave the game looking free to the very member the API refuses.
    """
    if fixture_odds is None:
        return []
    others = [holder for holder in fixture_holders if holder.player_id != str(my_id)]
    whole_fixture = others[0] if scope is PickScope.fixture and others else None

    options: list[SelectionOption] = []
    for selection in fixture_odds.selections:
        if selection.market.value not in offered:
            continue
        key = (str(fixture.id), selection.market.value, selection.outcome.value)
        # Whoever holds this exact selection outranks the fixture-level blocker, so a
        # caller looking at a game they share with somebody else still sees their own
        # pick as theirs. Reading `whole_fixture` first would hand every selection to
        # the other member, this caller's own included.
        holder = taken.get(key) or whole_fixture
        options.append(
            SelectionOption(
                market=selection.market.value,
                outcome=selection.outcome.value,
                runner_name=selection.runner_name,
                odds=float(selection.price),
                taken_by_player_id=holder.player_id if holder else None,
                taken_by_name=holder.name if holder else None,
                taken_at=holder.taken_at if holder else None,
                mine=holder is not None and holder.player_id == str(my_id),
            )
        )
    return options
