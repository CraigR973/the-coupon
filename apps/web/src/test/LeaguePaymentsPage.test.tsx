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

describe('LeaguePaymentsPage — Monzo link health (Batch 210)', () => {
  const CONNECTED = {
    status: 'connected',
    last_success_at: '2026-10-16T21:32:44Z',
    last_error: null,
    last_error_at: null,
    token_expires_at: '2026-10-18T03:28:59Z',
    counting_since: '2026-10-16T21:29:00Z',
    webhook_registered: true,
  };

  function withLink(
    link: PaymentsOverview['monzo_link'],
    linkId: string | null = 'unipaylink_0000Abc123',
  ): PaymentsOverview {
    return { ...OVERVIEW, monzo_link: link, monzo_link_id: linkId };
  }

  it('shows a connected link with its last read, login renewal and counting start', async () => {
    stub(withLink(CONNECTED));
    renderPage();
    expect((await screen.findByTestId('monzo-status')).textContent).toBe('Connected');
    expect(screen.getByTestId('monzo-last-read').textContent).toBe(
      'Last read Fri 16 Oct, 21:32 · login renews before Sun 18 Oct, 03:28',
    );
    expect(screen.getByTestId('monzo-counting-since').textContent).toMatch(
      /payments count from fri 16 oct, 21:29/i,
    );
    expect(screen.queryByTestId('monzo-problem')).toBeNull();
    expect(screen.queryByTestId('monzo-no-link-id')).toBeNull();
  });

  it('says it is waiting for the Monzo app while approval is pending', async () => {
    stub(withLink({ ...CONNECTED, status: 'awaiting_approval', last_success_at: null }));
    renderPage();
    expect((await screen.findByTestId('monzo-status')).textContent).toBe(
      'Waiting for approval in the Monzo app',
    );
    expect(screen.queryByTestId('monzo-last-read')).toBeNull();
  });

  it('asks for a reconnect, and says why, once Monzo refuses the saved login', async () => {
    stub(
      withLink({
        ...CONNECTED,
        status: 'needs_reconnect',
        last_error: 'refresh_refused',
        last_error_at: '2026-10-18T03:20:00Z',
      }),
    );
    renderPage();
    expect((await screen.findByTestId('monzo-status')).textContent).toBe('Needs connecting again');
    expect(screen.getByTestId('monzo-problem').textContent).toBe(
      'Sun 18 Oct, 03:20: Monzo refused the saved login, so the owner needs to connect again.',
    );
  });

  it('shows a problem only while nothing has worked since it', async () => {
    stub(
      withLink({
        ...CONNECTED,
        last_error: 'monzo_unavailable',
        last_error_at: '2026-10-16T21:00:00Z',
      }),
    );
    const { unmount } = renderPage();
    await screen.findByTestId('monzo-status');
    expect(screen.queryByTestId('monzo-problem')).toBeNull();
    unmount();

    stub(
      withLink({
        ...CONNECTED,
        last_error: 'monzo_unavailable',
        last_error_at: '2026-10-16T21:40:00Z',
      }),
    );
    renderPage();
    expect((await screen.findByTestId('monzo-problem')).textContent).toMatch(
      /monzo could not be reached/i,
    );
  });

  it('says the link is not connected before the owner first connects', async () => {
    stub(withLink(null));
    renderPage();
    expect((await screen.findByTestId('monzo-status')).textContent).toBe('Not connected');
    expect(screen.queryByTestId('monzo-counting-since')).toBeNull();
  });

  it('says nothing about Monzo when the API is older than Batch 208', async () => {
    stub(OVERVIEW);
    renderPage();
    await screen.findByTestId('payments-fee');
    expect(screen.queryByTestId('monzo-link')).toBeNull();
  });

  it('points to league settings while the league has no Monzo link id', async () => {
    stub(withLink(CONNECTED, null));
    renderPage();
    const hint = await screen.findByTestId('monzo-no-link-id');
    expect(hint.textContent).toMatch(/none of its payments are read yet/i);
    expect(within(hint).getByRole('link', { name: /league settings/i }).getAttribute('href')).toBe(
      '/leagues/2-1-hibs/admin/settings',
    );
  });

  // Batch 214: Monzo asks the owner to approve the app again every 90 days.
  it('says until when Monzo’s approval lasts', async () => {
    stub(withLink({ ...CONNECTED, approval_lapses_at: '2027-01-14T21:32:44Z' }));
    renderPage();
    const approval = await screen.findByTestId('monzo-approval');
    expect(approval.textContent).toMatch(/^Approved until Thu 14 Jan, 21:32\./);
    expect(approval.textContent).toMatch(/every 90 days/i);
    expect(screen.getByTestId('monzo-last-read').textContent).toBe(
      'Last read Fri 16 Oct, 21:32 · login renews before Sun 18 Oct, 03:28',
    );
  });

  it('says nothing about approval when the API does not send its date', async () => {
    stub(withLink(CONNECTED));
    renderPage();
    await screen.findByTestId('monzo-last-read');
    expect(screen.queryByTestId('monzo-approval')).toBeNull();
  });

  it('explains a refused read as an approval that lapsed or was withdrawn', async () => {
    stub(
      withLink({
        ...CONNECTED,
        last_error: 'forbidden',
        last_error_at: '2026-10-16T21:40:00Z',
      }),
    );
    renderPage();
    expect((await screen.findByTestId('monzo-problem')).textContent).toMatch(
      /approval lasts 90 days, or it was withdrawn in the Monzo app/i,
    );
  });
});
