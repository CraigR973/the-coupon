/**
 * Coupon display helpers — odds formatting, market/outcome labels, the
 * points-a-winner-scores rule. Kept pure so they're unit-testable and shared
 * across the pick screen, the combined-acca view, and the home page.
 */

import type { PickMarket, PickOutcome, PickStatus } from './types';

/** Decimal odds to a stable 2-dp string, e.g. 2.5 → "2.50". */
export function formatOdds(odds: number): string {
  return odds.toFixed(2);
}

/**
 * Points a winning pick at these odds scores. Mirrors the backend rule
 * `round(odds × 10)` (half-up) so the UI's "win = N pts" matches settlement.
 */
export function potentialPoints(odds: number): number {
  return Math.round(odds * 10);
}

export function marketLabel(market: PickMarket): string {
  return market === 'MATCH_ODDS' ? 'Match Odds' : 'Both Teams to Score';
}

/** Short tag for chips/badges. */
export function marketTag(market: PickMarket): string {
  return market === 'MATCH_ODDS' ? '1X2' : 'BTTS';
}

/**
 * Human label for an outcome within a fixture. Match Odds resolves HOME/AWAY to
 * the team names; BTTS reads "Both teams score — Yes/No". Falls back sensibly
 * for any unexpected value.
 */
export function outcomeLabel(
  market: PickMarket,
  outcome: PickOutcome,
  home: string,
  away: string,
): string {
  if (market === 'MATCH_ODDS') {
    if (outcome === 'HOME') return home;
    if (outcome === 'AWAY') return away;
    return 'Draw';
  }
  return outcome === 'YES' ? 'Both teams score' : 'No — not both score';
}

/** Stable identity for a selection within a fixture (React keys, comparisons). */
export function selectionKey(market: PickMarket, outcome: PickOutcome): string {
  return `${market}:${outcome}`;
}

const STATUS_LABELS: Record<PickStatus, string> = {
  pending: 'Pending',
  won: 'Won',
  lost: 'Lost',
  void: 'Void',
};

export function pickStatusLabel(status: PickStatus): string {
  return STATUS_LABELS[status] ?? status;
}
