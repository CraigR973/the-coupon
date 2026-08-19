import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { CouponPickPage } from '@/pages/CouponPickPage';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';
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
  starts_on: '2026-08-08',
  status: 'open',
  locks_at_utc: '2999-01-01T14:30:00Z',
  picks_open_at_utc: null,
  fixtures: [
    {
      fixture_id: 'fx1',
      provider_event_id: 'ev1',
      home: 'Forfar',
      away: 'Brechin',
      competition_id: 'scotland-league-two',
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
      competition_id: 'england-premier-league',
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
      competition: 'Scottish League 2',
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
      competition: null,
      market: null,
      outcome: null,
      runner_name: null,
      odds: null,
    },
  ],
  members_missing_picks: 1,
  pick_scope: 'selection',
};

const GAMEWEEKS = [
  {
    gameweek_id: 'gw1',
    starts_on: '2026-08-08',
    status: 'open',
    locks_at_utc: '2999-01-01T14:30:00Z',
    picks_open_at_utc: null,
    fixture_count: 2,
    pick_count: 1,
  },
  {
    gameweek_id: 'gw0',
    starts_on: '2026-08-01',
    status: 'settled',
    locks_at_utc: '2026-08-01T13:30:00Z',
    picks_open_at_utc: null,
    fixture_count: 3,
    pick_count: 2,
  },
];

/** Backs `localStorage` with a real store, so writes (the recency key) can be read back. */
function stubAuth(): Record<string, string> {
  const store: Record<string, string> = {
    coupon_player: STORED_PLAYER,
    coupon_access: FAKE_JWT,
  };
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  });
  return store;
}

function stubFetchWithSlate() {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/gameweek/current')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
    }
    if (String(url).includes('/gameweeks')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

/** The same routes, with the slate patched — for the states the default one isn't in. */
function stubSlate(overrides: Partial<GameweekSlate>) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/gameweek/current')) {
      const slate = { ...SLATE, ...overrides };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(slate) });
    }
    if (String(url).includes('/gameweeks')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

function renderPage(entries: string[] = ['/leagues/the-coupon/predictions']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/predictions" element={<CouponPickPage />} />
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
  stubFetchWithSlate();
});

