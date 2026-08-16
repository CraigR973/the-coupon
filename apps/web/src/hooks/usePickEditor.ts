import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { useOddsFormat } from './useOddsFormat';
import { formatOdds, selectionKey } from '../lib/coupon';
import type { PickMarket, PickOutcome, PickResponse, SubmitPickBody } from '../lib/types';

// Query keys the pick screen + combined view read; a successful grab invalidates
// all three so the slate re-fetches taken-flags, the coupon rebuilds, and "my
// pick" updates. Exported so the pages register under the same keys.
//
// The gameweek is part of the key because Batch 12 made both reads browsable back
// through the season — without it, viewing a past week would poison the cache
// entry the current week reads from. `undefined` is the "latest" entry.
export const gameweekKey = (slug: string, gameweekId?: string) =>
  ['gameweek', slug, gameweekId] as const;
export const couponKey = (slug: string, gameweekId?: string) =>
  ['coupon', slug, gameweekId] as const;
export const gameweekListKey = (slug: string) => ['gameweeks', slug] as const;
export const myPickKey = (slug: string, gameweekId: string | undefined) =>
  ['my-pick', slug, gameweekId] as const;

/** Turn the backend `detail` code into a player-facing message. */
export function pickErrorMessage(detail: string): string {
  switch (detail) {
    case 'SELECTION_TAKEN':
      return 'Someone in your league just grabbed that selection — pick another.';
    case 'FIXTURE_TAKEN':
      return 'Someone in your league already has that game — pick another match.';
    case 'PICKS_LOCKED':
      return 'Picks are locked for this week.';
    case 'PICKS_NOT_OPEN':
      return 'Picks haven’t opened for this round yet — check back closer to kick-off.';
    case 'SELECTION_NOT_AVAILABLE':
      return 'That selection isn’t being priced right now — try another.';
    default:
      return detail || 'Could not save your pick — try again.';
  }
}

export interface PickEditor {
  /** Grab (or re-pick to) a selection. One pick per member per gameweek. */
  submit: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
  /** `selectionKey` currently being submitted, for a per-button spinner. */
  pendingKey: string | null;
  isSubmitting: boolean;
}

/**
 * The weekly land-grab. Owns the pick mutation (POST .../picks): optimistic
 * per-button pending state, cache invalidation of the slate / coupon / my-pick,
 * and mapping the backend's 409/422 detail codes to friendly toasts.
 *
 * The odds are snapshotted server-side, so the client sends only the selection
 * identity `{ fixture_id, market, outcome }`.
 */
export function usePickEditor(slug: string, gameweekId: string | undefined): PickEditor {
  const queryClient = useQueryClient();
  const oddsFormat = useOddsFormat();
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: SubmitPickBody) =>
      apiFetch<PickResponse>(`/api/v1/leagues/${slug}/picks`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (pick) => {
      // Prefix-matched, so every gameweek's entry for this league is refreshed —
      // a grab changes the season list's pick counts as well as this week's slate.
      void queryClient.invalidateQueries({ queryKey: ['gameweek', slug] });
      void queryClient.invalidateQueries({ queryKey: ['coupon', slug] });
      void queryClient.invalidateQueries({ queryKey: gameweekListKey(slug) });
      void queryClient.invalidateQueries({ queryKey: myPickKey(slug, gameweekId) });
      toast.success(`Grabbed ${pick.runner_name} @ ${formatOdds(pick.odds, oddsFormat)}`);
    },
    onError: (err) => {
      toast.error(pickErrorMessage(err instanceof Error ? err.message : ''));
    },
    onSettled: () => setPendingKey(null),
  });

  const submit = useCallback(
    (fixtureId: string, market: PickMarket, outcome: PickOutcome) => {
      setPendingKey(`${fixtureId}:${selectionKey(market, outcome)}`);
      mutation.mutate({ fixture_id: fixtureId, market, outcome });
    },
    [mutation],
  );

  return { submit, pendingKey, isSubmitting: mutation.isPending };
}
