import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { CurrentRoundPage } from '@/pages/CurrentRoundPage';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';
import type { Coupon, GameweekSlate } from '@/lib/types';

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
  locks_at_utc: '2999-01-01T14:30:00',
  picks_open_at_utc: null,
  fixtures: [
    {
      fixture_id: 'fx1',
      provider_event_id: 'ev1',
      home: 'Forfar',
      away: 'Brechin',
      competition_id: 'scotland-league-two',
      competition: 'Scottish League 2',
      kickoff_utc: '2026-08-08T14:00:00',
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
      kickoff_utc: '2026-08-08T12:30:00',
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

/**
 * The same round, read from the other endpoint the merged surface now calls.
 *
 * Alice's draw is one leg; Bob appears nowhere in it, which is the whole reason the
 * screen also reads the slate's members — a coupon cannot name who is missing.
 */
const COUPON: Coupon = {
  gameweek_id: 'gw1',
  status: 'open',
  leg_count: 1,
  combined_odds: 3.5,
  legs: [
    {
      player_id: 'p1',
      player_name: 'Alice',
      fixture_id: 'fx1',
      home: 'Forfar',
      away: 'Brechin',
      competition: 'Scottish League 2',
      market: 'MATCH_ODDS',
      outcome: 'DRAW',
      runner_name: 'The Draw',
      odds: 3.5,
      status: 'pending',
    },
  ],
  all_won: null,
};

const GAMEWEEKS = [
  {
    gameweek_id: 'gw1',
    starts_on: '2026-08-08',
    status: 'open',
    locks_at_utc: '2999-01-01T14:30:00',
    picks_open_at_utc: null,
    fixture_count: 2,
    pick_count: 1,
  },
  {
    gameweek_id: 'gw0',
    starts_on: '2026-08-01',
    status: 'settled',
    locks_at_utc: '2026-08-01T13:30:00',
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
    if (String(url).includes('/coupon')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COUPON) });
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
function stubSlate(overrides: Partial<GameweekSlate>, couponOverrides: Partial<Coupon> = {}) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/gameweek/current')) {
      const slate = { ...SLATE, ...overrides };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(slate) });
    }
    if (String(url).includes('/coupon')) {
      const value = { ...COUPON, ...couponOverrides };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(value) });
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

/**
 * An instant `minutes` from now, in the offset-less shape the API sends.
 *
 * Relative rather than fixed because the assertion is about *now* — a hardcoded 2026
 * date stops being two hours away the day after it is written.
 */
function naiveUtc(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString().slice(0, 19);
}

