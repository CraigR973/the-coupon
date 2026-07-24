"""Unit tests for the auto result-fetch job (Phase 5.3).

These tests run without a database; the session is a MagicMock that
records the in-memory mutations the sync routine applies. Postgres-only
behaviour (the row-level lock, the scoring trigger) is exercised in the
integration job that runs against a real database in CI.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.match import Match, MatchStatus, ResultSource
from src.models.notification import (
    ActionType,
    ActorType,
    AuditLog,
    NotificationLog,
)
from src.models.team import TournamentStage
from src.services import result_sync
from src.services.football_data import (
    FDMatch,
    FDMatchesResponse,
    FDMatchStatus,
    FDScore,
    FDScoreLine,
    FDTeam,
    FootballDataServerError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 6, 11, 18, 30, 0)


def _make_match(
    *,
    fd_id: int = 419665,
    status: MatchStatus = MatchStatus.locked,
    stage: TournamentStage = TournamentStage.group,
    kickoff: datetime | None = None,
    result_source: ResultSource | None = None,
    result_finalized_at: datetime | None = None,
    original_kickoff: datetime | None = None,
    home_team_id: uuid.UUID | None = None,
    away_team_id: uuid.UUID | None = None,
) -> MagicMock:
    m = MagicMock(spec=Match)
    m.id = uuid.uuid4()
    m.stage = stage
    m.football_data_match_id = fd_id
    m.status = status
    m.match_number = 1
    m.kickoff_utc = kickoff or _now() - timedelta(minutes=30)
    m.original_kickoff_utc = original_kickoff
    m.locked_at = None
    m.home_team_id = home_team_id
    m.away_team_id = away_team_id
    m.home_team_placeholder = None
    m.away_team_placeholder = None
    m.actual_home_score = None
    m.actual_away_score = None
    m.extra_time = False
    m.penalties = False
    m.penalty_winner_id = None
    m.extra_time_home_score = None
    m.extra_time_away_score = None
    m.penalty_home_score = None
    m.penalty_away_score = None
    m.result_source = result_source
    m.result_finalized_at = result_finalized_at
    m.result_entered_by = None
    m.last_synced_at = None
    m.deleted_at = None
    return m


def _fd_match(
    *,
    fd_id: int = 419665,
    status: FDMatchStatus = FDMatchStatus.FINISHED,
    stage: str = "GROUP_STAGE",
    utc_date: datetime | None = None,
    home_score: int | None = 2,
    away_score: int | None = 1,
    duration: str = "REGULAR",
    winner: str | None = None,
    regular_home: int | None = None,
    regular_away: int | None = None,
    et_home: int | None = None,
    et_away: int | None = None,
    pen_home: int | None = None,
    pen_away: int | None = None,
    home_team_id: int | None = 1,
    away_team_id: int | None = 2,
    home_tla: str | None = "HOM",
    away_tla: str | None = "AWY",
    home_name: str | None = "Home",
    away_name: str | None = "Away",
) -> FDMatch:
    return FDMatch(
        id=fd_id,
        utcDate=utc_date or datetime(2026, 6, 11, 18, 0, 0, tzinfo=UTC),
        status=status,
        stage=stage,
        group="GROUP_A",
        homeTeam=FDTeam(id=home_team_id, name=home_name, tla=home_tla),
        awayTeam=FDTeam(id=away_team_id, name=away_name, tla=away_tla),
        score=FDScore(
            winner=winner,
            duration=duration,
            fullTime=FDScoreLine(home=home_score, away=away_score),
            regularTime=(
                FDScoreLine(home=regular_home, away=regular_away)
                if regular_home is not None or regular_away is not None
                else None
            ),
            extraTime=(
                FDScoreLine(home=et_home, away=et_away)
                if et_home is not None or et_away is not None
                else None
            ),
            penalties=(
                FDScoreLine(home=pen_home, away=pen_away)
                if pen_home is not None or pen_away is not None
                else None
            ),
        ),
    )


def _make_team(*, code: str, fd_team_id: int | None = None) -> MagicMock:
    team = MagicMock()
    team.id = uuid.uuid4()
    team.code = code
    team.football_data_team_id = fd_team_id
    return team


def _scalars(items: list[Any]) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = items[0] if items else None
    r.scalars.return_value.all.return_value = items
    return r


def _orient(match: MagicMock, fd: FDMatch, *, mode: str = "aligned") -> MagicMock:
    """Return the ``_scalars`` result that ``_resolve_orientation``'s team-load
    query replays, with the loaded teams shaped to the requested orientation.

    Appended to a session factory's execute queue after the match-resolve result:
    ``_mock_session_factory([_scalars([match]), _orient(match, fd)])``.

    It preserves ``match``'s existing ``home_team_id``/``away_team_id`` (only
    filling them when unset), so a test that derived another field from them
    (e.g. ``penalty_winner_id = match.home_team_id``) keeps that identity intact —
    it points the loaded team rows at those ids instead of the reverse.

    ``mode``:
      * ``"aligned"``  — stored home/away match the feed's order (positional write).
      * ``"reversed"`` — stored home/away are the feed's away/home (swap on write).
      * ``"mismatch"`` — stored teams are neither of the feed's (fail-safe / audit).
    """
    if match.home_team_id is None:
        match.home_team_id = uuid.uuid4()
    if match.away_team_id is None:
        match.away_team_id = uuid.uuid4()

    if mode == "mismatch":
        # Two teams that match neither of the feed's, keyed to the stored ids.
        home = _make_team(code="XXX", fd_team_id=9911)
        away = _make_team(code="YYY", fd_team_id=9922)
    else:
        home = _make_team(code=fd.homeTeam.tla or "HOM", fd_team_id=fd.homeTeam.id)
        away = _make_team(code=fd.awayTeam.tla or "AWY", fd_team_id=fd.awayTeam.id)

    if mode == "reversed":
        # Our stored home is the feed's away team (and vice-versa).
        away.id, home.id = match.home_team_id, match.away_team_id
    else:
        home.id, away.id = match.home_team_id, match.away_team_id
    return _scalars([home, away])


def _mock_session_factory(execute_results: list[MagicMock]) -> tuple[MagicMock, AsyncMock]:
    """Build a session_factory whose session.execute replays the given results."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_results)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    class _Ctx:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, *a: object) -> None:
            return None

    factory = MagicMock(return_value=_Ctx())
    return factory, session


