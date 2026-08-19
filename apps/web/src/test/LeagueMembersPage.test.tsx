import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { LeagueMembersPage } from '@/pages/LeagueMembersPage';

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    player: {
      id: 'admin-id',
      displayName: 'Test Admin',
      role: 'admin',
      timezone: 'UTC',
    },
  }),
}));

const MEMBERS = [
  {
    id: 'admin-id',
    display_name: 'Test Admin',
    role: 'admin',
    joined_at: '2026-07-01T00:00:00Z',
    avatar_url: null,
  },
  {
    id: 'player-id',
    display_name: 'Test Player',
    role: 'player',
    joined_at: '2026-07-02T00:00:00Z',
    avatar_url: null,
  },
];

const VALID_JWT =
  'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbi1pZCIsImV4cCI6OTk5OTk5OTk5OX0.fake';

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/leagues/the-coupon/admin/members']}>
        <LeagueProvider>
          <Routes>
            <Route
              path="/leagues/:slug/admin/members"
              element={<LeagueMembersPage />}
            />
          </Routes>
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  localStorage.setItem('coupon_access', VALID_JWT);
});

describe('LeagueMembersPage', () => {
  it('uses the API id and display_name fields for admin actions', async () => {
    const fetchMock = vi.fn((_url: string, options?: RequestInit) => {
      if (options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 204,
          json: () => Promise.resolve(undefined),
        });
      }
      // `LeagueProvider` wraps the page since Batch 34; without its own answer it
      // would read the member list as the member's leagues.
      if (String(_url).includes('/leagues/mine')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([{ slug: 'the-coupon', name: 'The Coupon' }]),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(MEMBERS),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    expect(await screen.findByText('Test Player')).toBeInTheDocument();
    expect(screen.getByText('You')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Promote' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          '/api/v1/leagues/the-coupon/members/player-id/promote',
        ),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });
});
