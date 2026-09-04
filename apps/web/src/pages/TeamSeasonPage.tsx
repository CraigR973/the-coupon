import { useMemo } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import type { TeamSeason, TeamSeasonMatch } from '../lib/types';
import { formatInstant } from '../lib/time';
import { seasonLabel, splitSeason, tablePathFor } from '../lib/teamSeason';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Badge } from '../components/ui/badge';
import { cn } from '../lib/utils';

/** Wording for each non-final state. `scheduled` says nothing — the date already has. */
const STATE_LABEL: Record<string, string> = {
  live: 'Live',
  postponed: 'Postponed',
  cancelled: 'Cancelled',
};

/**
 * One club's whole season in one competition (Batch 111).
 *
 * The table used to be a dead end. A club's name was a label, and the only way into its
 * results was a disclosure hidden behind five form pips — which opened five matches, in
 * a panel, on a control nothing announced. This is the destination that replaces it:
 * one address, the complete season, and the club's name in the table is now the link to
 * it.
 *
 * **Every parameter is in the URL because the answer depends on all three.** A club
 * plays a league and a cup in the same year and has a season for each, so neither the
 * competition nor the season is inferable from the team id — and a member sharing what
 * they are looking at should not have the other person land somewhere else.
 *
 * Reads Batch 110's `GET /football/teams/{id}/season`, which is database-only. Nothing
 * on this screen can reach a provider.
 */
export function TeamSeasonPage() {
  const { teamId = '' } = useParams();
  const [params] = useSearchParams();
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';

  const competition = params.get('competition') ?? '';
  const seasonParam = Number(params.get('season'));
  const season = Number.isFinite(seasonParam) && seasonParam > 0 ? seasonParam : undefined;

  const query = useQuery<TeamSeason>({
    queryKey: ['football', 'team-season', teamId, competition, season ?? 'default'],
    queryFn: () => {
      const search = new URLSearchParams({ competition });
      if (season !== undefined) search.set('season', String(season));
      return apiFetch<TeamSeason>(`/api/v1/football/teams/${teamId}/season?${search}`);
    },
    // A season is written by the same daily job the tables are, so it is no fresher
    // than they are and costs a request every time a member steps back and forward.
    staleTime: 5 * 60_000,
    enabled: Boolean(teamId && competition),
  });

  const { results, fixtures, next } = useMemo(() => splitSeason(query.data), [query.data]);
  const backTo = tablePathFor(competition, season ?? query.data?.season ?? 0);

  return (
    <div>
      <PageHeader
        title={query.data?.team ?? 'Season'}
        eyebrow={
          query.data
            ? `${query.data.competition} · ${seasonLabel(query.data.season)}`
            : 'Team season'
        }
      />

      {competition && (
        <Link
          to={backTo}
          className="mb-4 inline-flex items-center gap-1 rounded-md px-1 py-1 font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted tap-target press-down hover:text-text-primary focus-visible:outline-none focus-visible:shadow-glow"
          data-testid="back-to-table"
        >
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
          Back to table
        </Link>
      )}

      {!competition && (
        <EmptyState
          title="No competition named"
          description="A club plays more than one competition in a season, so this page needs to know which one. Open it from a league table."
        />
      )}

      {competition && query.isLoading && (
        <div className="space-y-3" aria-label="Loading the season">
          <Skeleton className="h-[180px] w-full rounded-lg" />
          <Skeleton className="h-[180px] w-full rounded-lg" />
        </div>
      )}

      {competition && query.isError && (
        <EmptyState
          title="Couldn't load this season"
          description={
            query.error instanceof Error ? query.error.message : 'Please try again shortly.'
          }
        />
      )}

      {competition && query.isSuccess && results.length === 0 && fixtures.length === 0 && (
        <EmptyState
          title="Nothing stored for this season yet"
          description="Matches appear once the football data has been pulled in for this competition and season."
        />
      )}

      {competition && query.isSuccess && (results.length > 0 || fixtures.length > 0) && (
        <div className="flex flex-col gap-4" data-testid="team-season">
          {fixtures.length > 0 && (
            <MatchSection
              heading="Fixtures"
              matches={fixtures}
              timezone={timezone}
              nextId={next?.match_id ?? null}
              testId="team-season-fixtures"
            />
          )}
          {results.length > 0 && (
            <MatchSection
              heading="Results"
              matches={results}
              timezone={timezone}
              nextId={null}
              testId="team-season-results"
            />
          )}
        </div>
      )}
    </div>
  );
}