def _mock_client_factory(
    fd_matches: list[FDMatch] | None = None,
    raise_error: Exception | None = None,
) -> MagicMock:
    client = AsyncMock()
    if raise_error is not None:
        client.get_competition_matches = AsyncMock(side_effect=raise_error)
    else:
        client.get_competition_matches = AsyncMock(
            return_value=FDMatchesResponse(count=len(fd_matches or []), matches=fd_matches or [])
        )
    client.close = AsyncMock()
    return MagicMock(return_value=client)


@pytest.fixture(autouse=True)
def _reset_counter() -> None:
    result_sync.reset_failure_counter()


@pytest.fixture(autouse=True)
def _no_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        patch("src.services.result_sync.notify_result_detected", new_callable=AsyncMock),
        patch("src.services.result_sync.notify_kickoff_changed", new_callable=AsyncMock),
        patch("src.services.result_sync.notify_match_postponed", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_bracket_sync() -> Iterator[AsyncMock]:
    """Stub the knockout bracket resolver for every sync test.

    ``sync_results`` now calls ``sync_knockout_bracket`` after a finished
    result settles. The resolver issues several ``session.execute`` queries,
    which would exhaust this module's fixed mock ``execute`` side-effect queue,
    so it is patched to a no-op by default. Tests that assert on the call
    request this fixture and inspect the returned mock.
    """
    with patch("src.services.result_sync.sync_knockout_bracket", new_callable=AsyncMock) as mock:
        mock.return_value = 0
        yield mock


# ---------------------------------------------------------------------------
# FINISHED — new result
# ---------------------------------------------------------------------------


async def test_finished_match_writes_score_and_audit() -> None:
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 3
    assert match.actual_away_score == 1
    assert match.result_source == ResultSource.auto
    assert match.status == MatchStatus.completed
    assert match.result_entered_by is None
    assert match.result_finalized_at is not None  # anchors the self-heal window
    audit = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog))
    assert audit.actor_type == ActorType.system
    assert audit.action_type == ActionType.result_auto_fetched
    assert audit.target_id == match.id


# ---------------------------------------------------------------------------
# FINISHED — extra time / penalties: store the regulation score, not fullTime
# ---------------------------------------------------------------------------


