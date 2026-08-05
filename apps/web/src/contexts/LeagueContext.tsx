import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '../lib/api';
import { getLastViewedLeague } from '../lib/leagueRecency';
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

  const activeSlug = useMemo(() => {
    if (leagues.length === 0) return DEFAULT_LEAGUE_SLUG;
    const lastViewedSlug = getLastViewedLeague()?.slug ?? null;
    const stillMember = lastViewedSlug && leagues.some((league) => league.slug === lastViewedSlug);
    return stillMember ? (lastViewedSlug as string) : leagues[0].slug;
  }, [leagues]);

  return (
    <LeagueContext.Provider
      value={{
        leagues,
        isLoading,
        refetch: refetchLeagues,
        activeSlug,
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
