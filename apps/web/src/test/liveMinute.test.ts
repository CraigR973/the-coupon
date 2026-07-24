import { describe, it, expect } from 'vitest';
import { formatLiveMinute } from '@/lib/liveMinute';

const KICKOFF = '2026-06-22T17:00:00Z';
const at = (mins: number) => new Date(KICKOFF).getTime() + mins * 60_000;

describe('formatLiveMinute', () => {
  it('returns null before kickoff', () => {
    expect(formatLiveMinute(KICKOFF, at(-1))).toBeNull();
  });

  it('returns null for an invalid kickoff', () => {
    expect(formatLiveMinute('not-a-date', at(10))).toBeNull();
  });

  it('shows the raw minute in the first half', () => {
    expect(formatLiveMinute(KICKOFF, at(0))).toBe("0'");
    expect(formatLiveMinute(KICKOFF, at(10))).toBe("10'");
    expect(formatLiveMinute(KICKOFF, at(45))).toBe("45'");
  });

  it('shows HT across the half-time break window', () => {
    expect(formatLiveMinute(KICKOFF, at(46))).toBe('HT');
    expect(formatLiveMinute(KICKOFF, at(60))).toBe('HT');
  });

  it('discounts the break in the second half', () => {
    expect(formatLiveMinute(KICKOFF, at(61))).toBe("46'");
    expect(formatLiveMinute(KICKOFF, at(100))).toBe("85'");
    expect(formatLiveMinute(KICKOFF, at(104))).toBe("89'");
  });

  it('caps at 90+ once play passes full time', () => {
    expect(formatLiveMinute(KICKOFF, at(105))).toBe("90+'");
    expect(formatLiveMinute(KICKOFF, at(130))).toBe("90+'");
  });
});