async def test_finished_penalty_shootout_stores_regulation_score_and_advancer() -> None:
    """football-data's fullTime for a shootout is the aggregate (regulation +
    the shootout tally). We must store ``regularTime`` (the 90-minute score) and
    record the shootout winner as the advancer, or both the scoreline and the
    bracket go wrong (the 2026-06-30 Ger-Par / Ned-Mar prod incident)."""
    match = _make_match(
        status=MatchStatus.locked,
        stage=TournamentStage.r32,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_32",
        duration="PENALTY_SHOOTOUT",
        winner="AWAY_TEAM",
        home_score=4,  # fullTime aggregate = regulation 1 + pens 3
        away_score=5,  # fullTime aggregate = regulation 1 + pens 4
        regular_home=1,
        regular_away=1,
        pen_home=3,
        pen_away=4,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 1
    assert match.actual_away_score == 1
    assert match.extra_time is True
    assert match.penalties is True
    assert match.penalty_winner_id == match.away_team_id
    assert match.extra_time_home_score == 1  # regulation 1-1, goalless ET
    assert match.extra_time_away_score == 1
    assert match.penalty_home_score == 3
    assert match.penalty_away_score == 4
    assert match.result_source == ResultSource.auto


async def test_finished_extra_time_win_stores_regulation_score_and_advancer() -> None:
    """A knockout settled by an extra-time goal: ``regularTime`` is level but the
    match has a winner, so we still record the advancer from ``winner``."""
    match = _make_match(
        status=MatchStatus.locked,
        stage=TournamentStage.r16,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_16",
        duration="EXTRA_TIME",
        winner="HOME_TEAM",
        home_score=2,  # fullTime includes the extra-time goal
        away_score=1,
        regular_home=1,
        regular_away=1,
        et_home=1,  # the winning goal, scored in extra time
        et_away=0,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 1
    assert match.actual_away_score == 1
    assert match.extra_time is True
    assert match.penalties is False
    assert match.penalty_winner_id == match.home_team_id
    assert match.extra_time_home_score == 2  # regulation 1 + the extra-time goal
    assert match.extra_time_away_score == 1
    assert match.penalty_home_score is None
    assert match.penalty_away_score is None


async def test_finished_extra_time_with_lying_duration_derives_regulation_score() -> None:
    """Regression (Belgium–Senegal R32, 2026-07-01): in the minutes after full time
    football-data served an *inconsistent* payload — ``duration="REGULAR"`` and
    ``regularTime=null``, yet ``extraTime`` goals recorded and ``fullTime`` the ET
    aggregate (3-2). Trusting ``duration`` stored the aggregate as the 90-minute
    score, so every draw prediction was graded a loss. We must detect the extra
    time from the ``extraTime`` goals and back the regulation score out of
    ``fullTime`` (3-2 − 1-0 = 2-2)."""
    match = _make_match(
        status=MatchStatus.locked,
        stage=TournamentStage.r32,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_32",
        duration="REGULAR",  # the feed's lie — it really went to extra time
        winner="HOME_TEAM",
        home_score=3,  # fullTime aggregate = regulation 2 + extra-time 1
        away_score=2,  # fullTime aggregate = regulation 2 + extra-time 0
        regular_home=None,  # feed omitted the 90-minute breakdown
        regular_away=None,
        et_home=1,  # but recorded the extra-time goal
        et_away=0,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 2  # the 90-min draw, not the 3-2 aggregate
    assert match.actual_away_score == 2
    assert match.extra_time is True  # detected from extraTime goals, not duration
    assert match.penalties is False
    assert match.penalty_winner_id == match.home_team_id  # HOME advanced in ET
    assert match.extra_time_home_score == 3  # regulation 2 + the extra-time goal
    assert match.extra_time_away_score == 2
    assert match.penalty_home_score is None
    assert match.penalty_away_score is None


async def test_finished_regular_match_uses_fulltime_and_no_advancer() -> None:
    """Ordinary 90-minute matches: the feed omits ``regularTime``, so ``fullTime``
    is the real score and there is no penalty advancer to record."""
    match = _make_match(
        status=MatchStatus.locked,
        stage=TournamentStage.r32,
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_32",
        duration="REGULAR",
        winner="HOME_TEAM",
        home_score=2,
        away_score=1,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert match.actual_home_score == 2
    assert match.actual_away_score == 1
    assert match.extra_time is False
    assert match.penalties is False
    assert match.penalty_winner_id is None
    assert match.extra_time_home_score is None
    assert match.extra_time_away_score is None
    assert match.penalty_home_score is None
    assert match.penalty_away_score is None


async def test_live_extra_time_uses_regulation_score() -> None:
    """During extra time the running ``fullTime`` climbs past the 90-minute score;
    the in-play write must track ``regularTime`` so live grading matches the
    eventual final result."""
    match = _make_match(status=MatchStatus.live, stage=TournamentStage.r32)
    match.actual_home_score = 1
    match.actual_away_score = 0
    fd = _fd_match(
        status=FDMatchStatus.IN_PLAY,
        stage="LAST_32",
        duration="EXTRA_TIME",
        home_score=3,  # climbing aggregate — storing this would be the bug
        away_score=1,
        regular_home=1,
        regular_away=1,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert match.actual_home_score == 1
    assert match.actual_away_score == 1
    assert match.result_source is None  # not final yet


async def test_live_captures_extra_time_phase_for_display() -> None:
    """U64: while a knockout match is live and into extra time, _apply_live mirrors
    the AET scoreline into extra_time_*_score (for the dashboard's live caption)
    without setting penalty_winner_id or result_source — those stay for full-time."""
    match = _make_match(status=MatchStatus.live, stage=TournamentStage.r32)
    match.actual_home_score = 1
    match.actual_away_score = 1
    fd = _fd_match(
        status=FDMatchStatus.IN_PLAY,
        stage="LAST_32",
        duration="EXTRA_TIME",
        home_score=2,
        away_score=1,
        regular_home=1,
        regular_away=1,
        et_home=1,
        et_away=0,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.extra_time is True
    assert match.penalties is False
    assert match.extra_time_home_score == 2
    assert match.extra_time_away_score == 1
    assert match.penalty_winner_id is None
    assert match.result_source is None


async def test_live_captures_penalty_tally_for_display() -> None:
    """During a live shootout, the running penalty tally is mirrored for display
    even though the match (and the advancer pick) is not yet settled."""
    match = _make_match(status=MatchStatus.live, stage=TournamentStage.r32)
    match.actual_home_score = 1
    match.actual_away_score = 1
    match.extra_time = True
    match.extra_time_home_score = 1
    match.extra_time_away_score = 1
    fd = _fd_match(
        status=FDMatchStatus.IN_PLAY,
        stage="LAST_32",
        duration="PENALTY_SHOOTOUT",
        home_score=1,
        away_score=1,
        regular_home=1,
        regular_away=1,
        et_home=0,
        et_away=0,
        pen_home=3,
        pen_away=2,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.penalties is True
    assert match.penalty_home_score == 3
    assert match.penalty_away_score == 2
    assert match.penalty_winner_id is None
    assert match.result_source is None


# ---------------------------------------------------------------------------
# Orientation reconciliation (U65) — a stored home/away that disagrees with the
# feed must never persist the scoreline backwards or advance the wrong team.
# ---------------------------------------------------------------------------


async def test_aligned_finished_writes_positionally() -> None:
    """The ALIGNED path — every current fixture, including the re-oriented m95 — is
    a pure no-op: the scoreline is written in feed order exactly as before U65."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd, mode="aligned")])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 3
    assert match.actual_away_score == 1


async def test_reversed_finished_stores_scoreline_in_our_orientation() -> None:
    """Feed order disagrees with our stored home/away: the 3-1 feed scoreline must
    be persisted as 1-3 so it lands on the team that actually scored the goals."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd, mode="reversed")])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 1  # feed away (1) is our home
    assert match.actual_away_score == 3  # feed home (3) is our away
    assert match.result_source == ResultSource.auto
    assert match.status == MatchStatus.completed


async def test_reversed_finished_penalty_winner_mapped_by_identity() -> None:
    """A reversed knockout: every score tuple is swapped into our orientation and
    the shootout winner is mapped to a team id by identity, never positionally."""
    match = _make_match(status=MatchStatus.locked, stage=TournamentStage.r32)
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_32",
        duration="PENALTY_SHOOTOUT",
        winner="AWAY_TEAM",  # the feed's away team won the shootout
        home_score=5,  # fullTime aggregate (regulation 2 + pens 3)
        away_score=5,  # fullTime aggregate (regulation 1 + pens 4)
        regular_home=2,
        regular_away=1,
        pen_home=3,
        pen_away=4,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd, mode="reversed")])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    # Feed regulation 2-1 stored as our 1-2; shootout tally 3-4 stored as our 4-3.
    assert match.actual_home_score == 1
    assert match.actual_away_score == 2
    assert match.extra_time is True
    assert match.penalties is True
    assert match.extra_time_home_score == 1  # ET base = regulation, goalless ET
    assert match.extra_time_away_score == 2
    assert match.penalty_home_score == 4
    assert match.penalty_away_score == 3
    # Feed AWAY_TEAM won → in our reversed orientation that is our HOME team.
    assert match.penalty_winner_id == match.home_team_id


async def test_reversed_live_swaps_running_score() -> None:
    """A reversed fixture's live in-play score is stored in our orientation too, so
    live grading matches the eventual final result."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=2, away_score=0)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd, mode="reversed")])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.status == MatchStatus.live
    assert match.actual_home_score == 0  # feed away (0) is our home
    assert match.actual_away_score == 2
    assert match.result_source is None


async def test_mismatch_finished_refuses_write_and_audits() -> None:
    """When the feed's teams match neither of ours, we refuse to write and log a
    sync_failed audit — a per-match anomaly, so the failure counter is untouched."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
    factory, session = _mock_session_factory(
        [_scalars([match]), _orient(match, fd, mode="mismatch")]
    )
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score is None  # nothing written
    assert match.actual_away_score is None
    assert match.result_source is None
    assert match.status == MatchStatus.locked
    audit = next(
        c.args[0]
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type == ActionType.sync_failed
    )
    assert audit.target_id == match.id
    assert audit.changes["reason"] == "orientation_mismatch"
    # Distinguishable from a feed-outage failure (which carries this key), so the
    # DB failure-recovery count never mistakes it for an outage.
    assert "consecutive_failures" not in audit.changes
    # No admin alert: a per-match data anomaly is not a feed outage.
    assert not [
        c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], NotificationLog)
    ]


async def test_unresolved_teams_finished_refuses_write_and_audits() -> None:
    """A knockout slot whose teams are still unresolved placeholders (home_team_id
    NULL) can't be oriented, so we refuse to write and audit rather than guess."""
    match = _make_match(status=MatchStatus.locked, stage=TournamentStage.r16)
    # home_team_id / away_team_id left as None — the placeholder knockout slot.
    fd = _fd_match(status=FDMatchStatus.FINISHED, stage="LAST_16", home_score=2, away_score=0)
    # No team-load result queued: _resolve_orientation short-circuits on NULL ids.
    factory, session = _mock_session_factory([_scalars([match])])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score is None
    assert match.result_source is None
    audit = next(
        c.args[0]
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type == ActionType.sync_failed
    )
    assert audit.changes["reason"] == "orientation_mismatch"


async def test_repeated_mismatch_never_alerts_admins() -> None:
    """Three feed-outage failures alert admins; orientation mismatches must not —
    they never touch the consecutive-failure counter that gates the alert."""
    with patch("src.services.result_sync.notify_auto_sync_failed", new_callable=AsyncMock) as alert:
        for _ in range(result_sync._FAILURE_ALERT_THRESHOLD + 1):
            match = _make_match(status=MatchStatus.locked)
            fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
            factory, _ = _mock_session_factory(
                [_scalars([match]), _orient(match, fd, mode="mismatch")]
            )
            client_factory = _mock_client_factory([fd])
            await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    alert.assert_not_awaited()
    assert result_sync._consecutive_failures == 0


# ---------------------------------------------------------------------------
# Idempotency — no-op when result_source is already set
# ---------------------------------------------------------------------------


async def test_finished_match_with_existing_result_is_noop() -> None:
    match = _make_match(status=MatchStatus.completed, result_source=ResultSource.manual)
    match.actual_home_score = 1
    match.actual_away_score = 0
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=3, away_score=1)
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 1
    assert match.actual_away_score == 0
    assert match.result_source == ResultSource.manual
    # No match-level audit row (sync_triggered system row is expected even for noops).
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


# ---------------------------------------------------------------------------
# Self-heal window — an auto result may be revised while the feed settles
# ---------------------------------------------------------------------------


def _recent_now(minutes_ago: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes_ago)


def _corrected_et_payload() -> FDMatch:
    """The Belgium–Senegal result *after* football-data self-corrected: an
    extra-time win whose regulation score (the grading score) is a 2-2 draw."""
    return _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_32",
        duration="EXTRA_TIME",
        winner="HOME_TEAM",
        home_score=3,  # aggregate
        away_score=2,
        regular_home=2,  # the true 90-minute draw
        regular_away=2,
        et_home=1,
        et_away=0,
    )


