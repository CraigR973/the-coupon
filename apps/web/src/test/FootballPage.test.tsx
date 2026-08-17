import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { FootballPage } from '@/pages/FootballPage';
import type { CompetitionTable, ResultEntry } from '@/lib/types';

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

const TABLES: CompetitionTable[] = [
  {
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    season: 2025,
    updated_at: '2026-08-06T06:30:00Z',
    rows: [
      {
        position: 1,
        team_id: 't-arsenal',
        team: 'Arsenal FC',
        played: 38,
        won: 26,
        drawn: 8,
        lost: 4,
        goals_for: 84,
        goals_against: 32,
        goal_difference: 52,
        points: 86,
        form: 'WWDWW',
      },
      {
        position: 2,
        team_id: 't-chelsea',
        team: 'Chelsea FC',
        played: 38,
        won: 23,
        drawn: 7,
        lost: 8,
        goals_for: 71,
        goals_against: 40,
        goal_difference: 31,
        points: 76,
        form: 'WLWDW',
      },
    ],
  },
  {
    competition_id: 'scotland-league-two',
    competition: 'Scotland - Scottish League Two',
    season: 2025,
    updated_at: '2026-08-06T06:30:00Z',
    rows: [
      {
        position: 1,
        team_id: 't-forfar',
        team: 'Forfar Athletic FC',
        played: 36,
        won: 20,
        drawn: 8,
        lost: 8,
        goals_for: 58,
        goals_against: 39,
        goal_difference: 19,
        points: 68,
        form: 'WDWWL',
      },
    ],
  },
];

const RESULTS: ResultEntry[] = [
  {
    match_id: 'm107',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00Z',
    home: 'Chelsea FC',
    away: 'Arsenal FC',
    home_goals: 0,
    away_goals: 1,
  },
  {
    match_id: 'm108',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00Z',
    home: 'Liverpool FC',
    away: 'Everton FC',
    home_goals: 4,
    away_goals: 0,
  },
  {
    match_id: 'm105',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-04-25T14:00:00Z',
    home: 'Arsenal FC',
    away: 'Tottenham Hotspur FC',
    home_goals: 2,
    away_goals: 1,
  },
];

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

function stubFetch({
  tables = TABLES,
  results = RESULTS,
}: { tables?: CompetitionTable[]; results?: ResultEntry[] } = {}) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/football/tables')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(tables) });
    }
    if (String(url).includes('/football/results')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(results) });
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
      <MemoryRouter initialEntries={['/predictions/football']}>
        <AuthProvider>
          <LeagueProvider>
            <FootballPage />
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

describe('FootballPage — tables', () => {
  it('renders a table per competition the league plays', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    expect(screen.getByTestId('league-table-scotland-league-two')).toBeTruthy();
  });

  it('shows the standings figures in position order', async () => {
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');
    const rows = within(table).getAllByRole('row').slice(1); // drop the header
    expect(within(rows[0]).getByRole('rowheader').textContent).toBe('Arsenal FC');
    expect(rows[0].textContent).toContain('+52');
    expect(rows[0].textContent).toContain('86');
    expect(within(rows[1]).getByRole('rowheader').textContent).toBe('Chelsea FC');
  });

  it('says when the table was last ingested — nothing here is live', async () => {
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');
    expect(table.textContent).toMatch(/As of 6 Aug, 06:30/);
  });

  it('opens only the first competition, so thirty divisions stay scannable', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    const [first, second] = screen.getAllByRole('button', { name: /premier league|league two/i });
    expect(first.getAttribute('aria-expanded')).toBe('true');
    expect(second.getAttribute('aria-expanded')).toBe('false');
  });

  it('expands a collapsed competition on tap', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    const scotland = screen.getAllByRole('button', { expanded: false })[0];
    fireEvent.click(scotland);
    expect(screen.getByTestId('table-row-t-forfar')).toBeTruthy();
  });

  it('explains an empty section rather than showing a blank page', async () => {
    stubFetch({ tables: [] });
    renderPage();
    expect(await screen.findByText('No tables yet')).toBeTruthy();
  });
});

describe('FootballPage — results', () => {
  it('lists previous results grouped by day, newest day first', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    fireEvent.click(screen.getByRole('tab', { name: 'Results' }));

    const list = await screen.findByTestId('football-results');
    const days = within(list).getAllByRole('heading', { level: 2 });
    expect(days[0].textContent).toBe('Saturday 2 May');
    expect(days[1].textContent).toBe('Saturday 25 April');
  });

  it('shows each score against the two clubs', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    fireEvent.click(screen.getByRole('tab', { name: 'Results' }));

    const result = await screen.findByTestId('result-m107');
    expect(result.textContent).toContain('Chelsea FC');
    expect(result.textContent).toContain('Arsenal FC');
    expect(result.textContent).toContain('0–1');
  });

  it('reads the score out unambiguously for screen readers', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    fireEvent.click(screen.getByRole('tab', { name: 'Results' }));

    const result = await screen.findByTestId('result-m107');
    expect(within(result).getByText('Chelsea FC 0, Arsenal FC 1')).toBeTruthy();
  });

  it('explains an empty results list', async () => {
    stubFetch({ results: [] });
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Results' }));
    expect(await screen.findByText('No results yet')).toBeTruthy();
  });
});

// ── Batch 29: league identity ─────────────────────────────────────────────

describe('FootballPage — league identity', () => {
  it('names the bound league in the header', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    expect(screen.getByText(/the coupon/i, { selector: 'p' })).toBeTruthy();
  });

  it('shows the no-league state and skips the football queries for a member of no league', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByText("You're not in a league yet")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/football/'))).toBe(false);
  });
});
