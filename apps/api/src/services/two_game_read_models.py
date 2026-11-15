"""Price-free group cards, independently scored fantasy cards and exact legacy links."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from src.schemas import UtcDatetime
from src.services.dues import RoundFeeStatus
from src.services.weekly_fees import WeekFee


class GameCard(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    game_id: uuid.UUID
    format: Literal["two_game"] = "two_game"
    week_label: date
    week_number: str
    destination: str
    opens_at: UtcDatetime
    locks_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    entry_state: str
    purpose: Literal["entry", "results", "upcoming"]
    coverage_state: str
    result_version: int
    archived: bool = False
    fee: WeekFee


class GroupCard(GameCard):
    game_kind: Literal["group"] = "group"
    progress: dict[str, int | bool]
    my_entry: dict[str, Any]
    result: dict[str, Any]


class FantasyCard(GameCard):
    game_kind: Literal["fantasy"] = "fantasy"
    progress: dict[str, int | bool]
    slots: list[dict[str, Any]]
    result: dict[str, Any]
    members: list[dict[str, Any]]
    winner_ids: list[str]


AddressedCard = Annotated[GroupCard | FantasyCard, Field(discriminator="game_kind")]


class LegacyRoundCard(BaseModel):
    format: Literal["legacy"] = "legacy"
    league_id: uuid.UUID
    week_id: uuid.UUID
    starts_on: date
    week_number: str
    destination: str
    status: str
    picks_open_at: UtcDatetime | None
    locks_at: UtcDatetime
    can_pick: bool
    picked_count: int
    archived: bool = False
    my_pick: dict[str, Any] | None
    fee: RoundFeeStatus | None


class WeeklyForm(BaseModel):
    week_id: uuid.UUID
    week_label: date
    format: Literal["legacy", "two_game"]
    game_kind: Literal["legacy", "fantasy"]
    destination: str
    status: str
    weekly_points: int
    slots_filled: int


class LeagueGames(BaseModel):
    league_id: uuid.UUID
    slug: str
    name: str
    two_games_enabled: bool
    suspended: bool
    next_game_state: Literal["known", "pending"]
    next_game_opens_at: UtcDatetime | None
    calendar_state: str | None
    server_now: UtcDatetime
    season: int
    season_stats: dict[str, Any] | None
    weekly_form: list[WeeklyForm]
    games: list[AddressedCard]
    legacy_rounds: list[LegacyRoundCard]
    next_cursor: str | None


class HomeGames(BaseModel):
    leagues: list[LeagueGames]


class WeekResults(BaseModel):
    league_id: uuid.UUID
    week_id: uuid.UUID
    week_label: date
    format: Literal["legacy", "two_game"]
    group: GroupCard | None = None
    fantasy: FantasyCard | None = None
    legacy: dict[str, Any] | None = None
