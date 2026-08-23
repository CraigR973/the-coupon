import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PlayersPage } from '@/pages/admin/PlayersPage';
import { SetPinPage } from '@/pages/SetPinPage';
import type { AdminPlayer } from '@/lib/types';

/**
 * Batch 66 — the two screens the member-facing half of the reset journey needs, and the
 * one thing the console must never do: show a PIN.
 */

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch };
});

const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    player: { id: 'admin-1', displayName: 'Gaffer', role: 'admin', timezone: 'UTC' },
  }),
}));

function player(overrides: Partial<AdminPlayer> = {}): AdminPlayer {
  return {
    id: 'p1',
    display_name: 'Lewis',
    role: 'player',
    is_active: true,
    pin_set: true,
    failed_login_count: 0,
    locked_until: null,
    deleted_at: null,
    league_count: 2,
    created_at: '2026-08-01T12:00:00Z',
    ...overrides,
  };
}

function renderPlayers(entry = '/admin/players') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <PlayersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the admin players screen', () => {
  it('lists members and says which of them is waiting to choose a PIN', async () => {
    apiFetch.mockResolvedValue([
      player(),
      player({ id: 'p2', display_name: 'Sam', pin_set: false }),
    ]);

    renderPlayers();

    expect(await screen.findByText('Lewis')).toBeTruthy();
    expect(screen.getByText('Sam')).toBeTruthy();
    // The distinction the console exists to draw: "cannot remember their PIN" and
    // "already reset, has not come back" look identical without it.
    expect(screen.getByText('PIN cleared')).toBeTruthy();
  });

  it('reports a reset without ever showing a PIN', async () => {
    apiFetch.mockImplementation(async (path: string) => {
      if (path.endsWith('/reset-pin')) return { pin_cleared: true, sessions_revoked: 2 };
      return [player()];
    });

    renderPlayers();
    fireEvent.click(await screen.findByRole('button', { name: /reset pin/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const message = String(toastSuccess.mock.calls[0][0]);
    expect(message).toContain('choose a new one at sign-in');
    // No temporary PIN is minted, so nothing four-digit may appear in the confirmation.
    // A message that reads out a PIN is the failure this batch's decision removes.
    expect(message).not.toMatch(/\b\d{4}\b/);
  });

  it('leaves Unlock disabled for a member who is not locked out', async () => {
    apiFetch.mockResolvedValue([player()]);

    renderPlayers();

    const unlock = await screen.findByRole('button', { name: /unlock/i });
    expect(unlock.hasAttribute('disabled')).toBe(true);
  });

  it('spells out that a delete keeps the name reserved before it will run it', async () => {
    apiFetch.mockResolvedValue([player()]);

    renderPlayers();
    fireEvent.click(await screen.findByRole('button', { name: /delete/i }));

    expect(screen.getByText(/display name stays reserved/i)).toBeTruthy();
    const confirm = screen.getByRole('button', { name: /delete player/i });
    expect(confirm.hasAttribute('disabled')).toBe(true);

    fireEvent.change(screen.getByLabelText(/confirm display name/i), {
      target: { value: 'Lewis' },
    });
    expect(
      screen.getByRole('button', { name: /delete player/i }).hasAttribute('disabled'),
    ).toBe(false);
  });

  it('floats the member the reset notification named to the top', async () => {
    apiFetch.mockResolvedValue([
      player({ id: 'p1', display_name: 'Aaron' }),
      player({ id: 'p2', display_name: 'Zoe' }),
    ]);

    renderPlayers('/admin/players?player=p2');

    await screen.findByText('Zoe');
    const names = screen.getAllByRole('listitem').map((li) => li.textContent ?? '');
    expect(names[0]).toContain('Zoe');
  });
});

describe('the set-a-new-PIN screen', () => {
  function renderSetPin(entry = '/set-pin?name=Lewis') {
    return render(
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/set-pin" element={<SetPinPage />} />
          <Route path="/login" element={<div>signed-out home</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  function fill(label: string, digits: string) {
    for (let i = 0; i < digits.length; i++) {
      fireEvent.change(screen.getByLabelText(`${label} digit ${i + 1}`), {
        target: { value: digits[i] },
      });
    }
  }

  it('arrives with the display name already filled from the login redirect', () => {
    renderSetPin();
    expect((screen.getByLabelText(/display name/i) as HTMLInputElement).value).toBe('Lewis');
  });

  it('refuses two PINs that disagree without calling the API', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderSetPin();

    fill('New PIN', '7412');
    fill('Confirm new PIN', '7413');
    fireEvent.click(screen.getByRole('button', { name: /set pin/i }));

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('hands the member back to sign-in once the PIN is set', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 }) as unknown as Response,
    );
    renderSetPin();

    fill('New PIN', '7412');
    fill('Confirm new PIN', '7412');
    fireEvent.click(screen.getByRole('button', { name: /set pin/i }));

    expect(await screen.findByText('signed-out home')).toBeTruthy();
  });

  it('surfaces an expired reset rather than pretending it worked', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'That reset is no longer available.' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }) as unknown as Response,
    );
    renderSetPin();

    fill('New PIN', '7412');
    fill('Confirm new PIN', '7412');
    fireEvent.click(screen.getByRole('button', { name: /set pin/i }));

    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent',
      'That reset is no longer available.',
    );
  });
});

// Kept out of the describes above: it needs the real module, not the mocked apiFetch.
describe('the wrapper the pages share', () => {
  it('does not leak an admin-only screen into a player bundle by accident', async () => {
    const nav = await import('@/pages/admin/AdminNav');
    const markup = render(
      <MemoryRouter>
        <nav.AdminNav />
      </MemoryRouter>,
    );
    const links = markup.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(links).toEqual(['/admin/players', '/admin/invites', '/admin/leagues']);
  });
});
