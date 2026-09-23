import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useCrossLeagueSummary } from '../hooks/useCrossLeagueSummary';
import type { PerLeagueSummary } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { StatCard } from '../components/StatCard';
import { PickShapeGrid, PickShapeLine, hasPickShape } from '../components/PickShapeLine';
import { Avatar } from '../components/ui/avatar';
import { Skeleton } from '../components/ui/skeleton';

/**
 * The member's own record across every league they play.
 *
 * Batch 13 rejected a career-wide profile wholesale; this splits the question by
 * figure instead of answering it once. **Points and win rate aggregate** — every
 * league scores `round(odds × 10)` off the same scale, so a season total across
 * three leagues is a real number. **Rank does not**: first of three and first of
 * fifteen are not the same achievement, so Batch 157 dropped the averaged rank
 * entirely, and the only ranks shown are the per-league ones in the breakdown.
 *
 * The breakdown links into each league's own profile, which is where a pick's
 * history belongs — a pick's meaning is partly who else could have taken it.
 */
export function CareerProfilePage() {
  const { player } = useAuth();

  const { data, isLoading, isError } = useCrossLeagueSummary();

  if (isLoading) {
    return (
      <div className="space-y-6" aria-label="Loading profile">
        <Skeleton className="h-16 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[88px] rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <EmptyState
        title="Couldn't load your record"
        description="Please try again shortly."
      />
    );
  }

  return (
    <div className="space-y-7">
      <div className="flex items-center gap-4">
        <Avatar name={player?.displayName ?? '?'} size="lg" className="shrink-0" />
        <PageHeader title={player?.displayName ?? 'Your record'} eyebrow="Your record" />
      </div>

      <section>
        <h2 className="mb-3 font-sans text-base font-semibold tracking-tight text-text-primary">
          Across your leagues
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="career-stats">
          <StatCard label="Points" value={data.total_points} />
          <StatCard
            label="Win rate"
            value={data.win_rate_pct === null ? '—' : `${data.win_rate_pct}%`}
          />
          <StatCard label="Picks won" value={`${data.picks_won}/${data.picks_played}`} />
        </div>
        {/* Batch 157, owner's decision 2026-09-22: the averaged rank is gone. The
            contract says points and win rate aggregate across leagues and rank does not,
            and a mean of ranks taken in leagues of different sizes is not a number
            anybody can act on — third of fifteen and third of three are not the same
            achievement. The per-league ranks below are where rank means something. */}
        <p className="mt-2 font-sans text-xs text-text-muted">
          Points and win rate cover every league. Rank does not average across them — the
          per-league ranks below are the ones to compare.
        </p>
      </section>

      {/* Batch 70. Summed across leagues rather than averaged: every league prices in the
          same decimal odds, so a cumulative total across three of them is a real number. */}
      {hasPickShape(data) && (
        <section data-testid="career-pick-shape">
          <h2 className="mb-3 font-sans text-base font-semibold tracking-tight text-text-primary">
            What you pick
          </h2>
          <PickShapeGrid shape={data} />
        </section>
      )}

      <section>
        <h2 className="mb-3 font-sans text-base font-semibold tracking-tight text-text-primary">
          By league
        </h2>
        {data.per_league.length === 0 ? (
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
        ) : (
          <ul className="flex flex-col gap-2" data-testid="career-leagues">
            {data.per_league.map((entry) => (
              <li key={entry.slug}>
                <LeagueRecordRow entry={entry} playerId={player?.id ?? ''} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function LeagueRecordRow({ entry, playerId }: { entry: PerLeagueSummary; playerId: string }) {
  return (
    <Link
      to={`/leagues/${entry.slug}/players/${playerId}`}
      className="flex items-center gap-3 rounded-lg border border-border bg-surface p-3 transition-colors press-down hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
      data-testid={`career-league-${entry.slug}`}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate font-sans text-sm font-medium text-text-primary">{entry.name}</p>
        <p className="font-sans text-xs text-text-muted">
          {entry.rank === null ? 'Unranked' : `#${entry.rank} of ${entry.member_count}`}
          <span className="mx-1.5">·</span>
          {entry.picks_won}/{entry.picks_played} won
        </p>
        <PickShapeLine shape={entry} />
      </div>
      <span className="shrink-0 font-mono text-sm tabular-nums text-text-primary">
        {entry.total_points} pts
      </span>
      <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden />
    </Link>
  );
}
