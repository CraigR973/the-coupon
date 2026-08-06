import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useGameweekHistory } from '../hooks/useGameweekHistory';
import { couponKey } from '../hooks/usePickEditor';
import type { Coupon } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { CombinedAccaView } from '../components/CombinedAccaView';
import { GameweekNav } from '../components/GameweekNav';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';

/**
 * The leaderboard's combined accumulator — everyone's one pick stacked into a
 * single acca to reference on a real book. Defaults to the current gameweek and
 * browses back through the season alongside the pick screen.
 */
export function CouponCombinedPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const { activeSlug: slug } = useLeague();
  const history = useGameweekHistory(slug);
  const gameweekId = history.selectedId;

  const {
    data: coupon,
    isLoading,
    isError,
    error,
  } = useQuery<Coupon>({
    queryKey: couponKey(slug, gameweekId),
    queryFn: () =>
      apiFetch<Coupon>(
        `/api/v1/leagues/${slug}/coupon${gameweekId ? `?gameweek_id=${gameweekId}` : ''}`,
      ),
    staleTime: 30_000,
  });

  return (
    <div>
      <PageHeader
        title="Combined coupon"
        eyebrow={history.isLatest ? 'This week' : 'Earlier in the season'}
      />
      <CouponSubNav />
      <GameweekNav history={history} timezone={timezone} />

      {isLoading && (
        <div className="space-y-3" aria-label="Loading combined coupon">
          <Skeleton className="h-28 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
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

      {coupon && <CombinedAccaView coupon={coupon} />}
    </div>
  );
}
