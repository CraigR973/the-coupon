// ---------------------------------------------------------------------------
// League admin configuration helpers (Batch 15) — shared by the create and
// settings screens so the two present the window and markets identically.
// ---------------------------------------------------------------------------

import type { PickMarket, SlateWindow } from './types';

/** `date.weekday()` order: Monday 0 … Sunday 6, matching the backend. */
export const WEEKDAYS: { value: number; label: string }[] = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
];

/** The rule the product shipped with, and the default a new league gets. */
export const SATURDAY_3PM_WINDOW: SlateWindow = {
  start_weekday: 5,
  start_minute: 15 * 60,
  end_weekday: 5,
  end_minute: 15 * 60,
  lock_offset_minutes: 30,
};

/** Minutes-from-midnight → an `HH:MM` string for a native time input. */
export function minutesToHHMM(minutes: number): string {
  const clamped = Math.max(0, Math.min(1439, Math.round(minutes)));
  const h = Math.floor(clamped / 60);
  const m = clamped % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** `HH:MM` → minutes-from-midnight; invalid input falls back to `fallback`. */
export function hhmmToMinutes(value: string, fallback = 0): number {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return fallback;
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return Number.isFinite(minutes) && minutes >= 0 && minutes <= 1439 ? minutes : fallback;
}

/** All markets the game can offer, with the labels the UI shows. */
export const ALL_MARKETS: { value: PickMarket; label: string }[] = [
  { value: 'MATCH_ODDS', label: 'Match result (1 · X · 2)' },
  { value: 'BOTH_TEAMS_TO_SCORE', label: 'Both teams to score' },
];

/** True when a window is exactly the Saturday-15:00 default. */
export function isSaturday3pm(window: SlateWindow): boolean {
  return (
    window.start_weekday === 5 &&
    window.start_minute === 900 &&
    window.end_weekday === 5 &&
    window.end_minute === 900 &&
    window.lock_offset_minutes === 30
  );
}

/** A short human summary of a window, e.g. "Saturday 15:00" or "Friday 19:00 – Monday 22:00". */
export function describeWindow(window: SlateWindow): string {
  const day = (w: number) => WEEKDAYS[w]?.label ?? '?';
  const start = `${day(window.start_weekday)} ${minutesToHHMM(window.start_minute)}`;
  if (window.start_weekday === window.end_weekday && window.start_minute === window.end_minute) {
    return start;
  }
  return `${start} – ${day(window.end_weekday)} ${minutesToHHMM(window.end_minute)}`;
}
