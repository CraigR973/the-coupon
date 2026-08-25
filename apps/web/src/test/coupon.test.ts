import { describe, it, expect } from 'vitest';
import {
  formatOdds,
  toFractional,
  potentialPoints,
  marketLabel,
  marketTag,
  outcomeLabel,
  selectionKey,
  pickStatusLabel,
  roundName,
  pickRefusal,
  roundStateLabel,
} from '@/lib/coupon';

describe('formatOdds', () => {
  it('renders decimal odds to a stable 2 dp', () => {
    expect(formatOdds(2.5)).toBe('2.50');
    expect(formatOdds(13)).toBe('13.00');
    expect(formatOdds(1.909)).toBe('1.91');
  });

  it('defaults to decimal when no preference is given', () => {
    expect(formatOdds(2.5)).toBe(formatOdds(2.5, 'decimal'));
  });

  it('renders fractional odds when asked', () => {
    expect(formatOdds(2.5, 'fractional')).toBe('3/2');
    expect(formatOdds(13, 'fractional')).toBe('12/1');
  });
});

describe('toFractional', () => {
  it('converts the net return, not the decimal price', () => {
    // 3.00 decimal returns 2 profit on 1 staked.
    expect(toFractional(3)).toBe('2/1');
    expect(toFractional(2)).toBe('1/1');
  });

  it('snaps to the traditional ladder rather than the exact ratio', () => {
    // The exact fraction of 1.91 is 91/100; every real coupon says 10/11.
    expect(toFractional(1.91)).toBe('10/11');
    expect(toFractional(1.9)).toBe('10/11');
    expect(toFractional(1.5)).toBe('1/2');
    expect(toFractional(4.5)).toBe('7/2');
  });

  it('falls back to a whole-number fraction above the ladder', () => {
    expect(toFractional(151)).toBe('150/1');
  });

  it('never returns a negative or zero-denominator fraction', () => {
    expect(toFractional(1)).toBe('0/1');
    expect(toFractional(0.5)).toBe('0/1');
  });

  it('preserves the scoring relationship — points come off the decimal price', () => {
    // Display changes; the winner still scores round(odds × 10).
    expect(toFractional(2.5)).toBe('3/2');
    expect(potentialPoints(2.5)).toBe(25);
  });
});

describe('potentialPoints', () => {
  it('is round(odds × 10), matching the backend rule', () => {
    expect(potentialPoints(1.5)).toBe(15);
    expect(potentialPoints(6)).toBe(60);
    expect(potentialPoints(13)).toBe(130);
  });

  it('rounds half up like the settlement maths', () => {
    // 2.05 × 10 = 20.5 → 21 (not banker's-rounding 20)
    expect(potentialPoints(2.05)).toBe(21);
  });
});

describe('marketLabel / marketTag', () => {
  it('labels the two markets', () => {
    expect(marketLabel('MATCH_ODDS')).toBe('Match Odds');
    expect(marketLabel('BOTH_TEAMS_TO_SCORE')).toBe('Both Teams to Score');
    expect(marketTag('MATCH_ODDS')).toBe('1X2');
    expect(marketTag('BOTH_TEAMS_TO_SCORE')).toBe('BTTS');
  });
});

describe('outcomeLabel', () => {
  it('resolves match-odds outcomes to team names / Draw', () => {
    expect(outcomeLabel('MATCH_ODDS', 'HOME', 'Forfar', 'Brechin')).toBe('Forfar');
    expect(outcomeLabel('MATCH_ODDS', 'AWAY', 'Forfar', 'Brechin')).toBe('Brechin');
    expect(outcomeLabel('MATCH_ODDS', 'DRAW', 'Forfar', 'Brechin')).toBe('Draw');
  });

  it('describes BTTS yes/no', () => {
    expect(outcomeLabel('BOTH_TEAMS_TO_SCORE', 'YES', 'A', 'B')).toBe('Both teams score');
    expect(outcomeLabel('BOTH_TEAMS_TO_SCORE', 'NO', 'A', 'B')).toBe('No — not both score');
  });
});

describe('selectionKey / pickStatusLabel', () => {
  it('builds a stable selection identity', () => {
    expect(selectionKey('MATCH_ODDS', 'HOME')).toBe('MATCH_ODDS:HOME');
  });

  it('labels pick statuses', () => {
    expect(pickStatusLabel('won')).toBe('Won');
    expect(pickStatusLabel('pending')).toBe('Pending');
    expect(pickStatusLabel('void')).toBe('Void');
  });
});

