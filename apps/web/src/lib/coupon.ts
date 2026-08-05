/**
 * Coupon display helpers — odds formatting, market/outcome labels, the
 * points-a-winner-scores rule. Kept pure so they're unit-testable and shared
 * across the pick screen, the combined-acca view, and the home page.
 */

import type { OddsFormat, PickMarket, PickOutcome, PickStatus } from './types';

/**
 * The traditional UK fractional ladder, as `[numerator, denominator]` ascending.
 *
 * Bookmakers quote from a fixed ladder rather than from an exact conversion, so
 * a decimal price is snapped to its nearest rung. Deriving a fraction
 * arithmetically instead would print 1.91 as "91/100" where every real coupon
 * says "10/11".
 */
const FRACTIONAL_LADDER: ReadonlyArray<readonly [number, number]> = [
  [1, 100], [1, 66], [1, 50], [1, 40], [1, 33], [1, 25], [1, 20], [1, 16],
  [1, 14], [1, 12], [1, 11], [1, 10], [1, 9], [1, 8], [1, 7], [2, 13],
  [1, 6], [2, 11], [1, 5], [2, 9], [1, 4], [2, 7], [3, 10], [1, 3],
  [4, 11], [2, 5], [4, 9], [1, 2], [8, 15], [4, 7], [8, 13], [2, 3],
  [7, 10], [8, 11], [4, 5], [5, 6], [10, 11], [1, 1], [11, 10], [6, 5],
  [5, 4], [11, 8], [7, 5], [3, 2], [8, 5], [13, 8], [7, 4], [15, 8],
  [2, 1], [21, 10], [11, 5], [9, 4], [12, 5], [5, 2], [13, 5], [11, 4],
  [3, 1], [10, 3], [7, 2], [4, 1], [9, 2], [5, 1], [11, 2], [6, 1],
  [13, 2], [7, 1], [15, 2], [8, 1], [17, 2], [9, 1], [10, 1], [11, 1],
  [12, 1], [14, 1], [16, 1], [18, 1], [20, 1], [22, 1], [25, 1], [28, 1],
  [33, 1], [40, 1], [50, 1], [66, 1], [80, 1], [100, 1],
];

/**
 * Decimal odds as a traditional fraction, e.g. 2.5 → "3/2", 1.91 → "10/11".
 *
 * The stake is implicit in decimal odds and explicit in fractional, so the net
 * return `odds - 1` is what gets converted. Prices above the ladder's 100/1 top
 * rung fall back to a whole-number fraction rather than clamping.
 */
export function toFractional(odds: number): string {
  const net = odds - 1;
  if (net <= 0) return '0/1';
  const top = FRACTIONAL_LADDER[FRACTIONAL_LADDER.length - 1];
  if (net > top[0] / top[1]) return `${Math.round(net)}/1`;

  let best = FRACTIONAL_LADDER[0];
  let bestDelta = Infinity;
  for (const rung of FRACTIONAL_LADDER) {
    const delta = Math.abs(net - rung[0] / rung[1]);
    if (delta < bestDelta) {
      best = rung;
      bestDelta = delta;
    }
  }
  return `${best[0]}/${best[1]}`;
}

/**
 * A price in the member's chosen notation — decimal "2.50" or fractional "3/2".
 *
 * Display only. Prices are stored decimal and a winner always scores
 * `round(odds × 10)` off the decimal value, so the notation a member reads
 * never changes what a pick is worth.
 */
export function formatOdds(odds: number, format: OddsFormat = 'decimal'): string {
  return format === 'fractional' ? toFractional(odds) : odds.toFixed(2);
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
