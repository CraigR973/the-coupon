import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  PickShapeGrid,
  PickShapeLine,
  VoidDenominatorNote,
  hasPickShape,
  type PickShape,
} from '@/components/PickShapeLine';

/**
 * Batch 70 — what kind of picks people are actually making.
 *
 * The load-bearing test here is the last one. `picks_played` counts void picks and the
 * odds figures do not, so the two figures on one row have different denominators — and a
 * screen that shows both without saying so is lying quietly.
 */

function shape(overrides: Partial<PickShape> = {}): PickShape {
  return {
    picks_played: 4,
    picks_priced: 4,
    cumulative_odds: 10.7,
    average_odds: 2.67,
    points_per_pick: 13.75,
    best_return: 40,
    longshot_picks: 2,
    favourite_picks: 2,
    longshot_odds: 3,
    ...overrides,
  };
}

describe('the pick-shape figures', () => {
  it('names the one figure it shows', () => {
    // Batch 73 — `avg` alone was ambiguous on a table whose other columns are points.
    render(<PickShapeLine shape={shape()} />);
    expect(screen.getByText(/avg odds selected 2\.67/)).toBeTruthy();
  });

  it('renders no longshot split', () => {
    // Dropped in Batch 73 on the owner's call: two figures at this size read as a ratio,
    // and the second was usually zero. The split survives on `PickShapeGrid`, below.
    const { container } = render(<PickShapeLine shape={shape({ longshot_picks: 2 })} />);
    expect(container.textContent).not.toMatch(/3\.00\+/);
    expect(container.textContent).not.toMatch(/ at /);
  });

  it('labels the grid split from the line it was computed with', () => {
    // The line travels with the figure, so the label cannot drift from the value the
    // split was made at — the same reason `odds_degraded` travels with the odds. Batch 73
    // moved this off `PickShapeLine`, which no longer shows a split, onto the surface
    // that still does rather than dropping the guarantee with the line.
    render(<PickShapeGrid shape={shape({ longshot_odds: 4 })} />);
    expect(screen.getByText(/Longshots \(4\.00\+\)/)).toBeTruthy();
  });

  it('shows every figure on the full grid', () => {
    render(<PickShapeGrid shape={shape()} />);
    expect(screen.getByText('10.70')).toBeTruthy();
    expect(screen.getByText('13.75')).toBeTruthy();
    expect(screen.getByText('40 pts')).toBeTruthy();
  });

  it('renders nothing at all when the API has not shipped the figures', () => {
    // Vercel deploys the web app on merge while the API waits for /ship-prod, so for
    // that window every one of these is absent. Absent must read as nothing, never as 0.
    const bare: PickShape = { picks_played: 4 };
    expect(hasPickShape(bare)).toBe(false);
    const { container } = render(<PickShapeGrid shape={bare} />);
    expect(container.textContent).toBe('');
  });

  it('renders nothing for a member whose only picks were voided', () => {
    // No average over nothing. A zero here would read as "they take even-money picks".
    expect(hasPickShape(shape({ picks_priced: 0, average_odds: null }))).toBe(false);
  });
});

describe('the note about the two denominators', () => {
  it('says so when a void pick makes the denominators differ', () => {
    render(<VoidDenominatorNote shape={shape({ picks_played: 5, picks_priced: 4 })} />);
    const note = screen.getByText(/4 picks that ran/);
    expect(note.textContent).toContain('1 void pick counts as played');
  });

  it('pluralises the void half honestly', () => {
    render(<VoidDenominatorNote shape={shape({ picks_played: 6, picks_priced: 4 })} />);
    expect(screen.getByText(/2 void picks count as played/)).toBeTruthy();
  });

  it('says nothing when the two denominators are the same', () => {
    // The note is only true when there is a difference; printing it always would train
    // readers to ignore it by the time it matters.
    const { container } = render(<VoidDenominatorNote shape={shape()} />);
    expect(container.textContent).toBe('');
  });
});
