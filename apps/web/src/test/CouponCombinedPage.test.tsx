import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { CouponCombinedPage } from '@/pages/CouponCombinedPage';
import type { Coupon } from '@/lib/types';

const MOCK_LEAGUE = {
  slug: 'the-coupon',
  name: 'The Coupon',
  description: null,
  privacy: 'private',
  member_count: 2,
  max_members: null,
  created_at: '2026-01-01T00:00:00Z',
};

// Far-future exp so apiFetch's ensureFreshToken never tries to refresh.
const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const COUPON: Coupon = {
  gameweek_id: 'gw1',
  status: 'open',
  leg_count: 1,
  combined_odds: 2.0,
  legs: [
    {
      player_id: 'p1',
      player_name: 'Alice',
      fixture_id: 'fx1',
      home: 'Forfar',
      away: 'Brechin',
      competition: 'Scottish League 2',
      market: 'MATCH_ODDS',
      outcome: 'HOME',
      runner_name: 'Forfar',
      odds: 2.0,
      status: 'pending',
    },
  ],
  all_won: null,
};

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

function stubFetch(leagues: unknown[] = [MOCK_LEAGUE]) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/coupon')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COUPON) });
    }
    if (String(url).includes('/gameweeks')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(leagues) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

function renderPage(entry = '/leagues/the-coupon/predictions/coupon') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route
                path="/leagues/:slug/predictions/coupon"
                element={<CouponCombinedPage />}
              />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
  stubFetch();
});

describe('CouponCombinedPage — league identity', () => {
  it('names the bound league in the header', async () => {
    renderPage();
    await screen.findByTestId('acca-leg-0');
    expect(screen.getByText(/the coupon/i, { selector: 'p' })).toBeTruthy();
  });

  it('renders the league switcher when the member is in more than one league', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    stubFetch([MOCK_LEAGUE, second]);
    renderPage();
    expect(await screen.findByTestId('league-switch-strip')).toBeTruthy();
  });

  /**
   * Presence is not the property that matters, and asserting it alone is how the
   * strip kept `LeaderboardPage`'s destination through two batches aimed here: it
   * rendered on the coupon and pointed away from it, so switching league meant
   * leaving the surface you were reading. Assert where it goes.
   */
  it('switches league without leaving the combined coupon', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    stubFetch([MOCK_LEAGUE, second]);
    renderPage();

    await screen.findByTestId('league-switch-strip');
    const link = screen.getByTitle('Open Friends League');
    expect(link.getAttribute('href')).toBe('/leagues/friends-league/predictions/coupon');
  });

  it('drops the browsed gameweek when switching league', async () => {
    // `?gw=` names a round of the league being left; the destination 404s on it and
    // renders "No coupon this week yet" — a worse landing than the standings were.
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    stubFetch([MOCK_LEAGUE, second]);
    renderPage('/leagues/the-coupon/predictions/coupon?gw=gw-owned-by-the-coupon');

    await screen.findByTestId('league-switch-strip');
    const link = screen.getByTitle('Open Friends League');
    expect(link.getAttribute('href')).toBe('/leagues/friends-league/predictions/coupon');
  });

  it('shows the no-league state and skips the coupon query for a member of no league', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByText("You're not in a league yet")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/coupon'))).toBe(false);
  });
});