function MatchSection({
  heading,
  matches,
  timezone,
  nextId,
  testId,
}: {
  heading: string;
  matches: TeamSeasonMatch[];
  timezone: string;
  nextId: string | null;
  testId: string;
}) {
  return (
    <section data-testid={testId}>
      <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
        {heading}
      </h2>
      <ul className="overflow-hidden rounded-lg border border-border bg-surface">
        {matches.map((match) => (
          <MatchRow
            key={match.match_id}
            match={match}
            timezone={timezone}
            isNext={match.match_id === nextId}
          />
        ))}
      </ul>
    </section>
  );
}

/**
 * One match, readable without colour and without the score's orientation being guessed.
 *
 * `goals_for`/`goals_against` are already from this club's point of view, so `2–1` is a
 * win whether the club was home or away, and `H`/`A` says which — the same rule the form
 * panel followed, kept because it is the thing that makes a bare scoreline mean
 * something.
 */
function MatchRow({
  match,
  timezone,
  isNext,
}: {
  match: TeamSeasonMatch;
  timezone: string;
  isNext: boolean;
}) {
  const played = match.goals_for !== null && match.goals_against !== null;
  const stateLabel = STATE_LABEL[match.state];
  const kickoff = formatInstant(match.kickoff_utc, timezone, 'd MMM') ?? '';
  const time = formatInstant(match.kickoff_utc, timezone, 'HH:mm') ?? '';

  return (
    <li
      className={cn(
        'flex items-center gap-3 border-b border-border/50 px-3 py-2.5 last:border-0',
        isNext && 'bg-primary/10',
      )}
      data-testid={`team-match-${match.match_id}`}
      data-next={isNext ? 'true' : undefined}
    >
      <div className="w-16 shrink-0 font-mono text-[10px] uppercase tracking-wide text-text-muted">
        <span className="block">{kickoff}</span>
        {!played && <span className="block opacity-70">{time}</span>}
      </div>

      <span aria-hidden className="w-3 shrink-0 font-mono text-[10px] font-semibold text-text-muted">
        {match.home ? 'H' : 'A'}
      </span>
      <span className="sr-only">{match.home ? 'home to' : 'away to'}</span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-sans text-text-primary">{match.opponent}</p>
        {(stateLabel || isNext) && (
          <div className="mt-0.5 flex items-center gap-1.5">
            {isNext && (
              <Badge variant="success" data-testid="next-fixture-badge">
                Next
              </Badge>
            )}
            {stateLabel && (
              <span
                className={cn(
                  'font-mono text-[10px] uppercase tracking-[0.15em]',
                  match.state === 'live' ? 'text-primary' : 'text-text-muted',
                )}
              >
                {stateLabel}
              </span>
            )}
          </div>
        )}
      </div>

      {played ? (
        <span className="shrink-0 rounded-md border border-border bg-surface-elevated px-2 py-1 font-mono text-xs font-semibold tabular-nums text-text-primary">
          <span className="sr-only">
            {match.result === 'W' ? 'won' : match.result === 'L' ? 'lost' : 'drew'}{' '}
            {match.goals_for}–{match.goals_against}
          </span>
          <span aria-hidden>
            {match.goals_for}–{match.goals_against}
          </span>
        </span>
      ) : (
        /* A fixture has no score, and an em dash says so without pretending to be 0–0. */
        <span
          aria-hidden
          className="shrink-0 rounded-md border border-dashed border-border px-2 py-1 font-mono text-xs text-text-muted"
        >
          —
        </span>
      )}

      {match.result && (
        <span
          aria-hidden
          className={cn(
            'w-3 shrink-0 text-center font-mono text-[10px] font-semibold',
            match.result === 'W'
              ? 'text-success'
              : match.result === 'L'
                ? 'text-error'
                : 'text-text-muted',
          )}
        >
          {match.result}
        </span>
      )}
    </li>
  );
}
