import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { CareerProfilePage } from '@/pages/CareerProfilePage';
import type { CrossLeagueSummary } from '@/lib/types';

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const SUMMARY: CrossLeagueSummary = {
  avg_rank: 2.0,
  avg_rank_leagues: 2,
  total_points: 57,
  picks_played: 5,
  picks_won: 3,
  win_rate_pct: 60,
  leagues_count: 2,
  per_league: [
    {
      slug: 'the-coupon',
      name: 'The Coupon',
      member_count: 4,
      rank: 1,
      total_points: 38,
      picks_played: 3,
      picks_won: 2,
      current_round: null,
    },
    {
      slug: 'work-league',
      name: 'Work League',
      member_count: 8,
      rank: 3,
      total_points: 19,
      picks_played: 2,
      picks_won: 1,
      current_round: null,
    },
  ],
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

function stubFetch(summary: CrossLeagueSummary = SUMMARY) {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(summary) }),
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/profile']}>
        <AuthProvider>
          <Routes>
            <Route path="/profile" element={<CareerProfilePage />} />
          </Routes>
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

describe('CareerProfilePage', () => {
  it('aggregates points and win rate across every league', async () => {
    renderPage();
    const stats = await screen.findByTestId('career-stats');
    expect(stats.textContent).toContain('57');
    expect(stats.textContent).toContain('60%');
    expect(stats.textContent).toContain('3/5');
  });

  it('breaks rank down per league rather than only averaging it', async () => {
    renderPage();
    const leagues = await screen.findByTestId('career-leagues');
    const rows = leagues.querySelectorAll('li');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('The Coupon');
    expect(rows[0].textContent).toContain('#1 of 4');
    expect(rows[1].textContent).toContain('#3 of 8');
  });

  it("links each league row into that league's own record", async () => {
    renderPage();
    const row = await screen.findByTestId('career-league-work-league');
    expect(row.getAttribute('href')).toBe('/leagues/work-league/players/p1');
  });

  it('says how many leagues the average rank actually covers', async () => {
    stubFetch({ ...SUMMARY, avg_rank: 1.0, avg_rank_leagues: 1 });
    renderPage();
    expect(await screen.findByText(/Averaged over 1 of your 2 leagues/)).toBeTruthy();
  });

  it('explains a missing average rather than showing a misleading number', async () => {
    stubFetch({ ...SUMMARY, avg_rank: null, avg_rank_leagues: 0 });
    renderPage();
    const stats = await screen.findByTestId('career-stats');
    expect(stats.textContent).toContain('—');
    expect(screen.getByText(/at least 3 members/)).toBeTruthy();
  });

  it('shows a dash for win rate before anything has settled', async () => {
    stubFetch({ ...SUMMARY, win_rate_pct: null, picks_played: 0, picks_won: 0 });
    renderPage();
    const stats = await screen.findByTestId('career-stats');
    expect(stats.textContent).toContain('0/0');
  });
});
