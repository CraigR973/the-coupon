"""Ingest and serve football data — league tables, previous results, and recent form.

Batch 16. Two halves that never meet a provider at the same time:

**Ingestion** (:func:`sync_football_data`, :func:`backfill_season`) runs on the scheduler,
pulls each competition's table and results, reconciles club names, and writes ``teams`` /
``matches`` / ``standings``.

**Reads** (:func:`league_tables`, :func:`recent_results`, :func:`fixture_context`) touch
only those tables. No screen, inline or otherwise, can cause an upstream request. That is
not a nicety: API-Football's free plan allows 100 requests a *day* and 10 a minute, so a
single member refreshing the pick screen could exhaust it before lunch.

What gets ingested is decided by what is already on the card. The competitions are the
distinct ``fixtures.competition_id`` values in the pool, which means the football data
follows the slate automatically — a league that adds a division gets its table on the next
run, and a division nobody plays costs nothing. They are synced least-recently-first, so
when there are more competitions than a run's budget the tail rotates in rather than
starving.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.fixture import Fixture
from src.models.gameweek import Gameweek, GameweekFixture
from src.models.league import League
from src.models.match import Match
from src.models.standing import Standing
from src.models.team import Team
from src.schemas import UtcDatetime
from src.services.football_provider import (
    CompetitionKey,
    FootballDataProvider,
    FormResult,
    LeagueTable,
    MatchResult,
    TeamRef,
    current_season,
    form_result,
)
from src.services.gameweek import selected_competition_slugs
from src.services.team_matching import normalise_name, record_alias, resolve_names

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

Sleeper = Callable[[float], Awaitable[None]]


def _naive_utc(value: datetime) -> datetime:
    """Strip to naive UTC (the storage convention for every ``*_utc`` column)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


# ── Read views (what the router serialises) ────────────────────────────────────


class FormMatch(BaseModel):
    """One finished match from one club's point of view."""

    match_id: str
    kickoff_utc: UtcDatetime
    opponent: str
    home: bool
    goals_for: int
    goals_against: int
    result: FormResult


class TeamContext(BaseModel):
    """A club's table line and recent form — what sits beside a fixture on the card.

    Table figures are ``None`` when the competition has no table stored (a cup round, a
    division the provider does not carry, or a season not yet ingested). Form can be
    present without them, and often is early in a season.
    """

    team_id: str
    name: str
    position: int | None = None
    played: int | None = None
    points: int | None = None
    goal_difference: int | None = None
    #: Most recent **last**, e.g. ``"LWWDW"`` — the order every football table prints.
    form: str = ""
    recent: list[FormMatch] = []


class FixtureContext(BaseModel):
    """Both clubs' context for one fixture. Either side may be unresolved."""

    home: TeamContext | None = None
    away: TeamContext | None = None


class TableEntry(BaseModel):
    position: int
    team_id: str
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str


class CompetitionTable(BaseModel):
    competition_id: str
    competition: str
    season: int
    #: When this table was last ingested — shown as "as of", because a stored table is
    #: only as current as the last run.
    updated_at: UtcDatetime | None
    rows: list[TableEntry]


class ResultEntry(BaseModel):
    match_id: str
    competition_id: str
    competition: str
    kickoff_utc: UtcDatetime
    home: str
    away: str
    home_goals: int
    away_goals: int


class CompetitionSync(BaseModel):
    """What one competition's ingestion did — the job's log line, and its test surface."""

    competition_id: str
    competition: str
    season: int
    table_rows: int = 0
    matches: int = 0
    fixtures_reconciled: int = 0
    carried: bool = True


