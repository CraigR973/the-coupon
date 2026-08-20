import { describe, it, expect } from 'vitest';
import { parseInstant, formatInstant, formatCalendarDate } from '@/lib/time';

/**
 * Batch 43. These run with `TZ=America/New_York` (pinned in `vite.config.ts`), which is
 * load-bearing: in a UTC process a naive string parses to the very instant it names, so
 * every assertion below passes with or without the fix and the suite proves nothing.
 */

describe('parseInstant', () => {
  it('reads an offset-less date-time as UTC, not as local time', () => {
    // What the API sent before Batch 43, and still sends until the next /ship-prod.
    expect(parseInstant('2026-08-22T13:30:00').getTime()).toBe(Date.UTC(2026, 7, 22, 13, 30));
  });

  it('reads the Z form the API sends after Batch 43', () => {
    expect(parseInstant('2026-08-22T13:30:00Z').getTime()).toBe(Date.UTC(2026, 7, 22, 13, 30));
  });

  it('leaves an explicit offset alone', () => {
    expect(parseInstant('2026-08-22T14:30:00+01:00').getTime()).toBe(Date.UTC(2026, 7, 22, 13, 30));
    expect(parseInstant('2026-08-22T09:30:00-04:00').getTime()).toBe(Date.UTC(2026, 7, 22, 13, 30));
  });

  it('keeps fractional seconds', () => {
    expect(parseInstant('2026-08-22T13:30:00.250').getTime()).toBe(
      Date.UTC(2026, 7, 22, 13, 30, 0, 250),
    );
  });

  it('does not stamp UTC on a date-only value', () => {
    // `2026-08-22` is already UTC midnight to `Date`; appending `Z` would be a no-op
    // that quietly claims the string is an instant. It is not — see formatCalendarDate.
    expect(parseInstant('2026-08-22').getTime()).toBe(Date.UTC(2026, 7, 22));
  });
});

describe('formatInstant', () => {
  it('renders a 13:30 UTC lock as 14:30 in London under BST', () => {
    expect(formatInstant('2026-08-22T13:30:00', 'Europe/London', 'HH:mm')).toBe('14:30');
  });

  it('renders the same instant as 09:30 in New York', () => {
    expect(formatInstant('2026-08-22T13:30:00', 'America/New_York', 'HH:mm')).toBe('09:30');
  });

  it('renders a winter instant as 13:30 in London under GMT', () => {
    // The half of the year that hid this bug: with no offset in play the wrong code
    // and the right code agree, and they will again next late October.
    expect(formatInstant('2026-12-19T13:30:00', 'Europe/London', 'HH:mm')).toBe('13:30');
  });

  it('crosses the date line where the zone does', () => {
    expect(formatInstant('2026-08-22T02:00:00', 'America/New_York', 'd MMM, HH:mm')).toBe(
      '21 Aug, 22:00',
    );
  });

  it('returns null for a missing or unparseable value', () => {
    expect(formatInstant(null, 'Europe/London', 'HH:mm')).toBeNull();
    expect(formatInstant(undefined, 'Europe/London', 'HH:mm')).toBeNull();
    expect(formatInstant('not a date', 'Europe/London', 'HH:mm')).toBeNull();
  });
});

describe('formatCalendarDate', () => {
  it('renders the day it names, in any reader’s zone', () => {
    // `new Date('2026-08-22')` is UTC midnight, so converting it into New York lands on
    // the 21st and announces the round for a Friday the league does not play.
    expect(formatCalendarDate('2026-08-22', 'EEE d MMM yyyy')).toBe('Sat 22 Aug 2026');
  });

  it('handles the first of a month, where an off-by-one crosses two boundaries', () => {
    expect(formatCalendarDate('2026-03-01', 'EEEE d MMMM')).toBe('Sunday 1 March');
  });

  it('returns the input unchanged when it is not a calendar date', () => {
    expect(formatCalendarDate('', 'd MMM')).toBe('');
    expect(formatCalendarDate('nonsense', 'd MMM')).toBe('nonsense');
  });
});
