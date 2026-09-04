import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { SettingsPage } from '@/pages/SettingsPage';

// ── Mock browser-specific hooks ───────────────────────────────────────────────

vi.mock('@/hooks/usePushSubscription', () => ({
  usePushSubscription: () => ({
    permission: 'granted',
    isSubscribed: true,
    isLoading: false,
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
  }),
}));

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    canInstall: true,
    isInstalled: false,
    isIosSafari: false,
    prompt: vi.fn(),
  }),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const DEFAULT_PREFS: {
  global_mute: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  leagues: { league_id: string; league_name: string; muted: boolean }[];
} = {
  global_mute: false,
  quiet_hours_start: null,
  quiet_hours_end: null,
  leagues: [],
};

const MUTED_PREFS = { ...DEFAULT_PREFS, global_mute: true };

const PREFS_WITH_LEAGUES = {
  ...DEFAULT_PREFS,
  leagues: [{ league_id: 'league-1', league_name: 'Friday League', muted: false }],
};

function makeFetch(prefs = DEFAULT_PREFS, patchResult = DEFAULT_PREFS) {
  return vi.fn((url: string, opts?: RequestInit) => {
    // The default deployment stores no avatars, so the profile-picture card is absent —
    // answered here rather than falling through to the 401 catch-all, which would look
    // like an expired session to `apiFetch` and tear the page's auth down.
    if (url.includes('/api/v1/config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ avatar_uploads: false }) });
    }
    if (url.includes('/api/v1/notifications/preferences') && (!opts?.method || opts.method === 'GET')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(prefs) });
    }
    if (url.includes('/api/v1/notifications/preferences') && opts?.method === 'PATCH') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(patchResult) });
    }
    if (url.includes('/api/v1/push/test')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ sent: 1 }) });
    }
    if (url.includes('/api/v1/auth/me') && opts?.method === 'PATCH') {
      const patch = JSON.parse(String(opts.body ?? '{}'));
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'p1',
            display_name: 'Alice',
            role: 'player',
            timezone: 'UTC',
            odds_format: 'decimal',
            ...patch,
          }),
      });
    }
    // token refresh — return 401 to skip
    return Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) });
  });
}

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function makeStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
    clear: vi.fn(() => {
      values.clear();
    }),
  };
}

function renderPage(fetchMock?: ReturnType<typeof makeFetch>) {
  const storage = makeStorage({
    coupon_player: STORED_PLAYER,
    coupon_access: FAKE_JWT,
  });
  vi.stubGlobal('localStorage', storage);

  vi.stubGlobal('fetch', fetchMock ?? makeFetch());

  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, storage };
}

beforeEach(() => {
  vi.restoreAllMocks();
  // Stub browser push APIs so PushSection doesn't bail out with "not supported"
  Object.defineProperty(window, 'PushManager', { value: {}, writable: true, configurable: true });
  Object.defineProperty(navigator, 'serviceWorker', { value: {}, writable: true, configurable: true });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SettingsPage', () => {
  it('renders section headings', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Push Notifications')).toBeInTheDocument();
      expect(screen.getByText('Notification Preferences')).toBeInTheDocument();
      expect(screen.getByText('Install App')).toBeInTheDocument();
    });
  });

  it('shows test push button when subscribed', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('test-push-btn')).toBeInTheDocument();
    });
  });

  it('test push button calls POST /api/v1/push/test', async () => {
    const fetch = makeFetch();
    renderPage(fetch);
    await waitFor(() => screen.getByTestId('test-push-btn'));
    fireEvent.click(screen.getByTestId('test-push-btn'));
    await waitFor(() => {
      const testCall = (fetch.mock.calls as [string, RequestInit?][]).find(
        ([url]) => url.includes('/api/v1/push/test'),
      );
      expect(testCall).toBeDefined();
      expect(testCall![1]?.method).toBe('POST');
    });
  });

  it('toggling global mute sends PATCH request', async () => {
    const fetch = makeFetch();
    renderPage(fetch);
    await waitFor(() => screen.getByRole('switch', { name: /enable all notifications/i }));
    fireEvent.click(screen.getByRole('switch', { name: /enable all notifications/i }));
    await waitFor(() => {
      const patchCall = (fetch.mock.calls as [string, RequestInit?][]).find(
        ([url, opts]) => url.includes('/api/v1/notifications/preferences') && opts?.method === 'PATCH',
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1]!.body as string);
      expect(body).toEqual({ global_mute: true });
    });
  });

  it('does not render unsupported category toggles', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('switch', { name: /pick confirmation/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('switch', { name: /deadline warning/i })).not.toBeInTheDocument();
    });
  });

  it('shows a per-league toggle and sends league_mutes on change', async () => {
    const fetch = makeFetch(PREFS_WITH_LEAGUES);
    renderPage(fetch);
    await waitFor(() => screen.getByRole('switch', { name: 'Friday League' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Friday League' }));
    await waitFor(() => {
      const patchCall = (fetch.mock.calls as [string, RequestInit?][]).find(
        ([url, opts]) => url.includes('/api/v1/notifications/preferences') && opts?.method === 'PATCH',
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1]!.body as string);
      expect(body).toEqual({ league_mutes: { 'league-1': true } });
    });
  });

  it('global mute disables quiet-hour controls', async () => {
    renderPage(makeFetch(MUTED_PREFS));
    await waitFor(() => {
      expect(screen.getByLabelText(/from/i)).toBeDisabled();
      expect(screen.getByLabelText(/to/i)).toBeDisabled();
    });
  });

  it('shows install button when canInstall is true', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Install app')).toBeInTheDocument();
    });
  });

  it('does not render a passkey unlock setting', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('switch', { name: /unlock with face id/i })).not.toBeInTheDocument();
    });
  });

  it('defaults the odds format to decimal and shows both samples', async () => {
    renderPage();
    const group = await screen.findByRole('radiogroup', { name: /odds format/i });
    const [decimal, fractional] = within(group).getAllByRole('radio');
    expect(decimal.getAttribute('aria-checked')).toBe('true');
    expect(fractional.getAttribute('aria-checked')).toBe('false');
    // The samples are the same price in each notation.
    expect(decimal.textContent).toContain('2.50');
    expect(fractional.textContent).toContain('3/2');
  });

  it('PATCHes the odds format and reflects the new preference', async () => {
    const fetch = makeFetch();
    renderPage(fetch);
    const group = await screen.findByRole('radiogroup', { name: /odds format/i });
    fireEvent.click(within(group).getAllByRole('radio')[1]);

    await waitFor(() => {
      const patch = fetch.mock.calls.find(
        ([url, opts]) => String(url).includes('/api/v1/auth/me') && opts?.method === 'PATCH',
      );
      expect(patch).toBeTruthy();
      // Only the changed field is sent — timezone is left alone.
      expect(JSON.parse(String(patch![1]!.body))).toEqual({ odds_format: 'fractional' });
    });

    await waitFor(() => {
      const [decimal, fractional] = within(group).getAllByRole('radio');
      expect(fractional.getAttribute('aria-checked')).toBe('true');
      expect(decimal.getAttribute('aria-checked')).toBe('false');
    });
  });

  // ── Batch 108: the per-league switch is named for what it does ──────────────

  it('calls the per-league switch notifications, and says it silences all of them', async () => {
    renderPage(makeFetch(PREFS_WITH_LEAGUES));

    // It gates every league-scoped push — the round opening, other members' picks, the
    // all-picks completion and a returned pick, as well as the pre-lock reminder. Calling
    // it "reminders" named one of the five, so a member muting a league to stop being
    // nagged was also switching off the alert that their claim had been handed back.
    expect(await screen.findByText(/per-league notifications/i)).toBeTruthy();
    expect(
      screen.getByText(/silences all of its notifications, not just reminders/i),
    ).toBeTruthy();
    expect(screen.queryByText(/per-league reminders/i)).toBeNull();
  });
});

