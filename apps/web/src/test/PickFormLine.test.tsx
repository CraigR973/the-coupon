import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PickFormLine } from '@/components/PickFormLine';
import type { FormRound } from '@/lib/types';

/**
 * Batch 80. Every figure on the leaderboard was a season aggregate, so a member who has
 * won the last four rounds and one who has scored nothing since July read identically.
 *
 * The assertions that matter are the two that would be quietly wrong: a void round is
 * not a defeat, and a run of letters cannot carry points that are `round(odds × 10)`.
 */

function round(overrides: Partial<FormRound> = {}): FormRound {
  return {
    gameweek_id: `gw-${Math.random().toString(36).slice(2, 8)}`,
    starts_on: '2026-08-22',
    status: 'won',
    points: 20,
    ...overrides,
  };
}

describe('PickFormLine', () => {
  it('draws the run oldest-first, against an API that sends it newest-first', () => {
    // The whole point of the order: the nth pip is the nth round, matching every other
    // form line in the app and any panel a reader opens underneath one.
    render(
      <PickFormLine
        form={[
          round({ gameweek_id: 'newest', status: 'lost', points: 0 }),
          round({ gameweek_id: 'oldest', status: 'won', points: 35 }),
        ]}
      />,
    );
    expect(screen.getByTestId('pick-form').textContent).toBe('W35L');
  });

  it('gives a void round its own letter rather than the draw’s', () => {
    // A void fixture never ran. Reusing `FormLine`'s `D` would erase the distinction
    // `picks_played` and `picks_priced` exist to keep, in the place it is most visible.
    render(<PickFormLine form={[round({ status: 'void', points: 0 })]} />);
    const run = screen.getByTestId('pick-form');
    expect(run.textContent).toContain('V');
    expect(run.textContent).not.toContain('D');
  });

  it('carries what each round scored, because the letters cannot', () => {
    // One win at 5.00 outscores two at 2.00. A run drawn as letters alone would read
    // the same for both.
    render(
      <PickFormLine
        form={[round({ status: 'won', points: 50 }), round({ status: 'won', points: 20 })]}
      />,
    );
    expect(screen.getByTestId('pick-form').textContent).toBe('W20W50');
  });

  it('leaves a zero blank rather than printing a column of noughts', () => {
    render(<PickFormLine form={[round({ status: 'lost', points: 0 })]} />);
    expect(screen.getByTestId('pick-form').textContent).toBe('L');
  });

  it('says the result in words, not only in colour', () => {
    render(
      <PickFormLine
        form={[round({ status: 'void', points: 0 }), round({ status: 'won', points: 35 })]}
        player="Alice"
      />,
    );
    const label = screen.getByTestId('pick-form').getAttribute('aria-label') ?? '';
    expect(label).toContain('Alice');
    expect(label).toContain('won 35 points');
    expect(label).toContain('void');
  });

  it('renders nothing for a member with no settled rounds', () => {
    const { container } = render(<PickFormLine form={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing against an API that predates the field', () => {
    // Vercel deploys this app from `main` on merge while the API waits for /ship-prod.
    const { container } = render(<PickFormLine form={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});