describe('roundName', () => {
  it('names a numbered round', () => {
    expect(roundName(12, 'Sat 8 Aug 2026')).toBe('Gameweek 12');
  });

  it('falls back to the date when the round has no number', () => {
    // A round discovered before Batch 41, or a slate served by an API deployed before
    // it — routine, since the web app ships ahead of the API.
    expect(roundName(null, 'Sat 8 Aug 2026')).toBe('Sat 8 Aug 2026');
    expect(roundName(undefined, 'Sat 8 Aug 2026')).toBe('Sat 8 Aug 2026');
  });

  it('names Gameweek 0 rather than treating it as absent', () => {
    // Guards the falsy-check bug: `number || fallback` would drop a legitimate 0.
    expect(roundName(0, 'Sat 8 Aug 2026')).toBe('Gameweek 0');
  });
});

/**
 * Batch 73 — the claim period is decided by the clock, and `status` is only the label
 * the hourly jobs have caught up with.
 *
 * These mirror the API's `pick_refusal` case for case. The pair that matter are the two
 * where `status` and the instants disagree, because those are the hour-long windows the
 * screen used to get wrong — one at each end.
 */
describe('pickRefusal', () => {
  const OPENS = '2026-08-29T09:00:00Z';
  const LOCKS = '2026-08-29T14:30:00Z';
  const round = { status: 'open', picks_open_at_utc: OPENS, locks_at_utc: LOCKS };
  const at = (iso: string) => Date.parse(iso);

  it('accepts a pick inside the claim period', () => {
    expect(pickRefusal(round, at('2026-08-29T12:00:00Z'))).toBeNull();
  });

  it('refuses a round labelled open whose opening has not arrived', () => {
    // The case the owner hit: saving `pick_open_offset_minutes` restamps every unlocked
    // round (Batch 65) without re-deriving `status`, so the round keeps `open` while the
    // API answers PICKS_NOT_OPEN. `open_due_gameweeks` never moves a label backwards.
    expect(pickRefusal(round, at('2026-08-29T08:59:00Z'))).toBe('PICKS_NOT_OPEN');
  });

  it('refuses a round labelled open whose deadline has passed', () => {
    // The mirror, and the one that has always been there: the lock job runs hourly, so
    // a round reads `open` for up to an hour after nobody can claim on it.
    expect(pickRefusal(round, at('2026-08-29T14:30:00Z'))).toBe('PICKS_LOCKED');
  });

  it('treats a round with no announced opening as claimable from discovery', () => {
    // `picks_open_at_utc = null` is no gate at all, not an offset of zero.
    const ungated = { status: 'scheduled', picks_open_at_utc: null, locks_at_utc: LOCKS };
    expect(pickRefusal(ungated, at('2026-08-20T00:00:00Z'))).toBeNull();
  });

  it('lets status alone decide a round settlement has finished with', () => {
    // `locked` and `settled` are reached by settlement rather than by a clock, so no
    // instant can talk them back open.
    const inside = at('2026-08-29T12:00:00Z');
    expect(pickRefusal({ ...round, status: 'locked' }, inside)).toBe('PICKS_LOCKED');
    expect(pickRefusal({ ...round, status: 'settled' }, inside)).toBe('PICKS_LOCKED');
  });
});

describe('roundStateLabel', () => {
  const OPENS = '2026-08-29T09:00:00Z';
  const LOCKS = '2026-08-29T14:30:00Z';
  const round = { status: 'open', picks_open_at_utc: OPENS, locks_at_utc: LOCKS };
  const at = (iso: string) => Date.parse(iso);

  it('reads Open only while a pick would actually be taken', () => {
    expect(roundStateLabel(round, at('2026-08-29T12:00:00Z'))).toEqual({
      label: 'Open',
      open: true,
    });
  });

  it('reads Not open for a round labelled open before its opening', () => {
    expect(roundStateLabel(round, at('2026-08-29T08:59:00Z'))).toEqual({
      label: 'Not open',
      open: false,
    });
  });

  it('reads Locked for a round labelled open after its deadline', () => {
    expect(roundStateLabel(round, at('2026-08-29T15:00:00Z'))).toEqual({
      label: 'Locked',
      open: false,
    });
  });

  it('keeps Settled as its own word', () => {
    // "Locked" and "Settled" are not interchangeable to a member: one says come back
    // never, the other says the points are in.
    const settled = { ...round, status: 'settled' };
    expect(roundStateLabel(settled, at('2026-08-30T12:00:00Z')).label).toBe('Settled');
  });
});
