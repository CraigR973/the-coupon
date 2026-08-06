import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LeagueSettingsPage } from '@/pages/LeagueSettingsPage';

// sonner needs a <Toaster/> to render; the page only calls toast.*, so stub it out.
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({ id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' });

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function leagueDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 'l1',
    slug: 'the-coupon',
    name: 'The Coupon',
    description: null,
    privacy: 'public_open',
    max_members: 15,
    pick_scope: 'selection',
    slate_window: { start_weekday: 5, start_minute: 900, end_weekday: 5, end_minute: 900, lock_offset_minutes: 30 },
    competitions: null,
    offered_markets: ['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE'],
    member_count: 1,
    created_by: 'p1',
    created_at: '2026-01-01T00:00:00Z',
    join_code: null,
    members: [],
    ...overrides,
  };
}

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) });
}

/** Route all the settings-page endpoints; capture the PATCH and ad-hoc POST bodies. */
function stubApi(catalogue?: Record<string, unknown>) {
  const captured: { patch: Record<string, unknown> | null; post: Record<string, unknown> | null } = {
    patch: null,
    post: null,
  };
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    if (url.includes('/competitions')) {
      return json(
        catalogue ?? {
          all_uk: true,
          available: [
            { slug: 'epl', name: 'English Premier League' },
            { slug: 'sl2', name: 'Scottish League Two' },
          ],
          selected: [],
        },
      );
    }
    if (url.endsWith('/gameweeks') && method === 'POST') {
      captured.post = JSON.parse(init.body as string) as Record<string, unknown>;
      return json(
        { gameweek_id: 'g1', starts_on: '2027-12-26', status: 'open', locks_at_utc: '2027-12-26T14:30:00', fixture_count: 3, created: true },
        201,
      );
    }
    if (method === 'PATCH') {
      captured.patch = JSON.parse(init.body as string) as Record<string, unknown>;
      return json(leagueDetail());
    }
    if (/\/api\/v1\/leagues\/[^/]+$/.test(url)) {
      return json(leagueDetail());
    }
    return json({});
  });
  return captured;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/leagues/the-coupon/admin/settings']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/leagues/:slug/admin/settings" element={<LeagueSettingsPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('LeagueSettingsPage — admin configuration (Batch 15)', () => {
  it('saves the offered-market set, dropping an unticked market', async () => {
    const api = stubApi();
    renderPage();
    // Both markets load ticked.
    const btts = await screen.findByLabelText(/both teams to score/i);
    expect((btts as HTMLInputElement).checked).toBe(true);

    fireEvent.click(btts); // untick BTTS
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).not.toBeNull());
    expect(api.patch?.offered_markets).toEqual(['MATCH_ODDS']);
    // All-UK by default → competitions saved as null.
    expect(api.patch?.competitions).toBeNull();
    // The window is round-tripped.
    expect(api.patch?.slate_start_weekday).toBe(5);
    expect(api.patch?.lock_offset_minutes).toBe(30);
  });

  it('saves an explicit competition selection when All UK is switched off', async () => {
    const api = stubApi();
    renderPage();
    const allUk = await screen.findByRole('switch', { name: /all uk leagues/i });
    fireEvent.click(allUk); // turn the group off → the checklist appears

    const epl = await screen.findByLabelText(/english premier league/i);
    fireEvent.click(epl); // select the EPL
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).not.toBeNull());
    expect(api.patch?.competitions).toEqual([{ slug: 'epl', name: 'English Premier League' }]);
  });

  it('widens the window and saves the new range', async () => {
    const api = stubApi();
    renderPage();
    const openDay = await screen.findByLabelText(/opens — day/i);
    fireEvent.change(openDay, { target: { value: '4' } }); // Friday
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).not.toBeNull());
    expect(api.patch?.slate_start_weekday).toBe(4);
  });

  it('keeps a stored selection the provider no longer lists ticked and saveable', async () => {
    // Batch 21: `available` is the provider's catalogue, so a competition it has dropped
    // survives only by being unioned back in from `selected`.
    const api = stubApi({
      all_uk: false,
      available: [{ slug: 'epl', name: 'English Premier League' }],
      selected: [{ slug: 'retired', name: 'Retired Cup' }],
    });
    renderPage();

    const retired = await screen.findByLabelText(/retired cup/i);
    expect((retired as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).not.toBeNull());
    expect(api.patch?.competitions).toEqual([{ slug: 'retired', name: 'Retired Cup' }]);
  });

  it('creates an ad-hoc round for a chosen date', async () => {
    const api = stubApi();
    renderPage();
    const dateInput = await screen.findByLabelText(/round date/i);
    fireEvent.change(dateInput, { target: { value: '2027-12-26' } });
    fireEvent.click(screen.getByRole('button', { name: /create round/i }));

    await waitFor(() => expect(api.post).not.toBeNull());
    expect(api.post?.starts_on).toBe('2027-12-26');
  });
});
