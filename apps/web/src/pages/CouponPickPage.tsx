import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatInTimeZone } from 'date-fns-tz';
import { ChevronDown, Clock, Lock } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useGameweekHistory } from '../hooks/useGameweekHistory';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { usePickEditor, gameweekKey } from '../hooks/usePickEditor';
import type {
  FixtureSlate,
  GameweekSlate,
  OddsFormat,
  PickMarket,
  PickOutcome,
  SelectionOption,
} from '../lib/types';
import { formatOdds, outcomeLabel } from '../lib/coupon';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { OddsGuide } from '../components/OddsGuide';
import { PickCard } from '../components/PickCard';
import { MemberRoster } from '../components/MemberRoster';
import { GameweekNav } from '../components/GameweekNav';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Badge } from '../components/ui/badge';
import { cn } from '../lib/utils';

const FAR_PAST = new Date(0).toISOString();

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return 'Locked';
  if (p.days > 0) return `${p.days}d ${p.hours}h ${p.minutes}m`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m ${p.seconds}s`;
  return `${p.minutes}m ${p.seconds}s`;
}

/** The current pick, derived from the slate's `mine` flags. */
function findMyPick(slate: GameweekSlate | undefined) {
  if (!slate) return null;
  for (const fixture of slate.fixtures) {
    const sel = fixture.selections.find((s: SelectionOption) => s.mine);
    if (sel) return { fixture, sel };
  }
  return null;
}

interface CompetitionGroup {
  competition: string;
  fixtures: FixtureSlate[];
}

/**
 * The slate grouped by competition, each group ordered by kick-off.
 *
 * Competitions are ordered by their earliest kick-off rather than
 * alphabetically, so the games that lock first sit at the top. The backend
 * already returns fixtures in kick-off order, so within a group that order is
 * preserved by construction.
 */
function groupByCompetition(fixtures: FixtureSlate[]): CompetitionGroup[] {
  const groups = new Map<string, FixtureSlate[]>();
  for (const fixture of fixtures) {
    const bucket = groups.get(fixture.competition) ?? [];
    bucket.push(fixture);
    groups.set(fixture.competition, bucket);
  }
  return [...groups.entries()]
    .map(([competition, groupFixtures]) => ({
      competition,
      fixtures: [...groupFixtures].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc)),
    }))
    .sort((a, b) => a.fixtures[0].kickoff_utc.localeCompare(b.fixtures[0].kickoff_utc));
}

export function CouponPickPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const oddsFormat = useOddsFormat();
  const { activeSlug: slug } = useLeague();
  const history = useGameweekHistory(slug);
  const gameweekId = history.selectedId;

  const {
    data: slate,
    isLoading,
    isError,
    error,
  } = useQuery<GameweekSlate>({
    queryKey: gameweekKey(slug, gameweekId),
    queryFn: () =>
      apiFetch<GameweekSlate>(
        `/api/v1/leagues/${slug}/gameweek/current${gameweekId ? `?gameweek_id=${gameweekId}` : ''}`,
      ),
    staleTime: 30_000,
  });

  const countdown = useCountdown(slate?.locks_at_utc ?? FAR_PAST);
  const { submit, pendingKey, isSubmitting } = usePickEditor(slug, slate?.gameweek_id);

  const locked = !slate || slate.status !== 'open' || countdown.expired;
  const myPick = findMyPick(slate);
  const groups = useMemo(() => groupByCompetition(slate?.fixtures ?? []), [slate?.fixtures]);

  return (
    <div>
      <PageHeader
        title={history.isLatest ? "This week's coupon" : 'Past coupon'}
        eyebrow={
          slate ? formatInTimeZone(new Date(slate.saturday_date), timezone, 'EEE d MMM yyyy') : 'Saturday slate'
        }
      />
      <CouponSubNav />
      <GameweekNav history={history} timezone={timezone} />

      {/* Lock / countdown banner */}
      {slate && (
        <div
          className={cn(
            'mb-4 flex items-center justify-center gap-2 rounded-lg border px-4 py-2.5 font-mono text-sm',
            locked
              ? 'border-border bg-surface text-text-muted'
              : 'border-success/30 bg-success/10 text-success',
          )}
          data-testid="lock-banner"
        >
          {locked ? <Lock className="h-4 w-4" aria-hidden /> : <Clock className="h-4 w-4" aria-hidden />}
          <span className="tabular-nums">
            {slate.status === 'settled'
              ? 'This gameweek is settled'
              : locked
                ? 'Picks are locked'
                : `Picks lock in ${formatCountdown(countdown)}`}
          </span>
        </div>
      )}

      <OddsGuide />

      {/* Your current pick */}
      {myPick && (
        <div
          className="mb-5 rounded-lg border-2 border-success/60 bg-success/10 p-4"
          data-testid="my-pick-summary"
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-success">Your pick</p>
          <p className="mt-1 text-sm font-sans font-medium text-text-primary">
            {outcomeLabel(myPick.sel.market, myPick.sel.outcome, myPick.fixture.home, myPick.fixture.away)}
            <span className="mx-1.5 text-text-muted">·</span>
            <span className="font-mono tabular-nums">
              {formatOdds(myPick.sel.odds, oddsFormat)}
            </span>
          </p>
          <p className="mt-0.5 text-xs font-sans text-text-muted">
            {myPick.fixture.home} v {myPick.fixture.away}
          </p>
          {!locked && (
            <p className="mt-2 text-xs font-sans text-text-muted">Tap another selection below to switch.</p>
          )}
        </div>
      )}

      {isLoading && (
        <div className="space-y-4" aria-label="Loading this week's coupon">
          <Skeleton className="h-[220px] w-full rounded-lg" />
          <Skeleton className="h-[220px] w-full rounded-lg" />
        </div>
      )}

      {isError && (
        <EmptyState
          title="No coupon this week yet"
          description={
            error instanceof Error && error.message !== 'API error 404'
              ? error.message
              : "This Saturday's slate hasn't been published yet. Check back soon."
          }
        />
      )}

      {slate && (
        <MemberRoster
          members={slate.members}
          missingCount={slate.members_missing_picks}
          oddsFormat={oddsFormat}
        />
      )}

      {slate && slate.fixtures.length === 0 && (
        <EmptyState
          title="No fixtures on the slate"
          description="There are no priced fixtures for this gameweek yet."
        />
      )}

      {slate && slate.fixtures.length > 0 && (
        <div className="flex flex-col gap-4">
          {!myPick && !locked && (
            <Badge variant="warning" className="w-fit">
              You haven't grabbed a selection yet
            </Badge>
          )}
          {groups.map((group) => (
            <CompetitionSection
              key={group.competition}
              group={group}
              timezone={timezone}
              locked={locked}
              pendingKey={pendingKey}
              busy={isSubmitting}
              oddsFormat={oddsFormat}
              onGrab={submit}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * One competition's fixtures behind a collapsible header.
 *
 * Open by default: a member arriving at the coupon wants to see games, not a
 * list of league names to expand. Collapsing is for skipping past the
 * competitions they don't follow on a slate that can run past a hundred games.
 */
function CompetitionSection({
  group,
  timezone,
  locked,
  pendingKey,
  busy,
  oddsFormat,
  onGrab,
}: {
  group: CompetitionGroup;
  timezone: string;
  locked: boolean;
  pendingKey: string | null;
  busy: boolean;
  oddsFormat: OddsFormat;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}) {
  const [open, setOpen] = useState(true);
  const claimed = group.fixtures.filter((f) => f.taken_by_names.length > 0).length;

  return (
    <section data-testid={`competition-${group.competition}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-2 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="min-w-0 truncate font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary">
          {group.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-[10px] tabular-nums text-text-muted">
            {claimed > 0 ? `${claimed}/${group.fixtures.length}` : group.fixtures.length}
          </span>
          <ChevronDown
            className={cn('h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-4">
          {group.fixtures.map((fixture) => (
            <PickCard
              key={fixture.fixture_id}
              fixture={fixture}
              timezone={timezone}
              locked={locked}
              pendingKey={pendingKey}
              busy={busy}
              oddsFormat={oddsFormat}
              onGrab={onGrab}
            />
          ))}
        </div>
      )}
    </section>
  );
}
