import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MoneyCard } from '@/components/MoneyCard';
import { isLeagueMoney } from '@/lib/money';
import type { LeagueMoney, MemberMoneyStatus } from '@/lib/types';

/**
 * Batch 212 — the league's money on the standings page.
 *
 * Owner decisions of 2026-10-17: every member sees every member's status (a friends'
 * league, and the nudge is the point), and the target shows both to date and full season,
 * the full-season figure flagged as an estimate while the season's last round is unknown.
 */

function member(
  name: string,
  status: MemberMoneyStatus['status'],
  amount_pence = 0,
): MemberMoneyStatus {
  return { player_id: `p-${name}`, display_name: name, status, amount_pence };
}

const MONEY: LeagueMoney = {
  season: 2026,
  label: '2026/27',
  entry_fee_pence: 100,
  pot_pence: 500,
  target_to_date: { rounds: 2, per_person_pence: 200, total_pence: 900 },
  target_full_season: {
    rounds: 13,
    per_person_pence: 1300,
    total_pence: 5300,
    estimated_through: '2027-05-31',
    is_estimate: true,
  },
  short_of_target_pence: 400,
  // Deliberately out of order: the card sorts.
  members: [
    member('Saver', 'credit', 200),
    member('Steady', 'paid_up'),
    member('Skint', 'owes', 200),
    member('Alice', 'paid_up'),
    member('Behind', 'owes', 500),
  ],
};

describe('MoneyCard', () => {
  it('shows the prize fund, both targets per person and in total, and the shortfall', () => {
    render(<MoneyCard money={MONEY} />);
    expect(screen.getByTestId('money-pot').textContent).toBe('£5');
    const toDate = screen.getByTestId('money-target-to-date');
    expect(toDate.textContent).toMatch(/target to date · 2 rounds/i);
    expect(toDate.textContent).toContain('£2 each');
    expect(toDate.textContent).toContain('£9 total');
    const full = screen.getByTestId('money-target-full-season');
    expect(full.textContent).toMatch(/full season \(estimate\) · 13 rounds/i);
    expect(full.textContent).toContain('£13 each');
    expect(full.textContent).toContain('£53 total');
    expect(screen.getByTestId('money-estimate-note').textContent).toMatch(
      /one round a week to 31 May/,
    );
    expect(screen.getByTestId('money-shortfall').textContent).toMatch(/£4 short of the target/);
  });

  it('lists every member owes first, most owed first, then paid up, then in credit', () => {
    render(<MoneyCard money={MONEY} currentPlayerId="p-Skint" />);
    const rows = screen.getAllByTestId('money-member');
    expect(rows.map((row) => row.dataset.status)).toEqual([
      'owes',
      'owes',
      'paid_up',
      'paid_up',
      'credit',
    ]);
    expect(rows.map((row) => row.textContent)).toEqual([
      'BehindOwes £5',
      'Skint (you)Owes £2',
      'AlicePaid up',
      'SteadyPaid up',
      'SaverIn credit £2',
    ]);
  });

  it('drops the estimate once the season is known, and says when nothing is unpaid', () => {
    render(
      <MoneyCard
        money={{
          ...MONEY,
          target_full_season: { ...MONEY.target_full_season, estimated_through: null, is_estimate: false },
          short_of_target_pence: 0,
          members: [member('Alice', 'paid_up')],
        }}
      />,
    );
    const full = screen.getByTestId('money-target-full-season');
    expect(full.textContent).toMatch(/^full season · 13 rounds/i);
    expect(screen.queryByTestId('money-estimate-note')).toBeNull();
    expect(screen.getByTestId('money-shortfall').textContent).toMatch(/everything due so far is paid/i);
    expect(within(screen.getByTestId('money-members')).getByText('Paid up')).toBeTruthy();
  });

  it('recognises only the money read, not whatever else an older API answers', () => {
    expect(isLeagueMoney(MONEY)).toBe(true);
    expect(isLeagueMoney(null)).toBe(false);
    expect(isLeagueMoney({ slug: 'the-coupon', name: 'The Coupon', members: [] })).toBe(false);
    expect(isLeagueMoney({ ...MONEY, target_full_season: undefined })).toBe(false);
  });
});
