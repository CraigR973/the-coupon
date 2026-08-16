import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Clock, Lock, Ticket, Trophy } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useCrossLeagueSummary } from '../hooks/useCrossLeagueSummary';
import { useOddsFormat } from '../hooks/useOddsFormat';
import type { GameweekStatus, PerLeagueSummary } from '../lib/types';
import { formatOdds, outcomeLabel } from '../lib/coupon';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';

const FAR_PAST = new Date(0).toISOString();

/** The two states a round can still be claimed in — settlement has finished with the rest. */
const PICKABLE: ReadonlySet<GameweekStatus> = new Set(['scheduled', 'open']);

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return 'Locked';
  if (p.days > 0) return `${p.days}d ${p.hours}h`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m`;
  return `${p.minutes}m ${p.seconds}s`;
}

/**
 * Home, once per league.
 *
 * It used to answer for `activeSlug` alone — one pick, one coupon peek, one
 * standings card — which is the wrong question for a member in three leagues:
 * two of their weeks were invisible until they switched. Every league the member
 * plays now gets a card carrying that league's pick and standing, and one tap
 * opens that league's coupon. The whole page is one request
 * (`GET /me/cross-league-summary`), not three per league.
 */
export function DashboardPage() {
  const { player } = useAuth();

  const { data, isLoading, isError } = useCrossLeagueSummary();
  const leagues = data?.per_league ?? [];

  return (
    <div>
      <PageHeader title={`Hi ${player?.displayName ?? 'there'}`} eyebrow="The Coupon" />

      {isLoading && (
        <div className="flex flex-col gap-4" aria-label="Loading your leagues">
          <Skeleton className="h-[132px] w-full rounded-lg" />
          <Skeleton className="h-[132px] w-full rounded-lg" />
        </div>
      )}

      {isError && (
        <EmptyState
          title="Couldn't load your leagues"
          description="Please try again shortly."
        />
      )}

      {!isLoading && !isError && leagues.length === 0 && (
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
      )}

      {leagues.length > 0 && (
        <ul className="flex flex-col gap-4" data-testid="home-league-cards">
          {leagues.map((entry) => (
            <li key={entry.slug}>
              <LeagueHomeCard entry={entry} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LeagueHomeCard({ entry }: { entry: PerLeagueSummary }) {
  const oddsFormat = useOddsFormat();
  const navigate = useNavigate();
  const { selectLeague } = useLeague();
  const round = entry.current_round;
  const countdown = useCountdown(round?.locks_at_utc ?? FAR_PAST);
  const openCountdown = useCountdown(round?.picks_open_at_utc ?? FAR_PAST);
  // Same rule as the pick screen and the API: the stored instants decide, `status` only
  // rules out a round settlement has finished with.
  const notOpenYet =
    !!round?.picks_open_at_utc && !openCountdown.expired && PICKABLE.has(round.status);
  const locked = !round || !PICKABLE.has(round.status) || notOpenYet || countdown.expired;

  // The coupon screens read `activeSlug`, so opening another league's week means
  // binding to it first — otherwise the tap lands on whichever league was already
  // in context.
  function openCoupon() {
    selectLeague(entry.slug);
    navigate('/predictions');
  }

  return (
    <div className="rounded-lg border border-border bg-surface" data-testid={`home-card-${entry.slug}`}>
      <button
        type="button"
        onClick={openCoupon}
        className="w-full rounded-t-lg p-4 text-left transition-colors press-down hover:border-primary/50 hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
      >
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Ticket className="h-4 w-4 shrink-0 text-primary" aria-hidden />
            <p className="truncate font-sans text-sm font-semibold text-text-primary">{entry.name}</p>
          </div>
          <ArrowRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden />
        </div>

        {!round ? (
          <p className="font-sans text-sm text-text-muted">No coupon published yet.</p>
        ) : round.my_pick ? (
          <>
            <p className="font-sans text-sm font-medium text-text-primary">
              {outcomeLabel(
                round.my_pick.market,
                round.my_pick.outcome,
                round.my_pick.home,
                round.my_pick.away,
              )}
              <span className="mx-1.5 text-text-muted">·</span>
              <span className="font-mono tabular-nums">
                {formatOdds(round.my_pick.odds, oddsFormat)}
              </span>
            </p>
            <p className="mt-0.5 truncate font-sans text-xs text-text-muted">
              {round.my_pick.home} v {round.my_pick.away}
            </p>
          </>
        ) : (
          <p className="font-sans text-sm font-medium text-warning">
            {notOpenYet
              ? 'Picks haven’t opened yet'
              : locked
                ? 'No pick made this week'
                : 'You haven’t grabbed a selection yet'}
          </p>
        )}

        {round && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-text-muted">
            <span className="flex items-center gap-1.5">
              {locked && !notOpenYet ? (
                <Lock className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Clock className="h-3.5 w-3.5" aria-hidden />
              )}
              <span className="tabular-nums">
                {round.status === 'settled'
                  ? 'Settled'
                  : notOpenYet
                    ? `Opens in ${formatCountdown(openCountdown)}`
                    : locked
                      ? 'Locked'
                      : `Locks in ${formatCountdown(countdown)}`}
              </span>
            </span>
            {round.leg_count > 0 && (
              <span className="tabular-nums">
                {round.leg_count}-fold · {formatOdds(round.combined_odds, oddsFormat)}
              </span>
            )}
          </div>
        )}
      </button>

      <Link
        to={`/leagues/${entry.slug}/leaderboard`}
        className="flex items-center justify-between gap-3 rounded-b-lg border-t border-border px-4 py-2.5 transition-colors hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          <Trophy className="h-3.5 w-3.5 text-primary" aria-hidden />
          Standings
        </span>
        <span className="font-mono text-xs tabular-nums text-text-secondary">
          <span className={cn(entry.rank === 1 && 'font-semibold text-primary')}>
            {entry.rank === null ? '—' : `#${entry.rank}`}
          </span>
          <span className="mx-1.5 text-text-muted">of {entry.member_count}</span>
          <span className="text-text-muted">·</span>
          <span className="ml-1.5">{entry.total_points} pts</span>
        </span>
      </Link>
    </div>
  );
}
