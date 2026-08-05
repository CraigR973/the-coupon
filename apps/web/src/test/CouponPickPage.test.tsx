import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { CouponPickPage } from '@/pages/CouponPickPage';
import type { GameweekSlate } from '@/lib/types';

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
const STORED_PLAYER = JSON.stringify({ id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' });

const SLATE: GameweekSlate = {
  gameweek_id: 'gw1',
  saturday_date: '2026-08-08',
  status: 'open',
  locks_at_utc: '2999-01-01T14:30:00Z',
  fixtures: [
    {
      fixture_id: 'fx1',
      provider_event_id: 'ev1',
      home: 'Forfar',
      away: 'Brechin',
      competition: 'Scottish League 2',
      kickoff_utc: '2026-08-08T14:00:00Z',
      selections: [
        { market: 'MATCH_ODDS', outcome: 'HOME', runner_name: 'Forfar', odds: 2.0, taken_by_player_id: null, taken_by_name: null, mine: false },
        { market: 'MATCH_ODDS', outcome: 'DRAW', runner_name: 'The Draw', odds: 3.5, taken_by_player_id: 'p1', taken_by_name: 'Alice', mine: true },
      ],
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

function stubFetchWithSlate() {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/gameweek/current')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/predictions']}>
        <AuthProvider>
          <LeagueProvider>
            <CouponPickPage />
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
  stubFetchWithSlate();
});

describe('CouponPickPage', () => {
  it('renders this Saturday’s fixtures from the slate', async () => {
    renderPage();
    const card = await screen.findByTestId('pick-card-fx1');
    expect(within(card).getByText('Scottish League 2')).toBeTruthy();
    expect(within(card).getByText('Brechin')).toBeTruthy();
  });

  it('surfaces the caller’s current pick', async () => {
    renderPage();
    const summary = await screen.findByTestId('my-pick-summary');
    expect(within(summary).getByText('Draw')).toBeTruthy();
    expect(within(summary).getByText('3.50')).toBeTruthy();
  });

  it('shows the countdown-to-lock banner while the gameweek is open', async () => {
    renderPage();
    const banner = await screen.findByTestId('lock-banner');
    expect(banner.textContent).toMatch(/picks lock in/i);
  });
});
