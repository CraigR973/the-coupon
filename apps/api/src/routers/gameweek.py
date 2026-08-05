"""The weekly pick screen — this Saturday's slate with live odds and taken selections.

``GET /api/v1/leagues/{slug}/gameweek/current`` returns the latest gameweek's fixtures,
each with the currently-priced selections, marking which are already grabbed in this
leaderboard (and which is the caller's own). It's a read view; grabbing happens via
``POST .../picks``.

The odds here come from the provider on every request, which is why the provider handed
out by ``deps.get_odds_provider`` caches: fifteen members refreshing this page must not
turn into fifteen upstream calls against a 100/hour quota.
"""

from datetime import date, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import CurrentUser
from src.database import get_db
from src.deps import LeagueMemberDep, OddsProviderDep
from src.models.fixture import Fixture
from src.models.league_membership import LeagueMembership
from src.models.pick import Pick
from src.models.profile import Profile
from src.services.gameweek import latest_gameweek
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
    mine: bool


class FixtureSlate(BaseModel):
    fixture_id: str
    provider_event_id: str
    home: str
    away: str
    competition: str
    kickoff_utc: datetime
    selections: list[SelectionOption]
    # Fixture-level "already picked" marker, alongside the per-selection one.
    # Several members can hold different selections on one game under the
    # current selection-level rule, so this is a list rather than a flag.
    taken_by_names: list[str]
    mine: bool


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
    market: str | None
    outcome: str | None
    runner_name: str | None
    odds: float | None


class GameweekSlateResponse(BaseModel):
    gameweek_id: str
    saturday_date: date
    status: str
    locks_at_utc: datetime
    fixtures: list[FixtureSlate]
    members: list[GameweekMember]
    members_missing_picks: int


@router.get("/{slug}/gameweek/current", response_model=GameweekSlateResponse)
async def current_gameweek(
    slug: str,
    player: CurrentUser,
    league: LeagueMemberDep,
    provider: OddsProviderDep,
    db: Db,
) -> GameweekSlateResponse:
    gameweek = await latest_gameweek(db)
    if gameweek is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No gameweek yet")

    fixtures_result = await db.execute(
        select(Fixture)
        .where(Fixture.gameweek_id == gameweek.id)
        .order_by(Fixture.kickoff_utc, Fixture.home)
    )
    fixtures = list(fixtures_result.scalars().all())

    taken = await _taken_selections(db, league.id, gameweek.id)
    odds_by_event = await _live_odds(provider, [f.provider_event_id for f in fixtures])

    holders_by_fixture = _holders_by_fixture(taken)
    slate = [
        FixtureSlate(
            fixture_id=str(fixture.id),
            provider_event_id=fixture.provider_event_id,
            home=fixture.home,
            away=fixture.away,
            competition=fixture.competition,
            kickoff_utc=fixture.kickoff_utc,
            selections=_selection_options(
                fixture, odds_by_event.get(fixture.provider_event_id), taken, player.id
            ),
            taken_by_names=[name for _, name in holders_by_fixture.get(str(fixture.id), [])],
            mine=any(
                pid == str(player.id) for pid, _ in holders_by_fixture.get(str(fixture.id), [])
            ),
        )
        for fixture in fixtures
    ]
    members = await _gameweek_members(db, league.id, gameweek.id, fixtures)
    return GameweekSlateResponse(
        gameweek_id=str(gameweek.id),
        saturday_date=gameweek.saturday_date,
        status=gameweek.status.value,
        locks_at_utc=gameweek.locks_at_utc,
        fixtures=slate,
        members=members,
        members_missing_picks=sum(1 for m in members if not m.has_picked),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

# key: (fixture_id, market_value, outcome_value) -> (player_id, player_name)
_TakenMap = dict[tuple[str, str, str], tuple[str, str]]


async def _taken_selections(db: AsyncSession, league_id: object, gameweek_id: object) -> _TakenMap:
    result = await db.execute(
        select(Pick, Profile.display_name)
        .join(Profile, Profile.id == Pick.player_id)
        .where(Pick.league_id == league_id, Pick.gameweek_id == gameweek_id)
    )
    taken: _TakenMap = {}
    for pick, display_name in result.all():
        key = (str(pick.fixture_id), pick.market.value, pick.outcome.value)
        taken[key] = (str(pick.player_id), display_name)
    return taken


def _holders_by_fixture(taken: _TakenMap) -> dict[str, list[tuple[str, str]]]:
    """Collapse the selection-keyed map to ``fixture_id -> [(player_id, name)]``.

    Distinct per player, because one member holding two selections on a fixture
    would otherwise be named twice — which the selection-level rule permits.
    """
    by_fixture: dict[str, list[tuple[str, str]]] = {}
    for (fixture_id, _, _), holder in taken.items():
        holders = by_fixture.setdefault(fixture_id, [])
        if holder not in holders:
            holders.append(holder)
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
                market=pick.market.value,
                outcome=pick.outcome.value,
                runner_name=pick.runner_name,
                odds=float(pick.odds_at_pick),
            )
        )
    return members


async def _live_odds(provider: OddsProviderDep, event_ids: list[str]) -> dict[str, FixtureOdds]:
    if not event_ids:
        return {}
    odds = await provider.fetch_odds(event_ids)
    return {o.provider_event_id: o for o in odds}


def _selection_options(
    fixture: Fixture,
    fixture_odds: FixtureOdds | None,
    taken: _TakenMap,
    my_id: object,
) -> list[SelectionOption]:
    if fixture_odds is None:
        return []
    options: list[SelectionOption] = []
    for selection in fixture_odds.selections:
        key = (str(fixture.id), selection.market.value, selection.outcome.value)
        holder = taken.get(key)
        options.append(
            SelectionOption(
                market=selection.market.value,
                outcome=selection.outcome.value,
                runner_name=selection.runner_name,
                odds=float(selection.price),
                taken_by_player_id=holder[0] if holder else None,
                taken_by_name=holder[1] if holder else None,
                mine=holder is not None and holder[0] == str(my_id),
            )
        )
    return options