// ── Profile picture (Batch 44) ────────────────────────────────────────────────
//
// Whether uploads work is a property of the deployment, not the build: a bucket has to
// be provisioned and `AVATAR_STORAGE` set. `GET /api/v1/config` is how the client finds
// out, and the card is absent — not disabled — until it says yes. Batch 42 left this
// control built and unmounted precisely because a visible control that always fails is
// worse for a member than none.

function fetchWithConfig(avatarUploads: boolean | 'missing') {
  const base = makeFetch();
  return vi.fn((url: string, opts?: RequestInit) => {
    if (String(url).includes('/api/v1/config')) {
      if (avatarUploads === 'missing') {
        return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ avatar_uploads: avatarUploads }),
      });
    }
    if (String(url).includes('/api/v1/auth/me/avatar')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ avatar_url: 'https://cdn.test/p1/abc.webp' }),
      });
    }
    return base(url, opts);
  });
}

describe('SettingsPage — profile picture', () => {
  it('offers no upload control where the deployment cannot store one', async () => {
    renderPage(fetchWithConfig(false));
    await waitFor(() => expect(screen.getByText('Timezone')).toBeInTheDocument());
    expect(screen.queryByText('Profile picture')).toBeNull();
  });

  it('stays hidden when the API is too old to have a config route', async () => {
    // The web app deploys from `main` on merge while the API waits for /ship-prod, so
    // a 404 here is a normal state for a few days — and must read as "not available".
    renderPage(fetchWithConfig('missing'));
    await waitFor(() => expect(screen.getByText('Timezone')).toBeInTheDocument());
    expect(screen.queryByText('Profile picture')).toBeNull();
  });

  it('mounts the control once the API reports a backend', async () => {
    renderPage(fetchWithConfig(true));
    expect(await screen.findByText('Profile picture')).toBeInTheDocument();
    expect(screen.getByLabelText('Choose a profile picture')).toBeInTheDocument();
  });

  it('sends the file as the raw body and keeps the returned URL', async () => {
    const fetch = fetchWithConfig(true);
    renderPage(fetch);

    const input = (await screen.findByLabelText('Choose a profile picture')) as HTMLInputElement;
    const file = new File([new Uint8Array([1, 2, 3])], 'me.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      const upload = fetch.mock.calls.find(([url, opts]) =>
        String(url).includes('/api/v1/auth/me/avatar') && opts?.method === 'POST',
      );
      expect(upload).toBeTruthy();
      // The raw File, not a FormData envelope — the API types it off Content-Type.
      expect(upload![1]!.body).toBe(file);
      expect((upload![1]!.headers as Record<string, string>)['Content-Type']).toBe('image/png');
    });
  });
});
