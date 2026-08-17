import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { formatInTimeZone } from 'date-fns-tz';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import type { CompetitionTable, ResultEntry } from '../lib/types';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { LeagueTableCard } from '../components/LeagueTableCard';
import { EmptyState } from '../components/EmptyState';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs } from '../components/ui/tabs';

type View = 'tables' | 'results';

const VIEWS = [
  { value: 'tables' as const, label: 'Tables' },
  { value: 'results' as const, label: 'Results' },
];

/**
 * League tables and previous results for the competitions this league plays.
 *
 * The standalone half of Batch 16 — the inline half is the position and form that
 * sit beside each game on the pick screen.
 *
 * Both queries are cheap and unchanging by the hour: the data behind them is
 * written by a daily ingestion job, not fetched live, so a long `staleTime` costs
 * nothing in freshness and saves a request on every tab switch.
 */
export function FootballPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const { activeSlug: slug, activeLeagueName, hasLeagues, isLoading: leaguesLoading } = useLeague();
  const [view, setView] = useState<View>('tables');

  const tables = useQuery<CompetitionTable[]>({
    queryKey: ['football', 'tables', slug],
    queryFn: () => apiFetch<CompetitionTable[]>(`/api/v1/leagues/${slug}/football/tables`),
    staleTime: 5 * 60_000,
    enabled: hasLeagues,
  });
  const results = useQuery<ResultEntry[]>({
    queryKey: ['football', 'results', slug],
    queryFn: () => apiFetch<ResultEntry[]>(`/api/v1/leagues/${slug}/football/results`),
    staleTime: 5 * 60_000,
    enabled: hasLeagues,
  });

  const active = view === 'tables' ? tables : results;
  // The API's shape becomes the UI's assumption here, so it is checked here.
  const tableList = Array.isArray(tables.data) ? tables.data : [];
  const resultList = Array.isArray(results.data) ? results.data : [];

  if (!leaguesLoading && !hasLeagues) {
    return (
      <div>
        <PageHeader title="Football" />
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
        title="Football"
        eyebrow={activeLeagueName ? `${activeLeagueName} · Tables & results` : 'Tables & results'}
      />
      <LeagueSwitchStrip currentSlug={slug} className="mb-5" />
      <CouponSubNav />

      <Tabs items={VIEWS} value={view} onChange={setView} className="mb-4" variant="segmented" />

      {active.isLoading && (
        <div className="space-y-3" aria-label="Loading football data">
          <Skeleton className="h-[220px] w-full rounded-lg" />
          <Skeleton className="h-[220px] w-full rounded-lg" />
        </div>
      )}

      {active.isError && (
        <EmptyState
          title="Couldn't load the football data"
          description={
            active.error instanceof Error ? active.error.message : 'Please try again shortly.'
          }
        />
      )}

      {view === 'tables' && !tables.isLoading && !tables.isError && (
        <TablesView tables={tableList} timezone={timezone} />
      )}

      {view === 'results' && !results.isLoading && !results.isError && (
        <ResultsView results={resultList} timezone={timezone} />
      )}
    </div>
  );
}

function TablesView({ tables, timezone }: { tables: CompetitionTable[]; timezone: string }) {
  if (tables.length === 0) {
    return (
      <EmptyState
        title="No tables yet"
        description="Tables appear once the football data has been pulled in for the competitions this league plays. Cup rounds never have one."
      />
    );
  }
  return (
    <div className="flex flex-col gap-4" data-testid="football-tables">
      {tables.map((table, index) => (
        <LeagueTableCard
          key={table.competition_id}
          table={table}
          timezone={timezone}
          // Only the first is expanded: a league playing thirty divisions would
          // otherwise open onto several hundred rows.
          defaultOpen={index === 0}
        />
      ))}
    </div>
  );
}

interface ResultDay {
  day: string;
  results: ResultEntry[];
}

/**
 * Results newest first, grouped by the day they were played.
 *
 * Grouped because a flat list of eighty matches across four competitions and three
 * weekends reads as one undifferentiated column; the date is the thing a member
 * scans for.
 */
function groupByDay(results: ResultEntry[], timezone: string): ResultDay[] {
  const days = new Map<string, ResultEntry[]>();
  for (const result of results) {
    const day = formatInTimeZone(new Date(result.kickoff_utc), timezone, 'EEEE d MMMM');
    const bucket = days.get(day) ?? [];
    bucket.push(result);
    days.set(day, bucket);
  }
  return [...days.entries()].map(([day, dayResults]) => ({ day, results: dayResults }));
}

function ResultsView({ results, timezone }: { results: ResultEntry[]; timezone: string }) {
  const days = useMemo(() => groupByDay(results, timezone), [results, timezone]);

  if (results.length === 0) {
    return (
      <EmptyState
        title="No results yet"
        description="Previous results appear once the football data has been pulled in for the competitions this league plays."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="football-results">
      {days.map(({ day, results: dayResults }) => (
        <section key={day}>
          <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
            {day}
          </h2>
          <ul className="overflow-hidden rounded-lg border border-border bg-surface">
            {dayResults.map((result) => (
              <li
                key={result.match_id}
                className="flex items-center gap-3 border-b border-border/50 px-3 py-2.5 last:border-0"
                data-testid={`result-${result.match_id}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-sans text-text-primary">
                    <span className="font-medium">{result.home}</span>
                    <span className="mx-1.5 text-text-muted">v</span>
                    <span className="font-medium">{result.away}</span>
                  </p>
                  <p className="truncate font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted">
                    {result.competition}
                  </p>
                </div>
                <span className="shrink-0 rounded-md border border-border bg-surface-elevated px-2 py-1 font-mono text-xs font-semibold tabular-nums text-text-primary">
                  <span className="sr-only">
                    {result.home} {result.home_goals}, {result.away} {result.away_goals}
                  </span>
                  <span aria-hidden>
                    {result.home_goals}–{result.away_goals}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
