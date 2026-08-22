import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '@/contexts/AuthContext';
import { JoinPage } from '@/pages/JoinPage';

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    isInstalled: true,
    isMobile: true,
    isIos: false,
    isIosSafari: false,
    isAndroid: false,
    canInstall: false,
    prompt: vi.fn(),
  }),
  detectStandalone: () => true,
}));

function renderJoin(token: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/join/${token}`]}>
        <AuthProvider>
          <Routes>
            <Route path="/join/:token" element={<JoinPage />} />
            <Route path="/leagues/:slug" element={<p>Joined</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function storeSignedInPlayer() {
  localStorage.setItem('coupon_access', 'header.eyJleHAiOjk5OTk5OTk5OTl9.signature');
  localStorage.setItem('coupon_refresh', 'refresh-token');
  localStorage.setItem(
    'coupon_player',
    JSON.stringify({
      id: 'player-1',
      displayName: 'Alice',
      role: 'player',
      timezone: 'Europe/London',
    }),
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('JoinPage', () => {
  // Before public signup this offered sign-in alone and told the visitor their admin
  // would supply credentials — which, for the new member an invite is usually aimed at,
  // was an instruction they could not act on. Both doors now exist and both must keep
  // the return path, or claiming the invite is lost on the way through.
  it('offers an unauthenticated invite recipient both doors, preserving the return path', () => {
    renderJoin('ABC123');

    expect(screen.getByRole('link', { name: /create account/i })).toHaveAttribute(
      'href',
      '/register?next=%2Fjoin%2FABC123',
    );
    expect(screen.getByRole('link', { name: /already have an account/i })).toHaveAttribute(
      'href',
      '/login?next=%2Fjoin%2FABC123',
    );
  });

  it('claims a six-character join code for the signed-in player', async () => {
    storeSignedInPlayer();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ league_slug: 'the-coupon' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('abc123');
    fireEvent.click(screen.getByRole('button', { name: /join league/i }));

    expect(await screen.findByText('Joined')).toBeTruthy();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/leagues/join-by-code'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ code: 'ABC123' }),
        }),
      );
    });
  });

  it('uses the invite-claim endpoint for a long invite token', async () => {
    storeSignedInPlayer();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ league_slug: 'the-coupon' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('signed-invite-token');
    fireEvent.click(screen.getByRole('button', { name: /join league/i }));

    expect(await screen.findByText('Joined')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/leagues/claim-invite'),
      expect.objectContaining({
        body: JSON.stringify({ token: 'signed-invite-token' }),
      }),
    );
  });
});
