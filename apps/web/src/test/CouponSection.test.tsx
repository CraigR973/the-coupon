import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CouponSection } from '@/components/CouponSection';
import { entriesForRound } from '@/components/PickRow';
import { buildCouponShareText, buildSettledResultShareText } from '@/lib/share';
import type { RoundPhase } from '@/lib/coupon';
import type { Coupon, CouponLeg, GameweekMember } from '@/lib/types';

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

/** A member of the league who never claimed anything — the roster half of the merge. */
function absentee(player_id: string, display_name: string): GameweekMember {
  return {
    player_id,
    display_name,
    has_picked: false,
    fixture_id: null,
    home: null,
    away: null,
    competition: null,
    market: null,
    outcome: null,
    runner_name: null,
    odds: null,
  };
}

interface Options {
  phase?: RoundPhase;
  memberCount?: number;
  members?: GameweekMember[];
  myPlayerId?: string;
}

function renderSection(value: Coupon, options: Options = {}) {
  const members = options.members ?? [];
  return render(
    <CouponSection
      coupon={value}
      entries={entriesForRound(value, members, options.myPlayerId)}
      phase={options.phase ?? 'open'}
      memberCount={options.memberCount ?? value.leg_count}
      roundLabel="Gameweek 4"
      oddsFormat="decimal"
    />,
  );
}

describe('CouponSection', () => {
  it('renders an empty state when nobody has picked', () => {
    renderSection(coupon({ leg_count: 0, legs: [], combined_odds: 1 }), { memberCount: 0 });
    expect(screen.getByText(/no picks in yet/i)).toBeTruthy();
  });

  it('shows the fold count, combined odds and each leg', () => {
    renderSection(coupon());
    expect(screen.getByText(/2-fold accumulator/i)).toBeTruthy();
    expect(screen.getByText('3.50')).toBeTruthy(); // combined odds
    expect(screen.getByText(/frozen at pick time/i)).toBeTruthy();
    expect(screen.getAllByText('Forfar').length).toBeGreaterThan(0);
    expect(screen.getByText(/Scottish League 2/)).toBeTruthy();
    expect(screen.getByText('Both teams score')).toBeTruthy(); // leg B selection label
    expect(screen.getAllByTestId(/^acca-leg-/)).toHaveLength(2);
    expect(screen.getByRole('button', { name: /copy text/i })).toBeTruthy();
  });

  /**
   * Batch 105. The fold, the combined price and the frozen-price sentence were printed
   * on both coupon screens and inside the pasted text, so a member reading one round saw
   * the same three facts four times. There is one of each now, and this is the assertion
   * that keeps it that way on the surface itself.
   */
  it('states the frozen-price fact exactly once', () => {
    renderSection(coupon());
    expect(screen.getAllByText(/frozen/i)).toHaveLength(1);
  });

  it('builds plain text with frozen prices and no outbound bet link', () => {
    expect(buildCouponShareText(coupon(), { roundLabel: 'Gameweek 4', memberCount: 2 })).toBe(
      [
        'The Coupon — Gameweek 4',
        '2-fold accumulator @ 3.50',
        '',
        '1. Alice — Forfar (v Brechin) @ 2.00',
        '2. Bob — Both teams score (Celtic v Rangers) @ 1.75',
        '',
        'Odds were frozen when each member picked — check your book for current prices before placing anything.',
      ].join('\n'),
    );
  });

  it('copies the plain text coupon to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    renderSection(coupon());
    await userEvent.click(screen.getByRole('button', { name: /copy text/i }));

    expect(writeText).toHaveBeenCalledWith(
      buildCouponShareText(coupon(), { roundLabel: 'Gameweek 4', memberCount: 2 }),
    );
  });

  it('flags a fully-won settled coupon', () => {
    renderSection(
      coupon({
        status: 'settled',
        all_won: true,
        legs: [
          { ...LEG_A, status: 'won' },
          { ...LEG_B, status: 'won' },
        ],
      }),
      { phase: 'settled' },
    );
    expect(screen.getByText(/all legs won/i)).toBeTruthy();
    expect(screen.getAllByText('Won').length).toBeGreaterThan(0);
  });

  it('marks a settled coupon that did not fully land', () => {
    renderSection(
      coupon({
        status: 'settled',
        all_won: false,
        legs: [
          { ...LEG_A, status: 'won' },
          { ...LEG_B, status: 'lost' },
        ],
      }),
      { phase: 'settled' },
    );
    expect(screen.getByText(/not all legs landed/i)).toBeTruthy();
  });
});

