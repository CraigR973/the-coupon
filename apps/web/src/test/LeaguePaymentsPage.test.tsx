import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { LeaguePaymentsPage } from '@/pages/LeaguePaymentsPage';
import type { PaymentsOverview } from '@/lib/types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/**
 * Batch 206 (ADR 0009) — a league's payments, for the site admin who runs it.
 *
 * Everything on this screen writes a permanent ledger entry, so the assertions are about
 * what is sent: the right route, the right member, the amount in pence and — for the one
 * entry that can charge a member — the sign.
 */

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const ADMIN = JSON.stringify({ id: 'p1', displayName: 'Organiser', role: 'admin', timezone: 'UTC' });

const OVERVIEW: PaymentsOverview = {
  entry_fee_pence: 100,
  payment_link_url: 'https://monzo.me/organiser/pot',
  balances: [
    { player_id: 'p-ann', display_name: 'Ann', active: true, balance_pence: -200, owed_pence: 200, credit_pence: 0, adult_confirmed: true },
    { player_id: 'p-bob', display_name: 'Bob', active: true, balance_pence: 300, owed_pence: 0, credit_pence: 300, adult_confirmed: true },
    { player_id: 'p-cat', display_name: 'Cat', active: true, balance_pence: 0, owed_pence: 0, credit_pence: 0, adult_confirmed: false },
    { player_id: 'p-dan', display_name: 'Dan', active: false, balance_pence: -100, owed_pence: 100, credit_pence: 0, adult_confirmed: true },
  ],
  queued_payments: [
    { id: 'q1', amount_pence: 200, payer_name: 'A SMITH', occurred_at: '2026-10-10T09:30:00Z' },
  ],
  season_pot: { season: 2026, label: '2026/27', pot_pence: 1400 },
};

interface Sent {
  url: string;
  body: Record<string, unknown>;
}

let sent: Sent[] = [];

function stub(
  overview: PaymentsOverview = OVERVIEW,
  refusal: { status: number; detail: string } | null = null,
) {
  sent = [];
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return ADMIN;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    const address = String(url);
    const ok = (body: unknown, status = 200) =>
      Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
    if ((init.method ?? 'GET') === 'POST') {
      sent.push({ url: address, body: JSON.parse(init.body as string) as Record<string, unknown> });
      if (refusal) return ok({ detail: refusal.detail }, refusal.status);
      return ok({ id: 'entry' }, 201);
    }
    if (address.includes('/leagues/mine')) return ok([{ slug: '2-1-hibs', name: '2-1 Hibs' }]);
    if (address.endsWith('/payments')) return ok(overview);
    return ok({});
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/leagues/2-1-hibs/admin/payments']}>
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/admin/payments" element={<LeaguePaymentsPage />} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast.success).mockClear();
  stub();
});

describe('LeaguePaymentsPage — what it shows', () => {
  it('heads the screen with the fee and the season pot', async () => {
    renderPage();
    expect((await screen.findByTestId('payments-fee')).textContent).toBe('£1 a round');
    expect(screen.getByTestId('payments-pot').textContent).toBe('£14');
    expect(screen.getByText(/2026\/27 pot/i)).toBeTruthy();
  });

  it('lists each member as owing, in credit or paid up — and a former member as left', async () => {
    renderPage();
    expect((await screen.findByTestId('balance-p-ann')).textContent).toMatch(/owes £2/i);
    expect(screen.getByTestId('balance-p-bob').textContent).toMatch(/£3 credit/i);
    expect(screen.getByTestId('balance-p-cat').textContent).toMatch(/paid up/i);
    const dan = screen.getByTestId('balance-p-dan');
    expect(dan.textContent).toMatch(/left/i);
    expect(dan.textContent).toMatch(/owes £1/i);
  });

  it('lists the queued payments with the payer’s name, date and amount', async () => {
    renderPage();
    const row = await screen.findByTestId('queued-q1');
    expect(row.textContent).toContain('A SMITH');
    expect(row.textContent).toMatch(/sat 10 oct, 09:30/i);
    expect(row.textContent).toContain('£2');
  });

  it('says so when nothing is waiting to be matched', async () => {
    stub({ ...OVERVIEW, queued_payments: [] });
    renderPage();
    expect(await screen.findByTestId('queued-empty')).toBeTruthy();
    expect(screen.queryByTestId('queued-payments')).toBeNull();
  });

  it('says when no fee is set', async () => {
    stub({ ...OVERVIEW, entry_fee_pence: null });
    renderPage();
    expect((await screen.findByTestId('payments-fee')).textContent).toBe('No fee set');
  });
});

