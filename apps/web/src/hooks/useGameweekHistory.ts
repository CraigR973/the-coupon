import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { gameweekListKey } from './usePickEditor';
import type { GameweekSummary } from '../lib/types';

export interface GameweekHistory {
  /** The season, newest first. Empty until the list loads. */
  gameweeks: GameweekSummary[];
  /** The gameweek being viewed, or `undefined` for "whatever is latest". */
  selectedId: string | undefined;
  /** The selected row once the list has loaded, for labelling. */
  selected: GameweekSummary | undefined;
  /** True when viewing the newest gameweek (or before the list has loaded). */
  isLatest: boolean;
  /** Newer / older neighbours, `undefined` at either end of the season. */
  newer: GameweekSummary | undefined;
  older: GameweekSummary | undefined;
  select: (gameweekId: string | undefined) => void;
}

/**
 * Which gameweek the coupon surfaces are showing, and the season to move through.
 *
 * The selection lives in the URL rather than component state so a past week can be
 * linked, reloaded, and reached with the browser's back button — the way a
 * fantasy-football season is browsed. Omitting the parameter means "latest",
 * which keeps the default URL clean and the default query key stable.
 */
export function useGameweekHistory(slug: string, enabled = true): GameweekHistory {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('gw') ?? undefined;

  const { data } = useQuery<GameweekSummary[]>({
    queryKey: gameweekListKey(slug),
    queryFn: () => apiFetch<GameweekSummary[]>(`/api/v1/leagues/${slug}/gameweeks`),
    staleTime: 60_000,
    enabled,
  });
  // This is the boundary where the API's shape becomes the UI's assumption, so it
  // is where the shape gets checked. Everything downstream indexes into this list.
  const gameweeks = Array.isArray(data) ? data : [];

  const select = useCallback(
    (gameweekId: string | undefined) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (gameweekId === undefined) next.delete('gw');
          else next.set('gw', gameweekId);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const index = selectedId ? gameweeks.findIndex((g) => g.gameweek_id === selectedId) : 0;
  const selected = index >= 0 ? gameweeks[index] : undefined;

  return {
    gameweeks,
    selectedId,
    selected,
    // Before the list arrives, an absent parameter already means the latest.
    isLatest: selectedId === undefined || index === 0,
    // The list is newest-first, so the *newer* neighbour is the earlier index.
    newer: index > 0 ? gameweeks[index - 1] : undefined,
    older: index >= 0 ? gameweeks[index + 1] : undefined,
    select,
  };
}