/**
 * Batch 105 — a coupon the deadline caught is not a complete one.
 *
 * `leg_count` alone cannot tell a two-member league that took two picks from a
 * three-member league that took two, and reading "2-fold accumulator" next to three
 * member names is exactly the implication the owner review objected to.
 */
describe('a round that locked before everybody picked', () => {
  const locked = () => coupon({ status: 'locked' });
  const options: Options = {
    phase: 'locked_incomplete',
    memberCount: 3,
    members: [absentee('p3', 'Cara')],
  };

  it('says how many members it is short of, rather than presenting a whole coupon', () => {
    renderSection(locked(), options);
    expect(screen.getByText(/1 of 3 never picked/i)).toBeTruthy();
  });

  it('keeps the member who never picked in the list', () => {
    renderSection(locked(), options);
    expect(screen.getByText('Cara')).toBeTruthy();
    expect(screen.getByText('Yet to pick')).toBeTruthy();
    expect(screen.getAllByTestId(/^acca-leg-/)).toHaveLength(3);
  });

  it('says so in the pasted text too', () => {
    expect(buildCouponShareText(locked(), { roundLabel: 'Gameweek 4', memberCount: 3 })).toContain(
      '2-fold accumulator @ 3.50 — incomplete, 1 of 3 never picked',
    );
  });

  it('says nothing about absentees when the coupon is whole', () => {
    renderSection(coupon(), { phase: 'complete', memberCount: 2 });
    expect(screen.queryByText(/never picked/i)).toBeNull();
    expect(screen.getByText(/combined odds, frozen at pick time/i)).toBeTruthy();
  });
});