class FootballSweep(BaseModel):
    """What a whole run did, including the competitions that produced no report at all.

    A list of reports cannot answer the question the job actually has to answer, because
    a competition that *raised* leaves no report behind: an empty list means either "the
    card was empty" or "every single competition failed", and those are opposite
    verdicts. Batch 45 exists because the job could not tell them apart and called both
    a success — on 2026-08-20 the production sweep failed all 21 competitions, logged
    ``football data synced``, and exited 0 for weeks.

    ``attempted`` is therefore carried alongside the reports rather than derived from
    them.
    """

    attempted: int = 0
    reports: list[CompetitionSync] = []

    @property
    def carried(self) -> int:
        """Competitions that produced a table or at least one result."""
        return sum(1 for report in self.reports if report.carried)

    @property
    def failed(self) -> int:
        """Competitions that raised, and so are missing from ``reports`` entirely."""
        return self.attempted - len(self.reports)

    @property
    def carried_nothing(self) -> bool:
        """True when the run had work to do and none of it landed.

        One condition covers both shapes of total failure — every competition raising,
        and every competition being honestly empty — because ``carried`` counts reports
        and a competition that raised has none.

        ``attempted == 0`` is *not* a failure: an empty fixture pool is a legitimate
        zero-work run, as is a deployment with no provider (which returns before a sweep
        ever starts). A card where every competition genuinely has nothing yet would be
        called a failure here; across twenty-odd British divisions that is not a state
        that lasts, and a morning where nothing at all could be ingested is worth
        surfacing rather than hiding.
        """
        return self.attempted > 0 and self.carried == 0

    def summary(self) -> dict[str, int]:
        """The figures both the success and the failure log line carry."""
        return {
            "attempted": self.attempted,
            "reported": len(self.reports),
            "failed": self.failed,
            "carried": self.carried,
            "table_rows": sum(report.table_rows for report in self.reports),
            "matches": sum(report.matches for report in self.reports),
        }


# ── Which competitions matter ──────────────────────────────────────────────────


async def pooled_competitions(
    db: AsyncSession, *, since: date | None = None
) -> list[CompetitionKey]:
    """Every competition in the fixture pool, least-recently-synced first.

    ``since`` bounds it to fixtures kicking off on or after a date, so a run does not keep
    paying for a competition that dropped off the card months ago.

    The ordering is what makes a per-run cap safe. Competitions are sorted by the newest
    ``standings.updated_at`` they have, nulls (never synced) first, so a slate with more
    competitions than the budget allows works through them across successive runs instead
    of always syncing the same head of the list.
    """
    query = select(Fixture.competition_id, func.min(Fixture.competition).label("competition"))
    if since is not None:
        query = query.where(Fixture.kickoff_utc >= datetime.combine(since, datetime.min.time()))
    rows = (await db.execute(query.group_by(Fixture.competition_id))).all()
    if not rows:
        return []

    freshness = await db.execute(
        select(Standing.competition_id, func.max(Standing.updated_at)).group_by(
            Standing.competition_id
        )
    )
    last_synced: dict[str, datetime] = {row[0]: row[1] for row in freshness.all() if row[1]}
    never = datetime.min
    return [
        CompetitionKey(slug=slug, name=name)
        for slug, name in sorted(rows, key=lambda row: (last_synced.get(row[0], never), row[0]))
    ]


async def league_competitions(db: AsyncSession, league: League) -> list[CompetitionKey]:
    """The competitions one league plays — the scope of its tables and results screen.

    An explicit selection (``leagues.competitions``) is taken at face value, because that
    is what the admin chose even before a round has been built from it. A league on the
    "all UK" default is described instead by the competitions its own rounds actually
    carry, which is narrower and more honest than listing every division in the pool.
    """
    selected = selected_competition_slugs(league)
    if selected is not None and league.competitions:
        return [
            CompetitionKey(slug=entry["slug"], name=entry.get("name", entry["slug"]))
            for entry in league.competitions
            if isinstance(entry, dict) and entry.get("slug")
        ]

    rows = await db.execute(
        select(Fixture.competition_id, func.min(Fixture.competition))
        .join(GameweekFixture, GameweekFixture.fixture_id == Fixture.id)
        .join(Gameweek, Gameweek.id == GameweekFixture.gameweek_id)
        .where(Gameweek.league_id == league.id)
        .group_by(Fixture.competition_id)
        .order_by(func.min(Fixture.competition))
    )
    return [CompetitionKey(slug=row[0], name=row[1]) for row in rows.all()]


def season_or_default(season: int | None) -> int:
    """The configured season, or the one today falls in."""
    return season if season is not None else current_season()


# ── Ingestion ──────────────────────────────────────────────────────────────────


