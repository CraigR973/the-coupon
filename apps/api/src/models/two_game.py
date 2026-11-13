"""Inactive two-game persistence. Legacy picks and their identifiers stay untouched."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class TwoGameRollout(Base):
    __tablename__ = "two_game_rollouts"
    __table_args__ = (
        CheckConstraint("extract(isodow from first_week) = 6", name="ck_rollout_saturday"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), primary_key=True)
    first_week: Mapped[date] = mapped_column(Date, nullable=False)
    effective_opening: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    suspended: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)


class TwoGame(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    __tablename__ = "two_games"
    __table_args__ = (
        ForeignKeyConstraint(["week_id", "league_id"], ["gameweeks.id", "gameweeks.league_id"]),
        UniqueConstraint("week_id", "kind", name="uq_two_games_week_kind"),
        UniqueConstraint("id", "league_id", "week_id", "kind", name="uq_two_games_owner"),
        Index("ix_two_games_week_league", "week_id", "league_id"),
        CheckConstraint("kind IN ('group', 'fantasy')", name="ck_two_games_kind"),
        CheckConstraint("opens_at <= locks_at", name="ck_two_games_open_before_lock"),
        CheckConstraint("window_start <= window_end", name="ck_two_games_window"),
        CheckConstraint(
            "status IN ('scheduled','open','locked','settled','cancelled')",
            name="ck_two_games_status",
        ),
        CheckConstraint(
            "coverage_state IN ('pending','unavailable','complete','confirmed_empty')",
            name="ck_two_games_coverage",
        ),
        Index("ix_two_games_league_lock", "league_id", "locks_at"),
    )

    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    opens_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    locks_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(12), server_default="scheduled", nullable=False)
    coverage_state: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False
    )
    result_status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    result_version: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime)


class TwoGameFixture(Base):
    __tablename__ = "two_game_fixtures"
    __table_args__ = (Index("ix_two_game_fixtures_fixture", "fixture_id"),)

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("two_games.id"), primary_key=True)
    fixture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fixtures.id"), primary_key=True)


class _EntryFields:
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(24), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    runner_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(8), server_default="pending", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


def _entry_constraints(kind: str) -> tuple[Any, ...]:
    return (
        ForeignKeyConstraint(
            ["game_id", "league_id", "week_id", "game_kind"],
            ["two_games.id", "two_games.league_id", "two_games.week_id", "two_games.kind"],
        ),
        ForeignKeyConstraint(
            ["game_id", "fixture_id"],
            ["two_game_fixtures.game_id", "two_game_fixtures.fixture_id"],
        ),
        ForeignKeyConstraint(
            ["league_id", "player_id"],
            ["league_memberships.league_id", "league_memberships.player_id"],
        ),
        CheckConstraint(f"game_kind = '{kind}'", name=f"ck_{kind}_pick_kind"),
        CheckConstraint(
            "(market = 'MATCH_ODDS' AND outcome IN ('HOME','DRAW','AWAY')) OR "
            "(market = 'BOTH_TEAMS_TO_SCORE' AND outcome IN ('YES','NO'))",
            name=f"ck_{kind}_pick_selection",
        ),
        CheckConstraint("status IN ('pending','won','lost','void')", name=f"ck_{kind}_pick_status"),
        CheckConstraint("revision >= 1", name=f"ck_{kind}_pick_revision"),
        Index(f"ix_{kind}_picks_owner", "game_id", "league_id", "week_id", "game_kind"),
        Index(f"ix_{kind}_picks_game_fixture", "game_id", "fixture_id"),
        Index(f"ix_{kind}_picks_member", "league_id", "player_id"),
        Index(f"ix_{kind}_picks_player", "player_id"),
        Index(f"ix_{kind}_picks_fixture", "fixture_id"),
    )


class GroupPick(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin, _EntryFields):
    __tablename__ = "group_picks"
    __table_args__ = (
        *_entry_constraints("group"),
        UniqueConstraint("week_id", "player_id", name="uq_group_pick_member"),
        UniqueConstraint("week_id", "fixture_id", name="uq_group_pick_fixture"),
    )
    game_kind: Mapped[str] = mapped_column(String(8), server_default="group", nullable=False)


class FantasyPick(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin, _EntryFields):
    __tablename__ = "fantasy_picks"
    __table_args__ = (
        *_entry_constraints("fantasy"),
        UniqueConstraint("week_id", "player_id", "slot", name="uq_fantasy_pick_slot"),
        UniqueConstraint("week_id", "player_id", "fixture_id", name="uq_fantasy_pick_fixture"),
        CheckConstraint("slot BETWEEN 1 AND 6", name="ck_fantasy_pick_slot"),
        CheckConstraint("frozen_odds > 0", name="ck_fantasy_pick_price"),
        CheckConstraint("points_awarded IS NULL OR points_awarded >= 0", name="ck_fantasy_points"),
    )
    game_kind: Mapped[str] = mapped_column(String(8), server_default="fantasy", nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_odds: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    quoted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False)
    points_awarded: Mapped[int | None] = mapped_column(Integer)


class MembershipInterval(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "membership_intervals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["league_id", "player_id"],
            ["league_memberships.league_id", "league_memberships.player_id"],
        ),
        UniqueConstraint("id", "league_id", "player_id", name="uq_membership_interval_owner"),
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name="ck_membership_interval"),
        Index("ix_membership_intervals_member", "league_id", "player_id"),
        Index(
            "uq_membership_intervals_active",
            "league_id",
            "player_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
    )
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime)
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)


class WeeklyFeeObligation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "weekly_fee_obligations"
    __table_args__ = (
        ForeignKeyConstraint(["week_id", "league_id"], ["gameweeks.id", "gameweeks.league_id"]),
        ForeignKeyConstraint(
            ["interval_id", "league_id", "player_id"],
            [
                "membership_intervals.id",
                "membership_intervals.league_id",
                "membership_intervals.player_id",
            ],
        ),
        UniqueConstraint("league_id", "player_id", "week_label", name="uq_weekly_fee_member_week"),
        UniqueConstraint("week_id", "player_id", name="uq_weekly_fee_parent_member"),
        CheckConstraint("amount_pence = 100", name="ck_weekly_fee_amount"),
        CheckConstraint("billing_start < billing_end", name="ck_weekly_fee_interval"),
        CheckConstraint("extract(isodow from week_label) = 6", name="ck_weekly_fee_label"),
        Index("ix_weekly_fee_interval", "interval_id", "league_id", "player_id"),
        Index("ix_weekly_fee_week_league", "week_id", "league_id"),
    )
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_label: Mapped[date] = mapped_column(Date, nullable=False)
    interval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ledger_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ledger_entries.id"), unique=True)
    amount_pence: Mapped[int] = mapped_column(Integer, server_default="100", nullable=False)
    billing_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    billing_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    owed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("now()"))


class ProviderAttempt(Base, UUIDPrimaryKeyMixin):
    """A committed reservation remains spent even if dispatch/response is uncertain."""

    __tablename__ = "provider_attempts"
    __table_args__ = (Index("ix_provider_attempts_meter_time", "meter", "reserved_at"),)
    meter: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ProviderControl(Base):
    __tablename__ = "provider_controls"
    meter: Mapped[str] = mapped_column(String(80), primary_key=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime)
    header_remaining: Mapped[int | None] = mapped_column(Integer)
    header_reset_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_clock_at: Mapped[datetime | None] = mapped_column(DateTime)


class ProviderRefusal(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "provider_refusals"
    __table_args__ = (Index("ix_provider_refusals_meter_time", "meter", "refused_at"),)
    meter: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    refused_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    retry_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)


class ProviderSnapshot(Base):
    __tablename__ = "provider_snapshots"
    __table_args__ = (Index("ix_provider_snapshots_fixture", "fixture_id"),)
    key: Mapped[str] = mapped_column(String(240), primary_key=True)
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixtures.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    negative_recheck_at: Mapped[datetime | None] = mapped_column(DateTime)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ProviderWork(Base):
    __tablename__ = "provider_work"
    __table_args__ = (
        Index("ix_provider_work_due", "kind", "next_at", "key"),
        Index("ix_provider_work_fixture", "fixture_id"),
    )
    key: Mapped[str] = mapped_column(String(240), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixtures.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(240))
    next_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(200))


class GameOperation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "two_game_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "league_id", "week_id", "game_kind"],
            ["two_games.id", "two_games.league_id", "two_games.week_id", "two_games.kind"],
        ),
        UniqueConstraint(
            "player_id",
            "league_id",
            "week_id",
            "game_kind",
            "slot",
            "operation_id",
            name="uq_two_game_operations_target",
        ),
        CheckConstraint(
            "(game_kind = 'group' AND slot = 0) OR "
            "(game_kind = 'fantasy' AND slot BETWEEN 1 AND 6)",
            name="ck_two_game_operations_slot",
        ),
        Index("ix_two_game_operations_owner", "game_id", "league_id", "week_id", "game_kind"),
    )
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    game_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False, index=True
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class TwoGameEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "two_game_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["game_id", "league_id", "week_id", "game_kind"],
            ["two_games.id", "two_games.league_id", "two_games.week_id", "two_games.kind"],
        ),
        UniqueConstraint("game_id", "kind", "version", name="uq_two_game_events_version"),
        Index("ix_two_game_events_owner", "game_id", "league_id", "week_id", "game_kind"),
        Index("ix_two_game_events_league", "league_id"),
        CheckConstraint(
            "game_kind <> 'group' OR NOT (payload ?| ARRAY['odds','points','combined_odds'])",
            name="ck_two_game_group_event_unpriced",
        ),
    )
    game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    week_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    game_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConfirmedBreak(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "two_game_breaks"
    __table_args__ = (
        UniqueConstraint("league_id", "week_label", name="uq_two_game_break_week"),
        CheckConstraint("length(evidence) > 0", name="ck_two_game_break_evidence"),
    )
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    week_label: Mapped[date] = mapped_column(Date, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False, index=True
    )


TABLE_NAMES = (
    "two_game_rollouts",
    "two_games",
    "two_game_fixtures",
    "group_picks",
    "fantasy_picks",
    "membership_intervals",
    "weekly_fee_obligations",
    "provider_attempts",
    "provider_controls",
    "provider_snapshots",
    "provider_work",
    "provider_refusals",
    "two_game_operations",
    "two_game_events",
    "two_game_breaks",
)