async def test_auto_result_corrected_within_window(_no_bracket_sync: AsyncMock) -> None:
    """An auto result first stored wrong (the transient 3-2 aggregate) is revised
    to the true 2-2 draw when the feed corrects itself inside the window — silently
    (no re-notify), and the bracket resolver re-runs in case the advancer changed."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r32,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(5),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    # The bad first read: the ET aggregate, stored as if a clean 3-2 regulation win.
    match.actual_home_score = 3
    match.actual_away_score = 2
    match.extra_time = False
    finalized_before = match.result_finalized_at
    fd = _corrected_et_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    with patch(
        "src.services.result_sync.notify_result_detected", new_callable=AsyncMock
    ) as mock_notify:
        count = await result_sync.sync_results(
            session_factory=factory, client_factory=client_factory
        )

    assert count == 1
    assert match.actual_home_score == 2  # corrected to the 90-minute draw
    assert match.actual_away_score == 2
    assert match.extra_time is True
    assert match.penalty_winner_id == match.home_team_id
    assert match.extra_time_home_score == 3  # end-of-ET scoreline for display
    assert match.extra_time_away_score == 2
    # The window is anchored to the first finalization — a correction never extends it.
    assert match.result_finalized_at == finalized_before
    # Silent: no second "result is in!" push on a correction.
    mock_notify.assert_not_called()
    # Bracket re-resolves in case the advancer flipped.
    _no_bracket_sync.assert_awaited()
    audit = next(
        c.args[0]
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].changes.get("corrected")
    )
    assert audit.changes["previous_home_score"] == 3
    assert audit.changes["actual_home_score"] == 2


async def test_auto_result_frozen_after_window() -> None:
    """Past the window, a settled auto result is frozen — a late feed change is
    ignored so it can't reshuffle the leaderboard long after the fact."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r32,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(40),  # outside the 30-minute window
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 3
    match.actual_away_score = 2
    match.extra_time = False
    fd = _corrected_et_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 3  # unchanged — frozen
    assert match.actual_away_score == 2
    assert match.extra_time is False
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


