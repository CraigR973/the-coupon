import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import type { LeagueDetail, Standing } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Avatar } from '../components/ui/avatar';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { LeagueActionsMenu } from '../components/LeagueActionsMenu';
import { cn } from '../lib/utils';

export function LeaderboardPage() {
  const { slug = DEFAULT_LEAGUE_SLUG } = useParams<{ slug: string }>();
  const { player } = useAuth();

  const { data: league } = useQuery<LeagueDetail>({
    queryKey: ['league', slug],
    queryFn: () => apiFetch<LeagueDetail>(`/api/v1/leagues/${slug}`),
    staleTime: 60_000,
  });

  const {
    data: standings = [],
    isLoading,
    isError,
  } = useQuery<Standing[]>({
    queryKey: ['standings', slug],
    queryFn: () => apiFetch<Standing[]>(`/api/v1/leagues/${slug}/standings`),
    staleTime: 30_000,
  });

  const isAdmin = league?.members?.find((m) => m.id === player?.id)?.role === 'admin';

  return (
    <div>
      <PageHeader
        title={league?.name ?? 'Standings'}
        eyebrow="Season standings"
        action={
          league ? (
            <LeagueActionsMenu slug={slug} leagueName={league.name} isAdmin={!!isAdmin} />
          ) : undefined
        }
      />

      <LeagueSwitchStrip currentSlug={slug} />

      {isLoading && (
        <div className="space-y-2" aria-label="Loading standings">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState title="Couldn’t load standings" description="Check your connection and try again." />
      )}

      {!isLoading && !isError && standings.length === 0 && (
        <EmptyState
          title="No points on the board yet"
          description="Standings fill in once picks are settled each week."
        />
      )}

      {standings.length > 0 && (
        <ol className="flex flex-col gap-2" data-testid="standings">
          {standings.map((s) => {
            const isMe = s.player_id === player?.id;
            return (
              <li key={s.player_id} data-testid={`standing-${s.rank}`}>
                <Link
                  to={`/leagues/${slug}/players/${s.player_id}`}
                  className={cn(
                    'flex items-center gap-3 rounded-lg border p-3 transition-colors press-down focus-visible:outline-none focus-visible:shadow-glow',
                    isMe
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border bg-surface hover:border-primary/40',
                  )}
                >
                  <span className="w-6 shrink-0 text-center font-mono text-sm tabular-nums text-text-muted">
                    {s.rank}
                  </span>
                  <Avatar name={s.display_name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className={cn('truncate text-sm font-sans', isMe ? 'font-semibold text-primary' : 'text-text-primary')}>
                      {s.display_name}
                    </p>
                    <p className="text-xs font-sans text-text-muted">
                      {s.picks_won}/{s.picks_played} won
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-mono text-lg font-semibold tabular-nums text-text-primary">{s.total_points}</p>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-text-muted">pts</p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