function renderPage(entries: string[] = ['/leagues/the-coupon/predictions']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/predictions" element={<CurrentRoundPage />} />
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

describe('CurrentRoundPage', () => {
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

  it('names the competition on the caller’s current pick', async () => {
    // Batch 50. The combined coupon already printed the competition on every leg —
    // this summary was the one surface out of step with its neighbour.
    renderPage();
    const summary = await screen.findByTestId('my-pick-summary');
    expect(within(summary).getByText(/Scottish League 2/)).toBeTruthy();
  });

  it('shows the countdown-to-lock clock while the gameweek is open', async () => {
    renderPage();
    const clock = await screen.findByTestId('round-clock');
    expect(clock.textContent).toMatch(/picks lock in/i);
  });

  // ── Batch 43: the lock is an instant, not a wall-clock number ────────────
  //
  // `useCountdown` drives `locked`, which disables every selection, so an instant read
  // in the wrong zone does not just mislabel the banner — it decides whether the member
  // can pick at all, while the API goes on applying the real one. These tests run in
  // `America/New_York` (see `vite.config.ts`), where reading the API's offset-less
  // string as local time moves the lock four hours later.

  it('locks the screen on a round the API has already locked', async () => {
    stubSlate({ locks_at_utc: naiveUtc(-60) });
    renderPage();

    const clock = await screen.findByTestId('round-clock');
    expect(clock.textContent).toMatch(/picks are locked/i);
  });

  it('counts down to the real lock instant, not to the same numbers read locally', async () => {
    stubSlate({ locks_at_utc: naiveUtc(120) });
    renderPage();

    const clock = await screen.findByTestId('round-clock');
    // Two hours away: "1h 59m 5?s". Parsed as local time it would read about 5h 59m.
    expect(clock.textContent).toMatch(/picks lock in 1h 5\dm/i);
  });

  // ── Batch 48: prices the API could not refresh ───────────────────────────

  it('warns that prices may be out of date when the API says they are degraded', async () => {
    stubSlate({ odds_degraded: true });
    renderPage();

    const banner = await screen.findByTestId('odds-degraded-banner');
    expect(banner.textContent).toMatch(/out of date/i);
    // Still a working card underneath — degrading is the whole point.
    fireEvent.click(await screen.findByRole('button', { name: /scottish league 2/i }));
    expect(await screen.findByTestId('pick-card-fx1')).toBeTruthy();
  });

  it('says nothing about staleness on a healthy slate', async () => {
    renderPage();
    await screen.findByTestId('round-status');
    expect(screen.queryByTestId('odds-degraded-banner')).toBeNull();
  });

  // ── Batch 27: a round that exists but has not opened ─────────────────────

  it('counts down to the opening, not to the lock, before picks open', async () => {
    stubSlate({ status: 'scheduled', picks_open_at_utc: '2999-01-01T14:00:00' });
    renderPage();

    const clock = await screen.findByTestId('round-clock');
    expect(clock.textContent).toMatch(/picks open in/i);
    expect(clock.textContent).not.toMatch(/locked/i);
    // Nothing to grab yet, so the nudge to go and grab one stays out of the way.
    expect(screen.queryByText(/grab a selection below/i)).toBeNull();
  });

  it('treats a scheduled round whose opening has passed as open', async () => {
    // The hourly job has not relabelled it yet; the stored instant is the authority,
    // exactly as it is on the API side.
    stubSlate({ status: 'scheduled', picks_open_at_utc: '2020-01-01T14:00:00' });
    renderPage();

    const clock = await screen.findByTestId('round-clock');
    expect(clock.textContent).toMatch(/picks lock in/i);
  });

  it('reads a settled round as settled even with an opening still ahead', async () => {
    stubSlate({ status: 'settled', picks_open_at_utc: '2999-01-01T14:00:00' });
    renderPage();

    const status = await screen.findByTestId('round-status');
    expect(status.textContent).toMatch(/settled/i);
    // Settlement is not a countdown, so the round stops carrying a clock at all.
    expect(screen.queryByTestId('round-clock')).toBeNull();
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
    const progress = await screen.findByTestId('round-progress');
    expect(progress.textContent).toContain('1 of 2 picked');
    expect(progress.textContent).toContain('1 to go');
  });

  it('offers navigation back through the season', async () => {
    renderPage();
    const nav = await screen.findByTestId('gameweek-nav');
    // Newest gameweek: nothing newer to go to, but there is something older.
    expect(within(nav).getByLabelText('Newer gameweek')).toBeDisabled();
    expect(within(nav).getByLabelText('Older gameweek')).not.toBeDisabled();
    expect(nav.textContent).toContain('Open');
    // pick_count / fixture_count for the selected week.
    expect(nav.textContent).toContain('1 pick');
  });

  it('follows the round the API resolved to, not the top of the list', async () => {
    // Batch 35: the API's default is the round the league is *currently on*, which is
    // no longer the newest `starts_on`. A one-off added for Boxing Day sits at the top
    // of the season list; the nav must still label the round the card below is showing,
    // and offer it as something to navigate *forward* to.
    const ONE_OFF = {
      gameweek_id: 'gw-boxing-day',
      starts_on: '2026-12-26',
      status: 'open',
      locks_at_utc: '2999-01-01T14:30:00',
      picks_open_at_utc: null,
      fixture_count: 5,
      pick_count: 0,
    };
    vi.stubGlobal('fetch', (url: string) => {
      if (String(url).includes('/gameweek/current')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(SLATE) });
      }
      if (String(url).includes('/gameweeks')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([ONE_OFF, ...GAMEWEEKS]),
        });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    renderPage();
    const nav = await screen.findByTestId('gameweek-nav');

    // `gw1`'s counts, not the one-off's 0/5 — the label follows the slate.
    await waitFor(() => expect(nav.textContent).toContain('1 pick'));
    expect(nav.textContent).toContain('Aug 2026');
    // Both directions are reachable: the one-off ahead, the settled week behind.
    expect(within(nav).getByLabelText('Newer gameweek')).not.toBeDisabled();
    expect(within(nav).getByLabelText('Older gameweek')).not.toBeDisabled();
    // No `gw` parameter, so this is still the default view.
    expect(within(nav).queryByTestId('gameweek-latest')).toBeNull();
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
    // Batch 105: the coupon's legs and the roster's absentees are one list now, so a
    // member reading it can see both what was taken and who the deadline would catch.
    renderPage();
    const claimed = await screen.findByTestId('acca-leg-0');
    expect(claimed.textContent).toContain('Draw');
    expect(claimed.textContent).toContain('Scottish League 2');
    expect(within(screen.getByTestId('acca-leg-1')).getByText('Bob')).toBeTruthy();
    expect(within(screen.getByTestId('acca-leg-1')).getByText('Yet to pick')).toBeTruthy();
  });

  // ── Batch 78: one round, one list ─────────────────────────────────────────

  it('draws the caller’s own selection in one summary and one list, not three', async () => {
    renderPage();
    // Batch 78 kept the member's own bet off two of three drawings; Batch 105 left one
    // summary and one list, and the fixtures stay collapsed behind their competitions.
    const summary = await screen.findByTestId('my-pick-summary');
    expect(within(summary).getByText('Draw')).toBeTruthy();
    expect(screen.queryByTestId('pick-card-fx1')).toBeNull();
  });

  it('marks the caller’s own leg and nobody else’s', async () => {
    renderPage();
    expect(within(await screen.findByTestId('acca-leg-0')).getByText('You')).toBeTruthy();
    expect(within(screen.getByTestId('acca-leg-1')).queryByText('You')).toBeNull();
  });

  // ── Batch 29: league identity ─────────────────────────────────────────────

  it('names the bound league in the header', async () => {
    renderPage();
    await screen.findByTestId('round-status');
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
    await screen.findByTestId('round-status');

    await waitFor(() => {
      expect(JSON.parse(store[LAST_VIEWED_LEAGUE_KEY]!).slug).toBe('friends-league');
    });
  });

  it('links the sub-nav inside the league it is showing', async () => {
    renderPage();
    await screen.findByTestId('round-status');

    const subNav = screen.getByLabelText('Coupon sections');
    expect(
      within(subNav).getByRole('link', { name: 'Current round' }).getAttribute('href'),
    ).toBe('/leagues/the-coupon/predictions');
    expect(within(subNav).getByRole('link', { name: 'Season' }).getAttribute('href')).toBe(
      '/leagues/the-coupon/predictions/results',
    );
    // Batch 105: the combined coupon is a section of the current round, not a third tab.
    expect(within(subNav).queryByRole('link', { name: /combined coupon/i })).toBeNull();
  });

  it('no longer offers Football Stats here — Batch 51 made it a top-level tab', async () => {
    renderPage();
    await screen.findByTestId('round-status');

    const subNav = screen.getByLabelText('Coupon sections');
    expect(within(subNav).queryByRole('link', { name: /football/i })).toBeNull();
  });
});

