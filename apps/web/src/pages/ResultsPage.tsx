import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import { useLeague } from '../contexts/LeagueContext';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { useRouteLeague } from '../hooks/useRouteLeague';
import { formatOdds } from '../lib/coupon';
import { couponSectionPath } from '../lib/leagues';
import { formatCalendarDate } from '../lib/time';
import type { GameweekResult } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { EmptyState } from '../components/EmptyState';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';

/**
 * Every settled gameweek this league has played, newest first — the week-by-week
 * record that stepping back through `GameweekNav` one round at a time never
 * surfaced on its own. Each row opens that week's combined coupon.
 *
 * Titled **Season** since Batch 78, and that is what it has always been. It was called
 * Results while showing none: the scorelines, the points and the won/lost badges live in
 * the round's own coupon section, where Batch 67 put them, and every row here navigates
 * there. The route keeps its `/results` path because members have it in their history.
 *
 * Batch 105 moved that destination without changing it: the combined coupon became the
 * `#coupon` section of the current-round surface, so a row now opens that week's round
 * scrolled to its coupon rather than a screen of its own.
 */
export function ResultsPage() {
  const { slug, name: leagueName } = useRouteLeague();
  const { hasLeagues, isLoading: leaguesLoading } = useLeague();
  const oddsFormat = useOddsFormat();
  const navigate = useNavigate();

  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery<GameweekResult[]>({
    queryKey: ['results', slug],
    queryFn: () => apiFetch<GameweekResult[]>(`/api/v1/leagues/${slug}/results`),
    staleTime: 30_000,
    enabled: hasLeagues,
  });
  const results = Array.isArray(data) ? data : [];

  if (!leaguesLoading && !hasLeagues) {
    return (
      <div>
        <PageHeader title="Season" />
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
        title="Season"
        eyebrow={leagueName ? `${leagueName} · Every settled gameweek` : 'Every settled gameweek'}
      />
      <LeagueSwitchStrip currentSlug={slug} className="mb-5" />
      <CouponSubNav slug={slug} />

      {isLoading && (
        <div className="space-y-3" aria-label="Loading results">
          <Skeleton className="h-20 w-full rounded-lg" />
          <Skeleton className="h-20 w-full rounded-lg" />
          <Skeleton className="h-20 w-full rounded-lg" />
        </div>
      )}

      {isError && (
        <EmptyState
          title="Couldn't load results"
          description={error instanceof Error ? error.message : 'Please try again shortly.'}
        />
      )}

      {!isLoading && !isError && results.length === 0 && (
        <EmptyState
          title="No results yet"
          description="A gameweek appears here once it has been settled."
        />
      )}

      {results.length > 0 && (
        <ol className="flex flex-col gap-2" data-testid="results-list">
          {results.map((result) => (
            <li key={result.gameweek_id} id={`gw-${result.gameweek_id}`}>
              <button
                type="button"
                // Both halves of the address matter: the gameweek id is league-scoped,
                // so it only resolves against the league it came from.
                onClick={() => navigate(couponSectionPath(slug, result.gameweek_id))}
                className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface p-3 text-left transition-colors press-down hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
                data-testid={`result-${result.gameweek_id}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="font-sans text-sm font-medium text-text-primary">
                    {formatCalendarDate(result.starts_on, 'EEEE d MMMM')}
                  </p>
                  <p className="truncate font-sans text-xs text-text-muted">
                    {result.winner_names.length === 0
                      ? 'No picks made'
                      : result.winner_names.length === 1
                        ? `${result.winner_names[0]} won`
                        : `${result.winner_names.join(', ')} tied`}
                    {/* Batch 79. `all_won` could only say every leg or not every leg, so
                        five of six and none of six read the same. Absent on an API that
                        predates the field, which renders as the row always did. */}
                    {result.picks_won != null && result.leg_count > 0 && (
                      <>
                        <span className="mx-1.5">·</span>
                        {result.picks_won} of {result.leg_count} landed
                      </>
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="font-mono text-sm tabular-nums text-text-primary">
                    {result.winner_points} pts
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] tabular-nums text-text-muted">
                      {formatOdds(result.combined_odds, oddsFormat)}
                    </span>
                    {result.all_won !== null && (
                      <Badge variant={result.all_won ? 'success' : 'muted'}>
                        {result.all_won ? 'Coupon won' : 'Coupon lost'}
                      </Badge>
                    )}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
