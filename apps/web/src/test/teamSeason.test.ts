import { describe, it, expect } from 'vitest';
import { seasonLabel, splitSeason, tablePathFor, teamSeasonPath } from '@/lib/teamSeason';
import type { MatchState, TeamSeason, TeamSeasonMatch } from '@/lib/types';

function match(
  id: string,
  day: string,
  state: MatchState,
  extra: Partial<TeamSeasonMatch> = {},
): TeamSeasonMatch {
  const played = state === 'finished';
  return {
    match_id: id,
    kickoff_utc: `${day}T14:00:00Z`,
    opponent: 'Chelsea FC',
    opponent_team_id: 't-chelsea',
    home: true,
    state,
    status: played ? 'FT' : '',
    goals_for: played ? 2 : null,
    goals_against: played ? 1 : null,
    result: played ? 'W' : null,
    ...extra,
  };
}

function season(matches: TeamSeasonMatch[]): TeamSeason {
  return {
    team_id: 't-arsenal',
    team: 'Arsenal FC',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    season: 2026,
    matches,
  };
}

describe('splitSeason', () => {
  /**
   * The two halves run in opposite directions on purpose: what a member wants from the
   * played half is the most recent result, and from the unplayed half the next fixture.
   */
  it('reads results backwards and fixtures forwards', () => {
    const { results, fixtures } = splitSeason(
      season([
        match('r1', '2026-08-08', 'finished'),
        match('r2', '2026-08-15', 'finished'),
        match('f1', '2026-08-22', 'scheduled'),
        match('f2', '2026-08-29', 'scheduled'),
      ]),
    );
    expect(results.map((m) => m.match_id)).toEqual(['r2', 'r1']);
    expect(fixtures.map((m) => m.match_id)).toEqual(['f1', 'f2']);
  });

  it('orders each half itself, whatever order the API sent', () => {
    const { results, fixtures } = splitSeason(
      season([
        match('f2', '2026-08-29', 'scheduled'),
        match('r1', '2026-08-08', 'finished'),
        match('f1', '2026-08-22', 'scheduled'),
        match('r2', '2026-08-15', 'finished'),
      ]),
    );
    expect(results.map((m) => m.match_id)).toEqual(['r2', 'r1']);
    expect(fixtures.map((m) => m.match_id)).toEqual(['f1', 'f2']);
  });

  it('keeps postponed and cancelled matches visible among the fixtures', () => {
    const { fixtures } = splitSeason(
      season([
        match('pp', '2026-08-22', 'postponed'),
        match('can', '2026-08-25', 'cancelled'),
        match('sch', '2026-08-29', 'scheduled'),
      ]),
    );
    // A season with a hole in it should say so rather than quietly lose the row.
    expect(fixtures.map((m) => m.match_id)).toEqual(['pp', 'can', 'sch']);
  });

  it('calls the earliest playable match next', () => {
    const { next } = splitSeason(
      season([
        match('r1', '2026-08-08', 'finished'),
        match('f1', '2026-08-22', 'scheduled'),
        match('f2', '2026-08-29', 'scheduled'),
      ]),
    );
    expect(next?.match_id).toBe('f1');
  });

  /**
   * A postponed match sorts into the list on the date it is *not* being played on, so
   * pointing "Next" at it would send a member to a night nothing happens. A cancelled
   * one is never next at all.
   */
  it('skips past a postponed or cancelled match to find the next real one', () => {
    const { next } = splitSeason(
      season([
        match('pp', '2026-08-15', 'postponed'),
        match('can', '2026-08-18', 'cancelled'),
        match('sch', '2026-08-22', 'scheduled'),
      ]),
    );
    expect(next?.match_id).toBe('sch');
  });

  it('prefers a match being played right now', () => {
    const { next } = splitSeason(
      season([match('live', '2026-08-22', 'live'), match('sch', '2026-08-29', 'scheduled')]),
    );
    expect(next?.match_id).toBe('live');
  });

  it('has no next fixture once the season is played out', () => {
    const { next, fixtures, results } = splitSeason(
      season([match('r1', '2026-08-08', 'finished'), match('r2', '2026-08-15', 'finished')]),
    );
    expect(next).toBeNull();
    expect(fixtures).toEqual([]);
    expect(results).toHaveLength(2);
  });

  it('survives a season that has not loaded, and one with nothing in it', () => {
    expect(splitSeason(undefined)).toEqual({ results: [], fixtures: [], next: null });
    expect(splitSeason(season([]))).toEqual({ results: [], fixtures: [], next: null });
  });

  it('breaks a same-kickoff tie on a stable key so a card cannot reshuffle', () => {
    const { fixtures } = splitSeason(
      season([match('b', '2026-08-22', 'scheduled'), match('a', '2026-08-22', 'scheduled')]),
    );
    expect(fixtures.map((m) => m.match_id)).toEqual(['a', 'b']);
  });
});

describe('addresses', () => {
  it('writes a season as British football writes it', () => {
    expect(seasonLabel(2026)).toBe('2026/27');
    expect(seasonLabel(2009)).toBe('2009/10');
    expect(seasonLabel(1999)).toBe('1999/00');
  });

  it('carries both the competition and the season into a club link', () => {
    expect(teamSeasonPath('t-arsenal', 'england-premier-league', 2026)).toBe(
      '/football/teams/t-arsenal?competition=england-premier-league&season=2026',
    );
  });

  it('sends the reader back to the division they came from', () => {
    expect(tablePathFor('england-premier-league', 2026)).toBe(
      '/football?competition=england-premier-league&season=2026',
    );
  });

  it('escapes a competition slug rather than pasting it into a query', () => {
    expect(teamSeasonPath('t 1', 'a&b=c', 2026)).toContain('competition=a%26b%3Dc');
  });
});