async def test_auto_result_within_window_unchanged_is_noop() -> None:
    """Inside the window but the feed agrees with what we stored: no rewrite, no
    audit — the common case where the first read was already correct."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r32,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(5),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    # Already the corrected result.
    match.actual_home_score = 2
    match.actual_away_score = 2
    match.extra_time = True
    match.penalty_winner_id = match.home_team_id
    match.extra_time_home_score = 3
    match.extra_time_away_score = 2
    fd = _corrected_et_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 2
    assert match.actual_away_score == 2
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


async def test_manual_result_never_corrected_within_window() -> None:
    """A manual/override result is authoritative — the self-heal window never
    touches it, even if the feed disagrees inside the window."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r32,
        result_source=ResultSource.override,
        result_finalized_at=_recent_now(5),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 3
    match.actual_away_score = 2
    fd = _corrected_et_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 3
    assert match.result_source == ResultSource.override


# ---------------------------------------------------------------------------
# Incomplete-knockout self-heal — a level knockout with no advancer is impossible
# and stays revisable past the window until the feed backfills the decider
# (the Switzerland–Colombia R16 incident, 2026-07-08).
# ---------------------------------------------------------------------------


def _incomplete_knockout_payload() -> FDMatch:
    """A knockout football-data reports FINISHED *before* it has the shootout: a
    bare 0-0 with duration=REGULAR and no extraTime/penalties sub-scores — the
    payload that first froze Switzerland–Colombia as a plain 0-0."""
    return _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_16",
        home_score=0,
        away_score=0,
        duration="REGULAR",
        winner=None,
    )


def _shootout_decider_payload() -> FDMatch:
    """The same knockout after football-data backfills the shootout: 0-0 at 90'
    (and after extra time), HOME_TEAM winning 4-3 on penalties."""
    return _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_16",
        duration="PENALTY_SHOOTOUT",
        winner="HOME_TEAM",
        home_score=4,  # aggregate: 0 reg + 0 ET + 4 pens
        away_score=3,
        regular_home=0,
        regular_away=0,
        et_home=0,
        et_away=0,
        pen_home=4,
        pen_away=3,
    )


