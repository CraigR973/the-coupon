import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Clock, Lock, Ticket, Trophy } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useCrossLeagueSummary } from '../hooks/useCrossLeagueSummary';
import { useOddsFormat } from '../hooks/useOddsFormat';
import type { FormRound, GameweekStatus, LastResult, PerLeagueSummary } from '../lib/types';
import { formatOdds, outcomeLabel, roundName } from '../lib/coupon';
import { predictionsPath } from '../lib/leagues';
import { formatCalendarDate } from '../lib/time';
import { PickFormLine } from '../components/PickFormLine';
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
  const round = entry.current_round;
  const countdown = useCountdown(round?.locks_at_utc ?? FAR_PAST);
  const openCountdown = useCountdown(round?.picks_open_at_utc ?? FAR_PAST);
  // The *next* round's opening, which is a different instant to this round's: once a
  // round has settled or locked there is nothing left to count down to on it, and "when
  // does the next one open" is the question a member has on a Sunday.
  const nextOpenCountdown = useCountdown(entry.next_opens_at_utc ?? FAR_PAST);
  const nextOpens = !!entry.next_opens_at_utc && !nextOpenCountdown.expired;
  // Same rule as the pick screen and the API: the stored instants decide, `status` only
  // rules out a round settlement has finished with.
  const notOpenYet =
    !!round?.picks_open_at_utc && !openCountdown.expired && PICKABLE.has(round.status);
  const locked = !round || !PICKABLE.has(round.status) || notOpenYet || countdown.expired;

  // The coupon has its own address per league now, so opening another league's
  // week is just going there: the destination binds the context, rather than this
  // card having to bind it before navigating and hope the two agree.
  function openCoupon() {
    navigate(predictionsPath(entry.slug));
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
          <p className="font-sans text-sm text-text-muted">
            {nextOpens
              ? `Picks open in ${formatCountdown(nextOpenCountdown)}.`
              : 'No coupon published yet.'}
          </p>
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
                  ? nextOpens
                    ? `Next opens in ${formatCountdown(nextOpenCountdown)}`
                    : 'Settled'
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

      {entry.last_result && (
        <LastResultPanel result={entry.last_result} form={entry.recent_form} />
      )}

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

/**
 * How the week just gone actually went (Batch 79).
 *
 * Four facts the card printed the word `Settled` in place of: whether the member's pick
 * came in, what it scored, how many of the league's picks landed, and whether they moved
 * in the table. It is a sibling of the coupon button rather than part of it because the
 * two answer different rounds — on most leagues the round above this panel is next
 * week's, not the one being reported.
 *
 * Movement never rides on colour alone: the arrow is decorative and the direction is a
 * word underneath it, the same rule the live scoreline follows.
 *
 * Batch 81 hangs the season's run of five here rather than on the standings link below.
 * Two reasons, and the second is the binding one: a run belongs with "how it is going"
 * rather than beside a tap target, and `PickFormLine` carries a `role="img"` label that
 * spells the run out in words — nested in a link, that whole sentence is appended to the
 * link's accessible name. A member with any form necessarily has a `last_result`, since
 * both come from a settled round holding that member's pick, so this panel can never be
 * the thing that hides a run.
 */
function LastResultPanel({ result, form }: { result: LastResult; form?: FormRound[] }) {
  const movement = result.rank_movement;
  const mine = result.my_pick;
  const label = roundName(result.number, formatCalendarDate(result.starts_on, 'EEE d MMM'));

  return (
    <div className="border-t border-border px-4 py-3" data-testid="last-result">
      <div className="flex items-center justify-between gap-3">
        <p className="truncate font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          Result · {label}
        </p>
        {movement != null && movement !== 0 && (
          <span
            className={cn(
              'shrink-0 font-mono text-xs tabular-nums',
              movement > 0 ? 'text-success' : 'text-error',
            )}
            data-testid="rank-movement"
          >
            <span aria-hidden>{movement > 0 ? '▲' : '▼'}</span>
            {Math.abs(movement)}
            <span className="sr-only">
              {' '}
              {movement > 0 ? 'places gained' : 'places lost'}
            </span>
          </span>
        )}
      </div>

      <p className="mt-1 font-sans text-sm font-medium text-text-primary">
        {!mine ? (
          <span className="text-text-muted">You didn’t pick this round</span>
        ) : mine.status === 'won' ? (
          <>
            <span className="text-success">Your pick won</span>
            {mine.points_awarded != null && (
              <>
                <span className="mx-1.5 text-text-muted">·</span>
                <span className="font-mono tabular-nums">{mine.points_awarded} pts</span>
              </>
            )}
          </>
        ) : mine.status === 'void' ? (
          // A void pick is not a loss: the fixture never ran, so there was nothing to
          // win. Saying "lost" here would be the same conflation the leaderboard's two
          // denominators exist to avoid.
          <span className="text-text-muted">Your pick was void</span>
        ) : mine.status === 'lost' ? (
          <span className="text-text-muted">Your pick didn’t come in</span>
        ) : (
          <span className="text-text-muted">Your pick hasn’t settled</span>
        )}
      </p>

      <div className="mt-0.5 flex items-end justify-between gap-3">
        <p className="font-sans text-xs text-text-muted">
          {result.leg_count === 0
            ? 'Nobody picked this round'
            : `${result.picks_won} of ${result.leg_count} ${result.leg_count === 1 ? 'pick' : 'picks'} landed`}
        </p>
        <PickFormLine form={form} className="shrink-0" />
      </div>
    </div>
  );
}
