import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '../lib/api';
import { getLastViewedLeague, setLastViewedLeague } from '../lib/leagueRecency';
import type { LeagueSummary } from '../lib/types';

interface LeagueContextValue {
  leagues: LeagueSummary[];
  isLoading: boolean;
  refetch: () => void;
  /**
   * The league to bind league-agnostic screens (home, coupon, combined acca)
   * to: the last one the member viewed, falling back to their first league,
   * and to `DEFAULT_LEAGUE_SLUG` only while `leagues` is still loading/empty.
   */
  activeSlug: string;
  /**
   * Bind those screens to `slug` and remember it. Home's per-league cards need
   * this: they open one league's coupon while another is bound, and writing the
   * recency store alone would not re-render — `activeSlug` is derived, so the
   * choice has to live in state as well. Ignores a slug the member is not in.
   */
  selectLeague: (slug: string) => void;
}

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();

  const { data: leagues = [], isLoading } = useQuery<LeagueSummary[]>({
    queryKey: ['leagues', 'mine'],
    queryFn: () => apiFetch<LeagueSummary[]>('/api/v1/leagues/mine'),
    staleTime: 60_000,
  });

  const refetchLeagues = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['leagues', 'mine'] });
  }, [queryClient]);

  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  const selectLeague = useCallback(
    (slug: string) => {
      const league = leagues.find((entry) => entry.slug === slug);
      if (!league) return;
      setSelectedSlug(league.slug);
      setLastViewedLeague({ slug: league.slug, name: league.name });
    },
    [leagues],
  );

  const activeSlug = useMemo(() => {
    if (leagues.length === 0) return DEFAULT_LEAGUE_SLUG;
    const preferredSlug = selectedSlug ?? getLastViewedLeague()?.slug ?? null;
    const stillMember = preferredSlug && leagues.some((league) => league.slug === preferredSlug);
    return stillMember ? (preferredSlug as string) : leagues[0].slug;
  }, [leagues, selectedSlug]);

  return (
    <LeagueContext.Provider
      value={{
        leagues,
        isLoading,
        refetch: refetchLeagues,
        activeSlug,
        selectLeague,
      }}
    >
      {children}
    </LeagueContext.Provider>
  );
}

export function useLeague(): LeagueContextValue {
  const ctx = useContext(LeagueContext);
  if (!ctx) throw new Error('useLeague must be used within LeagueProvider');
  return ctx;
}