async def test_incomplete_knockout_corrected_after_window(_no_bracket_sync: AsyncMock) -> None:
    """A knockout first stored level 0-0 with no advancer (incomplete feed) is still
    corrected once the feed backfills the shootout — *even long past the 30-minute
    window* — because a level knockout with no advancer is an impossible result we
    keep open until the decider lands. Correcting only *adds* the advancer."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r16,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(60),  # long past the 30-minute window
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 0
    match.actual_away_score = 0  # the frozen-looking bare draw, no advancer
    fd = _shootout_decider_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    with patch(
        "src.services.result_sync.notify_result_detected", new_callable=AsyncMock
    ) as mock_notify:
        count = await result_sync.sync_results(
            session_factory=factory, client_factory=client_factory
        )

    assert count == 1
    assert match.actual_home_score == 0  # 90-minute score unchanged
    assert match.actual_away_score == 0
    assert match.extra_time is True
    assert match.penalties is True
    assert match.penalty_winner_id == match.home_team_id  # advancer finally set
    assert match.penalty_home_score == 4
    assert match.penalty_away_score == 3
    mock_notify.assert_not_called()  # silent correction, not a fresh result push
    _no_bracket_sync.assert_awaited()  # bracket re-resolves so the QF slot fills
    audit = next(
        c.args[0]
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].changes.get("corrected")
    )
    assert audit.changes["actual_home_score"] == 0


async def test_incomplete_knockout_still_incomplete_after_window_is_noop() -> None:
    """While the feed still lacks the decider, re-reading the incomplete knockout is
    a clean no-op (no rewrite, no audit): the freeze is lifted but there is nothing
    to apply yet, so it never churns — it simply keeps watching for the backfill."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r16,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(60),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 0
    match.actual_away_score = 0
    fd = _incomplete_knockout_payload()
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.penalty_winner_id is None  # still no advancer — nothing to apply
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


async def test_group_draw_frozen_after_window() -> None:
    """The relaxation is knockout-only: a group-stage draw is a legitimate final
    result, so past the window it freezes normally and a late feed revision is
    ignored — the knockout exception must not leak to the group stage."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.group,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(60),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 1
    match.actual_away_score = 1
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="GROUP_STAGE",
        home_score=2,
        away_score=2,  # a late revision we must ignore
    )
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 1  # frozen — unchanged
    assert match.actual_away_score == 1


async def test_knockout_with_advancer_frozen_after_window() -> None:
    """Once the advancer is known the knockout is complete, so the exception no
    longer applies: past the window it freezes like any other result. Pins that the
    relaxation keys on a *missing* advancer, not merely a level scoreline."""
    match = _make_match(
        status=MatchStatus.completed,
        stage=TournamentStage.r16,
        result_source=ResultSource.auto,
        result_finalized_at=_recent_now(60),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
    )
    match.actual_home_score = 1
    match.actual_away_score = 1
    match.penalty_winner_id = match.home_team_id  # already decided
    # A late feed that would flip the advancer to the away team, were we not frozen.
    fd = _fd_match(
        status=FDMatchStatus.FINISHED,
        stage="LAST_16",
        duration="PENALTY_SHOOTOUT",
        winner="AWAY_TEAM",
        home_score=5,
        away_score=6,
        regular_home=1,
        regular_away=1,
        et_home=0,
        et_away=0,
        pen_home=4,
        pen_away=5,
    )
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.penalty_winner_id == match.home_team_id  # frozen — advancer unchanged


# ---------------------------------------------------------------------------
# Race condition — admin manual entry between rows
# ---------------------------------------------------------------------------


async def test_race_with_manual_entry_skipped() -> None:
    """If a manual entry won the row-lock race, we observe result_source != None."""
    match = _make_match(status=MatchStatus.completed, result_source=ResultSource.override)
    match.actual_home_score = 2
    match.actual_away_score = 2
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=4, away_score=0)
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    # Admin's override stands.
    assert match.result_source == ResultSource.override
    assert match.actual_home_score == 2


# ---------------------------------------------------------------------------
# POSTPONED + CANCELLED + IN_PLAY status deltas
# ---------------------------------------------------------------------------


async def test_postponed_transitions_status_and_audits() -> None:
    match = _make_match(status=MatchStatus.scheduled)
    fd = _fd_match(status=FDMatchStatus.POSTPONED, home_score=None, away_score=None)
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.status == MatchStatus.postponed
    audit = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog))
    assert audit.action_type == ActionType.match_postponed
    assert audit.actor_type == ActorType.system


async def test_cancelled_transitions_status() -> None:
    match = _make_match(status=MatchStatus.scheduled)
    fd = _fd_match(status=FDMatchStatus.CANCELLED, home_score=None, away_score=None)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert match.status == MatchStatus.cancelled


async def test_in_play_transitions_locked_to_live() -> None:
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=None, away_score=None)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.status == MatchStatus.live


async def test_live_status_transitions_locked_to_live_and_writes_score() -> None:
    """football-data's "LIVE" status is handled exactly like IN_PLAY.

    Regression for the 2026-07-01 prod incident: the feed reported status="LIVE"
    for an in-progress match, a value that was neither modelled nor in
    ``_LIVE_STATUSES``, so the match never flipped to live and its score never
    synced.
    """
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.LIVE, home_score=0, away_score=1)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.status == MatchStatus.live
    assert match.actual_home_score == 0
    assert match.actual_away_score == 1
    assert match.result_source is None  # not a final result yet


async def test_in_play_writes_live_score() -> None:
    """U63: a live match writes the running in-play score so predictions and the
    leaderboard update during the match — result_source stays NULL (not final)."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=1, away_score=0)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.status == MatchStatus.live
    assert match.actual_home_score == 1
    assert match.actual_away_score == 0
    assert match.result_source is None  # not a final result yet


