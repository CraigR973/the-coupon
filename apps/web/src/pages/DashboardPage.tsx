import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Lock, Ticket, Trophy } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { gameweekKey, couponKey } from '../hooks/usePickEditor';
import type { Coupon, GameweekSlate, SelectionOption, Standing } from '../lib/types';
import { formatOdds, outcomeLabel } from '../lib/coupon';
import { PageHeader } from '../components/PageHeader';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';

const FAR_PAST = new Date(0).toISOString();

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return 'Locked';
  if (p.days > 0) return `${p.days}d ${p.hours}h`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m`;
  return `${p.minutes}m ${p.seconds}s`;
}

function findMyPick(slate: GameweekSlate | undefined) {
  if (!slate) return null;
  for (const fixture of slate.fixtures) {
    const sel = fixture.selections.find((s: SelectionOption) => s.mine);
    if (sel) return { fixture, sel };
  }
  return null;
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('rounded-lg border border-border bg-surface p-4', className)}>{children}</div>;
}

export function DashboardPage() {
  const { player } = useAuth();
  const oddsFormat = useOddsFormat();
  const { activeSlug: slug, leagues } = useLeague();
  const leagueName = leagues.find((l) => l.slug === slug)?.name;

  const { data: slate, isLoading: slateLoading } = useQuery<GameweekSlate>({
    queryKey: gameweekKey(slug),
    queryFn: () => apiFetch<GameweekSlate>(`/api/v1/leagues/${slug}/gameweek/current`),
    staleTime: 30_000,
    retry: false,
  });

  const { data: coupon } = useQuery<Coupon>({
    queryKey: couponKey(slug),
    queryFn: () => apiFetch<Coupon>(`/api/v1/leagues/${slug}/coupon`),
    staleTime: 30_000,
    retry: false,
  });

  const { data: standings = [] } = useQuery<Standing[]>({
    queryKey: ['standings', slug],
    queryFn: () => apiFetch<Standing[]>(`/api/v1/leagues/${slug}/standings`),
    staleTime: 30_000,
    retry: false,
  });

  const countdown = useCountdown(slate?.locks_at_utc ?? FAR_PAST);
  const locked = !slate || slate.status !== 'open' || countdown.expired;
  const myPick = findMyPick(slate);
  const myStanding = standings.find((s) => s.player_id === player?.id);
  const topThree = standings.slice(0, 3);

  return (
    <div>
      <PageHeader title={`Hi ${player?.displayName ?? 'there'}`} eyebrow={leagueName ?? 'The Coupon'} />

      <div className="flex flex-col gap-4">
        {/* This week's pick */}
        <Link to="/predictions" className="block rounded-lg focus-visible:outline-none focus-visible:shadow-glow">
          <Card className="transition-colors hover:border-primary/50">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Ticket className="h-4 w-4 text-primary" aria-hidden />
                <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
                  This week's pick
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-text-muted" aria-hidden />
            </div>

            {slateLoading ? (
              <Skeleton className="h-6 w-40" />
            ) : !slate ? (
              <p className="text-sm font-sans text-text-muted">No coupon published yet.</p>
            ) : myPick ? (
              <>
                <p className="text-sm font-sans font-medium text-text-primary">
                  {outcomeLabel(myPick.sel.market, myPick.sel.outcome, myPick.fixture.home, myPick.fixture.away)}
                  <span className="mx-1.5 text-text-muted">·</span>
                  <span className="font-mono tabular-nums">{formatOdds(myPick.sel.odds, oddsFormat)}</span>
                </p>
                <p className="mt-0.5 text-xs font-sans text-text-muted">
                  {myPick.fixture.home} v {myPick.fixture.away}
                </p>
              </>
            ) : (
              <p className="text-sm font-sans font-medium text-warning">
                {locked ? 'No pick made this week' : 'You haven’t grabbed a selection yet'}
              </p>
            )}

            {slate && (
              <div className="mt-3 flex items-center gap-1.5 font-mono text-xs text-text-muted">
                {locked ? <Lock className="h-3.5 w-3.5" aria-hidden /> : <Clock className="h-3.5 w-3.5" aria-hidden />}
                <span className="tabular-nums">
                  {slate.status === 'settled'
                    ? 'Settled'
                    : locked
                      ? 'Locked'
                      : `Locks in ${formatCountdown(countdown)}`}
                </span>
              </div>
            )}
          </Card>
        </Link>

        {/* Combined coupon peek */}
        {coupon && coupon.leg_count > 0 && (
          <Link
            to="/predictions/coupon"
            className="block rounded-lg focus-visible:outline-none focus-visible:shadow-glow"
          >
            <Card className="transition-colors hover:border-primary/50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
                    Combined coupon
                  </p>
                  <p className="mt-1 text-sm font-sans text-text-primary">
                    {coupon.leg_count}-fold ·{' '}
                    <span className="font-mono font-semibold tabular-nums">{formatOdds(coupon.combined_odds, oddsFormat)}</span>
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-text-muted" aria-hidden />
              </div>
            </Card>
          </Link>
        )}

        {/* Standings snippet */}
        <Link
          to={`/leagues/${slug}/leaderboard`}
          className="block rounded-lg focus-visible:outline-none focus-visible:shadow-glow"
        >
          <Card className="transition-colors hover:border-primary/50">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-primary" aria-hidden />
                <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">Standings</p>
              </div>
              <ArrowRight className="h-4 w-4 text-text-muted" aria-hidden />
            </div>

            {topThree.length === 0 ? (
              <p className="text-sm font-sans text-text-muted">No points on the board yet.</p>
            ) : (
              <ol className="flex flex-col gap-1.5">
                {topThree.map((s) => (
                  <li key={s.player_id} className="flex items-center gap-2 text-sm font-sans">
                    <span className="w-5 text-center font-mono text-xs text-text-muted tabular-nums">{s.rank}</span>
                    <span
                      className={cn(
                        'flex-1 truncate',
                        s.player_id === player?.id ? 'font-semibold text-primary' : 'text-text-primary',
                      )}
                    >
                      {s.display_name}
                    </span>
                    <span className="font-mono tabular-nums text-text-secondary">{s.total_points}</span>
                  </li>
                ))}
              </ol>
            )}

            {myStanding && myStanding.rank > 3 && (
              <div className="mt-2 flex items-center gap-2 border-t border-border pt-2 text-sm font-sans">
                <span className="w-5 text-center font-mono text-xs text-text-muted tabular-nums">
                  {myStanding.rank}
                </span>
                <span className="flex-1 truncate font-semibold text-primary">{myStanding.display_name}</span>
                <span className="font-mono tabular-nums text-text-secondary">{myStanding.total_points}</span>
              </div>
            )}
          </Card>
        </Link>
      </div>
    </div>
  );
}
