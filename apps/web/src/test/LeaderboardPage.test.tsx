import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { LeaderboardPage } from '@/pages/LeaderboardPage';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';

vi.mock('@/lib/supabase', () => ({
  supabase: {
    channel: vi.fn(() => ({
      on: vi.fn().mockReturnThis(),
      subscribe: vi.fn(() => ({ unsubscribe: vi.fn() })),
    })),
    removeChannel: vi.fn(),
  },
}));

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const PLAYER = {
  id: 'p1',
  displayName: 'Alice Example',
  role: 'player',
  timezone: 'UTC',
};

const BASE_LEAGUE = {
  id: 'league-1',
  slug: 'steele-spreadsheet',
  name: 'The Steele Spreadsheet',
  description: 'Private league for spreadsheet loyalists',
  privacy: 'private' as const,
  member_count: 2,
  max_members: null,
  created_at: '2026-01-01T00:00:00Z',
  created_by: 'p1',
  join_code: 'STEELE',
};

const SECOND_LEAGUE = {
  id: 'league-2',
  slug: 'aib-sweepstake',
  name: 'AiB sweepstake',
  description: 'Private league for bankers',
  privacy: 'private' as const,
  member_count: 4,
  max_members: null,
  created_at: '2026-01-02T00:00:00Z',
  created_by: 'p2',
  join_code: 'AIB123',
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
}

function stubAuthStorage() {
  const store = new Map<string, string>([
    ['wc2026_player', JSON.stringify(PLAYER)],
    ['wc2026_access', FAKE_JWT],
  ]);
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key);
    }),
    clear: vi.fn(() => {
      store.clear();
    }),
  });
}

function stubFetch({
  leaderboard = [],
  members = [
    { id: 'p1', display_name: 'Alice Example', role: 'player', joined_at: '2026-01-01T00:00:00Z' },
    { id: 'p2', display_name: 'Bob Example', role: 'player', joined_at: '2026-01-02T00:00:00Z' },
  ],
  matches = [],
  leagues = [BASE_LEAGUE],
}: {
  leaderboard?: Array<Record<string, unknown>>;
  members?: Array<Record<string, unknown>>;
  matches?: Array<Record<string, unknown>>;
  leagues?: Array<Record<string, unknown>>;
}) {
  return vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (/\/api\/v1\/leagues\/[^/]+\/leaderboard$/.test(url)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(leaderboard) });
      }
      if (/\/api\/v1\/leagues\/[^/]+$/.test(url) && !url.endsWith('/api/v1/leagues/mine') && init?.method !== 'DELETE') {
        const slug = url.split('/').at(-1) ?? BASE_LEAGUE.slug;
        const league = leagues.find((entry) => entry.slug === slug) ?? BASE_LEAGUE;
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              ...league,
              members,
            }),
        });
      }
      if (/\/api\/v1\/leagues\/[^/]+\/membership$/.test(url) && init?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
      }
      if (/\/api\/v1\/leagues\/[^/]+$/.test(url) && !url.endsWith('/api/v1/leagues/mine') && init?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
      }
      if (url.endsWith('/api/v1/matches')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(matches) });
      }
      if (url.endsWith('/api/v1/leagues/mine')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(leagues) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    }),
  );
}

