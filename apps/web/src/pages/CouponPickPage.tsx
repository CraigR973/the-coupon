import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, Clock, Lock } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useGameweekHistory, useSelectedGameweekId } from '../hooks/useGameweekHistory';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { useRouteLeague } from '../hooks/useRouteLeague';
import { usePickEditor, gameweekKey } from '../hooks/usePickEditor';
import type {
  FixtureSlate,
  GameweekSlate,
  GameweekStatus,
  OddsFormat,
  PickMarket,
  PickOutcome,
  SelectionOption,
} from '../lib/types';
import { competitionRank } from '../lib/competitions';
import { formatOdds, outcomeLabel, roundName } from '../lib/coupon';
import { formatCalendarDate } from '../lib/time';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { OddsGuide } from '../components/OddsGuide';
import { PickCard } from '../components/PickCard';
import { MemberRoster } from '../components/MemberRoster';
import { GameweekNav } from '../components/GameweekNav';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Badge } from '../components/ui/badge';
import { cn } from '../lib/utils';

const FAR_PAST = new Date(0).toISOString();

/** The two states a round can still be claimed in — settlement has finished with the rest. */
const PICKABLE: ReadonlySet<GameweekStatus> = new Set(['scheduled', 'open']);

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
  competition_id: string;
  competition: string;
  fixtures: FixtureSlate[];
}

/**
 * The slate grouped by the provider's competition slug, each group ordered by kick-off.
 *
 * Display names can carry sponsor text and have changed before, so the group
 * identity and ordering use `fixtures.competition_id`.
 */
function groupByCompetition(fixtures: FixtureSlate[]): CompetitionGroup[] {
  const groups = new Map<string, FixtureSlate[]>();
  for (const fixture of fixtures) {
    const bucket = groups.get(fixture.competition_id) ?? [];
    bucket.push(fixture);
    groups.set(fixture.competition_id, bucket);
  }
  return [...groups.entries()]
    .map(([competition_id, groupFixtures]) => ({
      competition_id,
      competition: groupFixtures[0].competition,
      fixtures: [...groupFixtures].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc)),
    }))
    .sort((a, b) => {
      const ar = competitionRank(a.competition_id);
      const br = competitionRank(b.competition_id);
      // The shared order, with one tiebreak only this screen can apply: among
      // competitions that rank equally the fuller card comes first, which is a
      // property of this slate rather than of the competition.
      return (
        ar[0] - br[0] ||
        ar[1] - br[1] ||
        b.fixtures.length - a.fixtures.length ||
        a.competition.localeCompare(b.competition) ||
        ar[2].localeCompare(br[2])
      );
    });
}

export function CouponPickPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const oddsFormat = useOddsFormat();
  const { slug, name: leagueName } = useRouteLeague();
  const { hasLeagues, isLoading: leaguesLoading } = useLeague();
  const gameweekId = useSelectedGameweekId();

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
    enabled: hasLeagues,
  });

  // Anchored on the round the slate actually came back with, which on the default view
  // is the API's choice rather than the newest date (see `useGameweekHistory`).
  const history = useGameweekHistory(slug, hasLeagues, slate?.gameweek_id);

  const countdown = useCountdown(slate?.locks_at_utc ?? FAR_PAST);
  const openCountdown = useCountdown(slate?.picks_open_at_utc ?? FAR_PAST);
  const { submit, pendingKey, isSubmitting } = usePickEditor(slug, slate?.gameweek_id);

  // Mirrors the API's own rule (`pick_refusal`): the stored instants decide both ends of
  // the claim period and `status` only rules out a round settlement has finished with.
  // Deriving "shut" from `status === 'open'` alone would hold members out of a round
  // whose opening has passed until the hourly job got round to relabelling it.
  //
  // Batch 73 made `pickRefusal` in `lib/coupon.ts` the written-down form of this rule, for
  // the surfaces that only *label* a round. This stays expressed through the countdowns
  // because it needs to flip live while a member watches, and because it decides whether a
  // pick can be submitted rather than what a badge says. Keep the two in step.
  const notOpenYet =
    !!slate?.picks_open_at_utc && !openCountdown.expired && PICKABLE.has(slate.status);
  const locked = !slate || !PICKABLE.has(slate.status) || notOpenYet || countdown.expired;
  const myPick = findMyPick(slate);
  const groups = useMemo(() => groupByCompetition(slate?.fixtures ?? []), [slate?.fixtures]);

  const roundLabel = slate
    ? roundName(slate.number, formatCalendarDate(slate.starts_on, 'EEE d MMM yyyy'))
    : 'This round';

  if (!leaguesLoading && !hasLeagues) {
    return (
      <div>
        <PageHeader title="This week's coupon" />
        <EmptyState
          title="You're not in a league yet"
          description={
            <>
              Join one to start picking.{' '}
              <Link to="/leagues/discover" className="text-primary underline underline-offset-2">
                Find a league
              </Link>
            </>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={history.isLatest ? "This week's coupon" : 'Past coupon'}
        eyebrow={leagueName ? `${leagueName} · ${roundLabel}` : roundLabel}
      />
      <LeagueSwitchStrip currentSlug={slug} className="mb-5" />
      <CouponSubNav slug={slug} />
      <GameweekNav history={history} />

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
          {locked && !notOpenYet ? (
            <Lock className="h-4 w-4" aria-hidden />
          ) : (
            <Clock className="h-4 w-4" aria-hidden />
          )}
          <span className="tabular-nums">
            {slate.status === 'settled'
              ? 'This gameweek is settled'
              : notOpenYet
                ? `Picks open in ${formatCountdown(openCountdown)}`
                : locked
                  ? 'Picks are locked'
                  : `Picks lock in ${formatCountdown(countdown)}`}
          </span>
        </div>
      )}

      {/*
        Batch 48: the API served this card from a *failed* price refresh — last known
        odds, or none at all. Saying so is the difference between stale numbers and
        stale numbers presented as current. Optional field, so an API that predates it
        simply never sets this.
      */}
      {slate?.odds_degraded && (
        <div
          role="status"
          aria-live="polite"
          data-testid="odds-degraded-banner"
          className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-2.5 text-center text-xs font-sans text-warning"
        >
          Prices may be out of date — the odds source isn't responding right now.
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
            {myPick.fixture.competition} · {myPick.fixture.home} v {myPick.fixture.away}
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
              : "This round's slate hasn't been published yet. Check back soon."
          }
        />
      )}

      {slate && (
        <MemberRoster
          members={slate.members}
          missingCount={slate.members_missing_picks}
          oddsFormat={oddsFormat}
          myPlayerId={player?.id}
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
              key={group.competition_id}
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
 * Closed by default: a hundred-fixture slate should scan as league headers
 * first, with members opening only the competitions they care about.
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
  const [open, setOpen] = useState(false);
  const claimed = group.fixtures.filter((f) => f.taken_by_names.length > 0).length;

  return (
    <section data-testid={`competition-${group.competition_id}`}>
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