async def test_in_play_without_score_does_not_write_score() -> None:
    """Pre-kickoff / no-data ticks report fullTime=null — we must not fabricate
    a 0-0 (that is the bug U54 guarded against on the frontend)."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=None, away_score=None)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1  # still transitioned locked → live
    assert match.status == MatchStatus.live
    assert match.actual_home_score is None
    assert match.actual_away_score is None


async def test_in_play_already_live_updates_changed_score() -> None:
    """A goal during an already-live match must be written — the old _apply_live
    returned early when status was already live and never updated the score."""
    match = _make_match(status=MatchStatus.live)
    match.actual_home_score = 0
    match.actual_away_score = 0
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=1, away_score=0)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert match.actual_home_score == 1
    assert match.actual_away_score == 0


async def test_in_play_already_live_unchanged_score_is_noop() -> None:
    """A sync tick where the score has not moved is a no-op (no re-write), so the
    DB trigger's IS DISTINCT FROM guard never sees a spurious change."""
    match = _make_match(status=MatchStatus.live)
    match.actual_home_score = 1
    match.actual_away_score = 0
    fd = _fd_match(status=FDMatchStatus.IN_PLAY, home_score=1, away_score=0)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.actual_home_score == 1
    assert match.actual_away_score == 0


# ---------------------------------------------------------------------------
# Kickoff change — drift detection + lock-job re-registration
# ---------------------------------------------------------------------------


async def test_kickoff_change_updates_kickoff_and_preserves_original() -> None:
    original = datetime(2026, 6, 15, 18, 0, 0)
    new_kickoff = datetime(2026, 6, 15, 20, 0, 0)
    match = _make_match(status=MatchStatus.scheduled, kickoff=original)
    fd = _fd_match(
        status=FDMatchStatus.TIMED,
        utc_date=new_kickoff.replace(tzinfo=UTC),
        home_score=None,
        away_score=None,
    )
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    # The periodic lock_due_matches job is the lock-job mechanism — it
    # picks up the new kickoff_utc on its next tick. That is the
    # "re-registration" path: we update the DB row only.
    assert match.kickoff_utc == new_kickoff
    assert match.original_kickoff_utc == original
    audit = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog))
    assert audit.action_type == ActionType.kickoff_changed
    assert audit.changes is not None
    assert audit.changes["new_kickoff_utc"] == new_kickoff.isoformat()
    assert audit.changes["old_kickoff_utc"] == original.isoformat()


async def test_kickoff_unchanged_is_noop() -> None:
    kickoff = datetime(2026, 6, 15, 18, 0, 0)
    match = _make_match(status=MatchStatus.scheduled, kickoff=kickoff)
    fd = _fd_match(
        status=FDMatchStatus.TIMED,
        utc_date=kickoff.replace(tzinfo=UTC),
        home_score=None,
        away_score=None,
    )
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    assert match.kickoff_utc == kickoff
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


# ---------------------------------------------------------------------------
# Failure counter + admin alert
# ---------------------------------------------------------------------------


async def test_api_failure_increments_counter_and_writes_audit() -> None:
    # No admin profiles returned, so alert path inserts nothing for admins.
    factory, session = _mock_session_factory([_scalars([])])
    client_factory = _mock_client_factory(raise_error=FootballDataServerError("503: maintenance"))

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    audit = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog))
    assert audit.action_type == ActionType.sync_failed
    assert audit.actor_type == ActorType.system


async def test_three_consecutive_failures_alerts_admins() -> None:
    err = FootballDataServerError("503")

    for _ in range(2):
        factory, _ = _mock_session_factory([_scalars([])])
        client_factory = _mock_client_factory(raise_error=err)
        await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    # Third failure should trigger notify_auto_sync_failed.
    factory, _ = _mock_session_factory([_scalars([])])
    client_factory = _mock_client_factory(raise_error=err)
    _alert_patch = "src.services.result_sync.notify_auto_sync_failed"
    with patch(_alert_patch, new_callable=AsyncMock) as mock_alert:
        await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    mock_alert.assert_awaited_once()
    assert "503" in mock_alert.call_args.args[1]


