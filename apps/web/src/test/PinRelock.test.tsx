import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';

// Expired JWT (exp=1, i.e. 1970) so isAccessTokenExpiringSoon() = true and the PIN gate fires.
const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6MX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function makeStorage() {
  const values = new Map([
    ['coupon_player', STORED_PLAYER],
    ['coupon_access', FAKE_JWT],
    ['coupon_refresh', 'refresh-token'],
  ]);

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

function fillPin(digits: string) {
  for (let i = 0; i < digits.length; i++) {
    fireEvent.change(screen.getByLabelText(`PIN digit ${i + 1}`), {
      target: { value: digits[i] },
    });
  }
}

/**
 * A fetch that answers `/auth/refresh` and `/auth/login` separately.
 *
 * Batch 123 made the cold start try the stored refresh token before asking for a PIN,
 * so a mock that says "ok" to everything now never reaches the PIN screen at all. Each
 * test says explicitly what each of the two paths answers, which is the distinction the
 * batch is about.
 */
function routedFetch(answers: {
  refresh?: { ok: boolean; status?: number; body?: unknown };
  login?: { ok: boolean; status?: number; body?: unknown };
}) {
  return vi.fn((url: string) => {
    const which = String(url).includes('/auth/refresh') ? answers.refresh : answers.login;
    const reply = which ?? { ok: false, status: 401, body: {} };
    return Promise.resolve({
      ok: reply.ok,
      status: reply.status ?? (reply.ok ? 200 : 401),
      json: () => Promise.resolve(reply.body ?? {}),
    });
  });
}

const TOKEN_PAIR = {
  access_token: 'new-access',
  refresh_token: 'new-refresh',
  player: {
    id: 'p1',
    display_name: 'Alice',
    role: 'player',
    timezone: 'UTC',
    avatar_url: 'https://example.supabase.co/avatars/p1/face.jpg',
  },
};

function renderProtectedApp(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('caches', { delete: vi.fn().mockResolvedValue(true) });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<div>Authed content</div>} />
            </Route>
            <Route path="/login" element={<div>PIN login</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal('localStorage', makeStorage());
});

describe('PIN re-lock gate', () => {
  it('keeps authed content hidden until the stored account PIN succeeds', async () => {
    // The refresh token is dead — revoked, or thirty days old — which is the state in
    // which a PIN is genuinely the only way back in.
    const fetchMock = routedFetch({
      refresh: { ok: false, status: 401 },
      login: { ok: true, body: TOKEN_PAIR },
    });

    renderProtectedApp(fetchMock);

    await waitFor(() => expect(screen.getByText(/signed in as/i)).toBeInTheDocument());
    expect(screen.queryByText('Authed content')).not.toBeInTheDocument();
    expect(screen.getByText(/signed in as/i)).toHaveTextContent(/Alice/);
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument();

    fillPin('1234');
    fireEvent.click(screen.getByRole('button', { name: /unlock with pin/i }));

    await waitFor(() => {
      expect(screen.getByText('Authed content')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ display_name: 'Alice', pin: '1234' }),
      }),
    );
  });

  it('rejects a wrong PIN and keeps protected content hidden', async () => {
    const fetchMock = routedFetch({
      refresh: { ok: false, status: 401 },
      login: { ok: false, status: 401, body: { detail: 'Invalid credentials' } },
    });

    renderProtectedApp(fetchMock);

    await screen.findByRole('button', { name: /unlock with pin/i });
    fillPin('9999');
    fireEvent.click(screen.getByRole('button', { name: /unlock with pin/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/invalid pin/i);
      expect(screen.queryByText('Authed content')).not.toBeInTheDocument();
    });
  });
});

describe('Batch 123 — a griefing lock must not cost a member their session', () => {
  /**
   * Five wrong PINs lock an account for fifteen minutes, and the lock is account-wide:
   * the correct PIN from anywhere is refused. Display names are on every leaderboard,
   * so any member can hold a rival on this screen for as long as they keep spending
   * attempts — and on a Saturday that is the round.
   *
   * An expired *access* token only means a day has passed. The thirty-day refresh token
   * beside it is what says the session is still good, and nothing consulted it.
   */
  it('signs a member in from the stored refresh token, without asking for a PIN', async () => {
    const fetchMock = routedFetch({
      refresh: { ok: true, body: { access_token: 'fresh', refresh_token: 'rotated' } },
      // The PIN path is shut: whoever is griefing has the account locked.
      login: { ok: false, status: 423, body: { detail: 'Too many failed attempts. Try again later.' } },
    });

    renderProtectedApp(fetchMock);

    await waitFor(() => expect(screen.getByText('Authed content')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /unlock with pin/i })).not.toBeInTheDocument();
    // And it never touched the locked path.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('/auth/refresh');
  });

  it('falls back to the PIN screen when the refresh token is dead', async () => {
    const fetchMock = routedFetch({
      refresh: { ok: false, status: 401 },
      login: { ok: true, body: TOKEN_PAIR },
    });

    renderProtectedApp(fetchMock);

    await screen.findByRole('button', { name: /unlock with pin/i });
    expect(screen.queryByText('Authed content')).not.toBeInTheDocument();
  });

  it('says the account is locked rather than blaming the PIN', async () => {
    // "Invalid PIN" on a 423 sends a member to reset a credential that works.
    const fetchMock = routedFetch({
      refresh: { ok: false, status: 401 },
      login: { ok: false, status: 423, body: {} },
    });

    renderProtectedApp(fetchMock);

    await screen.findByRole('button', { name: /unlock with pin/i });
    fillPin('1234');
    fireEvent.click(screen.getByRole('button', { name: /unlock with pin/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/too many/i));
    expect(screen.getByRole('alert')).not.toHaveTextContent(/invalid pin/i);
  });

  it('does not show the PIN screen while the refresh is still in flight', async () => {
    // A flash of "enter your PIN" for a member who is about to be let in without one is
    // the defect in miniature.
    let settle: (value: unknown) => void = () => undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          settle = resolve;
        }),
    );

    renderProtectedApp(fetchMock as unknown as ReturnType<typeof vi.fn>);

    expect(screen.getByTestId('session-resuming')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /unlock with pin/i })).not.toBeInTheDocument();

    settle({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: 'fresh', refresh_token: 'rotated' }),
    });
    await waitFor(() => expect(screen.getByText('Authed content')).toBeInTheDocument());
  });
});