describe('LeaguePaymentsPage — the admin queue', () => {
  it('assigns a queued payment to the chosen member', async () => {
    renderPage();
    const row = await screen.findByTestId('queued-q1');
    const assign = within(row).getByRole('button', { name: /assign/i });
    // Nothing is sent until somebody is chosen.
    expect((assign as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(within(row).getByLabelText(/whose payment/i), { target: { value: 'p-ann' } });
    await userEvent.click(assign);

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].url).toMatch(/\/api\/v1\/leagues\/2-1-hibs\/payments\/q1\/assign$/);
    expect(sent[0].body).toEqual({ player_id: 'p-ann' });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('says plainly when the payment was assigned by somebody else first', async () => {
    stub(OVERVIEW, { status: 409, detail: 'PAYMENT_ALREADY_ASSIGNED' });
    renderPage();
    const row = await screen.findByTestId('queued-q1');
    fireEvent.change(within(row).getByLabelText(/whose payment/i), { target: { value: 'p-bob' } });
    await userEvent.click(within(row).getByRole('button', { name: /assign/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const options = vi.mocked(toast.error).mock.calls[0][1] as { description: string };
    expect(options.description).toMatch(/already been assigned/i);
  });
});

describe('LeaguePaymentsPage — recording an entry', () => {
  async function fill(kind: string, member: string, amount: string, note = '') {
    renderPage();
    fireEvent.change(await screen.findByLabelText(/what happened/i), { target: { value: kind } });
    fireEvent.change(screen.getByLabelText(/^member$/i), { target: { value: member } });
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: amount } });
    if (note) {
      fireEvent.change(screen.getByLabelText(/reason|note/i), { target: { value: note } });
    }
  }

  it('records cash in pence against the member', async () => {
    await fill('cash', 'p-cat', '2');
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].url).toMatch(/\/payments\/cash$/);
    expect(sent[0].body).toEqual({ player_id: 'p-cat', amount_pence: 200, note: null });
  });

  it('records a cash-out as the positive amount repaid', async () => {
    await fill('cash-out', 'p-bob', '3', 'Repaid in the pub');
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].url).toMatch(/\/payments\/cash-outs$/);
    expect(sent[0].body).toEqual({ player_id: 'p-bob', amount_pence: 300, note: 'Repaid in the pub' });
  });

  it('explains a cash-out larger than the member’s credit', async () => {
    stub(OVERVIEW, { status: 409, detail: 'CASH_OUT_EXCEEDS_CREDIT' });
    await fill('cash-out', 'p-ann', '5');
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const options = vi.mocked(toast.error).mock.calls[0][1] as { description: string };
    expect(options.description).toMatch(/more than the member holds/i);
  });

  it('records an adjustment that charges the member as a negative amount', async () => {
    await fill('adjustment', 'p-ann', '1.50', 'Opening balance');
    fireEvent.change(screen.getByLabelText(/direction/i), { target: { value: 'charge' } });
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].url).toMatch(/\/payments\/adjustments$/);
    expect(sent[0].body).toEqual({ player_id: 'p-ann', amount_pence: -150, note: 'Opening balance' });
  });

  it('refuses an adjustment without a reason, before any request', async () => {
    await fill('adjustment', 'p-ann', '1');
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(vi.mocked(toast.error).mock.calls[0][0]).toMatch(/say why/i);
    expect(sent).toHaveLength(0);
  });

  it('refuses an amount that is not pounds and pence', async () => {
    await fill('cash', 'p-ann', '1.234');
    await userEvent.click(screen.getByRole('button', { name: /^record$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(sent).toHaveLength(0);
  });
});
