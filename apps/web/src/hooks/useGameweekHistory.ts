import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { gameweekListKey } from './usePickEditor';
import type { GameweekSummary } from '../lib/types';

export interface GameweekHistory {
  /** The season, newest first. Empty until the list loads. */
  gameweeks: GameweekSummary[];
  /** The gameweek being viewed, or `undefined` for "whatever the API defaults to". */
  selectedId: string | undefined;
  /** The row being shown once the list has loaded, for labelling. */
  selected: GameweekSummary | undefined;
  /** True on the default view — no `gw` parameter, so the API is choosing. */
  isLatest: boolean;
  /** Newer / older neighbours, `undefined` at either end of the season. */
  newer: GameweekSummary | undefined;
  older: GameweekSummary | undefined;
  select: (gameweekId: string | undefined) => void;
}

/**
 * The `gw` parameter, or `undefined` for "whatever the API defaults to".
 *
 * Separate from :func:`useGameweekHistory` because the surfaces need it *before* they
 * can call that hook: the round they fetch decides the round the history anchors on.
 */
export function useSelectedGameweekId(): string | undefined {
  const [searchParams] = useSearchParams();
  return searchParams.get('gw') ?? undefined;
}

/**
 * Which gameweek the coupon surfaces are showing, and the season to move through.
 *
 * The selection lives in the URL rather than component state so a past week can be
 * linked, reloaded, and reached with the browser's back button — the way a
 * fantasy-football season is browsed. Omitting the parameter means "whatever the API
 * defaults to", which keeps the default URL clean and the default query key stable.
 *
 * ``resolvedId`` is the round the surface's own read came back with, and is what the
 * default view anchors on. Taking the top of the list instead was right only while the
 * API's default *was* the newest ``starts_on``; since Batch 35 it is the round the
 * league is currently on, so a league holding a one-off in December — or simply a
 * second Saturday discovered ahead of its pick-open time — would have this control
 * labelling one round while the card below showed another.
 */
export function useGameweekHistory(
  slug: string,
  enabled = true,
  resolvedId?: string,
): GameweekHistory {
  const [, setSearchParams] = useSearchParams();
  const selectedId = useSelectedGameweekId();

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

  // Falls back to the top of the list only while neither is known — the first render,
  // before either query has answered.
  const anchorId = selectedId ?? resolvedId;
  const index = anchorId ? gameweeks.findIndex((g) => g.gameweek_id === anchorId) : 0;
  const selected = index >= 0 ? gameweeks[index] : undefined;

  return {
    gameweeks,
    selectedId,
    selected,
    // The default view is the one with no parameter, not the one that happens to sit at
    // the top of the list: naming the newest round explicitly is still a chosen round,
    // and the escape back to the default belongs on screen for it.
    isLatest: selectedId === undefined,
    // The list is newest-first, so the *newer* neighbour is the earlier index.
    newer: index > 0 ? gameweeks[index - 1] : undefined,
    older: index >= 0 ? gameweeks[index + 1] : undefined,
    select,
  };
}
