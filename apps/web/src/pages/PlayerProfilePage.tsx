import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { formatInTimeZone } from 'date-fns-tz';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { formatOdds, marketTag, outcomeLabel, pickStatusLabel } from '../lib/coupon';
import type { PlayerProfile, SettledPick, PickStatus } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { StatCard } from '../components/StatCard';
import { Avatar } from '../components/ui/avatar';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';

const STATUS_VARIANT: Record<PickStatus, 'success' | 'error' | 'muted' | 'default'> = {
  won: 'success',
  lost: 'error',
  void: 'muted',
  pending: 'default',
};

/**
 * One member's record in the league they are being viewed through.
 *
 * Per-league, not career-wide: picks are league-scoped, so a member in three
 * leagues has three records, and summing leagues that may be playing different
 * claim rules would produce a number that means nothing. The league switcher is
 * how you move between them.
 */
export function PlayerProfilePage() {
  const { slug = '', playerId = '' } = useParams<{ slug: string; playerId: string }>();
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const oddsFormat = useOddsFormat();

  const {
    data: profile,
    isLoading,
    isError,
  } = useQuery<PlayerProfile>({
    queryKey: ['player-profile', slug, playerId],
    queryFn: () =>
      apiFetch<PlayerProfile>(`/api/v1/leagues/${slug}/players/${playerId}/profile`),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-6" aria-label="Loading profile">
        <Skeleton className="h-16 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[88px] rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !profile) {
    return (
      <EmptyState
        title="Player not found"
        description="This member either isn't in this league or their profile couldn't be loaded."
      />
    );
  }

  const isSelf = profile.player_id === player?.id;

  return (
    <div className="space-y-7">
      <div className="flex items-center gap-4">
        <Avatar name={profile.display_name} size="lg" className="shrink-0" />
        <PageHeader
          title={profile.display_name}
          eyebrow={isSelf ? 'Your record' : 'Member record'}
          back={{ to: `/leagues/${slug}/leaderboard`, label: 'Leaderboard' }}
        />
      </div>

      <section>
        <h2 className="mb-3 font-sans text-base font-semibold tracking-tight text-text-primary">
          This league
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="profile-stats">
          <StatCard label="Points" value={profile.total_points} />
          <StatCard label="Rank" value={`#${profile.rank}`} />
          <StatCard
            label="Win rate"
            value={profile.win_rate_pct === null ? '—' : `${profile.win_rate_pct}%`}
          />
          <StatCard label="Picks won" value={`${profile.picks_won}/${profile.picks_played}`} />
        </div>
        {profile.win_rate_pct === null && (
          <p className="mt-2 font-sans text-xs text-text-muted">
            Nothing has settled yet — a win rate appears after the first result.
          </p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-sans text-base font-semibold tracking-tight text-text-primary">
            Settled picks
          </h2>
          <Link
            to="/predictions/results"
            className="shrink-0 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted hover:text-text-primary"
          >
            How each week went →
          </Link>
        </div>
        {profile.history.length === 0 ? (
          <EmptyState
            title="No settled picks yet"
            description="Picks appear here once their gameweek has been settled."
          />
        ) : (
          <ol className="flex flex-col gap-2" data-testid="profile-history">
            {profile.history.map((pick) => (
              <HistoryRow
                key={`${pick.gameweek_id}:${pick.fixture_id}`}
                pick={pick}
                timezone={timezone}
                oddsFormat={oddsFormat}
              />
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function HistoryRow({
  pick,
  timezone,
  oddsFormat,
}: {
  pick: SettledPick;
  timezone: string;
  oddsFormat: ReturnType<typeof useOddsFormat>;
}) {
  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-lg border border-border bg-surface p-3',
        pick.status === 'lost' && 'opacity-60',
      )}
      data-testid={`history-${pick.fixture_id}`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-sans text-sm font-medium text-text-primary">
            {outcomeLabel(pick.market, pick.outcome, pick.home, pick.away)}
          </p>
          <Badge variant="muted">{marketTag(pick.market)}</Badge>
        </div>
        <p className="truncate font-sans text-xs text-text-muted">
          {pick.competition}
          <span className="mx-1.5">·</span>
          {pick.home} v {pick.away}
          <span className="mx-1.5">·</span>
          {formatInTimeZone(new Date(pick.starts_on), timezone, 'd MMM yyyy')}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-0.5">
        <span className="font-mono text-sm tabular-nums text-text-primary">
          {pick.points_awarded ?? 0} pts
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] tabular-nums text-text-muted">
            {formatOdds(pick.odds, oddsFormat)}
          </span>
          <Badge variant={STATUS_VARIANT[pick.status]}>{pickStatusLabel(pick.status)}</Badge>
        </span>
      </div>
    </li>
  );
}
