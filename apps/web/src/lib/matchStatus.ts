// Shared match-status helpers used by the prediction-editing stack (PredictionCard,
// usePredictionEditor, the Predictions page and the home carousel). Kept framework-free
// so the hook can import `canEdit` without pulling in a React component module.

import type { MatchResponse } from './types';

/** Statuses for which a player may still enter or change a score prediction. */
export const EDITABLE_STATUSES = new Set<MatchResponse['status']>(['scheduled']);

export function canEdit(status: MatchResponse['status']): boolean;
export function canEdit(match: MatchResponse): boolean;
export function canEdit(statusOrMatch: MatchResponse['status'] | MatchResponse): boolean {
  if (typeof statusOrMatch === 'string') {
    return EDITABLE_STATUSES.has(statusOrMatch);
  }
  return statusOrMatch.status === 'scheduled' && new Date(statusOrMatch.kickoff_utc).getTime() > Date.now();
}

export function statusLabel(status: MatchResponse['status']): string {
  const map: Record<MatchResponse['status'], string> = {
    scheduled: 'Open',
    locked: 'Locked',
    live: 'Live',
    completed: 'FT',
    postponed: 'Postponed',
    cancelled: 'Voided',
  };
  return map[status];
}

export type StatusVariant = 'default' | 'success' | 'error' | 'muted' | 'warning' | 'live';

export function statusVariant(status: MatchResponse['status']): StatusVariant {
  const map: Record<MatchResponse['status'], StatusVariant> = {
    scheduled: 'success',
    locked: 'warning',
    live: 'live',
    completed: 'success',
    postponed: 'warning',
    cancelled: 'error',
  };
  return map[status];
}
