/**
 * What one league card on home is *about* right now.
 *
 * Batch 106. A card used to be assembled from whatever fields happened to be present, so
 * a settled round with a future opening printed the previous round's pick, fold and
 * combined odds directly beside `Next opens in 2d` — two different rounds, one paragraph,
 * neither labelled. The fix is to name the state first and let it decide what the primary
 * part of the card is allowed to say.
 *
 * The four are the whole space, and each one has exactly one next action:
 *
 * - `pick_required` — this league is waiting on the member. The deadline is the news.
 * - `pick_submitted` — they are in; the deadline and how many others are still out.
 * - `round_in_progress` — claiming has stopped and settlement has not happened. The
 *   coupon is frozen, so this is the one state where the fold and the combined price are
 *   a fact about now rather than a volatile number.
 * - `between_rounds` — nothing to claim: the round settled, or has not opened, or the
 *   league has no round at all. The next *opening* is the news, and everything about the
 *   round just gone belongs under `Last result`.
 *
 * Each league answers from its own summary. Nothing here reads a clock the league did not
 * supply, because the Saturday-at-14:30 default is one league's configuration and not the
 * product's rule.
 */
export type HomeCardState =
  | 'pick_required'
  | 'pick_submitted'
  | 'round_in_progress'
  | 'between_rounds';

export interface HomeRoundFacts {
  /** False when the league has published no round at all. */
  hasRound: boolean;
  settled: boolean;
  /** The round's claim window has not opened yet. */
  notOpenYet: boolean;
  /** Claiming has stopped — the deadline passed, or the round left the pickable states. */
  claimingShut: boolean;
  /** Whether the member holds a selection on this round. */
  mine: boolean;
}

export function homeCardState(facts: HomeRoundFacts): HomeCardState {
  if (!facts.hasRound || facts.settled || facts.notOpenYet) return 'between_rounds';
  if (facts.claimingShut) return 'round_in_progress';
  return facts.mine ? 'pick_submitted' : 'pick_required';
}

/** The chip each state carries. Colour supports the word; it never replaces it. */
export const HOME_CARD_STATE: Record<
  HomeCardState,
  { label: string; variant: 'warning' | 'success' | 'default' | 'muted' }
> = {
  pick_required: { label: 'Pick required', variant: 'warning' },
  pick_submitted: { label: 'Pick submitted', variant: 'success' },
  round_in_progress: { label: 'Round in progress', variant: 'default' },
  between_rounds: { label: 'Between rounds', variant: 'muted' },
};

/**
 * Whether the round's own coupon figures may appear in the primary part of the card.
 *
 * Only once the round is frozen. While picks are open the fold changes every time anybody
 * claims anything, so it competes with the deadline for attention and loses the member
 * nothing when it is left out; once claiming has stopped it is the round.
 */
export function showsCouponFigures(state: HomeCardState): boolean {
  return state === 'round_in_progress';
}
