import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LoginPage } from '@/pages/LoginPage';
import { AuthProvider } from '@/contexts/AuthContext';

function renderLoginAt(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderLogin() {
  return renderLoginAt('/login');
}

/** Login plus the screen it redirects a cleared credential to (Batch 66). */
function renderLoginWithSetPinRoute(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/set-pin" element={<div>choose a new pin</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Reports the router's current location. LoginPage's tests navigate for real rather than
 * through a `useNavigate` spy, so this asserts where a member *lands* — which is the
 * question OPS-08 asks — instead of which string was handed to the router.
 */
function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="landed-on">{`${location.pathname}${location.search}${location.hash}`}</div>
  );
}

function renderLoginWithLocationProbe(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <LoginPage />
          <LocationProbe />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubSuccessfulLogin() {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({
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
    }),
  );
}

function signIn() {
  fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: 'Alice' } });
  fillPin('1234');
  fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
}

function fillPin(digits: string) {
  for (let i = 0; i < digits.length; i++) {
    fireEvent.change(screen.getByLabelText(`PIN digit ${i + 1}`), {
      target: { value: digits[i] },
    });
  }
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('LoginPage', () => {
  it('shows a display-name input field', () => {
    renderLogin();
    expect(screen.getByLabelText(/display name/i)).toBeTruthy();
  });

  it('shows a PIN input', () => {
    renderLogin();
    expect(screen.getByLabelText(/pin digit 1/i)).toBeTruthy();
  });

  // Inverted on 2026-08-22. This asserted the absence of a create-account link, which
  // encoded the old operator-provisioned model: sharing the app's URL sent a stranger to
  // a form they could never satisfy. Public signup is now the owner's decision.
  it('offers public account creation', () => {
    renderLogin();
    expect(screen.getByRole('link', { name: /create account/i })).toBeTruthy();
  });

  it('carries ?next through to register, so an invite survives the detour', () => {
    renderLoginAt('/login?next=%2Fjoin%2FABC123');
    const link = screen.getByRole('link', { name: /create account/i });
    expect(link.getAttribute('href')).toBe('/register?next=%2Fjoin%2FABC123');
  });

  it('shows the value-proposition tagline', () => {
    renderLogin();
    expect(screen.getByText(/one pick\. one coupon\. every saturday/i)).toBeTruthy();
  });

  it('shows generic error even on locked account response (lockout removed)', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        json: () =>
          Promise.resolve({ detail: 'Account temporarily locked — try again later' }),
      }),
    );

    renderLogin();
    const displayNameInput = screen.getByLabelText(/display name/i);
    fireEvent.change(displayNameInput, { target: { value: 'Alice' } });
    fireEvent.change(screen.getByLabelText('PIN digit 1'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy();
    });
    expect(screen.getByRole('alert').textContent).toMatch(/invalid display name or pin/i);
  });

  it('shows generic error on invalid credentials', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        json: () => Promise.resolve({ detail: 'INVALID_CREDENTIALS' }),
      }),
    );

    renderLogin();
    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: 'Alice' } });
    fireEvent.change(screen.getByLabelText('PIN digit 1'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/invalid display name or pin/i);
    });
  });

  it('clears API caches on successful login before the new identity is used', async () => {
    const cachesDelete = vi.fn().mockResolvedValue(true);
    vi.stubGlobal('caches', { delete: cachesDelete });
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
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
      }),
    );

    renderLogin();
    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: 'Alice' } });
    fillPin('1234');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(cachesDelete).toHaveBeenCalledWith('api-coupon');
    });
    expect(localStorage.getItem('coupon_player')).toContain('Alice');
  });

  // Batch 66. An admin cleared this member's PIN at their own request. Telling them
  // their credentials are invalid would send them back round the forgot-PIN loop that
  // got them here — the loop that, until this batch, ended in silence.
  it('sends a member whose PIN was cleared to choose a new one', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ detail: 'PIN_NOT_SET' }),
      }),
    );

    renderLoginWithSetPinRoute('/login');
    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: 'Lewis' } });
    fillPin('1234');
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('choose a new pin')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('arrives with the display name filled when set-pin hands it back', () => {
    renderLoginAt('/login?name=Lewis');
    expect((screen.getByLabelText(/display name/i) as HTMLInputElement).value).toBe('Lewis');
  });

  describe('where it sends the member after sign-in', () => {
    it('returns to the invite that sent them', async () => {
      stubSuccessfulLogin();
      renderLoginWithLocationProbe('/login?next=%2Fjoin%2FABC123');
      signIn();
      await waitFor(() =>
        expect(screen.getByTestId('landed-on').textContent).toBe('/join/ABC123'),
      );
    });

    it('falls back to the dashboard when nothing asked for a destination', async () => {
      stubSuccessfulLogin();
      renderLoginWithLocationProbe('/login');
      signIn();
      await waitFor(() => expect(screen.getByTestId('landed-on').textContent).toBe('/'));
    });

    // OPS-08 / GHSA-wrjc-x8rr-h8h6 (Batch 88). `next` is read straight off a URL anyone
    // can send, and this page is public. The last two start with a single `/` and so
    // passed the `!startsWith('//')` guard that used to live here — browsers read `\` as
    // `/` inside a special scheme, so `/\evil.example` resolves to `https://evil.example/`.
    // Landing there with tokens freshly in localStorage is the whole risk.
    it.each([
      '//evil.example',
      'https://evil.example',
      'javascript:alert(1)',
      '/\\evil.example',
      '/\\/evil.example',
    ])('refuses to leave the app for %s', async (hostile) => {
      stubSuccessfulLogin();
      renderLoginWithLocationProbe(`/login?next=${encodeURIComponent(hostile)}`);
      signIn();
      await waitFor(() => expect(screen.getByTestId('landed-on').textContent).toBe('/'));
    });
  });
});