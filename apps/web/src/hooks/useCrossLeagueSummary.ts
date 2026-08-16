import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import type { CrossLeagueSummary } from '../lib/types';

export const crossLeagueSummaryKey = ['me', 'cross-league-summary'] as const;

/**
 * The member's season across every league they play.
 *
 * Home and the career profile are the same read at two altitudes — one shows the
 * per-league rows, the other the aggregate over them — so they share a cache
 * entry and a key. Both are lazy routes, hence a hook rather than one importing
 * the other's constant and dragging its chunk along.
 */
export function useCrossLeagueSummary(): UseQueryResult<CrossLeagueSummary> {
  return useQuery<CrossLeagueSummary>({
    queryKey: crossLeagueSummaryKey,
    queryFn: () => apiFetch<CrossLeagueSummary>('/api/v1/me/cross-league-summary'),
    staleTime: 30_000,
  });
}
