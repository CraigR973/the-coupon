import type { ResultEntry } from './types';
import { compareCompetitions } from './competitions';
import { formatInstant } from './time';

/** The matches one competition played on one day. */
export interface CompetitionGroup {
  competition_id: string;
  competition: string;
  results: ResultEntry[];
}

/** One result-bearing day, addressable by `?date=`. */
export interface ResultDay {
  /** `YYYY-MM-DD` in the member's timezone — the URL value and the stable key. */
  date: string;
  /** `Saturday 2 May 2026` — the heading above the day's matches. */
  label: string;
  /** `Sat 2 May` — the strip's chip, where sixty of them share one row. */
  short: string;
  /** How many matches the day holds, across every competition. */
  matchCount: number;
  competitions: CompetitionGroup[];
}

/**
 * The day a match belongs to, as the member reads it.
 *
 * A kickoff is an instant, and which *day* it lands on depends on where the reader
 * is: a 20:00 UTC Friday night game is Saturday morning in Auckland. The `?date=`
 * value therefore has to be derived in the member's own timezone, or a link they
 * open would select a day their screen does not show.
 *
 * The slice is the fallback for a kickoff that does not parse at all, so a single
 * malformed row lands in its own bucket instead of collapsing every day into one.
 */
function dayKey(result: ResultEntry, timezone: string): string {
  return formatInstant(result.kickoff_utc, timezone, 'yyyy-MM-dd') ?? result.kickoff_utc.slice(0, 10);
}

/**
 * Results as a list of result-bearing days, newest first.
 *
 * **Only days that were played.** A carousel that filled the gaps with empty calendar
 * dates would put a member six taps from the previous matchday in an international
 * break, and every one of those taps would show nothing — the archive is sparse by
 * nature and the navigation should be sparse with it (Batch 109).
 *
 * Days are sorted rather than left in the API's order. `YYYY-MM-DD` sorts
 * lexicographically into chronological order, and the carousel's ends — the disabled
 * previous/next boundaries — are only correct if the sequence is.
 *
 * Within a day the competitions read in `lib/competitions` order, the same order the
 * coupon and the tables use, because a Saturday can hold eighty matches across four
 * divisions and arrival order is no order at all.
 */
export function groupResultDays(results: ResultEntry[], timezone: string): ResultDay[] {
  const days = new Map<string, Map<string, CompetitionGroup>>();
  for (const result of results) {
    const key = dayKey(result, timezone);
    const competitions = days.get(key) ?? new Map<string, CompetitionGroup>();
    days.set(key, competitions);
    const group = competitions.get(result.competition_id) ?? {
      competition_id: result.competition_id,
      competition: result.competition,
      results: [],
    };
    group.results.push(result);
    competitions.set(result.competition_id, group);
  }

  return [...days.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, competitions]) => {
      const grouped = [...competitions.values()].sort(compareCompetitions);
      const first = grouped[0]?.results[0];
      return {
        date,
        // Formatted from a real match rather than from the key, so the calendar
        // arithmetic stays in one place — `formatInstant` — and the heading cannot
        // disagree with the day it was bucketed into.
        label: (first && formatInstant(first.kickoff_utc, timezone, 'EEEE d MMMM yyyy')) ?? date,
        short: (first && formatInstant(first.kickoff_utc, timezone, 'EEE d MMM')) ?? date,
        matchCount: grouped.reduce((total, group) => total + group.results.length, 0),
        competitions: grouped,
      };
    });
}

/**
 * The day to show for a `?date=` value: the one it names, or the latest we hold.
 *
 * A parameter naming a day with no results — a stale link, a hand-typed date, a day
 * whose fixtures were postponed — resolves to the newest day rather than to an empty
 * screen. The URL is left alone in that case: rewriting it during a render would
 * spend a history entry undoing the member's own back button.
 */
export function resolveResultDay(
  days: ResultDay[],
  requested: string | undefined,
): ResultDay | undefined {
  return days.find((day) => day.date === requested) ?? days[0];
}
