import { describe, it, expect } from 'vitest';
import {
  formatOdds,
  potentialPoints,
  marketLabel,
  marketTag,
  outcomeLabel,
  selectionKey,
  pickStatusLabel,
} from '@/lib/coupon';

describe('formatOdds', () => {
  it('renders decimal odds to a stable 2 dp', () => {
    expect(formatOdds(2.5)).toBe('2.50');
    expect(formatOdds(13)).toBe('13.00');
    expect(formatOdds(1.909)).toBe('1.91');
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
