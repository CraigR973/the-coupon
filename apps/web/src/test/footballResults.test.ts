import { describe, it, expect } from 'vitest';
import { groupResultDays, resolveResultDay } from '@/lib/footballResults';
import type { ResultEntry } from '@/lib/types';

function result(overrides: Partial<ResultEntry> & Pick<ResultEntry, 'match_id'>): ResultEntry {
  return {
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00Z',
    home: 'Chelsea FC',
    away: 'Arsenal FC',
    home_goals: 0,
    away_goals: 1,
    ...overrides,
  };
}

describe('groupResultDays', () => {
  it('keys each day by its calendar date in the member’s timezone', () => {
    const days = groupResultDays([result({ match_id: 'a' })], 'Europe/London');
    expect(days[0].date).toBe('2026-05-02');
    expect(days[0].label).toBe('Saturday 2 May 2026');
    expect(days[0].short).toBe('Sat 2 May');
  });

  /**
   * The reason the key cannot be derived from the ISO string.
   *
   * A Friday-night 20:45 kickoff in Britain is Saturday morning in Auckland, and a
   * member there scanning for Saturday has to find it under Saturday — otherwise the
   * `?date=` a link carries names a day their own screen does not show.
   */
  it('buckets a late kickoff into the day the member reads it on', () => {
    const late = [result({ match_id: 'a', kickoff_utc: '2026-05-01T19:45:00Z' })];
    expect(groupResultDays(late, 'Europe/London')[0].date).toBe('2026-05-01');
    expect(groupResultDays(late, 'Pacific/Auckland')[0].date).toBe('2026-05-02');
  });

  it('sorts days newest first however the API ordered them', () => {
    const days = groupResultDays(
      [
        result({ match_id: 'a', kickoff_utc: '2026-04-25T14:00:00Z' }),
        result({ match_id: 'b', kickoff_utc: '2026-05-02T14:00:00Z' }),
        result({ match_id: 'c', kickoff_utc: '2026-04-28T19:45:00Z' }),
      ],
      'UTC',
    );
    expect(days.map((day) => day.date)).toEqual(['2026-05-02', '2026-04-28', '2026-04-25']);
  });

  // The carousel's ends are the disabled previous/next controls, and they are only
  // correct if the sequence has no invented stops in it. An international break is
  // three empty weeks; filling them would be three taps that show nothing.
  it('holds only days that were played — no empty calendar dates between them', () => {
    const days = groupResultDays(
      [
        result({ match_id: 'a', kickoff_utc: '2026-04-25T14:00:00Z' }),
        result({ match_id: 'b', kickoff_utc: '2026-05-02T14:00:00Z' }),
      ],
      'UTC',
    );
    expect(days).toHaveLength(2);
  });

  it('orders a day’s competitions down the pyramid and counts its matches', () => {
    const days = groupResultDays(
      [
        result({
          match_id: 'a',
          competition_id: 'scotland-league-two',
          competition: 'Scotland - Scottish League Two',
        }),
        result({ match_id: 'b' }),
        result({ match_id: 'c' }),
      ],
      'UTC',
    );
    expect(days[0].competitions.map((group) => group.competition_id)).toEqual([
      'england-premier-league',
      'scotland-league-two',
    ]);
    expect(days[0].matchCount).toBe(3);
  });

  it('gives a kickoff it cannot parse its own bucket rather than merging every day', () => {
    const days = groupResultDays(
      [result({ match_id: 'a' }), result({ match_id: 'b', kickoff_utc: 'not-a-date' })],
      'UTC',
    );
    expect(days).toHaveLength(2);
    expect(days.map((day) => day.matchCount)).toEqual([1, 1]);
  });
});

describe('resolveResultDay', () => {
  const days = groupResultDays(
    [
      result({ match_id: 'a', kickoff_utc: '2026-05-02T14:00:00Z' }),
      result({ match_id: 'b', kickoff_utc: '2026-04-25T14:00:00Z' }),
    ],
    'UTC',
  );

  it('defaults to the latest day we hold', () => {
    expect(resolveResultDay(days, undefined)?.date).toBe('2026-05-02');
  });

  it('opens the day a link names', () => {
    expect(resolveResultDay(days, '2026-04-25')?.date).toBe('2026-04-25');
  });

  it('falls back to the latest day for a date with no results, or no date at all', () => {
    expect(resolveResultDay(days, '2026-04-26')?.date).toBe('2026-05-02');
    expect(resolveResultDay(days, 'banana')?.date).toBe('2026-05-02');
  });

  it('has nothing to resolve before any results are held', () => {
    expect(resolveResultDay([], '2026-05-02')).toBeUndefined();
  });
});
