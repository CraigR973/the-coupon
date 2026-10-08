import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useRouteLeague } from '../hooks/useRouteLeague';
import type { LeagueDetail, SeasonSummary, Standing } from '../lib/types';
import { VoidDenominatorNote } from '../components/PickShapeLine';
import { PickFormLine } from '../components/PickFormLine';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { QueryErrorState } from '../components/QueryErrorState';
import { Skeleton } from '../components/ui/skeleton';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { LeagueActionsMenu } from '../components/LeagueActionsMenu';
import { SeasonStrip } from '../components/SeasonStrip';
import { Button } from '../components/ui/button';
import { buildStandingsShareText } from '../lib/share';
import { cn } from '../lib/utils';
import { keys } from '@/lib/queryKeys';

export function LeaderboardPage() {
  const { slug } = useRouteLeague();
  const { player } = useAuth();
  const [params, setParams] = useSearchParams();

  // Batch 96. `null` is the season being played, and it is deliberately the *absence* of
  // a parameter rather than its own value: the ordinary leaderboard link stays clean, and
  // an archived table is addressable, shareable and survives a refresh.
  const seasonParam = params.get('season');
  const season = seasonParam !== null && /^\d+$/.test(seasonParam) ? Number(seasonParam) : null;

  const { data: league } = useQuery<LeagueDetail>({
    queryKey: ['league', slug],
    queryFn: () => apiFetch<LeagueDetail>(`/api/v1/leagues/${slug}`),
    staleTime: 60_000,
  });

  // No error branch on purpose: until the API half of this batch ships, this route 404s
  // and an empty list hides the strip, leaving the page as it was. The season is still
  // sent below — an API that does not know the parameter ignores it.
  const { data: seasons = [] } = useQuery<SeasonSummary[]>({
    queryKey: keys.league.seasons(slug),
    queryFn: () => apiFetch<SeasonSummary[]>(`/api/v1/leagues/${slug}/seasons`),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const {
    data: standings = [],
    isLoading,
    isError,
    refetch,
  } = useQuery<Standing[]>({
    queryKey: keys.standings.forSeason(slug, season),
    queryFn: () =>
      apiFetch<Standing[]>(
        `/api/v1/leagues/${slug}/standings${season !== null ? `?season=${season}` : ''}`,
      ),
    staleTime: 30_000,
  });

  const isAdmin = league?.members?.find((m) => m.id === player?.id)?.role === 'admin';
  const shown = seasons.find((entry) => (season === null ? entry.is_current : entry.season === season));
  const seasonHeading = shown ? `${shown.label} standings` : 'Season standings';

  const selectSeason = (next: number | null) => {
    const updated = new URLSearchParams(params);
    if (next === null) updated.delete('season');
    else updated.set('season', String(next));
    setParams(updated, { replace: true });
  };

  async function copyStandings() {
    if (!league || standings.length === 0) return;
    try {
      await navigator.clipboard.writeText(
        buildStandingsShareText(league.name, seasonHeading, standings),
      );
      toast.success('Standings copied');
    } catch {
      toast.error('Could not copy standings');
    }
  }

  return (
    <div>
      <PageHeader
        title={league?.name ?? 'Standings'}
        /* Batch 170. A league's name is its members' own words and can be long; at 320 it
           was cut off. An <h1> wraps rather than truncates. */
        wrapTitle
        /* The season is named up here as well as in the strip: a member who has followed
           an archived link needs to know which table they are reading without having to
           work it out from the standings themselves. */
        eyebrow={seasonHeading}
        action={
          league ? (
            <LeagueActionsMenu slug={slug} leagueName={league.name} isAdmin={!!isAdmin} />
          ) : undefined
        }
      />

      <LeagueSwitchStrip currentSlug={slug} />

      <SeasonStrip
        seasons={seasons}
        selected={season}
        onSelect={selectSeason}
        className="mt-3"
      />

      {isLoading && (
        <div className="space-y-2" aria-label="Loading standings">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {isError && (
        <QueryErrorState
          title="Couldn’t load standings"
          description="Check your connection and try again."
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && standings.length === 0 && (
        <EmptyState
          title="No points on the board yet"
          description={
            season !== null
              ? 'Nobody scored in this season.'
              : 'Standings fill in once picks are settled each week.'
          }
        />
      )}

      {standings.length > 0 && (
        <>
          <div className="mt-4 mb-3 flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={copyStandings}>
              <Copy className="h-3.5 w-3.5" aria-hidden />
              Copy standings
            </Button>
          </div>
          {/* Said once for the table rather than on every row: the odds figures and the
              played count have different denominators, and a leaderboard that shows both
              without saying so is lying quietly. */}
          <VoidDenominatorNote
            shape={{
              picks_played: standings.reduce((n, s) => n + s.picks_played, 0),
              picks_priced: standings.reduce(
                (n, s) => n + (s.picks_priced ?? s.picks_played),
                0,
              ),
            }}
          />
          {/* Batch 80. `V` is the letter a reader will not guess, and it is exactly the one
              that must not be mistaken for a defeat — a void fixture never ran. Said once
              for the table, like the denominator note above it. */}
          {standings.some((s) => (s.recent_form?.length ?? 0) > 0) && (
            <p className="mt-1 font-sans text-caption text-text-muted">
              Form covers the last five settled rounds, oldest first — W won, L lost, V void
              — with what each one scored.
            </p>
          )}
          <div
            aria-hidden="true"
            className="mt-3 hidden grid-cols-[2rem_minmax(0,1fr)_4rem_4rem_6rem_5rem] gap-2 px-3 font-mono text-caption uppercase tracking-wider text-text-muted lg:grid"
          >
            <span>Rank</span>
            <span>Member and form</span>
            <span className="text-right">Played</span>
            <span className="text-right">Won</span>
            <span className="text-right">Avg odds</span>
            <span className="text-right">Pts</span>
          </div>
          <ol className="mt-2 flex flex-col gap-1.5" data-testid="standings">
            {standings.map((s) => {
              const isMe = s.player_id === player?.id;
              const medal = s.rank === 1 ? 'bg-gold' : s.rank === 2 ? 'bg-silver' : s.rank === 3 ? 'bg-bronze' : null;
              return (
                <li key={s.player_id} data-testid={`standing-${s.rank}`}>
                  <Link
                    to={`/leagues/${slug}/players/${s.player_id}`}
                    className={cn(
                      'relative grid h-[52px] grid-cols-[1.5rem_minmax(0,1fr)_4rem] items-center gap-2 overflow-hidden rounded-lg border px-2 transition-colors press-down focus-visible:outline-none focus-visible:shadow-glow lg:grid-cols-[2rem_minmax(0,1fr)_4rem_4rem_6rem_5rem] lg:px-3',
                      isMe
                        ? 'border-primary/40 bg-primary/[0.08]'
                        : 'border-border bg-surface hover:border-primary/40',
                    )}
                  >
                    {medal && <span aria-hidden="true" data-testid="rank-medal" className={cn('absolute inset-y-0 left-0 w-[3px]', medal)} />}
                    <span className={cn(
                      'text-center font-mono text-sm tabular-nums text-text-muted',
                      s.rank === 1 && 'text-gold-ink',
                      s.rank === 3 && 'text-bronze-ink',
                    )}>
                      {s.rank}
                    </span>
                    <div className="flex min-w-0 flex-col justify-center">
                      <p
                        className={cn(
                          'truncate font-sans text-sm font-semibold leading-[18px]',
                          isMe ? 'text-primary-ink' : 'text-text-primary',
                        )}
                      >
                        {s.display_name}
                      </p>
                      <div className="flex h-7 min-w-0 items-start gap-1.5 overflow-hidden">
                        <PickFormLine form={s.recent_form} player={s.display_name} className="shrink-0" />
                        <span className="shrink-0 font-sans text-caption text-text-muted lg:hidden">
                          {s.picks_won}/{s.picks_played} won
                        </span>
                      </div>
                    </div>
                    <span className="hidden text-right font-mono text-sm tabular-nums text-text-secondary lg:block">{s.picks_played}</span>
                    <span className="hidden text-right font-mono text-sm tabular-nums text-text-secondary lg:block">{s.picks_won}</span>
                    <span className="hidden text-right font-mono text-sm tabular-nums text-text-secondary lg:block">{s.average_odds?.toFixed(2) ?? '—'}</span>
                    <span data-testid="standing-points" className="text-right font-mono text-price tabular-nums text-text-primary">
                      {s.total_points}<span className="sr-only"> points</span>
                    </span>
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
