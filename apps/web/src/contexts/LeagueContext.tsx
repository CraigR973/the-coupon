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
   * The league an address that names none resolves to: the last one the member
   * viewed, falling back to their first league, and to `DEFAULT_LEAGUE_SLUG` only
   * while `leagues` is still loading/empty.
   *
   * A default, not a source of truth — since Batch 30 the coupon surfaces carry
   * their league in the URL, and this is what the slug-less paths redirect through
   * and what the nav bars aim at.
   */
  activeSlug: string;
  /** `activeSlug`'s display name, once `leagues` has loaded and it resolves to a membership. */
  activeLeagueName: string | undefined;
  /**
   * True once `leagues` has loaded with at least one membership. `activeSlug`
   * falls back to `DEFAULT_LEAGUE_SLUG` while this is false, so screens that bind
   * to it should gate their queries on this rather than firing at the fallback.
   */
  hasLeagues: boolean;
  /**
   * Bind to `slug` and remember it — the route calls this on arrival
   * (`useRouteLeague`), which is what makes a slug-less entry afterwards resume at
   * the league last actually looked at. The choice has to live in state as well as
   * the recency store: `activeSlug` is derived, so writing the store alone would
   * not re-render. Ignores a slug the member is not in.
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

  const activeLeagueName = useMemo(
    () => leagues.find((league) => league.slug === activeSlug)?.name,
    [leagues, activeSlug],
  );

  return (
    <LeagueContext.Provider
      value={{
        leagues,
        isLoading,
        refetch: refetchLeagues,
        activeSlug,
        activeLeagueName,
        hasLeagues: leagues.length > 0,
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
