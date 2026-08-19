import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import { LeagueProvider } from '@/contexts/LeagueContext';
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

const SATURDAY_3PM = {
  start_weekday: 5,
  start_minute: 900,
  end_weekday: 5,
  end_minute: 900,
  lock_offset_minutes: 30,
  pick_open_offset_minutes: null,
};

function leagueDetail(
  overrides: Record<string, unknown> = {},
  window: Record<string, unknown> = {},
) {
  return {
    id: 'l1',
    slug: 'the-coupon',
    name: 'The Coupon',
    description: null,
    privacy: 'public_open',
    max_members: 15,
    pick_scope: 'selection',
    slate_window: { ...SATURDAY_3PM, ...window },
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
function stubApi(catalogue?: Record<string, unknown>, window: Record<string, unknown> = {}) {
  const captured: { patch: Record<string, unknown> | null; post: Record<string, unknown> | null } = {
    patch: null,
    post: null,
  };
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    // Before the `/leagues/{slug}` matcher below, which this URL also satisfies.
    // `LeagueProvider` wraps the page since Batch 34 and needs a list, not a detail.
    if (url.includes('/leagues/mine')) {
      return json([{ slug: 'the-coupon', name: 'The Coupon' }]);
    }
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
        { gameweek_id: 'g1', starts_on: '2027-12-26', status: 'open', locks_at_utc: '2027-12-26T14:30:00', picks_open_at_utc: null, fixture_count: 3, created: true },
        201,
      );
    }
    if (method === 'PATCH') {
      captured.patch = JSON.parse(init.body as string) as Record<string, unknown>;
      return json(leagueDetail({}, window));
    }
    if (/\/api\/v1\/leagues\/[^/]+$/.test(url)) {
      return json(leagueDetail({}, window));
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
        <LeagueProvider>
          <Routes>
            <Route path="/leagues/:slug/admin/settings" element={<LeagueSettingsPage />} />
          </Routes>
        </LeagueProvider>
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

describe('LeagueSettingsPage — when picks open (Batch 27)', () => {
  /**
   * Wait for the form to be *populated* from the league query, not merely rendered.
   *
   * The page renders its skeleton until `league` arrives, so the pick-open switch
   * appearing only proves that query resolved — the effect copying `league.name` into
   * the name field runs after that commit. Clicking Save in between submits a form
   * whose `required` name input is still empty, and jsdom then refuses to dispatch
   * `submit` at all: no handler, no toast, no PATCH, and a `waitFor` that can only
   * time out. Raising the timeout does not help, because nothing is in flight.
   *
   * The league name landing in the input is the moment the whole effect has run.
   */
  const formReady = () => screen.findByDisplayValue('The Coupon');

  it('sends null while the league announces no opening, and hides the field', async () => {
    const api = stubApi();
    renderPage();
    await screen.findByRole('switch', { name: /announce when picks open/i });
    expect(screen.queryByLabelText(/picks open \(minutes/i)).toBeNull();
    await formReady();

    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(api.patch).not.toBeNull());
    // Explicitly null, not omitted: the API reads this field from the keys sent, so
    // omitting it would mean "unchanged" and the setting could never be turned off.
    expect(api.patch).toHaveProperty('pick_open_offset_minutes', null);
  });

  it('switching it on seeds a week and saves the offset', async () => {
    const api = stubApi();
    renderPage();
    const toggle = await screen.findByRole('switch', { name: /announce when picks open/i });
    fireEvent.click(toggle);

    const field = (await screen.findByLabelText(/picks open \(minutes/i)) as HTMLInputElement;
    expect(field.value).toBe(String(7 * 24 * 60));

    fireEvent.change(field, { target: { value: '2880' } }); // two days
    await formReady();
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(api.patch).not.toBeNull());
    expect(api.patch?.pick_open_offset_minutes).toBe(2880);
  });

  it('refuses a claim period that would close before it opened', async () => {
    // Both offsets count back from the same anchor, so a pick-open offset smaller than
    // the lock offset means picks open *after* they lock — a round nobody could play.
    const api = stubApi(undefined, { lock_offset_minutes: 120 });
    // `vi.mock` builds the sonner spies once per file and `restoreAllMocks` does not
    // clear call history, so without this the assertion below could be satisfied by an
    // error toast raised in an earlier test.
    vi.mocked(toast.error).mockClear();
    renderPage();
    const toggle = await screen.findByRole('switch', { name: /announce when picks open/i });
    fireEvent.click(toggle);

    const field = await screen.findByLabelText(/picks open \(minutes/i);
    fireEvent.change(field, { target: { value: '60' } });
    await formReady();
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    // The toast has to come from *this* click, so the guard is what is being proven —
    // not a form that silently refused to submit for an unrelated reason.
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(api.patch).toBeNull();
  });

  it('loads a stored offset with the switch already on', async () => {
    stubApi(undefined, { pick_open_offset_minutes: 4320 }); // three days
    renderPage();
    // The switch mounts default-off and turns on when the league detail lands, and two
    // of the assertions below do not retry — so waiting for the element is not enough.
    // `leagueDetail` carries the name and the offset in one response, so this is a
    // barrier for the very data under test rather than a proxy for it.
    await formReady();

    const toggle = await screen.findByRole('switch', { name: /announce when picks open/i });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    const field = (await screen.findByLabelText(/picks open \(minutes/i)) as HTMLInputElement;
    expect(field.value).toBe('4320');
    expect(screen.getByText(/3 days before Saturday 15:00/i)).toBeTruthy();
  });
});