// Batch 67. Between one round ending and the next opening, this section is the *result*
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

  it('leads with the result rather than the fold', () => {
    renderSection(settledCoupon(), { phase: 'settled' });
    expect(screen.getByText('Result')).toBeTruthy();
    expect(screen.getByText(/1 of 2 landed/i)).toBeTruthy();
    expect(screen.queryByText(/2-fold accumulator/i)).toBeNull();
  });

  it('shows the scoreline for a leg whose match resolved', () => {
    renderSection(settledCoupon(), { phase: 'settled' });
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
  });

  it('builds settled-result text with the scoreline in the coupon format', () => {
    expect(
      buildSettledResultShareText(settledCoupon(), { roundLabel: 'Gameweek 4', memberCount: 2 }),
    ).toBe(
      [
        'The Coupon: Result — Gameweek 4 — 1 of 2 picks landed',
        '2-fold accumulator @ 3.50',
        '',
        '1. Alice — Forfar (v Brechin) @ 2.00 — Forfar 2–1 Brechin — Won, 20 pts',
        '2. Bob — Both teams score (Celtic v Rangers) @ 1.75 — Lost, 0 pts',
        '',
        'Odds were frozen when each member picked — check your book for current prices before placing anything.',
      ].join('\n'),
    );
  });

  it('copies a settled result rather than the pre-lock coupon text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    const result = settledCoupon();
    renderSection(result, { phase: 'settled' });
    await userEvent.click(screen.getByRole('button', { name: /copy result/i }));

    const context = { roundLabel: 'Gameweek 4', memberCount: 2 };
    expect(writeText).toHaveBeenCalledWith(buildSettledResultShareText(result, context));
    expect(writeText).not.toHaveBeenCalledWith(buildCouponShareText(result, context));
  });

  it('shows the outcome and no score for a leg that could not be resolved', () => {
    renderSection(settledCoupon(), { phase: 'settled' });
    // Bob's leg still reports that it lost…
    expect(screen.getAllByText(/lost/i).length).toBeGreaterThan(0);
    // …and prints no scoreline at all, rather than a nil-nil that would be a lie.
    expect(screen.queryByText(/Celtic \d+–\d+ Rangers/)).toBeNull();
  });

  it('shows what each leg scored', () => {
    renderSection(settledCoupon(), { phase: 'settled' });
    expect(screen.getByText('20 pts')).toBeTruthy();
    expect(screen.getByText('0 pts')).toBeTruthy();
  });

  it("marks the reader's own leg and nobody else's", () => {
    renderSection(settledCoupon(), { phase: 'settled', myPlayerId: 'p1' });
    expect(screen.getAllByText('You')).toHaveLength(1);
    expect(screen.getByTestId('acca-leg-0').className).toContain('border-primary');
    expect(screen.getByTestId('acca-leg-1').className).not.toContain('border-primary');
  });

  it('marks nothing when the reader is not in this league', () => {
    renderSection(settledCoupon(), { phase: 'settled' });
    expect(screen.queryByText('You')).toBeNull();
  });

  it('prints no scoreline on a round that has not settled', () => {
    // The API withholds them, but a client reading a cached settled response into an
    // open round must not print a final score against a pick still running.
    renderSection(coupon({ legs: [{ ...LEG_A, home_goals: 2, away_goals: 1 }], leg_count: 1 }));
    expect(screen.queryByText(/Forfar 2–1 Brechin/)).toBeNull();
  });

  it('reads the same when the deployed API predates the fields', () => {
    // Vercel ships the web app on merge while the API waits for /ship-prod, so for that
    // window every leg arrives without any of the three. It must degrade, not break.
    renderSection(
      coupon({ status: 'settled', all_won: false, legs: [{ ...LEG_A, status: 'won' }] }),
      { phase: 'settled', myPlayerId: 'p1' },
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
    renderSection(livePlaying(), { phase: 'complete' });
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
    expect(screen.getByText('Live')).toBeTruthy();
  });

  it('says in words that these are not results', () => {
    renderSection(livePlaying(), { phase: 'complete' });
    expect(screen.getByText(/not results/i)).toBeTruthy();
    expect(screen.getByText(/Points are awarded when the round settles/i)).toBeTruthy();
  });

  it('leaves every pick pending — a live score decides nothing', () => {
    renderSection(livePlaying(), { phase: 'complete' });
    // No won/lost badge on a round that has not settled: FotMob may say what the score
    // is, only settlement says what a pick did.
    expect(screen.queryByText(/^won$/i)).toBeNull();
    expect(screen.queryByText(/^lost$/i)).toBeNull();
  });

  it('does not mark a settled round live', () => {
    renderSection(
      coupon({
        status: 'settled',
        all_won: false,
        legs: [{ ...LEG_A, status: 'won', home_goals: 2, away_goals: 1 }],
        leg_count: 1,
      }),
      { phase: 'settled' },
    );
    expect(screen.getByText(/Forfar 2–1 Brechin/)).toBeTruthy();
    expect(screen.queryByText('Live')).toBeNull();
    expect(screen.queryByText(/not results/i)).toBeNull();
  });

  it('treats a score with no flag as final, the way the old API meant it', () => {
    // Vercel ships this app on merge while the API waits for /ship-prod, so for that
    // window `score_is_final` is simply absent — and absent has always meant final.
    renderSection(
      coupon({
        status: 'settled',
        all_won: false,
        legs: [{ ...LEG_A, status: 'won', home_goals: 2, away_goals: 1 }],
        leg_count: 1,
      }),
      { phase: 'settled' },
    );
    expect(screen.queryByText('Live')).toBeNull();
  });
});
