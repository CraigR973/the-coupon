"""Calendar-only preparation. Billing and provider availability never decide a week."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.gameweek import Gameweek
from src.models.league import League
from src.models.two_game import ConfirmedBreak, ProviderWork, TwoGame, TwoGameRollout
from src.services.provider_work import enqueue
from src.services.two_game_storage import LONDON, ensure_two_game_week, london_utc, rollout_for


def football_saturday(now: datetime) -> date:
    local = (
        now.replace(tzinfo=UTC).astimezone(LONDON) if now.tzinfo is None else now.astimezone(LONDON)
    )
    return local.date() + timedelta(days=5 - local.weekday())


def fantasy_opening(label: date, breaks: set[date]) -> datetime:
    previous = label - timedelta(days=7)
    while previous in breaks:
        previous -= timedelta(days=7)
    return london_utc(previous, 12)


def game_schedule(
    kind: str, label: date, league: League, breaks: set[date], now: datetime
) -> tuple[datetime, datetime, datetime, datetime]:
    if label.weekday() != 5:
        raise ValueError("two-game label must be Saturday")
    if kind == "fantasy":
        return (
            fantasy_opening(label, breaks),
            london_utc(label, 12),
            london_utc(label, 12, 30),
            london_utc(label + timedelta(days=2)),
        )
    if kind != "group":
        raise ValueError("unknown game kind")
    kickoff, lock = london_utc(label, 15), london_utc(label, 14, 30)
    offset = league.pick_open_offset_minutes
    if offset is None:
        # A late discovery records a locked, never-opened child. It cannot invent a
        # playable period before its actual creation time.
        opening = min(now, lock)
    else:
        local = datetime.combine(label, datetime.min.time()).replace(hour=15, tzinfo=LONDON)
        opening = (local - timedelta(minutes=offset)).astimezone(UTC).replace(tzinfo=None)
        if opening > lock:
            raise ValueError("group opening policy is later than Saturday 14:30")
    return opening, lock, kickoff, kickoff


async def prepare_calendar(
    db: AsyncSession, now: datetime, *, lookahead: int = 12
) -> list[TwoGame]:
    """Prepare current/next plus any already actionable longer-offset group games.

    A bounded exhausted scan persists its continuation; empty provider data never
    enters this calculation. Existing actionable children are never capped/removed.
    Caller commits; there is no provider acquisition or I/O here.
    """
    from src.config import settings

    if not settings.two_games_enabled:
        return []
    if lookahead <= 0:
        raise ValueError("lookahead must be positive")
    leagues = list(
        await db.scalars(
            select(League)
            .join(TwoGameRollout, TwoGameRollout.league_id == League.id)
            .where(
                League.deleted_at.is_(None),
                TwoGameRollout.enabled.is_(True),
                TwoGameRollout.suspended.is_(False),
            )
            .order_by(League.id)
        )
    )
    games: list[TwoGame] = []
    anchor = football_saturday(now)
    for league in leagues:
        rollout = await db.get(TwoGameRollout, league.id)
        if rollout is None:
            continue
        breaks = set(
            await db.scalars(
                select(ConfirmedBreak.week_label).where(ConfirmedBreak.league_id == league.id)
            )
        )
        key = f"calendar:{league.id}"
        await enqueue(db, key=key, kind="calendar", payload={}, next_at=now)
        progress = await db.get(ProviderWork, key, with_for_update=True)
        if progress is None:
            raise RuntimeError("calendar progress disappeared")
        start = max(anchor, rollout.first_week)
        if progress.payload.get("state") == "horizon_pending" and progress.cursor:
            start = max(start, date.fromisoformat(progress.cursor))
        labels: list[date] = []
        for index in range(lookahead):
            label = start + timedelta(weeks=index)
            if label in breaks:
                continue
            # The first two known eligible cards are a minimum, not a visibility cap.
            group_open = game_schedule("group", label, league, breaks, now)[0]
            long_offset = league.pick_open_offset_minutes is not None and group_open <= now
            if len(labels) < 2 or long_offset:
                labels.append(label)
        next_label = start + timedelta(weeks=lookahead)
        progress.cursor = next_label.isoformat()
        more_groups = (
            league.pick_open_offset_minutes is not None
            and game_schedule("group", next_label, league, breaks, now)[0] <= now
        )
        progress.payload = {
            "state": "ready" if len(labels) >= 2 and not more_groups else "horizon_pending",
            "anchor": anchor.isoformat(),
            "scanned_from": start.isoformat(),
            "scanned_saturdays": lookahead,
        }
        conflicts: list[str] = []
        for label in labels:
            if await rollout_for(db, league.id, label) is None:
                continue
            # A pre-existing legacy Saturday, including mixed-format W0, remains owned
            # by its original format and does not become a third entry surface.
            prior = await db.scalar(
                select(Gameweek).where(Gameweek.league_id == league.id, Gameweek.starts_on == label)
            )
            if prior is not None and prior.format == "legacy":
                conflicts.append(f"legacy_week:{prior.id}")
                continue
            parent = await ensure_two_game_week(db, league.id, label)
            if parent is None:
                continue
            for kind in ("group", "fantasy"):
                schedule = game_schedule(kind, label, league, breaks, now)
                child = await db.scalar(
                    select(TwoGame).where(TwoGame.week_id == parent.id, TwoGame.kind == kind)
                )
                if child is None:
                    child = TwoGame(
                        league_id=league.id,
                        week_id=parent.id,
                        kind=kind,
                        opens_at=schedule[0],
                        locks_at=schedule[1],
                        window_start=schedule[2],
                        window_end=schedule[3],
                    )
                    db.add(child)
                    await db.flush()
                elif (
                    (kind != "group" or league.pick_open_offset_minutes is not None)
                    and child.opens_at != schedule[0]
                ) or (child.locks_at, child.window_start, child.window_end) != schedule[1:]:
                    conflicts.append(str(child.id))
                if child.status not in ("settled", "cancelled"):
                    child.status = (
                        "locked"
                        if now >= child.locks_at
                        else "open"
                        if now >= child.opens_at
                        else "scheduled"
                    )
                games.append(child)
        # A later confirmed break can conflict with an already announced future game,
        # including one outside this pass. Retain the game and its accepted history.
        stored = list(
            await db.scalars(
                select(TwoGame)
                .join(Gameweek, Gameweek.id == TwoGame.week_id)
                .where(TwoGame.league_id == league.id, TwoGame.locks_at >= now)
            )
        )
        for child in stored:
            label = child.locks_at.replace(tzinfo=UTC).astimezone(LONDON).date()
            if label in breaks or (
                child.kind == "fantasy" and child.opens_at != fantasy_opening(label, breaks)
            ):
                conflicts.append(str(child.id))
        if conflicts:
            progress.payload = {
                **progress.payload,
                "state": "schedule_conflict",
                "conflicting_game_ids": sorted(set(conflicts)),
            }
    # Preserve every other stored child, including long announced windows. A missed
    # scheduler run repairs labels using the same stored instants as entry admission.
    for child in await db.scalars(
        select(TwoGame)
        .join(TwoGameRollout, TwoGameRollout.league_id == TwoGame.league_id)
        .where(
            TwoGameRollout.enabled.is_(True),
            TwoGameRollout.suspended.is_(False),
            TwoGame.status.in_(("scheduled", "open", "locked")),
        )
    ):
        child.status = (
            "locked" if now >= child.locks_at else "open" if now >= child.opens_at else "scheduled"
        )
    return games
