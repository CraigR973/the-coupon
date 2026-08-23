import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import type { CompetitionTable, ResultEntry } from '../lib/types';
import { compareCompetitions } from '../lib/competitions';
import { formatInstant } from '../lib/time';
import { PageHeader } from '../components/PageHeader';
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
 * League tables and previous results across every competition we hold data for.
 *
 * The standalone half of Batch 16 — the inline half is the position and form that
 * sit beside each game on the pick screen.
 *
 * **Not a coupon surface since Batch 51.** It used to live at
 * `/leagues/:slug/predictions/football` and show only the competitions that league
 * played, which is the subset of football the reader's own card happened to cover
 * rather than the football they opened the screen to read. Nothing about the data
 * was ever league-scoped — one shared pool, ingested once — so untying it took a
 * league off the address, the switcher off the page (it would have been a control
 * that changed nothing) and the sub-nav with it. A member of no league can read it
 * too, which is why neither query waits on the league context.
 *
 * Both queries are cheap and unchanging by the hour: the data behind them is
 * written by a daily ingestion job, not fetched live, so a long `staleTime` costs
 * nothing in freshness and saves a request on every tab switch.
 */
export function FootballPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const [view, setView] = useState<View>('tables');

  const tables = useQuery<CompetitionTable[]>({
    queryKey: ['football', 'tables'],
    queryFn: () => apiFetch<CompetitionTable[]>('/api/v1/football/tables'),
    staleTime: 5 * 60_000,
  });
  const results = useQuery<ResultEntry[]>({
    queryKey: ['football', 'results'],
    queryFn: () => apiFetch<ResultEntry[]>('/api/v1/football/results'),
    staleTime: 5 * 60_000,
  });

  const active = view === 'tables' ? tables : results;
  // The API's shape becomes the UI's assumption here, so it is checked here.
  const tableList = Array.isArray(tables.data) ? tables.data : [];
  const resultList = Array.isArray(results.data) ? results.data : [];

  return (
    <div>
      <PageHeader title="Football Stats" eyebrow="Tables & results" />

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
  // The pick screen's order, not the ingestion job's. These are the same divisions a
  // member has just been reading down the coupon, so arriving at them shuffled costs a
  // search every time — `lib/competitions` is the one order both screens read in.
  const ordered = useMemo(() => [...tables].sort(compareCompetitions), [tables]);

  if (tables.length === 0) {
    return (
      <EmptyState
        title="No tables yet"
        description="Tables appear once the football data has been pulled in. We cover every competition a coupon has drawn from — not every competition in Britain — and cup rounds never have a table."
      />
    );
  }
  return (
    <div className="flex flex-col gap-4" data-testid="football-tables">
      {ordered.map((table) => (
        <LeagueTableCard
          key={table.competition_id}
          table={table}
          timezone={timezone}
          // Every division starts closed (Batch 71). One-of-thirty-open was the right
          // instinct — thirty expanded tables is several hundred rows — with the wrong
          // answer: the reader has not asked for *any* of them yet, and opening the one
          // that happens to sort first makes it look chosen. The owner asked for the
          // screen collapsed on open.
          defaultOpen={false}
        />
      ))}
    </div>
  );
}

interface CompetitionGroup {
  competition_id: string;
  competition: string;
  results: ResultEntry[];
}

interface ResultDay {
  day: string;
  competitions: CompetitionGroup[];
}

/**
 * Results newest first, grouped by the day they were played and then by competition.
 *
 * Day stays the outer key: it is what a member scans for first. But a Saturday can
 * hold eighty matches across four competitions, and a flat list under one heading
 * reads as an undifferentiated column — the same failure this grouping was built to
 * fix, one level up. So each day's matches are grouped by competition too.
 */
function groupByDay(results: ResultEntry[], timezone: string): ResultDay[] {
  const days = new Map<string, Map<string, CompetitionGroup>>();
  for (const result of results) {
    const day = formatInstant(result.kickoff_utc, timezone, 'EEEE d MMMM') ?? result.kickoff_utc;
    const competitions = days.get(day) ?? new Map<string, CompetitionGroup>();
    days.set(day, competitions);
    const group = competitions.get(result.competition_id) ?? {
      competition_id: result.competition_id,
      competition: result.competition,
      results: [],
    };
    group.results.push(result);
    competitions.set(result.competition_id, group);
  }
  return [...days.entries()].map(([day, competitions]) => ({
    day,
    // Within a day, the same order the coupon lists competitions in — insertion order
    // here is the order results happened to arrive in, which is no order at all.
    competitions: [...competitions.values()].sort(compareCompetitions),
  }));
}

function ResultsView({ results, timezone }: { results: ResultEntry[]; timezone: string }) {
  const days = useMemo(() => groupByDay(results, timezone), [results, timezone]);

  if (results.length === 0) {
    return (
      <EmptyState
        title="No results yet"
        description="Previous results appear once the football data has been pulled in. We cover every competition a coupon has drawn from — not every competition in Britain."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="football-results">
      {days.map(({ day, competitions }) => (
        <section key={day}>
          <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
            {day}
          </h2>
          <div className="flex flex-col gap-3">
            {competitions.map((group) => (
              <div key={group.competition_id}>
                {competitions.length > 1 && (
                  <h3 className="mb-1 truncate font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted">
                    {group.competition}
                  </h3>
                )}
                <ul className="overflow-hidden rounded-lg border border-border bg-surface">
                  {group.results.map((result) => (
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
                        {competitions.length === 1 && (
                          <p className="truncate font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted">
                            {result.competition}
                          </p>
                        )}
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
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