async def upsert_teams(
    db: AsyncSession, competition: CompetitionKey, refs: Iterable[TeamRef]
) -> dict[str, Team]:
    """Upsert clubs by ``provider_team_id``, returning them keyed by that id.

    Names are refreshed on every run (clubs rename, and a provider tidies its spellings),
    and each name seen is recorded as an alias so the reconciliation layer keeps up.
    ``competition_id`` is moved to the competition the club was last seen in, which is how
    a promoted club stops being matched against its old division.
    """
    wanted = {ref.provider_team_id: ref for ref in refs if ref.provider_team_id}
    if not wanted:
        return {}

    existing = await db.execute(select(Team).where(Team.provider_team_id.in_(wanted)))
    by_id = {team.provider_team_id: team for team in existing.scalars().all()}

    for provider_id, ref in wanted.items():
        team = by_id.get(provider_id)
        if team is None:
            team = Team(provider_team_id=provider_id)
            db.add(team)
            by_id[provider_id] = team
        team.name = ref.name[:120]
        team.short_name = ref.short_name[:60]
        team.normalised_name = normalise_name(ref.name)[:120]
        team.competition_id = competition.slug[:120]
        team.country = competition.country[:60]
    await db.flush()

    for provider_id, ref in wanted.items():
        await record_alias(db, competition.slug, ref.name, by_id[provider_id], source="provider")
        if ref.short_name:
            await record_alias(
                db, competition.slug, ref.short_name, by_id[provider_id], source="provider"
            )
    return by_id


async def sync_table(db: AsyncSession, table: LeagueTable) -> int:
    """Replace one competition-season's stored table with the published one.

    A *replacement*, not a merge: a club that leaves the table — expunged, or the
    competition restructured — has to leave the stored one too, or it would sit in the
    listing forever at whatever position it last held.

    Every kept row's ``updated_at`` is stamped, whether or not its figures moved, because
    two things read it as "when did we last *ask*": the "as of" line on the table, and the
    least-recently-synced ordering in :func:`pooled_competitions`. Stamped here rather than
    with an ``onupdate`` on :class:`~src.models.base.UpdatedAtMixin`, which every other
    model shares and which no other batch asked to change. A server-side default is no use
    for the ordering either — ``NOW()`` is the *transaction's* start time, so a run that
    syncs several competitions would give them all one indistinguishable timestamp.

    Flushes but does not commit.
    """
    stamped_at = _naive_utc(datetime.now(UTC))
    teams = await upsert_teams(db, table.competition, [row.team for row in table.rows])
    existing = await db.execute(
        select(Standing).where(
            Standing.competition_id == table.competition.slug,
            Standing.season == table.season,
        )
    )
    by_team: dict[uuid.UUID, Standing] = {row.team_id: row for row in existing.scalars().all()}

    kept: set[uuid.UUID] = set()
    for row in table.rows:
        team = teams.get(row.team.provider_team_id)
        if team is None:
            continue
        standing = by_team.get(team.id)
        if standing is None:
            standing = Standing(
                competition_id=table.competition.slug[:120],
                season=table.season,
                team_id=team.id,
            )
            db.add(standing)
        standing.competition = table.competition.name[:120]
        standing.position = row.position
        standing.played = row.played
        standing.won = row.won
        standing.drawn = row.drawn
        standing.lost = row.lost
        standing.goals_for = row.goals_for
        standing.goals_against = row.goals_against
        standing.points = row.points
        standing.form = row.form[:10]
        standing.updated_at = stamped_at
        kept.add(team.id)

    for team_id, standing in by_team.items():
        if team_id not in kept:
            await db.delete(standing)
    await db.flush()
    return len(kept)


async def sync_results(db: AsyncSession, results: Sequence[MatchResult]) -> int:
    """Upsert matches by ``provider_match_id``. Idempotent; flushes, does not commit."""
    if not results:
        return 0
    competition = results[0].competition
    refs: dict[str, TeamRef] = {}
    for result in results:
        refs.setdefault(result.home.provider_team_id, result.home)
        refs.setdefault(result.away.provider_team_id, result.away)
    teams = await upsert_teams(db, competition, refs.values())

    ids = [result.provider_match_id for result in results]
    existing = await db.execute(select(Match).where(Match.provider_match_id.in_(ids)))
    by_id = {match.provider_match_id: match for match in existing.scalars().all()}

    written = 0
    for result in results:
        home = teams.get(result.home.provider_team_id)
        away = teams.get(result.away.provider_team_id)
        if home is None or away is None:
            continue
        match = by_id.get(result.provider_match_id)
        if match is None:
            match = Match(provider_match_id=result.provider_match_id)
            db.add(match)
            by_id[result.provider_match_id] = match
        match.competition_id = result.competition.slug[:120]
        match.competition = result.competition.name[:120]
        match.season = result.season
        match.kickoff_utc = _naive_utc(result.kickoff_utc)
        match.home_team_id = home.id
        match.away_team_id = away.id
        match.home_goals = result.home_goals
        match.away_goals = result.away_goals
        match.finished = result.finished and result.home_goals is not None
        match.status = result.status[:24]
        written += 1
    await db.flush()
    return written


