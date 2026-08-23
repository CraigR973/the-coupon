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

// Batch 67. Between one round ending and the next opening, this screen is the *result*
// rather than the coupon: a won/lost badge says what happened to the pick, not what the
// game finished. The join that reaches the score fails open, so "no score" is a state the
// view has to render properly rather than an error case.
describe('a settled round', () => {
  const settledCoupon = () =>
    coupon({
      status: 'settled',
      all_won: false,
      legs: [
        { ...LEG_A, status: 'won', points_awarded: 20, home_goals: 2, away_goals: 1 },
        { ...LEG_B, status: 'lost', points_awarded: 0, home_goals: null, away_goals: null },
      ],
    });

  it('shows the scoreline for a leg whose match resolved', () => {
    render(<CombinedAccaView coupon={settledCoupon()} />);
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
  });

  it('shows the outcome and no score for a leg that could not be resolved', () => {
    render(<CombinedAccaView coupon={settledCoupon()} />);
    // Bob's leg still reports that it lost…
    expect(screen.getAllByText(/lost/i).length).toBeGreaterThan(0);
    // …and prints no scoreline at all, rather than a nil-nil that would be a lie.
    expect(screen.queryByText(/Celtic \d+–\d+ Rangers/)).toBeNull();
  });

  it('shows what each leg scored', () => {
    render(<CombinedAccaView coupon={settledCoupon()} />);
    expect(screen.getByText('20 pts')).toBeTruthy();
    expect(screen.getByText('0 pts')).toBeTruthy();
  });

  it("marks the reader's own leg and nobody else's", () => {
    render(<CombinedAccaView coupon={settledCoupon()} myPlayerId="p1" />);
    expect(screen.getAllByText('You')).toHaveLength(1);
    expect(screen.getByTestId('acca-leg-0').className).toContain('border-primary');
    expect(screen.getByTestId('acca-leg-1').className).not.toContain('border-primary');
  });

  it('marks nothing when the reader is not in this league', () => {
    render(<CombinedAccaView coupon={settledCoupon()} />);
    expect(screen.queryByText('You')).toBeNull();
  });

  it('prints no scoreline on a round that has not settled', () => {
    // The API withholds them, but a client reading a cached settled response into an
    // open round must not print a final score against a pick still running.
    render(
      <CombinedAccaView
        coupon={coupon({ legs: [{ ...LEG_A, home_goals: 2, away_goals: 1 }] })}
      />,
    );
    expect(screen.queryByText(/Forfar 2–1 Brechin/)).toBeNull();
  });

  it('reads the same when the deployed API predates the fields', () => {
    // Vercel ships the web app on merge while the API waits for /ship-prod, so for that
    // window every leg arrives without any of the three. It must degrade, not break.
    render(
      <CombinedAccaView
        coupon={coupon({ status: 'settled', all_won: false, legs: [{ ...LEG_A, status: 'won' }] })}
        myPlayerId="p1"
      />,
    );
    expect(screen.getAllByText(/won/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/pts$/)).toBeNull();
  });
});

// Batch 72 — live scores while the round is being played.
//
// The load-bearing distinction: a running score and a result are opposite news to
// somebody holding that pick, and the view must never let the first read as the second.
describe('a round being played', () => {
  const livePlaying = () =>
    coupon({
      status: 'locked',
      all_won: null,
      legs: [
        { ...LEG_A, status: 'pending', home_goals: 2, away_goals: 1, score_is_final: false },
        { ...LEG_B, status: 'pending' },
      ],
    });

  it('shows the score so far and marks it live', () => {
    render(<CombinedAccaView coupon={livePlaying()} />);
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
    expect(screen.getByText('Live')).toBeTruthy();
  });

  it('says in words that these are not results', () => {
    render(<CombinedAccaView coupon={livePlaying()} />);
    expect(screen.getByText(/not results/i)).toBeTruthy();
    expect(screen.getByText(/Points are awarded when the round settles/i)).toBeTruthy();
  });

  it('leaves every pick pending — a live score decides nothing', () => {
    render(<CombinedAccaView coupon={livePlaying()} />);
    // No won/lost badge on a round that has not settled: FotMob may say what the score
    // is, only settlement says what a pick did.
    expect(screen.queryByText(/^won$/i)).toBeNull();
    expect(screen.queryByText(/^lost$/i)).toBeNull();
  });

  it('does not mark a settled round live', () => {
    render(
      <CombinedAccaView
        coupon={coupon({
          status: 'settled',
          all_won: false,
          legs: [{ ...LEG_A, status: 'won', home_goals: 2, away_goals: 1 }],
        })}
      />,
    );
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
    expect(screen.queryByText('Live')).toBeNull();
    expect(screen.queryByText(/not results/i)).toBeNull();
  });

  it('treats a score with no flag as final, the way the old API meant it', () => {
    // Vercel ships this app on merge while the API waits for /ship-prod, so for that
    // window `score_is_final` is simply absent — and absent has always meant final.
    render(
      <CombinedAccaView
        coupon={coupon({
          status: 'settled',
          all_won: false,
          legs: [{ ...LEG_A, status: 'won', home_goals: 2, away_goals: 1 }],
        })}
      />,
    );
    expect(screen.queryByText('Live')).toBeNull();
  });
});

