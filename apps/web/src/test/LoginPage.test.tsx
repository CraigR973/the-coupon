import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LoginPage } from '@/pages/LoginPage';
import { AuthProvider } from '@/contexts/AuthContext';

function renderLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
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

  it('does not offer public account creation', () => {
    renderLogin();
    expect(screen.queryByRole('link', { name: /create account/i })).toBeNull();
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
});
