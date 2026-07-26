import { useQuery } from '@tanstack/react-query';
import { formatInTimeZone } from 'date-fns-tz';
import { Clock, Lock } from 'lucide-react';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { usePickEditor, gameweekKey } from '../hooks/usePickEditor';
import type { GameweekSlate, SelectionOption } from '../lib/types';
import { formatOdds, outcomeLabel } from '../lib/coupon';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { OddsGuide } from '../components/OddsGuide';
import { PickCard } from '../components/PickCard';
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

export function CouponPickPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const slug = DEFAULT_LEAGUE_SLUG;

  const {
    data: slate,
    isLoading,
    isError,
    error,
  } = useQuery<GameweekSlate>({
    queryKey: gameweekKey(slug),
    queryFn: () => apiFetch<GameweekSlate>(`/api/v1/leagues/${slug}/gameweek/current`),
    staleTime: 30_000,
  });

  const countdown = useCountdown(slate?.locks_at_utc ?? FAR_PAST);
  const { submit, pendingKey, isSubmitting } = usePickEditor(slug, slate?.gameweek_id);

  const locked = !slate || slate.status !== 'open' || countdown.expired;
  const myPick = findMyPick(slate);

  return (
    <div>
      <PageHeader
        title="This week's coupon"
        eyebrow={
          slate ? formatInTimeZone(new Date(slate.saturday_date), timezone, 'EEE d MMM yyyy') : 'Saturday slate'
        }
      />
      <CouponSubNav />

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
            <span className="font-mono tabular-nums">{formatOdds(myPick.sel.odds)}</span>
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
          {slate.fixtures.map((fixture) => (
            <PickCard
              key={fixture.fixture_id}
              fixture={fixture}
              timezone={timezone}
              locked={locked}
              pendingKey={pendingKey}
              busy={isSubmitting}
              onGrab={submit}
            />
          ))}
        </div>
      )}
    </div>
  );
}