async def reconcile_fixture_names(db: AsyncSession, competition: CompetitionKey) -> int:
    """Teach the alias table the odds provider's spellings for one competition.

    Runs after the clubs are stored, over the free-text ``fixtures.home`` / ``away`` in
    that competition. Doing it at ingestion time rather than at read time is what keeps
    the pick screen's inline form a primary-key lookup: the fuzzy matching happens once,
    on the scheduler's clock, and its results are visible rows.

    Returns how many distinct spellings are now resolvable.
    """
    rows = await db.execute(
        select(Fixture.home, Fixture.away).where(Fixture.competition_id == competition.slug)
    )
    names = {name for row in rows.all() for name in row if name}
    if not names:
        return 0
    resolved = await resolve_names(db, competition.slug, names, source="odds")
    if len(resolved) < len(names):
        log.info(
            "fixture names unresolved",
            competition_id=competition.slug,
            resolved=len(resolved),
            seen=len(names),
        )
    return len(resolved)


async def sync_competition(
    db: AsyncSession,
    provider: FootballDataProvider,
    competition: CompetitionKey,
    season: int,
    *,
    since: date | None = None,
    until: date | None = None,
) -> CompetitionSync:
    """Ingest one competition: its table, its results, and the name reconciliation.

    Two upstream requests (plus paging on results), which is the unit the per-run budget
    counts. A competition the provider does not carry costs the same two and returns
    ``carried=False``, so the run can report coverage honestly rather than looking like a
    competition with no football in it.

    Flushes but does not commit — the caller owns the transaction.
    """
    report = CompetitionSync(
        competition_id=competition.slug, competition=competition.name, season=season
    )
    table = await provider.fetch_table(competition, season)
    if table is not None:
        report.table_rows = await sync_table(db, table)

    results = await provider.fetch_results(competition, season, since=since, until=until)
    if results:
        report.matches = await sync_results(db, results)

    report.carried = table is not None or bool(results)
    report.fixtures_reconciled = await reconcile_fixture_names(db, competition)
    return report


async def sync_football_data(
    db: AsyncSession,
    provider: FootballDataProvider,
    *,
    season: int,
    limit: int,
    lookback_days: int,
    today: date | None = None,
    competition_spacing_seconds: float = 0.0,
    sleeper: Sleeper = asyncio.sleep,
) -> FootballSweep:
    """The scheduled top-up: the least-recently-synced competitions on the card.

    Bounded by ``limit`` competitions per run — the whole point of the ordering in
    :func:`pooled_competitions`. Results are asked for over a ``lookback_days`` window
    rather than the whole season, because the season's history is the backfill's job and
    re-fetching it daily would spend the entire allowance on data that cannot change.

    One competition's failure does not take the run down: it is logged and the rest
    continue, because a provider that has stopped carrying one division should not cost
    the other twenty-nine their tables. That tolerance is right and is unchanged by
    Batch 45 — what changed is that the *caller* can now see how much of the card was
    attempted, so total failure is distinguishable from an empty card. See
    :class:`FootballSweep`. ``competition_spacing_seconds`` spaces the scheduled sweep
    below API-Football's 10-requests/minute cap; it is injected so tests can assert the
    cadence without waiting.
    """
    day = today or datetime.now(UTC).date()
    competitions = await pooled_competitions(db, since=day - timedelta(days=lookback_days))
    targets = competitions[: max(limit, 0)]
    reports: list[CompetitionSync] = []
    for index, competition in enumerate(targets):
        try:
            reports.append(
                await sync_competition(
                    db,
                    provider,
                    competition,
                    season,
                    since=day - timedelta(days=lookback_days),
                    until=day + timedelta(days=1),
                )
            )
        except Exception:
            log.exception("football data sync failed", competition_id=competition.slug)
        if competition_spacing_seconds > 0 and index < len(targets) - 1:
            await sleeper(competition_spacing_seconds)
    return FootballSweep(attempted=len(targets), reports=reports)


