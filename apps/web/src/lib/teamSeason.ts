import type { MatchState, TeamSeason, TeamSeasonMatch } from './types';

/** The states that mean "this match still has to be played". */
const STILL_TO_COME: ReadonlySet<MatchState> = new Set<MatchState>([
  'scheduled',
  'live',
  'postponed',
]);

/** The states a match can be "next" in. A cancelled game is never next; a postponed
 *  one has no date left to be next *on*, only the one it was called off from. */
const PLAYABLE_NEXT: ReadonlySet<MatchState> = new Set<MatchState>(['live', 'scheduled']);

export interface SeasonSplit {
  /** Finished matches, **newest first** — a results list is read backwards. */
  results: TeamSeasonMatch[];
  /**
   * Everything still to come, **chronologically** — a fixture list is read forwards.
   *
   * Cancelled matches are here rather than dropped: a season with a hole in it should
   * say so. They sort on the kickoff they were called off from, which is the only date
   * they have.
   */
  fixtures: TeamSeasonMatch[];
  /** The match to draw attention to, or `null` for a season with nothing left. */
  next: TeamSeasonMatch | null;
}

/**
 * A club's season as the two lists a reader actually wants (Batch 111).
 *
 * The API returns one chronological list because that is what the season *is*; the
 * split is presentation, and it belongs here rather than in the component so the
 * ordering rules can be tested without rendering anything.
 *
 * **The two halves are ordered in opposite directions on purpose.** What a member wants
 * from the played half is the most recent result, and from the unplayed half the next
 * fixture — so both lists put the interesting end first, and the seam between them is
 * "now".
 */
export function splitSeason(season: TeamSeason | undefined): SeasonSplit {
  const matches = Array.isArray(season?.matches) ? season.matches : [];
  const byKickoff = (a: TeamSeasonMatch, b: TeamSeasonMatch) =>
    a.kickoff_utc.localeCompare(b.kickoff_utc) || a.match_id.localeCompare(b.match_id);

  const results = matches.filter((match) => match.state === 'finished').sort(byKickoff).reverse();
  const fixtures = matches.filter((match) => STILL_TO_COME.has(match.state)).sort(byKickoff);
  const cancelled = matches.filter((match) => match.state === 'cancelled').sort(byKickoff);

  const upcoming = [...fixtures, ...cancelled].sort(byKickoff);

  return {
    results,
    fixtures: upcoming,
    // The first one that can actually be played. A postponed match sorts into the list
    // on a date it is no longer being played on, so highlighting it would point a member
    // at a night nothing happens.
    next: upcoming.find((match) => PLAYABLE_NEXT.has(match.state)) ?? null,
  };
}

/** `2026` → `2026/27` — how a British football season is written. */
export function seasonLabel(season: number): string {
  return `${season}/${String((season + 1) % 100).padStart(2, '0')}`;
}

/**
 * The address of one club's season.
 *
 * Both query parameters are required rather than inferred: a club plays a league and a
 * cup in the same year, and the reader is looking at one table when they follow this.
 */
export function teamSeasonPath(teamId: string, competitionId: string, season: number): string {
  const query = new URLSearchParams({ competition: competitionId, season: String(season) });
  return `/football/teams/${teamId}?${query}`;
}

/**
 * The address to go back to — the table this club was opened from.
 *
 * Carries the competition and season so the division the member had expanded is open
 * again when they land, which is also what lets the browser restore their scroll
 * position: a page that comes back a different height scrolls back to somewhere else.
 */
export function tablePathFor(competitionId: string, season: number): string {
  const query = new URLSearchParams({ competition: competitionId, season: String(season) });
  return `/football?${query}`;
}
