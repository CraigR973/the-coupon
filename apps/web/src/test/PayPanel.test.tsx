import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PayPanel } from '@/components/PayPanel';
import { formatPence, parsePounds, penceToInput } from '@/lib/money';
import { keys } from '@/lib/queryKeys';
import type { RoundFeeStatus } from '@/lib/types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/**
 * Batch 206 (ADR 0009) — the pay panel on the round screen.
 *
 * £1 a week, owed whether a member picks or not, and a member must be fully paid up to
 * pick. So the panel has to answer three questions without a tap: how much, why that
 * much (a missed week rolls over), and how to pay — with the link held back until the
 * one-time 18+ confirmation.
 */

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => (k === 'coupon_access' ? FAKE_JWT : null),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

/** Week 3 missed, week 4 open: £2 to pick, both weeks listed. */
const OWED: RoundFeeStatus = {
  entry_fee_pence: 100,
  round_due_pence: 100,
  owed_pence: 200,
  owed_rounds: [
    { gameweek_id: 'gw3', starts_on: '2026-10-03', number: 3, season_week: null, amount_pence: 100 },
    { gameweek_id: 'gw4', starts_on: '2026-10-10', number: 4, season_week: null, amount_pence: 100 },
  ],
  credit_pence: 0,
  adult_confirmed: true,
  has_payment_link: true,
  payment_link_url: 'https://monzo.me/organiser/pot',
};

function renderPanel(fee: RoundFeeStatus, client = new QueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <PayPanel slug="2-1-hibs" gameweekId="gw4" fee={fee} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('PayPanel — a member who owes', () => {
  it('gives the amount owed now, with the rolled-over week listed beside this one', () => {
    renderPanel(OWED);
    const panel = screen.getByTestId('pay-panel');
    expect(panel.dataset.state).toBe('owed');
    expect(screen.getByTestId('pay-panel-owed').textContent).toBe('£2');
    // A £2 must never be a surprise: the week that rolled over is named.
    const rolled = screen.getAllByTestId('pay-panel-rolled-over');
    expect(rolled).toHaveLength(1);
    expect(rolled[0].textContent).toMatch(/gameweek 3/i);
    expect(rolled[0].textContent).toMatch(/rolled over/i);
    expect(rolled[0].textContent).toContain('£1');
    expect(within(screen.getByTestId('pay-panel-rounds')).getByText('This round')).toBeTruthy();
  });

  it('lists no rolled-over weeks when only this round is owed', () => {
    renderPanel({
      ...OWED,
      owed_pence: 100,
      owed_rounds: [OWED.owed_rounds[1]],
    });
    expect(screen.getByTestId('pay-panel-owed').textContent).toBe('£1');
    expect(screen.queryAllByTestId('pay-panel-rolled-over')).toHaveLength(0);
  });

  it('offers the league’s payment link as a button once the member is confirmed 18+', () => {
    renderPanel(OWED);
    const link = screen.getByRole('link', { name: /pay £2/i });
    expect(link.getAttribute('href')).toBe('https://monzo.me/organiser/pot');
    // It leaves the app, so it opens apart from it and carries nothing back.
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
  });

  it('asks for the one-time 18+ confirmation before any link is shown', () => {
    renderPanel({ ...OWED, adult_confirmed: false, payment_link_url: null });
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('button', { name: /i’m 18 or over/i })).toBeTruthy();
  });

  it('records the confirmation and re-reads the round, which is what brings the link', async () => {
    const posted: string[] = [];
    vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
      if ((init.method ?? 'GET') === 'POST') posted.push(String(url));
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ adult_confirmed_at: '2026-10-13T20:00:00Z' }),
      });
    });
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    renderPanel({ ...OWED, adult_confirmed: false, payment_link_url: null }, client);

    await userEvent.click(screen.getByRole('button', { name: /i’m 18 or over/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatch(/\/api\/v1\/leagues\/2-1-hibs\/adult-confirmation$/);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.gameweek.all('2-1-hibs') }),
    );
  });

  it('says to ask the organiser when the league has no payment link', () => {
    renderPanel({ ...OWED, has_payment_link: false, payment_link_url: null, adult_confirmed: false });
    expect(screen.getByTestId('pay-panel-no-link')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
    // Nothing to unlock, so the confirmation is not asked for either.
    expect(screen.queryByRole('button', { name: /18 or over/i })).toBeNull();
  });
});

describe('PayPanel — a member who is paid up', () => {
  it('shows the credit of a member who has paid ahead', () => {
    renderPanel({ ...OWED, owed_pence: 0, owed_rounds: [], credit_pence: 300 });
    const panel = screen.getByTestId('pay-panel');
    expect(panel.dataset.state).toBe('credit');
    expect(panel.textContent).toMatch(/£3 in credit/);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('says paid up, and offers no link, to a member who owes nothing', () => {
    renderPanel({ ...OWED, owed_pence: 0, owed_rounds: [], credit_pence: 0 });
    const panel = screen.getByTestId('pay-panel');
    expect(panel.dataset.state).toBe('paid');
    expect(panel.textContent).toMatch(/paid up/i);
    expect(screen.queryByRole('link')).toBeNull();
  });
});

describe('money formatting', () => {
  it.each([
    [100, '£1'],
    [200, '£2'],
    [150, '£1.50'],
    [5, '£0.05'],
    [123456, '£1,234.56'],
    [-250, '−£2.50'],
  ])('formats %i pence as %s', (pence, text) => {
    expect(formatPence(pence)).toBe(text);
  });

  it.each([
    ['1', 100],
    ['£1', 100],
    [' 2.5 ', 250],
    ['0.01', 1],
    ['12.34', 1234],
    ['', null],
    ['abc', null],
    ['1.234', null],
    ['-1', null],
  ])('reads %j as %j pence', (input, pence) => {
    expect(parsePounds(input)).toBe(pence);
  });

  it('reads a negative amount only where an adjustment allows it', () => {
    expect(parsePounds('-2.50', { allowNegative: true })).toBe(-250);
    expect(parsePounds('-£1', { allowNegative: true })).toBe(-100);
  });

  it('puts a stored fee back into its field as pounds', () => {
    expect(penceToInput(100)).toBe('1');
    expect(penceToInput(150)).toBe('1.50');
    expect(penceToInput(null)).toBe('');
  });
});
