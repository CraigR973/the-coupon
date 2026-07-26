import { useQuery } from '@tanstack/react-query';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '../lib/api';
import { couponKey } from '../hooks/usePickEditor';
import type { Coupon } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { CombinedAccaView } from '../components/CombinedAccaView';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';

/**
 * The leaderboard's combined accumulator for the current gameweek — everyone's
 * one pick stacked into a single acca to reference on a real book.
 */
export function CouponCombinedPage() {
  const slug = DEFAULT_LEAGUE_SLUG;

  const {
    data: coupon,
    isLoading,
    isError,
    error,
  } = useQuery<Coupon>({
    queryKey: couponKey(slug),
    queryFn: () => apiFetch<Coupon>(`/api/v1/leagues/${slug}/coupon`),
    staleTime: 30_000,
  });

  return (
    <div>
      <PageHeader title="Combined coupon" eyebrow="This week" />
      <CouponSubNav />

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
              : "This Saturday's slate hasn't been published yet. Check back soon."
          }
        />
      )}

      {coupon && <CombinedAccaView coupon={coupon} />}
    </div>
  );
}
