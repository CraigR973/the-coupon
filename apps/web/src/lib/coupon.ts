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
/**
 * What to call a round: "Gameweek 12", or its date when it has no number.
 *
 * One helper because the pick screen's header and the back/forward control must never
 * disagree about what the same round is called. A round discovered before Batch 41 — or
 * served by an API deployed before it, which happens routinely since the web app ships
 * ahead — has no number, and the date it always showed is the honest fallback rather
 * than a "Gameweek ?" placeholder.
 */
export function roundName(
  number: number | null | undefined,
  fallbackDate: string,
): string {
  return typeof number === 'number' ? `Gameweek ${number}` : fallbackDate;
}

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

/**
 * The fixture context a selection does not already carry.
 *
 * Batch 105. Every coupon row and every pasted line used to print the selection and then
 * the whole fixture — "Arsenal · Arsenal v Chelsea" — so the one word a reader is
 * actually scanning for appeared twice and pushed the price off the row. A selection on
 * Match Odds *is* one of the two teams, so what disambiguates it is the other one; a draw
 * or a Both-Teams-to-Score call names neither, so it takes the pairing.
 *
 * This is the whole of the "context needed to disambiguate it" rule, in one place,
 * because the screen and the clipboard have to apply it identically.
 */
export function fixtureContext(
  market: PickMarket,
  outcome: PickOutcome,
  home: string,
  away: string,
): string {
  if (market === 'MATCH_ODDS') {
    if (outcome === 'HOME') return `v ${away}`;
    if (outcome === 'AWAY') return `at ${home}`;
  }
  return `${home} v ${away}`;
}

/** A selection and its disambiguating context as one phrase — "Draw (Forfar v Brechin)". */
export function selectionSummary(
  market: PickMarket,
  outcome: PickOutcome,
  home: string,
  away: string,
): string {
  return `${outcomeLabel(market, outcome, home, away)} (${fixtureContext(market, outcome, home, away)})`;
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

/** Why a round refuses a pick, or `null` when it accepts one. */
export type PickRefusal = 'PICKS_NOT_OPEN' | 'PICKS_LOCKED' | null;

/** The statuses a round can still be claimed on — the API's `PICKABLE_STATES`. */
export const PICKABLE_STATUSES: ReadonlySet<string> = new Set(['scheduled', 'open']);

/** The three fields the claim-period rule reads, on whichever shape carries them. */
export interface ClaimPeriod {
  status: string;
  locks_at_utc: string;
  picks_open_at_utc?: string | null;
}

/**
 * Why this round refuses a pick right now, or `null` when it accepts one.
 *
 * A direct mirror of the API's `pick_refusal` (`services/gameweek.py`), and the reason it
 * exists here is that **`status` is not the authority and never was**. It is the label
 * the hourly scheduler keeps up with: `open_due_gameweeks` only ever moves
 * `scheduled -> open` and never back, and the lock job only ever moves `open -> locked`.
 * So a round is mislabelled for up to an hour after either instant passes — at the
 * opening as well as at the deadline — and a screen that reads the label is wrong for
 * that hour in both directions. Time decides; status only rules out a round settlement
 * has finished with.
 *
 * Batch 73. The case that made it visible: a league whose `pick_open_offset_minutes` is
 * saved for the first time has `rederive_claim_periods` restamp every unlocked round
 * (Batch 65) *without* re-deriving `status`, so a round keeps `status = 'open'` while the
 * API answers `PICKS_NOT_OPEN` — the badge said **Open** while every pick was refused.
 *
 * **`CurrentRoundPage` states this same rule a second time**, through `useCountdown` rather
 * than through a `now` argument, because it needs the claim period to flip live while a
 * member is sitting on the screen and it is already rendering those countdowns. That copy
 * gates whether a pick can be submitted at all, so Batch 73 left it alone rather than
 * rewiring the one path where being subtly wrong stops the product working. If the rule
 * below changes, change it there too.
 */
export function pickRefusal(round: ClaimPeriod, now: number = Date.now()): PickRefusal {
  if (!PICKABLE_STATUSES.has(round.status)) return 'PICKS_LOCKED';
  if (round.picks_open_at_utc && now < Date.parse(round.picks_open_at_utc)) {
    return 'PICKS_NOT_OPEN';
  }
  if (now >= Date.parse(round.locks_at_utc)) return 'PICKS_LOCKED';
  return null;
}

/** How a round's state should read, and whether that reads as live. */
export interface RoundState {
  label: string;
  open: boolean;
}

/**
 * The badge a round should carry — derived from the clock, not from `status`.
 *
 * `settled` and `locked` keep their own words because those are reached by settlement
 * rather than by a deadline passing, and "Settled" tells a member something "Locked"
 * does not. Everything else follows :func:`pickRefusal`.
 */
export function roundStateLabel(round: ClaimPeriod, now: number = Date.now()): RoundState {
  if (round.status === 'settled') return { label: 'Settled', open: false };
  if (round.status === 'locked') return { label: 'Locked', open: false };
  const refusal = pickRefusal(round, now);
  if (refusal === 'PICKS_NOT_OPEN') return { label: 'Not open', open: false };
  if (refusal === 'PICKS_LOCKED') return { label: 'Locked', open: false };
  return { label: 'Open', open: true };
}

/**
 * What the current round is *doing*, which is the one thing the merged Coupon surface
 * orders itself by (Batch 105).
 *
 * `Your pick` and `Combined coupon` were two screens asking the member which half of one
 * weekly job they wanted, and neither could lead with the thing that mattered at the
 * moment they opened it. One surface can, but only if it knows which moment that is.
 *
 * The order of the checks is the product rule and not an implementation detail:
 *
 * - Settlement outranks everything, because a settled round is a result and not a coupon.
 * - **A complete coupon outranks the deadline.** Everybody having picked is what makes the
 *   coupon worth copying, and that can happen well before the lock; it is also why
 *   `locked_incomplete` can only be reached with somebody still missing.
 * - `locked_incomplete` is the honest name for a round the deadline caught. Calling it
 *   complete because claiming has stopped is exactly the implication the review objected
 *   to.
 */
export type RoundPhase =
  | 'not_open'
  | 'open'
  | 'submitted'
  | 'complete'
  | 'locked_incomplete'
  | 'settled';

export interface RoundProgress {
  /** Settlement has finished with this round. */
  settled: boolean;
  /** Claiming has stopped — the deadline passed, or the round left the pickable states. */
  claimingShut: boolean;
  /** The claim window has not opened yet. */
  notOpenYet: boolean;
  memberCount: number;
  /** Members of this league with no selection on this round. */
  missingCount: number;
  /** Whether the reader holds a selection on this round. */
  mine: boolean;
}

export function roundPhase(progress: RoundProgress): RoundPhase {
  if (progress.settled) return 'settled';
  if (progress.memberCount > 0 && progress.missingCount === 0) return 'complete';
  if (progress.claimingShut) return 'locked_incomplete';
  if (progress.notOpenYet) return 'not_open';
  return progress.mine ? 'submitted' : 'open';
}

/** True while the coupon is the round's headline rather than the fixture list. */
export function couponLeads(phase: RoundPhase): boolean {
  return phase === 'complete' || phase === 'locked_incomplete' || phase === 'settled';
}