/**
 * Batch 105 — one surface that orders itself by what the round is doing.
 *
 * The two screens this replaced could not do this: `Your pick` led with the fixture list
 * whether or not a pick was still possible, and `Combined coupon` led with a fold whether
 * or not the coupon was worth having. The states below are the whole argument for merging
 * them, so each one is pinned here.
 */
describe('the round’s phase decides what leads', () => {
  /** The same slate with nobody's claim on it — the state a member opens the app in. */
  function unclaimed(): Partial<GameweekSlate> {
    return {
      fixtures: SLATE.fixtures.map((fixture) => ({
        ...fixture,
        mine: false,
        taken_by_names: [],
        selections: fixture.selections.map((selection) => ({
          ...selection,
          mine: false,
          taken_by_player_id: null,
          taken_by_name: null,
        })),
      })),
      members: SLATE.members.map((member) => ({ ...member, has_picked: false })),
      members_missing_picks: 2,
    };
  }

  /** Every member in, which is what makes the coupon worth copying. */
  function everyoneIn(): Partial<GameweekSlate> {
    return {
      members: SLATE.members.map((member) => ({ ...member, has_picked: true })),
      members_missing_picks: 0,
    };
  }

  function order() {
    const coupon = screen.getByTestId('coupon-section');
    const slate = screen.getByTestId('slate-section');
    return coupon.compareDocumentPosition(slate) & Node.DOCUMENT_POSITION_FOLLOWING
      ? 'coupon-first'
      : 'slate-first';
  }

  it('asks for a pick, and leads with the slate, while the member holds none', async () => {
    stubSlate(unclaimed(), { leg_count: 0, legs: [] });
    renderPage();

    expect(await screen.findByText('Pick required')).toBeTruthy();
    expect(screen.getByTestId('my-pick-summary').textContent).toMatch(/grab a selection below/i);
    expect(order()).toBe('slate-first');
  });

  it('says the pick is in, and still leads with the slate, while others are missing', async () => {
    renderPage();
    expect(await screen.findByText('Pick submitted')).toBeTruthy();
    expect(order()).toBe('slate-first');
  });

  it('leads with the completed coupon once every member has picked', async () => {
    stubSlate(everyoneIn());
    renderPage();

    expect(await screen.findByText('Coupon complete')).toBeTruthy();
    expect(order()).toBe('coupon-first');
    expect(screen.getByRole('button', { name: /copy text/i })).toBeTruthy();
    expect(screen.getByTestId('round-progress').textContent).toContain('2 of 2 picked');
  });

  it('labels a round the deadline caught incomplete rather than complete', async () => {
    // The honesty case. One member never picked, claiming has stopped, and the coupon on
    // screen is a one-fold that a two-member league will never add to.
    stubSlate({ locks_at_utc: naiveUtc(-60) });
    renderPage();

    expect(await screen.findByText('Incomplete coupon')).toBeTruthy();
    expect(screen.getByTestId('round-progress').textContent).toContain('1 never picked');
    expect(screen.getByTestId('coupon-section').textContent).toMatch(/1 of 2 never picked/i);
    expect(order()).toBe('coupon-first');
  });

  it('leads with the outcome once the round has settled', async () => {
    stubSlate({ status: 'settled' }, { status: 'settled', all_won: false });
    renderPage();

    expect(await screen.findByText('Round settled')).toBeTruthy();
    expect(order()).toBe('coupon-first');
    expect(screen.getByRole('button', { name: /copy result/i })).toBeTruthy();
    // The member's own leg stays identifiable in the result.
    expect(within(screen.getByTestId('acca-leg-0')).getByText('You')).toBeTruthy();
  });
});

/**
 * The copy section's address. Batch 107's all-picked notification deep-links to it, and
 * every combined-coupon link minted before this batch redirects into it, so it has to be
 * a real destination on the page rather than a place the reader has to go looking for.
 */
describe('the copy section', () => {
  it('answers at #coupon and takes focus when the URL names it', async () => {
    renderPage(['/leagues/the-coupon/predictions#coupon']);

    const section = await screen.findByTestId('coupon-section');
    expect(section.id).toBe('coupon');
    await waitFor(() => expect(document.activeElement).toBe(section));
  });

  it('is not focused when the URL does not name it', async () => {
    renderPage();
    const section = await screen.findByTestId('coupon-section');
    expect(document.activeElement).not.toBe(section);
  });
});