describe('CouponPickPage', () => {
  it('renders this Saturday’s fixtures from the slate', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /scottish league 2/i }));
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

  // ── Batch 27: a round that exists but has not opened ─────────────────────

  it('counts down to the opening, not to the lock, before picks open', async () => {
    stubSlate({ status: 'scheduled', picks_open_at_utc: '2999-01-01T14:00:00Z' });
    renderPage();

    const banner = await screen.findByTestId('lock-banner');
    expect(banner.textContent).toMatch(/picks open in/i);
    expect(banner.textContent).not.toMatch(/locked/i);
    // Nothing to grab yet, so the "you haven't picked" nudge stays out of the way.
    expect(screen.queryByText(/haven't grabbed a selection/i)).toBeNull();
  });

  it('treats a scheduled round whose opening has passed as open', async () => {
    // The hourly job has not relabelled it yet; the stored instant is the authority,
    // exactly as it is on the API side.
    stubSlate({ status: 'scheduled', picks_open_at_utc: '2020-01-01T14:00:00Z' });
    renderPage();

    const banner = await screen.findByTestId('lock-banner');
    expect(banner.textContent).toMatch(/picks lock in/i);
  });

  it('reads a settled round as settled even with an opening still ahead', async () => {
    stubSlate({ status: 'settled', picks_open_at_utc: '2999-01-01T14:00:00Z' });
    renderPage();

    const banner = await screen.findByTestId('lock-banner');
    expect(banner.textContent).toMatch(/settled/i);
  });

  it('groups the slate by competition slug, pyramid order first', async () => {
    renderPage();
    const epl = await screen.findByTestId('competition-england-premier-league');
    const sl2 = await screen.findByTestId('competition-scotland-league-two');
    const headings = screen
      .getAllByTestId(/^competition-/)
      .map((section) => within(section).getByRole('button', { expanded: false }).textContent ?? '');
    // The EPL group ranks above SL2 even when the Scottish game appears first in the payload.
    expect(headings[0]).toContain('English Premier League');
    expect(headings[1]).toContain('Scottish League 2');
    expect(epl.compareDocumentPosition(sl2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('orders unranked competitions by slate size after pyramid leagues', async () => {
    vi.stubGlobal('fetch', (url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              ...SLATE,
              fixtures: [
                ...SLATE.fixtures,
                {
                  ...SLATE.fixtures[1],
                  fixture_id: 'fx3',
                  provider_event_id: 'ev3',
                  competition_id: 'england-county-cup',
                  competition: 'English County Cup',
                  home: 'Barnet',
                  away: 'York',
                },
                {
                  ...SLATE.fixtures[1],
                  fixture_id: 'fx4',
                  provider_event_id: 'ev4',
                  competition_id: 'england-county-cup',
                  competition: 'English County Cup',
                  home: 'Halifax',
                  away: 'Oldham',
                },
                {
                  ...SLATE.fixtures[1],
                  fixture_id: 'fx5',
                  provider_event_id: 'ev5',
                  competition_id: 'wales-premier-league',
                  competition: 'Welsh Premier League',
                  home: 'Bangor',
                  away: 'Barry',
                },
              ],
            }),
        });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    renderPage();
    await screen.findByTestId('competition-england-premier-league');
    const headings = screen
      .getAllByTestId(/^competition-/)
      .map((section) => within(section).getByRole('button', { expanded: false }).textContent ?? '');

    expect(headings).toEqual([
      expect.stringContaining('English Premier League'),
      expect.stringContaining('Scottish League 2'),
      expect.stringContaining('English County Cup'),
      expect.stringContaining('Welsh Premier League'),
    ]);
  });

  it('keeps competitions collapsed until a member opens one', async () => {
    renderPage();
    await screen.findByRole('button', { name: /english premier league/i });
    expect(screen.queryByTestId('pick-card-fx1')).toBeNull();
    expect(screen.queryByTestId('pick-card-fx2')).toBeNull();
    const epl = screen
      .getAllByRole('button', { expanded: false })
      .find((b) => (b.textContent ?? '').includes('English Premier League'))!;
    fireEvent.click(epl);
    expect(screen.getByTestId('pick-card-fx2')).toBeTruthy();
    expect(screen.queryByTestId('pick-card-fx1')).toBeNull();
  });

  it('reports how many members are still to pick', async () => {
    renderPage();
    const roster = await screen.findByTestId('member-roster');
    expect(roster.textContent).toContain('1 of 2 picked');
    expect(roster.textContent).toContain('1 to go');
  });

  it('offers navigation back through the season', async () => {
    renderPage();
    const nav = await screen.findByTestId('gameweek-nav');
    // Newest gameweek: nothing newer to go to, but there is something older.
    expect(within(nav).getByLabelText('Newer gameweek')).toBeDisabled();
    expect(within(nav).getByLabelText('Older gameweek')).not.toBeDisabled();
    expect(nav.textContent).toContain('Open');
    // pick_count / fixture_count for the selected week.
    expect(nav.textContent).toContain('1/2');
  });

  it('requests the named gameweek and offers a way back to the latest', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage(['/leagues/the-coupon/predictions?gw=gw0']);
    const nav = await screen.findByTestId('gameweek-nav');

    await waitFor(() => {
      const asked = fetchMock.mock.calls.some(([url]) =>
        String(url).includes('/gameweek/current?gameweek_id=gw0'),
      );
      expect(asked).toBe(true);
    });

    // Viewing a past week: the header says so and a "latest" escape appears.
    expect(screen.getByText('Past coupon')).toBeTruthy();
    expect(within(nav).getByTestId('gameweek-latest')).toBeTruthy();
    expect(within(nav).getByLabelText('Older gameweek')).toBeDisabled();
  });

  it('lists every member and flags the ones yet to pick', async () => {
    renderPage();
    const roster = await screen.findByTestId('member-roster');
    fireEvent.click(within(roster).getByRole('button'));
    expect(screen.getByTestId('roster-p1').textContent).toContain('Draw');
    expect(screen.getByTestId('roster-p1').textContent).toContain('Scottish League 2');
    expect(within(screen.getByTestId('roster-p2')).getByText('Yet to pick')).toBeTruthy();
  });

  // ── Batch 29: league identity ─────────────────────────────────────────────

  it('names the bound league in the header', async () => {
    renderPage();
    await screen.findByTestId('lock-banner');
    expect(screen.getByText(/the coupon/i, { selector: 'p' })).toBeTruthy();
  });

  it('renders the league switcher when the member is in more than one league', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    vi.stubGlobal('fetch', (url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE, second]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    renderPage();
    expect(await screen.findByTestId('league-switch-strip')).toBeTruthy();
  });

  // ── Batch 34: switching without leaving the surface ───────────────────────

  it('switches league without leaving the pick screen', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    vi.stubGlobal('fetch', (url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE, second]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    renderPage();
    await screen.findByTestId('league-switch-strip');
    // Not `/leagues/friends-league/leaderboard`: a member changing league mid-pick is
    // choosing a different slate to play, not asking to read the standings.
    expect(screen.getByTitle('Open Friends League').getAttribute('href')).toBe(
      '/leagues/friends-league/predictions',
    );
  });

  it('does not fire the slate query and shows the no-league state for a member of no league', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByText("You're not in a league yet")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/gameweek/current'))).toBe(false);
  });

  // ── Batch 30: the URL names the league ────────────────────────────────────

  it('shows the league the URL names, not the one last viewed', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([MOCK_LEAGUE, second]),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    // `the-coupon` is first, so it is what a slug-less entry would have bound to.
    renderPage(['/leagues/friends-league/predictions']);

    expect(await screen.findByText(/friends league/i, { selector: 'p' })).toBeTruthy();
    await waitFor(() => {
      const asked = fetchMock.mock.calls.some(([url]) =>
        String(url).includes('/leagues/friends-league/gameweek/current'),
      );
      expect(asked).toBe(true);
    });
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/leagues/the-coupon/gameweek')),
    ).toBe(false);
  });

  it('remembers the league it was opened at, so a slug-less entry resumes there', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    vi.stubGlobal('fetch', (url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([MOCK_LEAGUE, second]),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    const store = stubAuth();
    renderPage(['/leagues/friends-league/predictions']);
    await screen.findByTestId('lock-banner');

    await waitFor(() => {
      expect(JSON.parse(store[LAST_VIEWED_LEAGUE_KEY]!).slug).toBe('friends-league');
    });
  });

  it('links the sub-nav inside the league it is showing', async () => {
    renderPage();
    await screen.findByTestId('lock-banner');

    const subNav = screen.getByLabelText('Coupon sections');
    expect(within(subNav).getByRole('link', { name: 'Results' }).getAttribute('href')).toBe(
      '/leagues/the-coupon/predictions/results',
    );
    expect(within(subNav).getByRole('link', { name: 'Football' }).getAttribute('href')).toBe(
      '/leagues/the-coupon/predictions/football',
    );
  });
});
