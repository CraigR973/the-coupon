import { useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import type { KnockoutPredictionResponse } from '../lib/types';

const KNOCKOUT_PREDICTIONS_ME_KEY = ['knockout-predictions', 'me'] as const;

// ---------------------------------------------------------------------------
// useKnockoutWinnerEditor — the shared who-progresses editing stack.
//
// Owns: optimistic local winner state, the upsert PUT
// (/knockout-predictions/{matchId}), error rollback to the last server value,
// and per-match saving/error flags. Mirrors usePredictionEditor so every
// surface that lets a player pick who progresses (the home carousel, the
// Predictions list, and the dedicated Knockout Picks page) shares one
// implementation rather than three drifting copies.
//
// Data fetching stays with the caller; all three surfaces read the
// ['knockout-predictions','me'] query key, so React Query dedupes them.
// ---------------------------------------------------------------------------

export interface KnockoutWinnerEditor {
  /**
   * Server predictions overlaid with optimistic local picks, keyed by
   * `match_id`. Pass `predictionByMatch[matchId]` straight to PredictionCard's
   * `knockoutPrediction` prop, or read `.predicted_winner_id` for a bare id.
   */
  predictionByMatch: Record<string, KnockoutPredictionResponse>;
  /** Per-match in-flight save flag (for surfaces showing a "Saving…" hint). */
  saving: Record<string, boolean>;
  /** Per-match last-save-failed flag (for surfaces showing "Save failed"). */
  errors: Record<string, boolean>;
  /** Optimistically set + persist who progresses for a knockout match. */
  pickWinner: (matchId: string, winnerId: string) => void;
}

export function useKnockoutWinnerEditor({
  knockoutPredictions,
  playerId,
}: {
  knockoutPredictions: KnockoutPredictionResponse[];
  playerId?: string;
}): KnockoutWinnerEditor {
  const queryClient = useQueryClient();
  const [localWinners, setLocalWinners] = useState<Record<string, string | null>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, boolean>>({});

  const serverPredByMatch = useMemo(
    () => Object.fromEntries(knockoutPredictions.map((p) => [p.match_id, p])),
    [knockoutPredictions],
  );

  const pickWinner = useCallback(
    (matchId: string, winnerId: string) => {
      // Optimistic: reflect the pick immediately so the card highlights without
      // waiting on the network round-trip.
      setLocalWinners((prev) => ({ ...prev, [matchId]: winnerId }));
      setSaving((prev) => ({ ...prev, [matchId]: true }));
      setErrors((prev) => ({ ...prev, [matchId]: false }));

      void (async () => {
        try {
          await apiFetch(`/api/v1/knockout-predictions/${matchId}`, {
            method: 'PUT',
            body: JSON.stringify({ predicted_winner_id: winnerId }),
          });
          void queryClient.invalidateQueries({ queryKey: KNOCKOUT_PREDICTIONS_ME_KEY });
        } catch {
          // Roll back to the last server-confirmed winner and surface a retry.
          setLocalWinners((prev) => ({
            ...prev,
            [matchId]: serverPredByMatch[matchId]?.predicted_winner_id ?? null,
          }));
          setErrors((prev) => ({ ...prev, [matchId]: true }));
          toast.error('Failed to save who-progresses pick — please try again');
        } finally {
          setSaving((prev) => ({ ...prev, [matchId]: false }));
        }
      })();
    },
    [serverPredByMatch, queryClient],
  );

  const predictionByMatch = useMemo(() => {
    const next: Record<string, KnockoutPredictionResponse> = {};
    for (const p of knockoutPredictions) {
      next[p.match_id] = {
        ...p,
        predicted_winner_id: localWinners[p.match_id] ?? p.predicted_winner_id,
      };
    }
    // Synthesize entries for matches that only have an optimistic local pick
    // (no server prediction yet) so the card can highlight them straight away.
    for (const [matchId, winnerId] of Object.entries(localWinners)) {
      if (winnerId && !next[matchId]) {
        next[matchId] = {
          id: '',
          player_id: playerId ?? '',
          match_id: matchId,
          predicted_winner_id: winnerId,
          submitted_at: null,
          update_count: 0,
          points_awarded: null,
          updated_at: '',
        };
      }
    }
    return next;
  }, [knockoutPredictions, localWinners, playerId]);

  return { predictionByMatch, saving, errors, pickWinner };
}
