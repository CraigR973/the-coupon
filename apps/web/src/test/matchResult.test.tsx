import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { matchResultPhases, formatMatchResultLine } from '@/lib/matchResult';
import { MatchResult } from '@/components/MatchResult';
import type { MatchResponse } from '@/lib/types';

function makeMatch(overrides: Partial<MatchResponse> = {}): MatchResponse {
  return {
    id: 'm1',
    match_number: 75,
    stage: 'r32',
    group_id: null,
    group_name: null,
    home_team: null,
    away_team: null,
    home_team_placeholder: null,
    away_team_placeholder: null,
    kickoff_utc: '2026-06-29T20:30:00Z',
    venue: null,
    status: 'completed',
    actual_home_score: 2,
    actual_away_score: 1,
    extra_time: false,
    penalties: false,
    postponed_reason: null,
    ...overrides,
  };
}

describe('matchResultPhases', () => {
  it('returns nothing when there is no final score', () => {
    expect(
      matchResultPhases(
        makeMatch({ status: 'scheduled', actual_home_score: null, actual_away_score: null }),
      ),
    ).toEqual([]);
  });

  it('one unlabelled phase for a 90-minute result', () => {
    expect(matchResultPhases(makeMatch({ actual_home_score: 2, actual_away_score: 1 }))).toEqual([
      { label: null, home: 2, away: 1 },
    ]);
  });

  it('90 / AET / Pens for a shootout (goalless extra time)', () => {
    expect(
      matchResultPhases(
        makeMatch({
          actual_home_score: 1,
          actual_away_score: 1,
          extra_time: true,
          penalties: true,
          extra_time_home_score: 1,
          extra_time_away_score: 1,
          penalty_home_score: 3,
          penalty_away_score: 4,
        }),
      ),
    ).toEqual([
      { label: "90'", home: 1, away: 1 },
      { label: 'AET', home: 1, away: 1 },
      { label: 'Pens', home: 3, away: 4 },
    ]);
  });

  it('90 / AET for an extra-time-decided win', () => {
    expect(
      matchResultPhases(
        makeMatch({
          actual_home_score: 1,
          actual_away_score: 1,
          extra_time: true,
          extra_time_home_score: 2,
          extra_time_away_score: 1,
        }),
      ),
    ).toEqual([
      { label: "90'", home: 1, away: 1 },
      { label: 'AET', home: 2, away: 1 },
    ]);
  });

  it('omits the pens line and falls back to the 90 score for AET when tallies are missing', () => {
    expect(
      matchResultPhases(
        makeMatch({
          actual_home_score: 1,
          actual_away_score: 1,
          extra_time: true,
          penalties: true,
        }),
      ),
    ).toEqual([
      { label: "90'", home: 1, away: 1 },
      { label: 'AET', home: 1, away: 1 },
    ]);
  });
});

describe('formatMatchResultLine', () => {
  it('plain for a 90-minute result', () => {
    expect(formatMatchResultLine(makeMatch({ actual_home_score: 2, actual_away_score: 1 }))).toBe(
      '2 – 1',
    );
  });

  it('joins labelled phases for a shootout', () => {
    expect(
      formatMatchResultLine(
        makeMatch({
          actual_home_score: 1,
          actual_away_score: 1,
          extra_time: true,
          penalties: true,
          extra_time_home_score: 1,
          extra_time_away_score: 1,
          penalty_home_score: 3,
          penalty_away_score: 4,
        }),
      ),
    ).toBe("90' 1–1 · AET 1–1 · Pens 3–4");
  });
});

describe('<MatchResult>', () => {
  it('renders a bare score for a 90-minute result', () => {
    const { container } = render(
      <MatchResult match={makeMatch({ actual_home_score: 2, actual_away_score: 1 })} />,
    );
    expect(container.textContent).toBe('2 – 1');
    expect(screen.queryByTestId('match-result-phases')).toBeNull();
  });

  it('renders stacked labelled phases for a shootout', () => {
    render(
      <MatchResult
        match={makeMatch({
          actual_home_score: 1,
          actual_away_score: 1,
          extra_time: true,
          penalties: true,
          extra_time_home_score: 1,
          extra_time_away_score: 1,
          penalty_home_score: 3,
          penalty_away_score: 4,
        })}
      />,
    );
    const block = screen.getByTestId('match-result-phases');
    expect(block.textContent).toContain("90'");
    expect(block.textContent).toContain('AET');
    expect(block.textContent).toContain('Pens');
    expect(block.textContent).toContain('3 – 4');
  });
});
