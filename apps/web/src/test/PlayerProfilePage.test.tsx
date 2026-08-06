import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { PlayerProfilePage } from '@/pages/PlayerProfilePage';
import type { PlayerProfile } from '@/lib/types';

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const PROFILE: PlayerProfile = {
  player_id: 'p2',
  display_name: 'Bob',
  total_points: 43,
  picks_played: 4,
  picks_won: 3,
  rank: 2,
  win_rate_pct: 75,
  history: [
    {
      gameweek_id: 'gw1',
      starts_on: '2026-08-08',
      fixture_id: 'fx1',
      home: 'Arsenal',
      away: 'Chelsea',
      competition: 'English Premier League',
      market: 'MATCH_ODDS',
      outcome: 'HOME',
      runner_name: 'Arsenal',
      odds: 1.9,
      status: 'won',
      points_awarded: 19,
    },
    {
      gameweek_id: 'gw0',
      starts_on: '2026-08-01',
      fixture_id: 'fx2',
      home: 'Forfar Athletic',
      away: 'Brechin City',
      competition: 'Scottish League Two',
      market: 'BOTH_TEAMS_TO_SCORE',
      outcome: 'YES',
      runner_name: 'Yes',
      odds: 2.4,
      status: 'lost',
      points_awarded: 0,
    },
  ],
};

function stubFetch(profile: PlayerProfile | null) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/profile')) {
      return profile
        ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(profile) })
        : Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/leagues/the-coupon/players/p2']}>
        <AuthProvider>
          <Routes>
            <Route path="/leagues/:slug/players/:playerId" element={<PlayerProfilePage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
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
});

describe('PlayerProfilePage', () => {
  it('surfaces the league record including win rate', async () => {
    stubFetch(PROFILE);
    renderPage();
    const stats = await screen.findByTestId('profile-stats');
    expect(within(stats).getByText('43')).toBeTruthy();
    expect(within(stats).getByText('#2')).toBeTruthy();
    expect(within(stats).getByText('75%')).toBeTruthy();
    expect(within(stats).getByText('3/4')).toBeTruthy();
  });

  it('lists settled picks with their points and result', async () => {
    stubFetch(PROFILE);
    renderPage();
    const history = await screen.findByTestId('profile-history');
    const won = within(history).getByTestId('history-fx1');
    expect(won.textContent).toContain('Arsenal');
    expect(won.textContent).toContain('19 pts');
    expect(won.textContent).toContain('Won');

    const lost = within(history).getByTestId('history-fx2');
    expect(lost.textContent).toContain('Both teams score');
    expect(lost.textContent).toContain('Lost');
  });

  it('shows an untested record rather than a zero win rate', async () => {
    stubFetch({
      ...PROFILE,
      picks_played: 0,
      picks_won: 0,
      win_rate_pct: null,
      history: [],
    });
    renderPage();
    const stats = await screen.findByTestId('profile-stats');
    expect(within(stats).getByText('—')).toBeTruthy();
    expect(screen.getByText(/a win rate appears after the first result/i)).toBeTruthy();
    expect(screen.getByText('No settled picks yet')).toBeTruthy();
  });

  it('reports a player who is not in this league', async () => {
    stubFetch(null);
    renderPage();
    expect(await screen.findByText('Player not found')).toBeTruthy();
  });
});
