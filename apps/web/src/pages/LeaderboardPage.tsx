import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useRouteLeague } from '../hooks/useRouteLeague';
import type { LeagueDetail, Standing } from '../lib/types';
import { PickShapeLine, VoidDenominatorNote, hasPickShape } from '../components/PickShapeLine';
import { PickFormLine } from '../components/PickFormLine';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Avatar } from '../components/ui/avatar';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { LeagueActionsMenu } from '../components/LeagueActionsMenu';
import { cn } from '../lib/utils';

export function LeaderboardPage() {
  const { slug } = useRouteLeague();
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
        <>
        {/* Said once for the table rather than on every row: the odds figures and the
            played count have different denominators, and a leaderboard that shows both
            without saying so is lying quietly. */}
        <VoidDenominatorNote
          shape={{
            picks_played: standings.reduce((n, s) => n + s.picks_played, 0),
            picks_priced: standings.reduce((n, s) => n + (s.picks_priced ?? s.picks_played), 0),
          }}
        />
        {/* Batch 80. `V` is the letter a reader will not guess, and it is exactly the one
            that must not be mistaken for a defeat — a void fixture never ran. Said once
            for the table, like the denominator note above it. */}
        {standings.some((s) => (s.recent_form?.length ?? 0) > 0) && (
          <p className="mt-1 font-sans text-[11px] text-text-muted">
            Form covers the last five settled rounds, oldest first — W won, L lost, V void
            — with what each one scored.
          </p>
        )}
        <ol className="mt-2 flex flex-col gap-2" data-testid="standings">
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
                    {/* Batch 70: the owner's fifth point. Renders nothing at all when the
                        deployed API has not shipped the figures yet. Batch 80's run sits
                        beside it and follows the same rule. */}
                    {(hasPickShape(s) || (s.recent_form?.length ?? 0) > 0) && (
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                        <PickShapeLine shape={s} />
                        <PickFormLine form={s.recent_form} player={s.display_name} />
                      </div>
                    )}
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
        </>
      )}
    </div>
  );
}