async def backfill_season(
    db: AsyncSession,
    provider: FootballDataProvider,
    *,
    season: int,
    competitions: Sequence[CompetitionKey] | None = None,
) -> FootballSweep:
    """Pull a whole season's results and current table for every pooled competition.

    The one-off counterpart to :func:`sync_football_data`: unbounded in date so a season's
    history arrives in one pass, and unbounded in competitions because it is run
    deliberately rather than on a clock. It is still the same two requests per competition
    (plus result paging), so a thirty-competition backfill is affordable in a day — which
    is exactly why the daily job asks for a window instead.

    Reports a :class:`FootballSweep` for the same reason the daily job does. A human runs
    this one and reads its output, which is exactly the sort of thing that makes a silent
    total failure *more* likely to be believed rather than less.
    """
    targets = list(competitions) if competitions is not None else await pooled_competitions(db)
    reports: list[CompetitionSync] = []
    for competition in targets:
        try:
            reports.append(await sync_competition(db, provider, competition, season))
        except Exception:
            log.exception("football data backfill failed", competition_id=competition.slug)
    return FootballSweep(attempted=len(targets), reports=reports)


# ── Reads (database only — never a provider) ───────────────────────────────────


async def league_tables(
    db: AsyncSession, competitions: Sequence[CompetitionKey], season: int
) -> list[CompetitionTable]:
    """Stored tables for the given competitions, in position order.

    Competitions with nothing stored are omitted rather than returned empty: a cup round
    has no table, and a placeholder saying so on every screen is noise.
    """
    slugs = [competition.slug for competition in competitions]
    if not slugs:
        return []
    rows = await db.execute(
        select(Standing, Team.name)
        .join(Team, Team.id == Standing.team_id)
        .where(Standing.competition_id.in_(slugs), Standing.season == season)
        .order_by(Standing.competition_id, Standing.position)
    )

    names = {competition.slug: competition.name for competition in competitions}
    tables: dict[str, CompetitionTable] = {}
    for standing, team_name in rows.all():
        table = tables.get(standing.competition_id)
        if table is None:
            table = CompetitionTable(
                competition_id=standing.competition_id,
                competition=standing.competition or names.get(standing.competition_id, ""),
                season=season,
                updated_at=standing.updated_at,
                rows=[],
            )
            tables[standing.competition_id] = table
        newest = table.updated_at
        if standing.updated_at and (newest is None or standing.updated_at > newest):
            table.updated_at = standing.updated_at
        table.rows.append(
            TableEntry(
                position=standing.position,
                team_id=str(standing.team_id),
                team=team_name,
                played=standing.played,
                won=standing.won,
                drawn=standing.drawn,
                lost=standing.lost,
                goals_for=standing.goals_for,
                goals_against=standing.goals_against,
                goal_difference=standing.goals_for - standing.goals_against,
                points=standing.points,
                form=standing.form,
            )
        )
    return [tables[slug] for slug in slugs if slug in tables]


async def recent_results(
    db: AsyncSession, competitions: Sequence[CompetitionKey], *, limit: int
) -> list[ResultEntry]:
    """The latest finished matches across the given competitions, newest first."""
    slugs = [competition.slug for competition in competitions]
    if not slugs or limit <= 0:
        return []
    home_team = Team.__table__.alias("home_team")
    away_team = Team.__table__.alias("away_team")
    rows = await db.execute(
        select(Match, home_team.c.name, away_team.c.name)
        .join(home_team, home_team.c.id == Match.home_team_id)
        .join(away_team, away_team.c.id == Match.away_team_id)
        .where(
            Match.competition_id.in_(slugs),
            Match.finished.is_(True),
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
        )
        .order_by(Match.kickoff_utc.desc(), Match.provider_match_id)
        .limit(limit)
    )
    return [
        ResultEntry(
            match_id=str(match.id),
            competition_id=match.competition_id,
            competition=match.competition,
            kickoff_utc=match.kickoff_utc,
            home=home,
            away=away,
            home_goals=match.home_goals or 0,
            away_goals=match.away_goals or 0,
        )
        for match, home, away in rows.all()
    ]


