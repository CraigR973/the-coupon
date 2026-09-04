import { describe, it, expect } from 'vitest';
import { HOME_CARD_STATE, homeCardState, showsCouponFigures } from '@/lib/home';

/**
 * Batch 106. The card's state is the thing that decides what its primary part may say, so
 * the precedence is asserted here rather than only through the rendered card: `settled`
 * and `notOpenYet` both mean *between rounds* however the deadline reads, because in both
 * cases the next action is an opening rather than a pick.
 */
const OPEN = {
  hasRound: true,
  settled: false,
  notOpenYet: false,
  claimingShut: false,
  mine: false,
};

describe('homeCardState', () => {
  it('asks for a pick while the round is claimable and the member holds none', () => {
    expect(homeCardState(OPEN)).toBe('pick_required');
  });

  it('says the pick is submitted once they hold one', () => {
    expect(homeCardState({ ...OPEN, mine: true })).toBe('pick_submitted');
  });

  it('calls a shut, unsettled round a round in progress', () => {
    expect(homeCardState({ ...OPEN, claimingShut: true })).toBe('round_in_progress');
    expect(homeCardState({ ...OPEN, claimingShut: true, mine: true })).toBe('round_in_progress');
  });

  it('is between rounds with no round, a settled one, or one not yet open', () => {
    expect(homeCardState({ ...OPEN, hasRound: false, claimingShut: true })).toBe('between_rounds');
    expect(homeCardState({ ...OPEN, settled: true, claimingShut: true })).toBe('between_rounds');
    expect(homeCardState({ ...OPEN, notOpenYet: true })).toBe('between_rounds');
  });

  it('lets settlement and a closed window outrank a pick the member holds', () => {
    // The Sunday shape: last round settled with their pick still on it. The card is
    // about the next opening, and that pick belongs under `Last result`.
    expect(homeCardState({ ...OPEN, settled: true, claimingShut: true, mine: true })).toBe(
      'between_rounds',
    );
    expect(homeCardState({ ...OPEN, notOpenYet: true, mine: true })).toBe('between_rounds');
  });

  it('names all four states', () => {
    expect(Object.keys(HOME_CARD_STATE)).toEqual([
      'pick_required',
      'pick_submitted',
      'round_in_progress',
      'between_rounds',
    ]);
  });
});

describe('showsCouponFigures', () => {
  it('shows the fold only once the coupon is frozen', () => {
    // While picks are open the fold moves every time anybody claims anything, and it is
    // competing with a deadline for the same line.
    expect(showsCouponFigures('round_in_progress')).toBe(true);
    expect(showsCouponFigures('pick_required')).toBe(false);
    expect(showsCouponFigures('pick_submitted')).toBe(false);
    expect(showsCouponFigures('between_rounds')).toBe(false);
  });
});
