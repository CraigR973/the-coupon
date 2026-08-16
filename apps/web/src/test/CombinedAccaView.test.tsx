import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { buildCouponShareText, CombinedAccaView } from '@/components/CombinedAccaView';
import type { Coupon, CouponLeg } from '@/lib/types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const LEG_A: CouponLeg = {
  player_id: 'p1',
  player_name: 'Alice',
  fixture_id: 'fx1',
  home: 'Forfar',
  away: 'Brechin',
  competition: 'Scottish League 2',
  market: 'MATCH_ODDS',
  outcome: 'HOME',
  runner_name: 'Forfar',
  odds: 2.0,
  status: 'pending',
};
const LEG_B: CouponLeg = {
  player_id: 'p2',
  player_name: 'Bob',
  fixture_id: 'fx2',
  home: 'Celtic',
  away: 'Rangers',
  competition: 'Scottish Premiership',
  market: 'BOTH_TEAMS_TO_SCORE',
  outcome: 'YES',
  runner_name: 'Yes',
  odds: 1.75,
  status: 'pending',
};

function coupon(overrides: Partial<Coupon> = {}): Coupon {
  return {
    gameweek_id: 'gw1',
    status: 'open',
    leg_count: 2,
    combined_odds: 3.5,
    legs: [LEG_A, LEG_B],
    all_won: null,
    ...overrides,
  };
}

describe('CombinedAccaView', () => {
  it('renders an empty state when nobody has picked', () => {
    render(<CombinedAccaView coupon={coupon({ leg_count: 0, legs: [], combined_odds: 1 })} />);
    expect(screen.getByText(/no picks in yet/i)).toBeTruthy();
  });

  it('shows the fold count, combined odds and each leg', () => {
    render(<CombinedAccaView coupon={coupon()} />);
    expect(screen.getByText(/2-fold accumulator/i)).toBeTruthy();
    expect(screen.getByText('3.50')).toBeTruthy(); // combined odds
    expect(screen.getByText(/frozen combined odds from pick time/i)).toBeTruthy();
    // "Forfar" is both leg A's selection label and part of its "Forfar v Brechin" subline.
    expect(screen.getAllByText('Forfar').length).toBeGreaterThan(0);
    expect(screen.getByText(/Scottish League 2/)).toBeTruthy();
    expect(screen.getByText('Both teams score')).toBeTruthy(); // leg B selection label
    expect(screen.getAllByTestId(/^acca-leg-/)).toHaveLength(2);
    expect(screen.getByRole('button', { name: /copy text/i })).toBeTruthy();
  });

  it('builds plain text with frozen prices and no outbound bet link', () => {
    expect(buildCouponShareText(coupon())).toBe(
      [
        'The Coupon: 2-fold accumulator',
        'Frozen combined odds: 3.50 (historical, from pick time)',
        '',
        '1. Forfar @ 2.00 - Forfar v Brechin (Scottish League 2, 1X2) - Alice',
        '2. Both teams score @ 1.75 - Celtic v Rangers (Scottish Premiership, BTTS) - Bob',
        '',
        'Prices were frozen when each member picked. Check your book for current odds before placing anything.',
      ].join('\n'),
    );
  });

  it('copies the plain text coupon to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(<CombinedAccaView coupon={coupon()} />);
    await userEvent.click(screen.getByRole('button', { name: /copy text/i }));

    expect(writeText).toHaveBeenCalledWith(buildCouponShareText(coupon()));
  });

  it('flags a fully-won settled coupon', () => {
    render(
      <CombinedAccaView
        coupon={coupon({ status: 'settled', all_won: true, legs: [{ ...LEG_A, status: 'won' }, { ...LEG_B, status: 'won' }] })}
      />,
    );
    expect(screen.getByText(/all legs won/i)).toBeTruthy();
    expect(screen.getAllByText('Won').length).toBeGreaterThan(0);
  });

  it('marks a settled coupon that did not fully land', () => {
    render(
      <CombinedAccaView
        coupon={coupon({ status: 'settled', all_won: false, legs: [{ ...LEG_A, status: 'won' }, { ...LEG_B, status: 'lost' }] })}
      />,
    );
    expect(screen.getByText(/not all legs landed/i)).toBeTruthy();
  });
});