async def team_form(
    db: AsyncSession, team_ids: Sequence[uuid.UUID], *, limit: int
) -> dict[uuid.UUID, list[FormMatch]]:
    """Each club's last ``limit`` finished matches, most recent **first**.

    One query for every club on the card rather than one per club: a slate can run past a
    hundred fixtures, and two hundred round trips to draw a form line would be worse than
    not drawing it. Over-fetching and trimming in Python keeps it to a single statement —
    a per-club window function would be tidier SQL but is not worth a second query plan
    for a set this size.
    """
    if not team_ids or limit <= 0:
        return {}
    wanted = set(team_ids)
    home_team = Team.__table__.alias("home_team")
    away_team = Team.__table__.alias("away_team")
    rows = await db.execute(
        select(Match, home_team.c.name, away_team.c.name)
        .join(home_team, home_team.c.id == Match.home_team_id)
        .join(away_team, away_team.c.id == Match.away_team_id)
        .where(
            Match.finished.is_(True),
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
            Match.home_team_id.in_(wanted) | Match.away_team_id.in_(wanted),
        )
        .order_by(Match.kickoff_utc.desc(), Match.provider_match_id)
        .limit(limit * len(wanted) * 2)
    )

    form: dict[uuid.UUID, list[FormMatch]] = {team_id: [] for team_id in wanted}
    for match, home_name, away_name in rows.all():
        for team_id, at_home in ((match.home_team_id, True), (match.away_team_id, False)):
            if team_id not in wanted or len(form[team_id]) >= limit:
                continue
            goals_for = (match.home_goals if at_home else match.away_goals) or 0
            goals_against = (match.away_goals if at_home else match.home_goals) or 0
            form[team_id].append(
                FormMatch(
                    match_id=str(match.id),
                    kickoff_utc=match.kickoff_utc,
                    opponent=away_name if at_home else home_name,
                    home=at_home,
                    goals_for=goals_for,
                    goals_against=goals_against,
                    result=form_result(goals_for, goals_against),
                )
            )
    return form


def form_string(matches: Sequence[FormMatch]) -> str:
    """A form line from matches ordered most-recent-first, printed most-recent-last."""
    return "".join(match.result.value for match in reversed(matches))


async def fixture_context(
    db: AsyncSession,
    fixtures: Sequence[Fixture],
    *,
    season: int,
    form_matches: int,
) -> dict[str, FixtureContext]:
    """Table position and recent form for both clubs on each fixture, keyed by fixture id.

    This is the inline half of Batch 16 — what the pick screen shows beside a game. It
    resolves the odds provider's free-text club names through the alias table
    (:mod:`src.services.team_matching`), which the ingestion run has already taught, so
    the whole thing is three queries for a slate of any size and no upstream request at
    all.

    Fixtures whose clubs cannot be resolved are simply absent from the result. The screen
    then shows the fixture exactly as it did before this batch, which is the right
    degradation: a form line is an enhancement, not a precondition for picking.
    """
    if not fixtures:
        return {}

    by_competition: dict[str, list[Fixture]] = {}
    for fixture in fixtures:
        by_competition.setdefault(fixture.competition_id, []).append(fixture)

    resolved: dict[str, dict[str, Team]] = {}
    for competition_id, group in by_competition.items():
        names = {name for fixture in group for name in (fixture.home, fixture.away)}
        resolved[competition_id] = await resolve_names(db, competition_id, names, source="odds")

    team_ids = {team.id for teams in resolved.values() for team in teams.values()}
    if not team_ids:
        return {}

    standings = await db.execute(
        select(Standing).where(Standing.team_id.in_(team_ids), Standing.season == season)
    )
    standing_by_team = {row.team_id: row for row in standings.scalars().all()}
    form_by_team = await team_form(db, list(team_ids), limit=form_matches)

    def context_for(competition_id: str, name: str) -> TeamContext | None:
        team = resolved.get(competition_id, {}).get(name)
        if team is None:
            return None
        standing = standing_by_team.get(team.id)
        recent = form_by_team.get(team.id, [])
        return TeamContext(
            team_id=str(team.id),
            name=team.name,
            position=standing.position if standing else None,
            played=standing.played if standing else None,
            points=standing.points if standing else None,
            goal_difference=(standing.goals_for - standing.goals_against) if standing else None,
            form=form_string(recent) or (standing.form if standing else ""),
            recent=recent,
        )

    contexts: dict[str, FixtureContext] = {}
    for fixture in fixtures:
        home = context_for(fixture.competition_id, fixture.home)
        away = context_for(fixture.competition_id, fixture.away)
        if home is None and away is None:
            continue
        contexts[str(fixture.id)] = FixtureContext(home=home, away=away)
    return contexts


def competition_names(competitions: Iterable[CompetitionKey]) -> Mapping[str, str]:
    """``slug -> display name``, for callers labelling stored rows."""
    return {competition.slug: competition.name for competition in competitions}