async def test_successful_sync_resets_failure_counter() -> None:
    # Fail twice, then succeed → counter back to 0.
    err = FootballDataServerError("503")
    for _ in range(2):
        factory, _ = _mock_session_factory([_scalars([])])
        client_factory = _mock_client_factory(raise_error=err)
        await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    factory, _ = _mock_session_factory([_scalars([])])
    client_factory = _mock_client_factory([])
    await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    # Now another failure should be the *first* in a new streak, not the third.
    factory, session = _mock_session_factory([_scalars([])])
    client_factory = _mock_client_factory(raise_error=err)
    await result_sync.sync_results(session_factory=factory, client_factory=client_factory)
    notifications = [
        c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], NotificationLog)
    ]
    assert notifications == []


# ---------------------------------------------------------------------------
# Unknown match — silently skipped
# ---------------------------------------------------------------------------


async def test_unknown_fd_match_id_is_skipped() -> None:
    fd = _fd_match(status=FDMatchStatus.FINISHED)
    factory, session = _mock_session_factory([_scalars([]), _scalars([])])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 0
    # No match-level audit rows for unknown matches (sync_triggered system row is expected).
    assert not [
        c
        for c in session.add.call_args_list
        if isinstance(c.args[0], AuditLog) and c.args[0].action_type != ActionType.sync_triggered
    ]


async def test_unknown_fd_match_id_backfills_ids_via_team_codes() -> None:
    home_team = _make_team(code="HOM")
    away_team = _make_team(code="AWY")
    match = _make_match(
        fd_id=None,
        status=MatchStatus.locked,
        stage=TournamentStage.group,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
    )
    fd = _fd_match(
        fd_id=998877,
        status=FDMatchStatus.FINISHED,
        stage="GROUP_STAGE",
        home_team_id=11,
        away_team_id=22,
        home_tla="HOM",
        away_tla="AWY",
    )
    factory, _ = _mock_session_factory(
        [
            _scalars([]),
            _scalars([home_team, away_team]),
            _scalars([match]),
            _scalars([home_team, away_team]),  # _resolve_orientation team-load (aligned)
        ]
    )
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    assert home_team.football_data_team_id == 11
    assert away_team.football_data_team_id == 22
    assert match.football_data_match_id == 998877
    assert match.actual_home_score == 2
    assert match.actual_away_score == 1
    assert match.status == MatchStatus.completed


# ---------------------------------------------------------------------------
# R6.6 — push failure does not block match commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_failure_does_not_block_match_commit(caplog: pytest.LogCaptureFixture) -> None:
    """A raising notify provider must not prevent the match result from being committed."""
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=2, away_score=0)
    factory, session = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    with (
        patch(
            "src.services.result_sync.notify_result_detected",
            new_callable=AsyncMock,
            side_effect=Exception("push provider down"),
        ),
        patch("src.services.result_sync.notify_kickoff_changed", new_callable=AsyncMock),
        patch("src.services.result_sync.notify_match_postponed", new_callable=AsyncMock),
    ):
        import logging

        with caplog.at_level(logging.ERROR, logger="src.services.result_sync"):
            count = await result_sync.sync_results(
                session_factory=factory, client_factory=client_factory
            )

    # Match result was still applied and committed
    assert count == 1
    assert match.actual_home_score == 2
    assert match.actual_away_score == 0
    assert match.status == MatchStatus.completed
    session.commit.assert_awaited()

    # The notification failure stayed isolated to logging/observability.
    assert match.result_source == ResultSource.auto


# ---------------------------------------------------------------------------
# Auto-advance — knockout bracket resolves on the auto-fetch path (C-P0)
# ---------------------------------------------------------------------------


async def test_finished_result_triggers_knockout_bracket_sync(
    _no_bracket_sync: AsyncMock,
) -> None:
    """A settled result on the auto path resolves the next knockout round.

    Regression for the C-P0 where ``sync_results`` never called
    ``sync_knockout_bracket`` (only manual admin paths did), so R16+ fixtures
    stayed on TBD placeholders and could never be scored.
    """
    match = _make_match(status=MatchStatus.locked)
    fd = _fd_match(status=FDMatchStatus.FINISHED, home_score=2, away_score=1)
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    _no_bracket_sync.assert_awaited_once()


async def test_no_finished_result_skips_knockout_bracket_sync(
    _no_bracket_sync: AsyncMock,
) -> None:
    """A cycle with only kickoff drift (no settled result) leaves the bracket alone."""
    kickoff = datetime(2026, 6, 15, 18, 0, 0)
    new_kickoff = datetime(2026, 6, 15, 20, 0, 0)
    match = _make_match(status=MatchStatus.scheduled, kickoff=kickoff)
    fd = _fd_match(
        status=FDMatchStatus.TIMED,
        utc_date=new_kickoff.replace(tzinfo=UTC),
        home_score=None,
        away_score=None,
    )
    factory, _ = _mock_session_factory([_scalars([match]), _orient(match, fd)])
    client_factory = _mock_client_factory([fd])

    count = await result_sync.sync_results(session_factory=factory, client_factory=client_factory)

    assert count == 1
    _no_bracket_sync.assert_not_awaited()


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------


def test_scheduler_registers_5_minute_sync_job() -> None:
    from src.scheduler import create_scheduler

    scheduler = create_scheduler()
    try:
        job = scheduler.get_job("sync_results")
        assert job is not None
        assert job.trigger.interval == timedelta(minutes=5)
        assert job.coalesce is True
        assert job.max_instances == 1
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
