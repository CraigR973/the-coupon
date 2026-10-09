import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '@/contexts/AuthContext';
import { JoinPage } from '@/pages/JoinPage';

const installState = vi.hoisted(() => ({ isInstalled: true }));

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    isInstalled: installState.isInstalled,
    isMobile: true,
    isIos: false,
    isIosSafari: false,
    isAndroid: false,
    canInstall: false,
    prompt: vi.fn(),
  }),
  detectStandalone: () => true,
}));

function renderJoin(token: string, queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})) {
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
  installState.isInstalled = true;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('JoinPage', () => {
  it('shows only the three public invite facts before sign-in', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        league_name: 'Saturday League',
        inviter_name: 'Craig',
        member_count: 2,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('opaque-invite-token');

    expect(await screen.findByText('Saturday League')).toBeTruthy();
    expect(screen.getByText('Invited by Craig')).toBeTruthy();
    expect(screen.getByText('2 members')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/leagues/invite-preview/opaque-invite-token'),
      { cache: 'no-store' },
    );
    expect(screen.getByRole('link', { name: /create account/i })).toHaveAttribute(
      'href', '/register?next=%2Fjoin%2Fopaque-invite-token',
    );
  });

  it('keeps the invite claim path when the older API has no preview route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('opaque-invite-token');

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('heading', { name: 'Join the league' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /create account/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /already have an account/i })).toBeTruthy();
    expect(screen.queryByText(/invite.*invalid/i)).toBeNull();
  });

  it('does not request an invite preview for a reusable six-character code', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('ABC123');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the preview on mobile browser onboarding before installation', async () => {
    installState.isInstalled = false;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        league_name: 'Saturday League', inviter_name: 'Craig', member_count: 1,
      }),
    }));

    renderJoin('opaque-invite-token');

    expect(await screen.findByText('Saturday League')).toBeTruthy();
    expect(screen.getByText('Invited by Craig')).toBeTruthy();
    expect(screen.getByText('1 member')).toBeTruthy();
    expect(screen.getByRole('heading', { name: /one saturday pick/i })).toBeTruthy();
  });

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


  // Batch 124. An approval-gated league answers the join code with `pending`: the code
  // opened a *request*, not a membership. Navigating into the league on that answer
  // would land the member on a screen they are not yet allowed to see — and, worse,
  // tell them they are in when an admin has not yet said so.
  it('stays put and says a request was sent when the league is approval-gated', async () => {
    storeSignedInPlayer();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ league_slug: 'the-coupon', status: 'pending' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderJoin('abc123');
    fireEvent.click(screen.getByRole('button', { name: /join league/i }));

    expect(await screen.findByText(/request sent/i)).toBeTruthy();
    expect(screen.queryByText('Joined')).toBeNull();
  });

  // The membership list is cached for a minute and every coupon surface gates its
  // own query on it, so a join that left the stale copy in place landed the new member
  // on "You're not in a league yet" — the one screen they had just joined to reach.
  it('drops the cached membership list before landing on the league', async () => {
    storeSignedInPlayer();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ league_slug: 'the-coupon' }) }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // What the member had before joining: no leagues at all.
    queryClient.setQueryData(['leagues', 'mine'], []);

    renderJoin('abc123', queryClient);
    fireEvent.click(screen.getByRole('button', { name: /join league/i }));

    expect(await screen.findByText('Joined')).toBeTruthy();
    await waitFor(() => {
      expect(queryClient.getQueryData(['leagues', 'mine'])).toBeUndefined();
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
