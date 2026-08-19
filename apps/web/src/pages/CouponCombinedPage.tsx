import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useGameweekHistory, useSelectedGameweekId } from '../hooks/useGameweekHistory';
import { useRouteLeague } from '../hooks/useRouteLeague';
import { couponKey } from '../hooks/usePickEditor';
import type { Coupon } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
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
  const { slug, name: leagueName } = useRouteLeague();
  const { hasLeagues, isLoading: leaguesLoading } = useLeague();
  const gameweekId = useSelectedGameweekId();

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
    enabled: hasLeagues,
  });

  // Anchored on the round the coupon actually came back with, which on the default view
  // is the API's choice rather than the newest date (see `useGameweekHistory`).
  const history = useGameweekHistory(slug, hasLeagues, coupon?.gameweek_id);

  if (!leaguesLoading && !hasLeagues) {
    return (
      <div>
        <PageHeader title="Combined coupon" />
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

  const roundLabel = history.isLatest ? 'This week' : 'Earlier in the season';

  return (
    <div>
      <PageHeader
        title="Combined coupon"
        eyebrow={leagueName ? `${leagueName} · ${roundLabel}` : roundLabel}
      />
      <LeagueSwitchStrip currentSlug={slug} className="mb-5" />
      <CouponSubNav slug={slug} />
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
