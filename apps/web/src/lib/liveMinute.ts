const FIRST_HALF_MINUTES = 45;
const HALF_TIME_BREAK_MINUTES = 15;
const FULL_TIME_MINUTES = 90;

/**
 * Numeric counterpart to `formatLiveMinute`, used when we need a stable ordering
 * for live matches even though the upstream feed usually omits a real match clock.
 */
export function approximateLiveMinute(kickoffUtc: string, now: number = Date.now()): number | null {
  const kickoffMs = new Date(kickoffUtc).getTime();
  if (Number.isNaN(kickoffMs)) return null;

  const elapsedWall = Math.floor((now - kickoffMs) / 60_000);
  if (elapsedWall < 0) return null;
  if (elapsedWall <= FIRST_HALF_MINUTES) return elapsedWall;
  if (elapsedWall <= FIRST_HALF_MINUTES + HALF_TIME_BREAK_MINUTES) return FIRST_HALF_MINUTES;

  const playMinute = elapsedWall - HALF_TIME_BREAK_MINUTES;
  return Math.min(playMinute, FULL_TIME_MINUTES);
}

/**
 * Approximate live-match minute, derived from kickoff wall-clock time.
 *
 * The football-data free tier carries no match clock (it serves live full-time +
 * half-time scores only — U63), so there is no real minute to display. We estimate
 * from elapsed wall time, which deliberately can't see added time or the exact
 * half-time break. To avoid showing an impossible "104'", we render "HT" across the
 * break window, discount a nominal 15-min break in the second half, and cap at
 * "90+'". Treat the result as a rough live indicator, not the official minute.
 *
 * Returns `null` before kickoff (nothing sensible to show) or for an invalid date.
 */
export function formatLiveMinute(kickoffUtc: string, now: number = Date.now()): string | null {
  const kickoffMs = new Date(kickoffUtc).getTime();
  if (Number.isNaN(kickoffMs)) return null;

  const elapsedWall = Math.floor((now - kickoffMs) / 60_000);
  if (elapsedWall < 0) return null; // not kicked off yet

  // First half (and a touch of first-half stoppage) shows the raw elapsed minute.
  if (elapsedWall <= FIRST_HALF_MINUTES) return `${elapsedWall}'`;

  // The ~15-min half-time window: don't pretend to know the exact minute.
  if (elapsedWall <= FIRST_HALF_MINUTES + HALF_TIME_BREAK_MINUTES) return 'HT';

  // Second half: discount the break so the clock reads ~46'+ rather than ~61'+.
  const playMinute = approximateLiveMinute(kickoffUtc, now);
  if (playMinute === null) return null;
  if (playMinute >= FULL_TIME_MINUTES) return `${FULL_TIME_MINUTES}+'`;
  return `${playMinute}'`;
}
