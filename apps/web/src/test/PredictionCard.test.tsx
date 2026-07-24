import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PredictionCard } from '@/components/PredictionCard';
import type {
  MatchResponse,
  PredictionResponse,
  KnockoutPredictionResponse,
} from '@/lib/types';

// ---------------------------------------------------------------------------
// PredictionCard — knockout who-progresses picker.
//
// The picker is safety-critical: the scoring trigger grades knockout
// progression purely on `predicted_winner_id`, so the card must (a) auto-save
// the score-implied winner on a clear 90-min win, (b) never let a stray tap on
// the losing team overwrite that winner, and (c) require a manual pick only on
// a predicted draw.
// ---------------------------------------------------------------------------

const HOME_ID = 'home';
const AWAY_ID = 'away';

function koMatch(overrides: Record<string, unknown> = {}): MatchResponse {
  return {
    id: 'm73',
    match_number: 73,
    stage: 'r32',
    group_id: null,
    group_name: null,
    home_team: { id: HOME_ID, name: 'Netherlands', code: 'NED', flag_emoji: '🇳🇱' },
    away_team: { id: AWAY_ID, name: 'Uruguay', code: 'URU', flag_emoji: '🇺🇾' },
    home_team_placeholder: null,
    away_team_placeholder: null,
    kickoff_utc: '2026-07-01T20:00:00Z',
    venue: 'MetLife Stadium',
    status: 'scheduled',
    actual_home_score: null,
    actual_away_score: null,
    extra_time: false,
    penalties: false,
    postponed_reason: null,
    ...overrides,
  } as unknown as MatchResponse;
}

function scorePred(home: number, away: number): PredictionResponse {
  return {
    id: 'p',
    player_id: 'p1',
    match_id: 'm73',
    predicted_home: home,
    predicted_away: away,
    submitted_at: null,
    update_count: 0,
    points_awarded: null,
    points_breakdown: null,
    updated_at: '',
  } as unknown as PredictionResponse;
}

function koPred(winnerId: string): KnockoutPredictionResponse {
  return {
    id: 'kp',
    player_id: 'p1',
    match_id: 'm73',
    predicted_winner_id: winnerId,
    submitted_at: null,
    update_count: 0,
    points_awarded: null,
    updated_at: '',
  };
}

function renderCard(props: Partial<React.ComponentProps<typeof PredictionCard>>) {
  return render(
    <PredictionCard
      match={koMatch()}
      prediction={undefined}
      local={undefined}
      timezone="UTC"
      highlighted={false}
      onHomeChange={vi.fn()}
      onAwayChange={vi.fn()}
      onKnockoutWinnerChange={vi.fn()}
      {...props}
    />,
  );
}

beforeEach(() => {
  // Pin "now" to before the July fixture so `canEdit` (scheduled && kickoff >
  // Date.now()) stays deterministic as the real tournament dates pass.
  vi.spyOn(Date, 'now').mockReturnValue(new Date('2026-06-01T12:00:00Z').getTime());
});

describe('PredictionCard — knockout who-progresses', () => {
  it('predicted draw: both team buttons are tappable and a tap reports the picked team', () => {
    const onPick = vi.fn();
    renderCard({ prediction: scorePred(1, 1), onKnockoutWinnerChange: onPick });

    expect(screen.getByText(/draw: tap to pick/i)).toBeTruthy();
    const ned = screen.getByRole('button', { name: /Netherlands/ }) as HTMLButtonElement;
    const uru = screen.getByRole('button', { name: /Uruguay/ }) as HTMLButtonElement;
    expect(ned.disabled).toBe(false);
    expect(uru.disabled).toBe(false);

    fireEvent.click(uru);
    expect(onPick).toHaveBeenCalledWith('m73', AWAY_ID);
  });

  it('clear 90-min win: the implied progressor is highlighted and BOTH buttons are read-only', () => {
    const onPick = vi.fn();
    // knockoutPrediction already matches the auto-winner, so the auto-save
    // effect is a no-op and we can isolate the button interactivity.
    renderCard({
      prediction: scorePred(2, 1),
      knockoutPrediction: koPred(HOME_ID),
      onKnockoutWinnerChange: onPick,
    });

    const winner = screen.getByRole('button', { name: /Netherlands/ }) as HTMLButtonElement;
    const loser = screen.getByRole('button', { name: /Uruguay/ }) as HTMLButtonElement;

    expect(winner.disabled).toBe(true);
    expect(loser.disabled).toBe(true);
    expect(winner.textContent).toMatch(/✓/);
    expect(winner.className).toMatch(/border-success/);

    // F1 regression: the losing team must not be selectable on a clear win —
    // tapping it previously overwrote the correct winner and silently zeroed
    // the player's progression points.
    fireEvent.click(loser);
    expect(onPick).not.toHaveBeenCalled();
  });

  it('clear 90-min win: auto-saves the score-implied winner with no manual pick needed', async () => {
    const onPick = vi.fn();
    renderCard({ prediction: scorePred(2, 1), onKnockoutWinnerChange: onPick });

    await waitFor(() => expect(onPick).toHaveBeenCalledWith('m73', HOME_ID), { timeout: 1500 });
  });

  it('unresolved knockout tie (placeholder teams): renders no who-progresses buttons', () => {
    renderCard({
      match: koMatch({
        home_team: null,
        away_team: null,
        home_team_placeholder: 'Winner Group A',
        away_team_placeholder: 'Best 3rd #1',
      }),
    });

    expect(screen.queryByText(/Who progresses/i)).toBeNull();
  });

  it('group-stage match: no 90-min label and no who-progresses section', () => {
    renderCard({ match: koMatch({ stage: 'group', group_name: 'A' }), prediction: scorePred(1, 1) });

    expect(screen.queryByText(/Who progresses/i)).toBeNull();
    expect(screen.queryByText(/90-min score/i)).toBeNull();
  });
});
