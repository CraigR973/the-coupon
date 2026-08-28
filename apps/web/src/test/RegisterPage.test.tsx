import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegisterPage } from '@/pages/RegisterPage';
import { AuthProvider } from '@/contexts/AuthContext';

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

function renderRegisterAt(entry = '/register') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The two PIN groups are told apart by their group label — see `PinInput`. */
function fillPinGroup(label: string, digits: string) {
  for (let i = 0; i < digits.length; i++) {
    fireEvent.change(screen.getByLabelText(`${label} digit ${i + 1}`), {
      target: { value: digits[i] },
    });
  }
}

function fillForm(name: string, pin: string, confirm: string = pin) {
  fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: name } });
  fillPinGroup('Choose a PIN', pin);
  fillPinGroup('Confirm PIN', confirm);
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: /create account/i }));
}

/** Typed so `mock.calls` destructures without a cast — vi.fn() alone infers `[]`. */
function makeFetchMock() {
  return vi.fn((_url: string, _init?: RequestInit) => okResponse());
}

function requestOf(fetchMock: ReturnType<typeof makeFetchMock>, call = 0) {
  const [url, init] = fetchMock.mock.calls[call];
  return { url, body: JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown> };
}

function okResponse() {
  return Promise.resolve({
    ok: true,
    json: () =>
      Promise.resolve({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        player: {
          id: 'p1',
          display_name: 'Alice',
          role: 'player',
          timezone: 'Europe/London',
          avatar_url: null,
        },
      }),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigate.mockClear();
  localStorage.clear();
});

describe('RegisterPage', () => {
  it('asks for a display name and two PINs', () => {
    renderRegisterAt();
    expect(screen.getByLabelText(/display name/i)).toBeTruthy();
    expect(screen.getByLabelText('Choose a PIN digit 1')).toBeTruthy();
    expect(screen.getByLabelText('Confirm PIN digit 1')).toBeTruthy();
  });

  it('says plainly that a forgotten PIN needs an admin', () => {
    renderRegisterAt();
    expect(screen.getByText(/there is no email\s+reset/i)).toBeTruthy();
  });

  it('refuses a mismatched confirmation without calling the API', async () => {
    const fetchMock = makeFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderRegisterAt();
    fillForm('Alice', '3719', '3718');
    submit();

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/pins do not match/i);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refuses a name that is too short without calling the API', async () => {
    const fetchMock = makeFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderRegisterAt();
    fillForm('A', '3719');
    submit();

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/2-32 characters/i);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refuses a name with characters the login form cannot reproduce', async () => {
    const fetchMock = makeFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderRegisterAt();
    fillForm('Alice 🎉', '3719');
    submit();

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/letters, numbers, spaces/i);
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('posts the collapsed name, so what is validated is what is stored', async () => {
    const fetchMock = makeFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderRegisterAt();
    fillForm('  Alice   Smith  ', '3719');
    submit();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const { url, body } = requestOf(fetchMock);
    expect(url).toMatch(/\/api\/v1\/auth\/register$/);
    expect(body.display_name).toBe('Alice Smith');
  });

  it('sends the browser timezone so the first coupon reads in local time', async () => {
    const fetchMock = makeFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderRegisterAt();
    fillForm('Alice', '3719');
    submit();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const { body } = requestOf(fetchMock);
    expect(typeof body.timezone).toBe('string');
    expect(String(body.timezone).length).toBeGreaterThan(0);
  });

  it('signs the new account in and clears the previous member’s cached responses', async () => {
    const cachesDelete = vi.fn().mockResolvedValue(true);
    vi.stubGlobal('caches', { delete: cachesDelete });
    vi.stubGlobal('fetch', makeFetchMock());

    renderRegisterAt();
    fillForm('Alice', '3719');
    submit();

    await waitFor(() => expect(cachesDelete).toHaveBeenCalledWith('api-coupon'));
    expect(localStorage.getItem('coupon_player')).toContain('Alice');
  });

  it('shows the API’s own message when a name is taken', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        json: () => Promise.resolve({ detail: 'That display name is taken — try another.' }),
      }),
    );

    renderRegisterAt();
    fillForm('Alice', '3719');
    submit();

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/display name is taken/i);
    });
  });

  it('shows the API’s own message when signups are closed', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        json: () =>
          Promise.resolve({ detail: 'Sign-ups are closed right now. Ask a league admin for an invite.' }),
      }),
    );

    renderRegisterAt();
    fillForm('Alice', '3719');
    submit();

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/sign-ups are closed/i);
    });
  });

  it('keeps ?next on the sign-in link, so an invite is not lost by picking the wrong door', () => {
    renderRegisterAt('/register?next=%2Fjoin%2FABC123');
    const link = screen.getByRole('link', { name: /already have an account/i });
    expect(link.getAttribute('href')).toBe('/login?next=%2Fjoin%2FABC123');
  });

  // The limiter's body uses `error`, not `detail` — the shape the generic handler
  // cannot read. Asserted here because 5/hour is reachable without malice.
  it('says a rate limit is a rate limit, not a bad detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 429,
          json: () => Promise.resolve({ error: 'Rate limit exceeded: 5 per 1 hour' }),
        }),
      ),
    );
    renderRegisterAt();
    fillForm('Alice', '4821');
    submit();
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/too many attempts/i);
    });
    expect(navigate).not.toHaveBeenCalled();
  });

  describe('where it sends the new account', () => {
    it('returns to the invite that sent them, rather than a dashboard with no leagues', async () => {
      vi.stubGlobal('fetch', makeFetchMock());
      renderRegisterAt('/register?next=%2Fjoin%2FABC123');
      fillForm('Alice', '4821');
      submit();
      await waitFor(() =>
        expect(navigate).toHaveBeenCalledWith('/join/ABC123', { replace: true }),
      );
    });

    it('falls back to the dashboard when nothing asked for a destination', async () => {
      vi.stubGlobal('fetch', makeFetchMock());
      renderRegisterAt();
      fillForm('Alice', '4821');
      submit();
      await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }));
    });

    // `next` is attacker-reachable: it is read straight off a URL anyone can send. A
    // protocol-relative `//host` is a *path* to the router and an absolute origin to the
    // browser, so without this guard a shared link could hand a member who has just
    // authenticated — tokens already in localStorage — to another host.
    //
    // The backslash forms are OPS-08 / GHSA-wrjc-x8rr-h8h6 (Batch 88). They start with a
    // single `/` and so passed the `!startsWith('//')` guard that used to sit here, but
    // browsers read `\` as `/` inside a special scheme, making `/\evil.example` resolve
    // to `https://evil.example/`. react-router has no fix for this on 6.x — the guard in
    // `lib/redirect.ts` is what closes it, by resolving through the URL parser instead of
    // trying to name the hostile shapes.
    it.each([
      '//evil.example',
      'https://evil.example',
      'javascript:alert(1)',
      '/\\evil.example',
      '/\\/evil.example',
    ])(
      'refuses to leave the app for %s',
      async (hostile) => {
        vi.stubGlobal('fetch', makeFetchMock());
        renderRegisterAt(`/register?next=${encodeURIComponent(hostile)}`);
        fillForm('Alice', '4821');
        submit();
        await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }));
      },
    );
  });
});
