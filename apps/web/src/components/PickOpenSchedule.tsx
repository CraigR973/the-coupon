import type { GameweekSummary } from '../lib/types';
import { pickRefusal, roundName } from '../lib/coupon';
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
 * Rounds an opening time can still apply to — anything whose deadline is still ahead.
 *
 * Filtered on `pickRefusal` rather than on `status` (Batch 73), because `status` is only
 * what the hourly jobs have caught up with and `rederive_claim_periods` bounds itself on
 * `locks_at_utc > now`. A round still labelled `open` an hour after its deadline would
 * otherwise be listed here as something this setting moves, which it is not.
 *
 * `Array.isArray` rather than trusting the parameter: the web app deploys ahead of the
 * API, so an older deployment can answer this route with a shape this build does not
 * expect, and a settings page that throws is a worse outcome than one that shows nothing.
 */
function upcoming(gameweeks: GameweekSummary[]): GameweekSummary[] {
  if (!Array.isArray(gameweeks)) return [];
  return gameweeks
    .filter((gw) => gw && pickRefusal(gw) !== 'PICKS_LOCKED')
    .slice()
    .reverse(); // the list arrives newest first; the next round up is the useful one
}

/**
 * What the rounds already on the board will actually do (Batch 40, corrected in Batch 73).
 *
 * **This screen used to say the opposite of the truth.** It told the admin a settings
 * change "never restamps a round that already exists", which was right when Batch 40
 * wrote it and wrong from Batch 65 onwards: `rederive_claim_periods` now restamps both
 * ends of the claim period on every round that has **not locked**, so the setting reaches
 * each round the admin can see rather than only the next one discovered. That is the text
 * they read while making this exact change, so it was wrong at the worst possible moment.
 *
 * The half that did not change is the half that was load-bearing: a round that has
 * already locked keeps its deadline, because members were told it and claimed against it.
 *
 * A round carrying `picks_open_at_utc = null` has **no opening gate at all** — it is
 * claimable from the moment discovery wrote it, which is the documented pre-Batch-27 rule
 * and not an older offset. That is the case that reads as "my setting was ignored", so it
 * is the one named most clearly.
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
          ? 'Changing the time below moves the opening on every round listed here, and applies to rounds discovered from now on. A round that has already locked keeps its deadline.'
          : 'Turning the setting on moves the opening on every round listed here, and applies to rounds discovered from now on. A round that has already locked keeps its deadline.'}
      </p>
    </div>
  );
}
