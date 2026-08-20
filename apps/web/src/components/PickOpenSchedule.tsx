import type { GameweekSummary } from '../lib/types';
import { roundName } from '../lib/coupon';
import { formatCalendarDate, formatInstant } from '../lib/time';

export interface PickOpenScheduleProps {
  /** The season, newest first — exactly what `GET /leagues/{slug}/gameweeks` returns. */
  gameweeks: GameweekSummary[];
  /** The admin's own timezone, so the instant reads on the clock they are looking at. */
  timezone: string;
  /** True when the league announces an opening at all. */
  announced: boolean;
}

/**
 * Rounds an opening time can still apply to — anything not yet locked or settled.
 *
 * `Array.isArray` rather than trusting the parameter: the web app deploys ahead of the
 * API, so an older deployment can answer this route with a shape this build does not
 * expect, and a settings page that throws is a worse outcome than one that shows nothing.
 */
function upcoming(gameweeks: GameweekSummary[]): GameweekSummary[] {
  if (!Array.isArray(gameweeks)) return [];
  return gameweeks
    .filter((gw) => gw?.status === 'scheduled' || gw?.status === 'open')
    .slice()
    .reverse(); // the list arrives newest first; the next round up is the useful one
}

/**
 * What the rounds already on the board will actually do (Batch 40).
 *
 * `pick_open_offset_minutes` is applied at **discovery**, and a settings change
 * deliberately never restamps a round that already exists — moving a deadline members
 * were already told is the one thing the PATCH refuses to do. That rule is correct and
 * it is staying, but it was invisible at exactly the moment it bites: an admin sets
 * twelve hours, saves, sees picks open anyway, and nothing on the screen explains why.
 *
 * So this says it plainly. A round carrying `picks_open_at_utc = null` predates the
 * setting and has **no opening gate at all** — it is claimable from the moment discovery
 * wrote it, which is the documented pre-Batch-27 rule and not an older offset. That is
 * the case that reads as "my setting was ignored", so it is the one named most clearly.
 */
export function PickOpenSchedule({ gameweeks, timezone, announced }: PickOpenScheduleProps) {
  const rounds = upcoming(gameweeks);
  if (rounds.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-border pt-3" data-testid="pick-open-schedule">
      <p className="text-xs font-sans font-medium text-text-primary">
        Rounds already scheduled
      </p>
      <ul className="space-y-1.5">
        {rounds.map((gw) => {
          const label = roundName(gw.number, formatCalendarDate(gw.starts_on, 'd MMM'));
          const opensAt = formatInstant(gw.picks_open_at_utc, timezone, 'EEE d MMM, HH:mm');
          return (
            <li
              key={gw.gameweek_id}
              className="flex flex-wrap items-baseline justify-between gap-x-2 text-xs font-sans"
              data-testid={`pick-open-round-${gw.gameweek_id}`}
            >
              <span className="text-text-secondary">{label}</span>
              {opensAt ? (
                <span className="tabular-nums text-text-primary">Picks open {opensAt}</span>
              ) : (
                <span className="text-text-muted">Open now — no opening time was set</span>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs font-sans text-text-muted">
        {announced
          ? 'Changing the time below applies to rounds discovered from now on. These keep the opening they were created with.'
          : 'These rounds keep the opening they were created with. Turning the setting on applies to rounds discovered from now on.'}
      </p>
    </div>
  );
}