function renderLeaderboard() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={['/leagues/steele-spreadsheet/leaderboard']}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/leaderboard" element={<LeaderboardPage />} />
              <Route path="/leagues" element={<div>Leagues hub</div>} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LeaderboardPage', () => {
  beforeEach(() => {
    stubAuthStorage();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the league roster at 0 points before any results exist', async () => {
    stubFetch({ leaderboard: [] });

    renderLeaderboard();

    // shortenName renders "First L." format; members panel shows full names
    await waitFor(() => expect(screen.getByText('Alice E.')).toBeInTheDocument());
    expect(screen.getByText('Bob E.')).toBeInTheDocument();
    expect(screen.queryByText('No results entered yet')).not.toBeInTheDocument();
    expect(screen.getAllByText('0').length).toBeGreaterThan(2);
  });

  it('shows role-gated actions as inline buttons for members', async () => {
    stubFetch({ leaderboard: [] });

    renderLeaderboard();

    // LeagueActionsMenu renders inline buttons (not an overflow/kebab menu)
    await waitFor(() => expect(screen.getByRole('link', { name: /members/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /leave/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /settings/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('shows settings and delete for admins and opens the leave confirm dialog', async () => {
    const user = userEvent.setup({ delay: null });
    stubFetch({
      leaderboard: [],
      members: [
        { id: 'p1', display_name: 'Alice Example', role: 'admin', joined_at: '2026-01-01T00:00:00Z' },
        { id: 'p2', display_name: 'Bob Example', role: 'player', joined_at: '2026-01-02T00:00:00Z' },
      ],
    });

    renderLeaderboard();

    // Wait for league data to load — Settings/Delete only appear once isLeagueAdmin resolves.
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /members/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /leave/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /leave/i }));
    expect(await screen.findByRole('dialog', { name: 'Leave league' })).toBeInTheDocument();
  });

  it('opens the delete confirm dialog for admins', async () => {
    const user = userEvent.setup({ delay: null });
    stubFetch({
      leaderboard: [],
      members: [
        { id: 'p1', display_name: 'Alice Example', role: 'admin', joined_at: '2026-01-01T00:00:00Z' },
        { id: 'p2', display_name: 'Bob Example', role: 'player', joined_at: '2026-01-02T00:00:00Z' },
      ],
    });

    renderLeaderboard();

    await waitFor(() => expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /delete/i }));
    expect(await screen.findByRole('dialog', { name: 'Delete league' })).toBeInTheDocument();
  });

  it('keeps the player name cell untruncated in the mobile layout', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 375 });
    stubFetch({
      leaderboard: [
        {
          rank: 1,
          player_id: 'p1',
          player_name: 'Alexandria Spreadsheet-Cunningham',
          total_points: 0,
          match_points: 0,
          knockout_winner_points: 0,
          special_points: 0,
          is_active: true,
          last_match_points: 0,
          today_points: 0,
          round_points: 0,
        },
      ],
      members: [
        { id: 'p1', display_name: 'Alexandria Spreadsheet-Cunningham', role: 'player', joined_at: '2026-01-01T00:00:00Z' },
      ],
    });

    renderLeaderboard();

    // shortenName("Alexandria Spreadsheet-Cunningham") → "Alexandria S."
    const nameLink = await screen.findByRole('link', { name: 'Alexandria S.' });
    expect(nameLink.className).toContain('break-normal');
    expect(nameLink.className).toContain('whitespace-normal');
    expect(nameLink.className).not.toContain('truncate');

    const cols = document.querySelectorAll('colgroup col');
    expect(cols).toHaveLength(6);
    expect(cols[1].className).toBe('');

    const exHeader = screen.getByTitle('Exact scores');
    expect(exHeader.className).toContain('px-3');
  });

  it('shows the live standings banner while a match is in play', async () => {
    stubFetch({ leaderboard: [], matches: [{ id: 'm1', status: 'live' }] });

    renderLeaderboard();

    const banner = await screen.findByTestId('live-standings-banner');
    expect(banner).toHaveTextContent(/live/i);
    expect(banner).not.toHaveTextContent(/standings updating/i);
  });

  it('hides the live standings banner when no match is live', async () => {
    stubFetch({ leaderboard: [], matches: [{ id: 'm1', status: 'completed' }] });

    renderLeaderboard();

    await waitFor(() => expect(screen.getByText('Alice E.')).toBeInTheDocument());
    expect(screen.queryByTestId('live-standings-banner')).not.toBeInTheDocument();
  });

  it('shows a league hop strip for multi-league players and remembers the current league', async () => {
    stubFetch({
      leaderboard: [],
      leagues: [BASE_LEAGUE, SECOND_LEAGUE],
    });

    renderLeaderboard();

    const switchStrip = await screen.findByTestId('league-switch-strip');
    expect(switchStrip).toBeInTheDocument();
    expect(
      within(switchStrip).getByText('The Steele Spreadsheet').closest('[aria-current="page"]'),
    ).toBeTruthy();

    const otherLeagueLink = within(switchStrip).getByRole('link', { name: 'AiB sweepstake' });
    expect(otherLeagueLink.getAttribute('href')).toBe('/leagues/aib-sweepstake/leaderboard');

    await waitFor(() =>
      expect(window.localStorage.setItem).toHaveBeenCalledWith(
        LAST_VIEWED_LEAGUE_KEY,
        JSON.stringify({ slug: 'steele-spreadsheet', name: 'The Steele Spreadsheet' }),
      ),
    );

    const positionedStrip = screen.getByTestId('league-switch-strip');
    const heading = screen.getByRole('heading', { name: 'The Steele Spreadsheet' });
    expect(positionedStrip.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not show the league hop strip for single-league players', async () => {
    stubFetch({ leaderboard: [], leagues: [BASE_LEAGUE] });

    renderLeaderboard();

    await waitFor(() => expect(screen.getByText('Alice E.')).toBeInTheDocument());
    expect(screen.queryByTestId('league-switch-strip')).not.toBeInTheDocument();
  });

  it('preserves horizontal strip position when hopping between leagues', async () => {
    const user = userEvent.setup({ delay: null });
    stubFetch({ leaderboard: [], leagues: [BASE_LEAGUE, SECOND_LEAGUE] });

    renderLeaderboard();

    const scrollNav = await screen.findByTestId('league-switch-scroll');
    scrollNav.scrollLeft = 84;
    fireEvent.scroll(scrollNav);

    await user.click(
      within(screen.getByTestId('league-switch-strip')).getByRole('link', { name: 'AiB sweepstake' }),
    );

    await waitFor(() =>
      expect(
        within(screen.getByTestId('league-switch-strip'))
          .getByText('AiB sweepstake')
          .closest('[aria-current="page"]'),
      ).toBeTruthy(),
    );

    expect(window.sessionStorage.getItem('wc2026_league_switch_scroll')).toBe('84');
    expect(screen.getByTestId('league-switch-scroll').scrollLeft).toBe(84);
    expect(screen.getByText('Jump between tables')).toBeInTheDocument();
  });
});
