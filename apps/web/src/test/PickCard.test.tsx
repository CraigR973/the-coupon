import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PickCard } from '@/components/PickCard';
import type { FixtureSlate } from '@/lib/types';

const FIXTURE: FixtureSlate = {
  fixture_id: 'fx1',
  provider_event_id: 'ev1',
  home: 'Forfar',
  away: 'Brechin',
  competition: 'Scottish League 2',
  kickoff_utc: '2026-08-08T14:00:00Z',
  selections: [
    { market: 'MATCH_ODDS', outcome: 'HOME', runner_name: 'Forfar', odds: 2.0, taken_by_player_id: null, taken_by_name: null, mine: false },
    { market: 'MATCH_ODDS', outcome: 'DRAW', runner_name: 'The Draw', odds: 3.5, taken_by_player_id: 'p1', taken_by_name: 'Alice Adams', mine: true },
    { market: 'MATCH_ODDS', outcome: 'AWAY', runner_name: 'Brechin', odds: 3.2, taken_by_player_id: 'p2', taken_by_name: 'Bob Baker', mine: false },
    { market: 'BOTH_TEAMS_TO_SCORE', outcome: 'YES', runner_name: 'Yes', odds: 1.8, taken_by_player_id: null, taken_by_name: null, mine: false },
  ],
};

function renderCard(overrides: Partial<React.ComponentProps<typeof PickCard>> = {}) {
  const onGrab = vi.fn();
  render(
    <PickCard
      fixture={FIXTURE}
      timezone="UTC"
      locked={false}
      pendingKey={null}
      busy={false}
      onGrab={onGrab}
      {...overrides}
    />,
  );
  return { onGrab };
}

describe('PickCard', () => {
  it('renders the fixture teams, competition and odds', () => {
    renderCard();
    // Team names appear in both the header and the match-odds selection labels.
    expect(screen.getAllByText('Forfar').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Brechin').length).toBeGreaterThan(0);
    expect(screen.getByText('Scottish League 2')).toBeTruthy();
    expect(screen.getByText('2.00')).toBeTruthy();
  });

  it('grabs an available selection and reports the identity to onGrab', () => {
    const { onGrab } = renderCard();
    fireEvent.click(screen.getByTestId('selection-fx1-MATCH_ODDS-HOME'));
    expect(onGrab).toHaveBeenCalledWith('fx1', 'MATCH_ODDS', 'HOME');
  });

  it('marks the caller’s own selection as the current pick', () => {
    renderCard();
    const draw = screen.getByTestId('selection-fx1-MATCH_ODDS-DRAW');
    expect(draw.getAttribute('aria-pressed')).toBe('true');
    expect(draw.textContent).toContain('your pick');
  });

  it('shows a selection held by another member as unavailable', () => {
    const { onGrab } = renderCard();
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY') as HTMLButtonElement;
    expect(away.disabled).toBe(true);
    expect(away.textContent).toContain('taken by Bob');
    fireEvent.click(away);
    expect(onGrab).not.toHaveBeenCalled();
  });

  it('disables every selection once locked', () => {
    const { onGrab } = renderCard({ locked: true });
    const home = screen.getByTestId('selection-fx1-MATCH_ODDS-HOME') as HTMLButtonElement;
    expect(home.disabled).toBe(true);
    fireEvent.click(home);
    expect(onGrab).not.toHaveBeenCalled();
  });
});
