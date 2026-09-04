import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import type { CompetitionTable, ResultEntry } from '../lib/types';
import { compareCompetitions } from '../lib/competitions';
import { groupResultDays, resolveResultDay } from '../lib/footballResults';
import { PageHeader } from '../components/PageHeader';
import { LeagueTableCard } from '../components/LeagueTableCard';
import { ResultDayCarousel } from '../components/ResultDayCarousel';
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
  const [params, setParams] = useSearchParams();
  const requestedDate = params.get('date') ?? undefined;
  // A `?date=` link is a link to a result day, so it opens on the tab that has one.
  // Read once, at mount: after that the tabs are the member's to move between, and a
  // later selection must not throw them back across the page.
  const [view, setView] = useState<View>(() => (params.has('date') ? 'results' : 'tables'));

  /**
   * Put the chosen day in the URL — pushed, not replaced.
   *
   * `useGameweekHistory` replaces because its parameter is a filter on one screen.
   * This one is the screen: moving through matchdays is the navigation, so back has
   * to be the way out of it, and Batch 109 asks for exactly that. The newest day is
   * named explicitly rather than left as a bare `/football`, because "latest" is a
   * different Saturday next week and a shared link should not drift.
   */
  const selectDay = useCallback(
    (date: string) => {
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set('date', date);
        return next;
      });
    },
    [setParams],
  );

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
        <ResultsView
          results={resultList}
          timezone={timezone}
          requestedDate={requestedDate}
          onSelectDay={selectDay}
        />
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

interface ResultsViewProps {
  results: ResultEntry[];
  timezone: string;
  /** The `?date=` value, or `undefined` for the latest day we hold. */
  requestedDate: string | undefined;
  onSelectDay: (date: string) => void;
}

/**
 * One matchday at a time, its competitions grouped beneath it (Batch 109).
 *
 * This was the whole archive in one column, newest day first, and the job it is
 * actually used for — moving between matchdays — meant scrolling past every match of
 * the days in between. Day is still the outer key, because it is what a member scans
 * for first; what changed is that only one of them is on screen, with the strip above
 * naming the others.
 *
 * Competition grouping stays underneath it. A Saturday can hold eighty matches across
 * four competitions, and a flat list under one heading reads as an undifferentiated
 * column — the same failure the day grouping was built to fix, one level down.
 */
function ResultsView({ results, timezone, requestedDate, onSelectDay }: ResultsViewProps) {
  const days = useMemo(() => groupResultDays(results, timezone), [results, timezone]);
  const day = resolveResultDay(days, requestedDate);

  if (!day) {
    return (
      <EmptyState
        title="No results yet"
        description="Previous results appear once the football data has been pulled in. We cover every competition a coupon has drawn from — not every competition in Britain."
      />
    );
  }

  const { competitions } = day;

  return (
    <div data-testid="football-results">
      {/* Below two days there is nothing to move between, and a carousel offering one
          stop is a control that changes nothing — the same rule `GameweekNav` and
          `SeasonStrip` hide themselves under. */}
      {days.length > 1 && (
        <ResultDayCarousel days={days} selected={day.date} onSelect={onSelectDay} />
      )}

      <section>
        {/* The full day, year included. The strip's chips are abbreviated to fit a row
            of them, so this is the only place that says which season is on screen. */}
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
          {day.label}
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
    </div>
  );
}
