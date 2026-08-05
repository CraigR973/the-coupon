import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
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
      taken_by_names: ['Alice'],
      mine: true,
    },
    {
      fixture_id: 'fx2',
      provider_event_id: 'ev2',
      home: 'Arsenal',
      away: 'Chelsea',
      competition: 'English Premier League',
      kickoff_utc: '2026-08-08T12:30:00Z',
      selections: [
        { market: 'MATCH_ODDS', outcome: 'HOME', runner_name: 'Arsenal', odds: 1.9, taken_by_player_id: null, taken_by_name: null, mine: false },
      ],
      taken_by_names: [],
      mine: false,
    },
  ],
  members: [
    {
      player_id: 'p1',
      display_name: 'Alice',
      has_picked: true,
      fixture_id: 'fx1',
      home: 'Forfar',
      away: 'Brechin',
      market: 'MATCH_ODDS',
      outcome: 'DRAW',
      runner_name: 'The Draw',
      odds: 3.5,
    },
    {
      player_id: 'p2',
      display_name: 'Bob',
      has_picked: false,
      fixture_id: null,
      home: null,
      away: null,
      market: null,
      outcome: null,
      runner_name: null,
      odds: null,
    },
  ],
  members_missing_picks: 1,
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

  it('groups the slate by competition, earliest kick-off first', async () => {
    renderPage();
    await screen.findByTestId('pick-card-fx1');
    const headings = screen
      .getAllByRole('button', { expanded: true })
      .map((b) => b.textContent ?? '');
    // Arsenal v Chelsea kicks off at 12:30, Forfar at 14:00.
    expect(headings[0]).toContain('English Premier League');
    expect(headings[1]).toContain('Scottish League 2');
  });

  it('collapses a competition without unmounting the others', async () => {
    renderPage();
    await screen.findByTestId('pick-card-fx1');
    const epl = screen
      .getAllByRole('button', { expanded: true })
      .find((b) => (b.textContent ?? '').includes('English Premier League'))!;
    fireEvent.click(epl);
    expect(screen.queryByTestId('pick-card-fx2')).toBeNull();
    expect(screen.getByTestId('pick-card-fx1')).toBeTruthy();
  });

  it('reports how many members are still to pick', async () => {
    renderPage();
    const roster = await screen.findByTestId('member-roster');
    expect(roster.textContent).toContain('1 of 2 picked');
    expect(roster.textContent).toContain('1 to go');
  });

  it('lists every member and flags the ones yet to pick', async () => {
    renderPage();
    const roster = await screen.findByTestId('member-roster');
    fireEvent.click(within(roster).getByRole('button'));
    expect(within(screen.getByTestId('roster-p1')).getByText('Draw')).toBeTruthy();
    expect(within(screen.getByTestId('roster-p2')).getByText('Yet to pick')).toBeTruthy();
  });
});
