import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { FootballPage } from '@/pages/FootballPage';
import type { CompetitionTable, FormMatch, ResultEntry } from '@/lib/types';

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
    updated_at: '2026-08-06T06:30:00',
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
    updated_at: '2026-08-06T06:30:00',
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
    kickoff_utc: '2026-05-02T14:00:00',
    home: 'Chelsea FC',
    away: 'Arsenal FC',
    home_goals: 0,
    away_goals: 1,
  },
  {
    match_id: 'm108',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00',
    home: 'Liverpool FC',
    away: 'Everton FC',
    home_goals: 4,
    away_goals: 0,
  },
  {
    match_id: 'm105',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-04-25T14:00:00',
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
      <MemoryRouter initialEntries={['/football']}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/football" element={<FootballPage />} />
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

describe('FootballPage — tables', () => {
  it('renders a table per competition in the pool', async () => {
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

  it('keeps form visible at mobile width — the GD column hides instead', async () => {
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');
    const row = within(table).getByTestId('table-row-t-arsenal');
    const formCell = row.querySelector('td:last-child');
    expect(formCell?.className).not.toMatch(/\bhidden\b/);
    expect(screen.getAllByLabelText(/Arsenal FC form, oldest first/)[0]).toBeTruthy();
  });
});

// ── Opening a table row's form (Batch 53) ─────────────────────────────────────
//
// `recent` is optional on `TableEntry` and the shared fixture above omits it, which is
// also the deploy-gap case: Vercel ships this app from `main` while the API waits for
// `/ship-prod`, so for that window every row arrives without it and every run of pips
// stays the graphic it was.

const ARSENAL_RECENT: FormMatch[] = [
  {
    match_id: 'm107',
    kickoff_utc: '2026-05-02T14:00:00Z',
    opponent: 'Chelsea FC',
    home: false,
    goals_for: 1,
    goals_against: 0,
    result: 'W',
  },
  {
    match_id: 'm105',
    kickoff_utc: '2026-04-25T14:00:00Z',
    opponent: 'Tottenham Hotspur FC',
    home: true,
    goals_for: 2,
    goals_against: 1,
    result: 'W',
  },
];

const TABLES_WITH_FORM: CompetitionTable[] = [
  {
    ...TABLES[0],
    rows: TABLES[0].rows.map((row) =>
      row.team_id === 't-arsenal' ? { ...row, form: 'WW', recent: ARSENAL_RECENT } : row,
    ),
  },
];

describe('FootballPage — opening a table row’s form', () => {
  it('opens the matches behind the pips in a row of their own', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');

    fireEvent.click(within(table).getByLabelText(/Arsenal FC form, oldest first/));

    const panel = screen.getByRole('list', { name: /Arsenal FC recent results/ });
    expect(within(panel).getAllByRole('listitem').length).toBe(2);
    expect(panel.textContent).toContain('Tottenham Hotspur FC');

    // Across the whole table rather than inside the Form cell, which is five pips wide
    // on a phone and would push the table into sideways scrolling.
    const panelRow = within(table).getByTestId('form-matches-row-t-arsenal');
    expect(panelRow.contains(panel)).toBe(true);
    expect(panelRow.querySelector('td')?.getAttribute('colspan')).toBe('9');
    expect(within(table).getByTestId('table-row-t-arsenal').contains(panel)).toBe(false);
  });

  it('closes it again, and opens only one club at a time', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');
    const pips = within(table).getByLabelText(/Arsenal FC form, oldest first/);

    fireEvent.click(pips);
    expect(pips.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(pips);
    expect(pips.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('list', { name: /recent results/ })).toBeNull();
  });

  it('leaves a row with a form string but no stored matches inert', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await screen.findByTestId('league-table-england-premier-league');

    const chelsea = within(table).getByLabelText(/Chelsea FC form, oldest first/);
    expect(chelsea.tagName).not.toBe('BUTTON');
    expect(chelsea.getAttribute('role')).toBe('img');
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

  it('groups two competitions on one day into two competition headings', async () => {
    const mixedResults: ResultEntry[] = [
      ...RESULTS.filter((r) => r.match_id !== 'm105'),
      {
        match_id: 'm200',
        competition_id: 'scotland-league-two',
        competition: 'Scotland - Scottish League Two',
        kickoff_utc: '2026-05-02T14:00:00',
        home: 'Forfar Athletic FC',
        away: 'Edinburgh City FC',
        home_goals: 2,
        away_goals: 2,
      },
    ];
    stubFetch({ results: mixedResults });
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    fireEvent.click(screen.getByRole('tab', { name: 'Results' }));

    const list = await screen.findByTestId('football-results');
    const competitionHeadings = within(list).getAllByRole('heading', { level: 3 });
    expect(competitionHeadings.map((h) => h.textContent)).toEqual([
      'England - English Premier League',
      'Scotland - Scottish League Two',
    ]);
  });

  it('does not grow a redundant heading for a day with a single competition', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    fireEvent.click(screen.getByRole('tab', { name: 'Results' }));

    const list = await screen.findByTestId('football-results');
    expect(within(list).queryAllByRole('heading', { level: 3 })).toHaveLength(0);
  });
});

// ── Batch 51: no league anywhere on the screen ────────────────────────────

describe('FootballPage — untied from a league', () => {
  it('asks the slug-less endpoints, not a league-scoped pair', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/football/tables')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(TABLES) });
      }
      if (String(url).includes('/football/results')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(RESULTS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([MOCK_LEAGUE]),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    await screen.findByTestId('league-table-england-premier-league');

    const football = fetchMock.mock.calls
      .map(([url]) => String(url))
      .filter((url) => url.includes('/football/'));
    expect(football.some((url) => url.endsWith('/api/v1/football/tables'))).toBe(true);
    expect(football.some((url) => url.endsWith('/api/v1/football/results'))).toBe(true);
    expect(football.some((url) => url.includes('/leagues/'))).toBe(false);
  });

  it('names no league in the header, and carries neither switcher nor sub-nav', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');

    expect(screen.getByRole('heading', { name: 'Football Stats' })).toBeTruthy();
    expect(screen.queryByText(/the coupon/i)).toBeNull();
    expect(screen.queryByTestId('league-switch-strip')).toBeNull();
    expect(screen.queryByLabelText('Coupon sections')).toBeNull();
  });

  it('still reads for a member of no league at all', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/football/tables')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(TABLES) });
      }
      if (String(url).includes('/football/results')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(RESULTS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByTestId('league-table-england-premier-league')).toBeTruthy();
    expect(screen.queryByText("You're not in a league yet")).toBeNull();
  });

  it('says what "every competition" actually covers when there is nothing yet', async () => {
    stubFetch({ tables: [] });
    renderPage();

    const empty = await screen.findByText('No tables yet');
    expect(empty.parentElement?.textContent).toContain('not every competition in Britain');
  });
});
