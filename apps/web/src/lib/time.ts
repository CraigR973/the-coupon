import { format } from 'date-fns';
import { formatInTimeZone } from 'date-fns-tz';

/**
 * Reading the API's dates and times without an hour going missing (Batch 43).
 *
 * Two different things arrive from the API and only one of them is an instant:
 *
 * - **Instants** — `locks_at_utc`, `kickoff_utc`, `taken_at`, `created_at`. A moment
 *   in time, rendered in the member's timezone.
 * - **Calendar dates** — `starts_on`. A day in the league's football calendar, the
 *   same day for every member wherever they read it.
 *
 * `new Date(string)` gets both wrong in its own way. A date-time carrying no offset
 * (`"2026-08-22T13:30:00"`, which is what the API sent before Batch 43) is parsed as
 * **local** time, so the wall-clock number never moves and a 13:30 UTC lock reads as
 * 13:30 anywhere — an hour early in London under BST. A date-only string
 * (`"2026-08-22"`) is parsed as UTC **midnight**, so converting it into a timezone
 * west of UTC lands on the previous day and the round is announced for the wrong
 * Saturday.
 *
 * The durable fix for the first is at the API boundary — it now stamps `Z` on every
 * instant (`apps/api/src/schemas.py`). `parseInstant` keeps the client right anyway,
 * because Vercel deploys this app from `main` the moment it merges while the API waits
 * for `/ship-prod`: for that window the browser is talking to an API that still sends
 * the offset-less form, and members should not lose an hour of the round to a deploy
 * ordering they cannot see.
 */

/** True for a date-time that names no offset — neither `Z` nor `±HH:MM`. */
function lacksOffset(iso: string): boolean {
  if (!iso.includes('T')) return false;
  const time = iso.slice(iso.indexOf('T') + 1);
  return !/([zZ]|[+-]\d{2}:?\d{2})$/.test(time);
}

/**
 * Parse an instant from the API, treating a missing offset as UTC.
 *
 * UTC is the right assumption rather than a hopeful one: every datetime column in
 * this product is stored in UTC, so an offset-less value is UTC that lost its label
 * on the way out.
 */
export function parseInstant(iso: string): Date {
  return new Date(lacksOffset(iso) ? `${iso}Z` : iso);
}

/** Render an API instant in `timezone`. Returns `null` when it does not parse. */
export function formatInstant(
  iso: string | null | undefined,
  timezone: string,
  pattern: string,
): string | null {
  if (!iso) return null;
  const at = parseInstant(iso);
  if (Number.isNaN(at.getTime())) return null;
  return formatInTimeZone(at, timezone, pattern);
}

/**
 * Render an API calendar date (`YYYY-MM-DD`) as the day it names.
 *
 * Deliberately not timezone-converted: `starts_on` is the day the round is played,
 * not an instant, and shifting it into the reader's zone can only ever move it to a
 * day the league is not playing.
 */
export function formatCalendarDate(value: string, pattern: string): string {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return format(new Date(year, month - 1, day), pattern);
}
